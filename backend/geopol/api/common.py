"""Shared HTTP access, pagination and filtering helpers."""

from fastapi import HTTPException
from sqlalchemy import func, or_, select

from ..models import (
    Location,
    Upload,
)
from ..security import roles

operator = roles("admin", "operator")
reviewer = roles("admin", "reviewer")
administrator = roles("admin")

FINISHED = {"COMPLETED", "COMPLETED_WITH_ISSUES"}
REVIEW_STATUSES = {
    "REVISION_REQUERIDA",
    "SIN_COINCIDENCIA",
    "INFORMACION_INSUFICIENTE",
    "NO_EVALUABLE_REFERENCIA",
    "ERROR_TECNICO",
}


def require(db, model, identifier):
    item = db.get(model, identifier)
    if item is None:
        raise HTTPException(404, "Recurso no encontrado")
    return item


def page_result(db, query, serializer, page, page_size):
    total = db.scalar(select(func.count()).select_from(query.order_by(None).subquery()))
    items = db.scalars(query.offset((page - 1) * page_size).limit(page_size)).all()
    return {"items": [serializer(x) for x in items], "total": total, "page": page, "page_size": page_size}


def upload_dict(upload):
    return {
        key: getattr(upload, key)
        for key in ("id", "filename", "size", "offset", "status", "sha256", "profile")
    }


def owned_upload(db, identifier, user):
    upload = require(db, Upload, identifier)
    if upload.created_by != user.id and user.role != "admin":
        raise HTTPException(403, "La carga pertenece a otro operador")
    return upload


def filtered_locations(query, q, resolution=None):
    if resolution:
        query = query.where(Location.resolution == resolution)
    if q:
        escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        query = query.where(
            or_(
                Location.location_normalized.ilike(f"%{escaped}%", escape="\\"),
                Location.complaint_id.ilike(f"%{escaped}%", escape="\\"),
                Location.ubigeo.ilike(f"%{escaped}%", escape="\\"),
            )
        )
    return query.order_by(Location.id)
