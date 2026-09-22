"""Acquire public national cartography; no case data or selectors enter requests."""

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen

OSM_URL = "https://download.geofabrik.de/south-america/peru-latest.osm.pbf"
MINAM_URL = "https://geoservidorperu.minam.gob.pe/arcgis/rest/services/ServicioPMIZMC/MapServer/8"
OSM_LICENSE = "https://www.openstreetmap.org/copyright"


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024**2), b""):
            digest.update(block)
    return digest.hexdigest()


def save_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    temporary.replace(path)


def public_json(url):
    for attempt in range(3):
        try:
            request = Request(url, headers={"User-Agent": "GeoPol-public-reference-builder/0.1"})
            with urlopen(request, timeout=180) as response:
                payload = json.load(response)
            if payload.get("error"):
                raise ValueError("Public cartography service returned an error")
            return payload
        except (OSError, ValueError):
            if attempt == 2:
                raise
            time.sleep(1 + attempt)


def download_osm(folder):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / "peru-latest.osm.pbf"
    manifest_path = folder / "osm-source.json"
    if target.exists() and manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if sha256_file(target) == manifest["sha256"]:
            return manifest
        raise ValueError("Cached OSM snapshot checksum mismatch")
    request = Request(OSM_URL, headers={"User-Agent": "GeoPol-public-reference-builder/0.1"})
    digest, md5 = hashlib.sha256(), hashlib.md5(usedforsecurity=False)
    temporary = target.with_suffix(".pbf.part")
    size, progress = 0, 0
    acquired = utc_now()
    with urlopen(request, timeout=180) as response, temporary.open("wb") as stream:
        source_headers = {
            key: response.headers.get(key) for key in ("Last-Modified", "ETag", "Content-Length")
        }
        final_url = response.url
        for block in iter(lambda: response.read(4 * 1024**2), b""):
            stream.write(block)
            digest.update(block)
            md5.update(block)
            size += len(block)
            if size - progress >= 32 * 1024**2:
                progress = size
                print(f"Public OSM download: {size // 1024**2} MiB", flush=True)
    expected_size = source_headers.get("Content-Length")
    if expected_size and size != int(expected_size):
        raise ValueError("Incomplete OSM national download")
    with urlopen(OSM_URL + ".md5", timeout=60) as response:
        expected_md5 = response.read().decode("ascii").split()[0]
    if md5.hexdigest() != expected_md5:
        raise ValueError("Geofabrik MD5 mismatch; snapshot may have changed during download")
    temporary.replace(target)
    manifest = dict(
        source="OpenStreetMap contributors / Geofabrik",
        url=OSM_URL,
        resolved_url=final_url,
        acquired_at=acquired,
        headers=source_headers,
        bytes=size,
        sha256=digest.hexdigest(),
        official_md5=expected_md5,
        md5_verified=True,
        crs="EPSG:4326",
        license="ODbL-1.0",
        license_url=OSM_LICENSE,
        scope="National Peru extract, downloaded without local case selectors",
    )
    save_json(manifest_path, manifest)
    return manifest


def download_boundaries(folder, page_size=100):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / "minam-national-boundaries.geojson"
    manifest_path = folder / "minam-source.json"
    if target.exists() and manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if sha256_file(target) == manifest["sha256"]:
            return manifest
        raise ValueError("Cached MINAM snapshot checksum mismatch")
    metadata = public_json(MINAM_URL + "?f=pjson")
    save_json(folder / "minam-layer-metadata.json", metadata)
    total = public_json(
        MINAM_URL + "/query?" + urlencode({"where": "1=1", "returnCountOnly": "true", "f": "json"})
    )["count"]
    features, identifiers, pages = [], set(), []
    acquired = utc_now()
    while len(features) < total:
        offset = len(features)
        query = {
            "where": "1=1",
            "outFields": "*",
            "outSR": "4326",
            "returnGeometry": "true",
            "orderByFields": "OBJECTID ASC",
            "resultOffset": offset,
            "resultRecordCount": page_size,
            "f": "geojson",
        }
        url = MINAM_URL + "/query?" + urlencode(query)
        document = public_json(url)
        batch = document.get("features")
        if document.get("type") != "FeatureCollection" or not isinstance(batch, list) or not batch:
            raise ValueError("Invalid or incomplete national boundary pagination")
        for feature in batch:
            identifier = feature.get("properties", {}).get("OBJECTID", feature.get("id"))
            if identifier is None or identifier in identifiers:
                raise ValueError("Duplicate or missing MINAM object identifier")
            identifiers.add(identifier)
        page_path = folder / f"minam-page-{offset:05d}.geojson"
        save_json(page_path, document)
        pages.append(
            dict(file=page_path.name, sha256=sha256_file(page_path), feature_count=len(batch), url=url)
        )
        features.extend(batch)
        print(f"Public MINAM boundaries: {len(features)}/{total}", flush=True)
    if len(features) != total:
        raise ValueError("National boundary feature count changed during pagination")
    save_json(target, {"type": "FeatureCollection", "features": features})
    manifest = dict(
        source="MINAM GeoServidor / Limites Politico Referenciales",
        url=MINAM_URL,
        acquired_at=acquired,
        feature_count=total,
        sha256=sha256_file(target),
        bytes=target.stat().st_size,
        source_crs=metadata.get("sourceSpatialReference"),
        output_crs="EPSG:4326",
        transform="ArcGIS outSR=4326",
        temporal_validity="Not declared by service; acquisition date is not legal validity",
        license="No explicit reuse license in layer metadata",
        referential=True,
        metadata_sha256=sha256_file(folder / "minam-layer-metadata.json"),
        pages=pages,
    )
    save_json(manifest_path, manifest)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source", choices=("osm", "minam", "both"), default="both")
    args = parser.parse_args()
    if args.source in {"minam", "both"}:
        result = download_boundaries(args.output)
        print(json.dumps({"source": "minam", "features": result["feature_count"], "bytes": result["bytes"]}))
    if args.source in {"osm", "both"}:
        result = download_osm(args.output)
        print(json.dumps({"source": "osm", "bytes": result["bytes"], "md5_verified": result["md5_verified"]}))


if __name__ == "__main__":
    main()
