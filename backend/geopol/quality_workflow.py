"""Persistent quality progress: geographic rules live in domain.quality."""

import time

from sqlalchemy import func, or_, select

from .domain.quality import (
    POLICY_VERSION,
    STAGES,
    location_quality_flag,
    quality_after_review,
    quality_review_state,
)
from .models import Location
from .schemas import ReviewState
from typing import get_args

QUALITY_FIELDS = (
    "quality_code",
    "quality_stage",
    "quality_status",
    "quality_reason",
    "quality_policy_version",
)
STAGE_KEYS = tuple(stage["key"] for stage in STAGES)
ELIGIBLE = ("unmatched", "blocked")


def stage_scope(run_id, stage):
    query = select(Location).where(Location.run_id == run_id)
    index = STAGE_KEYS.index(stage)
    if index == 0:
        return query.where(Location.resolution == "PENDIENTE")
    return query.where(
        Location.quality_stage == STAGE_KEYS[index - 1],
        Location.quality_status.in_(ELIGIBLE),
        or_(
            Location.resolution.not_in(("ACEPTADO_AUTOMATICO", "ACEPTADO_MANUAL")),
            Location.product.not_in(("PUNTO", "AREA_TRAMO")),
        ),
        or_(Location.review_owner.is_(None), Location.review_expires_at < time.time()),
    )


def record_quality_revision(item, actor, action):
    if action != "automatic_resolution":
        values = {
            key: getattr(item, key)
            for key in QUALITY_FIELDS + ("resolution", "product", "precision", "reason", "candidates")
        }
        updated = quality_after_review(values, values, action=action)
        for key in QUALITY_FIELDS:
            setattr(item, key, updated[key])
    for key, value in location_quality_flag(item.normalized or {}).items():
        setattr(item, key, value)
    item.review_state = quality_review_state(
        {
            **{key: getattr(item, key) for key in QUALITY_FIELDS},
            "resolution": item.resolution,
            "product": item.product,
            "reason": item.reason,
            "candidates": item.candidates,
            "review_bucket": item.review_bucket,
        }
    )
    entry = {key: getattr(item, key) for key in QUALITY_FIELDS}
    entry.update(
        quality_flag=item.quality_flag,
        quality_flag_reason=item.quality_flag_reason,
        review_state=item.review_state,
        stage=item.quality_stage,
        status=item.quality_status,
        revision=item.revision,
        action=action,
        at=time.time(),
    )
    item.quality_history = [*(item.quality_history or []), entry]


def quality_summary(db, run):
    totals = {
        key: 0
        for key in ("units", "source_rows", "resolved", "review", "unmatched", "blocked", "unprocessed")
    }
    stages = {
        stage["key"]: {
            "key": stage["key"],
            "label": stage["label"],
            **{key: 0 for key in ("units", "source_rows", "resolved", "review", "unmatched", "blocked")},
        }
        for stage in STAGES
    }
    labels = {
        1: "Puerta exacta corroborada",
        2: "Puerta · revisión rápida",
        3: "Puerta · revisión detallada",
        4: "Cuadra",
        None: "Sin calidad numérica asignada",
    }
    qualities = {
        code: {"code": code, "label": label, "units": 0, "source_rows": 0} for code, label in labels.items()
    }
    flags = {
        flag: {
            "flag": flag,
            "label": f"Flag {flag}" if flag else "Sin flag asignado",
            **{key: 0 for key in totals},
        }
        for flag in (1, 2, None)
    }
    review_states = {state: {"state": state, "units": 0, "source_rows": 0} for state in get_args(ReviewState)}
    query = (
        select(
            Location.quality_code,
            Location.quality_status,
            Location.source_row_count,
            Location.quality_history,
            Location.quality_flag,
            Location.review_state,
        )
        .where(Location.run_id == run.id)
        .execution_options(yield_per=500)
    )
    for code, status, source_rows, history, flag, review_state in db.execute(query):
        totals["units"] += 1
        totals["source_rows"] += source_rows
        totals[status if status in totals and status not in {"units", "source_rows"} else "unprocessed"] += 1
        group = qualities.get(code, qualities[None])
        group["units"] += 1
        group["source_rows"] += source_rows
        flag_group = flags.get(flag, flags[None])
        flag_group["units"] += 1
        flag_group["source_rows"] += source_rows
        flag_group[status if status in {"resolved", "review", "unmatched", "blocked"} else "unprocessed"] += 1
        state_group = review_states.get(review_state, review_states["unprocessed"])
        state_group["units"] += 1
        state_group["source_rows"] += source_rows
        latest = {entry["stage"]: entry for entry in history or [] if entry.get("stage") in stages}
        for key, entry in latest.items():
            stage = stages[key]
            stage["units"] += 1
            stage["source_rows"] += source_rows
            if entry.get("status") in {"resolved", "review", "unmatched", "blocked"}:
                stage[entry["status"]] += 1
    for stage in stages.values():
        stage["percent_of_total"] = round(stage["units"] / totals["units"] * 100, 2) if totals["units"] else 0
    next_stage, eligible = None, 0
    if run.config.get("workflow") == "quality_v1":
        for stage in STAGE_KEYS[1:]:
            count = db.scalar(select(func.count()).select_from(stage_scope(run.id, stage).subquery()))
            if count:
                next_stage, eligible = stage, count
                break
    return {
        "run_id": run.id,
        "policy_version": POLICY_VERSION,
        "provisional": True,
        "workflow": run.config.get("workflow", "legacy"),
        "totals": totals,
        "qualities": list(qualities.values()),
        "flags": list(flags.values()),
        "review_states": list(review_states.values()),
        "stages": list(stages.values()),
        "next_stage": next_stage,
        "eligible_units": eligible,
        "held_review_units": totals["review"],
        "can_advance": bool(
            next_stage and run.status in {"COMPLETED", "COMPLETED_WITH_ISSUES"} and not run.superseded_by
        ),
    }
