"""Advance only pending locations; resolved results remain unchanged."""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Job, Run, User
from ..quality_workflow import quality_summary
from ..schemas import Input
from ..security import current_user
from ..serialization import audit, run_dict
from .common import operator, require

router = APIRouter()


class AdvanceInput(Input):
    stage: Literal["block", "intersection", "street", "nucleus", "jurisdiction"]


@router.get("/api/runs/{identifier}/quality")
def quality(identifier: str, db: Session = Depends(get_db), _: User = Depends(current_user)):
    return quality_summary(db, require(db, Run, identifier))


@router.post("/api/runs/{identifier}/advance")
def advance(
    identifier: str, payload: AdvanceInput, db: Session = Depends(get_db), user: User = Depends(operator)
):
    db.execute(update(Run).where(Run.id == identifier).values(id=Run.id))
    run = require(db, Run, identifier)
    db.refresh(run)
    summary = quality_summary(db, run)
    if not summary["can_advance"] or summary["next_stage"] != payload.stage:
        raise HTTPException(
            409, "Esta etapa no tiene pendientes elegibles o existe otro procesamiento en curso"
        )
    if db.scalar(
        select(Job.id).where(Job.target_id == identifier, Job.status.in_(("QUEUED", "RUNNING"))).limit(1)
    ):
        raise HTTPException(409, "Ya existe un trabajo en curso")
    run.config = {**run.config, "quality_target_stage": payload.stage}
    run.status, run.error, run.cancel_requested = "QUEUED", None, False
    db.add(Job(kind="RUN", target_id=run.id))
    audit(
        db,
        user.username,
        "quality.advance",
        run.id,
        {"stage": payload.stage, "eligible_units": summary["eligible_units"]},
    )
    db.commit()
    return run_dict(db, run)
