"""HTTP endpoints for review."""

import math
import time
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import case, func, or_, select, update
from sqlalchemy.orm import Session

from ..db import get_db
from ..address_memory import remember_address, retire_memory, usable_geometry
from ..models import (
    AddressMemory,
    Location,
    Revision,
    Run,
    User,
)
from ..schemas import DecisionInput, MemoryRevokeInput
from ..domain.normalization import normalize_record
from ..review_workflow import classify_review
from ..security import current_user
from ..serialization import add_revision, audit, iso, location_dict
from .common import FINISHED, filtered_locations, page_result, require, reviewer

router = APIRouter()


@router.post("/api/address-memory/{identifier}/revoke")
def revoke_memory(
    identifier: str, payload: MemoryRevokeInput, db: Session = Depends(get_db), user: User = Depends(reviewer)
):
    item = require(db, AddressMemory, identifier)
    item.active = False
    audit(db, user.username, "address_memory.revoked", identifier, {"reason": payload.reason})
    db.commit()
    return {"id": item.id, "active": False}


BucketFilter = Literal["all", "actionable", "needs_reference", "needs_data", "technical"]
StageFilter = Literal["open", "closed", "all"]


def review_scope(db, run_id, q, include_superseded):
    if run_id:
        require(db, Run, run_id)
    query = select(Location).join(Run, Location.run_id == Run.id).where(Run.status.in_(FINISHED))
    if run_id:
        query = query.where(Run.id == run_id)
    if not include_superseded:
        query = query.where(Run.superseded_by.is_(None))
    return filtered_locations(query, q)


def review_filters(query, stage, bucket):
    if stage != "all":
        query = query.where(Location.review_status == stage.upper())
    if bucket != "all":
        query = query.where(Location.review_bucket == bucket)
    return query.order_by(None).order_by(
        case(
            (Location.review_bucket == "actionable", 0),
            (Location.review_bucket == "needs_data", 1),
            (Location.review_bucket == "needs_reference", 2),
            else_=3,
        ),
        Location.id,
    )


def editable_run(db, item):
    run = db.get(Run, item.run_id)
    if run.status not in FINISHED:
        raise HTTPException(409, "Espere a que termine el lote antes de revisarlo")
    if run.superseded_by:
        raise HTTPException(409, "Esta ejecución tiene una versión más reciente; revise la versión vigente")
    return run


@router.get("/api/review")
def review(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    q: str = Query("", max_length=100),
    run_id: str | None = None,
    bucket: BucketFilter = "all",
    stage: StageFilter = "open",
    include_superseded: bool = False,
    db: Session = Depends(get_db),
    _: User = Depends(current_user),
):
    query = review_filters(review_scope(db, run_id, q, include_superseded), stage, bucket)
    return page_result(db, query, location_dict, page, page_size)


@router.get("/api/review/summary")
def review_summary(
    run_id: str | None = None,
    q: str = Query("", max_length=100),
    include_superseded: bool = False,
    db: Session = Depends(get_db),
    _: User = Depends(current_user),
):
    query = review_scope(db, run_id, q, include_superseded)
    counts = db.execute(
        query.with_only_columns(Location.review_status, Location.review_bucket, func.count())
        .order_by(None)
        .group_by(Location.review_status, Location.review_bucket)
    ).all()
    result = {
        "open": {"actionable": 0, "needs_reference": 0, "needs_data": 0, "technical": 0},
        "closed": 0,
        "total": 0,
    }
    for status, bucket, count in counts:
        result["total"] += count
        if status == "CLOSED":
            result["closed"] += count
        elif bucket in result["open"]:
            result["open"][bucket] += count
    return result


