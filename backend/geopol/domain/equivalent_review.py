"""Conservative, pure equivalence rules for one explicitly reviewed address group.

This module does not promote candidates to automatic decisions. It only establishes
whether a human decision can be repeated without discarding any geographic evidence.
"""

import hashlib
import json
import re

from shapely.geometry import Point, shape

from .coordinate_context import documented_crs
from .normalization import valid_pair

GROUP_LIMIT = 200
_NON_ADDRESS_FIELDS = {"complaint_id", "location_original", "transformations", "extraction_evidence"}
_BLOCKED_EVIDENCE = {
    "PUNTO_EN_LIMITE_TERRITORIAL",
    "PUNTO_FUERA_UBIGEO",
    "GEOMETRIA_EXCEDE_UBIGEO",
    "LIMITE_TERRITORIAL_NO_DISPONIBLE",
    "LIMITE_TERRITORIAL_INVALIDO",
    "LIMITE_TERRITORIAL_INVALIDO_O_CRS_NO_CONFIRMADO",
    "CRS_NO_CONFIRMADO",
    "CRS_REFERENCIA_NO_CONFIRMADO",
    "PROCEDENCIA_REFERENCIA_INCOMPLETA",
    "TERRITORIO_NO_CONFIRMADO",
    "GEOMETRIA_REAL_DE_PRECISION_NO_DISPONIBLE",
    "CONTEXTO_MANZANA_NO_CONFIRMADO",
    "CONEXION_A_NIVEL_NO_CONFIRMADA",
    "NUCLEO_URBANO_CONTRADICTORIO_REFERENCIA",
    "GEOMETRIA_FUERA_NUCLEO_DECLARADO",
    "CONTEXTO_URBANO_REFERENCIAL_NO_DISPONIBLE",
    "VIA_RAMIFICADA_O_AMBIGUA",
    "PUNTO_SITIO_NO_IDENTIFICADO_COMO_NODO_O_ENTRADA",
    "CRUCE_NO_RESUELTO_POR_UNA_VIA",
    "COORDENADA_Y_REFERENCIA_CONTRADICTORIAS",
    "MULTIPLES_CANDIDATOS",
    "MEMORIA_CONFLICTIVA_O_DATOS_CONTRADICTORIOS",
    "BUSQUEDA_REFERENCIAL_TRUNCADA",
}


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def fingerprint(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def _usable_geometry(value, product):
    try:
        geometry = shape(value)
        allowed = (
            {"Point"} if product == "PUNTO" else {"LineString", "MultiLineString", "Polygon", "MultiPolygon"}
        )
        west, south, east, north = geometry.bounds
        return bool(
            geometry.geom_type in allowed
            and geometry.is_valid
            and not geometry.is_empty
            and not geometry.has_z
            and -180 <= west <= east <= 180
            and -90 <= south <= north <= 90
        )
    except (ValueError, TypeError, AttributeError, KeyError):
        return False


def candidate_is_corroborable(candidate, normalized):
    """A valid geometry alone is insufficient: territory, CRS and source must exist."""
    if not isinstance(candidate, dict):
        return False
    if not all(candidate.get(name) for name in ("id", "method", "source", "version")):
        return False
    evidence = candidate.get("evidence")
    if not isinstance(evidence, list) or not all(isinstance(code, str) for code in evidence):
        return False
    codes = set(evidence)
    if _BLOCKED_EVIDENCE & codes:
        return False
    product, precision = candidate.get("product"), candidate.get("precision")
    inside = "PUNTO_DENTRO_UBIGEO" if product == "PUNTO" else "GEOMETRIA_COMPLETA_DENTRO_UBIGEO"
    if inside not in codes:
        return False
    allowed = (
        {"PUERTA", "INTERSECCION", "SITIO", "COORDENADA"}
        if product == "PUNTO"
        else {"MANZANA", "CUADRA", "VIA", "NUCLEO"}
    )
    if product not in {"PUNTO", "AREA_TRAMO"} or precision not in allowed:
        return False
    if not _usable_geometry(candidate.get("geometry"), product):
        return False
    if product == "PUNTO":
        pair = valid_pair(candidate.get("latitude"), candidate.get("longitude"))
        if not pair or candidate["geometry"].get("coordinates") != [pair[1], pair[0]]:
            return False
    elif candidate.get("latitude") is not None or candidate.get("longitude") is not None:
        return False
    if candidate["method"] in {"COORD_ORIGINAL", "COORD_TEXTO"}:
        return documented_crs(normalized) and valid_pair(
            normalized.get("latitude"), normalized.get("longitude")
        ) == valid_pair(candidate.get("latitude"), candidate.get("longitude"))
    return {"CRS_REFERENCIA_EPSG4326", "UBIGEO_COINCIDENTE"} <= codes


def eligibility_reason(item, user_id, now):
    """Return an explanation when a persisted result cannot participate."""
    if item.get("manual") or item.get("review_status") != "OPEN":
        return "Solo se agrupan ubicaciones abiertas sin una decisión manual previa."
    if item.get("review_bucket") != "actionable" or item.get("resolution") != "REVISION_REQUERIDA":
        return "Primero resuelva la falta de referencias, datos o el problema técnico."
    owner, expires = item.get("review_owner"), item.get("review_expires_at")
    if owner and owner != user_id and (expires is None or expires > now):
        return "Otra persona tiene esta ubicación reservada."
    normalized = item.get("normalized") or {}
    if not re.fullmatch(r"\d{6}", item.get("ubigeo") or "") or not item.get("location_normalized"):
        return "La agrupación requiere dirección normalizada y UBIGEO válidos."
    if (
        normalized.get("ubigeo") != item["ubigeo"]
        or normalized.get("location_normalized") != item["location_normalized"]
    ):
        return "La dirección y su información normalizada no son coherentes."
    if (
        normalized.get("warnings")
        or normalized.get("decision_constraints")
        or normalized.get("reference_truncated")
    ):
        return "Hay advertencias de origen que requieren resolver este caso por separado."
    if normalized.get("text_coordinates"):
        return "Existen coordenadas textuales contradictorias."
    if any(normalized.get(axis) is not None for axis in ("latitude", "longitude")):
        if not documented_crs(normalized) or not valid_pair(
            normalized.get("latitude"), normalized.get("longitude")
        ):
            return "Las coordenadas originales requieren un sistema de referencia confirmado con su fuente."
    if _BLOCKED_EVIDENCE & set((item.get("reason") or "").split("; ")):
        return "La evidencia presenta ambigüedades o contradicciones que requieren revisión individual."
    candidates = item.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        return "No hay candidatos corroborables para una decisión de grupo."
    if not all(candidate_is_corroborable(candidate, normalized) for candidate in candidates):
        return "Los candidatos necesitan geometría, procedencia, CRS y verificación territorial coherentes."
    if len({str(candidate["id"]) for candidate in candidates}) != len(candidates):
        return "Los identificadores de los candidatos no son únicos."
    # Distinct spatial alternatives remain an individual investigation, even when
    # their text similarity and display labels happen to be identical.
    if len({canonical([c["geometry"], c["precision"], c["product"]]) for c in candidates}) != 1:
        return "Hay alternativas geográficas diferentes; resuelva la ambigüedad individualmente."
    source_pair = valid_pair(normalized.get("latitude"), normalized.get("longitude"))
    if source_pair and any(
        not shape(candidate["geometry"]).covers(Point(source_pair[1], source_pair[0]))
        for candidate in candidates
    ):
        return "Las coordenadas de origen no coinciden con la geometría propuesta."
    return None


def equivalence_key(item):
    """Exact normalized components, original coordinates and every candidate datum.

    Only non-geographic bookkeeping fields are omitted. New normalization fields
    therefore make grouping stricter by default rather than silently losing context.
    """
    normalized = {k: v for k, v in item["normalized"].items() if k not in _NON_ADDRESS_FIELDS}
    return fingerprint(
        {
            "address": item["location_normalized"],
            "ubigeo": item["ubigeo"],
            "normalized": normalized,
            "candidates": sorted(item["candidates"], key=lambda c: str(c["id"])),
            "reason": item.get("reason"),
        }
    )
