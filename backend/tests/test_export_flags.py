"""Flag describes address format; export review state remains a separate field."""

import csv
import io

import pytest

from geopol.models import Export
from test_api import harness as harness
from test_export_xlsx import create, download, label, records
from test_quality_flow import start


def test_csv_flag_and_review_state_filter_preserves_source_rows(harness):
    run_id = start(harness)
    export = create(
        harness, run_id, profile="source_rows", format="csv", quality_flag=1, review_state="automatic"
    )
    assert harness.worker.work_once()
    manifest = harness.client.get(
        f"/api/exports/{export['id']}/manifest", headers=harness.headers["admin"]
    ).json()
    response = harness.client.get(f"/api/exports/{export['id']}/download", headers=harness.headers["admin"])
    assert response.status_code == 200
    reader = csv.DictReader(io.StringIO(response.content.decode("utf-8-sig")))
    rows = list(reader)
    assert manifest["schema_version"] == 5
    assert len(rows) == manifest["expected_rows"] == manifest["row_count"] == 2
    assert {row["GEOPOL_quality_flag"] for row in rows} == {"1"}
    assert {row["GEOPOL_review_state"] for row in rows} == {"automatic"}
    assert [row["persona_sintetica"] for row in rows] == ["Persona A", "Persona B"]
    assert "GEOPOL_quality_flag_reason" in reader.fieldnames
    assert "GEOPOL_quality_code" not in reader.fieldnames
    assert "GEOPOL_quality_status" not in reader.fieldnames


def test_flag_two_exports_incomplete_geography_without_claiming_validation(harness):
    source = (
        "complaint_id,location_original,ubigeo,urban_core,street_name,jurisdiction_name\n"
        "NUCLEO,AAHH LOS PINOS,150101,LOS PINOS,,\n"
        "NUCLEO,AAHH LOS PINOS,150101,LOS PINOS,,\n"
        "JUR,AV LIBERTAD,150101,,LIBERTAD,COMISARIA DEMO\n"
        "SIN,UBICACION DESCONOCIDA,150101,,,\n"
    ).encode()
    upload_id = harness.upload(source)
    response = harness.client.post(
        "/api/runs",
        json={"upload_id": upload_id, "name": "Flag dos", "workflow": "quality_v1", "reference_id": None},
        headers=harness.headers["admin"],
    )
    assert response.status_code == 201, response.text
    run_id = response.json()["id"]
    assert harness.worker.work_once()
    export = create(harness, run_id, profile="source_rows", quality_flag=2)
    assert harness.worker.work_once()
    workbook, info, manifest = download(harness, export["id"])
    try:
        rows = records(workbook, manifest)
        assert info["row_count"] == manifest["expected_rows"] == 3
        assert {row[label(manifest, "quality_flag")] for row in rows} == {2}
        assert {row[label(manifest, "review_state")] for row in rows} == {"reference_pending"}
        assert all(
            row[label(manifest, "latitude")] is None and row[label(manifest, "longitude")] is None
            for row in rows
        )
        assert label(manifest, "quality_flag_reason") == "Motivo del flag"
        assert label(manifest, "review_state") == "Estado de revisión"
        labels = [column["label"] for column in manifest["workbook"]["columns"]]
        assert len(labels) == len(set(labels))
        assert len(records(workbook, manifest, "Datos originales")) == 3
    finally:
        workbook.close()


def test_review_state_without_flag_is_an_independent_export_filter(harness):
    run_id = start(harness)
    export = create(harness, run_id, review_state="quick_review")
    assert harness.worker.work_once()
    workbook, info, manifest = download(harness, export["id"])
    try:
        rows = records(workbook, manifest)
        assert info["row_count"] == 1
        assert manifest["quality_filter"] == {"flag": None, "review_state": "quick_review", "stage": None}
        assert rows[0][label(manifest, "complaint_id")] == "Q2"
        assert rows[0][label(manifest, "quality_flag")] == 1
    finally:
        workbook.close()


def test_pending_schema_four_keeps_historical_columns(harness):
    run_id = start(harness)
    export = create(harness, run_id, quality_code=1)
    # A persisted pre-change export retains both its contract and snapshot.
    with harness.sessions() as db:
        pending = db.get(Export, export["id"])
        pending.manifest = {**pending.manifest, "schema_version": 4}
        db.commit()
    assert harness.worker.work_once()
    workbook, info, manifest = download(harness, export["id"])
    try:
        assert manifest["schema_version"] == 4
        keys = {column["key"] for column in manifest["workbook"]["columns"]}
        assert {"quality_code", "quality_status"} <= keys
        assert not {"quality_flag", "review_state", "quality_flag_reason"} & keys
        assert records(workbook, manifest)[0][label(manifest, "quality_code")] == 1
        assert info["row_count"] == 1
    finally:
        workbook.close()


@pytest.mark.parametrize("filters", [{"quality_flag": 3}, {"quality_flag": 0}, {"review_state": "review"}])
def test_invalid_flag_or_review_state_filter_is_rejected(harness, filters):
    run_id = start(harness)
    response = harness.client.post(
        f"/api/runs/{run_id}/exports", json={"format": "xlsx", **filters}, headers=harness.headers["admin"]
    )
    assert response.status_code == 422


def test_source_permission_still_applies_to_flag_filtered_export(harness):
    run_id = start(harness)
    response = harness.client.post(
        f"/api/runs/{run_id}/exports",
        json={"format": "xlsx", "profile": "source_rows", "quality_flag": 1, "review_state": "automatic"},
        headers=harness.headers["analyst"],
    )
    assert response.status_code == 403
