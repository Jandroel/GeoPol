"""Persist job-specific progress without changing geographic decisions or counters.

The latest operation's metadata lives in Run.config; immutable result revisions
and historical jobs remain untouched. Counts represent evaluated locations in
this operation, never accepted locations or the cumulative run counter.
"""

import time
from datetime import datetime, timezone

from sqlalchemy import select

from .config import settings
from .models import Heartbeat, Job

KEY = "processing_activity"
ACTIVE = {"QUEUED", "INGESTING", "PROCESSING"}
PHASES = {
    "QUEUED": "queued",
    "INGESTING": "ingestion",
    "PROCESSING": "resolution",
    "COMPLETED": "completed",
    "COMPLETED_WITH_ISSUES": "completed",
    "FAILED": "failed",
    "CANCELLED": "cancelled",
}


def queue_activity(run, job, *, total_units=None):
    run.config = {
        **run.config,
        KEY: {
            "job_id": job.id,
            "queued_at": job.created_at,
            "started_at": None,
            "finished_at": None,
            "processed_units": 0,
            "total_units": total_units,
        },
    }


def start_activity(run, job):
    activity = run.config.get(KEY, {})
    if activity.get("job_id") != job.id:
        queue_activity(run, job)
        activity = run.config[KEY]
    if activity.get("started_at") is None:
        run.config = {**run.config, KEY: {**activity, "started_at": time.time()}}


def set_activity_total(run, pending_units):
    activity = run.config.get(KEY, {})
    total = activity.get("processed_units", 0) + pending_units
    if activity.get("total_units") != total:
        run.config = {**run.config, KEY: {**activity, "total_units": total}}


def progress_activity(run, count):
    activity = run.config.get(KEY, {})
    run.config = {
        **run.config,
        KEY: {**activity, "processed_units": activity.get("processed_units", 0) + count},
    }


def finish_activity(run, job_id):
    activity = run.config.get(KEY, {})
    if activity.get("job_id") == job_id:
        run.config = {**run.config, KEY: {**activity, "finished_at": run.finished_at}}


def _iso(value):
    return datetime.fromtimestamp(value, timezone.utc).isoformat() if value is not None else None


def activity_dict(db, run):
    job = db.scalar(
        select(Job)
        .where(Job.kind == "RUN", Job.target_id == run.id)
        .order_by(Job.created_at.desc(), Job.id.desc())
        .limit(1)
    )
    stored = run.config.get(KEY, {})
    current = stored if job and stored.get("job_id") == job.id else {}
    stage = (
        run.config.get("quality_target_stage", "door") if run.config.get("workflow") == "quality_v1" else None
    )
    phase = PHASES.get(run.status, "unknown")
    active = run.status in ACTIVE
    started = current.get("started_at")
    # Old later stages and retries did not record their start time. The original
    # run start must not be presented as the duration of a later operation.
    if not current and job and run.started_at and run.started_at >= job.created_at:
        started = run.started_at
    processed, total = current.get("processed_units"), current.get("total_units")
    if not current and stage in {None, "door"} and run.ingested:
        processed, total = run.processed_units, run.location_units
    if phase == "ingestion":
        processed, total = None, None
    online = None
    if active:
        now = time.time()
        query = select(Heartbeat.id).where(Heartbeat.seen_at >= now - settings.lease_seconds)
        if phase != "queued":
            query = query.where(Heartbeat.job_id == (job.id if job else ""))
        online = bool(db.scalar(query.limit(1)))
        if phase != "queued" and job and (job.lease_until is None or job.lease_until < now):
            online = False
    return {
        "job_id": job.id if job else None,
        "status": "RUNNING"
        if phase in {"ingestion", "resolution"}
        else "COMPLETED"
        if phase == "completed"
        else run.status
        if phase != "unknown"
        else None,
        "phase": phase,
        "stage": stage,
        "queued_at": _iso(job.created_at) if job else None,
        "started_at": _iso(started),
        "finished_at": None if active else _iso(current.get("finished_at") or run.finished_at),
        "processed_units": processed,
        "total_units": total,
        "source_rows": run.source_rows,
        "worker_online": online,
    }
