"""Build local reference catalogs from downloaded OSM and referential district polygons.

No web requests occur here. Optional selectors contain local search names by
UBIGEO; fuzzy filtering keeps every name/explicit alias with similarity >= cutoff.
Roads retain their actual geometry within each reference boundary. No house
numbers, block boundaries or centroids are inferred. Install optional
`osmium==4.3.1` to read .osm.pbf/.osm input.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
from itertools import combinations
import json
from pathlib import Path
import re
import time

from rapidfuzz import fuzz, process
from shapely.geometry import LineString, Point, Polygon, mapping, shape
from shapely.ops import linemerge, unary_union
from shapely.strtree import STRtree

from .catalogs import read_catalog, search_key
from .domain import RULES_VERSION
from .domain.normalization import street_parts
from .reference_download import MINAM_URL, OSM_LICENSE, OSM_URL, save_json, sha256_file, utc_now

BUILDER_VERSION = "2026.1"
ALIASES = ("alt_name", "official_name", "loc_name", "short_name")
ROAD_EXCLUSIONS = {"construction", "proposed", "abandoned", "razed", "platform", "elevator", "steps"}
POI_TAGS = {"amenity", "shop", "tourism", "leisure", "office", "historic", "healthcare", "railway", "aeroway"}
NUCLEUS_PLACES = {"suburb", "neighbourhood", "quarter", "hamlet", "village", "town"}


def name_key(value):
    return street_parts(value)[1] or search_key(value)


def explicit_aliases(tags):
    return sorted(
        {value.strip() for key in ALIASES for value in tags.get(key, "").split(";") if value.strip()}
    )


def at_grade(tags):
    return (
        tags.get("bridge", "no") in {"no", "false", "0"}
        and tags.get("tunnel", "no") in {"no", "false", "0"}
        and tags.get("layer", "0") == "0"
        and tags.get("level", "0") == "0"
        and tags.get("covered", "no") in {"no", "false", "0"}
    )


class LocalSelector:
    def __init__(self, names=None, cutoff=80):
        if not 0 <= cutoff <= 100:
            raise ValueError("Similarity cutoff must be between 0 and 100")
        self.cutoff = cutoff
        self.names = (
            None
            if names is None
            else {
                code: tuple(sorted({name_key(value) for value in values if name_key(value)}))
                for code, values in names.items()
            }
        )
        self.all_names = tuple(sorted({name for values in (self.names or {}).values() for name in values}))
        self.cache = {}

    def matches(self, names, ubigeo=None):
        if self.names is None:
            return True
        keys = tuple(sorted({name_key(name) for name in names if name_key(name)}))
        cache_key = (ubigeo, keys)
        if cache_key not in self.cache:
            choices = self.all_names if ubigeo is None else self.names.get(ubigeo, ())
            self.cache[cache_key] = any(
                process.extractOne(name, choices, scorer=fuzz.ratio, score_cutoff=self.cutoff)
                for name in keys
            )
        return self.cache[cache_key]


class Territories:
    def __init__(self, document, wanted, version):
        self.features, self.geometries, self.codes = [], [], []
        self.issues = Counter()
        seen = set()
        for raw in document["features"]:
            props = raw.get("properties") or {}
            code = str(props.get("IDDIST", props.get("ubigeo", ""))).strip()
            if code not in wanted:
                continue
            if not re.fullmatch(r"\d{6}", code) or code in seen:
                raise ValueError("District UBIGEO is invalid or duplicated in boundary source")
            seen.add(code)
            try:
                geometry = shape(raw["geometry"])
            except (ValueError, TypeError, KeyError):
                self.issues["invalid_boundary"] += 1
                continue
            if (
                geometry.geom_type not in {"Polygon", "MultiPolygon"}
                or geometry.is_empty
                or not geometry.is_valid
            ):
                self.issues["invalid_boundary"] += 1
                continue
            self.codes.append(code)
            self.geometries.append(geometry)
            self.features.append(
                {
                    "type": "Feature",
                    "geometry": mapping(geometry),
                    "properties": {
                        "id": f"minam:district:{code}",
                        "kind": "boundary",
                        "ubigeo": code,
                        "name": props.get("NOMBDIST", code),
                        "source": "MINAM GeoServidor / Limites Politico Referenciales",
                        "version": version,
                        "source_url": MINAM_URL,
                        "source_objectid": props.get("OBJECTID", raw.get("id")),
                        "crs": "EPSG:4326",
                        "referential": True,
                        "temporal_validity": "NOT_DECLARED",
                        "license": "NOT_DECLARED_IN_SERVICE",
                        "geometry_transform": "ArcGIS outSR=4326; no local simplification",
                    },
                }
            )
        self.missing = sorted(set(wanted) - set(self.codes))
        self.tree = STRtree(self.geometries)
        self.by_code = dict(zip(self.codes, self.geometries, strict=True))
        self.version = version

    def assign(self, geometry):
        return [self.codes[int(index)] for index in self.tree.query(geometry, predicate="intersects")]


def clip_street(geometry, boundary):
    """Keep only genuine line portions; a tangent point is never a street."""
    clipped = geometry.intersection(boundary)
    parts = []

    def collect(value):
        if value.geom_type == "LineString" and value.length > 0:
            parts.append(value)
        elif hasattr(value, "geoms"):
            for part in value.geoms:
                collect(part)

    collect(clipped)
    return unary_union(parts) if parts else None


def _feature(properties, geometry):
    return {"type": "Feature", "properties": properties, "geometry": mapping(geometry)}


class ReferenceCollector:
    """Pure extraction policy; the osmium adapter only supplies immutable objects."""

    def __init__(self, territories, selector, version):
        self.territories, self.selector, self.version = territories, selector, version
        self.features = []
        self.roads = defaultdict(list)
        self.junctions = defaultdict(dict)
        self.stats = Counter()

    def provenance(self, kind, identifier, object_version=None):
        result = {
            "source": "OpenStreetMap contributors / Geofabrik",
            "version": self.version,
            "crs": "EPSG:4326",
            "license": "ODbL-1.0",
            "license_url": OSM_LICENSE,
            "source_url": f"https://www.openstreetmap.org/{kind}/{identifier}",
            "osm_type": kind,
            "osm_id": identifier,
        }
        if object_version is not None:
            result["osm_version"] = object_version
        return result

    def node(self, identifier, lon, lat, tags, object_version=None):
        self.stats["nodes_seen"] += 1
        address = tags.get("addr:street")
        house_number = tags.get("addr:housenumber")
        poi = tags.get("name") if POI_TAGS.intersection(tags) else None
        aliases = explicit_aliases(tags)
        names = [value for value in (address, poi, *aliases) if value]
        if not names or not self.selector.matches(names):
            return
        point = Point(lon, lat)
        for code in self.territories.assign(point):
            if address and house_number and self.selector.matches([address], code):
                street_type, street_name = street_parts(address)
                props = dict(
                    self.provenance("node", identifier, object_version),
                    id=f"osm:node:{identifier}:door:{code}",
                    kind="door",
                    ubigeo=code,
                    street_name=street_name,
                    door_number=house_number,
                    point_role="explicit_address_node",
                    address_number_origin="addr:housenumber",
                )
                if street_type:
                    props["street_type"] = street_type
                self.features.append(_feature(props, point))
            if poi and self.selector.matches([poi, *aliases], code):
                self.features.append(
                    _feature(
                        dict(
                            self.provenance("node", identifier, object_version),
                            id=f"osm:node:{identifier}:site:{code}",
                            kind="site",
                            ubigeo=code,
                            name=poi,
                            aliases=aliases,
                            point_role="mapped_poi",
                        ),
                        point,
                    )
                )

    def way(self, identifier, nodes, tags, object_version=None):
        self.stats["ways_seen"] += 1
        name = tags.get("name")
        if not name or len(nodes) < 2:
            return
        aliases = explicit_aliases(tags)
        if not self.selector.matches([name, *aliases]):
            return
        coords = [(node[1], node[2]) for node in nodes]
        road = bool(
            tags.get("highway") and tags["highway"] not in ROAD_EXCLUSIONS and tags.get("area") != "yes"
        )
        if road:
            geometry = LineString(coords)
            if geometry.is_empty or not geometry.is_valid or geometry.length == 0:
                self.stats["invalid_osm_way"] += 1
                return
            street_type, street_name = street_parts(name)
            for code in self.territories.assign(geometry):
                if not self.selector.matches([name, *aliases], code):
                    continue
                clipped = clip_street(geometry, self.territories.by_code[code])
                if clipped is None:
                    continue
                self.roads[(code, street_type, street_name)].append(
                    (clipped, identifier, object_version, aliases)
                )
                if at_grade(tags):
                    for node, lon, lat in nodes:
                        self.junctions[(code, node, lon, lat)][(street_type, street_name)] = {
                            "way": identifier,
                            "name": street_name,
                            "type": street_type,
                            "aliases": aliases,
                        }
            return
        if nodes[0][0] != nodes[-1][0] or len(nodes) < 4:
            return
        kind = (
            "nucleus"
            if tags.get("place") in NUCLEUS_PLACES
            else "site"
            if POI_TAGS.intersection(tags)
            else None
        )
        if kind:
            self.area(identifier, Polygon(coords), tags, "way", object_version)

    def area(self, identifier, geometry, tags, object_type="relation", object_version=None):
        name, aliases = tags.get("name"), explicit_aliases(tags)
        kind = (
            "nucleus"
            if tags.get("place") in NUCLEUS_PLACES
            else "site"
            if POI_TAGS.intersection(tags)
            else None
        )
        if not kind or not name or not self.selector.matches([name, *aliases]):
            return
        if (
            geometry.is_empty
            or not geometry.is_valid
            or geometry.geom_type not in {"Polygon", "MultiPolygon"}
        ):
            self.stats["invalid_osm_area"] += 1
            return
        for code in self.territories.assign(geometry):
            if self.selector.matches([name, *aliases], code):
                self.features.append(
                    _feature(
                        dict(
                            self.provenance(object_type, identifier, object_version),
                            id=f"osm:{object_type}:{identifier}:{kind}:{code}",
                            kind=kind,
                            ubigeo=code,
                            name=name,
                            aliases=aliases,
                            geometry_origin="mapped_closed_way_or_multipolygon",
                        ),
                        geometry,
                    )
                )

    def finish(self):
        for (code, street_type, street_name), pieces in sorted(
            self.roads.items(), key=lambda item: (item[0][0], item[0][1] or "", item[0][2])
        ):
            merged = unary_union([piece[0] for piece in pieces])
            if merged.geom_type == "MultiLineString":
                merged = linemerge(merged)
            if merged.geom_type not in {"LineString", "MultiLineString"}:
                self.stats["unsupported_merged_road"] += 1
                continue
            key = hashlib.sha256(f"{code}|{street_type}|{street_name}".encode()).hexdigest()[:20]
            props = {
                "id": f"osm:street:{key}",
                "kind": "street",
                "ubigeo": code,
                "street_name": street_name,
                "source": "OpenStreetMap contributors / Geofabrik",
                "version": self.version,
                "source_url": OSM_URL,
                "crs": "EPSG:4326",
                "license": "ODbL-1.0",
                "license_url": OSM_LICENSE,
                "osm_way_ids": sorted({piece[1] for piece in pieces}),
                "aliases": sorted({alias for piece in pieces for alias in piece[3]}),
                "geometry_transform": "clip_to_boundary: exact intersection, union and line merge; no simplification",
                "clip_boundary_id": f"minam:district:{code}",
                "clip_boundary_version": self.territories.version,
                "multiple_components": merged.geom_type == "MultiLineString",
            }
            if street_type:
                props["street_type"] = street_type
            self.features.append(_feature(props, merged))
        for (code, node, lon, lat), streets in sorted(self.junctions.items()):
            if len(streets) < 2 or code not in self.territories.assign(Point(lon, lat)):
                continue
            for left, right in combinations(
                sorted(streets.values(), key=lambda x: (x["name"], x["type"] or "")), 2
            ):
                if left["name"] == right["name"] and left["type"] == right["type"]:
                    continue
                pair = hashlib.sha256(
                    f"{left['type']}|{left['name']}|{right['type']}|{right['name']}".encode()
                ).hexdigest()[:16]
                props = dict(
                    self.provenance("node", node),
                    id=f"osm:intersection:{node}:{pair}:{code}",
                    kind="intersection",
                    ubigeo=code,
                    street_name=left["name"],
                    cross_street=right["name"],
                    aliases=left["aliases"],
                    cross_aliases=right["aliases"],
                    connects_at_grade=True,
                    osm_way_ids=sorted([left["way"], right["way"]]),
                    topology_evidence="Shared OSM node; both ways layer/level=0 and no bridge/tunnel/covered tags",
                )
                if left["type"]:
                    props["street_type"] = left["type"]
                self.features.append(_feature(props, Point(lon, lat)))
        result = self.territories.features + self.features
        # Defensive de-duplication of multipolygon/closed-way adapter emissions.
        return list({feature["properties"]["id"]: feature for feature in result}.values())


def read_osm(path, collector):
    import osmium

    factory = osmium.geom.GeoJSONFactory()

    class Handler(osmium.SimpleHandler):
        def node(self, obj):
            if obj.tags and obj.location.valid():
                collector.node(obj.id, obj.location.lon, obj.location.lat, dict(obj.tags), obj.version)

        def way(self, obj):
            tags = dict(obj.tags)
            if not tags.get("name") or not collector.selector.matches(
                [tags["name"], *explicit_aliases(tags)]
            ):
                return
            if not (
                tags.get("highway") or POI_TAGS.intersection(tags) or tags.get("place") in NUCLEUS_PLACES
            ):
                return
            try:
                nodes = [(node.ref, node.lon, node.lat) for node in obj.nodes]
            except osmium.InvalidLocationError:
                collector.stats["missing_osm_node_location"] += 1
                return
            collector.way(obj.id, nodes, tags, obj.version)

        def area(self, obj):
            if obj.from_way():
                return  # Closed ways handled above; relations retain their real rings.
            tags = dict(obj.tags)
            if not tags.get("name") or not (
                POI_TAGS.intersection(tags) or tags.get("place") in NUCLEUS_PLACES
            ):
                return
            if collector.selector.matches([tags["name"], *explicit_aliases(tags)]):
                try:
                    collector.area(
                        obj.orig_id(),
                        shape(json.loads(factory.create_multipolygon(obj))),
                        tags,
                        "relation",
                        obj.version,
                    )
                except (RuntimeError, ValueError):
                    collector.stats["invalid_osm_relation"] += 1

    Handler().apply_file(str(path), locations=True, idx="flex_mem")
    with osmium.io.Reader(str(path)) as reader:
        return reader.header().get("osmosis_replication_timestamp") or None


def build(pbf, boundaries, ubigeos, output, selector_path=None, cutoff=80, max_bytes=24 * 1024**2):
    started = time.perf_counter()
    pbf, boundaries, output = Path(pbf), Path(boundaries), Path(output)
    wanted = set(json.loads(Path(ubigeos).read_text(encoding="utf-8")))
    if not wanted or any(not isinstance(code, str) or not re.fullmatch(r"\d{6}", code) for code in wanted):
        raise ValueError("UBIGEO selector must be a nonempty JSON array of six-digit strings")
    names = json.loads(Path(selector_path).read_text(encoding="utf-8")) if selector_path else None
    if names is not None and (
        not isinstance(names, dict)
        or any(
            not isinstance(values, list) or any(not isinstance(value, str) for value in values)
            for values in names.values()
        )
    ):
        raise ValueError("Name selector must map district codes to lists of names")
    with pbf.open("rb"):
        pass
    osm_sha, boundary_sha = sha256_file(pbf), sha256_file(boundaries)
    version = f"osm-sha256:{osm_sha[:16]}"
    territories = Territories(
        json.loads(boundaries.read_text(encoding="utf-8")), wanted, f"minam-sha256:{boundary_sha[:16]}"
    )
    collector = ReferenceCollector(territories, LocalSelector(names, cutoff), version)
    osm_timestamp = read_osm(pbf, collector)
    features = collector.finish()
    output.mkdir(parents=True, exist_ok=True)
    document = {"type": "FeatureCollection", "features": features}
    catalog = output / "catalog.geojson"
    save_json(catalog, document)
    # Exercise the real importer before declaring the artifact usable.
    validated = list(
        read_catalog(catalog.read_bytes(), catalog.name, "Mixed public references", BUILDER_VERSION)
    )
    per_kind = Counter(feature["kind"] for feature in validated)
    coverage = defaultdict(Counter)
    for feature in validated:
        coverage[feature["ubigeo"]][feature["kind"]] += 1
    manifest = {
        "builder_version": BUILDER_VERSION,
        "builder_sha256": sha256_file(__file__),
        "normalizer_rules_version": RULES_VERSION,
        "built_at": utc_now(),
        "catalog_sha256": sha256_file(catalog),
        "catalog_bytes": catalog.stat().st_size,
        "features": len(validated),
        "counts_by_kind": dict(per_kind),
        "source_files": {
            "osm": {
                "sha256": osm_sha,
                "url": OSM_URL,
                "license": "ODbL-1.0",
                "replication_timestamp": osm_timestamp,
            },
            "boundary": {
                "sha256": boundary_sha,
                "url": MINAM_URL,
                "referential": True,
                "license": "NOT_DECLARED_IN_SERVICE",
            },
        },
        "local_selector": {
            "ubigeos_sha256": sha256_file(ubigeos),
            "names_sha256": sha256_file(selector_path) if selector_path else None,
            "district_count": len(wanted),
            "criterion": "Any primary name or explicit OSM alias; rapidfuzz.ratio >= cutoff, same district",
            "cutoff": cutoff if selector_path else None,
            "transmitted_to_external_services": False,
        },
        "missing_or_invalid_boundary_districts": territories.missing,
        "boundary_issues": dict(territories.issues),
        "coverage_by_ubigeo": {code: dict(counts) for code, counts in sorted(coverage.items())},
        "processing_stats": dict(collector.stats),
        "within_import_limits": catalog.stat().st_size <= max_bytes and len(validated) <= 100_000,
        "configured_max_bytes": max_bytes,
        "elapsed_seconds": round(time.perf_counter() - started, 3),
        "limitations": [
            "Reference boundaries, not legal jurisdiction certification",
            "No completeness guarantee for streets, doors, POIs or districts",
            "No inferred house numbers or street block numbering",
            "No manzana polygons generated from buildings",
            "Street geometry is intersected with the referential district polygon; source ways remain in raw PBF",
            "No simplification of district boundaries",
        ],
    }
    save_json(output / "manifest.json", manifest)
    print(
        json.dumps(
            {
                key: manifest[key]
                for key in (
                    "catalog_bytes",
                    "features",
                    "counts_by_kind",
                    "within_import_limits",
                    "elapsed_seconds",
                )
            },
            ensure_ascii=False,
        )
    )
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for argument in ("pbf", "boundaries", "ubigeos", "output"):
        parser.add_argument("--" + argument, type=Path, required=True)
    parser.add_argument("--selector", type=Path)
    parser.add_argument("--cutoff", type=float, default=80)
    parser.add_argument("--max-bytes", type=int, default=24 * 1024**2)
    args = parser.parse_args()
    build(args.pbf, args.boundaries, args.ubigeos, args.output, args.selector, args.cutoff, args.max_bytes)


if __name__ == "__main__":
    main()
