"""Local evidence-based matching. Similarity scores are never probabilities.

The caller supplies a bounded territorial subset and truncation metadata. This
module never transforms coordinates, generates centroids or calls a service.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from typing import Any

from rapidfuzz.fuzz import ratio
from shapely.errors import GEOSException
from shapely.geometry import shape
from shapely.ops import linemerge, unary_union

from . import RULES_VERSION
from .normalization import DECISION_WARNINGS, canonical_street_type, key, street_parts, text, valid_pair

_KIND_ALIASES = {
    "puerta": "door",
    "cuadra": "block",
    "cruce": "intersection",
    "sitio": "site",
    "nucleo": "nucleus",
    "limite": "boundary",
    "via": "street",
}
_GEOMETRIES = {
    "door": {"Point"},
    "intersection": {"Point"},
    "block": {"LineString", "MultiLineString", "Polygon", "MultiPolygon"},
    "street": {"LineString", "MultiLineString"},
    "manzana": {"Polygon", "MultiPolygon"},
    "nucleus": {"Polygon", "MultiPolygon"},
    "site": {"Point", "Polygon", "MultiPolygon"},
    "boundary": {"Polygon", "MultiPolygon"},
}
_PRECISION_RANK = {
    "COORDENADA": 70,
    "PUERTA": 60,
    "INTERSECCION": 60,
    "SITIO": 50,
    "MANZANA": 40,
    "CUADRA": 40,
    "VIA": 20,
    "NUCLEO": 10,
}
_FUZZY_THRESHOLD = 96
_FUZZY_MARGIN = 5


def _kind(feature: dict) -> str:
    value = str(feature.get("kind", "")).lower()
    return _KIND_ALIASES.get(value, value)


def _street(value: Any) -> str:
    return street_parts(value)[1]


def _number(value: Any) -> str:
    # Keep numeric names, suffixes and leading zeros distinct.
    return re.sub(r"\s+", "", key(value))


def _ubigeo(value: Any) -> str:
    value = text(value)
    return value.zfill(6) if re.fullmatch(r"\d{1,6}", value) else ""


def _stable_id(feature: dict) -> str:
    if feature.get("id") is not None:
        return str(feature["id"])
    return hashlib.sha256(
        json.dumps(feature, sort_keys=True, ensure_ascii=False, default=str).encode()
    ).hexdigest()[:20]


def _valid_geometry(value: Any):
    try:
        geometry = shape(value or {})
        if geometry.is_empty or not geometry.is_valid or geometry.has_z:
            return None
        west, south, east, north = geometry.bounds
        if (
            not all(math.isfinite(v) for v in geometry.bounds)
            or west < -180
            or east > 180
            or south < -90
            or north > 90
        ):
            return None
        return geometry
    except (ValueError, TypeError, KeyError, AttributeError, GEOSException):
        return None


def _boundary_context(ubigeo: str, boundaries: list[dict]) -> tuple[Any, list[str], dict[str, str]]:
    relevant = [f for f in boundaries if ubigeo and _ubigeo(f.get("ubigeo")) == ubigeo]
    if not relevant:
        return None, ["LIMITE_TERRITORIAL_NO_DISPONIBLE"], {}
    polygons, evidence, versions = [], [], {}
    for feature in relevant:
        polygon = _valid_geometry(feature.get("geometry"))
        if (
            polygon is not None
            and polygon.geom_type in _GEOMETRIES["boundary"]
            and key(feature.get("crs")) == "EPSG:4326"
            and feature.get("source")
            and feature.get("version")
        ):
            polygons.append(polygon)
            evidence.extend([f"LIMITE:{_stable_id(feature)}", f"VERSION:{feature['version']}"])
            versions[_stable_id(feature)] = str(feature["version"])
    if not polygons:
        return None, ["LIMITE_TERRITORIAL_INVALIDO_O_CRS_NO_CONFIRMADO"], {}
    try:
        return unary_union(polygons), evidence, versions
    except (ValueError, GEOSException):
        return None, ["LIMITE_TERRITORIAL_INVALIDO"], {}


def _territory(geometry: Any, context: tuple, feature: dict | None = None) -> tuple[str, list[str]]:
    polygon, evidence, versions = context
    if polygon is None:
        return "UNKNOWN", list(evidence)
    try:
        if geometry.geom_type == "Point":
            if polygon.contains(geometry):
                return "INSIDE", ["PUNTO_DENTRO_UBIGEO", *evidence]
            if polygon.covers(geometry):
                return "BORDER", ["PUNTO_EN_LIMITE_TERRITORIAL", *evidence]
            return "OUTSIDE", ["PUNTO_FUERA_UBIGEO", *evidence]
        if polygon.covers(geometry) or geometry.difference(polygon).is_empty:
            return "INSIDE", ["GEOMETRIA_COMPLETA_DENTRO_UBIGEO", *evidence]
        # Clipping is an arithmetic operation on binary doubles. Only a proven
        # clip against this exact boundary/version may use an ULP-scale guard.
        # This is not a geographic tolerance and never changes stored geometry.
        feature = feature or {}
        proven_clip = (
            geometry.geom_type in {"LineString", "MultiLineString"}
            and str(feature.get("geometry_transform", "")).startswith("clip_to_boundary")
            and str(feature.get("clip_boundary_id")) in versions
            and versions[str(feature.get("clip_boundary_id"))] == str(feature.get("clip_boundary_version"))
        )
        if proven_clip:
            tolerance = min(1e-11, 64 * max(math.ulp(v) for v in (*polygon.bounds, *geometry.bounds)))
            if polygon.buffer(tolerance).covers(geometry):
                return "INSIDE", [
                    "RECORTE_VERIFICADO_RESIDUO_NUMERICO_ULP",
                    f"TOLERANCIA_ARITMETICA_GRADOS:{tolerance:.17g}",
                    *evidence,
                ]
        return "OUTSIDE", ["GEOMETRIA_EXCEDE_UBIGEO", *evidence]
    except (ValueError, GEOSException):
        return "UNKNOWN", ["LIMITE_TERRITORIAL_INVALIDO"]


def _name_match(sought: str, found: Any, aliases: Any = None, *, street: bool = True) -> tuple[str, float]:
    canonical = _street if street else key
    names = [canonical(found)]
    if isinstance(aliases, list):
        names.extend(canonical(alias) for alias in aliases if isinstance(alias, str))
    names = list(dict.fromkeys(name for name in names if name))
    if not sought or not names:
        return "NONE", 0.0
    if sought == names[0]:
        return "EXACT", 100.0
    if sought in names[1:]:
        return "ALIAS", 100.0
    best = max(names, key=lambda name: ratio(sought, name))
    similarity = float(ratio(sought, best))
    numbers_equal = re.findall(r"\d+", sought) == re.findall(r"\d+", best)
    if not numbers_equal or similarity < 88 or min(len(sought), len(best)) < 5:
        return "NONE", similarity
    strong = (
        similarity >= _FUZZY_THRESHOLD
        and min(len(sought), len(best)) >= 10
        and len(sought.split()) == len(best.split())
    )
    return ("STRONG_FUZZY" if strong else "WEAK_FUZZY"), similarity


def _candidate(feature: dict, method: str, precision: str, score: float | None, evidence: list[str]) -> dict:
    geometry = feature.get("geometry")
    point = (
        geometry
        and geometry.get("type") == "Point"
        and precision not in {"MANZANA", "CUADRA", "VIA", "NUCLEO"}
    )
    pair = (
        valid_pair(geometry["coordinates"][1], geometry["coordinates"][0])
        if point and len(geometry.get("coordinates", [])) == 2
        else None
    )
    label = " ".join(
        str(v)
        for v in (
            feature.get("street_type"),
            feature.get("street_name"),
            feature.get("door_number") or feature.get("block_number") or feature.get("manzana_code"),
        )
        if v
    )
    if feature.get("cross_street"):
        label += " / " + str(feature["cross_street"])
    return {
        "id": _stable_id(feature),
        "label": feature.get("name") or label or "Referencia",
        "method": method,
        "precision": precision,
        "product": "PUNTO" if point else "AREA_TRAMO",
        "latitude": pair[0] if pair else None,
        "longitude": pair[1] if pair else None,
        "score": round(score, 2) if score is not None else None,
        "score_type": "SIMILITUD_TEXTUAL_NO_PROBABILIDAD" if score is not None else "NO_APLICA",
        "evidence": evidence,
        "geometry": geometry,
        "source": feature.get("source"),
        "version": feature.get("version"),
        "reference_metadata": {
            name: feature[name]
            for name in (
                "geometry_transform",
                "clip_boundary_id",
                "clip_boundary_version",
                "osm_way_ids",
                "source_url",
                "license",
                "point_role",
            )
            if name in feature
        },
    }


def resolve_location(normalized: dict, features: list[dict], reference_available: bool) -> dict:
    ubigeo = _ubigeo(normalized.get("ubigeo"))
    warnings = set(normalized.get("warnings") or [])
    input_crs_confirmed = key(normalized.get("crs")) == "EPSG:4326"
    boundaries = [f for f in features if _kind(f) == "boundary"]
    territorial_context = _boundary_context(ubigeo, boundaries)
    available = set(normalized.get("available_reference_kinds") or [_kind(f) for f in features])
    candidates: list[dict] = []
    attempts: list[dict] = []
    states: dict[int, dict] = {}  # Eligibility belongs to evidence, never a public ID.
    applicable, searched_any, missing_any = [], False, False

    def attempt(method, status, reason, count=0, **extra):
        attempts.append(
            {
                "method": method,
                "status": status,
                "reason": reason,
                "candidate_count": count,
                "rules_version": RULES_VERSION,
                **extra,
            }
        )

    def add(candidate, *, auto=False, quality="EXACT", geometry=None, territorial=False):
        candidates.append(candidate)
        states[id(candidate)] = {
            "auto": auto,
            "quality": quality,
            "geometry": geometry,
            "territorial": territorial,
        }

    coordinate = valid_pair(normalized.get("latitude"), normalized.get("longitude"))
    origin = normalized.get("coordinate_origin")
    if coordinate and origin in {"PNP_ORIGINAL", "TEXTO_SIDPOL"}:
        method = "COORD_TEXTO" if origin == "TEXTO_SIDPOL" else "COORD_ORIGINAL"
        geometry = {"type": "Point", "coordinates": [coordinate[1], coordinate[0]]}
        spatial = _valid_geometry(geometry)
        territory, evidence = _territory(spatial, territorial_context)
        if not input_crs_confirmed:
            evidence.append("CRS_NO_CONFIRMADO")
        candidate = _candidate(
            {
                "id": f"{method.lower()}:source",
                "name": "Coordenada extraída del texto"
                if method == "COORD_TEXTO"
                else "Coordenada original declarada",
                "geometry": geometry,
                "source": "ARCHIVO_ORIGINAL",
                "version": RULES_VERSION,
            },
            method,
            "COORDENADA",
            None,
            [origin, *evidence],
        )
        add(
            candidate,
            auto=territory == "INSIDE" and input_crs_confirmed,
            geometry=spatial,
            territorial=territory == "INSIDE",
        )
        attempt(method, "CANDIDATOS_ENCONTRADOS", "; ".join(evidence), 1)
    else:
        attempt(
            "COORD_ORIGINAL",
            "NO_APLICABLE",
            "COORDENADA_SUSTITUTA" if origin == "SUSTITUTO_HEREDADO" else "SIN_COORDENADA_ORIGINAL_VALIDA",
        )
    conflicting = normalized.get("text_coordinates")
    if conflicting and (pair := valid_pair(conflicting.get("latitude"), conflicting.get("longitude"))):
        geometry = {"type": "Point", "coordinates": [pair[1], pair[0]]}
        add(
            _candidate(
                {
                    "id": "coord_texto:conflict",
                    "name": "Coordenada textual contradictoria",
                    "geometry": geometry,
                    "source": "ARCHIVO_ORIGINAL",
                    "version": RULES_VERSION,
                },
                "COORD_TEXTO",
                "COORDENADA",
                None,
                ["COORDENADAS_CONTRADICTORIAS"],
            ),
            geometry=_valid_geometry(geometry),
        )
        attempt("COORD_TEXTO", "CANDIDATOS_ENCONTRADOS", "COORDENADAS_CONTRADICTORIAS", 1)

    street = _street(normalized.get("street_name"))
    street_type = canonical_street_type(normalized.get("street_type"))
    cross = _street(normalized.get("cross_street"))
    door, block = _number(normalized.get("door_number")), _number(normalized.get("block_number"))
    manzana, lot = _number(normalized.get("manzana_code")), _number(normalized.get("lot_number"))
    site, nucleus = key(normalized.get("site_name")), key(normalized.get("urban_core"))
    nucleus_geometries = []
    if nucleus:
        for feature in features:
            if (
                _kind(feature) != "nucleus"
                or _ubigeo(feature.get("ubigeo")) != ubigeo
                or key(feature.get("crs")) != "EPSG:4326"
            ):
                continue
            quality, _ = _name_match(nucleus, feature.get("name"), feature.get("aliases"), street=False)
            geometry = _valid_geometry(feature.get("geometry"))
            if (
                quality in {"EXACT", "ALIAS"}
                and geometry is not None
                and geometry.geom_type in _GEOMETRIES["nucleus"]
                and feature.get("source")
                and feature.get("version")
            ):
                nucleus_geometries.append(geometry)
    branches = [
        ("door", "PUERTA_CON_TIPO" if street_type else "PUERTA_SIN_TIPO", "PUERTA", bool(street and door)),
        ("intersection", "CRUCE", "INTERSECCION", bool(street and cross)),
        ("site", "SITIO", "SITIO", bool(site)),
        ("manzana", "MANZANA", "MANZANA", bool(manzana)),
        ("block", "CUADRA_CON_TIPO" if street_type else "CUADRA_SIN_TIPO", "CUADRA", bool(street and block)),
        ("street", "VIA_JURISDICCION", "VIA", bool(street)),
        ("nucleus", "NUCLEO", "NUCLEO", bool(nucleus)),
    ]
    for kind, method, precision, is_applicable in branches:
        if not is_applicable:
            attempt(method, "NO_APLICABLE", "COMPONENTES_AUSENTES")
            continue
        applicable.append(kind)
        if not reference_available or kind not in available:
            missing_any = True
            attempt(method, "NO_EVALUABLE_REFERENCIA", "REFERENCIA_NO_DISPONIBLE")
            continue
        searched_any = True
        count_before = len(candidates)
        eligible = [
            f for f in features if _kind(f) == kind and (not ubigeo or _ubigeo(f.get("ubigeo")) == ubigeo)
        ]
        for feature in eligible:
            ftype = canonical_street_type(feature.get("street_type"))
            evidence = [
                f"REFERENCIA:{feature.get('source') or 'NO_DECLARADA'}",
                f"VERSION:{feature.get('version') or 'NO_DECLARADA'}",
            ]
            quality, similarity, corroborated = "NONE", 0.0, False
            if kind in {"door", "block", "street"}:
                if street_type and ftype and ftype != street_type:
                    continue
                if kind != "street":
                    field, sought = ("door_number", door) if kind == "door" else ("block_number", block)
                    if sought != _number(feature.get(field)):
                        continue
                    evidence.append("NUMERO_COINCIDENTE")
                    corroborated = bool(street_type and ftype == street_type)
                quality, similarity = _name_match(
                    street, feature.get("street_name") or feature.get("name"), feature.get("aliases")
                )
                evidence.append(
                    "TIPO_COINCIDENTE"
                    if street_type and ftype
                    else "TIPO_REFERENCIA_AUSENTE"
                    if street_type
                    else "TIPO_NO_RESTRINGIDO"
                )
            elif kind == "intersection":
                ordered = [
                    (
                        _name_match(street, feature.get("street_name"), feature.get("aliases")),
                        _name_match(cross, feature.get("cross_street"), feature.get("cross_aliases")),
                    ),
                    (
                        _name_match(street, feature.get("cross_street"), feature.get("cross_aliases")),
                        _name_match(cross, feature.get("street_name"), feature.get("aliases")),
                    ),
                ]
                matches = max(ordered, key=lambda pair: min(m[1] for m in pair))
                quality = (
                    "NONE"
                    if any(m[0] == "NONE" for m in matches)
                    else "WEAK_FUZZY"
                    if any(m[0] == "WEAK_FUZZY" for m in matches)
                    else "STRONG_FUZZY"
                    if any(m[0] == "STRONG_FUZZY" for m in matches)
                    else "ALIAS"
                    if any(m[0] == "ALIAS" for m in matches)
                    else "EXACT"
                )
                similarity = min(m[1] for m in matches)
                corroborated = feature.get("connects_at_grade") is True and any(
                    m[0] in {"EXACT", "ALIAS"} for m in matches
                )
                evidence.append(
                    "CONEXION_A_NIVEL_CONFIRMADA"
                    if feature.get("connects_at_grade") is True
                    else "CONEXION_A_NIVEL_NO_CONFIRMADA"
                )
            elif kind == "manzana":
                if manzana != _number(feature.get("manzana_code")):
                    continue
                contexts = []
                if nucleus:
                    contexts.append(
                        _name_match(
                            nucleus,
                            feature.get("urban_core"),
                            feature.get("urban_core_aliases"),
                            street=False,
                        )
                    )
                if street:
                    contexts.append(_name_match(street, feature.get("street_name"), feature.get("aliases")))
                if not contexts:
                    quality, similarity = "WEAK_FUZZY", 100.0
                    evidence.append("CONTEXTO_MANZANA_NO_CONFIRMADO")
                elif any(m[0] == "NONE" for m in contexts):
                    continue
                else:
                    quality = "EXACT" if all(m[0] in {"EXACT", "ALIAS"} for m in contexts) else "WEAK_FUZZY"
                    similarity = min(m[1] for m in contexts)
                    evidence.append("CONTEXTO_MANZANA_COINCIDENTE")
                evidence.append("CODIGO_MANZANA_EXACTO")
                if lot:
                    evidence.append("LOTE_NO_RESUELTO_PRECISION_MANZANA")
            else:
                quality, similarity = _name_match(
                    site if kind == "site" else nucleus,
                    feature.get("name"),
                    feature.get("aliases"),
                    street=False,
                )
            if quality == "NONE":
                continue
            evidence.append(
                {
                    "EXACT": "COMPONENTES_EXACTOS",
                    "ALIAS": "ALIAS_EXPLICITO_COINCIDENTE",
                    "STRONG_FUZZY": "SIMILITUD_FUERTE_CON_GUARDAS",
                    "WEAK_FUZZY": "SIMILITUD_TEXTUAL_REQUIERE_REVISION",
                }[quality]
            )
            territory_match = bool(ubigeo and _ubigeo(feature.get("ubigeo")) == ubigeo)
            evidence.append("UBIGEO_COINCIDENTE" if territory_match else "TERRITORIO_NO_CONFIRMADO")
            geometry = _valid_geometry(feature.get("geometry"))
            shape_valid = geometry is not None and geometry.geom_type in _GEOMETRIES[kind]
            if not shape_valid:
                evidence.append("GEOMETRIA_REAL_DE_PRECISION_NO_DISPONIBLE")
            territory = "UNKNOWN"
            if geometry is not None:
                territory, territorial_evidence = _territory(geometry, territorial_context, feature)
                evidence.extend(territorial_evidence)
            reference_crs = key(feature.get("crs")) == "EPSG:4326"
            evidence.append("CRS_REFERENCIA_EPSG4326" if reference_crs else "CRS_REFERENCIA_NO_CONFIRMADO")
            provenance = bool(feature.get("source") and feature.get("version"))
            if not provenance:
                evidence.append("PROCEDENCIA_REFERENCIA_INCOMPLETA")
            specific = True
            if nucleus and kind not in {"nucleus", "manzana"}:
                declared_context = key(feature.get("urban_core"))
                if declared_context:
                    context_quality, _ = _name_match(
                        nucleus, declared_context, feature.get("urban_core_aliases"), street=False
                    )
                    if context_quality not in {"EXACT", "ALIAS"}:
                        specific = False
                        evidence.append("NUCLEO_URBANO_CONTRADICTORIO_REFERENCIA")
                    else:
                        evidence.append("NUCLEO_URBANO_COINCIDENTE")
                elif nucleus_geometries and geometry is not None:
                    if any(area.covers(geometry) for area in nucleus_geometries):
                        evidence.append("GEOMETRIA_DENTRO_NUCLEO_DECLARADO")
                        corroborated = corroborated or bool(street_type and ftype == street_type)
                    else:
                        specific = False
                        evidence.append("GEOMETRIA_FUERA_NUCLEO_DECLARADO")
                else:
                    evidence.append("CONTEXTO_URBANO_REFERENCIAL_NO_DISPONIBLE")
            if kind == "intersection":
                specific = specific and feature.get("connects_at_grade") is True
            if kind == "site" and geometry is not None and geometry.geom_type == "Point":
                specific = specific and feature.get("point_role") in {"mapped_poi", "entrance"}
                if not specific:
                    evidence.append("PUNTO_SITIO_NO_IDENTIFICADO_COMO_NODO_O_ENTRADA")
            if kind == "street":
                disconnected = (
                    geometry is not None
                    and geometry.geom_type == "MultiLineString"
                    and linemerge(geometry).geom_type != "LineString"
                )
                if feature.get("ambiguous") is True or feature.get("branched") is True or disconnected:
                    specific = False
                    evidence.append("VIA_RAMIFICADA_O_AMBIGUA")
                if door:
                    evidence.append("PUERTA_NO_RESUELTA_PRECISION_VIA")
                if block:
                    evidence.append("CUADRA_NO_RESUELTA_PRECISION_VIA")
                if cross:
                    specific = False
                    evidence.append("CRUCE_NO_RESUELTO_POR_UNA_VIA")
            auto_name = quality in {"EXACT", "ALIAS"} or (quality == "STRONG_FUZZY" and corroborated)
            if quality == "STRONG_FUZZY" and not corroborated:
                evidence.append("SIMILITUD_SIN_COMPONENTE_INDEPENDIENTE")
            candidate = _candidate(feature, method, precision, similarity, evidence)
            add(
                candidate,
                auto=bool(
                    auto_name
                    and shape_valid
                    and territory_match
                    and territory == "INSIDE"
                    and reference_crs
                    and provenance
                    and specific
                ),
                quality=quality,
                geometry=geometry,
                territorial=territory_match and territory == "INSIDE",
            )
        count = len(candidates) - count_before
        attempt(
            method,
            "CANDIDATOS_ENCONTRADOS" if count else "SIN_CANDIDATO",
            "COINCIDENCIAS_REFERENCIA" if count else "BUSQUEDA_COMPLETADA_SIN_COINCIDENCIA",
            count,
            reference_versions=sorted({str(f.get("version")) for f in eligible if f.get("version")}),
        )

    result = {
        "resolution": "INFORMACION_INSUFICIENTE",
        "method": "SIN_METODO",
        "precision": "DESCONOCIDA",
        "evidence_band": "SIN_EVIDENCIA",
        "product": "NINGUNO",
        "latitude": None,
        "longitude": None,
        "geometry": None,
        "reason": "DIRECCION_INSUFICIENTE",
        "candidates": candidates,
        "attempts": attempts,
    }
    if candidates:

        def rank(candidate):
            state = states[id(candidate)]
            return (
                not state["auto"],
                -_PRECISION_RANK[candidate["precision"]],
                -(candidate["score"] or 0),
                candidate["id"],
            )

        candidates.sort(key=rank)
        chosen = candidates[0]
        chosen_state = states[id(chosen)]
        reasons = []
        hard_warnings = warnings & DECISION_WARNINGS
        independent_original = (
            chosen["method"] == "COORD_ORIGINAL"
            and chosen_state["auto"]
            and "MANZANA_LOTE_REQUIERE_REFERENCIA" in hard_warnings
        )
        resolved_area = (
            chosen["product"] == "AREA_TRAMO"
            and chosen_state["auto"]
            and chosen["precision"] in {"MANZANA", "CUADRA", "VIA", "NUCLEO"}
        )
        if independent_original or resolved_area:
            hard_warnings.discard("MANZANA_LOTE_REQUIERE_REFERENCIA")
            chosen["evidence"].append(
                "MANZANA_LOTE_NO_LIMITA_COORDENADA_ORIGINAL_VALIDADA"
                if independent_original
                else "MANZANA_RESUELTA_LOTE_NO_INFERIDO"
                if chosen["precision"] == "MANZANA"
                else f"MANZANA_LOTE_NO_RESUELTOS_PRECISION_{chosen['precision']}"
            )
        # Weak alternatives cannot defeat exact evidence. Finer eligible
        # ambiguity is retained rather than concealed by a coarser fallback.
        peers = [
            c
            for c in candidates
            if states[id(c)]["auto"]
            and _PRECISION_RANK[c["precision"]] == _PRECISION_RANK[chosen["precision"]]
        ]
        if chosen_state["quality"] in {"EXACT", "ALIAS"}:
            peers = [c for c in peers if states[id(c)]["quality"] in {"EXACT", "ALIAS"}]
        signatures = {
            (
                c["method"],
                c["precision"],
                c["product"],
                json.dumps(c["geometry"], sort_keys=True, separators=(",", ":")),
            )
            for c in peers
        }
        equivalent = len(peers) > 1 and len(signatures) == 1
        ambiguity = len(signatures) > 1
        if equivalent:
            for candidate in peers:
                candidate["evidence"].append(
                    "EVIDENCIAS_EQUIVALENTES_MISMO_PUNTO"
                    if chosen["product"] == "PUNTO"
                    else "EVIDENCIAS_EQUIVALENTES_MISMA_GEOMETRIA"
                )
        if chosen_state["quality"] == "STRONG_FUZZY":
            rivals = [
                c
                for c in candidates
                if c is not chosen
                and c["method"] == chosen["method"]
                and states[id(c)]["territorial"]
                and c["geometry"] != chosen["geometry"]
                and (chosen["score"] or 0) - (c["score"] or 0) < _FUZZY_MARGIN
            ]
            if rivals:
                ambiguity = True
                reasons.append("MARGEN_SIMILITUD_INSUFICIENTE")
            else:
                chosen["evidence"].append("MARGEN_SIMILITUD_SUFICIENTE")
        # Source coordinates in a confirmed CRS must agree with independently
        # eligible reference evidence; unknown source CRS cannot veto a reference.
        source_candidates = [
            c
            for c in candidates
            if c["method"] in {"COORD_ORIGINAL", "COORD_TEXTO"}
            and input_crs_confirmed
            and states[id(c)]["geometry"] is not None
        ]
        reference_candidates = [
            c for c in candidates if not c["method"].startswith("COORD_") and states[id(c)]["auto"]
        ]
        if reference_candidates:
            best_reference_precision = max(_PRECISION_RANK[c["precision"]] for c in reference_candidates)
            reference_candidates = [
                c for c in reference_candidates if _PRECISION_RANK[c["precision"]] == best_reference_precision
            ]
        for source in source_candidates:
            source_geometry = states[id(source)]["geometry"]
            for reference in reference_candidates:
                reference_geometry = states[id(reference)]["geometry"]
                agrees = (
                    source["geometry"] == reference["geometry"]
                    if reference["product"] == "PUNTO"
                    else reference_geometry.covers(source_geometry)
                )
                if not agrees and reference_geometry.geom_type not in {"LineString", "MultiLineString"}:
                    reasons.append("COORDENADA_Y_REFERENCIA_CONTRADICTORIAS")
                elif agrees:
                    chosen["evidence"].append("COORDENADA_Y_REFERENCIA_CONCORDANTES")
        if ambiguity:
            reasons.append("MULTIPLES_CANDIDATOS")
        reasons.extend(sorted(hard_warnings))
        if normalized.get("reference_truncated"):
            reasons.append("BUSQUEDA_REFERENCIAL_TRUNCADA")
        if not chosen_state["auto"]:
            reasons.extend(chosen["evidence"])
        accepted = chosen_state["auto"] and not reasons
        accepted_reason = (
            "EVIDENCIAS_EQUIVALENTES_MISMO_PUNTO"
            if equivalent and chosen["product"] == "PUNTO"
            else "EVIDENCIAS_EQUIVALENTES_MISMA_GEOMETRIA"
            if equivalent
            else "COORDENADA_ORIGINAL_VALIDADA_INDEPENDIENTE_DE_MANZANA_LOTE"
            if independent_original
            else "COINCIDENCIA_APROXIMADA_FUERTE_CON_EVIDENCIA_INDEPENDIENTE"
            if chosen_state["quality"] == "STRONG_FUZZY"
            else "COINCIDENCIA_UNICA_CON_EVIDENCIA_TERRITORIAL"
        )
        result.update(
            resolution="ACEPTADO_AUTOMATICO" if accepted else "REVISION_REQUERIDA",
            method=chosen["method"],
            precision=chosen["precision"],
            evidence_band="ALTA" if accepted else "REVISION",
            product=chosen["product"]
            if accepted
            else "DIRECCION_SIN_PUNTO"
            if normalized.get("location_normalized")
            else "NINGUNO",
            latitude=chosen["latitude"] if accepted else None,
            longitude=chosen["longitude"] if accepted else None,
            geometry=chosen["geometry"] if accepted else None,
            reason=accepted_reason
            if accepted
            else "; ".join(dict.fromkeys(reasons)) or "VERIFICACION_HUMANA_REQUERIDA",
        )
        if accepted:
            attempt(chosen["method"], "ACEPTADO", result["reason"], len(candidates))
    elif normalized.get("reference_truncated"):
        result.update(
            resolution="REVISION_REQUERIDA", evidence_band="REVISION", reason="BUSQUEDA_REFERENCIAL_TRUNCADA"
        )
    elif not ubigeo and (applicable or coordinate):
        result.update(
            resolution="REVISION_REQUERIDA", evidence_band="REVISION", reason="TERRITORIO_NO_CONFIRMADO"
        )
    elif searched_any:
        result.update(resolution="SIN_COINCIDENCIA", reason="BUSQUEDA_COMPLETADA_SIN_COINCIDENCIA")
    elif missing_any:
        result.update(resolution="NO_EVALUABLE_REFERENCIA", reason="REFERENCIA_NO_DISPONIBLE")
    elif warnings & {
        "COORDENADAS_ESTRUCTURADAS_INVALIDAS",
        "COORDENADAS_TEXTO_INVALIDAS",
        "COORDENADA_SUSTITUTA",
    }:
        result.update(
            resolution="REVISION_REQUERIDA", evidence_band="REVISION", reason="; ".join(sorted(warnings))
        )
    return result
