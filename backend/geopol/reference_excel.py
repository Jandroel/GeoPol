"""Bounded adapters for the five institutional Excel reference layers.

An Excel row is not a spatial reference merely because it has X/Y columns. The
original upload remains immutable, and only structurally valid rows with a
documented CRS become searchable Features. Unusable rows remain staged.
"""

from __future__ import annotations

from collections import Counter
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import re

from shapely import from_wkt
from shapely.geometry import mapping as geometry_mapping, shape
from sqlalchemy import select

from .catalogs import read_catalog
from .domain.coordinate_context import documented_crs
from .domain.ingestion import inspect_file, iter_records
from .domain.institutional_doors import map_door_record
from .domain.normalization import canonical_street_type, column_key, key, street_parts, text
from .models import Catalog, Feature, uid
from .serialization import audit

REFERENCE_KINDS = {"doors", "roads", "centers", "boundaries", "jurisdictions"}
MAX_ROWS = 100_000
MAX_PAYLOAD_BYTES = 24 * 1024**2
MAX_ISSUE_SAMPLES = 50

FIELD_ALIASES = {
    "id": ("id", "OBJECTID", "FID", "id_puerta", "id_via"),
    "ubigeo": ("ubigeo", "cod_ubigeo", "ubigeo_distrital"),
    "street_type": ("street_type", "tipo_via", "CATVIA"),
    "street_name": ("street_name", "NOMVIA", "nombre_via"),
    "door_number": ("door_number", "P17", "numero_puerta", "puerta"),
    "door_letter": ("door_letter", "P17_A", "letra_puerta"),
    "block_number": ("block_number", "cuadra", "numero_cuadra"),
    "cross_street": ("cross_street", "via_cruce", "segunda_via"),
    "name": ("name", "nombre", "NOMBCCPP", "NOMCCPP", "NOMBDIST", "jurisdiccion"),
    "urban_core": ("urban_core", "NUCLEO", "nucleo_urbano"),
    "center_code": ("center_code", "CODCCPP"),
    "center_name": ("center_name", "NOMBCCPP", "NOMCCPP"),
    "latitude": ("latitude", "latitud", "P13_1", "lat", "y"),
    "longitude": ("longitude", "longitud", "P13_2", "lon", "lng", "x"),
    "geometry": ("geometry", "geometria", "WKT", "geom", "geojson", "shape_wkt"),
    "kind": ("kind", "tipo_entidad"),
    "level": ("level", "nivel", "nivel_administrativo"),
    "connects_at_grade": ("connects_at_grade", "conexion_a_nivel"),
    "crs": ("crs", "srid", "sistema_coordenadas"),
}


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)


def preview_reference_excel(path, filename, *, kind, sheet=None):
    if kind not in REFERENCE_KINDS:
        raise ValueError("Tipo de referencia no admitido")
    if Path(filename).suffix.lower() != ".xlsx":
        raise ValueError("Las referencias de este módulo deben ser archivos XLSX")
    profile = inspect_file(Path(path), filename, sheet=sheet)
    lookup = {column_key(column): column for column in profile["columns"]}
    suggestions = {}
    for field, aliases in FIELD_ALIASES.items():
        for alias in aliases:
            if column_key(alias) in lookup:
                suggestions[field] = lookup[column_key(alias)]
                break
    # Generic PNP address warnings do not describe the reference schema.
    warnings = [value for value in profile["warnings"] if not value.startswith("SIN_LOCALIZADOR_")]
    if "geometry" not in suggestions and kind in {"roads", "boundaries", "jurisdictions"}:
        warnings.append("FALTA_GEOMETRIA: la tabla se conservará pendiente de espacialización")
    if suggestions.get("street_type") and column_key(suggestions["street_type"]) == "CATVIA":
        warnings.append("CATVIA_REQUIERE_DOMINIO: los códigos numéricos necesitan etiquetas confirmadas")
    return {
        "kind": kind,
        "columns": profile["columns"],
        "sheets": profile["sheets"],
        "sheet": profile["sheet"],
        "suggested_mapping": suggestions,
        "warnings": warnings,
    }


