"""Synthetic contracts for catalog defaults and documented coordinate declarations."""

import pytest
from sqlalchemy import select, text
from test_api import harness as harness
from test_review_workflow_api import catalog, checked

from geopol.migrations import migrate
from geopol.models import Audit, Catalog, Location, ProcessingDefaults, Run
from geopol.serialization import reference_status

EVIDENCE = "Metadatos de la muestra sintética: coordenadas geográficas WGS84"


def get_defaults(harness):
    return checked(harness.client.get("/api/processing-defaults", headers=harness.headers["analyst"]))


def set_defaults(harness, identifier):
    return checked(
        harness.client.put(
            "/api/processing-defaults", json={"reference_id": identifier}, headers=harness.headers["admin"]
        )
    )


def create_run(harness, **kwargs):
    return checked(
        harness.client.post(
            "/api/runs",
            json={"upload_id": harness.upload(), "name": "Selección sintética", **kwargs},
            headers=harness.headers["admin"],
        ),
        201,
    )


def test_default_starts_empty_and_requires_admin(harness):
    checked(harness.client.get("/api/processing-defaults"), 401)
    assert get_defaults(harness) == {
        "default_reference_id": None,
        "catalog": None,
        "status": "not_configured",
        "updated_at": None,
        "updated_by": None,
    }
    for role in ("operator", "reviewer", "analyst"):
        checked(
            harness.client.put(
                "/api/processing-defaults", json={"reference_id": None}, headers=harness.headers[role]
            ),
            403,
        )
    checked(harness.client.patch("/api/processing-defaults", json={}, headers=harness.headers["admin"]), 422)


def test_defaults_are_persistent_audited_and_catalog_version_is_snapshotted(harness):
    first = catalog(harness, "1")
    second = catalog(harness, "2")
    saved = set_defaults(harness, first)
    assert saved["status"] == "ready"
    assert saved["catalog"]["version"] == "1"
    assert saved["updated_at"] and saved["updated_by"]
    automatic = create_run(harness)
    disabled = create_run(harness, reference_id=None)
    explicit = create_run(harness, reference_id=second)
    assert automatic["reference_id"] == first
    assert automatic["config"]["reference_selection"] == "default"
    assert disabled["reference_id"] is None
    assert disabled["config"]["reference_selection"] == "explicit"
    assert explicit["reference_id"] == second
    set_defaults(harness, second)
    with harness.sessions() as db:
        assert db.get(ProcessingDefaults, "global").reference_id == second
        assert db.get(Run, automatic["id"]).reference_id == first
        events = list(db.scalars(select(Audit).where(Audit.action == "processing_defaults.updated")))
        assert len(events) == 2
        assert events[-1].detail == {"previous_reference_id": first, "reference_id": second}
    assert get_defaults(harness)["catalog"]["version"] == "2"
    cleared = set_defaults(harness, None)
    assert cleared["status"] == "not_configured" and cleared["default_reference_id"] is None


def test_missing_or_empty_catalog_cannot_be_default(harness):
    checked(
        harness.client.put(
            "/api/processing-defaults",
            json={"reference_id": "missing"},
            headers=harness.headers["admin"],
        ),
        404,
    )
    with harness.sessions() as db:
        db.add(Catalog(id="empty", name="Vacío sintético", version="1", source="SINTETICO", sha256="0"))
        db.commit()
        assert reference_status(db, "missing")["status"] == "missing"
        assert reference_status(db, "empty")["status"] == "empty"
    checked(
        harness.client.put(
            "/api/processing-defaults", json={"reference_id": "empty"}, headers=harness.headers["admin"]
        ),
        422,
    )
    assert get_defaults(harness)["status"] == "not_configured"


def test_unusable_default_is_explicit_failure_but_null_allows_no_catalog(harness):
    identifier = catalog(harness)
    set_defaults(harness, identifier)
    with harness.sessions() as db:
        # Simulate an incomplete restore without removing any referenced catalog.
        db.get(Catalog, identifier).feature_count = 0
        db.commit()
    assert get_defaults(harness)["status"] == "empty"
    checked(
        harness.client.post(
            "/api/runs",
            json={"upload_id": harness.upload(), "name": "Catálogo no disponible"},
            headers=harness.headers["admin"],
        ),
        409,
    )
    assert create_run(harness, reference_id=None)["reference_id"] is None


@pytest.mark.parametrize(
    "fields",
    [
        {"crs": "EPSG:4326"},
        {"crs": "EPSG:4326", "crs_evidence": "   "},
        {"crs": "EPSG:4326", "crs_evidence": "x" * 501},
        {"crs": None, "crs_evidence": EVIDENCE},
        {"crs": "EPSG:32718", "crs_evidence": EVIDENCE},
    ],
)
def test_crs_requires_supported_documented_declaration(harness, fields):
    checked(
        harness.client.post(
            "/api/runs",
            json={"upload_id": harness.upload(), "name": "CRS sintético", **fields},
            headers=harness.headers["admin"],
        ),
        422,
    )


