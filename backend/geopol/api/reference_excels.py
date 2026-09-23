"""Private, staged Excel reference imports using the resumable Upload contract."""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from ..catalogs import search_key
from ..config import settings
from ..db import get_db
from ..models import Catalog, Feature, User, uid
from ..reference_excel import parse_reference_excel, preview_reference_excel
from ..serialization import audit, catalog_dict
from ..storage import checksum, storage_file
from .common import operator, owned_upload

router = APIRouter()
ReferenceKind = Literal["doors", "roads", "centers", "boundaries", "jurisdictions"]


class ReferenceExcelPreviewInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    upload_id: str = Field(min_length=1, max_length=36)
    kind: ReferenceKind
    sheet: str | None = Field(default=None, max_length=200)


class ReferenceExcelInput(ReferenceExcelPreviewInput):
    name: str = Field(min_length=1, max_length=200)
    source: str = Field(min_length=1, max_length=500)
    version: str = Field(min_length=1, max_length=100)
    mapping: dict[str, str] = Field(default_factory=dict, max_length=32)
    crs: Literal["EPSG:4326"] | None = None
    crs_evidence: str | None = Field(default=None, max_length=500)
    street_types: dict[str, str] = Field(default_factory=dict, max_length=100)


def _uploaded_excel(db, payload, user):
    upload = owned_upload(db, payload.upload_id, user)
    if upload.status != "COMPLETE":
        raise HTTPException(409, "Complete la carga del Excel primero")
    if not upload.filename.lower().endswith(".xlsx"):
        raise HTTPException(422, "Las referencias de este módulo deben ser archivos XLSX")
    if upload.size > settings.catalog_bytes:
        raise HTTPException(413, "Referencia mayor de 24 MiB; particione el Excel")
    return upload, storage_file("uploads", upload.id)


@router.post("/api/reference-excels/preview")
def preview_reference(
    payload: ReferenceExcelPreviewInput, user: User = Depends(operator), db: Session = Depends(get_db)
):
    upload, path = _uploaded_excel(db, payload, user)
    try:
        return preview_reference_excel(path, upload.filename, kind=payload.kind, sheet=payload.sheet)
    except (ValueError, KeyError, OSError) as exc:
        raise HTTPException(422, f"Referencia no válida: {str(exc)[:250]}") from None


@router.post("/api/reference-excels", status_code=201)
def import_reference_excel(
    payload: ReferenceExcelInput, user: User = Depends(operator), db: Session = Depends(get_db)
):
    upload, path = _uploaded_excel(db, payload, user)
    if not payload.name.strip():
        raise HTTPException(422, "Indique un nombre para la referencia")
    try:
        if checksum(path) != upload.sha256:
            raise ValueError("El archivo original cambió; vuelva a cargarlo")
        features, report = parse_reference_excel(
            path, upload.filename, **payload.model_dump(exclude={"upload_id", "name"})
        )
        if checksum(path) != upload.sha256:
            raise ValueError("El archivo original cambió durante la importación")
    except (ValueError, KeyError, OSError) as exc:
        raise HTTPException(422, f"Referencia no válida: {str(exc)[:250]}") from None
    report.update(upload_id=upload.id, filename=upload.filename, source_sha256=upload.sha256)
    item = Catalog(
        id=uid(),
        name=payload.name.strip(),
        version=payload.version.strip(),
        source=payload.source.strip(),
        sha256=upload.sha256,
        feature_count=len(features),
        kinds=sorted({feature["kind"] for feature in features}),
        config={"reference_excel": report},
    )
    db.add(item)
    db.flush()
    for index, feature in enumerate(features, 1):
        feature.update(
            source_sha256=upload.sha256,
            source_upload_id=upload.id,
            source_sheet=report["sheet"],
            crs_evidence=report["crs_evidence"],
        )
        db.add(
            Feature(
                catalog_id=item.id,
                external_id=feature["id"],
                kind=feature["kind"],
                ubigeo=feature["ubigeo"],
                search_key=search_key(
                    feature.get("street_name") or feature.get("name") or feature.get("urban_core")
                ),
                payload=feature,
            )
        )
        if index % 500 == 0:
            db.flush()
    audit(
        db,
        user.username,
        "reference.excel_imported",
        item.id,
        {
            "upload_id": upload.id,
            "kind": payload.kind,
            "feature_count": item.feature_count,
            "staged_rows": report["staged_rows"],
            "sha256": item.sha256,
        },
    )
    db.commit()
    return catalog_dict(item)
