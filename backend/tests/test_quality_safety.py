"""Independent safety regressions around persisted manual quality and upgrades."""

from copy import deepcopy

from sqlalchemy import select, text

from geopol.migrations import migrate
from geopol.models import Catalog, Feature, Location, Revision, Run
from test_api import harness as harness
from test_export_xlsx import create, download, records
from test_quality_flow import advance, by_complaint, start, summary


def test_rejected_quick_door_loses_quality_code_and_can_advance(harness):
    run_id = start(harness)
    q2 = by_complaint(harness, run_id)["Q2"]
    response = harness.decide(q2, "unresolved")
    assert response.status_code == 200, response.text
    rejected = response.json()
    assert rejected["quality_status"] == "unmatched"
    assert rejected["quality_code"] is None
    assert summary(harness, run_id)["eligible_units"] == 3
    assert advance(harness, run_id).status_code == 200
    assert harness.worker.work_once()
    assert by_complaint(harness, run_id)["Q2"]["quality_stage"] == "block"


def test_manually_confirmed_block_receives_q4_and_history_preserves_review(harness):
    run_id = start(harness)
    with harness.sessions() as db:
        run = db.get(Run, run_id)
        catalog = db.get(Catalog, run.reference_id)
        original = db.scalar(select(Feature).where(Feature.catalog_id == catalog.id, Feature.kind == "block"))
        payload = deepcopy(original.payload)
        payload.update(
            id="other-block", geometry={"type": "LineString", "coordinates": [[-77.2, -12.2], [-77.1, -12.2]]}
        )
        db.add(
            Feature(
                catalog_id=catalog.id,
                external_id="other-block",
                kind="block",
                ubigeo=original.ubigeo,
                search_key=original.search_key,
                payload=payload,
            )
        )
        catalog.feature_count += 1
        db.commit()
    assert advance(harness, run_id).status_code == 200
    assert harness.worker.work_once()
    q4 = by_complaint(harness, run_id)["Q4"]
    assert q4["quality_stage"] == "block" and q4["quality_status"] == "review"
    assert q4["quality_code"] is None
    detail = harness.client.get(f"/api/results/{q4['id']}", headers=harness.headers["admin"]).json()
    response = harness.decide(q4, "accept_candidate", candidate_id=detail["candidates"][0]["id"])
    assert response.status_code == 200, response.text
    assert response.json()["quality_code"] == 4
    assert response.json()["quality_status"] == "resolved"
    with harness.sessions() as db:
        item = db.get(Location, q4["id"])
        assert item.quality_history[-2]["quality_status"] == "review"
        assert item.quality_history[-2]["quality_code"] is None
        assert item.quality_history[-1]["quality_code"] == 4
        latest = db.scalar(
            select(Revision).where(Revision.location_id == item.id, Revision.revision == item.revision)
        )
        assert latest.snapshot["quality_code"] == 4


def test_reopened_q1_is_never_exported_as_automatic_quality_one(harness):
    run_id = start(harness)
    q1 = by_complaint(harness, run_id)["Q1"]
    response = harness.decide(q1, "reopen")
    assert response.status_code == 200, response.text
    assert response.json()["quality_status"] == "review"
    assert response.json()["quality_code"] == 3
    report = summary(harness, run_id)
    assert next(group for group in report["qualities"] if group["code"] == 1)["units"] == 0


def test_filtered_empty_source_export_has_zero_rows_without_other_qualities(harness):
    run_id = start(harness)
    export = create(harness, run_id, profile="source_rows", quality_code=4)
    assert harness.worker.work_once()
    workbook, info, manifest = download(harness, export["id"])
    try:
        assert info["row_count"] == manifest["expected_rows"] == 0
        assert records(workbook, manifest) == []
        assert records(workbook, manifest, "Datos originales") == []
    finally:
        workbook.close()


def test_manual_point_cannot_claim_polygon_jurisdiction_precision(harness):
    run_id = start(harness)
    candidate = by_complaint(harness, run_id)["Q3"]
    response = harness.decide(
        candidate,
        "manual_point",
        latitude=-12.1,
        longitude=-77.1,
        precision="JURISDICCION",
        evidence="Verificación sintética de prueba",
    )
    assert response.status_code == 422, response.text
    current = by_complaint(harness, run_id)["Q3"]
    assert current["revision"] == candidate["revision"]
    assert current["product"] != "PUNTO"


def test_invalid_reference_selection_returns_validation_error_without_run(harness):
    upload_id = harness.upload()
    response = harness.client.post(
        "/api/runs",
        json={
            "upload_id": upload_id,
            "name": "Prueba",
            "reference_ids": ["missing-reference"],
            "workflow": "quality_v1",
        },
        headers=harness.headers["admin"],
    )
    assert response.status_code == 422, response.text
    with harness.sessions() as db:
        assert db.scalar(select(Run).where(Run.upload_id == upload_id)) is None


def test_actual_v4_upgrade_adds_quality_without_rewriting_history(harness):
    harness.run()
    engine = harness.sessions.kw["bind"]
    with engine.begin() as connection:
        snapshots_before = connection.execute(text("SELECT id, snapshot FROM revisions ORDER BY id")).all()
        runs_before = connection.execute(
            text("SELECT id, config, source_rows, processed_units FROM runs ORDER BY id")
        ).all()
        connection.execute(text("DROP INDEX ix_location_quality"))
        for column in (
            "quality_code",
            "quality_stage",
            "quality_status",
            "quality_reason",
            "quality_policy_version",
            "quality_history",
        ):
            connection.execute(text(f"ALTER TABLE locations DROP COLUMN {column}"))
        connection.execute(text("ALTER TABLE catalogs DROP COLUMN config"))
        connection.execute(text("DELETE FROM schema_versions WHERE version=5"))
    migrate(engine)
    with engine.begin() as connection:
        assert (
            connection.execute(text("SELECT id, snapshot FROM revisions ORDER BY id")).all()
            == snapshots_before
        )
        assert (
            connection.execute(
                text("SELECT id, config, source_rows, processed_units FROM runs ORDER BY id")
            ).all()
            == runs_before
        )
        rows = connection.execute(
            text("SELECT quality_code, quality_stage, quality_status, quality_history FROM locations")
        ).all()
        assert rows and all(tuple(row) == (None, None, None, "[]") for row in rows)
        connection.execute(
            text(
                "UPDATE locations SET quality_code=2, quality_stage='door', quality_status='review', quality_history='[{\"marker\":\"preserve\"}]'"
            )
        )
        changed = connection.execute(
            text(
                "SELECT id, quality_code, quality_stage, quality_status, quality_history FROM locations ORDER BY id"
            )
        ).all()
    migrate(engine)
    with engine.connect() as connection:
        assert (
            connection.execute(
                text(
                    "SELECT id, quality_code, quality_stage, quality_status, quality_history FROM locations ORDER BY id"
                )
            ).all()
            == changed
        )
        assert connection.scalar(text("SELECT count(*) FROM schema_versions WHERE version=5")) == 1
