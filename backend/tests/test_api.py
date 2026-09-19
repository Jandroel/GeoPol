"""Integration contracts: isolation, durable jobs, review and snapshot exports."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import shutil
import sqlite3
import time
from contextlib import closing
from dataclasses import dataclass

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from geopol.config import settings
from geopol.db import get_db, make_engine
from geopol.migrations import migrate
from geopol.models import Job, Location, LoginSession, Revision, Run, SourceRow, User
from geopol.security import password_hash, token_hash


PASSWORD = "synthetic-test-password-only"
CSV_DATA = (
    "complaint_id,location_original,ubigeo,person_name\n"
    "DEMO-A,AV. DEMOSTRACION 120,150101,Persona sintetica A\n"
    "DEMO-A,AV. DEMOSTRACION 120,150101,Persona sintetica B\n"
    "DEMO-B,UBICACION DESCONOCIDA,150101,=1+1\n"
).encode()


@dataclass
class Harness:
    client: TestClient
    sessions: object
    worker: object
    headers: dict

    def upload(self, data=CSV_DATA, filename="synthetic.csv"):
        response = self.client.post(
            "/api/uploads", json={"filename": filename, "size": len(data)}, headers=self.headers["admin"]
        )
        assert response.status_code in (200, 201), response.text
        identifier = response.json()["id"]
        response = self.client.patch(
            f"/api/uploads/{identifier}",
            content=data,
            headers={
                **self.headers["admin"],
                "Upload-Offset": "0",
                "Content-Type": "application/octet-stream",
            },
        )
        assert response.status_code == 200, response.text
        response = self.client.post(f"/api/uploads/{identifier}/complete", headers=self.headers["admin"])
        assert response.status_code == 200, response.text
        assert response.json()["sha256"] == hashlib.sha256(data).hexdigest()
        return identifier

    def run(self, data=CSV_DATA, reference_id=None):
        upload_id = self.upload(data)
        payload = {"upload_id": upload_id, "name": "Prueba sintética", "crs": "EPSG:4326"}
        if reference_id:
            payload["reference_id"] = reference_id
        response = self.client.post("/api/runs", json=payload, headers=self.headers["admin"])
        assert response.status_code in (200, 201, 202), response.text
        identifier = response.json()["id"]
        assert self.worker.work_once()
        response = self.client.get(f"/api/runs/{identifier}", headers=self.headers["admin"])
        assert response.json()["status"] in {"COMPLETED", "COMPLETED_WITH_ISSUES"}, response.text
        return response.json()

    def results(self, run_id, role="admin"):
        response = self.client.get(f"/api/runs/{run_id}/results", headers=self.headers[role])
        assert response.status_code == 200, response.text
        return response.json()["items"]

    def decide(self, result, action, **fields):
        response = self.client.post(f"/api/results/{result['id']}/claim", headers=self.headers["reviewer"])
        assert response.status_code == 200, response.text
        return self.client.post(
            f"/api/results/{result['id']}/decisions",
            json={
                "expected_revision": result["revision"],
                "action": action,
                "reason": "Decisión sobre evidencia sintética para prueba",
                **fields,
            },
            headers=self.headers["reviewer"],
        )

    def export(self, run_id, profile="locations", role="admin"):
        response = self.client.post(
            f"/api/runs/{run_id}/exports",
            json={"profile": profile, "safe_spreadsheet": True},
            headers=self.headers[role],
        )
        assert response.status_code in (200, 201, 202), response.text
        return response.json()["id"]

    def download_export(self, export_id, role="admin"):
        response = self.client.get(f"/api/exports/{export_id}", headers=self.headers[role])
        assert response.status_code == 200, response.text
        assert response.json()["status"] == "COMPLETED", response.text
        download = self.client.get(f"/api/exports/{export_id}/download", headers=self.headers[role])
        assert download.status_code == 200, download.text
        assert hashlib.sha256(download.content).hexdigest() == response.json()["sha256"]
        return list(csv.DictReader(io.StringIO(download.content.decode("utf-8-sig"))))


@pytest.fixture
def harness(tmp_path, monkeypatch):
    from geopol import main, worker

    engine = make_engine(f"sqlite:///{tmp_path / 'test.db'}")
    migrate(engine)
    sessions = sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(settings, "storage_path", tmp_path / "storage")
    monkeypatch.setattr(settings, "batch_size", 2)
    monkeypatch.setattr(worker, "SessionLocal", sessions)
    monkeypatch.setattr(main, "engine", engine, raising=False)
    monkeypatch.setattr(main, "SessionLocal", sessions, raising=False)

    def test_db():
        with sessions() as session:
            yield session

    main.app.dependency_overrides[get_db] = test_db
    encoded = password_hash(PASSWORD)
    with sessions() as db:
        db.add_all(
            [
                User(username=f"test-{role}", password_hash=encoded, role=role)
                for role in ("admin", "operator", "reviewer", "analyst")
            ]
        )
        db.commit()

    try:
        with TestClient(main.app) as client:
            headers = {}
            for role in ("admin", "operator", "reviewer", "analyst"):
                response = client.post(
                    "/api/auth/login", json={"username": f"test-{role}", "password": PASSWORD}
                )
                assert response.status_code == 200, response.text
                headers[role] = {"Authorization": f"Bearer {response.json()['token']}"}
            yield Harness(client, sessions, worker, headers)
    finally:
        main.app.dependency_overrides.clear()
        engine.dispose()


def test_authentication_roles_and_session_revocation(harness):
    client = harness.client
    assert client.get("/api/dashboard").status_code == 401
    assert (
        client.post("/api/auth/login", json={"username": "test-admin", "password": "incorrect"}).status_code
        == 401
    )
    assert client.get("/api/auth/me", headers=harness.headers["analyst"]).json()["role"] == "analyst"
    assert client.get("/api/audit", headers=harness.headers["analyst"]).status_code == 403
    assert (
        client.post(
            "/api/uploads", json={"filename": "a.csv", "size": 10}, headers=harness.headers["analyst"]
        ).status_code
        == 403
    )
    token = harness.headers["operator"]["Authorization"].removeprefix("Bearer ")
    with harness.sessions() as db:
        stored = db.get(LoginSession, token_hash(token))
        assert stored is not None and stored.token_hash != token
    assert client.post("/api/auth/logout", headers=harness.headers["operator"]).status_code == 200
    assert client.get("/api/auth/me", headers=harness.headers["operator"]).status_code == 401


def test_conflicting_declared_crs_requires_review(harness):
    source = b"complaint_id,location_original,ubigeo,latitude,longitude,crs\nDEMO-CRS,LUGAR SINTETICO,150101,-12.04,-77.03,EPSG:32718\n"
    run = harness.run(source)
    result = harness.results(run["id"])[0]
    assert result["resolution"] == "REVISION_REQUERIDA"
    assert result["latitude"] is None and result["longitude"] is None
    detail = harness.client.get(f"/api/results/{result['id']}", headers=harness.headers["admin"]).json()
    assert "CRS_CONFLICTIVO" in detail["normalized"]["warnings"]


@pytest.mark.parametrize(
    "geometry",
    [
        {"type": "Point", "coordinates": [-77, -12, 100]},
        {"type": "UnknownGeometry", "coordinates": [0, 0]},
    ],
)
def test_invalid_or_3d_catalog_geometry_is_rejected(harness, geometry):
    document = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"kind": "site", "ubigeo": "150101", "name": "DEMO"},
                "geometry": geometry,
            }
        ],
    }
    response = harness.client.post(
        "/api/references",
        headers=harness.headers["admin"],
        data={"name": "Demo", "version": "test", "source": "Sintético"},
        files={"file": ("invalid.geojson", json.dumps(document).encode(), "application/geo+json")},
    )
    assert response.status_code == 422, response.text


def test_expired_session_is_rejected(harness):
    token = harness.headers["analyst"]["Authorization"].removeprefix("Bearer ")
    with harness.sessions() as db:
        db.get(LoginSession, token_hash(token)).expires_at = time.time() - 1
        db.commit()
    assert harness.client.get("/api/dashboard", headers=harness.headers["analyst"]).status_code == 401


def test_login_preserves_password_whitespace(harness):
    password = "  synthetic password with spaces  "
    with harness.sessions() as db:
        db.add(User(username="test-spaces", password_hash=password_hash(password), role="analyst"))
        db.commit()
    response = harness.client.post("/api/auth/login", json={"username": "test-spaces", "password": password})
    assert response.status_code == 200, response.text


def test_upload_resumes_by_offset_and_cannot_complete_early(harness):
    client, headers = harness.client, harness.headers["operator"]
    response = client.post(
        "/api/uploads", json={"filename": "resume.csv", "size": len(CSV_DATA)}, headers=headers
    )
    assert response.status_code in (200, 201), response.text
    upload_id = response.json()["id"]
    cut = 71
    response = client.patch(
        f"/api/uploads/{upload_id}", content=CSV_DATA[:cut], headers={**headers, "Upload-Offset": "0"}
    )
    assert response.status_code == 200, response.text
    assert response.json()["offset"] == cut
    assert client.post(f"/api/uploads/{upload_id}/complete", headers=headers).status_code in (400, 409)
    assert (
        client.patch(
            f"/api/uploads/{upload_id}", content=b"wrong", headers={**headers, "Upload-Offset": "0"}
        ).status_code
        == 409
    )
    assert client.get(f"/api/uploads/{upload_id}", headers=headers).json()["offset"] == cut
    response = client.patch(
        f"/api/uploads/{upload_id}", content=CSV_DATA[cut:], headers={**headers, "Upload-Offset": str(cut)}
    )
    assert response.status_code == 200, response.text
    complete = client.post(f"/api/uploads/{upload_id}/complete", headers=headers)
    assert complete.status_code == 200, complete.text
    assert complete.json()["sha256"] == hashlib.sha256(CSV_DATA).hexdigest()
    assert (
        client.patch(
            f"/api/uploads/{upload_id}",
            content=b"x",
            headers={**headers, "Upload-Offset": str(len(CSV_DATA))},
        ).status_code
        == 409
    )


def test_worker_preserves_rows_and_deduplicates_location_units(harness):
    run = harness.run()
    assert run["source_rows"] == 3
    assert run["location_units"] == 2
    assert run["processed_units"] == 2
    results = harness.results(run["id"], "analyst")
    assert sorted(item["source_row_count"] for item in results) == [1, 2]
    assert all(item["latitude"] is None and item["longitude"] is None for item in results)
    assert "person_name" not in json.dumps(results)
    with harness.sessions() as db:
        assert db.scalar(select(func.count()).select_from(SourceRow)) == 3
        assert {row.raw["person_name"] for row in db.scalars(select(SourceRow))} == {
            "Persona sintetica A",
            "Persona sintetica B",
            "=1+1",
        }
    assert not harness.worker.work_once()


def test_original_download_requires_privileged_owner_or_admin(harness):
    upload_id = harness.upload()
    response = harness.client.get(f"/api/uploads/{upload_id}/download", headers=harness.headers["admin"])
    assert response.status_code == 200, response.text
    assert response.content == CSV_DATA
    assert (
        harness.client.get(
            f"/api/uploads/{upload_id}/download", headers=harness.headers["analyst"]
        ).status_code
        == 403
    )
    assert (
        harness.client.get(
            f"/api/uploads/{upload_id}/download", headers=harness.headers["operator"]
        ).status_code
        == 403
    )


def test_retry_resumes_from_committed_checkpoint_without_duplicate_rows(harness, monkeypatch):
    upload_id = harness.upload()
    response = harness.client.post(
        "/api/runs",
        json={"upload_id": upload_id, "name": "Recuperación sintética", "crs": "EPSG:4326"},
        headers=harness.headers["admin"],
    )
    assert response.status_code in (200, 201, 202), response.text
    run_id = response.json()["id"]
    original_ingest_batch = harness.worker.ingest_batch

    def interrupted_after_commit(*args, **kwargs):
        original_ingest_batch(*args, **kwargs)
        raise OSError("Synthetic process interruption after checkpoint")

    monkeypatch.setattr(harness.worker, "ingest_batch", interrupted_after_commit)
    assert harness.worker.work_once()
    failed = harness.client.get(f"/api/runs/{run_id}", headers=harness.headers["admin"]).json()
    assert failed["status"] == "FAILED"
    assert failed["source_rows"] == 2
    monkeypatch.setattr(harness.worker, "ingest_batch", original_ingest_batch)
    retry = harness.client.post(f"/api/runs/{run_id}/retry", headers=harness.headers["admin"])
    assert retry.status_code in (200, 202), retry.text
    assert harness.worker.work_once()
    completed = harness.client.get(f"/api/runs/{run_id}", headers=harness.headers["admin"]).json()
    assert completed["status"] == "COMPLETED"
    assert completed["source_rows"] == 3
    assert completed["location_units"] == 2
    with harness.sessions() as db:
        rows = list(
            db.scalars(select(SourceRow).where(SourceRow.run_id == run_id).order_by(SourceRow.ordinal))
        )
        assert [row.ordinal for row in rows] == [1, 2, 3]
    assert sorted(item["source_row_count"] for item in harness.results(run_id)) == [1, 2]


def test_review_requires_claim_and_rejects_stale_revision(harness):
    run = harness.run()
    result = harness.results(run["id"])[0]
    decision = {
        "expected_revision": result["revision"],
        "action": "unresolved",
        "reason": "No existe evidencia suficiente",
    }
    client = harness.client
    assert (
        client.post(
            f"/api/results/{result['id']}/decisions", json=decision, headers=harness.headers["operator"]
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"/api/results/{result['id']}/decisions", json=decision, headers=harness.headers["reviewer"]
        ).status_code
        == 409
    )
    claim = client.post(f"/api/results/{result['id']}/claim", headers=harness.headers["reviewer"])
    assert claim.status_code == 200, claim.text
    assert (
        client.post(f"/api/results/{result['id']}/claim", headers=harness.headers["admin"]).status_code == 409
    )
    response = client.post(
        f"/api/results/{result['id']}/decisions", json=decision, headers=harness.headers["reviewer"]
    )
    assert response.status_code == 200, response.text
    assert response.json()["revision"] == result["revision"] + 1
    client.post(f"/api/results/{result['id']}/claim", headers=harness.headers["reviewer"])
    assert (
        client.post(
            f"/api/results/{result['id']}/decisions", json=decision, headers=harness.headers["reviewer"]
        ).status_code
        == 409
    )
    detail = client.get(f"/api/results/{result['id']}", headers=harness.headers["reviewer"]).json()
    assert len(detail["history"]) >= 2


def test_manual_point_needs_evidence(harness):
    run = harness.run()
    result = harness.results(run["id"])[0]
    response = harness.decide(result, "manual_point", latitude=-12.04, longitude=-77.03, precision="PUERTA")
    assert response.status_code in (400, 422), response.text


def test_export_keeps_snapshot_and_unresolved_coordinates_empty(harness):
    run = harness.run()
    results = harness.results(run["id"])
    first = next(item for item in results if item["complaint_id"] == "DEMO-A")
    decision = harness.decide(
        first,
        "manual_point",
        latitude=-12.04,
        longitude=-77.03,
        precision="PUERTA",
        evidence="Referencia sintética inspeccionada para integración",
    )
    assert decision.status_code == 200, decision.text
    accepted = decision.json()
    export_id = harness.export(run["id"], role="analyst")
    reopened = harness.decide(accepted, "reopen")
    assert reopened.status_code == 200, reopened.text
    assert harness.worker.work_once()
    rows = harness.download_export(export_id, "analyst")
    assert len(rows) == 2
    row = next(item for item in rows if item["GEOPOL_complaint_id"] == "DEMO-A")
    assert float(row["GEOPOL_latitude"]) == -12.04
    assert float(row["GEOPOL_longitude"]) == -77.03
    assert int(row["GEOPOL_revision"]) == accepted["revision"]
    unresolved = next(item for item in rows if item["GEOPOL_complaint_id"] == "DEMO-B")
    assert unresolved["GEOPOL_latitude"] == unresolved["GEOPOL_longitude"] == ""
    manifest = harness.client.get(f"/api/exports/{export_id}/manifest", headers=harness.headers["analyst"])
    assert manifest.status_code == 200, manifest.text
    assert run["id"] in manifest.text
    assert "person_name" not in json.dumps(rows)


def test_source_export_is_restricted_preserves_rows_and_escapes_formulas(harness):
    run = harness.run()
    response = harness.client.post(
        f"/api/runs/{run['id']}/exports",
        json={"profile": "source_rows", "safe_spreadsheet": True},
        headers=harness.headers["analyst"],
    )
    assert response.status_code == 403
    export_id = harness.export(run["id"], "source_rows", "operator")
    assert harness.worker.work_once()
    rows = harness.download_export(export_id, "operator")
    assert len(rows) == 3
    assert any("'=1+1" in row.values() for row in rows)
    assert all("=1+1" not in row.values() for row in rows)
    for endpoint in ("", "/download", "/manifest"):
        assert (
            harness.client.get(
                f"/api/exports/{export_id}{endpoint}", headers=harness.headers["analyst"]
            ).status_code
            == 403
        )


def test_safe_source_export_also_escapes_formula_headers(harness):
    source = b"complaint_id,location_original,ubigeo,=1+1\nDEMO-H,UBICACION SINTETICA,150101,valor\n"
    run = harness.run(source)
    export_id = harness.export(run["id"], "source_rows")
    assert harness.worker.work_once()
    rows = harness.download_export(export_id)
    assert "'=1+1" in rows[0]
    assert "=1+1" not in rows[0]


def test_reference_import_preserves_version_and_rejects_malformed_input(harness):
    geojson = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "id": "synthetic-door",
                "properties": {
                    "kind": "door",
                    "ubigeo": "150101",
                    "street_type": "AVENIDA",
                    "street_name": "DEMOSTRACION",
                    "door_number": "120",
                },
                "geometry": {"type": "Point", "coordinates": [-77.0345, -12.0435]},
            }
        ],
    }
    metadata = {"name": "Catálogo sintético", "source": "Prueba", "version": "test-1"}
    response = harness.client.post(
        "/api/references",
        data=metadata,
        files={"file": ("synthetic.geojson", json.dumps(geojson).encode(), "application/geo+json")},
        headers=harness.headers["admin"],
    )
    assert response.status_code in (200, 201), response.text
    assert response.json()["version"] == "test-1"
    assert response.json()["feature_count"] == 1
    run = harness.run(reference_id=response.json()["id"])
    results = harness.results(run["id"])
    exact = next(item for item in results if item["complaint_id"] == "DEMO-A")
    assert exact["latitude"] == -12.0435
    assert exact["longitude"] == -77.0345
    malformed = harness.client.post(
        "/api/references",
        data=metadata,
        files={"file": ("malformed.geojson", b"[]", "application/geo+json")},
        headers=harness.headers["admin"],
    )
    assert malformed.status_code in (400, 422), malformed.text


def test_selected_xlsx_sheet_controls_mapping_and_original_export_columns(harness):
    workbook = Workbook()
    dictionary = workbook.active
    dictionary.title = "Diccionario"
    dictionary.append(["nota", "valor"])
    dictionary.append(["DEMO", "Contenido sintético distinto de los hechos"])
    selected = workbook.create_sheet("Hechos")
    selected.append(["codigo", "direccion", "territorio", "dato_privado"])
    selected.append(["HOJA-001", "AVENIDA DE PRUEBA 14", "150101", "Valor sintético a conservar"])
    stream = io.BytesIO()
    workbook.save(stream)
    workbook.close()
    upload_id = harness.upload(stream.getvalue(), "sheets.xlsx")
    profile = harness.client.get(
        f"/api/uploads/{upload_id}/profile", params={"sheet": "Hechos"}, headers=harness.headers["admin"]
    )
    assert profile.status_code == 200, profile.text
    assert profile.json()["columns"] == ["codigo", "direccion", "territorio", "dato_privado"]
    response = harness.client.post(
        "/api/runs",
        json={
            "upload_id": upload_id,
            "name": "Segunda hoja sintética",
            "sheet": "Hechos",
            "mapping": {"complaint_id": "codigo", "location_original": "direccion", "ubigeo": "territorio"},
            "crs": "EPSG:4326",
        },
        headers=harness.headers["admin"],
    )
    assert response.status_code == 201, response.text
    run_id = response.json()["id"]
    assert harness.worker.work_once()
    result = harness.results(run_id)[0]
    assert result["complaint_id"] == "HOJA-001"
    assert result["location_original"] == "AVENIDA DE PRUEBA 14"
    export_id = harness.export(run_id, "source_rows")
    assert harness.worker.work_once()
    rows = harness.download_export(export_id)
    assert len(rows) == 1
    assert rows[0]["dato_privado"] == "Valor sintético a conservar"
    assert "nota" not in rows[0] and "valor" not in rows[0]
    reprocess = harness.client.post(f"/api/runs/{run_id}/reprocess", headers=harness.headers["admin"])
    assert reprocess.status_code == 201, reprocess.text
    assert reprocess.json()["id"] != run_id
    assert harness.worker.work_once()
    assert harness.results(reprocess.json()["id"])[0]["complaint_id"] == "HOJA-001"


def test_sqlite_database_and_objects_restore_together(harness, tmp_path, monkeypatch):
    """Exercise a quiescent backup/restore, then use the restored API and worker."""
    from geopol import main

    run = harness.run()
    export_id = harness.export(run["id"], "source_rows")
    assert harness.worker.work_once()
    export_before = harness.client.get(f"/api/exports/{export_id}", headers=harness.headers["admin"]).json()
    original_database = harness.sessions.kw["bind"].url.database
    original_storage = settings.storage_path
    backup_database = tmp_path / "backup.db"
    backup_storage = tmp_path / "backup-storage"
    # SQLite's online backup API copies a consistent database including its WAL state.
    with (
        closing(sqlite3.connect(original_database)) as source,
        closing(sqlite3.connect(backup_database)) as target,
    ):
        source.backup(target)
    shutil.copytree(original_storage, backup_storage)
    restored_database = tmp_path / "restored.db"
    restored_storage = tmp_path / "restored-storage"
    with (
        closing(sqlite3.connect(backup_database)) as source,
        closing(sqlite3.connect(restored_database)) as target,
    ):
        source.backup(target)
    shutil.copytree(backup_storage, restored_storage)

    restored_engine = make_engine(f"sqlite:///{restored_database}")
    restored_sessions = sessionmaker(restored_engine, expire_on_commit=False)
    original_dependency = main.app.dependency_overrides[get_db]

    def restored_db():
        with restored_sessions() as db:
            yield db

    main.app.dependency_overrides[get_db] = restored_db
    monkeypatch.setattr(settings, "storage_path", restored_storage)
    monkeypatch.setattr(harness.worker, "SessionLocal", restored_sessions)
    monkeypatch.setattr(main, "engine", restored_engine)
    try:
        assert harness.client.get("/api/health").status_code == 200
        dashboard = harness.client.get("/api/dashboard", headers=harness.headers["admin"]).json()
        assert dashboard["runs"] == 1
        assert dashboard["source_rows"] == 3
        assert dashboard["location_units"] == 2
        restored_export = harness.client.get(
            f"/api/exports/{export_id}", headers=harness.headers["admin"]
        ).json()
        assert restored_export["sha256"] == export_before["sha256"]
        assert len(harness.download_export(export_id)) == 3
        assert (restored_storage / "uploads" / run["upload_id"]).read_bytes() == CSV_DATA
        # A new run confirms the restored originals and SQL queue remain usable.
        response = harness.client.post(f"/api/runs/{run['id']}/reprocess", headers=harness.headers["admin"])
        assert response.status_code == 201, response.text
        assert harness.worker.work_once()
        restored_run = harness.client.get(
            f"/api/runs/{response.json()['id']}", headers=harness.headers["admin"]
        ).json()
        assert restored_run["status"] == "COMPLETED"
        assert restored_run["source_rows"] == 3
        assert restored_run["location_units"] == 2
    finally:
        main.app.dependency_overrides[get_db] = original_dependency
        restored_engine.dispose()


def queue_synthetic_run(harness, name):
    upload_id = harness.upload()
    response = harness.client.post(
        "/api/runs",
        json={"upload_id": upload_id, "name": name, "crs": "EPSG:4326"},
        headers=harness.headers["admin"],
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_worker_reclaims_expired_running_job_without_duplicating_work(harness):
    run_id = queue_synthetic_run(harness, "Reserva vencida sintética")
    old_claim = harness.worker.claim_job()
    job_id, old_token, _, target_id = old_claim
    assert target_id == run_id
    assert harness.worker.claim_job() is None
    with harness.sessions() as db:
        job = db.get(Job, job_id)
        assert job.status == "RUNNING" and job.attempts == 1
        job.lease_until = time.time() - 1
        db.commit()
    assert harness.worker.work_once()
    with harness.sessions() as db:
        job = db.get(Job, job_id)
        assert job.status == "COMPLETED"
        assert job.lease_token != old_token
        assert job.attempts == 2
        assert db.scalar(select(func.count()).select_from(Job).where(Job.target_id == run_id)) == 1
        assert db.scalar(select(func.count()).select_from(SourceRow).where(SourceRow.run_id == run_id)) == 3
        assert db.get(Run, run_id).location_units == 2
    assert not harness.worker.work_once()


def test_old_worker_cannot_write_or_confirm_after_lease_reassignment(harness, monkeypatch):
    run_id = queue_synthetic_run(harness, "Fencing sintético")
    old_claim = harness.worker.claim_job()
    job_id, old_token, _, _ = old_claim
    with harness.sessions() as db:
        db.get(Job, job_id).lease_until = time.time() - 1
        db.commit()
    new_claim = harness.worker.claim_job()
    assert new_claim[0] == job_id and new_claim[1] != old_token

    row = (1, {"complaint_id": "STALE", "location_original": "NO DEBE PERSISTIR", "ubigeo": "150101"}, None)
    with pytest.raises(harness.worker.LeaseLost):
        harness.worker.ingest_batch(run_id, [row], job_id, old_token)

    # Simulate the old process returning from its work after a takeover. Its final
    # acknowledgement must not complete the new owner's RUNNING reservation.
    monkeypatch.setattr(harness.worker, "claim_job", lambda: old_claim)
    monkeypatch.setattr(harness.worker, "process_run", lambda *_: None)
    assert harness.worker.work_once()
    with harness.sessions() as db:
        job = db.get(Job, job_id)
        assert job.status == "RUNNING"
        assert job.lease_token == new_claim[1]
        assert job.attempts == 2
        assert db.scalar(select(func.count()).select_from(SourceRow)) == 0
        assert db.scalar(select(func.count()).select_from(Location)) == 0
        assert db.get(Run, run_id).source_rows == 0


def test_cancellation_and_retry_keep_committed_checkpoint_and_unique_rows(harness, monkeypatch):
    run_id = queue_synthetic_run(harness, "Cancelación sintética con checkpoint")
    original_ingest_batch = harness.worker.ingest_batch

    def cancel_after_committed_batch(*args, **kwargs):
        original_ingest_batch(*args, **kwargs)
        response = harness.client.post(f"/api/runs/{run_id}/cancel", headers=harness.headers["admin"])
        assert response.status_code == 200, response.text

    monkeypatch.setattr(harness.worker, "ingest_batch", cancel_after_committed_batch)
    assert harness.worker.work_once()
    cancelled = harness.client.get(f"/api/runs/{run_id}", headers=harness.headers["admin"]).json()
    assert cancelled["status"] == "CANCELLED"
    assert cancelled["source_rows"] == 2 and cancelled["location_units"] == 1
    assert cancelled["processed_units"] == 0
    monkeypatch.setattr(harness.worker, "ingest_batch", original_ingest_batch)
    retry = harness.client.post(f"/api/runs/{run_id}/retry", headers=harness.headers["admin"])
    assert retry.status_code == 200, retry.text
    assert (
        harness.client.post(f"/api/runs/{run_id}/retry", headers=harness.headers["admin"]).status_code == 409
    )
    with harness.sessions() as db:
        assert (
            db.scalar(
                select(func.count()).select_from(Job).where(Job.target_id == run_id, Job.status == "QUEUED")
            )
            == 1
        )
    assert harness.worker.work_once()
    completed = harness.client.get(f"/api/runs/{run_id}", headers=harness.headers["admin"]).json()
    assert completed["status"] == "COMPLETED"
    assert completed["source_rows"] == 3 and completed["location_units"] == 2
    assert completed["processed_units"] == 2
    with harness.sessions() as db:
        rows = list(
            db.scalars(select(SourceRow).where(SourceRow.run_id == run_id).order_by(SourceRow.ordinal))
        )
        assert [item.ordinal for item in rows] == [1, 2, 3]
        assert db.scalar(select(func.count()).select_from(Revision)) == 2
        assert sorted(db.scalars(select(Job.status).where(Job.target_id == run_id))) == [
            "CANCELLED",
            "COMPLETED",
        ]
    assert sorted(item["source_row_count"] for item in harness.results(run_id)) == [1, 2]
    assert not harness.worker.work_once()


def test_gdal_reads_actual_export_point_and_null_geometry(harness, tmp_path):
    """Optional GIS consumer QA, intentionally not an application dependency."""
    pyogrio = pytest.importorskip("pyogrio")
    pytest.importorskip("geopandas")
    source = (
        "complaint_id,location_original,ubigeo\n"
        "000001,PUNTO SINTETICO,010101\n"
        "000002,SIN LOCALIZACION,010101\n"
    ).encode()
    run = harness.run(source)
    result = next(item for item in harness.results(run["id"]) if item["complaint_id"] == "000001")
    response = harness.decide(
        result,
        "manual_point",
        latitude=-12.04,
        longitude=-77.03,
        precision="COORDENADA",
        evidence="Punto sintético para verificar lectura GDAL",
    )
    assert response.status_code == 200, response.text
    export_id = harness.export(run["id"])
    assert harness.worker.work_once()
    response = harness.client.get(f"/api/exports/{export_id}/download", headers=harness.headers["admin"])
    assert response.status_code == 200, response.text
    export_path = tmp_path / "geopol-gis-consumer.csv"
    export_path.write_bytes(response.content)
    data = pyogrio.read_dataframe(
        export_path,
        X_POSSIBLE_NAMES="GEOPOL_longitude",
        Y_POSSIBLE_NAMES="GEOPOL_latitude",
        KEEP_GEOM_COLUMNS="YES",
        EMPTY_STRING_AS_NULL="YES",
        AUTODETECT_TYPE="NO",
    )
    assert len(data) == 2
    assert data.geometry.notna().sum() == 1 and data.geometry.isna().sum() == 1
    located = data.loc[data["GEOPOL_complaint_id"] == "000001"].iloc[0]
    missing = data.loc[data["GEOPOL_complaint_id"] == "000002"].iloc[0]
    assert located.geometry.x == -77.03 and located.geometry.y == -12.04
    assert missing.geometry is None
    assert list(data["GEOPOL_ubigeo"]) == ["010101", "010101"]
    # CSV has no CRS metadata; assign the manifest's explicit EPSG:4326 contract.
    assert data.crs is None
    data = data.set_crs("EPSG:4326")
    assert data.crs.to_epsg() == 4326
    print(
        json.dumps(
            {
                "pyogrio": pyogrio.__version__,
                "gdal": pyogrio.__gdal_version_string__,
                "rows": len(data),
                "points": int(data.geometry.notna().sum()),
                "null_geometries": int(data.geometry.isna().sum()),
                "crs_assigned": "EPSG:4326",
                "zero_prefixed_identifiers": sorted(data["GEOPOL_complaint_id"].tolist()),
                "sha256": hashlib.sha256(response.content).hexdigest(),
            },
            ensure_ascii=False,
        )
    )
