"""Location-format flags and conservative resolution stages, kept independent.

Public flags 1/2 describe the structure of the supplied location, never its
verification, probability or resulting spatial precision. Legacy quality_code
values remain internal review-routing categories for compatibility. A source
coordinate can corroborate a reference but cannot alone prove an exact door.
Flag 10 preserves an explicit input exclusion or records entirely empty location
input; it never means an unsuccessful geographic search.
"""

from __future__ import annotations

from copy import deepcopy
import json
import re

from . import matching
from .normalization import DECISION_WARNINGS, canonical_street_type, key, street_parts, text, valid_pair


POLICY_VERSION = "quality-2.0"
INPUT_VALIDATION_VERSION = "input-validation-1.0"


def flag10_reason(normalized: dict) -> str | None:
    """Honor an explicit exclusion; infer it only from entirely empty original fields."""
    if normalized.get("source_quality_flag") == 10:
        return "FLAG_10_DECLARADO_EN_ORIGEN"
    if (
        normalized.get("location_input_empty") is True
        and not text(normalized.get("source_quality_flag_original"))
        and "FILA_ORIGEN_CON_INCIDENCIA" not in (normalized.get("warnings") or [])
    ):
        return "FLAG_10_SIN_DATOS_DE_UBICACION"
    return None


def excluded_input_result(normalized: dict) -> dict | None:
    reason = flag10_reason(normalized)
    if not reason:
        return None
    return {
        "resolution": "EXCLUIDO_FLAG_10",
        "method": "VALIDACION_ENTRADA",
        "precision": "DESCONOCIDA",
        "evidence_band": "SIN_EVIDENCIA",
        "product": "NINGUNO",
        "latitude": None,
        "longitude": None,
        "geometry": None,
        "reason": reason,
        "candidates": [],
        "attempts": [
            {
                "method": "VALIDACION_ENTRADA",
                "status": "excluded",
                "reason": reason,
                "policy_version": INPUT_VALIDATION_VERSION,
            }
        ],
        "quality_flag": 10,
        "quality_flag_reason": reason,
        "quality_status": "excluded",
        "quality_stage": None,
        "quality_code": None,
        "quality_reason": reason,
        "quality_policy_version": INPUT_VALIDATION_VERSION,
        "review_state": "excluded",
    }


