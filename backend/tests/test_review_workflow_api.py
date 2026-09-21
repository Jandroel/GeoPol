"""Synthetic API workflows for review ownership, queue state and run lineage."""

import time

import pytest
from test_api import harness as harness

from geopol.models import Export, Location


def checked(response, status=200):
    assert response.status_code == status, response.text
    return response.json()


def get(harness, path, **params):
    return checked(harness.client.get(path, params=params, headers=harness.headers["reviewer"]))


def catalog(harness, version="1", latitude=-12.04, longitude=-77.03):
    content = (
        "kind,ubigeo,street_type,street_name,door_number,latitude,longitude\n"
        f"door,150101,AVENIDA,DEMOSTRACION,120,{latitude},{longitude}\n"
    ).encode()
    return checked(
        harness.client.post(
            "/api/references",
            headers=harness.headers["admin"],
            data={"name": "Referencia sintética de integración", "version": version, "source": "SINTETICO"},
            files={"file": ("reference.csv", content, "text/csv")},
        ),
        201,
    )["id"]


def test_unresolved_closes_queue_and_explicit_reopen_preserves_history(harness):
    run = harness.run(b"complaint_id,location_original,ubigeo\nONLY,LUGAR DESCONOCIDO,150101\n")
    item = harness.results(run["id"])[0]
    assert item["review_status"] == "OPEN"
    assert get(harness, "/api/review", run_id=run["id"])["total"] == 1

    closed = checked(harness.decide(item, "unresolved"))
    assert closed["resolution"] == "SIN_COINCIDENCIA"
    assert closed["manual"] is True
    assert closed["review_status"] == "CLOSED"
    assert closed["review_bucket"] == "none"
    assert closed["review_owner"] is closed["review_expires_at"] is None
    assert get(harness, "/api/review", run_id=run["id"])["total"] == 0
    assert get(harness, "/api/review/next", run_id=run["id"])["item"] is None
    assert get(harness, "/api/review", run_id=run["id"], stage="closed")["items"][0]["id"] == item["id"]
    assert get(harness, "/api/review/summary", run_id=run["id"])["closed"] == 1
    export_id = harness.export(run["id"], role="analyst")

    reopened = checked(harness.decide(closed, "reopen"))
    assert reopened["resolution"] == "REVISION_REQUERIDA"
    assert reopened["review_status"] == "OPEN"
    assert reopened["review_bucket"] == "needs_data"
    assert reopened["revision"] == item["revision"] + 2
    assert get(harness, "/api/review", run_id=run["id"])["items"][0]["id"] == item["id"]
    assert get(harness, "/api/review", run_id=run["id"], stage="closed")["total"] == 0
    detail = get(harness, f"/api/results/{item['id']}")
    assert [revision["action"] for revision in detail["history"]] == [
        "reopen",
        "unresolved",
        "automatic_resolution",
    ]
    assert detail["history"][1]["snapshot"]["review_status"] == "CLOSED"
    assert detail["history"][1]["snapshot"]["resolution"] == "SIN_COINCIDENCIA"

    assert harness.worker.work_once()
    exported = harness.download_export(export_id, role="analyst")
    assert len(exported) == 1
    snapshot = exported[0]
    assert snapshot["GEOPOL_review_status"] == "CLOSED"
    assert snapshot["GEOPOL_review_bucket"] == "none"
    assert snapshot["GEOPOL_resolution"] == "SIN_COINCIDENCIA"
    assert snapshot["GEOPOL_latitude"] == snapshot["GEOPOL_longitude"] == ""
    assert int(snapshot["GEOPOL_revision"]) == closed["revision"]
    current = get(harness, f"/api/results/{item['id']}")
    assert current["review_status"] == "OPEN"
    assert current["resolution"] == "REVISION_REQUERIDA"
    assert current["revision"] == reopened["revision"]


def test_pending_legacy_export_keeps_its_original_csv_contract(harness):
    run = harness.run()
    export_id = harness.export(run["id"])
    with harness.sessions() as db:
        item = db.get(Export, export_id)
        item.manifest = {**item.manifest, "schema_version": 1}
        db.commit()
    assert harness.worker.work_once()
    exported = harness.download_export(export_id)
    assert len(exported) == run["location_units"]
    assert "GEOPOL_review_status" not in exported[0]
    assert "GEOPOL_review_bucket" not in exported[0]


