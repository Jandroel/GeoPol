"""Synthetic cartography extraction; no external requests or institutional records."""

import json

import pytest
from shapely.geometry import Point, Polygon, mapping, shape

from geopol.catalogs import read_catalog
from geopol.reference_builder import (
    LocalSelector,
    ReferenceCollector,
    Territories,
    at_grade,
    build,
    clip_street,
    read_osm,
)
from geopol.reference_download import download_boundaries


def territories():
    return Territories(
        {
            "features": [
                {
                    "properties": {"IDDIST": "010101", "NOMBDIST": "SINTETICO", "OBJECTID": 1},
                    "geometry": mapping(Polygon([(0, 0), (3, 0), (3, 3), (0, 3), (0, 0)])),
                }
            ]
        },
        {"010101"},
        "test-boundary",
    )


def test_fuzzy_selector_keeps_competitors_in_the_same_district():
    selector = LocalSelector({"010101": ["AV. DEMOSTRACION"], "020101": ["CALLE OTRA"]}, 80)
    assert selector.matches(["Avenida Demostración"], "010101")
    assert selector.matches(["Demostraclon"], "010101")
    assert not selector.matches(["Avenida Demostración"], "020101")
    assert selector.matches(["Nombre distinto", "AV DEMOSTRACION"], "010101")
    assert not LocalSelector({"010101": ["UNO"]}, 80).matches(["1"], "010101")


def test_extraction_preserves_real_geometry_numbers_and_at_grade_topology():
    collector = ReferenceCollector(territories(), LocalSelector(), "test-osm")
    collector.node(10, 1, 1, {"addr:street": "Avenida Alfa", "addr:housenumber": "12A"}, 3)
    collector.node(11, 1, 1, {"name": "Hospital Sintetico", "amenity": "hospital"}, 4)
    collector.way(
        20, [(1, 0, 1), (2, 1, 1), (3, 4, 1)], {"name": "Avenida Alfa", "highway": "residential"}, 2
    )
    collector.way(21, [(2, 1, 1), (4, 1, 2)], {"name": "Calle Beta", "highway": "residential"}, 1)
    collector.way(
        22, [(2, 1, 1), (5, 2, 2)], {"name": "Calle Puente", "highway": "residential", "bridge": "yes"}, 1
    )
    collector.way(
        23,
        [(6, 1, 1), (7, 2, 1), (8, 2, 2), (6, 1, 1)],
        {
            "name": "Edificio con dirección",
            "building": "yes",
            "addr:street": "Alfa",
            "addr:housenumber": "999",
        },
        1,
    )
    features = collector.finish()
    doors = [f for f in features if f["properties"]["kind"] == "door"]
    assert len(doors) == 1
    assert doors[0]["properties"]["door_number"] == "12A"
    assert doors[0]["properties"]["osm_id"] == 10
    assert shape(doors[0]["geometry"]).equals(Point(1, 1))
    intersections = [f for f in features if f["properties"]["kind"] == "intersection"]
    assert len(intersections) == 1
    assert intersections[0]["properties"]["osm_way_ids"] == [20, 21]
    assert intersections[0]["properties"]["connects_at_grade"] is True
    assert shape(intersections[0]["geometry"]).equals(Point(1, 1))
    road = next(
        f
        for f in features
        if f["properties"].get("street_name") == "ALFA" and f["properties"]["kind"] == "street"
    )
    assert shape(road["geometry"]).bounds == (0, 1, 3, 1)  # actual segment inside the unmodified boundary
    assert road["properties"]["clip_boundary_version"] == "test-boundary"
    assert "latitude" not in road["properties"]
    assert (
        next(f for f in features if f["properties"]["kind"] == "site")["properties"]["point_role"]
        == "mapped_poi"
    )


@pytest.mark.parametrize(
    "tags", [{"layer": "1"}, {"level": "-1"}, {"tunnel": "yes"}, {"bridge": "viaduct"}, {"covered": "yes"}]
)
def test_grade_separation_never_becomes_an_at_grade_intersection(tags):
    assert not at_grade(tags)


def test_boundary_tangency_does_not_invent_a_street_segment():
    from shapely.geometry import LineString

    assert clip_street(LineString([(-1, -1), (0, 0)]), territories().geometries[0]) is None


def test_catalog_preserves_each_feature_provenance_and_explicit_aliases():
    feature = territories().features[0]
    feature["properties"]["aliases"] = ["Distrito explícito"]
    parsed = list(
        read_catalog(
            json.dumps({"type": "FeatureCollection", "features": [feature]}).encode(),
            "mixed.geojson",
            "GLOBAL SOURCE",
            "GLOBAL VERSION",
        )
    )[0]
    assert parsed["source"] == "MINAM GeoServidor / Limites Politico Referenciales"
    assert parsed["version"] == "test-boundary"
    assert parsed["aliases"] == ["DISTRITO EXPLICITO"]
    assert parsed["crs"] == "EPSG:4326"


