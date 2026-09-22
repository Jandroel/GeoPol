"""Preview and atomically apply an explicit decision to equivalent locations."""

import hmac
import time
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field
from sqlalchemy import or_, select, update
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from ..domain.coordinate_context import documented_crs
from ..db import get_db
from ..domain.equivalent_review import GROUP_LIMIT, eligibility_reason, equivalence_key, fingerprint
from ..models import Location, Run, User
from ..schemas import DecisionInput, Input
from ..serialization import audit
from .common import require, reviewer
from .review import apply_decision, editable_run

router = APIRouter()


class GroupDecisionInput(Input):
    token: str = Field(pattern=r"^[a-f0-9]{64}$")
    candidate_id: str = Field(min_length=1, max_length=500)
    reason: str = Field(min_length=8, max_length=3000)


def state(item):
    return {
        field: getattr(item, field)
        for field in (
            "id",
            "run_id",
            "complaint_id",
            "location_normalized",
            "ubigeo",
            "normalized",
            "source_row_count",
            "candidates",
            "attempts",
            "revision",
            "resolution",
            "manual",
            "review_status",
            "review_bucket",
            "review_owner",
            "review_expires_at",
            "reason",
        )
    }


def assemble_preview(db, item, run, user, *, lock=False):
    now = time.time()
    base = state(item)
    reason = eligibility_reason(base, user.id, now)
    # Legacy runs assigned EPSG:4326 by default. Neither that run setting nor a
    # normalized axis pair constitutes a documented coordinate declaration.
    if any((base.get("normalized") or {}).get(axis) is not None for axis in ("latitude", "longitude")):
        if not documented_crs(run.config):
            reason = "El lote requiere documentar el sistema de coordenadas de origen y reprocesarse."
    response = {
        "base_id": item.id,
        "run_id": run.id,
        "eligible": False,
        "reason": reason,
        "token": None,
        "members": [],
        "count": 0,
        "source_rows": 0,
        "limit": GROUP_LIMIT,
        "truncated": False,
        "excluded_count": 0,
        "candidates": [],
    }
    if reason:
        return response, []
    query = (
        select(Location)
        .where(
            Location.run_id == run.id,
            Location.location_normalized == item.location_normalized,
            Location.ubigeo == item.ubigeo,
        )
        .order_by(Location.id)
    )
    if lock:
        query = query.with_for_update()
    matched, all_states = [], []
    signature = equivalence_key(base)
    total, source_rows, excluded = 0, 0, 0
    for other in db.scalars(query.execution_options(populate_existing=True, yield_per=500)):
        snapshot = state(other)
        if eligibility_reason(snapshot, user.id, now) or equivalence_key(snapshot) != signature:
            excluded += 1
            continue
        total += 1
        source_rows += other.source_row_count
        if len(matched) < GROUP_LIMIT or other.id == item.id:
            matched.append(other)
            all_states.append(snapshot)
    # Always display the base first, even if it sorts beyond the visible cap.
    matched.sort(key=lambda value: (value.id != item.id, value.id))
    visible = matched[:GROUP_LIMIT]
    truncated = total > GROUP_LIMIT
    response.update(
        count=total,
        source_rows=source_rows,
        excluded_count=excluded,
        truncated=truncated,
        members=[
            {
                field: getattr(member, field)
                for field in (
                    "id",
                    "complaint_id",
                    "location_normalized",
                    "ubigeo",
                    "revision",
                    "source_row_count",
                )
            }
            for member in visible
        ],
        candidates=[
            {
                field: candidate.get(field)
                for field in ("id", "label", "precision", "product", "method", "source", "version")
            }
            for candidate in item.candidates
        ],
    )
    if total < 2:
        response["reason"] = "No hay otras ubicaciones abiertas con exactamente la misma evidencia."
    elif truncated:
        response["reason"] = (
            f"El grupo contiene {total} ubicaciones y supera el límite de {GROUP_LIMIT}. "
            "No se aplicará una decisión parcial; continúe por revisión individual."
        )
    else:
        response["eligible"] = True
        # User, run configuration, candidate evidence, revisions and reservations
        # all participate. Claim/release changes invalidate a preview as well.
        response["token"] = fingerprint(
            {
                "policy": "equivalent-review-v1",
                "user_id": user.id,
                "base_id": item.id,
                "run": {
                    "id": run.id,
                    "status": run.status,
                    "superseded_by": run.superseded_by,
                    "reference_id": run.reference_id,
                    "rules_version": run.rules_version,
                    "config": run.config,
                },
                "members": sorted(all_states, key=lambda value: value["id"]),
            }
        )
    return response, visible