def test_summary_and_queue_filters_match_worker_classification_with_run_isolation(harness):
    reference_id = catalog(harness)
    run = harness.run(
        b"complaint_id,location_original,ubigeo\n"
        b"FILTER-ACTION,AV DEMOSTRACIOZ 120,150101\n"
        b"FILTER-REFERENCE,AV OTRA CUADRA 3,150101\n"
        b"FILTER-DATA,LUGAR DESCONOCIDO,150101\n"
        b"FILTER-CLOSED,AV DEMOSTRACION 120,150101\n",
        reference_id=reference_id,
    )
    other = harness.run()
    summary = get(harness, "/api/review/summary", run_id=run["id"])
    assert summary == {
        "open": {"actionable": 1, "needs_reference": 1, "needs_data": 1, "technical": 0},
        "closed": 1,
        "total": 4,
    }
    assert get(harness, "/api/review/summary")["total"] == summary["total"] + other["location_units"]
    opened = get(harness, "/api/review", run_id=run["id"])
    assert [item["complaint_id"] for item in opened["items"]] == [
        "FILTER-ACTION",
        "FILTER-DATA",
        "FILTER-REFERENCE",
    ]
    for bucket, complaint_id in (
        ("actionable", "FILTER-ACTION"),
        ("needs_reference", "FILTER-REFERENCE"),
        ("needs_data", "FILTER-DATA"),
    ):
        filtered = get(harness, "/api/review", run_id=run["id"], bucket=bucket)
        assert filtered["total"] == 1
        assert filtered["items"][0]["complaint_id"] == complaint_id
    assert get(harness, "/api/review", run_id=run["id"], bucket="technical")["total"] == 0
    assert get(harness, "/api/review", run_id=run["id"], stage="all")["total"] == 4
    assert (
        get(harness, "/api/review", run_id=run["id"], stage="closed")["items"][0]["complaint_id"]
        == "FILTER-CLOSED"
    )
    assert get(harness, "/api/review/summary", run_id=run["id"], q="FILTER-ACTION")["total"] == 1
    assert get(harness, "/api/review", run_id=other["id"], q="FILTER")["total"] == 0
    for invalid in ({"bucket": "unknown"}, {"stage": "unknown"}):
        checked(harness.client.get("/api/review", params=invalid, headers=harness.headers["reviewer"]), 422)
    checked(
        harness.client.get(
            "/api/review/summary", params={"run_id": "missing"}, headers=harness.headers["reviewer"]
        ),
        404,
    )


def test_release_requires_own_reservation_and_reviewer_role(harness):
    item = harness.results(harness.run()["id"])[0]
    path = f"/api/results/{item['id']}"
    claimed = checked(harness.client.post(f"{path}/claim", headers=harness.headers["reviewer"]))
    assert claimed["review_owner"] is not None
    checked(harness.client.post(f"{path}/release", headers=harness.headers["admin"]), 409)
    for role in ("operator", "analyst"):
        checked(harness.client.post(f"{path}/release", headers=harness.headers[role]), 403)
    assert get(harness, path)["review_owner"] == claimed["review_owner"]
    released = checked(harness.client.post(f"{path}/release", headers=harness.headers["reviewer"]))
    assert released["review_owner"] is released["review_expires_at"] is None
    assert released["revision"] == item["revision"]
    assert checked(harness.client.post(f"{path}/release", headers=harness.headers["reviewer"])) == released
    assert (
        checked(harness.client.post(f"{path}/claim", headers=harness.headers["admin"]))["review_owner"]
        != claimed["review_owner"]
    )


def test_next_excludes_current_and_others_reservations_without_claiming(harness):
    run = harness.run(
        b"complaint_id,location_original,ubigeo\n"
        b"NEXT-A,LUGAR A DESCONOCIDO,150101\n"
        b"NEXT-B,LUGAR B DESCONOCIDO,150101\n"
        b"NEXT-C,LUGAR C DESCONOCIDO,150101\n"
    )
    items = {item["complaint_id"]: item for item in harness.results(run["id"])}
    current, reserved, available = (items[name] for name in ("NEXT-A", "NEXT-B", "NEXT-C"))
    checked(harness.client.post(f"/api/results/{current['id']}/claim", headers=harness.headers["reviewer"]))
    reservation = checked(
        harness.client.post(f"/api/results/{reserved['id']}/claim", headers=harness.headers["admin"])
    )
    for _ in range(2):
        result = get(harness, "/api/review/next", run_id=run["id"], exclude_id=current["id"])["item"]
        assert result["id"] == available["id"]
        assert result["review_owner"] is result["review_expires_at"] is None
        assert result["revision"] == available["revision"]
    assert get(harness, f"/api/results/{available['id']}")["review_owner"] is None
    assert get(harness, "/api/review/next", run_id=run["id"], q="NEXT-B")["item"] is None
    assert get(harness, "/api/review/next", run_id=run["id"], stage="closed")["item"] is None

    with harness.sessions() as db:
        db.get(Location, reserved["id"]).review_expires_at = time.time() - 1
        db.commit()
    expired = get(harness, "/api/review/next", run_id=run["id"], q="NEXT-B")["item"]
    assert expired["id"] == reserved["id"]
    assert expired["review_owner"] == reservation["review_owner"]