@pytest.mark.parametrize("kind,geometry", [("street", Point(1, 1)), ("manzana", Point(1, 1))])
def test_new_catalog_kinds_require_their_actual_geometry(kind, geometry):
    document = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"id": "synthetic", "kind": kind, "ubigeo": "010101"},
                "geometry": mapping(geometry),
            }
        ],
    }
    with pytest.raises(ValueError, match="incompatible"):
        list(read_catalog(json.dumps(document).encode(), "synthetic.geojson", "test", "1"))


def test_boundary_pagination_is_national_and_complete(tmp_path, monkeypatch):
    from urllib.parse import parse_qs, urlparse
    from geopol import reference_download

    calls = []

    def get(url):
        calls.append(url)
        query = parse_qs(urlparse(url).query)
        if "/query?" not in url:
            return {"sourceSpatialReference": {"wkid": 32718}}
        assert query["where"] == ["1=1"]
        if "returnCountOnly" in query:
            return {"count": 2}
        assert query["outSR"] == ["4326"]
        offset = int(query["resultOffset"][0])
        return {
            "type": "FeatureCollection",
            "features": [{"id": offset + 1, "properties": {"OBJECTID": offset + 1}, "geometry": None}],
        }

    monkeypatch.setattr(reference_download, "public_json", get)
    result = download_boundaries(tmp_path, page_size=1)
    assert result["feature_count"] == 2
    assert len(result["pages"]) == 2
    assert result["referential"] is True
    assert len(calls) == 4
    # Second invocation verifies cached bytes and makes no new requests.
    assert download_boundaries(tmp_path, page_size=1)["sha256"] == result["sha256"]
    assert len(calls) == 4


def test_osmium_adapter_reads_real_osm_xml_structure(tmp_path):
    pytest.importorskip("osmium")
    path = tmp_path / "synthetic.osm"
    path.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
    <osm version="0.6" generator="synthetic-test">
      <node id="1" version="1" lat="1" lon="1"><tag k="addr:street" v="Calle Prueba"/><tag k="addr:housenumber" v="10"/></node>
      <node id="2" version="1" lat="1" lon="2"/>
      <way id="3" version="1"><nd ref="1"/><nd ref="2"/><tag k="highway" v="residential"/><tag k="name" v="Calle Prueba"/></way>
    </osm>""",
        encoding="utf-8",
    )
    collector = ReferenceCollector(territories(), LocalSelector(), "test")
    read_osm(path, collector)
    result = collector.finish()
    assert {f["properties"]["kind"] for f in result} == {"boundary", "door", "street"}


def test_repeated_offline_build_has_identical_catalog_and_reports_size_limit(tmp_path):
    pytest.importorskip("osmium")
    source = tmp_path / "synthetic.osm"
    source.write_text(
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<osm version="0.6" generator="synthetic-test">'
        '<node id="1" version="1" lat="1" lon="1">'
        '<tag k="addr:street" v="Calle Prueba"/>'
        '<tag k="addr:housenumber" v="10"/></node>'
        '<node id="2" version="1" lat="1" lon="2"/>'
        '<way id="3" version="1"><nd ref="1"/><nd ref="2"/>'
        '<tag k="highway" v="residential"/>'
        '<tag k="name" v="Calle Prueba"/></way></osm>',
        encoding="utf-8",
    )
    boundaries = tmp_path / "boundary.geojson"
    boundaries.write_text(
        json.dumps({"type": "FeatureCollection", "features": territories().features}),
        encoding="utf-8",
    )
    ubigeos = tmp_path / "ubigeos.json"
    ubigeos.write_text(json.dumps(["010101"]), encoding="utf-8")
    selector = tmp_path / "selector.json"
    selector.write_text(json.dumps({"010101": ["CALLE PRUEBA"]}), encoding="utf-8")

    first = build(source, boundaries, ubigeos, tmp_path / "first", selector)
    second = build(source, boundaries, ubigeos, tmp_path / "second", selector, max_bytes=1)

    assert (tmp_path / "first/catalog.geojson").read_bytes() == (
        tmp_path / "second/catalog.geojson"
    ).read_bytes()
    assert first["catalog_sha256"] == second["catalog_sha256"]
    assert first["source_files"] == second["source_files"]
    assert first["local_selector"] == second["local_selector"]
    assert first["counts_by_kind"] == {"boundary": 1, "door": 1, "street": 1}
    assert first["within_import_limits"] is True
    assert second["within_import_limits"] is False
    assert second["features"] == first["features"]  # Never hide features to fit the limit.
