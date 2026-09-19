"""HTTP endpoints for references."""

import csv
import hashlib
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..catalogs import read_catalog, search_key
from ..config import settings
from ..db import get_db
from ..models import (
    Catalog,
    Feature,
    User,
    uid,
)
from ..security import current_user
from ..serialization import audit, catalog_dict
from ..storage import storage_file
from .common import operator, page_result, require

router = APIRouter()


@router.get("/api/references")
def references(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    db: Session = Depends(get_db),
    _: User = Depends(current_user),
):
    return page_result(db, select(Catalog).order_by(Catalog.created_at.desc()), catalog_dict, page, page_size)


@router.get("/api/references/{identifier}")
def reference(identifier: str, db: Session = Depends(get_db), _: User = Depends(current_user)):
    return catalog_dict(require(db, Catalog, identifier))


@router.post("/api/references", status_code=201)
def import_reference(
    name: str = Form(min_length=1, max_length=200),
    version: str = Form(min_length=1, max_length=100),
    source: str = Form(min_length=1, max_length=500),
    file: UploadFile = File(),
    user: User = Depends(operator),
    db: Session = Depends(get_db),
):
    if not file.filename or Path(file.filename).suffix.lower() not in {".csv", ".geojson", ".json"}:
        raise HTTPException(422, "Use un catálogo CSV o GeoJSON")
    data = file.file.read(settings.catalog_bytes + 1)
    if len(data) > settings.catalog_bytes:
        raise HTTPException(413, "Catálogo mayor de 24 MiB; particione la referencia")
    item = Catalog(
        id=uid(),
        name=name,
        version=version,
        source=source,
        sha256=hashlib.sha256(data).hexdigest(),
        feature_count=0,
    )
    db.add(item)
    kinds = set()
    try:
        for feature in read_catalog(data, file.filename, source, version):
            kinds.add(feature["kind"])
            db.add(
                Feature(
                    catalog_id=item.id,
                    external_id=feature["id"],
                    kind=feature["kind"],
                    ubigeo=feature["ubigeo"],
                    search_key=search_key(feature.get("street_name") or feature.get("name")),
                    payload=feature,
                )
            )
            item.feature_count += 1
            if item.feature_count % 500 == 0:
                db.flush()
        item.kinds = sorted(kinds)
        db.flush()
    except (ValueError, TypeError, KeyError, AttributeError, csv.Error, IntegrityError):
        db.rollback()
        raise HTTPException(
            422,
            "Catálogo inválido: revise identificadores, UBIGEO, tipos, geometrías y coordenadas EPSG:4326",
        )
    path = storage_file("references", item.id)
    path.write_bytes(data)
    audit(
        db,
        user.username,
        "reference.imported",
        item.id,
        {"feature_count": item.feature_count, "sha256": item.sha256},
    )
    db.commit()
    return catalog_dict(item)