def test_new_run_does_not_infer_crs_and_retains_explicit_evidence(harness):
    unconfirmed = create_run(harness)
    assert unconfirmed["config"]["crs"] is None
    assert unconfirmed["config"]["crs_evidence"] is None
    confirmed = create_run(harness, crs="EPSG:4326", crs_evidence=EVIDENCE)
    assert confirmed["config"]["crs"] == "EPSG:4326"
    assert confirmed["config"]["crs_evidence"] == EVIDENCE


@pytest.mark.parametrize("with_catalog", [True, False])
def test_reprocess_preserves_catalog_instead_of_using_changed_default(harness, with_catalog):
    first = catalog(harness, "1")
    second = catalog(harness, "2")
    set_defaults(harness, first)
    parent = create_run(harness, reference_id=first if with_catalog else None)
    assert harness.worker.work_once()
    set_defaults(harness, second)
    child = checked(
        harness.client.post(f"/api/runs/{parent['id']}/reprocess", headers=harness.headers["admin"]), 201
    )
    assert child["reference_id"] == (first if with_catalog else None)


@pytest.mark.parametrize("legacy_evidence", [None, "", "   ", "old"])
def test_legacy_reprocess_drops_unconfirmed_crs_without_mutating_parent(harness, legacy_evidence):
    parent = harness.run()
    with harness.sessions() as db:
        legacy = db.get(Run, parent["id"])
        original = {**legacy.config, "crs": "EPSG:4326", "crs_evidence": legacy_evidence}
        legacy.config = original
        db.commit()
    readiness = checked(
        harness.client.get(f"/api/runs/{parent['id']}/readiness", headers=harness.headers["admin"])
    )
    assert readiness["coordinates"]["legacy_unconfirmed"] is True
    child = checked(
        harness.client.post(f"/api/runs/{parent['id']}/reprocess", json={}, headers=harness.headers["admin"]),
        201,
    )
    assert child["config"]["crs"] is child["config"]["crs_evidence"] is None
    with harness.sessions() as db:
        assert db.get(Run, parent["id"]).config == original


def test_reprocess_can_confirm_crs_and_then_preserve_its_source(harness):
    parent = harness.run()
    checked(
        harness.client.post(
            f"/api/runs/{parent['id']}/reprocess",
            json={"crs": "EPSG:4326"},
            headers=harness.headers["admin"],
        ),
        422,
    )
    child = checked(
        harness.client.post(
            f"/api/runs/{parent['id']}/reprocess",
            json={"crs": "EPSG:4326", "crs_evidence": EVIDENCE},
            headers=harness.headers["admin"],
        ),
        201,
    )
    assert child["config"]["crs_evidence"] == EVIDENCE
    assert harness.worker.work_once()
    grandchild = checked(
        harness.client.post(f"/api/runs/{child['id']}/reprocess", headers=harness.headers["admin"]), 201
    )
    assert grandchild["config"]["crs"] == "EPSG:4326"
    assert grandchild["config"]["crs_evidence"] == EVIDENCE


def test_readiness_aggregates_persisted_queue_without_candidates_or_source_rows(harness):
    identifier = catalog(harness)
    set_defaults(harness, identifier)
    run = harness.run()
    checked(harness.client.get(f"/api/runs/{run['id']}/readiness"), 401)
    checked(harness.client.get("/api/runs/missing/readiness", headers=harness.headers["analyst"]), 404)
    with harness.sessions() as db:
        items = list(db.scalars(select(Location).where(Location.run_id == run["id"])))
        items[0].resolution = "ACEPTADO_AUTOMATICO"
        items[0].product = "AREA_TRAMO"
        items[0].review_status = "CLOSED"
        items[0].review_bucket = "none"
        items[1].review_status = "OPEN"
        items[1].review_bucket = "needs_reference"
        db.commit()
    result = checked(
        harness.client.get(f"/api/runs/{run['id']}/readiness", headers=harness.headers["analyst"])
    )
    assert result["reference"]["reference_id"] == identifier
    assert result["reference"]["status"] == "ready"
    assert result["processing_defaults"]["default_reference_id"] == identifier
    assert result["coordinates"]["confirmed"] is True
    assert result["coordinates"]["legacy_unconfirmed"] is False
    assert result["review"]["total_open"] == 1
    assert result["review"]["by_bucket"] == {"needs_reference": 1}
    assert result["review"]["causes"][0]["bucket"] == "needs_reference"
    assert result["automatic"] == {"points": 0, "areas": 1}


def test_version_four_is_additive_and_idempotent(harness):
    identifier = catalog(harness)
    run = harness.run(reference_id=identifier)
    original = run["config"].copy()
    set_defaults(harness, identifier)
    with harness.sessions() as db:
        engine = db.get_bind()
        before = db.get(ProcessingDefaults, "global").updated_at
    migrate(engine)
    migrate(engine)
    with harness.sessions() as db:
        assert db.get(Run, run["id"]).config == original
        assert db.get(ProcessingDefaults, "global").reference_id == identifier
        assert db.get(ProcessingDefaults, "global").updated_at == before
        assert list(db.scalars(text("SELECT version FROM schema_versions ORDER BY version"))) == [1, 2, 3, 4]