@router.get("/api/review/next")
def next_review(
    run_id: str | None = None,
    q: str = Query("", max_length=100),
    bucket: BucketFilter = "all",
    stage: StageFilter = "open",
    exclude_id: str | None = None,
    include_superseded: bool = False,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    if stage == "closed":
        return {"item": None}
    query = review_filters(review_scope(db, run_id, q, include_superseded), "open", bucket)
    # Historical versions remain readable, but never become the next editable case.
    query = query.where(
        Run.superseded_by.is_(None),
        or_(
            Location.review_owner.is_(None),
            Location.review_owner == user.id,
            Location.review_expires_at < time.time(),
        ),
    )
    if exclude_id:
        query = query.where(Location.id != exclude_id)
    item = db.scalar(query.limit(1))
    return {"item": location_dict(item) if item else None}


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
    editable_run(db, item)
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


@router.post("/api/results/{identifier}/release")
def release_result(identifier: str, db: Session = Depends(get_db), user: User = Depends(reviewer)):
    item = require(db, Location, identifier)
    if item.review_owner is None:
        return location_dict(item)
    changed = db.execute(
        update(Location)
        .where(Location.id == identifier, Location.review_owner == user.id)
        .values(review_owner=None, review_expires_at=None)
    ).rowcount
    if changed != 1:
        raise HTTPException(409, "Solo puede liberar su propia asignación")
    audit(db, user.username, "review.release", identifier)
    db.commit()
    db.refresh(item)
    return location_dict(item)


@router.post("/api/results/{identifier}/decisions")
def decide(
    identifier: str, payload: DecisionInput, db: Session = Depends(get_db), user: User = Depends(reviewer)
):
    item = require(db, Location, identifier)
    editable_run(db, item)
    result = apply_decision(db, item, payload, user)
    db.commit()
    return result


def apply_decision(db, item, payload, user, *, group_id=None):
    """Apply one owned revision in the caller's transaction; never commit here.

    Group callers hold the run and location locks and reserve every member before
    invoking this same decision path. Any failure rolls back the entire group.
    """
    identifier = item.id
    if payload.learn_address and payload.action not in {"accept_candidate", "manual_point"}:
        raise HTTPException(422, "Solo una ubicación geográfica confirmada se puede reutilizar")
    values = dict(
        resolution="ACEPTADO_MANUAL",
        method="MANUAL",
        manual=True,
        latitude=None,
        longitude=None,
        geometry=None,
        product="NINGUNO",
        precision=payload.precision or "DESCONOCIDA",
        evidence_band="REVISION",
        reason=payload.reason,
        review_owner=None,
        review_expires_at=None,
        revision=payload.expected_revision + 1,
    )
    candidate = None
    if payload.action == "accept_candidate":
        candidate = next((x for x in item.candidates if str(x.get("id")) == payload.candidate_id), None)
        if candidate is None:
            raise HTTPException(422, "Candidato no encontrado")
        lat, lon = candidate.get("latitude"), candidate.get("longitude")
        area = candidate.get("product") == "AREA_TRAMO"
        if area and not usable_geometry(candidate.get("geometry"), "AREA_TRAMO"):
            raise HTTPException(422, "El candidato de área o tramo no contiene una geometría válida")
        if area and usable_geometry(candidate.get("geometry"), "AREA_TRAMO"):
            values.update(
                geometry=candidate["geometry"],
                product="AREA_TRAMO",
                precision=candidate.get("precision", "DESCONOCIDA"),
                method=candidate.get("method") or "MANUAL",
            )
        elif (
            lat is None
            or lon is None
            or not math.isfinite(lat)
            or not math.isfinite(lon)
            or not -90 <= lat <= 90
            or not -180 <= lon <= 180
        ):
            raise HTTPException(422, "El candidato no contiene un punto válido")
        else:
            values.update(
                latitude=lat,
                longitude=lon,
                product="PUNTO",
                geometry={"type": "Point", "coordinates": [lon, lat]},
                precision=candidate.get("precision", "DESCONOCIDA"),
                method=candidate.get("method") or "MANUAL",
            )
    elif payload.action == "manual_point":
        if payload.precision in {"VIA", "CUADRA", "MANZANA", "NUCLEO"}:
            raise HTTPException(422, "Una precisión de área o tramo requiere la geometría de un candidato")
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
            geometry={"type": "Point", "coordinates": [payload.longitude, payload.latitude]},
            product="PUNTO",
            precision=payload.precision or "COORDENADA",
            reason=f"{payload.reason}\nEvidencia: {payload.evidence}",
        )
    elif payload.action == "address_only":
        address = payload.address or item.location_normalized
        if not address:
            raise HTTPException(422, "Indique la dirección normalizada")
        corrected = normalize_record(
            {"location_original": address, "ubigeo": item.ubigeo, "district": item.normalized.get("district")}
        )
        corrected["legacy"] = item.normalized.get("legacy", {})
        corrected["complaint_id"] = item.complaint_id
        corrected["manual_address_before"] = item.location_normalized
        corrected["warnings"] = sorted(
            set(corrected.get("warnings", []))
            | (
                set(item.normalized.get("warnings", []))
                & {"UBIGEO_CONFLICTIVO_ORIGEN", "FILA_ORIGEN_CON_INCIDENCIA"}
            )
        )
        values.update(
            product="DIRECCION_SIN_PUNTO",
            location_normalized=corrected["location_normalized"],
            normalized=corrected,
            candidates=[],
            attempts=[],
        )
    elif payload.action == "unresolved":
        values.update(resolution="SIN_COINCIDENCIA", method=None, evidence_band="SIN_EVIDENCIA")
    elif payload.action == "reopen":
        values.update(resolution="REVISION_REQUERIDA", method=None)
    values["review_status"], values["review_bucket"] = classify_review(
        resolution=values["resolution"],
        manual=True,
        candidates=item.candidates,
        reason=values["reason"],
        latest_action=payload.action,
    )
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
    retire_memory(db, item.id)
    memory_id = None
    if payload.learn_address:
        try:
            memory_id = remember_address(db, item, user, candidate)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
    if group_id:
        item.normalized = {
            **item.normalized,
            "review_group": {"id": group_id, "candidate_id": payload.candidate_id},
        }
    add_revision(db, item, user.username, payload.action)
    if group_id:
        # The reference is retained in the immutable revision snapshot as well as
        # in the current result, so later individual decisions preserve its origin.
        for revision in db.new:
            if isinstance(revision, Revision) and revision.location_id == item.id:
                revision.snapshot = {**revision.snapshot, "review_group_id": group_id}
    audit(
        db,
        user.username,
        "review.decision",
        identifier,
        {
            "action": payload.action,
            "revision": item.revision,
            "learned_reference_id": memory_id,
            **({"review_group_id": group_id, "candidate_id": payload.candidate_id} if group_id else {}),
        },
    )
    return location_dict(item)