STAGES = (
    {"key": "door", "label": "Puertas", "kinds": ("door",)},
    {"key": "block", "label": "Cuadras", "kinds": ("block",)},
    {"key": "intersection", "label": "Cruces de vías", "kinds": ("intersection",)},
    {"key": "street", "label": "Vías", "kinds": ("street",)},
    {"key": "nucleus", "label": "Núcleos y centros poblados", "kinds": ("nucleus", "site")},
    {"key": "jurisdiction", "label": "Jurisdicciones", "kinds": ("jurisdiction",)},
)
STAGE_KEYS = tuple(stage["key"] for stage in STAGES)
_STAGE_KINDS = {stage["key"]: set(stage["kinds"]) for stage in STAGES}
_STAGE_METHODS = {
    "door": {"PUERTA_CON_TIPO", "PUERTA_SIN_TIPO"},
    "block": {"CUADRA_CON_TIPO", "CUADRA_SIN_TIPO"},
    "intersection": {"CRUCE"},
    "street": {"VIA_JURISDICCION"},
    "nucleus": {"NUCLEO", "CCPP_PUNTO_REFERENCIA"},
    "jurisdiction": {"JURISDICCION"},
}
_ACCEPTED = {"ACEPTADO_AUTOMATICO", "ACEPTADO_MANUAL"}
_FUZZY = {"SIMILITUD_FUERTE_CON_GUARDAS", "SIMILITUD_TEXTUAL_REQUIERE_REVISION"}
_QUICK_REQUIRED = {
    "NUMERO_COINCIDENTE",
    "TIPO_COINCIDENTE",
    "UBIGEO_COINCIDENTE",
    "PUNTO_DENTRO_UBIGEO",
    "CRS_REFERENCIA_EPSG4326",
}
_UNSAFE = {
    "PUNTO_EN_LIMITE_TERRITORIAL",
    "PUNTO_FUERA_UBIGEO",
    "GEOMETRIA_EXCEDE_UBIGEO",
    "LIMITE_TERRITORIAL_NO_DISPONIBLE",
    "LIMITE_TERRITORIAL_INVALIDO",
    "LIMITE_TERRITORIAL_INVALIDO_O_CRS_NO_CONFIRMADO",
    "CRS_REFERENCIA_NO_CONFIRMADO",
    "PROCEDENCIA_REFERENCIA_INCOMPLETA",
    "TERRITORIO_NO_CONFIRMADO",
    "GEOMETRIA_REAL_DE_PRECISION_NO_DISPONIBLE",
    "NUCLEO_URBANO_CONTRADICTORIO_REFERENCIA",
    "GEOMETRIA_FUERA_NUCLEO_DECLARADO",
    "COORDENADA_Y_REFERENCIA_CONTRADICTORIAS",
    "MULTIPLES_CANDIDATOS",
    "MARGEN_SIMILITUD_INSUFICIENTE",
    "BUSQUEDA_REFERENCIAL_TRUNCADA",
}
_ABSENT_FLAG_VALUES = {
    "",
    "NULL",
    "NONE",
    "NAN",
    "N/A",
    "NA",
    "S/D",
    "SIN DATO",
    "SIN DATOS",
    "NO DISPONIBLE",
    "NO INFORMADO",
    "DESCONOCIDO",
    "DESCONOCIDA",
    "SIN NOMBRE",
    "NO ESPECIFICADO",
    "NO ESPECIFICADA",
    "S/N",
    "SN",
    "SIN NUMERO",
}
_FLAG_CONFLICTS = {
    "COMPONENTES_CONTRADICTORIOS",
    "COORDENADAS_CONTRADICTORIAS",
    "UBIGEO_CONFLICTIVO_ORIGEN",
    "CRS_CONFLICTIVO",
    "FILA_ORIGEN_CON_INCIDENCIA",
}
_FLAG_STREET_TYPES = {
    "AVENIDA",
    "JIRON",
    "CALLE",
    "PASAJE",
    "CARRETERA",
    "MALECON",
    "PROLONGACION",
}
_REFERENCE_PENDING = {
    "LIMITE_TERRITORIAL_NO_DISPONIBLE",
    "LIMITE_TERRITORIAL_INVALIDO",
    "LIMITE_TERRITORIAL_INVALIDO_O_CRS_NO_CONFIRMADO",
    "CRS_NO_CONFIRMADO",
    "CRS_REFERENCIA_NO_CONFIRMADO",
    "PROCEDENCIA_REFERENCIA_INCOMPLETA",
    "REFERENCIA_DE_ETAPA_NO_DISPONIBLE",
    "REFERENCIA_NO_DISPONIBLE",
}


def _flag_value(value) -> str:
    if not isinstance(value, str):
        return ""
    normalized = key(value)
    if (
        normalized in _ABSENT_FLAG_VALUES
        or re.search(r"[;|/]", normalized)
        or not re.search(r"[A-Z0-9]", normalized)
    ):
        return ""
    return normalized


def _flag_district(normalized: dict, warnings: set) -> bool:
    code = key(normalized.get("ubigeo"))
    code_present = bool(
        re.fullmatch(r"\d{6}", code)
        and 1 <= int(code[:2]) <= 25
        and int(code[2:4]) > 0
        and int(code[4:]) > 0
        and not {"UBIGEO_INVALIDO", "UBIGEO_REQUIERE_VALIDACION_CATALOGO"} & warnings
    )
    # This checks that a district was explicitly supplied, not that a name has
    # been geographically disambiguated against a national gazetteer.
    district = _flag_value(normalized.get("district"))
    district_present = bool(district and re.search(r"[A-Z]", district) and "," not in district)
    return code_present or district_present