def _number(value):
    if isinstance(value, bool):
        raise ValueError("COORDENADAS_INVALIDAS")
    candidate = text(value).replace(",", ".")
    try:
        result = float(candidate)
    except (ValueError, TypeError, OverflowError):
        raise ValueError("COORDENADAS_INVALIDAS") from None
    if not math.isfinite(result):
        raise ValueError("COORDENADAS_INVALIDAS")
    return result


def _geometry(fields, kind):
    """Never construct a line/polygon from a table or a single coordinate pair."""
    raw = fields.get("geometry")
    geometry = None
    if raw not in (None, ""):
        try:
            document = json.loads(raw) if isinstance(raw, str) and raw.lstrip().startswith("{") else raw
            if isinstance(document, str):
                parsed = from_wkt(document)
            elif isinstance(document, dict):
                parsed = shape(document)
            else:
                raise ValueError()
            if parsed.is_empty or not parsed.is_valid or parsed.has_z:
                raise ValueError()
            if getattr(parsed, "has_m", False):
                raise ValueError()
            geometry = geometry_mapping(parsed)
        except Exception:
            raise ValueError("GEOMETRIA_INVALIDA") from None
    lat, lon = fields.get("latitude"), fields.get("longitude")
    has_lat, has_lon = lat not in (None, ""), lon not in (None, "")
    if has_lat != has_lon:
        raise ValueError("PAR_COORDENADAS_INCOMPLETO")
    if has_lat:
        lat, lon = _number(lat), _number(lon)
        if not -90 <= lat <= 90 or not -180 <= lon <= 180:
            raise ValueError("COORDENADAS_FUERA_DE_RANGO")
        if geometry is not None and geometry["type"] == "Point":
            if (lon, lat) != tuple(geometry["coordinates"]):
                raise ValueError("GEOMETRIA_Y_COORDENADAS_CONTRADICTORIAS")
        elif geometry is None and kind in {"door", "site", "intersection"}:
            geometry = {"type": "Point", "coordinates": [lon, lat]}
    if geometry is None:
        raise ValueError("GEOMETRIA_NO_DISPONIBLE")
    compatible = {
        "door": {"Point"},
        "site": {"Point"},
        "intersection": {"Point"},
        "street": {"LineString", "MultiLineString"},
        "block": {"LineString", "MultiLineString"},
        "boundary": {"Polygon", "MultiPolygon"},
        "jurisdiction": {"Polygon", "MultiPolygon"},
    }
    if geometry["type"] not in compatible[kind]:
        raise ValueError("GEOMETRIA_INCOMPATIBLE_CON_CAPA")
    return geometry


def _district_code(value, *, kind, level):
    code = text(value)
    # Numeric cells can lose a leading zero. Two/four-digit administrative codes
    # must never be padded into a district when importing boundary tables.
    declared = key(level)
    if kind == "boundaries":
        if declared and declared not in {"DISTRITO", "DISTRITAL", "DISTRICT", "3"}:
            raise ValueError("LIMITE_NO_DISTRITAL")
        if len(code) != 6 and not (len(code) == 5 and declared in {"DISTRITO", "DISTRITAL", "DISTRICT", "3"}):
            raise ValueError("LIMITE_REQUIERE_UBIGEO_DISTRITAL")
    if not re.fullmatch(r"\d{5,6}", code):
        raise ValueError("UBIGEO_DISTRITAL_INVALIDO")
    return code.zfill(6)


