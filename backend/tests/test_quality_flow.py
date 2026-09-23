"""End-to-end persistence of quality stages, protected decisions and exports."""

import io
import json

from openpyxl import Workbook

from test_api import harness as harness
from test_export_xlsx import create, download, label, records


def catalog(harness):
    point = {"type": "Point", "coordinates": [-77.1, -12.05]}
    properties = {
        "ubigeo": "150101",
        "kind": "door",
        "street_type": "AVENIDA",
        "street_name": "LAS FLORES",
        "door_number": "123",
    }
    features = [
        {"type": "Feature", "id": "door-one", "properties": properties, "geometry": point},
        {
            "type": "Feature",
            "id": "door-ambiguous-a",
            "properties": {
                **properties,
                "street_type": "CALLE",
                "street_name": "LAS PALMAS",
                "door_number": "50",
            },
            "geometry": point,
        },
        {
            "type": "Feature",
            "id": "door-ambiguous-b",
            "properties": {
                **properties,
                "street_type": "CALLE",
                "street_name": "LAS PALMAS",
                "door_number": "50",
            },
            "geometry": {"type": "Point", "coordinates": [-77.2, -12.05]},
        },
        {
            "type": "Feature",
            "id": "block-five",
            "properties": {
                "kind": "block",
                "ubigeo": "150101",
                "street_type": "AVENIDA",
                "street_name": "INDEPENDENCIA",
                "block_number": "5",
            },
            "geometry": {"type": "LineString", "coordinates": [[-77.2, -12.1], [-77.1, -12.1]]},
        },
        {
            "type": "Feature",
            "id": "boundary-one",
            "properties": {"kind": "boundary", "ubigeo": "150101"},
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[-78, -13], [-76, -13], [-76, -11], [-78, -11], [-78, -13]]],
            },
        },
    ]
    response = harness.client.post(
        "/api/references",
        data={"name": "Calidad sintética", "source": "SINTETICO", "version": "2026-prueba"},
        files={
            "file": (
                "synthetic.geojson",
                json.dumps({"type": "FeatureCollection", "features": features}).encode(),
                "application/geo+json",
            )
        },
        headers=harness.headers["admin"],
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def start(harness):
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["complaint_id", "location_original", "ubigeo", "persona_sintetica"])
    rows = [
        ["Q1", "AV LAS FLORES 123", "150101", "Persona A"],
        ["Q1", "AV LAS FLORES 123", "150101", "Persona B"],
        ["Q2", "AV LAS FLOREZ 123", "150101", "Persona C"],
        ["Q3", "CALLE LAS PALMAS 50", "150101", "Persona D"],
        ["Q4", "AV INDEPENDENCIA CUADRA 5", "150101", "Persona E"],
        ["NO", "AV SIN REFERENCIA 999", "150101", "Persona F"],
    ]
    for row in rows:
        sheet.append(row)
    data = io.BytesIO()
    workbook.save(data)
    upload_id = harness.upload(data.getvalue(), "synthetic-quality.xlsx")
    reference_id = catalog(harness)
    response = harness.client.post(
        "/api/runs",
        json={
            "upload_id": upload_id,
            "name": "Calidad de prueba",
            "reference_id": reference_id,
            "workflow": "quality_v1",
        },
        headers=harness.headers["admin"],
    )
    assert response.status_code == 201, response.text
    run_id = response.json()["id"]
    assert harness.worker.work_once()
    response = harness.client.get(f"/api/runs/{run_id}", headers=harness.headers["admin"])
    assert response.json()["status"] == "COMPLETED", response.text
    return run_id


def by_complaint(harness, run_id):
    return {item["complaint_id"]: item for item in harness.results(run_id)}


def summary(harness, run_id):
    response = harness.client.get(f"/api/runs/{run_id}/quality", headers=harness.headers["admin"])
    assert response.status_code == 200, response.text
    return response.json()


def advance(harness, run_id, stage="block"):
    return harness.client.post(
        f"/api/runs/{run_id}/advance", json={"stage": stage}, headers=harness.headers["admin"]
    )


def test_initial_stage_has_q1_q2_q3_and_correct_row_and_unit_denominators(harness):
    run_id = start(harness)
    results = by_complaint(harness, run_id)
    assert results["Q1"]["quality_code"] == 1
    assert results["Q1"]["quality_status"] == "resolved"
    assert results["Q1"]["source_row_count"] == 2
    assert results["Q2"]["quality_code"] == 2
    assert results["Q2"]["quality_status"] == "review"
    assert results["Q3"]["quality_code"] == 3
    assert results["Q3"]["quality_status"] == "review"
    assert results["Q4"]["quality_status"] == results["NO"]["quality_status"] == "unmatched"
    assert {item["quality_stage"] for item in results.values()} == {"door"}
    report = summary(harness, run_id)
    assert report["totals"]["units"] == 5
    assert report["totals"]["source_rows"] == 6
    assert report["totals"]["resolved"] == 1
    assert report["held_review_units"] == 2
    assert report["eligible_units"] == 2
    assert report["next_stage"] == "block"
    q1 = next(item for item in report["qualities"] if item["code"] == 1)
    assert (q1["units"], q1["source_rows"]) == (1, 2)