def location_quality_flag(normalized: dict) -> dict:
    """Classify input structure using the supplied UBICACION reference sheet.

    Complete flag-1 alternatives take priority over flag 2, in this order:
    coordinates, typed door with district, block with district, crossing with
    district. Flag 2 covers a named nucleus/center with district or a named road
    with explicit jurisdiction. An unknown CRS does not erase coordinate-format
    information; acceptance still requires independent geographic checks.

    Callers pass normalized source fields, never a candidate or resolved output.
    The function does not infer district names, door/block numbers, jurisdiction
    or coordinates from reference matches and never mutates its input.
    """
    warnings = set(normalized.get("warnings") or [])

    def classified(value, reason):
        return {"quality_flag": value, "quality_flag_reason": reason}

    exclusion = flag10_reason(normalized)
    if exclusion:
        return classified(10, exclusion)
    if warnings & _FLAG_CONFLICTS:
        return classified(None, "FLAG_SIN_ASIGNAR_COMPONENTES_CONTRADICTORIOS")
    coordinates = valid_pair(normalized.get("latitude"), normalized.get("longitude"))
    if (
        coordinates
        and normalized.get("coordinate_origin") != "SUSTITUTO_HEREDADO"
        and "COORDENADA_SUSTITUTA" not in warnings
    ):
        return classified(1, "FLAG_1_COORDENADAS_DECLARADAS")
    if "REFERENCIA_RELATIVA" in warnings:
        return classified(None, "FLAG_SIN_ASIGNAR_REFERENCIA_RELATIVA")
    district = _flag_district(normalized, warnings)
    street = _flag_value(street_parts(normalized.get("street_name"))[1])
    street_type = canonical_street_type(normalized.get("street_type"))
    door = key(normalized.get("door_number"))
    block = key(normalized.get("block_number"))
    cross = _flag_value(street_parts(normalized.get("cross_street"))[1])
    if district and street:
        if street_type in _FLAG_STREET_TYPES and re.fullmatch(r"\d+(?:\s*[-/]?\s*[A-Z])?", door):
            return classified(1, "FLAG_1_PUERTA_DISTRITO")
        if re.fullmatch(r"\d+(?:\s*[-/]?\s*[A-Z])?", block):
            return classified(1, "FLAG_1_CUADRA_DISTRITO")
        if cross and cross != street and "CRUCE_MISMA_VIA" not in warnings:
            return classified(1, "FLAG_1_CRUCE_DISTRITO")
    if district and (_flag_value(normalized.get("urban_core")) or _flag_value(normalized.get("center_name"))):
        return classified(2, "FLAG_2_NUCLEO_DISTRITO")
    if street and (
        _flag_value(normalized.get("jurisdiction_name"))
        or _flag_value(normalized.get("jurisdiction_code"))
        or _flag_value(normalized.get("jurisdiction"))
    ):
        return classified(2, "FLAG_2_VIA_JURISDICCION")
    return classified(None, "FLAG_SIN_ASIGNAR_COMPONENTES_INCOMPLETOS")


def quality_review_state(result: dict) -> str:
    """Describe processing/review separately from the input's public flag."""
    resolution = result.get("resolution")
    if resolution == "EXCLUIDO_FLAG_10":
        return "excluded"
    if resolution == "ACEPTADO_AUTOMATICO":
        return "automatic"
    if resolution == "ACEPTADO_MANUAL" and result.get("product") in {"PUNTO", "AREA_TRAMO"}:
        return "accepted_manual"
    if resolution == "PENDIENTE" or (
        not resolution and result.get("quality_status") in {None, "unprocessed"}
    ):
        return "unprocessed"
    if resolution == "NO_EVALUABLE_REFERENCIA" or result.get("quality_status") == "blocked":
        return "reference_pending"
    if (
        resolution in {"SIN_COINCIDENCIA", "INFORMACION_INSUFICIENTE"}
        or result.get("quality_status") == "unmatched"
    ):
        return "unmatched"
    reason = result.get("reason") or ""
    evidence = {
        code
        for candidate in result.get("candidates") or []
        for code in candidate.get("evidence") or []
        if isinstance(code, str)
    }
    if (
        result.get("review_bucket") == "needs_reference"
        or evidence & _REFERENCE_PENDING
        or any(code in reason for code in _REFERENCE_PENDING)
    ):
        return "reference_pending"
    if resolution == "REVISION_REQUERIDA" and result.get("quality_code") == 2:
        return "quick_review"
    if resolution == "ACEPTADO_MANUAL":
        return "unmatched"  # A corrected address without geometry can continue.
    return "detailed_review"