def _feature(raw, fields, *, kind, ordinal, source, version, street_types):
    if fields.get("crs") not in (None, "") and key(fields["crs"]) not in {
        "EPSG:4326",
        "4326",
        "WGS84",
        "WGS 84",
    }:
        raise ValueError("CRS_DECLARADO_EN_FILA_CONTRADICTORIO")
    feature_kind = {
        "doors": "door",
        "roads": "street",
        "centers": "site",
        "boundaries": "boundary",
        "jurisdictions": "jurisdiction",
    }[kind]
    if kind == "roads" and fields.get("kind") not in (None, ""):
        value = key(fields["kind"])
        feature_kind = {
            "STREET": "street",
            "VIA": "street",
            "BLOCK": "block",
            "CUADRA": "block",
            "INTERSECTION": "intersection",
            "CRUCE": "intersection",
        }.get(value)
        if not feature_kind:
            raise ValueError("TIPO_VIA_NO_ADMITIDO")
    geometry = _geometry(fields, feature_kind)
    ubigeo = _district_code(fields.get("ubigeo"), kind=kind, level=fields.get("level"))
    result = {
        field: text(value)
        for field, value in fields.items()
        if value not in (None, "")
        and field not in {"geometry", "latitude", "longitude", "kind", "level", "door_letter"}
    }
    result.update(
        id=text(fields.get("id")) or str(ordinal),
        kind=feature_kind,
        ubigeo=ubigeo,
        geometry=geometry,
        source=source,
        version=version,
        crs="EPSG:4326",
        source_ordinal=ordinal,
    )
    if geometry["type"] == "Point":
        result["longitude"], result["latitude"] = geometry["coordinates"]
    if kind == "doors":
        # The dictionary adapter also guards rural/lot/alternative-address fields
        # in the original schema; an unchecked alternate address is not a door.
        mapped = {key(name): value for name, value in raw.items()}
        for field, target in {
            "ubigeo": "UBIGEO",
            "street_name": "NOMVIA",
            "door_number": "P17",
            "door_letter": "P17_A",
            "urban_core": "NUCLEO",
            "center_code": "CODCCPP",
            "center_name": "NOMBCCPP",
        }.items():
            if field in fields:
                mapped[target] = fields[field]
        mapped.update(P13_1=result["latitude"], P13_2=result["longitude"], UBIGEO=ubigeo)
        if "street_type" in fields:
            mapped["CATVIA"] = fields["street_type"]
        types = dict(street_types)
        supplied_type = text(mapped.get("CATVIA"))
        if supplied_type and not re.fullmatch(r"\d+", supplied_type):
            canonical = canonical_street_type(supplied_type)
            if canonical:
                types[supplied_type] = canonical
        record = map_door_record(mapped, ordinal, street_types=types)
        if record["issues"]:
            raise ValueError("|".join(dict.fromkeys(issue["code"] for issue in record["issues"])))
        for field in (
            "street_type",
            "street_name",
            "door_number",
            "urban_core",
            "center_code",
            "center_name",
        ):
            if record["normalized"].get(field):
                result[field] = record["normalized"][field]
    elif kind == "roads":
        if not text(fields.get("street_name")):
            raise ValueError("NOMBRE_VIA_AUSENTE")
        category = text(fields.get("street_type"))
        if category and re.fullmatch(r"\d+", category):
            if category not in street_types or not canonical_street_type(street_types[category]):
                raise ValueError("CAT_VIA_DOMAIN_UNCONFIRMED")
            result["street_type"] = canonical_street_type(street_types[category])
        elif category and not canonical_street_type(category):
            raise ValueError("TIPO_VIA_NO_ADMITIDO")
        explicit_type, _ = street_parts(fields.get("street_name"))
        declared_type = canonical_street_type(result.get("street_type"))
        if explicit_type and declared_type and explicit_type != declared_type:
            raise ValueError("STREET_TYPE_CONFLICT")
        if feature_kind == "block" and not re.fullmatch(r"\d+", text(fields.get("block_number"))):
            raise ValueError("NUMERO_CUADRA_AUSENTE_O_INVALIDO")
        if feature_kind == "intersection" and not text(fields.get("cross_street")):
            raise ValueError("SEGUNDA_VIA_AUSENTE")
    elif kind == "centers":
        if not text(fields.get("name") or fields.get("center_name")):
            raise ValueError("NOMBRE_CENTRO_POBLADO_AUSENTE")
        result.update(
            name=text(fields.get("name") or fields.get("center_name")),
            point_role="settlement_reference",
            reference_precision="centro_poblado",
        )
    elif kind == "jurisdictions" and not text(fields.get("name")):
        raise ValueError("NOMBRE_JURISDICCION_AUSENTE")
    document = _json(
        {
            "type": "FeatureCollection",
            "features": [{"type": "Feature", "properties": result, "geometry": geometry}],
        }
    ).encode()
    try:
        return next(read_catalog(document, "reference.geojson", source, version))
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError):
        raise ValueError("REFERENCIA_ESPACIAL_INVALIDA") from None


