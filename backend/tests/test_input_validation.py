"""Input validation and explicit exclusion never discard source rows or invent a location."""

import csv
import io

import pytest
from openpyxl import Workbook
from sqlalchemy import func, select

from geopol.domain.normalization import normalize_record
from geopol.domain.quality import flag10_reason, location_quality_flag, resolve_quality_stage
from geopol.models import Location, Revision, Run, SourceRow
from test_api import harness as harness
from test_export_xlsx import create, download, label, records
from test_quality_flow import advance, catalog, summary


def source_file():
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["ID_DENUNCIA", "UBICACION", "UBIGEO_HECHO", "FLAG", "latitud", "longitud", "persona"])
    rows = [
        ["EXPLICIT", "AV LAS FLORES 123", "150101", 10, None, None, "Sintética A"],
        ["EXPLICIT", "AV LAS FLORES 123", "150101", 10, None, None, "Sintética B"],
        ["EMPTY", None, None, None, None, None, "Sintética C"],
        ["INVALID", None, None, None, "999", "-77", "Sintética D"],
        ["TERRITORY", None, "150101", None, None, None, "Sintética E"],
        ["UNMATCHED", "AV SIN REFERENCIA 999", "150101", None, None, None, "Sintética F"],
        ["DECLARED_ONE", None, None, 1, None, None, "Sintética G"],
        ["EXPLICIT", "AV LAS FLORES 123", "150101", None, None, None, "Sintética H"],
    ]
    for row in rows:
        sheet.append(row)
    buffer = io.BytesIO()
    workbook.save(buffer)
    workbook.close()
    return buffer.getvalue()


@pytest.mark.parametrize(
    "raw",
    [
        {"UBICACION": "Dirección desconocida"},
        {"UBICACION": "", "UBIGEO": "150101"},
        {"UBICACION": "", "latitud": "999"},
        {"UBICACION": "", "nombre_via": "", "REFERENCIA": "Frente al mercado"},
        {"UBICACION": "", "lat_hecho": "-12"},
        {"UBICACION": "", "DEPARTAMENTO": "LIMA"},
        {"UBICACION": "", "DIRECCION": "CALLE SINTETICA 10"},
        {"UBICACION": "", "FLAG": 1},
        {"UBICACION": "", "FLAG": 3},
        {"id_denuncia": "SYN-NO-CONTRACT"},
        {"UBICACION": "NULL"},
    ],
)
def test_flag10_inference_never_erases_partial_invalid_or_unknown_input(raw):
    assert flag10_reason(normalize_record(raw)) is None


def test_explicit_flag_and_empty_only_rule_keep_traceable_source():
    source = normalize_record({"UBICACION": "AV LAS FLORES 123", "UBIGEO": "150101", "FLAG": 10})
    assert location_quality_flag(source) == {
        "quality_flag": 10,
        "quality_flag_reason": "FLAG_10_DECLARADO_EN_ORIGEN",
    }
    assert source["source_quality_flag_original"] == 10
    assert source["source_quality_flag_column"] == "FLAG"
    resolved = resolve_quality_stage(source, [], reference_available=False, stage="door")
    assert resolved["resolution"] == "EXCLUIDO_FLAG_10"
    assert resolved["quality_stage"] is None
    empty = normalize_record({"ID_DENUNCIA": "SYN-EMPTY", "UBICACION": "", "UBIGEO": None})
    assert flag10_reason(empty) == "FLAG_10_SIN_DATOS_DE_UBICACION"
    empty["warnings"].append("FILA_ORIGEN_CON_INCIDENCIA")
    assert flag10_reason(empty) is None


def test_streaming_validation_reports_flags_without_writing_rows(harness):
    upload = harness.upload(source_file(), "DATACRIM_25092026.xlsx")
    headers = harness.headers["admin"]
    report = harness.client.post(f"/api/uploads/{upload}/validation", json={}, headers=headers)
    assert report.status_code == 200, report.text
    data = report.json()
    assert data["filename"]["valid"] is True
    assert data["filename"]["date"] == "2026-09-25"
    assert data["columns"]["mapping"]["source_quality_flag"] == "FLAG"
    assert data["flag_column_present"] is True
    assert (data["total_rows"], data["flag10_existing"], data["flag10_autoeligible"]) == (8, 2, 1)
    assert data["ready"] is True
    with harness.sessions() as db:
        assert db.scalar(select(func.count()).select_from(SourceRow)) == 0
        assert db.scalar(select(func.count()).select_from(Run)) == 0
    assert (
        harness.client.post(
            f"/api/uploads/{upload}/validation",
            json={"mapping": {"location_original": "NO_EXISTE"}},
            headers=headers,
        ).status_code
        == 422
    )
    assert (
        harness.client.post(
            f"/api/uploads/{upload}/validation", json={}, headers=harness.headers["reviewer"]
        ).status_code
        == 403
    )


def test_nonstandard_filename_missing_flag_and_csv_are_advisory(harness):
    upload = harness.upload(b"id_denuncia;otro_nombre;UBIGEO\nSYN-1;AV DEMO 10;150101\n", "Datos.csv")
    report = harness.client.post(
        f"/api/uploads/{upload}/validation",
        json={"mapping": {"location_original": "otro_nombre"}, "delimiter": ";"},
        headers=harness.headers["admin"],
    ).json()
    assert report["ready"] is True
    assert report["filename"]["valid"] is False
    assert report["flag_column_present"] is False
    assert report["columns"]["mapping"]["location_original"] == "otro_nombre"
    assert report["total_rows"] == 1
    empty = harness.upload(b"ID_DENUNCIA\nSYN-1\n", "sin-ubicacion.csv")
    invalid = harness.client.post(
        f"/api/uploads/{empty}/validation", json={}, headers=harness.headers["admin"]
    ).json()
    assert invalid["ready"] is False
    assert invalid["columns"]["missing"] == ["Datos de ubicación"]
    assert invalid["flag10_autoeligible"] == 0


