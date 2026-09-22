"""Real persistence/HTTP contracts for geometric results and explicit address memory."""

import json
import time

from sqlalchemy import select
from test_api import harness as harness

from geopol.models import AddressMemory, Catalog, Feature, Location
from geopol.reference_search import ReferenceSearch
from geopol.address_memory import address_signature, resolve_memory


def data(identifier="A", district="150101"):
    return f"complaint_id,location_original,ubigeo\n{identifier},AV DEMOSTRACION 120,{district}\n".encode()


def checked(response, status=200):
    assert response.status_code == status, response.text
    return response.json()


def learn(harness, item, latitude=-12.04, longitude=-77.03):
    return checked(
        harness.decide(
            item,
            "manual_point",
            latitude=latitude,
            longitude=longitude,
            precision="PUERTA",
            evidence="Verificación sintética de puerta",
            learn_address=True,
        )
    )


def test_memory_reuses_exact_address_across_complaints_and_retires_on_reopen(harness):
    first = harness.run(data())
    confirmed = learn(harness, harness.results(first["id"])[0])
    second = harness.run(data("B"))
    reused = harness.results(second["id"])[0]
    assert reused["resolution"] == "ACEPTADO_AUTOMATICO"
    assert reused["method"] == "DIRECCION_VALIDADA"
    assert reused["geometry"]["coordinates"] == [-77.03, -12.04]
    assert second["counts_by_product"] == {"PUNTO": 1}
    checked(harness.decide(confirmed, "reopen"))
    third = harness.run(data("C"))
    assert harness.results(third["id"])[0]["resolution"] != "ACEPTADO_AUTOMATICO"
    assert harness.results(second["id"])[0] == reused  # historical decisions are immutable


def test_memory_requires_opt_in_and_matches_territory(harness):
    first = harness.run(data())
    item = harness.results(first["id"])[0]
    checked(
        harness.decide(
            item,
            "manual_point",
            latitude=-12.04,
            longitude=-77.03,
            precision="PUERTA",
            evidence="Verificación sintética de puerta",
        )
    )
    second = harness.run(data("B"))
    assert harness.results(second["id"])[0]["resolution"] != "ACEPTADO_AUTOMATICO"
    learn(harness, harness.results(second["id"])[0])
    other = harness.run(data("C", "150102"))
    assert harness.results(other["id"])[0]["resolution"] != "ACEPTADO_AUTOMATICO"


def test_territorial_conflict_cannot_be_overridden_by_memory(harness):
    first = harness.run(data())
    learn(harness, harness.results(first["id"])[0])
    second = harness.run(
        b"complaint_id,location_original,ubigeo,FLAG_GEOREF\nB,AV DEMOSTRACION 120,150101,2\n"
    )
    assert harness.results(second["id"])[0]["resolution"] != "ACEPTADO_AUTOMATICO"


def test_memory_signature_includes_all_structured_address_evidence():
    base = {"location_normalized": "LUGAR", "ubigeo": "150101"}
    for field in ("street_type", "site_name", "urban_core", "district", "manzana_code", "lot_number"):
        assert address_signature({**base, field: "A"}) != address_signature({**base, field: "B"})


def test_memory_compares_new_evidence_at_its_own_precision(harness):
    first = harness.run(data())
    learned = learn(harness, harness.results(first["id"])[0])
    line = {"type": "LineString", "coordinates": [[-77.031, -12.041], [-77.031, -12.039]]}
    with harness.sessions() as db:
        normalized = {**db.get(Location, learned["id"]).normalized, "crs": None}
        base = {
            "resolution": "ACEPTADO_AUTOMATICO",
            "product": "AREA_TRAMO",
            "precision": "VIA",
            "method": "VIA_JURISDICCION",
            "geometry": line,
            "latitude": None,
            "longitude": None,
            "candidates": [],
            "attempts": [],
        }
        result = resolve_memory(db, normalized, base, time.time())
        assert result["resolution"] == "ACEPTADO_AUTOMATICO"
        assert result["product"] == "PUNTO"
        assert result["method"] == "DIRECCION_VALIDADA"
        original = {
            "method": "COORD_ORIGINAL",
            "geometry": {"type": "Point", "coordinates": [-77.04, -12.05]},
            "evidence": ["CRS_NO_CONFIRMADO"],
        }
        result = resolve_memory(db, normalized, {**base, "candidates": [original]}, time.time())
        assert result["resolution"] == "ACEPTADO_AUTOMATICO"
        result = resolve_memory(
            db, {**normalized, "crs": "EPSG:4326"}, {**base, "candidates": [original]}, time.time()
        )
        assert result["resolution"] == "REVISION_REQUERIDA"
        fresh_point = {
            **base,
            "product": "PUNTO",
            "precision": "PUERTA",
            "geometry": original["geometry"],
            "method": "PUERTA_CON_TIPO",
            "reason": "COINCIDENCIA_APROXIMADA_FUERTE_CON_EVIDENCIA_INDEPENDIENTE",
        }
        assert resolve_memory(db, normalized, fresh_point, time.time())["resolution"] == "REVISION_REQUERIDA"


