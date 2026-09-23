"""The UI reports the current operation, not cumulative resolved/run counters."""

import time

from sqlalchemy import select

from geopol.models import Heartbeat, Job, Location, Run, User
from geopol.processing_activity import KEY, activity_dict, start_activity
from test_api import harness as harness
from test_quality_flow import advance, start


def get_run(harness, run_id):
    return harness.client.get(f"/api/runs/{run_id}", headers=harness.headers["admin"]).json()


def queued(harness):
    response = harness.client.post(
        "/api/runs",
        json={"upload_id": harness.upload(), "name": "Synthetic activity", "reference_id": None},
        headers=harness.headers["admin"],
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_queue_has_no_invented_processing_duration_or_total(harness):
    run = queued(harness)
    activity = run["activity"]
    assert activity["phase"] == "queued"
    assert activity["queued_at"] and activity["started_at"] is None
    assert activity["total_units"] is None
    assert activity["processed_units"] == 0
    assert activity["worker_online"] is False


def test_completed_operation_has_frozen_times_and_evaluated_counts(harness):
    run = queued(harness)
    assert harness.worker.work_once()
    first = get_run(harness, run["id"])["activity"]
    assert first["phase"] == "completed"
    assert first["queued_at"] <= first["started_at"] <= first["finished_at"]
    assert first["processed_units"] == first["total_units"] == 2
    assert first["source_rows"] == 3
    assert get_run(harness, run["id"])["activity"] == first


def test_quality_advance_resets_operation_progress_not_geographic_results(harness):
    identifier = start(harness)
    first = get_run(harness, identifier)
    assert first["activity"]["processed_units"] == 5
    response = advance(harness, identifier)
    assert response.status_code == 200
    current = response.json()
    assert current["processed_units"] == 5  # Existing cumulative run contract.
    assert current["activity"]["processed_units"] == 0
    assert current["activity"]["total_units"] == 2
    assert current["activity"]["stage"] == "block"
    assert current["activity"]["started_at"] is None
    assert current["activity"]["finished_at"] is None
    assert current["activity"]["job_id"] != first["activity"]["job_id"]
    assert harness.worker.work_once()
    finished = get_run(harness, identifier)["activity"]
    assert finished["processed_units"] == finished["total_units"] == 2
    assert finished["started_at"] >= first["activity"]["finished_at"]


def test_ingestion_does_not_show_partial_row_count_as_known_total(harness):
    identifier = queued(harness)["id"]
    with harness.sessions() as db:
        run = db.get(Run, identifier)
        run.status, run.source_rows, run.location_units = "INGESTING", 300, 200
        result = activity_dict(db, run)
        assert result["phase"] == "ingestion"
        assert result["source_rows"] == 300
        assert result["processed_units"] is None and result["total_units"] is None


def test_expired_job_does_not_report_live_worker_from_unrelated_heartbeat(harness):
    identifier = queued(harness)["id"]
    with harness.sessions() as db:
        run = db.get(Run, identifier)
        job = db.scalar(select(Job).where(Job.target_id == identifier))
        run.status, job.status, job.lease_until = "PROCESSING", "RUNNING", time.time() - 10
        db.add(Heartbeat(id="synthetic-worker", seen_at=time.time(), job_id=job.id))
        db.flush()
        assert activity_dict(db, run)["worker_online"] is False
        job.lease_until = time.time() + 60
        assert activity_dict(db, run)["worker_online"] is True


def test_retry_clears_old_operation_clock_and_lease_reclaim_preserves_new_clock(harness):
    identifier = queued(harness)["id"]
    assert harness.worker.work_once()
    with harness.sessions() as db:
        run = db.get(Run, identifier)
        run.status = "FAILED"
        db.commit()
    response = harness.client.post(f"/api/runs/{identifier}/retry", headers=harness.headers["admin"])
    assert response.status_code == 200
    assert response.json()["activity"]["started_at"] is None
    with harness.sessions() as db:
        run = db.get(Run, identifier)
        job = db.scalar(select(Job).where(Job.target_id == identifier).order_by(Job.created_at.desc()))
        start_activity(run, job)
        first_start = run.config[KEY]["started_at"]
        start_activity(run, job)
        assert run.config[KEY]["started_at"] == first_start


def test_historical_later_stage_does_not_reuse_initial_start_or_rewrite_config(harness):
    identifier = start(harness)
    assert advance(harness, identifier).status_code == 200
    assert harness.worker.work_once()
    with harness.sessions() as db:
        run = db.get(Run, identifier)
        run.config = {key: value for key, value in run.config.items() if key != KEY}
        db.commit()
        previous = dict(run.config)
    activity = get_run(harness, identifier)["activity"]
    assert activity["stage"] == "block" and activity["started_at"] is None
    assert activity["total_units"] is None
    with harness.sessions() as db:
        assert db.get(Run, identifier).config == previous


def test_stage_total_includes_reserved_case_released_after_queuing(harness):
    identifier = start(harness)
    with harness.sessions() as db:
        case = db.scalar(select(Location).where(Location.run_id == identifier, Location.complaint_id == "NO"))
        case.review_owner = db.scalar(select(User.id).where(User.role == "reviewer"))
        case.review_expires_at = time.time() + 600
        case_id = case.id
        db.commit()
    response = advance(harness, identifier)
    assert response.status_code == 200
    assert response.json()["activity"]["total_units"] == 1
    with harness.sessions() as db:
        case = db.get(Location, case_id)
        case.review_owner, case.review_expires_at = None, None
        db.commit()
    assert harness.worker.work_once()
    activity = get_run(harness, identifier)["activity"]
    assert activity["total_units"] == activity["processed_units"] == 2
