"""HTTP endpoints for exports."""

import time

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import and_, func, insert, literal, select, update
from sqlalchemy.orm import Session

from ..db import get_db
from ..domain.normalization import suggest_mapping
from ..models import (
    Catalog,
    Export,
    ExportItem,
    Job,
    Location,
    Revision,
    Run,
    Upload,
    User,
    uid,
)
from ..schemas import ExportInput
from ..security import current_user
from ..serialization import audit, catalog_dict, export_dict, export_format, iso
from ..storage import storage_file
from .common import FINISHED, require

router = APIRouter()


@router.post("/api/runs/{identifier}/exports", status_code=201)
def create_export(
    identifier: str, payload: ExportInput, db: Session = Depends(get_db), user: User = Depends(current_user)
):
    db.execute(update(Run).where(Run.id == identifier).values(id=Run.id))
    run = require(db, Run, identifier)
    db.refresh(run)
    if run.status not in FINISHED:
        raise HTTPException(409, "Solo se exportan lotes completos")
    if payload.profile == "source_rows" and user.role not in {"admin", "operator"}:
        raise HTTPException(403, "Exportar filas originales requiere rol operador o administrador")
    upload = db.get(Upload, run.upload_id)
    catalog = db.get(Catalog, run.reference_id) if run.reference_id else None
    filters = [Location.run_id == identifier]
    if payload.quality_code is not None:
        filters.append(Location.quality_code == payload.quality_code)
    if payload.quality_stage is not None:
        filters.append(Location.quality_stage == payload.quality_stage)
    if payload.quality_flag is not None:
        filters.append(Location.quality_flag == payload.quality_flag)
    if payload.review_state is not None:
        filters.append(Location.review_state == payload.review_state)
    filtered = any(
        value is not None
        for value in (payload.quality_code, payload.quality_stage, payload.quality_flag, payload.review_state)
    )
    quality_filter = None
    if filtered:
        if payload.quality_flag is None and payload.review_state is None:
            # Preserve the historical manifest contract for legacy clients.
            quality_filter = {"code": payload.quality_code, "stage": payload.quality_stage}
        else:
            quality_filter = {
                "flag": payload.quality_flag,
                "review_state": payload.review_state,
                "stage": payload.quality_stage,
            }
            if payload.quality_code is not None:
                quality_filter["code"] = payload.quality_code
    expected_rows = run.source_rows if payload.profile == "source_rows" else run.location_units
    if filtered:
        expected_rows = db.scalar(
            select(
                func.coalesce(func.sum(Location.source_row_count), 0)
                if payload.profile == "source_rows"
                else func.count()
            )
            .select_from(Location)
            .where(*filters)
        )
    source_mapping = {
        **suggest_mapping(run.config.get("source_columns", upload.profile.get("columns", []))),
        **(run.config.get("mapping") or {}),
    }
    has_input_flags = bool(source_mapping.get("source_quality_flag")) or bool(
        db.scalar(
            select(Location.id).where(Location.run_id == identifier, Location.quality_flag == 10).limit(1)
        )
    )
    export = Export(
        id=uid(),
        run_id=identifier,
        profile=payload.profile,
        safe_spreadsheet=payload.safe_spreadsheet if payload.format == "csv" else True,
        created_by=user.id,
        manifest={
            "schema_version": 6
            if has_input_flags
            else 5
            if run.config.get("workflow") == "quality_v1"
            else 3,
            "format": payload.format,
            "run_id": identifier,
            "run_name": run.name,
            "filename": upload.filename,
            "source_columns": list(run.config.get("source_columns", upload.profile.get("columns", []))),
            "source_sha256": upload.sha256,
            "rules_version": run.rules_version,
            "config": run.config,
            "reference": catalog_dict(catalog) if catalog else None,
            "profile": payload.profile,
            "expected_rows": expected_rows,
            "quality_filter": quality_filter,
            "snapshot_at": iso(time.time()),
            "revision_policy": "Revisión vigente al crear esta exportación; instantánea inmutable por unidad",
        },
    )
    db.add(export)
    db.flush()
    snapshots = (
        select(literal(export.id), Location.id, Revision.snapshot)
        .join(Revision, and_(Revision.location_id == Location.id, Revision.revision == Location.revision))
        .where(*filters)
    )
    db.execute(insert(ExportItem).from_select(["export_id", "location_id", "snapshot"], snapshots))
    db.add(Job(kind="EXPORT", target_id=export.id))
    audit(
        db,
        user.username,
        "export.created",
        export.id,
        {"profile": payload.profile, "format": payload.format},
    )
    db.commit()
    return export_dict(export)


def accessible_export(db, identifier, user):
    item = require(db, Export, identifier)
    if item.profile == "source_rows" and user.role not in {"admin", "operator"}:
        raise HTTPException(403, "Exportación restringida a operadores y administradores")
    return item


@router.get("/api/exports/{identifier}")
def get_export(identifier: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return export_dict(accessible_export(db, identifier, user))


@router.get("/api/exports/{identifier}/manifest")
def export_manifest(identifier: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return accessible_export(db, identifier, user).manifest


@router.get("/api/exports/{identifier}/download")
def download_export(identifier: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    item = accessible_export(db, identifier, user)
    if item.status != "COMPLETED":
        raise HTTPException(409, "La exportación todavía no está lista")
    file_format = export_format(item)
    audit(db, user.username, "export.download", identifier, {"format": file_format})
    db.commit()
    return FileResponse(
        storage_file("exports", item.id, f".{file_format}"),
        filename=export_dict(item)["filename"],
        media_type=(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            if file_format == "xlsx"
            else "text/csv; charset=utf-8"
        ),
    )
