"""HTTP endpoints for review."""

import math
import time

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import (
    Location,
    Revision,
    Run,
    User,
)
from ..schemas import DecisionInput
from ..security import current_user
from ..serialization import add_revision, audit, iso, location_dict
from .common import FINISHED, REVIEW_STATUSES, filtered_locations, page_result, require, reviewer

router = APIRouter()


@router.get("/api/review")
def review(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    q: str = Query("", max_length=100),
    db: Session = Depends(get_db),
    _: User = Depends(current_user),
):
    query = (
        select(Location)
        .join(Run, Location.run_id == Run.id)
        .where(Location.resolution.in_(REVIEW_STATUSES), Run.status.in_(FINISHED))
    )
    return page_result(db, filtered_locations(query, q), location_dict, page, page_size)


@router.get("/api/results/{identifier}")
def get_result(identifier: str, db: Session = Depends(get_db), _: User = Depends(current_user)):
    item = require(db, Location, identifier)
    result = location_dict(item)
    # Normalized fields exclude person records; legacy contains only prior geocoding evidence.
    result.update(
        normalized=item.normalized,
        transformations=item.normalized.get("transformations", []),
        candidates=item.candidates,
        attempts=item.attempts,
        history=[
            {
                "revision": x.revision,
                "actor": x.actor,
                "created_at": iso(x.created_at),
                "action": x.action,
                "reason": x.reason,
                "snapshot": x.snapshot,
            }
            for x in db.scalars(
                select(Revision).where(Revision.location_id == identifier).order_by(Revision.revision.desc())
            )
        ],
    )
    return result


@router.post("/api/results/{identifier}/claim")
def claim_result(identifier: str, db: Session = Depends(get_db), user: User = Depends(reviewer)):
    item = require(db, Location, identifier)
    if db.get(Run, item.run_id).status not in FINISHED:
        raise HTTPException(409, "Espere a que termine el lote antes de revisarlo")
    now = time.time()
    changed = db.execute(
        update(Location)
        .where(
            Location.id == identifier,
            or_(
                Location.review_owner.is_(None),
                Location.review_owner == user.id,
                Location.review_expires_at < now,
            ),
        )
        .values(review_owner=user.id, review_expires_at=now + 600)
    ).rowcount
    if changed != 1:
        raise HTTPException(409, "Otra persona tiene la revisión asignada")
    audit(db, user.username, "review.claim", identifier)
    db.commit()
    db.refresh(item)
    return location_dict(item)


@router.post("/api/results/{identifier}/decisions")
def decide(
    identifier: str, payload: DecisionInput, db: Session = Depends(get_db), user: User = Depends(reviewer)
):
    item = require(db, Location, identifier)
    if db.get(Run, item.run_id).status not in FINISHED:
        raise HTTPException(409, "El lote todavía no está completo")
    values = dict(
        resolution="ACEPTADO_MANUAL",
        method="MANUAL",
        manual=True,
        latitude=None,
        longitude=None,
        product="NINGUNO",
        precision=payload.precision or "DESCONOCIDA",
        evidence_band="REVISION",
        reason=payload.reason,
        review_owner=None,
        review_expires_at=None,
        revision=payload.expected_revision + 1,
    )
    if payload.action == "accept_candidate":
        candidate = next((x for x in item.candidates if str(x.get("id")) == payload.candidate_id), None)
        if candidate is None:
            raise HTTPException(422, "Candidato no encontrado")
        lat, lon = candidate.get("latitude"), candidate.get("longitude")
        if (
            lat is None
            or lon is None
            or not math.isfinite(lat)
            or not math.isfinite(lon)
            or not -90 <= lat <= 90
            or not -180 <= lon <= 180
        ):
            raise HTTPException(422, "El candidato no contiene un punto válido")
        values.update(
            latitude=lat,
            longitude=lon,
            product="PUNTO",
            precision=candidate.get("precision", "DESCONOCIDA"),
            method=candidate.get("method") or "MANUAL",
        )
    elif payload.action == "manual_point":
        if (
            payload.latitude is None
            or payload.longitude is None
            or not payload.evidence
            or len(payload.evidence) < 8
        ):
            raise HTTPException(
                422, "Un punto manual requiere latitud, longitud y evidencia (mínimo 8 caracteres)"
            )
        values.update(
            latitude=payload.latitude,
            longitude=payload.longitude,
            product="PUNTO",
            precision=payload.precision or "COORDENADA",
            reason=f"{payload.reason}\nEvidencia: {payload.evidence}",
        )
    elif payload.action == "address_only":
        address = payload.address or item.location_normalized
        if not address:
            raise HTTPException(422, "Indique la dirección normalizada")
        values.update(product="DIRECCION_SIN_PUNTO", location_normalized=address)
    elif payload.action == "unresolved":
        values.update(resolution="SIN_COINCIDENCIA", method=None, evidence_band="SIN_EVIDENCIA")
    elif payload.action == "reopen":
        values.update(resolution="REVISION_REQUERIDA", method=None)
    changed = db.execute(
        update(Location)
        .where(
            Location.id == identifier,
            Location.revision == payload.expected_revision,
            Location.review_owner == user.id,
            Location.review_expires_at > time.time(),
        )
        .values(**values)
    ).rowcount
    if changed != 1:
        raise HTTPException(
            409, "La revisión cambió o su asignación expiró. Recargue y vuelva a tomar el registro"
        )
    db.refresh(item)
    add_revision(db, item, user.username, payload.action)
    audit(
        db,
        user.username,
        "review.decision",
        identifier,
        {"action": payload.action, "revision": item.revision},
    )
    db.commit()
    return location_dict(item)
