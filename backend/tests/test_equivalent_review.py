"""Synthetic safety and atomicity contracts for explicit equivalent-group decisions."""

import copy
import time
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from test_api import harness as harness
from test_review_workflow_api import catalog, checked

from geopol.api import review_groups
from geopol.domain.equivalent_review import candidate_is_corroborable, eligibility_reason, equivalence_key
from geopol.models import Audit, Location, Revision, Run, SourceRow


def seed(harness, count=2):
    reference = catalog(harness)
    data = "complaint_id,location_original,ubigeo\n" + "".join(
        f"GROUP-{i:03},AV DEMOSTRACIOZ 120,150101\n" for i in range(count)
    )
    run = harness.run(data.encode(), reference_id=reference)
    with harness.sessions() as db:
        items = list(db.scalars(select(Location).where(Location.run_id == run["id"]).order_by(Location.id)))
        assert all(item.review_bucket == "actionable" for item in items)
        assert all(item.normalized["warnings"] == [] for item in items)
        return run, [review_groups.state(item) for item in items]


def preview(harness, item, role="reviewer", status=200):
    return checked(
        harness.client.get(f"/api/results/{item['id']}/review-group/preview", headers=harness.headers[role]),
        status,
    )


def decide(harness, item, shown, role="reviewer", **fields):
    return harness.client.post(
        f"/api/results/{item['id']}/review-group/decide",
        headers=harness.headers[role],
        json={
            "token": shown["token"],
            "candidate_id": item["candidates"][0]["id"],
            "reason": "Contraste humano de la dirección sintética y su referencia",
            **fields,
        },
    )


def test_real_matching_preview_and_decision_are_atomic_manual_and_traceable(harness):
    run, items = seed(harness)
    with harness.sessions() as db:
        originals = [(row.id, copy.deepcopy(row.raw)) for row in db.scalars(select(SourceRow))]
    shown = preview(harness, items[0])
    assert shown["eligible"] is True
    assert shown["count"] == shown["source_rows"] == 2
    assert shown["excluded_count"] == 0
    assert shown["limit"] == 200 and not shown["truncated"]
    assert {item["id"] for item in shown["members"]} == {item["id"] for item in items}
    # Preview is read-only and does not reserve every record in the group.
    with harness.sessions() as db:
        assert all(db.get(Location, item["id"]).review_owner is None for item in items)
    applied = checked(decide(harness, items[0], shown))
    assert applied["applied_count"] == 2
    assert set(applied["location_ids"]) == {item["id"] for item in items}
    assert applied["item"]["id"] == items[0]["id"]
    with harness.sessions() as db:
        for before in items:
            after = db.get(Location, before["id"])
            assert after.resolution == "ACEPTADO_MANUAL" and after.manual is True
            assert after.review_status == "CLOSED" and after.review_bucket == "none"
            assert after.review_owner is after.review_expires_at is None
            assert after.revision == before["revision"] + 1
            assert after.geometry == before["candidates"][0]["geometry"]
            assert after.normalized["review_group"]["id"] == applied["group_id"]
            revision = db.scalar(
                select(Revision).where(Revision.location_id == after.id, Revision.revision == after.revision)
            )
            assert revision.action == "accept_candidate"
            assert revision.reason == after.reason
            assert revision.snapshot["review_group_id"] == applied["group_id"]
            assert revision.snapshot["candidates"] == before["candidates"]
            event = db.scalar(
                select(Audit).where(Audit.entity_id == after.id, Audit.action == "review.decision")
            )
            assert event.detail["review_group_id"] == applied["group_id"]
            assert event.detail["candidate_id"] == before["candidates"][0]["id"]
        group_event = db.scalar(select(Audit).where(Audit.entity_id == applied["group_id"]))
        assert group_event.detail["count"] == 2
        assert group_event.detail["run_id"] == run["id"]
        assert [(row.id, row.raw) for row in db.scalars(select(SourceRow))] == originals
    checked(decide(harness, items[0], shown), 409)


@pytest.mark.parametrize(
    "change",
    [
        "door_number",
        "street_type",
        "street_name",
        "block_number",
        "manzana_code",
        "lot_number",
        "cross_street",
        "site_name",
        "urban_core",
        "district",
        "coordinate_origin",
        "crs",
        "legacy",
    ],
)
def test_exact_equivalence_includes_all_address_and_coordinate_context(change):
    base = {
        "location_normalized": "AV DEMOSTRACION 120",
        "ubigeo": "150101",
        "normalized": {},
        "candidates": [],
    }
    different = copy.deepcopy(base)
    different["normalized"][change] = "DIFFERENT"
    assert equivalence_key(base) != equivalence_key(different)


