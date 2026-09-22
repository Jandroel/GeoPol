"""Map the supplied door dictionary without assigning a CRS or accepting a point.

The dictionary describes fields, not category domains or source provenance. Numeric
category codes therefore require a caller-supplied mapping. An explicit street type
inside NOMVIA may be read as text, but never confirms an unknown CATVIA code.
Only the engine's supported street types are eligible in this version; for example,
CAMINO and generic OTROS require an explicit implementation before activation.
MANZANA (reference identifier) and P21 (address manzana) remain separate. The
inconsistent descriptions of the *_R group do not establish its meaning or priority.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from copy import deepcopy
from decimal import Decimal
from typing import Any

from .normalization import canonical_street_type, key, street_parts

_MISSING = {
    "",
    "NULL",
    "(NULL)",
    "<NULL>",
    "NONE",
    "NAN",
    "<NA>",
    "NA",
    "N/A",
    "S/D",
    "SIN DATO",
    "SIN DATOS",
    "NO DISPONIBLE",
}
_NO_NUMBER = {"SN", "S/N", "S N", "SIN NUMERO", "SIN NOMBRE", "S/NOMBRE"}
_RELATIVE = re.compile(r"\b(?:FRENTE|FRONTIS|ALTURA|CERCA|ESPALDA|COSTADO|REFERENCIA)\b")
_SUPPORTED_STREET_TYPES = {
    "AVENIDA",
    "CALLE",
    "JIRON",
    "PASAJE",
    "CARRETERA",
    "MALECON",
    "PROLONGACION",
}


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, (int, float, Decimal)) and not isinstance(value, bool):
        number = Decimal(str(value))
        if not number.is_finite():
            return None
        if number == number.to_integral_value():
            value = str(int(number))
    result = key(value)
    marker = re.sub(r"\s*([/<>()[\]])\s*", r"\1", result)
    return None if marker in _MISSING else result


def _identifier(value: Any, width: int) -> str | None:
    if isinstance(value, bool):
        return None
    cleaned = _clean(value)
    if cleaned is None:
        return None
    # An integral spreadsheet value can have lost leading zeros. Never truncate.
    if not re.fullmatch(r"[0-9]+(?:\.0+)?", cleaned):
        return None
    digits = cleaned.split(".", 1)[0]
    return digits.zfill(width) if len(digits) <= width else None


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    cleaned = _clean(value)
    if cleaned is None or not re.fullmatch(r"[+-]?[0-9]+(?:[.,][0-9]+)?(?:E[+-]?[0-9]+)?", cleaned):
        return None
    number = float(cleaned.replace(",", "."))
    return number if math.isfinite(number) else None


def map_door_record(
    raw: Mapping[str, Any],
    ordinal: int,
    street_types: Mapping[Any, str] | None = None,
) -> dict:
    """Return staging data and structural eligibility, never a geographic decision.

    ``address_ready`` means the urban street/number representation is unambiguous
    and its coordinate values fit latitude/longitude ranges. It does not establish
    a datum, source version, district containment or permission to activate it.
    Unknown category codes and alternate address components prevent eligibility.
    Issues contain field names and fixed descriptions, never source cell values.
    """
    if isinstance(ordinal, bool) or not isinstance(ordinal, int) or ordinal < 1:
        raise ValueError("source ordinal must be a positive integer")

    values = {key(field): value for field, value in raw.items()}
    issues: list[dict[str, str]] = []

    def issue(code: str, field: str, message: str) -> None:
        issues.append({"code": code, "field": field, "message": message})

    normalized = {
        "ubigeo": _identifier(values.get("UBIGEO"), 6),
        "center_code": _identifier(values.get("CODCCPP"), 4),
        "department": _clean(values.get("NOMBDEP")),
        "province": _clean(values.get("NOMBPROV")),
        "district": _clean(values.get("NOMBDIST")),
        "center_name": _clean(values.get("NOMBCCPP")),
        "area": _clean(values.get("AREA")),
        "urban_core": _clean(values.get("NUCLEO")),
        "reference_manzana_code": _clean(values.get("MANZANA")),
        "manzana_code": _clean(values.get("P21")),
        "lot_number": _clean(values.get("P22")),
        "kilometer": _clean(values.get("P23_K")),
        "street_type_code": _clean(values.get("CATVIA")),
        "street_type_other": _clean(values.get("CATVIA_O")),
        "street_type": None,
        "street_name": None,
        "door_number_base": _clean(values.get("P17")),
        "door_letter": _clean(values.get("P17_A")),
        "door_number": None,
        "latitude": _number(values.get("P13_1")),
        "longitude": _number(values.get("P13_2")),
        "coordinates_valid": False,
        "reference": _clean(values.get("REFERENCIA")),
        "address_alternative_r": {
            field: _clean(values.get(field))
            for field in ("CATEGORIA_VIA_R", "CATEGORIA_VIA_O_R", "NOM_VIA_R")
        },
        "residential_address": {
            field: _clean(values.get(field)) for field in ("CATVIA_RES", "CATVIA_RES_O", "NOMVIA_RES")
        },
    }
    if not normalized["ubigeo"]:
        issue("UBIGEO_MISSING_OR_INVALID", "UBIGEO", "Se requiere un código distrital de seis dígitos.")
    if _clean(values.get("CODCCPP")) and not normalized["center_code"]:
        issue("CENTER_CODE_INVALID", "CODCCPP", "El código de centro poblado no admite ancho cuatro.")
    if normalized["area"] not in {None, "1", "2"}:
        issue("AREA_DOMAIN_INVALID", "AREA", "El diccionario solo declara 1 urbano y 2 rural.")
    elif normalized["area"] == "2":
        issue("RURAL_CONTEXT_REQUIRES_MAPPING", "AREA", "La dirección rural requiere un mapeo específico.")

    name = _clean(values.get("NOMVIA"))
    explicit_type, street_name = street_parts(name) if name else (None, "")
    if not street_name or street_name in _NO_NUMBER:
        issue("STREET_NAME_MISSING", "NOMVIA", "No se identifica una vía con nombre.")
    else:
        normalized["street_name"] = street_name
    normalized["street_type"] = explicit_type
    category = normalized["street_type_code"]
    mapped_categories = {_clean(code): value for code, value in (street_types or {}).items()}
    mapped_type = None
    if category:
        if category not in mapped_categories:
            issue("CAT_VIA_DOMAIN_UNCONFIRMED", "CATVIA", "Falta el dominio confirmado de categorías de vía.")
        else:
            supplied = _clean(mapped_categories[category])
            mapped_type = canonical_street_type(supplied) if supplied else None
            if mapped_type not in _SUPPORTED_STREET_TYPES:
                issue(
                    "STREET_TYPE_MAPPING_INVALID",
                    "CATVIA",
                    "El mapeo debe aportar un tipo de vía soportado y no ambiguo.",
                )
            else:
                if explicit_type and mapped_type != explicit_type:
                    issue(
                        "STREET_TYPE_CONFLICT",
                        "CATVIA,NOMVIA",
                        "El tipo mapeado contradice el nombre de vía.",
                    )
                else:
                    normalized["street_type"] = mapped_type
    if normalized["street_type_other"]:
        # CATVIA_O must not silently override CATVIA, even when a code map exists.
        issue(
            "OTHER_STREET_TYPE_REQUIRES_MAPPING",
            "CATVIA_O",
            "La otra categoría requiere interpretación explícita.",
        )

    base, letter = normalized["door_number_base"], normalized["door_letter"]
    if base in _NO_NUMBER:
        issue("DOOR_NUMBER_ABSENT", "P17", "La puerta está declarada sin número.")
    elif base:
        match = re.fullmatch(r"([0-9]+)(?:\s*[-/]?\s*([A-Z]+))?", base)
        if not match:
            issue("DOOR_NUMBER_INVALID", "P17", "El campo no contiene un número de puerta simple.")
        elif letter and not re.fullmatch(r"[A-Z]+", letter):
            issue("DOOR_LETTER_INVALID", "P17_A", "El sufijo de puerta no contiene únicamente letras.")
        elif match[2] and letter and match[2] != letter:
            issue(
                "DOOR_LETTER_CONFLICT",
                "P17,P17_A",
                "La letra incluida en el número contradice el campo de letra.",
            )
        else:
            normalized["door_number"] = match[1] + (match[2] or letter or "")
    else:
        issue("DOOR_NUMBER_MISSING", "P17", "No se dispone de un número de puerta.")
    if letter and (not base or base in _NO_NUMBER):
        issue("DOOR_LETTER_WITHOUT_NUMBER", "P17_A", "La letra no identifica una puerta sin su número.")

    lat, lon = normalized["latitude"], normalized["longitude"]
    normalized["coordinates_valid"] = (
        lat is not None and lon is not None and abs(lat) <= 90 and abs(lon) <= 180
    )
    for source_field, number, limit in (("P13_1", lat, 90), ("P13_2", lon, 180)):
        if number is None:
            issue("COORDINATE_MISSING_OR_INVALID", source_field, "Se requiere un valor numérico finito.")
        elif abs(number) > limit:
            issue("COORDINATE_OUT_OF_RANGE", source_field, "El valor excede el rango del eje declarado.")

    if normalized["manzana_code"] or normalized["lot_number"]:
        issue(
            "MANZANA_LOT_CONTEXT_REQUIRES_MAPPING",
            "P21,P22",
            "La manzana o lote requiere contexto de dirección.",
        )
    if normalized["kilometer"]:
        issue(
            "KILOMETER_CONTEXT_REQUIRES_MAPPING",
            "P23_K",
            "El kilómetro requiere una referencia de recorrido.",
        )
    if any(normalized["address_alternative_r"].values()):
        issue(
            "ALTERNATIVE_R_REQUIRES_MAPPING",
            "NOM_VIA_R",
            "El grupo R requiere aclarar su significado y relación.",
        )
    if any(normalized["residential_address"].values()):
        issue(
            "RESIDENTIAL_ADDRESS_REQUIRES_MAPPING",
            "NOMVIA_RES",
            "La vía residencial requiere aclarar su relación.",
        )
    if _RELATIVE.search(" ".join(filter(None, (name, normalized["reference"])))):
        issue(
            "RELATIVE_ADDRESS_REQUIRES_MAPPING",
            "NOMVIA,REFERENCIA",
            "La referencia relativa requiere interpretación.",
        )

    return {
        "source_ordinal": ordinal,
        "raw": deepcopy(dict(raw)),
        "normalized": normalized,
        "issues": issues,
        "address_ready": bool(
            normalized["ubigeo"]
            and normalized["street_name"]
            and normalized["door_number"]
            and normalized["coordinates_valid"]
            and not issues
        ),
    }