@router.get("/api/results/{identifier}/review-group/preview")
def preview_group(identifier: str, db: Session = Depends(get_db), user: User = Depends(reviewer)):
    item = require(db, Location, identifier)
    run = editable_run(db, item)
    preview, _ = assemble_preview(db, item, run, user)
    return preview


@router.post("/api/results/{identifier}/review-group/decide")
def decide_group(
    identifier: str,
    payload: GroupDecisionInput,
    db: Session = Depends(get_db),
    user: User = Depends(reviewer),
):
    try:
        item = require(db, Location, identifier)
        # A no-op update obtains the SQLite writer lock, and locks the run row on
        # PostgreSQL before reading decision evidence. It also serializes against
        # reprocessing supersession. No source data are updated.
        db.execute(update(Run).where(Run.id == item.run_id).values(status=Run.status))
        db.expire_all()
        item = require(db, Location, identifier)
        run = editable_run(db, item)
        preview, members = assemble_preview(db, item, run, user, lock=True)
        if not preview["eligible"] or not hmac.compare_digest(payload.token, preview["token"] or ""):
            raise HTTPException(
                409, "El grupo o su evidencia cambió. Actualice la vista previa antes de decidir."
            )
        if payload.candidate_id not in {str(candidate["id"]) for candidate in item.candidates}:
            raise HTTPException(422, "El candidato seleccionado no pertenece a la vista previa del grupo")
        now = time.time()
        # All leases must be acquired before the first revision. Existing own
        # leases are renewed; foreign leases are never overridden, even by admin.
        for member in members:
            changed = db.execute(
                update(Location)
                .where(
                    Location.id == member.id,
                    Location.revision == member.revision,
                    Location.review_status == "OPEN",
                    Location.manual.is_(False),
                    or_(
                        Location.review_owner.is_(None),
                        Location.review_owner == user.id,
                        Location.review_expires_at < now,
                    ),
                )
                .values(review_owner=user.id, review_expires_at=now + 600)
            ).rowcount
            if changed != 1:
                raise HTTPException(409, "Una ubicación cambió o fue reservada. Actualice la vista previa.")
        group_id = str(uuid.uuid4())
        updated = None
        location_ids = []
        for member in members:
            result = apply_decision(
                db,
                member,
                DecisionInput(
                    expected_revision=member.revision,
                    action="accept_candidate",
                    candidate_id=payload.candidate_id,
                    reason=payload.reason,
                ),
                user,
                group_id=group_id,
            )
            location_ids.append(member.id)
            if member.id == identifier:
                updated = result
        audit(
            db,
            user.username,
            "review.group_decision",
            group_id,
            {
                "base_id": identifier,
                "run_id": run.id,
                "location_ids": location_ids,
                "count": len(location_ids),
                "candidate_id": payload.candidate_id,
                "reason": payload.reason,
                "preview_token": payload.token,
            },
        )
        db.commit()
        return {
            "group_id": group_id,
            "applied_count": len(location_ids),
            "location_ids": location_ids,
            "item": updated,
        }
    except OperationalError as exc:
        db.rollback()
        raise HTTPException(
            409, "La revisión está siendo modificada. Actualice la vista previa e intente nuevamente."
        ) from exc
    except Exception:
        db.rollback()
        raise