@pytest.mark.parametrize("selection", ["new", "null", "omitted_field", "omitted_body"])
def test_reprocess_selects_catalog_and_supersedes_only_after_completion(harness, selection):
    original_reference = catalog(harness)
    parent = harness.run(reference_id=original_reference)
    baseline = get(harness, "/api/dashboard")
    assert baseline["runs"] == 1
    assert baseline["source_rows"] == 3
    assert baseline["location_units"] == 2
    assert baseline["accepted"] == baseline["unresolved"] == baseline["review_open"] == 1
    assert baseline["review_required"] == baseline["review_actionable"] == 0
    previous = {item["complaint_id"]: item for item in harness.results(parent["id"])}
    pending = previous["DEMO-B"]
    history_before = get(harness, f"/api/results/{pending['id']}")["history"]
    arguments = {}
    expected_reference = original_reference
    if selection == "new":
        expected_reference = catalog(harness, version="2", latitude=-12.06, longitude=-77.04)
        arguments["json"] = {"reference_id": expected_reference}
    elif selection == "null":
        expected_reference = None
        arguments["json"] = {"reference_id": None}
    elif selection == "omitted_field":
        arguments["json"] = {}
    child = checked(
        harness.client.post(
            f"/api/runs/{parent['id']}/reprocess", headers=harness.headers["admin"], **arguments
        ),
        201,
    )
    assert child["parent_run_id"] == parent["id"]
    assert child["upload_id"] == parent["upload_id"]
    assert child["reference_id"] == expected_reference
    assert child["status"] == "QUEUED"
    during_reprocess = get(harness, "/api/dashboard")
    assert during_reprocess["runs"] == 2
    for metric in (
        "source_rows",
        "location_units",
        "accepted",
        "unresolved",
        "review_required",
        "review_open",
        "review_actionable",
    ):
        assert during_reprocess[metric] == baseline[metric]
    assert get(harness, f"/api/runs/{parent['id']}")["superseded_by"] is None
    assert get(harness, "/api/review", run_id=parent["id"])["total"] == 1
    assert get(harness, "/api/review", run_id=child["id"])["total"] == 0
    checked(harness.client.post(f"/api/runs/{parent['id']}/reprocess", headers=harness.headers["admin"]), 409)
    checked(harness.client.post(f"/api/runs/{child['id']}/reprocess", headers=harness.headers["admin"]), 409)
    checked(harness.client.post(f"/api/results/{pending['id']}/claim", headers=harness.headers["reviewer"]))

    assert harness.worker.work_once()
    finished = get(harness, f"/api/runs/{child['id']}")
    assert finished["status"] == "COMPLETED"
    assert finished["source_rows"] == parent["source_rows"] == 3
    assert finished["location_units"] == parent["location_units"] == 2
    assert get(harness, f"/api/runs/{parent['id']}")["superseded_by"] == child["id"]
    current = {item["complaint_id"]: item for item in harness.results(child["id"])}
    if selection == "null":
        assert current["DEMO-A"]["resolution"] == "NO_EVALUABLE_REFERENCIA"
        assert current["DEMO-A"]["latitude"] is None
    else:
        assert current["DEMO-A"]["resolution"] == "ACEPTADO_AUTOMATICO"
        assert current["DEMO-A"]["latitude"] == (-12.06 if selection == "new" else -12.04)
    dashboard = get(harness, "/api/dashboard")
    assert dashboard["runs"] == 2
    assert dashboard["source_rows"] == baseline["source_rows"]
    assert dashboard["location_units"] == baseline["location_units"]
    assert dashboard["accepted"] == (0 if selection == "null" else 1)
    assert dashboard["unresolved"] == dashboard["review_open"] == (2 if selection == "null" else 1)
    assert dashboard["review_required"] == dashboard["review_actionable"] == 0

    assert get(harness, "/api/review", run_id=parent["id"], stage="all")["total"] == 0
    assert get(harness, "/api/review/summary", run_id=parent["id"])["total"] == 0
    assert (
        get(harness, "/api/review", run_id=parent["id"], stage="all", include_superseded=True)["total"] == 2
    )
    assert get(harness, "/api/review/next", run_id=parent["id"], include_superseded=True)["item"] is None
    assert get(harness, f"/api/results/{pending['id']}")["history"] == history_before
    assert len(harness.results(parent["id"])) == 2
    checked(
        harness.client.post(f"/api/results/{pending['id']}/claim", headers=harness.headers["reviewer"]), 409
    )
    checked(
        harness.client.post(
            f"/api/results/{pending['id']}/decisions",
            headers=harness.headers["reviewer"],
            json={
                "expected_revision": pending["revision"],
                "action": "unresolved",
                "reason": "No modificar historia sintética",
            },
        ),
        409,
    )
    checked(harness.client.post(f"/api/runs/{parent['id']}/reprocess", headers=harness.headers["admin"]), 409)