def parse_reference_excel(
    path,
    filename,
    *,
    kind,
    source,
    version,
    mapping,
    sheet=None,
    crs=None,
    crs_evidence=None,
    street_types=None,
):
    profile = preview_reference_excel(path, filename, kind=kind, sheet=sheet)
    if not mapping:
        mapping = profile["suggested_mapping"]
    if set(mapping) - set(FIELD_ALIASES) or any(
        value not in profile["columns"] for value in mapping.values()
    ):
        raise ValueError("El mapeo contiene campos o columnas inexistentes")
    if not source.strip() or not version.strip():
        raise ValueError("Declare la fuente y versión de la referencia")
    if crs not in (None, "EPSG:4326"):
        raise ValueError("Transforme la capa a EPSG:4326 antes de activar sus geometrías")
    if crs is not None and not documented_crs({"crs": crs, "crs_evidence": crs_evidence}):
        raise ValueError("Indique la fuente que confirma el sistema de coordenadas EPSG:4326")
    confirmed = documented_crs({"crs": crs, "crs_evidence": crs_evidence})
    features, issues, issue_counts, seen = [], [], Counter(), set()
    row_count = staged_rows = byte_count = 0
    records = iter_records(Path(path), filename, sheet=profile["sheet"])
    try:
        for ordinal, raw, issue in records:
            row_count += 1
            if row_count > MAX_ROWS:
                raise ValueError("Máximo 100 000 filas por referencia; particione el Excel")
            fields = {canonical: raw.get(column) for canonical, column in mapping.items()}
            identifier = text(fields.get("id")) or str(ordinal)
            if identifier in seen or len(identifier) > 200:
                raise ValueError(f"Identificador duplicado o demasiado largo en fila {ordinal}")
            seen.add(identifier)
            codes = []
            if issue:
                codes.append("FILA_ORIGEN_CON_INCIDENCIA")
            if not confirmed:
                codes.append("CRS_NO_CONFIRMADO")
            try:
                feature = _feature(
                    raw,
                    fields,
                    kind=kind,
                    ordinal=ordinal,
                    source=source.strip(),
                    version=version.strip(),
                    street_types=street_types or {},
                )
            except ValueError as exc:
                codes.extend(str(exc).split("|"))
                feature = None
            if codes:
                staged_rows += 1
                unique = list(dict.fromkeys(codes))
                issue_counts.update(unique)
                if len(issues) < MAX_ISSUE_SAMPLES:
                    issues.append({"ordinal": ordinal, "codes": unique})
            else:
                byte_count += len(_json(feature).encode("utf-8"))
                if byte_count > MAX_PAYLOAD_BYTES:
                    raise ValueError("Referencias espaciales mayores de 24 MiB; particione el Excel")
                features.append(feature)
    finally:
        records.close()
    if not row_count:
        raise ValueError("La hoja no contiene filas de referencia")
    return features, {
        "kind": kind,
        "sheet": profile["sheet"],
        "mapping": mapping,
        "crs": crs,
        "crs_evidence": crs_evidence.strip() if confirmed else None,
        "street_types": street_types or {},
        "row_count": row_count,
        "ready_rows": len(features),
        "staged_rows": staged_rows,
        "issue_counts": dict(issue_counts),
        "issues": issues,
        "issues_truncated": staged_rows > len(issues),
        "readiness": "staged" if not features else "partial" if staged_rows else "ready",
    }