def is_quality_resolved(result: dict | None) -> bool:
    """Only a completed geographic decision is protected from subsequent stages."""
    return bool(
        result
        and result.get("quality_status") == "resolved"
        and result.get("resolution") in _ACCEPTED
        and result.get("product") in {"PUNTO", "AREA_TRAMO"}
    )


def _without_coordinates(normalized: dict) -> dict:
    result = deepcopy(normalized)
    for field in ("latitude", "longitude", "coordinate_origin", "text_coordinates"):
        result.pop(field, None)
    return result


def _empty(normalized: dict, reason: str, *, blocked: bool = False) -> dict:
    return {
        "resolution": "NO_EVALUABLE_REFERENCIA" if blocked else "SIN_COINCIDENCIA",
        "method": "SIN_METODO",
        "precision": "DESCONOCIDA",
        "evidence_band": "SIN_EVIDENCIA",
        "product": "DIRECCION_SIN_PUNTO" if normalized.get("location_normalized") else "NINGUNO",
        "latitude": None,
        "longitude": None,
        "geometry": None,
        "reason": reason,
        "candidates": [],
        "attempts": [],
    }


def _review(result: dict, normalized: dict, reason: str) -> None:
    result.update(
        resolution="REVISION_REQUERIDA",
        evidence_band="REVISION",
        product="DIRECCION_SIN_PUNTO" if normalized.get("location_normalized") else "NINGUNO",
        latitude=None,
        longitude=None,
        geometry=None,
        reason=reason,
    )
    # A stricter policy must not retain a misleading accepted attempt.
    result["attempts"] = [
        attempt for attempt in result.get("attempts", []) if attempt["status"] != "ACEPTADO"
    ]


def _source_geometry(normalized: dict):
    if key(normalized.get("crs")) != "EPSG:4326":
        return None
    if normalized.get("coordinate_origin") not in {"PNP_ORIGINAL", "TEXTO_SIDPOL"}:
        return None
    pair = valid_pair(normalized.get("latitude"), normalized.get("longitude"))
    return matching._valid_geometry({"type": "Point", "coordinates": [pair[1], pair[0]]}) if pair else None


def _source_conflict(normalized: dict, candidate: dict) -> bool:
    source = _source_geometry(normalized)
    target = matching._valid_geometry(candidate.get("geometry"))
    if source is None or target is None or candidate.get("precision") == "CENTRO_POBLADO":
        return False
    if target.geom_type == "Point":
        return not source.equals(target)
    if target.geom_type in {"Polygon", "MultiPolygon"}:
        return not target.covers(source)
    # A line is a reference geometry; its exact binary coordinates cannot
    # establish whether a source point at the side of a road is contradictory.
    return False


def _quick_door(result: dict, normalized: dict) -> bool:
    candidates = result.get("candidates") or []
    if not candidates or set(normalized.get("warnings") or []) & DECISION_WARNINGS:
        return False
    if normalized.get("reference_truncated") or any(code in result.get("reason", "") for code in _UNSAFE):
        return False
    selected = candidates[0]
    evidence = set(selected.get("evidence") or [])
    if not evidence & _FUZZY or not _QUICK_REQUIRED <= evidence or evidence & _UNSAFE:
        return False
    if not selected.get("source") or not selected.get("version"):
        return False
    if selected.get("precision") != "PUERTA" or selected.get("product") != "PUNTO":
        return False
    if _source_conflict(normalized, selected):
        return False
    signatures = {
        json.dumps(candidate.get("geometry"), sort_keys=True)
        for candidate in candidates
        if candidate.get("precision") == "PUERTA"
    }
    return len(signatures) == 1


