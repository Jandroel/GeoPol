from datetime import datetime, timezone

from sqlalchemy import func, select

from .domain.coordinate_context import documented_crs
from .models import Audit, Catalog, Location, ProcessingDefaults, Revision, Upload
from .processing_activity import activity_dict


def iso(value):
    return datetime.fromtimestamp(value, timezone.utc).isoformat() if value is not None else None


def audit(db, actor, action, entity_id, detail=None):
    db.add(Audit(actor=actor, action=action, entity_id=entity_id, detail=detail or {}))


def location_dict(item):
    fields = (
        "id",
        "run_id",
        "complaint_id",
        "location_original",
        "location_normalized",
        "ubigeo",
        "resolution",
        "method",
        "precision",
        "evidence_band",
        "product",
        "latitude",
        "longitude",
        "geometry",
        "reason",
        "revision",
        "manual",
        "review_owner",
        "source_row_count",
        "review_status",
        "review_bucket",
        "quality_code",
        "quality_flag",
        "quality_flag_reason",
        "review_state",
        "quality_stage",
        "quality_status",
        "quality_reason",
        "quality_policy_version",
    )
    result = {key: getattr(item, key) for key in fields}
    result["review_expires_at"] = iso(item.review_expires_at)
    result["candidate_count"] = len(item.candidates or [])
    return result


def add_revision(db, item, actor, action):
    if item.quality_stage:
        from .quality_workflow import record_quality_revision

        record_quality_revision(item, actor, action)
    snapshot = location_dict(item)
    snapshot.update(candidates=item.candidates, attempts=item.attempts)
    if item.quality_stage:
        snapshot["quality_history"] = item.quality_history
    db.add(
        Revision(
            location_id=item.id,
            revision=item.revision,
            actor=actor,
            action=action,
            reason=item.reason,
            snapshot=snapshot,
        )
    )


def run_dict(db, run):
    result = {
        key: getattr(run, key)
        for key in (
            "id",
            "name",
            "status",
            "upload_id",
            "source_rows",
            "location_units",
            "processed_units",
            "issue_rows",
            "reference_id",
            "rules_version",
            "error",
            "config",
            "parent_run_id",
            "superseded_by",
        )
    }
    result.update({key: iso(getattr(run, key)) for key in ("created_at", "started_at", "finished_at")})
    upload = db.get(Upload, run.upload_id)
    result["filename"] = upload.filename
    result["activity"] = activity_dict(db, run)
    result["counts"] = dict(
        db.execute(
            select(Location.resolution, func.count())
            .where(Location.run_id == run.id)
            .group_by(Location.resolution)
        ).all()
    )
    result["counts_by_product"] = dict(
        db.execute(
            select(Location.product, func.count())
            .where(Location.run_id == run.id, Location.resolution == "ACEPTADO_AUTOMATICO")
            .group_by(Location.product)
        ).all()
    )
    return result


def catalog_dict(item):
    return {
        key: getattr(item, key)
        for key in ("id", "name", "version", "source", "feature_count", "sha256", "kinds", "config")
    }


def reference_status(db, reference_id):
    catalog = db.get(Catalog, reference_id) if reference_id else None
    return {
        "reference_id": reference_id,
        "catalog": catalog_dict(catalog) if catalog else None,
        "status": (
            "not_configured"
            if not reference_id
            else "missing"
            if catalog is None
            else "empty"
            if not catalog.feature_count
            else "ready"
        ),
    }


def processing_defaults_dict(db):
    item = db.get(ProcessingDefaults, "global")
    status = reference_status(db, item.reference_id if item else None)
    return {
        "default_reference_id": status["reference_id"],
        "catalog": status["catalog"],
        "status": status["status"],
        "updated_at": iso(item.updated_at) if item else None,
        "updated_by": item.updated_by if item else None,
    }


def run_readiness_dict(db, run):
    """Aggregate the persisted queue; do not load candidate lists or source rows."""
    buckets = dict(
        db.execute(
            select(Location.review_bucket, func.count())
            .where(Location.run_id == run.id, Location.review_status == "OPEN")
            .group_by(Location.review_bucket)
        ).all()
    )
    products = dict(
        db.execute(
            select(Location.product, func.count())
            .where(Location.run_id == run.id, Location.resolution == "ACEPTADO_AUTOMATICO")
            .group_by(Location.product)
        ).all()
    )
    evidence = run.config.get("crs_evidence")
    confirmed = documented_crs(run.config)
    actions = {
        "needs_reference": "Incorporar referencias o confirmar el sistema de coordenadas y reprocesar",
        "needs_data": "Completar los datos de origen antes de una revisión individual",
        "actionable": "Comparar candidatos y aprovechar las direcciones equivalentes",
        "technical": "Resolver la incidencia técnica y volver a procesar",
        "none": "Esperar a que finalice el procesamiento",
    }
    return {
        "run_id": run.id,
        "reference": reference_status(db, run.reference_id),
        "processing_defaults": processing_defaults_dict(db),
        "coordinates": {
            "crs": run.config.get("crs"),
            "evidence": evidence,
            "confirmed": confirmed,
            "legacy_unconfirmed": bool(run.config.get("crs")) and not confirmed,
        },
        "review": {
            "total_open": sum(buckets.values()),
            "by_bucket": buckets,
            "causes": [
                {"bucket": bucket, "count": count, "action": actions.get(bucket, "Consultar el resultado")}
                for bucket, count in sorted(buckets.items(), key=lambda item: (-item[1], item[0]))
            ],
        },
        "automatic": {"points": products.get("PUNTO", 0), "areas": products.get("AREA_TRAMO", 0)},
    }


def export_format(item):
    """Historical manifests without a format retain their original CSV contract."""
    value = (item.manifest or {}).get("format", "csv")
    if value not in {"csv", "xlsx"}:
        raise ValueError("Formato de exportación no admitido")
    return value


def export_dict(item):
    file_format = export_format(item)
    return {
        "id": item.id,
        "run_id": item.run_id,
        "status": item.status,
        "profile": item.profile,
        "format": file_format,
        "error": item.error,
        "filename": f"geopol-{item.profile}-{item.id}.{file_format}",
        "row_count": item.row_count,
        "sha256": item.sha256,
        "created_at": iso(item.created_at),
    }