@pytest.mark.parametrize("workflow", ["legacy", "quality_v1"])
def test_exclusion_survives_stages_reprocess_and_export_with_original_cardinality(harness, workflow):
    upload = harness.upload(source_file(), "DATACRIM_25092026.xlsx")
    response = harness.client.post(
        "/api/runs",
        json={
            "upload_id": upload,
            "name": "Flags sintéticos",
            "workflow": workflow,
            "reference_id": catalog(harness),
        },
        headers=harness.headers["admin"],
    )
    assert response.status_code == 201, response.text
    run_id = response.json()["id"]
    assert harness.worker.work_once()
    results = harness.results(run_id)
    excluded = [item for item in results if item["quality_flag"] == 10]
    assert len(results) == 7 and len(excluded) == 2
    assert sum(item["source_row_count"] for item in excluded) == 3
    assert {item["resolution"] for item in excluded} == {"EXCLUIDO_FLAG_10"}
    assert all(item["latitude"] is None and item["geometry"] is None for item in excluded)
    assert all(item["review_state"] == "excluded" and item["review_status"] == "CLOSED" for item in excluded)
    assert {item["complaint_id"] for item in excluded} == {"EXPLICIT", "EMPTY"}
    declared = next(item for item in results if item["complaint_id"] == "DECLARED_ONE")
    corrected = harness.decide(declared, "address_only", address="AV LAS FLORES 123")
    assert corrected.status_code == 200, corrected.text
    assert corrected.json()["source_quality_flag"] == 1
    assert corrected.json()["source_quality_flag_original"] == 1
    detail = harness.client.get(f"/api/results/{excluded[0]['id']}", headers=harness.headers["admin"]).json()
    assert detail["candidates"] == [] and len(detail["attempts"]) == 1
    assert detail["attempts"][0]["method"] == "VALIDACION_ENTRADA"
    queue = harness.client.get(
        f"/api/review?run_id={run_id}&quality_flag=10", headers=harness.headers["admin"]
    )
    assert queue.status_code == 200 and queue.json()["total"] == 0
    assert (
        harness.client.post(
            f"/api/results/{excluded[0]['id']}/claim", headers=harness.headers["reviewer"]
        ).status_code
        == 409
    )
    filtered = harness.client.get(
        f"/api/runs/{run_id}/results?quality_flag=10&review_state=excluded", headers=harness.headers["admin"]
    )
    assert filtered.status_code == 200 and filtered.json()["total"] == 2
    if workflow == "quality_v1":
        report = summary(harness, run_id)
        assert report["totals"]["excluded"] == 2
        flag = next(item for item in report["flags"] if item["flag"] == 10)
        assert flag["excluded"] == 2 and flag["source_rows"] == 3
        before = {item["id"]: item for item in excluded}
        assert advance(harness, run_id).status_code == 200
        assert harness.worker.work_once()
        assert {item["id"]: item for item in harness.results(run_id) if item["quality_flag"] == 10} == before
    for file_format in ("csv", "xlsx"):
        export = create(harness, run_id, profile="source_rows", format=file_format, quality_flag=10)
        assert harness.worker.work_once()
        if file_format == "csv":
            content = harness.client.get(
                f"/api/exports/{export['id']}/download", headers=harness.headers["admin"]
            ).content
            rows = list(csv.DictReader(io.StringIO(content.decode("utf-8-sig"))))
            assert len(rows) == 3
            assert {row["GEOPOL_quality_flag"] for row in rows} == {"10"}
            assert [row["FLAG"] for row in rows] == ["10", "10", ""]
            assert [row["GEOPOL_source_quality_flag"] for row in rows] == ["10", "10", ""]
        else:
            workbook, info, manifest = download(harness, export["id"])
            try:
                assert info["row_count"] == 3 and manifest["schema_version"] == 6
                rows = records(workbook, manifest)
                assert {row[label(manifest, "quality_flag")] for row in rows} == {10}
                assert len(records(workbook, manifest, "Datos originales")) == 3
            finally:
                workbook.close()
    reprocess = harness.client.post(
        f"/api/runs/{run_id}/reprocess", json={}, headers=harness.headers["admin"]
    )
    assert reprocess.status_code == 201, reprocess.text
    assert harness.worker.work_once()
    with harness.sessions() as db:
        child = db.get(Run, reprocess.json()["id"])
        assert (child.source_rows, child.location_units, child.processed_units) == (8, 7, 7)
        assert db.scalar(select(func.count()).select_from(SourceRow).where(SourceRow.run_id == child.id)) == 8
        rows = list(
            db.scalars(select(Location).where(Location.run_id == child.id, Location.quality_flag == 10))
        )
        assert len(rows) == 2
        snapshot = db.scalar(select(Revision).where(Revision.location_id == rows[0].id)).snapshot
        assert snapshot["quality_flag"] == 10 and snapshot["review_state"] == "excluded"