@pytest.mark.parametrize("change", ["geometry", "source", "version", "evidence", "reference_metadata", "id"])
def test_exact_equivalence_includes_candidate_geometry_and_provenance(change):
    base = {
        "location_normalized": "AV DEMOSTRACION 120",
        "ubigeo": "150101",
        "normalized": {},
        "candidates": [{"id": "a"}],
    }
    different = copy.deepcopy(base)
    different["candidates"][0][change] = "DIFFERENT"
    assert equivalence_key(base) != equivalence_key(different)


def test_components_and_source_coordinates_are_not_grouped_by_display_address(harness):
    _, items = seed(harness, 3)
    with harness.sessions() as db:
        door = db.get(Location, items[1]["id"])
        door.normalized = {**door.normalized, "door_number": "999"}
        coordinate = db.get(Location, items[2]["id"])
        coordinate.normalized = {
            **coordinate.normalized,
            "latitude": -12.04,
            "longitude": -77.03,
            "crs": "EPSG:4326",
            "coordinate_origin": "PNP_ORIGINAL",
        }
        db.commit()
    shown = preview(harness, items[0])
    assert shown["count"] == 1 and shown["excluded_count"] == 2
    assert not shown["eligible"] and shown["token"] is None


def test_warnings_unknown_crs_conflicts_and_missing_evidence_block_group(harness):
    _, items = seed(harness)
    base = items[0]
    user = "synthetic-reviewer"
    assert eligibility_reason(base, user, time.time()) is None
    cases = []
    for warning in ("CRS_CONFLICTIVO", "REFERENCIA_RELATIVA", "COORDENADAS_CONTRADICTORIAS"):
        case = copy.deepcopy(base)
        case["normalized"]["warnings"] = [warning]
        cases.append(case)
    unknown_crs = copy.deepcopy(base)
    unknown_crs["normalized"].update(latitude=-12.04, longitude=-77.03, crs=None)
    cases.append(unknown_crs)
    contradictory = copy.deepcopy(base)
    contradictory["normalized"].update(latitude=-12.09, longitude=-77.08, crs="EPSG:4326")
    cases.append(contradictory)
    missing_reference = copy.deepcopy(base)
    missing_reference["review_bucket"] = "needs_reference"
    cases.append(missing_reference)
    for code in (
        "CRS_REFERENCIA_NO_CONFIRMADO",
        "GEOMETRIA_EXCEDE_UBIGEO",
        "NUCLEO_URBANO_CONTRADICTORIO_REFERENCIA",
    ):
        case = copy.deepcopy(base)
        case["candidates"][0]["evidence"].append(code)
        cases.append(case)
    for field in ("source", "version", "geometry", "evidence"):
        case = copy.deepcopy(base)
        case["candidates"][0][field] = None
        cases.append(case)
    alternatives = copy.deepcopy(base)
    other = copy.deepcopy(base["candidates"][0])
    other.update(id="other", latitude=-12.08, geometry={"type": "Point", "coordinates": [-77.03, -12.08]})
    alternatives["candidates"].append(other)
    cases.append(alternatives)
    for case in cases:
        assert eligibility_reason(case, user, time.time()) is not None


def test_reservations_exclude_other_reviewers_and_allow_expired_reservations(harness):
    _, items = seed(harness, 3)
    checked(harness.client.post(f"/api/results/{items[1]['id']}/claim", headers=harness.headers["admin"]))
    shown = preview(harness, items[0])
    assert shown["count"] == 2 and shown["excluded_count"] == 1
    assert items[1]["id"] not in {item["id"] for item in shown["members"]}
    own = preview(harness, items[1], role="admin")
    assert own["count"] == 3
    with harness.sessions() as db:
        db.get(Location, items[1]["id"]).review_expires_at = time.time() - 1
        db.commit()
    available = preview(harness, items[0])
    assert available["count"] == 3
    checked(decide(harness, items[0], shown), 409)
    assert checked(decide(harness, items[0], available))["applied_count"] == 3


@pytest.mark.parametrize("change", ["revision", "candidate", "reservation", "manual", "bucket"])
def test_changed_preview_rejects_without_partial_decisions(harness, change):
    _, items = seed(harness)
    shown = preview(harness, items[0])
    if change == "reservation":
        checked(harness.client.post(f"/api/results/{items[1]['id']}/claim", headers=harness.headers["admin"]))
    else:
        with harness.sessions() as db:
            other = db.get(Location, items[1]["id"])
            if change == "revision":
                other.revision += 1
            elif change == "candidate":
                candidates = copy.deepcopy(other.candidates)
                candidates[0]["version"] = "new-source-version"
                other.candidates = candidates
            elif change == "manual":
                other.manual = True
            else:
                other.review_bucket = "needs_reference"
            db.commit()
    checked(decide(harness, items[0], shown), 409)
    with harness.sessions() as db:
        assert db.get(Location, items[0]["id"]).revision == items[0]["revision"]
        assert db.get(Location, items[0]["id"]).review_owner is None
        assert db.scalar(select(Audit).where(Audit.action == "review.group_decision")) is None


