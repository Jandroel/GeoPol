"""Local reference matching with explicit abstention and reproducible evidence.

Scores rank textual similarity only. They are never correctness probabilities.
The caller supplies a bounded territorial subset and marks a truncated search.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from rapidfuzz.fuzz import ratio
from shapely.geometry import Point, shape

from . import RULES_VERSION
from .normalization import DECISION_WARNINGS, canonical_street_type, key, street_parts, text, valid_pair

_KIND_ALIASES = {"puerta": "door", "cuadra": "block", "cruce": "intersection", "sitio": "site", "nucleo": "nucleus", "limite": "boundary"}


def _kind(feature: dict) -> str:
    kind = str(feature.get("kind", "")).lower()
    return _KIND_ALIASES.get(kind, kind)


def _street(value: Any) -> str:
    return street_parts(value)[1]


def _number(value: Any) -> str:
    # Do not turn UNO into 1, strip door suffixes, or infer a door from a block.
    return re.sub(r"\s+", "", key(value))


def _ubigeo(value: Any) -> str:
    value = text(value)
    return value.zfill(6) if re.fullmatch(r"\d{1,6}", value) else ""


def _coordinates(feature: dict) -> tuple[float, float] | None:
    coordinate = valid_pair(feature.get("latitude"), feature.get("longitude"))
    geometry = feature.get("geometry")
    if coordinate:
        return coordinate
    if geometry and geometry.get("type") == "Point":
        values = geometry.get("coordinates", [])
        if len(values) >= 2:
            return valid_pair(values[1], values[0])
    return None


def _stable_id(feature: dict) -> str:
    if feature.get("id") is not None:
        return str(feature["id"])
    return hashlib.sha256(json.dumps(feature, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()[:20]


def _territory(latitude: float, longitude: float, ubigeo: str, boundaries: list[dict]) -> tuple[str, list[str]]:
    relevant = [f for f in boundaries if _ubigeo(f.get("ubigeo")) == ubigeo and ubigeo]
    if not relevant:
        return "UNKNOWN", ["LIMITE_TERRITORIAL_NO_DISPONIBLE"]
    valid = False
    at_border = False
    for feature in relevant:
        try:
            polygon = shape(feature.get("geometry") or {})
            if polygon.geom_type not in {"Polygon", "MultiPolygon"} or not polygon.is_valid or polygon.is_empty:
                continue
            valid = True
            point = Point(longitude, latitude)
            if polygon.contains(point):
                return "INSIDE", ["PUNTO_DENTRO_UBIGEO", f"LIMITE:{_stable_id(feature)}", f"VERSION:{feature.get('version') or 'NO_DECLARADA'}"]
            if polygon.covers(point):
                at_border = True
        except (ValueError, TypeError, KeyError, AttributeError):
            continue
    if at_border:
        return "BORDER", ["PUNTO_EN_LIMITE_TERRITORIAL"]
    return ("OUTSIDE", ["PUNTO_FUERA_UBIGEO"]) if valid else ("UNKNOWN", ["LIMITE_TERRITORIAL_INVALIDO"])


def _candidate(feature: dict, method: str, precision: str, score: float, evidence: list[str]) -> dict:
    pair = _coordinates(feature)
    label = " ".join(str(v) for v in (feature.get("street_type"), feature.get("street_name"), feature.get("door_number") or feature.get("block_number")) if v)
    if feature.get("cross_street"):
        label += " / " + str(feature["cross_street"])
    label = feature.get("name") or label or str(feature.get("id") or "Referencia")
    return {
        "id": _stable_id(feature), "label": label, "method": method, "precision": precision,
        "product": "AREA_TRAMO" if precision in {"CUADRA", "NUCLEO", "VIA"} else "PUNTO",
        "latitude": pair[0] if pair else None, "longitude": pair[1] if pair else None,
        "score": round(score, 2), "score_type": "SIMILITUD_TEXTUAL_NO_PROBABILIDAD", "evidence": evidence,
        "geometry": feature.get("geometry"), "source": feature.get("source"), "version": feature.get("version"),
    }


def resolve_location(normalized: dict, features: list[dict], reference_available: bool) -> dict:
    ubigeo = _ubigeo(normalized.get("ubigeo"))
    warnings = set(normalized.get("warnings") or [])
    crs_confirmed = key(normalized.get("crs")) == "EPSG:4326"
    boundaries = [f for f in features if _kind(f) == "boundary"]
    # Metadata describes the whole catalogue, not merely the retrieved subset.
    available = set(normalized.get("available_reference_kinds") or [_kind(f) for f in features])
    applicable: list[tuple[str, str]] = []
    candidates, attempts = [], []
    automatic: dict[str, bool] = {}

    def attempt(method: str, status: str, reason: str, count: int = 0, **extra):
        attempts.append({"method": method, "status": status, "reason": reason, "candidate_count": count,
                         "rules_version": RULES_VERSION, **extra})

    coordinate = valid_pair(normalized.get("latitude"), normalized.get("longitude"))
    origin = normalized.get("coordinate_origin")
    if coordinate and origin in {"PNP_ORIGINAL", "TEXTO_SIDPOL"}:
        method = "COORD_TEXTO" if origin == "TEXTO_SIDPOL" else "COORD_ORIGINAL"
        territory, evidence = _territory(*coordinate, ubigeo, boundaries)
        if not crs_confirmed:
            evidence.append("CRS_NO_CONFIRMADO")
        candidate = {"id": f"{method.lower()}:source", "label": "Coordenada extraída del texto" if method == "COORD_TEXTO" else "Coordenada original declarada",
                     "method": method, "precision": "COORDENADA", "product": "PUNTO", "latitude": coordinate[0], "longitude": coordinate[1],
                     "score": None, "score_type": "NO_APLICA", "evidence": [origin, *evidence], "source": "ARCHIVO_ORIGINAL", "version": RULES_VERSION}
        candidates.append(candidate)
        automatic[candidate["id"]] = territory == "INSIDE" and crs_confirmed
        attempt(method, "CANDIDATOS_ENCONTRADOS", "; ".join(evidence), 1)
    else:
        reason = "COORDENADA_SUSTITUTA" if origin == "SUSTITUTO_HEREDADO" else "SIN_COORDENADA_ORIGINAL_VALIDA"
        attempt("COORD_ORIGINAL", "NO_APLICABLE", reason)
    conflicting = normalized.get("text_coordinates")
    if conflicting and valid_pair(conflicting.get("latitude"), conflicting.get("longitude")):
        pair = valid_pair(conflicting["latitude"], conflicting["longitude"])
        candidates.append({"id": "coord_texto:conflict", "label": "Coordenada textual contradictoria", "method": "COORD_TEXTO", "precision": "COORDENADA",
                           "product": "PUNTO", "latitude": pair[0], "longitude": pair[1], "score": None, "score_type": "NO_APLICA",
                           "evidence": ["COORDENADAS_CONTRADICTORIAS"], "source": "ARCHIVO_ORIGINAL", "version": RULES_VERSION})
        automatic["coord_texto:conflict"] = False
        attempt("COORD_TEXTO", "CANDIDATOS_ENCONTRADOS", "COORDENADAS_CONTRADICTORIAS", 1)

    street = _street(normalized.get("street_name"))
    street_type = canonical_street_type(normalized.get("street_type"))
    cross = _street(normalized.get("cross_street"))
    door = _number(normalized.get("door_number"))
    block = _number(normalized.get("block_number"))
    site = key(normalized.get("site_name"))
    nucleus = key(normalized.get("urban_core"))
    branches = [
        ("door", "PUERTA_CON_TIPO" if street_type else "PUERTA_SIN_TIPO", "PUERTA", bool(street and door)),
        ("intersection", "CRUCE", "INTERSECCION", bool(street and cross)),
        ("site", "SITIO", "SITIO", bool(site)),
        ("block", "CUADRA_CON_TIPO" if street_type else "CUADRA_SIN_TIPO", "CUADRA", bool(street and block)),
        ("nucleus", "NUCLEO", "NUCLEO", bool(nucleus)),
    ]
    searched_any, missing_any = False, False
    for kind, method, precision, is_applicable in branches:
        if not is_applicable:
            attempt(method, "NO_APLICABLE", "COMPONENTES_AUSENTES")
            continue
        applicable.append((kind, method))
        if not reference_available or kind not in available:
            missing_any = True
            attempt(method, "NO_EVALUABLE_REFERENCIA", "REFERENCIA_NO_DISPONIBLE")
            continue
        searched_any = True
        count_before = len(candidates)
        eligible = [f for f in features if _kind(f) == kind and (not ubigeo or _ubigeo(f.get("ubigeo")) == ubigeo)]
        for feature in eligible:
            fstreet = _street(feature.get("street_name"))
            ftype = canonical_street_type(feature.get("street_type"))
            evidence = [f"REFERENCIA:{feature.get('source') or 'NO_DECLARADA'}", f"VERSION:{feature.get('version') or 'NO_DECLARADA'}"]
            exact, similarity = False, 0.0
            if kind in {"door", "block"}:
                target_number = door if kind == "door" else block
                feature_number = _number(feature.get("door_number" if kind == "door" else "block_number"))
                if target_number != feature_number or (street_type and ftype != street_type):
                    continue
                similarity = ratio(street, fstreet)
                exact = street == fstreet
                if not exact and (len(street) < 5 or similarity < 88):
                    continue
                evidence += ["NUMERO_COINCIDENTE", "TIPO_COINCIDENTE" if street_type else "TIPO_NO_RESTRINGIDO"]
            elif kind == "intersection":
                fcross = _street(feature.get("cross_street"))
                exact = {street, cross} == {fstreet, fcross}
                similarity = max(min(ratio(street, fstreet), ratio(cross, fcross)), min(ratio(street, fcross), ratio(cross, fstreet)))
                if not exact and similarity < 88:
                    continue
                evidence.append("CONEXION_A_NIVEL_CONFIRMADA" if feature.get("connects_at_grade") is True else "CONEXION_A_NIVEL_NO_CONFIRMADA")
            else:
                sought = site if kind == "site" else nucleus
                found = key(feature.get("name"))
                exact, similarity = sought == found, ratio(sought, found)
                if not exact and (len(sought) < 5 or similarity < 88):
                    continue
            evidence.append("COMPONENTES_EXACTOS" if exact else "SIMILITUD_TEXTUAL_REQUIERE_REVISION")
            territorial_match = bool(ubigeo and ubigeo == _ubigeo(feature.get("ubigeo")))
            evidence.append("UBIGEO_COINCIDENTE" if territorial_match else "TERRITORIO_NO_CONFIRMADO")
            pair = _coordinates(feature)
            territory = "UNKNOWN"
            if pair and ubigeo:
                territory, territorial_evidence = _territory(*pair, ubigeo, boundaries)
                if territory != "UNKNOWN":
                    evidence.extend(territorial_evidence)
            if not pair:
                evidence.append("SIN_PUNTO_REFERENCIAL_VALIDO")
            if precision in {"CUADRA", "NUCLEO"}:
                evidence.append("APROXIMACION_ESPACIAL_REQUIERE_REVISION")
            if kind == "nucleus":
                evidence.append("POLITICA_GEOMETRICA_NUCLEO_PENDIENTE")
            if kind == "site":
                evidence.append("EXTENSION_Y_ENTRADA_DEL_SITIO_NO_CONFIRMADAS")
            if not crs_confirmed:
                evidence.append("CRS_NO_CONFIRMADO")
            candidate = _candidate(feature, method, precision, 100 if exact else similarity, evidence)
            candidates.append(candidate)
            automatic[candidate["id"]] = bool(
                exact and pair and territorial_match and crs_confirmed and territory not in {"OUTSIDE", "BORDER"}
                and (kind == "door" or (kind == "intersection" and feature.get("connects_at_grade") is True))
            )
        count = len(candidates) - count_before
        attempt(method, "CANDIDATOS_ENCONTRADOS" if count else "SIN_CANDIDATO", "COINCIDENCIAS_REFERENCIA" if count else "BUSQUEDA_COMPLETADA_SIN_COINCIDENCIA", count,
                reference_versions=sorted({str(f.get("version")) for f in eligible if f.get("version")}))
    if street and not (door or block or cross):
        attempt("VIA_JURISDICCION", "NO_EVALUABLE_REFERENCIA", "FUENTE_Y_POLITICA_GEOMETRICA_NO_CONFIRMADAS")
        missing_any = True

    result = {"resolution": "INFORMACION_INSUFICIENTE", "method": "SIN_METODO", "precision": "DESCONOCIDA", "evidence_band": "SIN_EVIDENCIA",
              "product": "NINGUNO", "latitude": None, "longitude": None, "reason": "DIRECCION_INSUFICIENTE", "candidates": candidates, "attempts": attempts}
    if candidates:
        # Keep every competing candidate, including evidence from different methods.
        candidates.sort(key=lambda c: (not automatic.get(c["id"], False), -(c.get("score") or 0), c["id"]))
        chosen = candidates[0]
        hard_warnings = warnings & DECISION_WARNINGS
        duplicate_candidates = len(candidates) > 1
        accepted = bool(automatic.get(chosen["id"]) and not hard_warnings and not duplicate_candidates and not normalized.get("reference_truncated"))
        reasons = []
        if duplicate_candidates:
            reasons.append("MULTIPLES_CANDIDATOS")
        if hard_warnings:
            reasons.extend(sorted(hard_warnings))
        if normalized.get("reference_truncated"):
            reasons.append("BUSQUEDA_REFERENCIAL_TRUNCADA")
        if not crs_confirmed:
            reasons.append("CRS_NO_CONFIRMADO")
        if not ubigeo:
            reasons.append("TERRITORIO_NO_CONFIRMADO")
        if not automatic.get(chosen["id"]):
            reasons.extend(chosen["evidence"])
        result.update({"resolution": "ACEPTADO_AUTOMATICO" if accepted else "REVISION_REQUERIDA", "method": chosen["method"],
                       "precision": chosen["precision"], "evidence_band": "ALTA" if accepted else "REVISION",
                       "product": chosen["product"] if accepted else ("DIRECCION_SIN_PUNTO" if normalized.get("location_normalized") else "NINGUNO"),
                       "latitude": chosen["latitude"] if accepted else None, "longitude": chosen["longitude"] if accepted else None,
                       "reason": "COINCIDENCIA_UNICA_CON_EVIDENCIA_TERRITORIAL" if accepted else "; ".join(dict.fromkeys(reasons)) or "VERIFICACION_HUMANA_REQUERIDA"})
        if accepted:
            attempt(chosen["method"], "ACEPTADO", result["reason"], 1)
    elif normalized.get("reference_truncated"):
        result.update(resolution="REVISION_REQUERIDA", evidence_band="REVISION", reason="BUSQUEDA_REFERENCIAL_TRUNCADA")
    elif not ubigeo and (applicable or street or coordinate):
        result.update(resolution="REVISION_REQUERIDA", evidence_band="REVISION", reason="TERRITORIO_NO_CONFIRMADO")
    elif missing_any:
        result.update(resolution="NO_EVALUABLE_REFERENCIA", reason="REFERENCIA_NO_DISPONIBLE_O_POLITICA_NO_CONFIRMADA")
    elif searched_any:
        result.update(resolution="SIN_COINCIDENCIA", reason="BUSQUEDA_COMPLETADA_SIN_COINCIDENCIA")
    elif warnings & {"COORDENADAS_ESTRUCTURADAS_INVALIDAS", "COORDENADAS_TEXTO_INVALIDAS", "COORDENADA_SUSTITUTA"}:
        result.update(resolution="REVISION_REQUERIDA", evidence_band="REVISION", reason="; ".join(sorted(warnings)))
    return result
