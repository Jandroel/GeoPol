"""HTTP endpoints for system."""

import time

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from .. import __version__
from ..db import get_db
from ..domain import RULES_VERSION
from ..models import (
    Audit,
    Heartbeat,
    Location,
    Run,
    User,
)
from ..security import current_user
from ..serialization import iso, run_dict
from .common import REVIEW_STATUSES, administrator, page_result

router = APIRouter()


@router.get("/api/health")
def health(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT version FROM schema_versions WHERE version = 1")).scalar_one()
        return {"status": "ok", "version": __version__, "database": "ok"}
    except SQLAlchemyError:
        raise HTTPException(503, "Base de datos no disponible o sin inicializar")


@router.get("/api/health/worker")
def worker_health(db: Session = Depends(get_db), _: User = Depends(current_user)):
    last = db.scalar(select(func.max(Heartbeat.seen_at)))
    return {"status": "ok" if last and time.time() - last < 60 else "unavailable", "last_seen_at": iso(last)}


@router.get("/api/dashboard")
def dashboard(db: Session = Depends(get_db), _: User = Depends(current_user)):
    counts = dict(db.execute(select(Location.resolution, func.count()).group_by(Location.resolution)).all())
    totals = db.execute(
        select(
            func.count(Run.id),
            func.coalesce(func.sum(Run.source_rows), 0),
            func.coalesce(func.sum(Run.location_units), 0),
        )
    ).one()
    return {
        "runs": totals[0],
        "source_rows": totals[1],
        "location_units": totals[2],
        "review_required": counts.get("REVISION_REQUERIDA", 0),
        "accepted": sum(counts.get(k, 0) for k in ("ACEPTADO_AUTOMATICO", "ACEPTADO_MANUAL")),
        "unresolved": sum(counts.get(k, 0) for k in REVIEW_STATUSES - {"REVISION_REQUERIDA"}),
        "recent_runs": [
            run_dict(db, x) for x in db.scalars(select(Run).order_by(Run.created_at.desc()).limit(6))
        ],
    }


@router.get("/api/audit")
def get_audit(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    db: Session = Depends(get_db),
    _: User = Depends(administrator),
):
    return page_result(
        db,
        select(Audit).order_by(Audit.created_at.desc()),
        lambda x: {
            "id": x.id,
            "actor": x.actor,
            "action": x.action,
            "entity_id": x.entity_id,
            "created_at": iso(x.created_at),
            "detail": x.detail,
        },
        page,
        page_size,
    )


@router.get("/api/rules")
def rules(_: User = Depends(current_user)):
    return {
        "version": RULES_VERSION,
        "policies": [
            {
                "name": "Conservación y trazabilidad",
                "description": "Cada fila permanece vinculada a su unidad de ubicación. Se conservan archivo, huella SHA-256, reglas, referencia y revisiones.",
            },
            {
                "name": "Coordenadas SIDPOL",
                "description": "xx representa latitud y yy longitud. Los centroides heredados no se promueven a coordenadas originales. La aceptación directa requiere CRS conocido y corroboración territorial.",
            },
            {
                "name": "Normalización",
                "description": "Mayúsculas, tildes, espacios, tipo de vía, puerta, cuadra, cruces y UBIGEO de seis dígitos; transformaciones registradas por unidad.",
            },
            {
                "name": "Coincidencia y ambigüedad",
                "description": "Puerta exacta, coordenadas corroboradas y cruces explícitos pueden aceptarse. Coincidencias aproximadas, múltiples candidatos, cuadras y sitios requieren revisión.",
            },
            {
                "name": "Revisión y exportación",
                "description": "Asignación temporal, control de versión y evidencia manual. Exportación por instantánea; registros no resueltos conservados con coordenadas vacías.",
            },
        ],
        "limitations": [
            "No se ha suministrado cartografía oficial INEI. Importe una referencia validada antes de evaluar métodos que la requieran.",
            "Las bandas de evidencia no representan probabilidades calibradas.",
            "El mapa local no usa una base cartográfica pública ni geocodificadores externos.",
            "Un catálogo admite hasta 24 MiB y 100 000 entidades; búsqueda difusa acotada a 500 candidatos territoriales, con revisión obligatoria si se trunca.",
            "El despliegue local SQLite admite un solo worker. PostgreSQL/PostGIS se utiliza para el despliegue institucional.",
        ],
    }