def test_internal_second_decision_failure_rolls_back_first_and_all_leases(harness, monkeypatch):
    _, items = seed(harness)
    shown = preview(harness, items[0])
    original = review_groups.apply_decision
    calls = []

    def fail_second(*args, **kwargs):
        calls.append(args[1].id)
        if len(calls) == 2:
            raise HTTPException(409, "Fallo sintético en la segunda revisión")
        return original(*args, **kwargs)

    monkeypatch.setattr(review_groups, "apply_decision", fail_second)
    checked(decide(harness, items[0], shown), 409)
    assert len(calls) == 2
    with harness.sessions() as db:
        for before in items:
            after = db.get(Location, before["id"])
            assert after.revision == before["revision"]
            assert after.manual is False
            assert after.review_owner is None
            assert "review_group" not in after.normalized
            assert len(list(db.scalars(select(Revision).where(Revision.location_id == after.id)))) == 1
        assert db.scalar(select(Audit).where(Audit.action == "review.decision")) is None


def test_group_roles_reason_and_candidate_are_validated(harness):
    _, items = seed(harness)
    shown = preview(harness, items[0])
    path = f"/api/results/{items[0]['id']}/review-group/preview"
    assert harness.client.get(path).status_code == 401
    for role in ("analyst", "operator"):
        preview(harness, items[0], role=role, status=403)
        checked(decide(harness, items[0], shown, role=role), 403)
    checked(decide(harness, items[0], shown, role="admin"), 409)  # token binds actor
    checked(decide(harness, items[0], shown, candidate_id="unseen-candidate"), 422)
    checked(decide(harness, items[0], shown, reason="        "), 422)
    checked(decide(harness, items[0], shown, learn_address=True), 422)
    assert (
        checked(decide(harness, items[0], preview(harness, items[0], role="admin"), role="admin"))[
            "applied_count"
        ]
        == 2
    )


@pytest.mark.parametrize("status", ["PROCESSING", "superseded"])
def test_incomplete_and_historical_runs_reject_group(harness, status):
    run, items = seed(harness)
    shown = preview(harness, items[0])
    with harness.sessions() as db:
        current = db.get(Run, run["id"])
        if status == "superseded":
            current.superseded_by = current.id  # synthetic lineage marker
        else:
            current.status = status
        db.commit()
    preview(harness, items[0], status=409)
    checked(decide(harness, items[0], shown), 409)


def test_limit_is_visible_and_never_applies_silent_partial_group(harness):
    _, items = seed(harness, 201)
    # The base must remain in the preview even when it sorts beyond the first 200.
    shown = preview(harness, items[-1])
    assert shown["count"] == 201 and shown["source_rows"] == 201
    assert len(shown["members"]) == 200 and shown["members"][0]["id"] == items[-1]["id"]
    assert shown["truncated"] and not shown["eligible"] and shown["token"] is None
    assert "No se aplicará una decisión parcial" in shown["reason"]
    checked(decide(harness, items[-1], {"token": "a" * 64}), 409)


def test_other_runs_are_not_members_and_run_config_changes_invalidate_preview(harness):
    run, items = seed(harness)
    _, other_items = seed(harness)
    shown = preview(harness, items[0])
    assert shown["count"] == 2
    assert not {row["id"] for row in shown["members"]} & {row["id"] for row in other_items}
    with harness.sessions() as db:
        current = db.get(Run, run["id"])
        current.config = {**current.config, "crs_evidence": "Nuevo documento sintético de confirmación"}
        db.commit()
    checked(decide(harness, items[0], shown), 409)


