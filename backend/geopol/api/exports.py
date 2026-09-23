"""HTTP endpoints for exports."""

import time

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import and_, insert, literal, select
from sqlalchemy.orm import Session

from ..db import get_db
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
    run = require(db, Run, identifier)
    if run.status not in FINISHED:
        raise HTTPException(409, "Solo se exportan lotes completos")
    if payload.profile == "source_rows" and user.role not in {"admin", "operator"}:
        raise HTTPException(403, "Exportar filas originales requiere rol operador o administrador")
    upload = db.get(Upload, run.upload_id)
    catalog = db.get(Catalog, run.reference_id) if run.reference_id else None
    export = Export(
        id=uid(),
        run_id=identifier,
        profile=payload.profile,
        safe_spreadsheet=payload.safe_spreadsheet if payload.format == "csv" else True,
        created_by=user.id,
        manifest={
            "schema_version": 3,
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
            "expected_rows": run.source_rows if payload.profile == "source_rows" else run.location_units,
            "snapshot_at": iso(time.time()),
            "revision_policy": "Revisión vigente al crear esta exportación; instantánea inmutable por unidad",
        },
    )
    db.add(export)
    db.flush()
    snapshots = (
        select(literal(export.id), Location.id, Revision.snapshot)
        .join(Revision, and_(Revision.location_id == Location.id, Revision.revision == Location.revision))
        .where(Location.run_id == identifier)
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
