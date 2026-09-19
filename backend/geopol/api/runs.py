"""HTTP endpoints for runs."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..db import get_db
from ..domain.ingestion import inspect_file, iter_records
from ..models import (
    Catalog,
    Job,
    Location,
    Run,
    User,
    uid,
)
from ..schemas import RunInput
from ..security import current_user
from ..serialization import audit, location_dict, run_dict
from ..storage import storage_file
from .common import filtered_locations, operator, owned_upload, page_result, require

router = APIRouter()


def new_run(db, payload, user):
    upload = owned_upload(db, payload.upload_id, user)
    if upload.status != "COMPLETE":
        raise HTTPException(409, "Complete la carga primero")
    if payload.reference_id:
        require(db, Catalog, payload.reference_id)
    if payload.sheet and payload.sheet not in upload.profile.get("sheets", []):
        raise HTTPException(422, "La hoja seleccionada no existe")
    config = payload.model_dump(exclude={"upload_id", "name", "reference_id"})
    if config.get("mapping") and len(config["mapping"]) > 40:
        raise HTTPException(422, "Demasiados campos de mapeo")
    try:
        selected = inspect_file(storage_file("uploads", upload.id), upload.filename, sheet=payload.sheet)
        records = iter_records(
            storage_file("uploads", upload.id),
            upload.filename,
            sheet=payload.sheet,
            delimiter=payload.delimiter,
            encoding=payload.encoding,
        )
        try:
            first = next(records, None)
        finally:
            records.close()
        config["source_columns"] = list(first[1]) if first else selected["columns"]
        if payload.mapping and any(
            column not in config["source_columns"] for column in payload.mapping.values()
        ):
            raise ValueError("El mapeo contiene columnas que no existen en la hoja o formato seleccionado")
    except (ValueError, KeyError, OSError) as exc:
        raise HTTPException(422, f"Revise el formato del lote: {str(exc)[:250]}")
    item = Run(
        id=uid(),
        upload_id=upload.id,
        name=payload.name,
        reference_id=payload.reference_id,
        config=config,
        created_by=user.id,
    )
    db.add(item)
    db.add(Job(kind="RUN", target_id=item.id))
    audit(
        db,
        user.username,
        "run.created",
        item.id,
        {"upload_id": upload.id, "reference_id": payload.reference_id},
    )
    db.commit()
    return run_dict(db, item)


@router.post("/api/runs", status_code=201)
def create_run(payload: RunInput, user: User = Depends(operator), db: Session = Depends(get_db)):
    return new_run(db, payload, user)


@router.get("/api/runs")
def runs(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    db: Session = Depends(get_db),
    _: User = Depends(current_user),
):
    return page_result(
        db, select(Run).order_by(Run.created_at.desc()), lambda x: run_dict(db, x), page, page_size
    )


@router.get("/api/runs/{identifier}")
def get_run(identifier: str, db: Session = Depends(get_db), _: User = Depends(current_user)):
    return run_dict(db, require(db, Run, identifier))


@router.post("/api/runs/{identifier}/cancel")
def cancel_run(identifier: str, db: Session = Depends(get_db), user: User = Depends(operator)):
    item = require(db, Run, identifier)
    if item.status not in {"QUEUED", "INGESTING", "PROCESSING"}:
        raise HTTPException(409, "Este lote no está en ejecución")
    item.cancel_requested = True
    audit(db, user.username, "run.cancel_requested", identifier)
    db.commit()
    return run_dict(db, item)


@router.post("/api/runs/{identifier}/retry")
def retry_run(identifier: str, db: Session = Depends(get_db), user: User = Depends(operator)):
    item = require(db, Run, identifier)
    changed = db.execute(
        update(Run)
        .where(Run.id == identifier, Run.status.in_(["FAILED", "CANCELLED"]))
        .values(status="QUEUED", cancel_requested=False, error=None, finished_at=None)
    ).rowcount
    if changed != 1:
        raise HTTPException(409, "Solo se reintentan lotes fallidos o cancelados")
    db.add(Job(kind="RUN", target_id=identifier))
    audit(db, user.username, "run.retry", identifier)
    db.commit()
    db.refresh(item)
    return run_dict(db, item)


@router.post("/api/runs/{identifier}/reprocess", status_code=201)
def reprocess_run(identifier: str, db: Session = Depends(get_db), user: User = Depends(operator)):
    item = require(db, Run, identifier)
    config = {key: value for key, value in item.config.items() if key in RunInput.model_fields}
    return new_run(
        db,
        RunInput(
            upload_id=item.upload_id,
            name=f"{item.name[:175]} · reproceso",
            reference_id=item.reference_id,
            **config,
        ),
        user,
    )


@router.get("/api/runs/{identifier}/results")
def run_results(
    identifier: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    resolution: str | None = None,
    q: str = Query("", max_length=100),
    db: Session = Depends(get_db),
    _: User = Depends(current_user),
):
    require(db, Run, identifier)
    return page_result(
        db,
        filtered_locations(select(Location).where(Location.run_id == identifier), q, resolution),
        location_dict,
        page,
        page_size,
    )
