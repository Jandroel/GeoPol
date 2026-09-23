"""Public location-format flags never stand in for a geographic decision."""

from sqlalchemy import select, text

from geopol.migrations import migrate
from geopol.models import Location, Revision
from test_api import harness as harness
from test_quality_flow import advance, by_complaint, start, summary


def test_same_flag_keeps_automatic_quick_detailed_and_unmatched_distinct(harness):
    run_id = start(harness)
    results = by_complaint(harness, run_id)
    assert {results[key]["quality_flag"] for key in ("Q1", "Q2", "Q3", "Q4")} == {1}
    assert results["NO"]["quality_flag"] is None
    assert results["Q1"]["review_state"] == "automatic"
    assert results["Q2"]["review_state"] == "quick_review"
    assert results["Q3"]["review_state"] == "detailed_review"
    assert results["Q4"]["review_state"] == "unmatched"
    report = summary(harness, run_id)
    flag = next(group for group in report["flags"] if group["flag"] == 1)
    assert (flag["units"], flag["source_rows"], flag["resolved"], flag["review"]) == (4, 5, 1, 2)
    assert sum(group["units"] for group in report["review_states"]) == 5
    before = results["Q1"]
    assert advance(harness, run_id).status_code == 200
    assert harness.worker.work_once()
    after = by_complaint(harness, run_id)
    assert after["Q1"] == before
    assert after["Q2"]["review_state"] == "quick_review"
    assert after["Q4"]["quality_flag"] == 1
    assert after["Q4"]["review_state"] == "automatic"
    assert after["Q4"]["precision"] == "CUADRA"
    assert after["Q4"]["product"] == "AREA_TRAMO"


def test_flag_and_review_filters_are_independent_and_preserved_for_next(harness):
    run_id = start(harness)
    headers = harness.headers["admin"]
    query = f"run_id={run_id}&quality_flag=1&review_state=quick_review"
    response = harness.client.get(f"/api/runs/{run_id}/results?{query}", headers=headers)
    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["complaint_id"] == "Q2"
    queue = harness.client.get(f"/api/review?{query}", headers=headers).json()
    assert queue["total"] == 1
    counts = harness.client.get(f"/api/review/summary?{query}", headers=headers).json()
    assert counts["total"] == 1
    following = harness.client.get(f"/api/review/next?{query}", headers=headers).json()
    assert following["item"]["complaint_id"] == "Q2"
    assert (
        harness.client.get(f"/api/runs/{run_id}/results?quality_flag=3", headers=headers).status_code == 422
    )
    assert harness.client.get("/api/review?review_state=flag1", headers=headers).status_code == 422


def test_manual_acceptance_keeps_flag_and_snapshots_review_state(harness):
    run_id = start(harness)
    candidate = by_complaint(harness, run_id)["Q2"]
    detail = harness.client.get(f"/api/results/{candidate['id']}", headers=harness.headers["admin"]).json()
    response = harness.decide(candidate, "accept_candidate", candidate_id=detail["candidates"][0]["id"])
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["quality_flag"] == 1
    assert result["review_state"] == "accepted_manual"
    with harness.sessions() as db:
        item = db.get(Location, candidate["id"])
        assert item.quality_history[-2]["review_state"] == "quick_review"
        assert item.quality_history[-1]["review_state"] == "accepted_manual"
        snapshots = list(
            db.scalars(select(Revision).where(Revision.location_id == item.id).order_by(Revision.revision))
        )
        assert [row.snapshot["quality_flag"] for row in snapshots] == [1, 1]
        assert snapshots[0].snapshot["review_state"] == "quick_review"


def test_flag_two_can_be_reference_pending_without_acceptance(harness):
    upload_id = harness.upload(
        b"complaint_id,location_original,ubigeo,center_name\nSYN-CCPP,CENTRO SINTETICO,150101,CENTRO SINTETICO\n",
        "synthetic-center.csv",
    )
    response = harness.client.post(
        "/api/runs",
        json={
            "upload_id": upload_id,
            "name": "Synthetic flag two",
            "reference_id": None,
            "workflow": "quality_v1",
        },
        headers=harness.headers["admin"],
    )
    assert response.status_code == 201, response.text
    assert harness.worker.work_once()
    item = harness.results(response.json()["id"])[0]
    assert item["quality_flag"] == 2
    assert item["review_state"] == "reference_pending"
    assert item["resolution"] == "NO_EVALUABLE_REFERENCIA"
    assert item["latitude"] is None and item["longitude"] is None


def test_schema_six_adds_flags_without_reclassifying_previous_snapshots(harness):
    run_id = start(harness)
    engine = harness.sessions.kw["bind"]
    with engine.begin() as connection:
        before = connection.execute(text("SELECT id, snapshot FROM revisions ORDER BY id")).all()
        connection.execute(text("DROP INDEX ix_location_quality_flag"))
        for column in ("quality_flag", "quality_flag_reason", "review_state"):
            connection.execute(text(f"ALTER TABLE locations DROP COLUMN {column}"))
        connection.execute(text("DELETE FROM schema_versions WHERE version=6"))
    migrate(engine)
    migrate(engine)
    with engine.connect() as connection:
        assert connection.execute(text("SELECT id, snapshot FROM revisions ORDER BY id")).all() == before
        assert connection.scalar(text("SELECT max(version) FROM schema_versions")) == 6
    with harness.sessions() as db:
        items = list(db.scalars(select(Location).where(Location.run_id == run_id)))
        assert items and all(item.quality_flag is None and item.review_state is None for item in items)
        assert any(item.quality_code == 1 for item in items)