def build_reference_bundle(db, ids, actor):
    """Create an immutable selection snapshot within the caller's transaction."""
    if not ids or len(ids) > 5 or len(set(ids)) != len(ids):
        raise ValueError("Seleccione entre uno y cinco catálogos distintos")
    catalogs = [db.get(Catalog, identifier) for identifier in ids]
    if any(catalog is None for catalog in catalogs):
        raise ValueError("Uno de los catálogos seleccionados no existe")
    if sum(catalog.feature_count for catalog in catalogs) > MAX_ROWS:
        raise ValueError("Máximo 100 000 entidades por conjunto de referencias")
    selections, kinds = [], set()
    for catalog in catalogs:
        config = catalog.config or {}
        excel = config.get("reference_excel", {})
        selections.append(
            {
                "id": catalog.id,
                "name": catalog.name,
                "source": catalog.source,
                "version": catalog.version,
                "sha256": catalog.sha256,
                "feature_count": catalog.feature_count,
                "kind": excel.get("kind"),
                "readiness": excel.get("readiness", "ready" if catalog.feature_count else "staged"),
            }
        )
        kinds.update(catalog.kinds or [])
    digest = hashlib.sha256(_json(selections).encode()).hexdigest()
    item = Catalog(
        id=uid(),
        name="Conjunto de referencias del procesamiento",
        source="Selección local de referencias versionadas",
        version=digest[:16],
        sha256=digest,
        feature_count=0,
        kinds=sorted(kinds),
        config={
            "reference_bundle": {
                "catalogs": selections,
                "readiness": "ready"
                if all(s["readiness"] == "ready" for s in selections)
                else "partial"
                if any(s["feature_count"] for s in selections)
                else "staged",
            }
        },
    )
    db.add(item)
    db.flush()
    byte_count = 0
    for catalog in catalogs:
        last_id = None
        while True:
            query = select(Feature).where(Feature.catalog_id == catalog.id)
            if last_id:
                query = query.where(Feature.id > last_id)
            batch = list(db.scalars(query.order_by(Feature.id).limit(500)))
            if not batch:
                break
            for original in batch:
                payload = deepcopy(original.payload)
                original_id = payload.get("id", original.external_id)
                external_id = f"{catalog.id}:{original.external_id}"
                if len(external_id) > 200:
                    external_id = f"{catalog.id}:{hashlib.sha256(original.external_id.encode()).hexdigest()}"
                payload.update(
                    id=external_id,
                    origin_catalog_id=catalog.id,
                    origin_feature_id=original_id,
                    origin_catalog_sha256=catalog.sha256,
                )
                byte_count += len(_json(payload).encode())
                if byte_count > MAX_PAYLOAD_BYTES:
                    raise ValueError("El conjunto supera 24 MiB de referencias; reduzca la selección")
                db.add(
                    Feature(
                        catalog_id=item.id,
                        external_id=external_id,
                        kind=original.kind,
                        ubigeo=original.ubigeo,
                        search_key=original.search_key,
                        payload=payload,
                    )
                )
                item.feature_count += 1
                if item.feature_count > MAX_ROWS:
                    raise ValueError("Máximo 100 000 entidades por conjunto de referencias")
            last_id = batch[-1].id
            db.flush()
    audit(
        db,
        actor,
        "reference.bundle_created",
        item.id,
        {"catalog_ids": ids, "feature_count": item.feature_count},
    )
    return item