@pytest.mark.parametrize("outcome", ["FAILED", "CANCELLED"])
def test_failed_or_cancelled_reprocess_does_not_hide_parent(harness, monkeypatch, outcome):
    parent = harness.run()
    child = checked(
        harness.client.post(f"/api/runs/{parent['id']}/reprocess", headers=harness.headers["admin"]), 201
    )
    if outcome == "CANCELLED":
        checked(harness.client.post(f"/api/runs/{child['id']}/cancel", headers=harness.headers["admin"]))
    else:

        def fail_ingestion(*args, **kwargs):
            raise OSError("Synthetic controlled failure before ingestion")

        monkeypatch.setattr(harness.worker, "ingest_batch", fail_ingestion)
    assert harness.worker.work_once()
    assert get(harness, f"/api/runs/{child['id']}")["status"] == outcome
    assert get(harness, f"/api/runs/{parent['id']}")["superseded_by"] is None
    assert get(harness, "/api/review", run_id=parent["id"])["total"] == 2
    old_item = harness.results(parent["id"])[0]
    checked(harness.client.post(f"/api/results/{old_item['id']}/claim", headers=harness.headers["reviewer"]))


def test_failed_child_cannot_retry_while_sibling_runs_or_after_parent_is_superseded(harness, monkeypatch):
    parent = harness.run()
    child = checked(
        harness.client.post(f"/api/runs/{parent['id']}/reprocess", headers=harness.headers["admin"]), 201
    )
    original_ingest = harness.worker.ingest_batch

    def fail_after_checkpoint(*args, **kwargs):
        original_ingest(*args, **kwargs)
        raise OSError("Synthetic failure after committed ingestion checkpoint")

    with monkeypatch.context() as patch:
        patch.setattr(harness.worker, "ingest_batch", fail_after_checkpoint)
        assert harness.worker.work_once()
    failed = get(harness, f"/api/runs/{child['id']}")
    assert failed["status"] == "FAILED"
    assert failed["source_rows"] == 2
    assert get(harness, f"/api/runs/{parent['id']}")["superseded_by"] is None
    dashboard = get(harness, "/api/dashboard")
    assert dashboard["runs"] == 2
    assert dashboard["source_rows"] == parent["source_rows"] == 3
    assert dashboard["location_units"] == parent["location_units"] == 2

    sibling = checked(
        harness.client.post(f"/api/runs/{parent['id']}/reprocess", headers=harness.headers["admin"]), 201
    )
    assert sibling["parent_run_id"] == parent["id"]
    assert sibling["status"] == "QUEUED"
    retry_path = f"/api/runs/{child['id']}/retry"
    checked(harness.client.post(retry_path, headers=harness.headers["admin"]), 409)
    assert get(harness, f"/api/runs/{child['id']}")["status"] == "FAILED"
    assert get(harness, f"/api/runs/{parent['id']}")["superseded_by"] is None

    assert harness.worker.work_once()
    assert get(harness, f"/api/runs/{sibling['id']}")["status"] == "COMPLETED"
    assert get(harness, f"/api/runs/{parent['id']}")["superseded_by"] == sibling["id"]
    checked(harness.client.post(retry_path, headers=harness.headers["admin"]), 409)
    assert get(harness, f"/api/runs/{child['id']}")["status"] == "FAILED"
    assert not harness.worker.work_once()
    final = get(harness, "/api/dashboard")
    assert final["runs"] == 3
    assert final["source_rows"] == 3
    assert final["location_units"] == 2
    assert final["accepted"] == final["review_required"] == final["review_actionable"] == 0
    assert final["unresolved"] == final["review_open"] == 2