def classify_quality(result: dict, stage: str, normalized: dict | None = None) -> dict:
    """Return metadata only; never change a geographic decision or its evidence."""
    if stage not in STAGE_KEYS:
        raise ValueError("Etapa de calidad desconocida")
    normalized = normalized or {}
    resolution = result.get("resolution")
    candidates = result.get("candidates") or []
    accepted = resolution in _ACCEPTED and result.get("product") in {"PUNTO", "AREA_TRAMO"}
    if accepted:
        status = "resolved"
    elif candidates or resolution == "REVISION_REQUERIDA":
        status = "review"
    elif resolution == "NO_EVALUABLE_REFERENCIA":
        status = "blocked"
    else:
        status = "unmatched"
    code = None
    if stage == "door":
        if accepted and resolution == "ACEPTADO_AUTOMATICO" and result.get("precision") == "PUERTA":
            code = 1
        elif candidates and _quick_door(result, normalized):
            code = 2
        elif candidates or accepted:
            code = 3
    elif stage == "block" and accepted and result.get("precision") == "CUADRA":
        code = 4
    return {
        "quality_code": code,
        "quality_stage": stage,
        "quality_status": status,
        "quality_reason": result.get("reason") or "SIN_EVIDENCIA",
        "quality_policy_version": POLICY_VERSION,
    }


def quality_after_review(previous_result: dict, reviewed_result: dict, *, action: str | None = None) -> dict:
    """Carry a human decision forward without relabeling it as an automatic Q1."""
    result = {**deepcopy(previous_result), **deepcopy(reviewed_result)}
    stage = previous_result.get("quality_stage")
    if stage not in STAGE_KEYS:
        return result
    fields = classify_quality(result, stage)
    if fields["quality_status"] == "resolved":
        if stage == "door" and previous_result.get("quality_code") in {2, 3}:
            fields["quality_code"] = previous_result["quality_code"]
        elif stage == "door" and result.get("resolution") == "ACEPTADO_MANUAL":
            fields["quality_code"] = 3
    elif action == "unresolved" or result.get("resolution") == "SIN_COINCIDENCIA":
        fields.update(quality_status="unmatched", quality_code=None)
    elif action == "address_only":
        fields.update(quality_status="unmatched", quality_code=None)
    elif action == "reopen":
        previous_code = previous_result.get("quality_code")
        fields.update(quality_status="review", quality_code=3 if previous_code == 1 else previous_code)
    result.update(fields)
    return result


def _settlement(feature: dict) -> bool:
    return matching._kind(feature) == "site" and feature.get("point_role") == "settlement_reference"


