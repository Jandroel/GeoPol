"""Auditable Spanish address extraction and conservative coordinate interpretation."""

from __future__ import annotations

import math
import re
import unicodedata
from functools import lru_cache
from typing import Any

from . import RULES_VERSION


def text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def key(value: Any) -> str:
    value = text(value)
    # Bounded cache saves repeated field names/reference names without retaining files.
    return _cached_key(value) if len(value) <= 2048 else _plain_key(value)


def _plain_key(value: str) -> str:
    value = unicodedata.normalize("NFKD", value)
    value = "".join(c for c in value if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", value.upper()).strip()


_cached_key = lru_cache(maxsize=1024)(_plain_key)


def column_key(value: Any) -> str:
    return re.sub(r"[^A-Z0-9]", "", key(value))


# DIRECCION is intentionally excluded: in SIDPOL it can identify the police station.
# Final lat_hecho/long_hecho are retained as legacy evidence, never original axes.
ALIASES = {
    "complaint_id": ("complaint_id", "ID_DENUNCIA", "denuncia_id"),
    "location_original": ("location_original", "UBICACION", "direccion_hecho", "address"),
    "ubigeo": ("UBIGEO_HECHO", "ubigeo"),
    "district": ("DIST_HECHO", "district", "distrito_hecho", "distrito"),
    "street_type": ("street_type", "tipo_via", "VIA"),
    "street_name": ("street_name", "nombre_via"),
    "door_number": ("door_number", "numero_puerta", "puerta"),
    "block_number": ("block_number", "CUADRA"),
    "cross_street": ("cross_street", "via_cruce", "segunda_via"),
    "site_name": ("site_name", "sitio"),
    "urban_core": ("urban_core", "nucleo_urbano"),
    "latitude": ("xx", "latitude", "latitud", "lat"),
    "longitude": ("yy", "longitude", "longitud", "lon", "lng"),
    "coordinate_origin": ("coordinate_origin", "origen_coordenadas"),
    "crs": ("crs", "srid"),
}


def suggest_mapping(columns: list[str]) -> dict[str, str]:
    if len(columns) > 128 or any(len(column) > 256 for column in columns):
        return dict(_mapping_for_columns.__wrapped__(tuple(columns)))
    return dict(_mapping_for_columns(tuple(columns)))


_ALIAS_KEYS = {canonical: tuple(column_key(alias) for alias in aliases) for canonical, aliases in ALIASES.items()}


@lru_cache(maxsize=128)
def _mapping_for_columns(columns: tuple[str, ...]) -> tuple[tuple[str, str], ...]:
    lookup = {column_key(c): c for c in columns}
    selected = []
    for canonical, aliases in _ALIAS_KEYS.items():
        for alias in aliases:
            if alias in lookup:
                selected.append((canonical, lookup[alias]))
                break
    return tuple(selected)


_TYPES = {
    "AV": "AVENIDA", "AVDA": "AVENIDA", "AVENIDA": "AVENIDA",
    "JR": "JIRON", "JIRON": "JIRON", "CL": "CALLE", "CAL": "CALLE", "CALLE": "CALLE",
    "PSJE": "PASAJE", "PJE": "PASAJE", "PASAJE": "PASAJE",
    "CAR": "CARRETERA", "CARRETERA": "CARRETERA", "MALECON": "MALECON",
    "PROL": "PROLONGACION", "PROLONGACION": "PROLONGACION",
}
_TYPE_RE = r"(?:AVENIDA|AVDA|AV|JIRON|JR|CALLE|CAL|CL|PASAJE|PSJE|PJE|CARRETERA|CAR|MALECON|PROLONGACION|PROL)\.?\b"
DECISION_WARNINGS = {
    "COORDENADAS_CONTRADICTORIAS", "REFERENCIA_RELATIVA", "MANZANA_LOTE_REQUIERE_REFERENCIA",
    "UBIGEO_INVALIDO", "UBIGEO_CONFLICTIVO_ORIGEN", "PROCEDENCIA_COORDENADA_NO_CONFIRMADA",
    "CRUCE_MISMA_VIA",
    "COMPONENTES_CONTRADICTORIOS",
}


def canonical_street_type(value: Any) -> str:
    value = key(value).strip(". ")
    return _TYPES.get(value, value)


def street_parts(value: Any) -> tuple[str | None, str]:
    value = key(value)
    match = re.match(rf"^({_TYPE_RE})\s*(.*)$", value)
    if match:
        return canonical_street_type(match[1]), match[2].strip(" .,-")
    return None, value.strip(" .,-")


def _axis(value: Any, latitude: bool) -> float | None:
    """Read a decimal or one DMS axis; hemisphere never double-negates a sign."""
    if isinstance(value, (float, int)) and not isinstance(value, bool):
        number = float(value)
        return number if math.isfinite(number) and abs(number) <= (90 if latitude else 180) else None
    value = key(value).replace("−", "-").replace("º", "°")
    if not value:
        return None
    if re.fullmatch(r"[+-]?\d+(?:\.\d+)?E[+-]?\d+", value):
        number = float(value)
        return number if math.isfinite(number) and abs(number) <= (90 if latitude else 180) else None
    match = re.fullmatch(
        r"([+-]?\d+(?:[.,]\d+)?)\s*(?:[°D]\s*(\d+(?:[.,]\d+)?)\s*['′M]"
        r"\s*(?:(\d+(?:[.,]\d+)?)\s*[\"″]?)?)?\s*([NSEOW])?", value
    )
    if not match:
        return None
    degrees = float(match[1].replace(",", "."))
    minutes = float((match[2] or "0").replace(",", "."))
    seconds = float((match[3] or "0").replace(",", "."))
    hemisphere = (match[4] or "").strip()
    if minutes >= 60 or seconds >= 60 or (hemisphere and hemisphere not in ("NS" if latitude else "EWO")):
        return None
    if degrees < 0 and hemisphere in "NE" and hemisphere:
        return None
    number = abs(degrees) + minutes / 60 + seconds / 3600
    if degrees < 0 or hemisphere in ("S", "W", "O"):
        number = -number
    if not math.isfinite(number) or abs(number) > (90 if latitude else 180):
        return None
    return number


def valid_pair(latitude: Any, longitude: Any) -> tuple[float, float] | None:
    lat, lon = _axis(latitude, True), _axis(longitude, False)
    if lat is None or lon is None:
        return None
    return lat, lon


def _coordinates_in_text(value: str) -> tuple[tuple[float, float] | None, str | None]:
    value = key(value).replace("−", "-").replace("º", "°")
    axis = r"(?<![\d.])[+-]?\d{1,3}(?:[.,]\d{1,12})?\s*°\s*\d{1,2}(?:[.,]\d{1,12})?\s*['′]\s*(?:\d{1,2}(?:[.,]\d{1,12})?\s*[\"″]?)?\s*[NS]"
    longitude = axis.replace("[NS]", "[EWO]")
    match = re.search(rf"({axis})\s*[,;/\s]*({longitude})", value)
    if match:
        return valid_pair(match[1], match[2]), match[0]
    match = re.search(
        r"LAT(?:ITUD|ITUDE)?\s*[:=]?\s*([+-]?\d+(?:[.,]\d+)?\s*[NS]?)"
        r"\s*[,; /]*\s*(?:LON(?:GITUD|GITUDE)?|LONG|LNG)\s*[:=]?\s*([+-]?\d+(?:[.,]\d+)?\s*[EWO]?)", value
    )
    if match:
        return valid_pair(match[1], match[2]), match[0]
    # Unlabelled decimal pairs require decimal points on both axes and clear separators.
    match = re.search(r"(?<![\d.])([+-]?\d{1,2}\.\d+\s*[NS]?)\s*[,; /]\s*([+-]?\d{1,3}\.\d+\s*[EWO]?)(?![\d.])", value)
    if match:
        return valid_pair(match[1], match[2]), match[0]
    return None, None


def normalize_record(raw: dict, mapping: dict | None = None) -> dict:
    selected = suggest_mapping(list(raw))
    if mapping is not None:
        selected.update(mapping)
    values = {name: raw.get(source) for name, source in selected.items() if source}
    original_value = values.get("location_original")
    original = "" if original_value is None else str(original_value)
    normalized = re.sub(r"\s+", " ", original.upper()).strip()
    changes, warnings = [], []
    if original != normalized:
        changes.append({"rule": "MAYUSCULAS_ESPACIOS", "before": original, "after": normalized})
    search = key(normalized)
    if search != normalized:
        changes.append({"rule": "CLAVE_SIN_DIACRITICOS", "before": normalized, "after": search})
    result = {name: None for name in ALIASES}
    result.update({"complaint_id": text(values.get("complaint_id")) or None,
                   "location_original": original, "location_normalized": normalized,
                   "transformations": changes, "warnings": warnings, "rules_version": RULES_VERSION,
                   "legacy": {}, "extraction_evidence": []})
    for name in ("district", "street_type", "street_name", "door_number", "block_number", "cross_street", "site_name", "urban_core"):
        result[name] = key(values.get(name)) or None
    if result["street_type"]:
        declared_type = canonical_street_type(result["street_type"])
        if declared_type not in _TYPES.values():
            result["legacy"]["street_type_original"] = values.get("street_type")
            warnings.append("TIPO_VIA_ESTRUCTURADO_NO_RECONOCIDO")
            result["street_type"] = None
        else:
            result["street_type"] = declared_type
    for component in ("door_number", "block_number"):
        candidate = result[component]
        no_number_door = component == "door_number" and candidate in {"S/N", "SN", "SIN NUMERO"}
        if candidate and not re.fullmatch(r"\d+(?:\s*[-/]?\s*[A-Z])?", candidate) and not no_number_door:
            result["legacy"][component + "_original"] = values.get(component)
            warnings.append("PUERTA_ESTRUCTURADA_INVALIDA" if component == "door_number" else "CUADRA_ESTRUCTURADA_INVALIDA")
            result[component] = None
    ubigeo = text(values.get("ubigeo"))
    if re.fullmatch(r"\d{1,5}", ubigeo):
        changes.append({"rule": "UBIGEO_SEIS_POSICIONES_CANDIDATO", "before": ubigeo, "after": ubigeo.zfill(6)})
        warnings.append("UBIGEO_REQUIERE_VALIDACION_CATALOGO")
        ubigeo = ubigeo.zfill(6)
    if ubigeo and not re.fullmatch(r"\d{6}", ubigeo):
        warnings.append("UBIGEO_INVALIDO")
        result["legacy"]["ubigeo_original"] = ubigeo
        ubigeo = ""
    result["ubigeo"] = ubigeo or None
    if not ubigeo:
        warnings.append("TERRITORIO_NO_CONFIRMADO")
    result["crs"] = text(values.get("crs")) or None
    if result["crs"] in ("4326", "WGS84", "WGS 84"):
        result["crs"] = "EPSG:4326"
    for name, value in raw.items():
        canonical = column_key(name)
        if canonical in {"LATHECHO", "LONGHECHO", "ESTADO", "ESTADOCOORD", "OBSERVACION", "FLAGGEOREF", "FLAGCALIDAD", "NIVELCRUCE"}:
            result["legacy"][name] = value
    legacy_text = " ".join(key(v) for k, v in result["legacy"].items() if column_key(k) in {"ESTADOCOORD", "OBSERVACION", "ESTADO"})
    origin = key(values.get("coordinate_origin"))
    flag = next((text(v) for k, v in result["legacy"].items() if column_key(k) == "FLAGGEOREF"), "")
    if flag == "2":
        warnings.append("UBIGEO_CONFLICTIVO_ORIGEN")
    forced = bool(re.search(r"CENTROID|FORZAD|SUSTITUT", legacy_text + " " + origin)) or flag == "3"
    coordinate = valid_pair(values.get("latitude"), values.get("longitude"))
    if forced:
        result["coordinate_origin"] = "SUSTITUTO_HEREDADO"
        warnings.append("COORDENADA_SUSTITUTA")
        if coordinate:
            result["legacy"]["coordenada_sustituta"] = {"latitude": coordinate[0], "longitude": coordinate[1]}
        coordinate = None
    elif coordinate:
        result["latitude"], result["longitude"] = coordinate
        result["coordinate_origin"] = "PNP_ORIGINAL"
        if origin and origin not in {"PNP_ORIGINAL", "ORIGINAL", "COORD_ORIGINAL"}:
            warnings.append("PROCEDENCIA_COORDENADA_NO_CONFIRMADA")
    elif text(values.get("latitude")) or text(values.get("longitude")):
        warnings.append("COORDENADAS_ESTRUCTURADAS_INVALIDAS")
    textual, fragment = _coordinates_in_text(search)
    if fragment:
        result["extraction_evidence"].append({"component": "coordinates", "fragment": fragment})
        if textual:
            if coordinate and (abs(coordinate[0] - textual[0]) > 1e-6 or abs(coordinate[1] - textual[1]) > 1e-6):
                warnings.append("COORDENADAS_CONTRADICTORIAS")
                result["text_coordinates"] = {"latitude": textual[0], "longitude": textual[1]}
            elif not coordinate:
                result["latitude"], result["longitude"] = textual
                result["coordinate_origin"] = "TEXTO_SIDPOL"
        else:
            warnings.append("COORDENADAS_TEXTO_INVALIDAS")
        other_pair, other_fragment = _coordinates_in_text(search.replace(fragment, " ", 1))
        if other_pair and other_pair != textual:
            warnings.append("COORDENADAS_CONTRADICTORIAS")
            result["text_coordinates"] = {"latitude": other_pair[0], "longitude": other_pair[1]}
            result["extraction_evidence"].append({"component": "coordinates", "fragment": other_fragment})
    if result["latitude"] is None and any(column_key(k) == "LATHECHO" for k in result["legacy"]):
        warnings.append("COORDENADA_FINAL_LEGADA_NO_ORIGINAL")
    if re.search(r"\b(?:FRENTE|FRONTIS|ALTURA|CERCA|ESPALDA|COSTADO|REFERENCIA)\b", search):
        warnings.append("REFERENCIA_RELATIVA")
    if re.search(r"\b(?:MZ|MANZANA|LOTE|LT)\b", search):
        warnings.append("MANZANA_LOTE_REQUIERE_REFERENCIA")

    address = search
    if fragment:
        address = address.replace(fragment, " ").strip(" ,;()")
    district = result["district"]
    if district:
        administrative_suffix = re.search(rf"(?:\s+(?:DISTRITO\s+DE\s+)?|\s*[-,]\s*){re.escape(district)}\s*$", address)
        if administrative_suffix:
            address = address[:administrative_suffix.start()].rstrip(" ,;-")
            changes.append({"rule": "SEPARAR_DISTRITO_DECLARADO", "before": search, "after": address})
    typed_street = re.search(rf"\b{_TYPE_RE}\s+", address)
    if typed_street:
        address = address[typed_street.start():]
    address = re.split(r"\s+(?:TOMANDO\s+COMO\s+REFERENCIA|COMO\s+REFERENCIA|REFERENCIA|AL\s+FRENTE)\b", address, maxsplit=1)[0]
    block = re.search(r"\b(?:CUADRA|CDRA|CDR)\.?\s*:?\s*(?:N[°ºO.]?\s*)?(\d+[A-Z]?)\b", address)
    if block:
        result["block_number"] = result["block_number"] or block[1]
        result["extraction_evidence"].append({"component": "block_number", "fragment": block[0]})
        address = address[:block.start()] + " " + address[block.end():]
    no_number = re.search(r"\bS\s*/\s*N\b|\bSIN NUMERO\b", address)
    if no_number or result["door_number"] in {"S/N", "SN", "SIN NUMERO"}:
        if no_number and result["door_number"] and result["door_number"] not in {"S/N", "SN", "SIN NUMERO"}:
            warnings.append("COMPONENTES_CONTRADICTORIOS")
        result["door_number"] = None
        warnings.append("PUERTA_SIN_NUMERO")
        address = re.sub(r"\bS\s*/\s*N\b|\bSIN NUMERO\b", "", address).strip()
    else:
        door = re.search(r"\s+(?:N(?:RO|UMERO|UM)?[°ºO.]?\.?\s*|#\s*)(\d+(?:[-/]?[A-Z])?)\b", address)
        if not door:
            door = re.search(r"\s+(\d+(?:[-/]?[A-Z])?)\s*(?=,|$)", address)
        address_without_door = address[:door.start()].strip() if door else ""
        _, name_without_door = street_parts(address_without_door)
        if door and name_without_door and not result["block_number"] and not re.search(r"\b(?:MZ|MANZANA|LOTE|LT|KM)\b", address):
            extracted_door = re.sub(r"\s+", "", door[1])
            if result["door_number"] and re.sub(r"\s+", "", result["door_number"]) != extracted_door:
                warnings.append("COMPONENTES_CONTRADICTORIOS")
            result["door_number"] = result["door_number"] or extracted_door
            result["extraction_evidence"].append({"component": "door_number", "fragment": door[0].strip()})
            # Text after a declared door belongs to context, not the street name.
            address = address[:door.start()]
    address = re.sub(r"^(?:INTERSECCION|CRUCE)\s+(?:DE\s+)?", "", address)
    split = re.split(rf"\s+(?:CON|ESQ(?:UINA)?\.?(?:\s+CON)?|INTERSECCION(?:\s+CON)?)\s+|\s+[&/]\s+|\s+Y\s+(?={_TYPE_RE})", address, maxsplit=1)
    text_type, text_street = street_parts(split[0])
    if text_type and result["street_type"] and text_type != result["street_type"]:
        warnings.append("COMPONENTES_CONTRADICTORIOS")
    if text_type and result["street_name"] and text_street != street_parts(result["street_name"])[1]:
        warnings.append("COMPONENTES_CONTRADICTORIOS")
    if len(split) == 2:
        first_type, first_street = street_parts(split[0])
        _, second_street = street_parts(split[1])
        if first_street and second_street:
            result["street_type"] = result["street_type"] or first_type
            result["street_name"] = result["street_name"] or first_street
            result["cross_street"] = result["cross_street"] or second_street
    if result["street_name"]:
        extracted_type, result["street_name"] = street_parts(result["street_name"])
        result["street_type"] = result["street_type"] or extracted_type
    elif len(split) == 1:
        extracted_type, extracted_street = street_parts(address)
        if extracted_type or result["door_number"]:
            result["street_type"], result["street_name"] = extracted_type, extracted_street
    if result["street_type"]:
        result["street_type"] = canonical_street_type(result["street_type"])
    if result["cross_street"]:
        _, result["cross_street"] = street_parts(result["cross_street"])
        if result["cross_street"] == result["street_name"]:
            warnings.append("CRUCE_MISMA_VIA")
    if not result["site_name"]:
        site = re.search(r"\b(?:CENTRO COMERCIAL|MERCADO|HOSPITAL|COLEGIO|ESTADIO|PARQUE|PLAYA|AEROPUERTO|TERMINAL)\s+.+", search)
        if site:
            result["site_name"] = site[0].strip(" .,")
    if not result["urban_core"]:
        nucleus = re.search(r"\b(?:CENTRO POBLADO|CASERIO|AA\.?\s*HH\.?|ASENTAMIENTO HUMANO|URBANIZACION|URB\.?)\s+(.+)", search)
        if nucleus:
            result["urban_core"] = nucleus[1].strip(" .,")
    result["search_names"] = list(dict.fromkeys(result[n] for n in ("street_name", "cross_street", "site_name", "urban_core") if result[n]))
    result["decision_constraints"] = sorted(set(warnings) & DECISION_WARNINGS)
    return result
