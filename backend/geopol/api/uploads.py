"""HTTP endpoints for uploads."""

import os
from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..domain.ingestion import inspect_file, iter_records
from ..models import (
    Upload,
    User,
    uid,
)
from ..schemas import UploadInput
from ..serialization import audit
from ..storage import checksum, storage_file, upload_lock
from .common import operator, owned_upload, upload_dict

router = APIRouter()


@router.post("/api/uploads", status_code=201)
def create_upload(payload: UploadInput, user: User = Depends(operator), db: Session = Depends(get_db)):
    filename = payload.filename.replace("\\", "/").split("/")[-1]
    if Path(filename).suffix.lower() not in {".csv", ".xlsx"}:
        raise HTTPException(422, "Solo se admiten archivos CSV y XLSX")
    if payload.size > settings.max_upload_bytes:
        raise HTTPException(413, "El archivo supera el límite de carga configurado")
    item = Upload(
        id=uid(), filename=filename, size=payload.size, offset=0, status="UPLOADING", created_by=user.id
    )
    db.add(item)
    storage_file("uploads", item.id).touch(exist_ok=False)
    audit(db, user.username, "upload.created", item.id, {"size": payload.size})
    db.commit()
    return upload_dict(item)


@router.get("/api/uploads/{identifier}")
def get_upload(identifier: str, user: User = Depends(operator), db: Session = Depends(get_db)):
    item = owned_upload(db, identifier, user)
    if item.status == "UPLOADING":
        item.offset = storage_file("uploads", item.id).stat().st_size
    return upload_dict(item)


@router.patch("/api/uploads/{identifier}")
async def upload_chunk(
    identifier: str,
    request: Request,
    upload_offset: int = Header(alias="Upload-Offset", ge=0),
    user: User = Depends(operator),
    db: Session = Depends(get_db),
):
    item = owned_upload(db, identifier, user)
    if item.status != "UPLOADING":
        raise HTTPException(409, "La carga ya está cerrada")
    data = bytearray()
    async for chunk in request.stream():
        if len(data) + len(chunk) > settings.chunk_bytes:
            raise HTTPException(413, "El fragmento supera 8 MiB")
        data.extend(chunk)
    if not data:
        raise HTTPException(422, "Fragmento vacío")
    with upload_lock(item.id):
        db.refresh(item)
        path = storage_file("uploads", item.id)
        actual = path.stat().st_size
        if item.status != "UPLOADING" or actual != upload_offset:
            raise HTTPException(409, "Offset distinto; consulte la carga para reanudar")
        if actual + len(data) > item.size:
            raise HTTPException(422, "El fragmento excede el tamaño declarado")
        with path.open("ab") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        item.offset = path.stat().st_size
        db.commit()
    return upload_dict(item)


@router.get("/api/uploads/{identifier}/profile")
def upload_profile(
    identifier: str,
    sheet: str | None = None,
    delimiter: str | None = Query(None, min_length=1, max_length=1),
    encoding: str | None = None,
    user: User = Depends(operator),
    db: Session = Depends(get_db),
):
    item = owned_upload(db, identifier, user)
    if item.status != "COMPLETE":
        raise HTTPException(409, "Complete la carga primero")
    path = storage_file("uploads", item.id)
    try:
        profile = inspect_file(path, item.filename, sheet=sheet)
        if delimiter or encoding:
            from ..domain.normalization import suggest_mapping

            records = iter_records(
                path,
                item.filename,
                sheet=sheet,
                delimiter=delimiter or profile["delimiter"],
                encoding=encoding or profile["encoding"],
            )
            try:
                first = next(records, None)
            finally:
                records.close()
            if first:
                profile["columns"] = list(first[1])
                profile["suggested_mapping"] = suggest_mapping(profile["columns"])
                profile["sample"] = [
                    {
                        k: first[1].get(v)
                        for k, v in profile["suggested_mapping"].items()
                        if k != "complaint_id"
                    }
                ]
            profile["delimiter"], profile["encoding"] = (
                delimiter or profile["delimiter"],
                encoding or profile["encoding"],
            )
        return profile
    except (ValueError, KeyError, OSError) as exc:
        raise HTTPException(422, f"Perfil no válido: {str(exc)[:250]}")


@router.get("/api/uploads/{identifier}/download")
def download_original(identifier: str, user: User = Depends(operator), db: Session = Depends(get_db)):
    item = owned_upload(db, identifier, user)
    if item.status != "COMPLETE":
        raise HTTPException(409, "El archivo original todavía está cargándose")
    audit(db, user.username, "upload.download", identifier)
    db.commit()
    return FileResponse(
        storage_file("uploads", identifier), filename=item.filename, media_type="application/octet-stream"
    )


@router.post("/api/uploads/{identifier}/complete")
def complete_upload(identifier: str, user: User = Depends(operator), db: Session = Depends(get_db)):
    item = owned_upload(db, identifier, user)
    if item.status == "COMPLETE":
        return upload_dict(item)
    with upload_lock(item.id):
        path = storage_file("uploads", item.id)
        if path.stat().st_size != item.size:
            raise HTTPException(409, "Aún faltan bytes por cargar")
        try:
            profile = inspect_file(path, item.filename)
        except (ValueError, OSError, KeyError) as exc:
            raise HTTPException(422, f"Archivo no válido: {str(exc)[:250]}")
        item.sha256, item.profile, item.offset, item.status = checksum(path), profile, item.size, "COMPLETE"
        audit(db, user.username, "upload.completed", item.id, {"sha256": item.sha256})
        db.commit()
    return upload_dict(item)