def _named_reference_result(normalized: dict, features: list[dict], stage: str) -> dict:
    """Resolve actual center points or police polygons with explicit semantics."""
    ubigeo = matching._ubigeo(normalized.get("ubigeo"))
    boundaries = [feature for feature in features if matching._kind(feature) == "boundary"]
    context = matching._boundary_context(ubigeo, boundaries)
    source = _source_geometry(normalized)
    sought_name = key(
        normalized.get("center_name") or normalized.get("urban_core")
        if stage == "nucleus"
        else normalized.get("jurisdiction_name") or normalized.get("jurisdiction")
    )
    sought_code = key(
        normalized.get("center_code") if stage == "nucleus" else normalized.get("jurisdiction_code")
    )
    candidates, eligibility = [], {}
    for feature in features:
        if stage == "nucleus" and not _settlement(feature):
            continue
        if stage == "jurisdiction" and matching._kind(feature) != "jurisdiction":
            continue
        if ubigeo and matching._ubigeo(feature.get("ubigeo")) != ubigeo:
            continue
        spatial = matching._valid_geometry(feature.get("geometry"))
        expected = {"Point"} if stage == "nucleus" else {"Polygon", "MultiPolygon"}
        shape_valid = spatial is not None and spatial.geom_type in expected
        quality, score = matching._name_match(
            sought_name, feature.get("name"), feature.get("aliases"), street=False
        )
        field = "center_code" if stage == "nucleus" else "jurisdiction_code"
        code_equal = bool(sought_code and sought_code == key(feature.get(field)))
        code_conflict = bool(sought_code and feature.get(field) and not code_equal)
        if code_conflict:
            continue
        by_containment = bool(
            stage == "jurisdiction"
            and not sought_code
            and not sought_name
            and source is not None
            and shape_valid
            and spatial.contains(source)
        )
        if quality == "NONE" and not code_equal and not by_containment:
            continue
        name_conflict = bool(code_equal and sought_name and quality == "NONE")
        exact = quality in {"EXACT", "ALIAS"} or code_equal or by_containment
        evidence = [
            f"REFERENCIA:{feature.get('source') or 'NO_DECLARADA'}",
            f"VERSION:{feature.get('version') or 'NO_DECLARADA'}",
        ]
        evidence.append(
            "COORDENADA_CONFIRMADA_DENTRO_JURISDICCION"
            if by_containment
            else "CODIGO_REFERENCIA_EXACTO"
            if code_equal
            else "COMPONENTES_EXACTOS"
            if quality == "EXACT"
            else "ALIAS_EXPLICITO_COINCIDENTE"
            if quality == "ALIAS"
            else "SIMILITUD_TEXTUAL_REQUIERE_REVISION"
        )
        if name_conflict:
            evidence.append("CODIGO_Y_NOMBRE_REFERENCIA_CONTRADICTORIOS")
        territory_match = bool(ubigeo and matching._ubigeo(feature.get("ubigeo")) == ubigeo)
        evidence.append("UBIGEO_COINCIDENTE" if territory_match else "TERRITORIO_NO_CONFIRMADO")
        if not shape_valid:
            evidence.append("GEOMETRIA_REAL_DE_PRECISION_NO_DISPONIBLE")
        territory, territorial_evidence = (
            matching._territory(spatial, context) if spatial is not None else ("UNKNOWN", [])
        )
        evidence.extend(territorial_evidence)
        confirmed = key(feature.get("crs")) == "EPSG:4326"
        evidence.append("CRS_REFERENCIA_EPSG4326" if confirmed else "CRS_REFERENCIA_NO_CONFIRMADO")
        provenance = bool(feature.get("source") and feature.get("version"))
        if not provenance:
            evidence.append("PROCEDENCIA_REFERENCIA_INCOMPLETA")
        precision, method = (
            ("CENTRO_POBLADO", "CCPP_PUNTO_REFERENCIA")
            if stage == "nucleus"
            else ("JURISDICCION", "JURISDICCION")
        )
        if stage == "nucleus":
            evidence.append("PUNTO_REFERENCIA_CCPP_NO_DOMICILIO_EXACTO")
        candidate = matching._candidate(feature, method, precision, score if sought_name else None, evidence)
        conflict = _source_conflict(normalized, candidate)
        if source is not None and matching._territory(source, context)[0] != "INSIDE":
            conflict = True
        if conflict:
            evidence.append("COORDENADA_Y_REFERENCIA_CONTRADICTORIAS")
        candidates.append(candidate)
        eligibility[id(candidate)] = bool(
            exact
            and shape_valid
            and territory_match
            and territory == "INSIDE"
            and confirmed
            and provenance
            and not name_conflict
            and not conflict
        )
    result = _empty(normalized, "BUSQUEDA_COMPLETADA_SIN_COINCIDENCIA")
    result["candidates"] = candidates
    if not candidates:
        return result
    candidates.sort(key=lambda c: (not eligibility[id(c)], -(c.get("score") or 0), c["id"]))
    selected = candidates[0]
    eligible = [candidate for candidate in candidates if eligibility[id(candidate)]]
    signatures = {json.dumps(candidate["geometry"], sort_keys=True) for candidate in eligible}
    warnings = set(normalized.get("warnings") or []) & DECISION_WARNINGS
    # A mapped center is coarser than a lot; its precision states that limitation.
    warnings.discard("MANZANA_LOTE_REQUIERE_REFERENCIA")
    reasons = sorted(warnings)
    if len(signatures) > 1:
        reasons.append("MULTIPLES_CANDIDATOS")
    if normalized.get("reference_truncated"):
        reasons.append("BUSQUEDA_REFERENCIAL_TRUNCADA")
    if not eligibility[id(selected)]:
        reasons.extend(selected["evidence"])
    result.update(method=selected["method"], precision=selected["precision"])
    if reasons:
        _review(result, normalized, "; ".join(dict.fromkeys(reasons)))
    else:
        result.update(
            resolution="ACEPTADO_AUTOMATICO",
            evidence_band="ALTA",
            product=selected["product"],
            latitude=selected["latitude"],
            longitude=selected["longitude"],
            geometry=selected["geometry"],
            reason="PUNTO_REFERENCIA_CCPP_VERIFICADO_NO_DOMICILIO_EXACTO"
            if stage == "nucleus"
            else "JURISDICCION_VERIFICADA_SIN_PUNTO_INFERIDO",
        )
    return result


