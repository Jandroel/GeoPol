"""HTTP endpoints for runs."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..domain.coordinate_context import documented_crs
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
from ..schemas import ReprocessInput, RunInput
from ..security import current_user
from ..serialization import audit, location_dict, processing_defaults_dict, run_dict, run_readiness_dict
from ..storage import storage_file
from .common import filtered_locations, operator, owned_upload, page_result, require

router = APIRouter()


def new_run(db, payload, user, parent_run_id=None):
    upload = owned_upload(db, payload.upload_id, user)
    if upload.status != "COMPLETE":
        raise HTTPException(409, "Complete la carga primero")
    reference_id = payload.reference_id
    uses_default = "reference_id" not in payload.model_fields_set
    if uses_default:
        defaults = processing_defaults_dict(db)
        if defaults["status"] in {"missing", "empty"}:
            raise HTTPException(
                409, "La referencia predeterminada no está disponible; revise su configuración"
            )
        reference_id = defaults["default_reference_id"]
    if reference_id:
        require(db, Catalog, reference_id)
    if payload.sheet and payload.sheet not in upload.profile.get("sheets", []):
        raise HTTPException(422, "La hoja seleccionada no existe")
    config = payload.model_dump(exclude={"upload_id", "name", "reference_id"})
    config["reference_selection"] = "default" if uses_default else "explicit"
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
        reference_id=reference_id,
        config=config,
        created_by=user.id,
        parent_run_id=parent_run_id,
    )
    db.add(item)
    db.add(Job(kind="RUN", target_id=item.id))
    audit(
        db,
        user.username,
        "run.created",
        item.id,
        {
            "upload_id": upload.id,
            "reference_id": reference_id,
            "reference_selection": config["reference_selection"],
            "parent_run_id": parent_run_id,
        },
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


@router.get("/api/runs/{identifier}/readiness")
def run_readiness(identifier: str, db: Session = Depends(get_db), _: User = Depends(current_user)):
    return run_readiness_dict(db, require(db, Run, identifier))


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
    if item.parent_run_id:
        db.execute(update(Run).where(Run.id == item.parent_run_id).values(id=Run.id))
        parent = db.get(Run, item.parent_run_id)
        if parent.superseded_by:
            raise HTTPException(409, "El reproceso ya fue sustituido por una ejecución completada")
        sibling = db.scalar(
            select(Run.id)
            .where(
                Run.parent_run_id == item.parent_run_id,
                Run.id != identifier,
                Run.status.in_({"QUEUED", "INGESTING", "PROCESSING"}),
            )
            .limit(1)
        )
        if sibling:
            raise HTTPException(409, "Ya existe otro reproceso en curso para esta ejecución")
    changed = db.execute(
        update(Run)
        .where(Run.id == identifier, Run.status.in_(["FAILED", "CANCELLED"]), Run.superseded_by.is_(None))
        .values(status="QUEUED", cancel_requested=False, error=None, finished_at=None)
    ).rowcount
    if changed != 1:
        raise HTTPException(409, "Solo se reintentan lotes fallidos o cancelados que siguen vigentes")
    db.add(Job(kind="RUN", target_id=identifier))
    audit(db, user.username, "run.retry", identifier)
    db.commit()
    db.refresh(item)
    return run_dict(db, item)


@router.post("/api/runs/{identifier}/reprocess", status_code=201)
def reprocess_run(
    identifier: str,
    payload: ReprocessInput | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(operator),
):
    item = require(db, Run, identifier)
    # Serialize creation of children on SQLite as well as PostgreSQL. Refresh after
    # acquiring the parent row's write lock, before checking the current lineage.
    db.execute(update(Run).where(Run.id == identifier).values(id=Run.id))
    db.refresh(item)
    if item.status not in {"COMPLETED", "COMPLETED_WITH_ISSUES", "FAILED", "CANCELLED"}:
        raise HTTPException(409, "Espere a que termine la ejecución antes de reprocesarla")
    if item.superseded_by:
        raise HTTPException(
            409, "Esta ejecución tiene una versión más reciente; reprocese la versión vigente"
        )
    active_child = db.scalar(
        select(Run.id)
        .where(Run.parent_run_id == item.id, Run.status.in_({"QUEUED", "INGESTING", "PROCESSING"}))
        .limit(1)
    )
    if active_child:
        raise HTTPException(409, "Ya existe un reproceso en curso para esta ejecución")
    reference_id = item.reference_id
    if payload is not None and "reference_id" in payload.model_fields_set:
        reference_id = payload.reference_id
    config = {
        key: value
        for key, value in item.config.items()
        if key in RunInput.model_fields and key not in {"upload_id", "name", "reference_id"}
    }
    if payload is not None and "crs" in payload.model_fields_set:
        config["crs"] = payload.crs
        config["crs_evidence"] = payload.crs_evidence if payload.crs else None
    else:
        # Older forms assigned WGS84 silently. Reprocessing must not turn that
        # historical assumption into newly confirmed geographic evidence.
        if not documented_crs(config):
            config["crs"] = None
            config["crs_evidence"] = None
    return new_run(
        db,
        RunInput(
            upload_id=item.upload_id,
            name=f"{item.name[:175]} · reproceso",
            reference_id=reference_id,
            **config,
        ),
        user,
        parent_run_id=item.id,
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
