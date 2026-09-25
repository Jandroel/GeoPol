"""Pure queue classification, independent of the geographic decision and its history."""

from collections.abc import Mapping, Sequence
from typing import Any

MISSING_BOUNDARY = frozenset({"LIMITE_TERRITORIAL_NO_DISPONIBLE", "LIMITE_TERRITORIAL_INVALIDO"})
MISSING_REFERENCE = MISSING_BOUNDARY | {
    "LIMITE_TERRITORIAL_INVALIDO_O_CRS_NO_CONFIRMADO",
    "CRS_NO_CONFIRMADO",
    "CRS_REFERENCIA_NO_CONFIRMADO",
    "PROCEDENCIA_REFERENCIA_INCOMPLETA",
}
ORIGINAL_COORDINATE_METHODS = frozenset({"COORD_ORIGINAL", "COORD_TEXTO"})


def classify_review(
    resolution: str,
    manual: bool,
    candidates: Sequence[Mapping[str, Any]] | None,
    reason: str | None,
    latest_action: str | None = None,
) -> tuple[str, str]:
    """Return queue status/bucket without changing the resolution or manual history.

    A reopened decision is open even if its retained resolution was accepted. Missing
    territorial reference takes priority over other review reasons for an original
    coordinate; those other reasons remain in the original evidence for later review.
    A human 'unresolved' decision closes the task until an explicit reopen.
    """
    if resolution == "EXCLUIDO_FLAG_10":
        return "CLOSED", "none"
    if latest_action != "reopen" and (resolution in {"ACEPTADO_AUTOMATICO", "ACEPTADO_MANUAL"} or manual):
        return "CLOSED", "none"
    if resolution == "ERROR_TECNICO":
        return "OPEN", "technical"
    if resolution == "NO_EVALUABLE_REFERENCIA":
        return "OPEN", "needs_reference"
    items = (
        [candidate for candidate in candidates if isinstance(candidate, Mapping)]
        if isinstance(candidates, Sequence) and not isinstance(candidates, (str, bytes))
        else []
    )
    reason = reason if isinstance(reason, str) else ""
    if "BUSQUEDA_REFERENCIAL_TRUNCADA" in reason:
        return "OPEN", "technical"
    for candidate in items:
        method = candidate.get("method")
        if not isinstance(method, str):
            continue
        raw_evidence = candidate.get("evidence")
        evidence = (
            {value for value in raw_evidence if isinstance(value, str)}
            if isinstance(raw_evidence, (list, tuple))
            else {raw_evidence}
            if isinstance(raw_evidence, str)
            else set()
        )
        if MISSING_REFERENCE.intersection(evidence) or any(code in reason for code in MISSING_REFERENCE):
            return "OPEN", "needs_reference"
    return "OPEN", "actionable" if items else "needs_data"