def test_conflicting_confirmations_do_not_autoresolve(harness):
    first = harness.run(data())
    learn(harness, harness.results(first["id"])[0])
    second = harness.run(data("B"))
    learn(harness, harness.results(second["id"])[0], longitude=-77.04)
    third = harness.run(data("C"))
    item = harness.results(third["id"])[0]
    assert item["resolution"] == "REVISION_REQUERIDA"
    assert "MEMORIA_CONFLICTIVA" in item["reason"]
    assert item["latitude"] is item["longitude"] is item["geometry"] is None


def test_corrected_address_is_learned_under_its_new_components(harness):
    first = harness.run(data())
    item = harness.results(first["id"])[0]
    corrected = checked(harness.decide(item, "address_only", address="AV DEMOSTRACION 999"))
    reopened = checked(harness.decide(corrected, "reopen"))
    learn(harness, reopened)
    old_address = harness.run(data("B"))
    assert harness.results(old_address["id"])[0]["resolution"] != "ACEPTADO_AUTOMATICO"
    new_address = harness.run(data("C").replace(b"120", b"999"))
    assert harness.results(new_address["id"])[0]["method"] == "DIRECCION_VALIDADA"


def test_memory_can_be_revoked_after_source_run_is_superseded(harness):
    first = harness.run(data())
    learned = learn(harness, harness.results(first["id"])[0])
    detail = checked(harness.client.get(f"/api/results/{learned['id']}", headers=harness.headers["reviewer"]))
    identifier = detail["normalized"]["learned_reference_id"]
    child = checked(
        harness.client.post(f"/api/runs/{first['id']}/reprocess", json={}, headers=harness.headers["admin"]),
        201,
    )
    assert harness.worker.work_once()
    assert harness.results(child["id"])[0]["method"] == "DIRECCION_VALIDADA"
    path = f"/api/address-memory/{identifier}/revoke"
    payload = {"reason": "Referencia sintética revocada para prueba"}
    checked(harness.client.post(path, json=payload, headers=harness.headers["analyst"]), 403)
    checked(harness.client.post(path, json=payload, headers=harness.headers["reviewer"]))
    other = harness.run(data("C"))
    assert harness.results(other["id"])[0]["resolution"] != "ACEPTADO_AUTOMATICO"
    assert harness.results(child["id"])[0]["method"] == "DIRECCION_VALIDADA"


def test_failed_learning_rolls_back_review_and_memory(harness):
    first = harness.run(data())
    item = harness.results(first["id"])[0]
    checked(
        harness.decide(
            item,
            "manual_point",
            latitude=-12,
            longitude=-77,
            precision="DESCONOCIDA",
            evidence="Evidencia sintética",
            learn_address=True,
        ),
        422,
    )
    current = harness.results(first["id"])[0]
    assert current["revision"] == item["revision"]
    with harness.sessions() as db:
        assert db.scalar(select(AddressMemory)) is None


def test_area_candidate_retains_geometry_in_review_memory_and_export(harness):
    first = harness.run(data())
    item = harness.results(first["id"])[0]
    geometry = {"type": "LineString", "coordinates": [[-77.03, -12.04], [-77.031, -12.041]]}
    with harness.sessions() as db:
        location = db.get(Location, item["id"])
        location.candidates = [
            {
                "id": "line",
                "product": "AREA_TRAMO",
                "precision": "VIA",
                "method": "VIA_JURISDICCION",
                "geometry": geometry,
                "latitude": None,
                "longitude": None,
            }
        ]
        db.commit()
    reviewed = checked(harness.decide(item, "accept_candidate", candidate_id="line", learn_address=True))
    assert reviewed["geometry"] == geometry
    assert reviewed["latitude"] is reviewed["longitude"] is None
    second = harness.run(data("B"))
    reused = harness.results(second["id"])[0]
    assert reused["product"] == "AREA_TRAMO"
    assert second["counts_by_product"] == {"AREA_TRAMO": 1}
    export_id = harness.export(second["id"])
    assert harness.worker.work_once()
    row = harness.download_export(export_id)[0]
    assert json.loads(row["GEOPOL_geometry"]) == geometry
    assert row["GEOPOL_latitude"] == row["GEOPOL_longitude"] == ""
    assert row["GEOPOL_precision"] == "VIA"