def resolve_quality_stage(
    normalized: dict,
    features: list[dict],
    reference_available: bool,
    stage: str,
    *,
    previous_result: dict | None = None,
    available_reference_kinds: list[str] | None = None,
    reference_truncated: bool | None = None,
) -> dict:
    """Evaluate one stage and never replace an already resolved quality result.

    Callers provide the catalog's available kinds even when the territorial
    query returns no records. This distinguishes a completed unmatched search
    from a missing layer. Features and normalized input are never mutated.
    """
    if stage not in STAGE_KEYS:
        raise ValueError("Etapa de calidad desconocida")
    if is_quality_resolved(previous_result):
        result = deepcopy(previous_result)
        result["quality_skipped"] = True
        return result
    excluded = excluded_input_result(normalized)
    if excluded is not None:
        return excluded
    query = deepcopy(normalized)
    if reference_truncated is not None:
        query["reference_truncated"] = reference_truncated
    available = set(
        available_reference_kinds
        if available_reference_kinds is not None
        else query.get("available_reference_kinds") or [matching._kind(feature) for feature in features]
    )
    kinds = _STAGE_KINDS[stage]
    selected = [feature for feature in features if matching._kind(feature) in kinds | {"boundary"}]
    if stage == "nucleus":
        selected = [
            feature for feature in selected if matching._kind(feature) != "site" or _settlement(feature)
        ]
    query["available_reference_kinds"] = sorted(available & (kinds | {"boundary"}))
    if not reference_available or not (available & kinds):
        result = _empty(query, "REFERENCIA_DE_ETAPA_NO_DISPONIBLE", blocked=True)
    elif stage == "jurisdiction":
        result = _named_reference_result(query, selected, stage)
    else:
        ordinary = [feature for feature in selected if not _settlement(feature)]
        ordinary_query = _without_coordinates(query)
        ordinary_query["available_reference_kinds"] = sorted((available & kinds) - {"site"}) + ["boundary"]
        result = matching.resolve_location(ordinary_query, ordinary, True)
        result["attempts"] = [
            attempt for attempt in result["attempts"] if attempt["method"] in _STAGE_METHODS[stage]
        ]
        if stage == "nucleus" and "site" in available:
            centers = _named_reference_result(query, selected, stage)
            # An accepted nucleus polygon retains greater contextual meaning;
            # otherwise an actual center point may provide the named reference.
            if result["resolution"] != "ACEPTADO_AUTOMATICO" and centers["candidates"]:
                if result["candidates"]:
                    centers["candidates"].extend(result["candidates"])
                    _review(centers, query, "REFERENCIAS_NUCLEO_Y_CCPP_REQUIEREN_REVISION")
                result = centers
        if result["candidates"]:
            chosen = result["candidates"][0]
            if _source_conflict(query, chosen):
                chosen["evidence"].append("COORDENADA_Y_REFERENCIA_CONTRADICTORIAS")
                _review(result, query, "COORDENADA_Y_REFERENCIA_CONTRADICTORIAS")
            if stage == "door" and set(chosen["evidence"]) & _FUZZY:
                if result["resolution"] == "ACEPTADO_AUTOMATICO":
                    _review(result, query, "SIMILITUD_DE_PUERTA_REQUIERE_CONFIRMACION_HUMANA")
        elif not query.get("reference_truncated"):
            # Missing components or unrelated unavailable branches do not stop
            # progression when this stage's layer was actually available.
            result = _empty(query, "BUSQUEDA_COMPLETADA_SIN_COINCIDENCIA")
    if (
        query.get("reference_truncated")
        and not result["candidates"]
        and result["resolution"] != "NO_EVALUABLE_REFERENCIA"
    ):
        _review(result, query, "BUSQUEDA_REFERENCIAL_TRUNCADA")
    result.update(classify_quality(result, stage, query))
    result["attempts"].append(
        {
            "method": "ETAPA_CALIDAD",
            "stage": stage,
            "status": result["quality_status"],
            "reason": result["quality_reason"],
            "candidate_count": len(result["candidates"]),
            "quality_policy_version": POLICY_VERSION,
        }
    )
    return result
