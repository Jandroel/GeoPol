"""HTTP endpoints for system."""

import time

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from .. import __version__
from ..db import get_db
from ..domain import RULES_VERSION
from ..migrations import SCHEMA_VERSION
from ..models import (
    Audit,
    Heartbeat,
    Location,
    Run,
    User,
)
from ..security import current_user
from ..serialization import iso, run_dict
from .common import FINISHED, REVIEW_STATUSES, administrator, page_result

router = APIRouter()


@router.get("/api/health")
def health(db: Session = Depends(get_db)):
    try:
        db.execute(
            text("SELECT version FROM schema_versions WHERE version = :version"),
            {"version": SCHEMA_VERSION},
        ).scalar_one()
        return {"status": "ok", "version": __version__, "database": "ok", "schema_version": SCHEMA_VERSION}
    except SQLAlchemyError:
        raise HTTPException(503, "Base de datos no disponible o sin inicializar")


@router.get("/api/health/worker")
def worker_health(db: Session = Depends(get_db), _: User = Depends(current_user)):
    last = db.scalar(select(func.max(Heartbeat.seen_at)))
    return {"status": "ok" if last and time.time() - last < 60 else "unavailable", "last_seen_at": iso(last)}


@router.get("/api/dashboard")
def dashboard(db: Session = Depends(get_db), _: User = Depends(current_user)):
    current = (Run.superseded_by.is_(None), Run.status.in_(FINISHED))
    locations = select(Location).join(Run, Location.run_id == Run.id).where(*current)
    counts = dict(
        db.execute(
            locations.with_only_columns(Location.resolution, func.count()).group_by(Location.resolution)
        ).all()
    )
    totals = db.execute(
        select(
            func.coalesce(func.sum(Run.source_rows), 0),
            func.coalesce(func.sum(Run.location_units), 0),
        ).where(*current)
    ).one()
    return {
        "runs": db.scalar(select(func.count()).select_from(Run)),
        "source_rows": totals[0],
        "location_units": totals[1],
        "review_open": db.scalar(
            locations.with_only_columns(func.count()).where(Location.review_status == "OPEN")
        ),
        "review_actionable": db.scalar(
            locations.with_only_columns(func.count()).where(
                Location.review_status == "OPEN", Location.review_bucket == "actionable"
            )
        ),
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
                "description": "Puerta exacta, coordenadas corroboradas y cruces explícitos pueden aceptarse. Las evidencias exactas del mismo punto, método y precisión conservan sus procedencias. Coincidencias aproximadas, candidatos distintos, cuadras y sitios requieren revisión.",
            },
            {
                "name": "Revisión y exportación",
                "description": "Bandeja por acción necesaria, reserva temporal, decisión y siguiente caso. Una decisión manual finaliza la tarea hasta su reapertura explícita. El reproceso conserva la historia y reemplaza la versión vigente solo al completarse. Exportación por instantánea; casos sin resolver conservados con coordenadas vacías.",
            },
        ],
        "limitations": [
            "Los métodos dependientes de cartografía requieren un catálogo validado y seleccionado para la ejecución; los límites distritales por sí solos no geocodifican direcciones sin coordenadas.",
            "Las bandas de evidencia no representan probabilidades calibradas.",
            "El mapa local no usa una base cartográfica pública ni geocodificadores externos.",
            "Un catálogo admite hasta 24 MiB y 100 000 entidades; búsqueda difusa acotada a 500 candidatos territoriales, con revisión obligatoria si se trunca.",
            "El despliegue local SQLite admite un solo worker. PostgreSQL/PostGIS se utiliza para el despliegue institucional.",
        ],
    }