def test_reprocess_changes_crs_only_when_explicit(harness):
    first = harness.run(data())
    child = checked(
        harness.client.post(
            f"/api/runs/{first['id']}/reprocess", json={"crs": None}, headers=harness.headers["admin"]
        ),
        201,
    )
    assert child["config"]["crs"] is None
    assert harness.worker.work_once()
    grandchild = checked(
        harness.client.post(f"/api/runs/{child['id']}/reprocess", json={}, headers=harness.headers["admin"]),
        201,
    )
    assert grandchild["config"]["crs"] is None


def test_cached_street_must_be_inside_new_independently_verified_area(harness):
    first = harness.run(data())
    item = harness.results(first["id"])[0]
    geometry = {"type": "LineString", "coordinates": [[-77.03, -12.04], [-77.031, -12.041]]}
    with harness.sessions() as db:
        location = db.get(Location, item["id"])
        location.candidates = [
            {
                "id": "line",
                "product": "AREA_TRAMO",
                "precision": "VIA",
                "method": "VIA_JURISDICCION",
                "geometry": geometry,
                "latitude": None,
                "longitude": None,
            }
        ]
        db.commit()
    checked(harness.decide(item, "accept_candidate", candidate_id="line", learn_address=True))
    with harness.sessions() as db:
        normalized = db.get(Location, item["id"]).normalized
        for offset, expected in ((0, "ACEPTADO_AUTOMATICO"), (1, "REVISION_REQUERIDA")):
            polygon = {
                "type": "Polygon",
                "coordinates": [
                    [
                        [longitude + offset, latitude]
                        for longitude, latitude in [
                            [-77.04, -12.05],
                            [-77.02, -12.05],
                            [-77.02, -12.03],
                            [-77.04, -12.03],
                            [-77.04, -12.05],
                        ]
                    ]
                ],
            }
            resolved = {
                "resolution": "ACEPTADO_AUTOMATICO",
                "product": "AREA_TRAMO",
                "precision": "NUCLEO",
                "method": "NUCLEO_URBANO",
                "geometry": polygon,
                "latitude": None,
                "longitude": None,
                "candidates": [],
                "attempts": [],
            }
            result = resolve_memory(db, normalized, resolved, time.time())
            assert result["resolution"] == expected
            if expected == "REVISION_REQUERIDA":
                assert result["geometry"] is result["latitude"] is result["longitude"] is None


def test_ranked_search_finds_names_beyond_old_first_500_and_explicit_alias(harness):
    with harness.sessions() as db:
        db.add(Catalog(id="catalog", name="Synthetic", version="1", source="synthetic", sha256="x"))
        db.flush()
        for index in range(520):
            name = f"SIN RELACION {index}"
            db.add(
                Feature(
                    id=f"{index:05}",
                    catalog_id="catalog",
                    external_id=str(index),
                    kind="door",
                    ubigeo="150101",
                    search_key=name,
                    payload={"name": name, "id": str(index)},
                )
            )
        db.add(
            Feature(
                id="99999",
                catalog_id="catalog",
                external_id="target",
                kind="door",
                ubigeo="150101",
                search_key="DEMOSTRACION",
                payload={"id": "target", "aliases": ["AV ANTIGUA"], "street_name": "DEMOSTRACION"},
            )
        )
        db.commit()
    search = ReferenceSearch(harness.sessions)
    matches, truncated = search.lookup("catalog", "150101", ("DEMOSTRACIOZ",))
    assert [feature["id"] for feature in matches] == ["target"]
    assert not truncated
    matches, truncated = search.lookup("catalog", "150101", ("ANTIGUA",))
    assert [feature["id"] for feature in matches] == ["target"]
    assert not truncated