def test_advance_only_touches_unmatched_and_rejects_repetition_and_out_of_order(harness):
    run_id = start(harness)
    before = by_complaint(harness, run_id)
    assert advance(harness, run_id, "nucleus").status_code == 409
    response = advance(harness, run_id)
    assert response.status_code == 200, response.text
    assert advance(harness, run_id).status_code == 409
    assert harness.worker.work_once()
    after = by_complaint(harness, run_id)
    for complaint in ("Q1", "Q2", "Q3"):
        assert after[complaint] == before[complaint]
    assert after["Q4"]["quality_code"] == 4
    assert after["Q4"]["quality_status"] == "resolved"
    assert after["Q4"]["quality_stage"] == "block"
    assert after["Q4"]["revision"] == before["Q4"]["revision"] + 1
    assert after["Q4"]["geometry"]["type"] == "LineString"
    assert after["Q4"]["latitude"] is after["Q4"]["longitude"] is None
    assert after["NO"]["quality_stage"] == "block"
    assert after["NO"]["quality_status"] == "unmatched"
    assert advance(harness, run_id).status_code == 409
    report = summary(harness, run_id)
    assert report["totals"]["resolved"] == 2
    assert report["next_stage"] == "intersection"
    stages = {item["key"]: item for item in report["stages"]}
    assert stages["door"]["units"] == 5
    assert stages["block"]["units"] == 2
    assert stages["block"]["resolved"] == 1


def test_quick_manual_acceptance_keeps_q2_and_is_protected_from_advance(harness):
    run_id = start(harness)
    q2 = by_complaint(harness, run_id)["Q2"]
    detail = harness.client.get(f"/api/results/{q2['id']}", headers=harness.headers["admin"]).json()
    response = harness.decide(q2, "accept_candidate", candidate_id=detail["candidates"][0]["id"])
    assert response.status_code == 200, response.text
    accepted = response.json()
    assert accepted["quality_code"] == 2
    assert accepted["quality_status"] == "resolved"
    assert accepted["resolution"] == "ACEPTADO_MANUAL"
    assert advance(harness, run_id).status_code == 200
    assert harness.worker.work_once()
    assert by_complaint(harness, run_id)["Q2"] == accepted


def test_filtered_excel_preserves_source_cardinality_and_cumulative_quality(harness):
    run_id = start(harness)
    filtered = create(harness, run_id, profile="source_rows", quality_flag=1, review_state="automatic")
    assert harness.worker.work_once()
    workbook, info, manifest = download(harness, filtered["id"])
    assert manifest["schema_version"] == 5
    assert manifest["quality_filter"] == {"flag": 1, "review_state": "automatic", "stage": None}
    assert info["row_count"] == manifest["expected_rows"] == 2
    source = records(workbook, manifest, "Datos originales")
    assert [row["persona_sintetica"] for row in source] == ["Persona A", "Persona B"]
    exported = records(workbook, manifest)
    assert [row[label(manifest, "quality_flag")] for row in exported] == [1, 1]
    assert [row[label(manifest, "review_state")] for row in exported] == ["automatic", "automatic"]
    assert all(row[label(manifest, "quality_stage")] == "door" for row in exported)
    workbook.close()
    assert advance(harness, run_id).status_code == 200
    assert harness.worker.work_once()
    accumulated = create(harness, run_id)
    assert harness.worker.work_once()
    workbook, info, manifest = download(harness, accumulated["id"])
    assert info["row_count"] == 5
    assert manifest["quality_filter"] is None
    accumulated_rows = records(workbook, manifest)
    assert {
        row[label(manifest, "complaint_id")]: row[label(manifest, "quality_flag")] for row in accumulated_rows
    } == {"Q1": 1, "Q2": 1, "Q3": 1, "Q4": 1, "NO": None}
    assert {row[label(manifest, "review_state")] for row in records(workbook, manifest)} == {
        "automatic",
        "quick_review",
        "detailed_review",
        "unmatched",
    }
    assert label(manifest, "quality_flag") == "Flag de calidad"
    assert not {"quality_code", "quality_status"} & {
        column["key"] for column in manifest["workbook"]["columns"]
    }
    workbook.close()


def test_quality_export_snapshot_remains_unchanged_after_manual_resolution(harness):
    run_id = start(harness)
    export = create(harness, run_id, quality_flag=1, review_state="quick_review")
    q2 = by_complaint(harness, run_id)["Q2"]
    detail = harness.client.get(f"/api/results/{q2['id']}", headers=harness.headers["admin"]).json()
    accepted = harness.decide(q2, "accept_candidate", candidate_id=detail["candidates"][0]["id"])
    assert accepted.status_code == 200
    assert harness.worker.work_once()
    workbook, info, manifest = download(harness, export["id"])
    assert info["row_count"] == 1
    row = records(workbook, manifest)[0]
    assert row[label(manifest, "quality_flag")] == 1
    assert row[label(manifest, "review_state")] == "quick_review"
    assert row[label(manifest, "revision")] == q2["revision"]
    assert row[label(manifest, "latitude")] is None
    workbook.close()


def test_analyst_can_filter_results_but_cannot_advance(harness):
    run_id = start(harness)
    response = harness.client.get(
        f"/api/runs/{run_id}/results?quality_code=2", headers=harness.headers["analyst"]
    )
    assert response.status_code == 200, response.text
    assert [item["complaint_id"] for item in response.json()["items"]] == ["Q2"]
    forbidden = harness.client.post(
        f"/api/runs/{run_id}/advance", json={"stage": "block"}, headers=harness.headers["analyst"]
    )
    assert forbidden.status_code == 403
