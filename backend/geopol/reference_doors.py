"""Prepare dictionary-mapped door references locally, without importing or geocoding.

Every row is retained in staging. Geographic output requires explicit metadata;
the existence of latitude/longitude fields never supplies a datum by inference.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path

from .catalogs import read_catalog
from .domain.ingestion import iter_records
from .domain.institutional_doors import map_door_record
from .domain.normalization import key

ADAPTER_VERSION = "2026.1"
MAX_ROWS = 100_000
MAX_STAGING_BYTES = 256 * 1024**2
MAX_CATALOG_BYTES = 24 * 1024**2
REQUIRED_COLUMNS = {"UBIGEO", "CATVIA", "NOMVIA", "P13_1", "P13_2", "P17", "P17_A"}


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)


def _address_key(record):
    normalized = record["normalized"]
    return (
        normalized.get("ubigeo"),
        normalized.get("street_type") or normalized.get("street_type_code"),
        normalized.get("street_name"),
        normalized.get("door_number"),
    )


def _point_key(record):
    normalized = record["normalized"]
    if not normalized.get("coordinates_valid"):
        return None
    return normalized["longitude"], normalized["latitude"]


def _feature(record, input_hash, source, version, dictionary_hash):
    n = record["normalized"]
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [n["longitude"], n["latitude"]]},
        "properties": {
            "id": f"institutional-door:{input_hash[:16]}:{record['source_ordinal']}",
            "kind": "door",
            "ubigeo": n["ubigeo"],
            "street_type": n.get("street_type"),
            "street_name": n["street_name"],
            "door_number": n["door_number"],
            "urban_core": n.get("urban_core"),
            "center_code": n.get("center_code"),
            "center_name": n.get("center_name"),
            "reference_manzana_code": n.get("reference_manzana_code"),
            "source": source,
            "version": version,
            "crs": "EPSG:4326",
            "source_ordinal": record["source_ordinal"],
            "source_sha256": input_hash,
            "dictionary_sha256": dictionary_hash,
            "adapter_version": ADAPTER_VERSION,
            "geometry_transform": "point_from_dictionary_confirmed_latitude_longitude",
        },
    }


def prepare_doors(
    input_path,
    output_dir,
    *,
    sheet=None,
    dictionary_path=None,
    crs=None,
    source=None,
    version=None,
    street_types=None,
):
    """Return a report; write new private artifacts only in an unused directory.

    Supplying crs=EPSG:4326 explicitly confirms the source datum. No coordinate
    transformation is implemented. A different CRS must be transformed upstream.
    """
    input_path, output_dir = Path(input_path).resolve(), Path(output_dir).resolve()
    if crs not in (None, "EPSG:4326"):
        raise ValueError("Transforme el CRS confirmado a EPSG:4326 antes de exportar")
    if source is not None and (not source.strip() or len(source) > 500):
        raise ValueError("Fuente vacía o demasiado extensa")
    if version is not None and (not version.strip() or len(version) > 100):
        raise ValueError("Versión vacía o demasiado extensa")
    if street_types is not None and (
        not isinstance(street_types, dict)
        or any(not isinstance(value, str) for value in street_types.values())
    ):
        raise ValueError("El dominio de categorías debe ser un objeto de códigos a etiquetas")
    if output_dir.exists():
        raise ValueError("Use un directorio nuevo para conservar preparaciones anteriores")
    input_hash = sha256_file(input_path)
    dictionary_hash = sha256_file(dictionary_path) if dictionary_path else None
    blockers = []
    for value, code in (
        (crs, "CRS_NOT_CONFIRMED"),
        (source, "SOURCE_NOT_DECLARED"),
        (version, "VERSION_NOT_DECLARED"),
        (dictionary_hash, "DICTIONARY_NOT_ATTACHED"),
    ):
        if not value:
            blockers.append(code)
    records, total_bytes = [], 0
    reader = iter_records(input_path, input_path.name, sheet=sheet)
    try:
        for ordinal, raw, issue in reader:
            if ordinal == 1:
                missing = {key(c) for c in REQUIRED_COLUMNS} - {key(c) for c in raw}
                if missing:
                    raise ValueError("El archivo no contiene el esquema de puertas requerido")
            if ordinal > MAX_ROWS:
                raise ValueError("Particione la referencia: máximo 100000 filas por preparación")
            record = map_door_record(raw, ordinal, street_types=street_types)
            if issue:
                record["issues"].append(
                    {"code": "SOURCE_ROW_ISSUE", "field": None, "message": "Incidencia de lectura"}
                )
                record["source_issue"] = issue
                record["address_ready"] = False
            total_bytes += len(_json(record).encode("utf-8"))
            if total_bytes > MAX_STAGING_BYTES:
                raise ValueError("Particione la referencia: preparación mayor de 256 MiB")
            records.append(record)
    finally:
        reader.close()
    if not records:
        raise ValueError("La referencia no contiene filas")
    if sha256_file(input_path) != input_hash:
        raise ValueError("El archivo de entrada cambió durante la preparación")

    groups = defaultdict(list)
    for record in records:
        n = record["normalized"]
        if n.get("ubigeo") and n.get("street_name") and n.get("door_number"):
            groups[_address_key(record)].append(record)
    repeated_keys = conflicts = conflicting_rows = 0
    for members in groups.values():
        if len(members) < 2:
            continue
        repeated_keys += 1
        points = {_point_key(record) for record in members if _point_key(record) is not None}
        if len(points) > 1:
            conflicts += 1
            conflicting_rows += len(members)
            group_hash = hashlib.sha256(_json(_address_key(members[0])).encode()).hexdigest()
            for record in members:
                record["issues"].append(
                    {
                        "code": "ADDRESS_MULTIPLE_COORDINATES",
                        "field": None,
                        "message": "La misma clave de dirección presenta coordenadas distintas",
                    }
                )
                record["conflict_group"] = group_hash

    statuses, issues = Counter(), Counter()
    features = []
    for record in records:
        record["metadata_blockers"] = list(blockers)
        record["catalog_eligible"] = not blockers and record["address_ready"] and not record["issues"]
        if record.get("conflict_group"):
            status = "ADDRESS_CONFLICT"
        elif not record["address_ready"] or record["issues"]:
            status = "NEEDS_DATA_OR_DICTIONARY"
        elif blockers:
            status = "NEEDS_METADATA"
        else:
            status = "CATALOG_ELIGIBLE"
        record["status"] = status
        statuses[status] += 1
        issues.update({issue["code"] for issue in record["issues"]})
        if record["catalog_eligible"]:
            features.append(_feature(record, input_hash, source.strip(), version.strip(), dictionary_hash))
    catalog = _json({"type": "FeatureCollection", "features": features}).encode("utf-8")
    if len(catalog) > MAX_CATALOG_BYTES:
        raise ValueError("Particione el catálogo: salida mayor de 24 MiB")
    if features:
        assert len(list(read_catalog(catalog, "catalog.geojson", source, version))) == len(features)

    output_dir.mkdir(parents=True, exist_ok=False)
    staging = output_dir / "staging.jsonl"
    with staging.open("w", encoding="utf-8", newline="\n") as stream:
        for record in records:
            stream.write(_json(record) + "\n")
    if features:
        (output_dir / "catalog.geojson").write_bytes(catalog)
    manifest = {
        "adapter_version": ADAPTER_VERSION,
        "input_name": input_path.name,
        "input_sha256": input_hash,
        "dictionary_sha256": dictionary_hash,
        "sheet": sheet,
        "source": source,
        "version": version,
        "confirmed_crs": crs,
        "street_types": street_types,
        "source_rows": len(records),
        "valid_coordinate_pairs": sum(r["normalized"].get("coordinates_valid", False) for r in records),
        "numbered_address_rows": sum(
            bool(
                r["normalized"].get("ubigeo")
                and r["normalized"].get("street_name")
                and r["normalized"].get("door_number")
                and r["normalized"].get("coordinates_valid")
            )
            for r in records
        ),
        "address_ready_rows": sum(r["address_ready"] for r in records),
        "repeated_address_keys": repeated_keys,
        "conflicting_address_keys": conflicts,
        "conflicting_address_rows": conflicting_rows,
        "statuses": dict(statuses),
        "issue_row_counts": dict(issues),
        "metadata_blockers": blockers,
        "catalog_features": len(features),
        "catalog_sha256": hashlib.sha256(catalog).hexdigest() if features else None,
        "staging_sha256": sha256_file(staging),
        "geocoding_performed": False,
        "database_imported": False,
        "notice": "Preparación de referencia; las entidades exportables aún requieren validación territorial",
    }
    (output_dir / "manifest.json").write_text(_json(manifest) + "\n", encoding="utf-8")
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description="Preparar referencias de puertas según diccionario")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--sheet")
    parser.add_argument("--dictionary", type=Path)
    parser.add_argument("--crs", choices=["EPSG:4326"], help="Solo si el datum de origen está confirmado")
    parser.add_argument("--source")
    parser.add_argument("--version")
    parser.add_argument(
        "--street-types", type=Path, help="JSON de código a tipo, confirmado para esta fuente"
    )
    args = parser.parse_args(argv)
    try:
        types = json.loads(args.street_types.read_text(encoding="utf-8-sig")) if args.street_types else None
        manifest = prepare_doors(
            args.input,
            args.output,
            sheet=args.sheet,
            dictionary_path=args.dictionary,
            crs=args.crs,
            source=args.source,
            version=args.version,
            street_types=types,
        )
    except (ValueError, OSError, TypeError):
        parser.exit(
            1, "No se pudo preparar la referencia: revise formato, parámetros y directorio de salida.\n"
        )
    # Keep source values, dictionary labels and provider metadata out of console output.
    print(
        _json(
            {
                key: manifest[key]
                for key in (
                    "source_rows",
                    "valid_coordinate_pairs",
                    "numbered_address_rows",
                    "address_ready_rows",
                    "conflicting_address_keys",
                    "conflicting_address_rows",
                    "statuses",
                    "issue_row_counts",
                    "metadata_blockers",
                    "catalog_features",
                    "geocoding_performed",
                    "database_imported",
                )
            }
        )
    )


if __name__ == "__main__":
    main()