def test_group_area_preserves_precision_and_never_substitutes_a_centroid(harness):
    _, items = seed(harness)
    geometry = {"type": "LineString", "coordinates": [[-77.03, -12.04], [-77.031, -12.041]]}
    with harness.sessions() as db:
        for item in items:
            row = db.get(Location, item["id"])
            candidate = copy.deepcopy(row.candidates[0])
            candidate.update(
                geometry=geometry,
                product="AREA_TRAMO",
                precision="VIA",
                method="VIA_JURISDICCION",
                latitude=None,
                longitude=None,
            )
            candidate["evidence"] = [
                "GEOMETRIA_COMPLETA_DENTRO_UBIGEO" if code == "PUNTO_DENTRO_UBIGEO" else code
                for code in candidate["evidence"]
            ]
            row.candidates = [candidate]
        db.commit()
    shown = preview(harness, items[0])
    assert shown["eligible"] and shown["candidates"][0]["precision"] == "VIA"
    checked(decide(harness, items[0], shown))
    with harness.sessions() as db:
        for item in items:
            row = db.get(Location, item["id"])
            assert row.geometry == geometry and row.precision == "VIA"
            assert row.latitude is row.longitude is None
            assert row.product == "AREA_TRAMO"


def test_simultaneous_group_decisions_cannot_double_apply(harness, monkeypatch):
    _, items = seed(harness)
    shown = preview(harness, items[0])
    entered, release, second_started = Event(), Event(), Event()
    original = review_groups.apply_decision

    def pause_first(*args, **kwargs):
        if not entered.is_set():
            entered.set()
            assert release.wait(timeout=10)
        return original(*args, **kwargs)

    def second_request():
        second_started.set()
        return decide(harness, items[0], shown)

    monkeypatch.setattr(review_groups, "apply_decision", pause_first)
    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(decide, harness, items[0], shown)
        try:
            assert entered.wait(timeout=10)
            second = executor.submit(second_request)
            assert second_started.wait(timeout=10)
        finally:
            release.set()
        responses = [first.result(timeout=15), second.result(timeout=15)]
    assert sorted(response.status_code for response in responses) == [200, 409]
    with harness.sessions() as db:
        for before in items:
            assert db.get(Location, before["id"]).revision == before["revision"] + 1
        events = list(db.scalars(select(Audit).where(Audit.action == "review.group_decision")))
        assert len(events) == 1


@pytest.mark.parametrize(
    "evidence,expected",
    [(None, False), ("", False), ("corto", False), ("Fuente sintética documentada", True)],
)
def test_original_candidate_rejects_legacy_crs_without_documented_source(evidence, expected):
    normalized = {"crs": "EPSG:4326", "crs_evidence": evidence, "latitude": -12.04, "longitude": -77.03}
    candidate = {
        "id": "original",
        "method": "COORD_ORIGINAL",
        "source": "ARCHIVO_ORIGINAL",
        "version": "synthetic",
        "precision": "COORDENADA",
        "product": "PUNTO",
        "latitude": -12.04,
        "longitude": -77.03,
        "geometry": {"type": "Point", "coordinates": [-77.03, -12.04]},
        "evidence": ["PNP_ORIGINAL", "PUNTO_DENTRO_UBIGEO"],
    }
    assert candidate_is_corroborable(candidate, normalized) is expected


@pytest.mark.parametrize(
    "normalized_documented,run_documented", [(False, False), (False, True), (True, False), (True, True)]
)
def test_source_coordinates_require_documentation_on_both_result_and_run(
    harness, normalized_documented, run_documented
):
    run, items = seed(harness)
    with harness.sessions() as db:
        current = db.get(Run, run["id"])
        current.config = {
            **current.config,
            "crs": "EPSG:4326",
            "crs_evidence": "Documento sintético del CRS" if run_documented else None,
        }
        for item in items:
            row = db.get(Location, item["id"])
            row.normalized = {
                **row.normalized,
                "latitude": -12.04,
                "longitude": -77.03,
                "crs": "EPSG:4326",
                "coordinate_origin": "PNP_ORIGINAL",
                "crs_evidence": "Documento sintético del CRS" if normalized_documented else None,
            }
        db.commit()
    shown = preview(harness, items[0])
    expected = normalized_documented and run_documented
    assert shown["eligible"] is expected
    if expected:
        assert checked(decide(harness, items[0], shown))["applied_count"] == 2
    else:
        assert shown["token"] is None
        checked(decide(harness, items[0], {"token": "a" * 64}), 409)
        with harness.sessions() as db:
            assert all(db.get(Location, item["id"]).revision == item["revision"] for item in items)


def test_reference_group_without_source_coordinates_does_not_require_input_crs(harness):
    run, items = seed(harness)
    with harness.sessions() as db:
        current = db.get(Run, run["id"])
        current.config = {**current.config, "crs": None, "crs_evidence": None}
        for item in items:
            row = db.get(Location, item["id"])
            row.normalized = {**row.normalized, "crs": None, "crs_evidence": None}
        db.commit()
    shown = preview(harness, items[0])
    assert shown["eligible"]
    assert checked(decide(harness, items[0], shown))["applied_count"] == 2
