from datetime import datetime, timezone

from sqlalchemy import func, select

from .models import Audit, Location, Revision, Upload


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
        "reason",
        "revision",
        "manual",
        "review_owner",
        "source_row_count",
        "review_status",
        "review_bucket",
    )
    result = {key: getattr(item, key) for key in fields}
    result["review_expires_at"] = iso(item.review_expires_at)
    result["candidate_count"] = len(item.candidates or [])
    return result


def add_revision(db, item, actor, action):
    snapshot = location_dict(item)
    snapshot.update(candidates=item.candidates, attempts=item.attempts)
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
    result["counts"] = dict(
        db.execute(
            select(Location.resolution, func.count())
            .where(Location.run_id == run.id)
            .group_by(Location.resolution)
        ).all()
    )
    return result


def catalog_dict(item):
    return {
        key: getattr(item, key)
        for key in ("id", "name", "version", "source", "feature_count", "sha256", "kinds")
    }


def export_dict(item):
    return {
        "id": item.id,
        "run_id": item.run_id,
        "status": item.status,
        "profile": item.profile,
        "error": item.error,
        "filename": f"geopol-{item.profile}-{item.id}.csv",
        "row_count": item.row_count,
        "sha256": item.sha256,
        "created_at": iso(item.created_at),
    }
