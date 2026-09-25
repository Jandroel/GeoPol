"""Read-only, streaming validation of the operational Excel/CSV contract."""

from datetime import datetime
from pathlib import Path
import re

from .ingestion import inspect_file, iter_records
from .normalization import ALIASES, LOCATION_INPUT_FIELDS, source_flag_metadata, suggest_mapping
from .quality import flag10_reason


def validate_upload(path: Path, filename: str, *, sheet=None, mapping=None, delimiter=None, encoding=None):
    profile = inspect_file(path, filename, sheet=sheet)
    columns = profile["columns"]
    supplied = mapping or {}
    if set(supplied) - set(ALIASES):
        raise ValueError("El mapeo contiene campos desconocidos")
    selected = {**suggest_mapping(columns), **supplied}
    totals = {"total_rows": 0, "flag10_existing": 0, "flag10_autoeligible": 0, "issue_rows": 0}
    records = iter_records(
        path,
        filename,
        sheet=sheet,
        delimiter=delimiter or profile["delimiter"],
        encoding=encoding or profile["encoding"],
    )
    try:
        for _, raw, issue in records:
            if not totals["total_rows"]:
                columns = list(raw)
                if any(value and value not in columns for value in supplied.values()):
                    raise ValueError("El mapeo contiene columnas que no existen")
                selected = {**suggest_mapping(columns), **supplied}
            totals["total_rows"] += 1
            totals["issue_rows"] += bool(issue)
            metadata = source_flag_metadata(raw, selected)
            if issue:
                metadata["warnings"] = ["FILA_ORIGEN_CON_INCIDENCIA"]
            reason = flag10_reason(metadata)
            totals["flag10_existing"] += reason == "FLAG_10_DECLARADO_EN_ORIGEN"
            totals["flag10_autoeligible"] += reason == "FLAG_10_SIN_DATOS_DE_UBICACION"
    finally:
        records.close()
    date = None
    match = re.fullmatch(r"DATACRIM_(\d{8})\.xlsx", filename, flags=re.IGNORECASE)
    if match:
        try:
            date = datetime.strptime(match[1], "%d%m%Y").date().isoformat()
        except ValueError:
            pass
    missing = [] if any(selected.get(field) for field in LOCATION_INPUT_FIELDS) else ["Datos de ubicación"]
    flag_present = bool(selected.get("source_quality_flag"))
    warnings = list(profile["warnings"])
    if not date:
        warnings.append(
            "Nombre recomendado: DATACRIM_DDMMYYYY.xlsx, con una fecha válida. Se admite el nombre actual."
        )
    if not flag_present:
        warnings.append(
            "No se detectó una columna FLAG. GeoPol conservará el original y agregará su clasificación al exportar."
        )
    if totals["flag10_autoeligible"]:
        warnings.append(
            "Solo las filas sin ningún dato de ubicación recibirán FLAG 10 automático; se conservarán en los resultados y exportaciones."
        )
    if totals["issue_rows"]:
        warnings.append("Hay filas con incidencias de lectura; no se les asignará FLAG 10 automático.")
    if not totals["total_rows"]:
        warnings.append("El archivo no contiene filas de datos.")
    return {
        "filename": {
            "valid": date is not None,
            "expected": "DATACRIM_DDMMYYYY.xlsx",
            "date": date,
            "message": "Nombre y fecha conformes" if date else "Nombre fuera de la convención recomendada",
        },
        "columns": {
            "detected": columns,
            "required": ["Datos de ubicación"],
            "missing": missing,
            "mapping": selected,
        },
        "flag_column_present": flag_present,
        **totals,
        "warnings": list(dict.fromkeys(warnings)),
        "ready": bool(totals["total_rows"] and not missing),
    }
