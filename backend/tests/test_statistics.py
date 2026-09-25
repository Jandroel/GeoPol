"""Statistics cover the complete selected run; map limits never change totals."""

from sqlalchemy import select

from geopol.models import Location, Run, uid
from test_api import harness as harness


def get_stats(harness, run_id, suffix=""):
    response = harness.client.get(
        f"/api/runs/{run_id}/statistics{suffix}", headers=harness.headers["analyst"]
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_statistics_aggregate_all_rows_after_map_budget(harness):
    run = harness.run()
    with harness.sessions() as db:
        for index in range(205):
            db.add(
                Location(
                    id=uid(),
                    run_id=run["id"],
                    unit_key=f"synthetic-{index}",
                    normalized={"district": "DISTRITO SINTETICO"},
                    ubigeo="150102",
                    source_row_count=1,
                    resolution="ACEPTADO_AUTOMATICO",
                    method="COORD_ORIGINAL",
                    precision="COORDENADA",
                    product="PUNTO",
                    latitude=-12.0,
                    longitude=-77.0,
                    quality_flag=1,
                    review_state="automatic",
                )
            )
        db.get(Run, run["id"]).source_rows += 205
        db.commit()
    result = get_stats(harness, run["id"], "?map_limit=2")
    assert result["totals"]["units"] == 207
    assert result["totals"]["source_rows"] == 208
    assert result["totals"]["mapped"] == 205
    assert result["map"]["shown"] == 2 and result["map"]["total"] == 205
    assert result["map"]["truncated"] is True
    assert result["map"]["layers"] == {"original": 205}
    district = next(item for item in result["districts"] if item["ubigeo"] == "150102")
    assert district["units"] == district["mapped"] == 205
    assert district["district"] == "DISTRITO SINTETICO"
    assert sum(item["units"] for item in result["resolutions"]) == 207


def test_map_only_contains_accepted_valid_geometry_and_no_area_centroid(harness):
    run = harness.run()
    with harness.sessions() as db:
        rows = list(db.scalars(select(Location).where(Location.run_id == run["id"])))
        rows[0].resolution = "REVISION_REQUERIDA"
        rows[0].latitude, rows[0].longitude = -12, -77
        rows[1].resolution = "ACEPTADO_AUTOMATICO"
        rows[1].precision, rows[1].method = "CUADRA", "CUADRA_CON_TIPO"
        rows[1].latitude, rows[1].longitude = -12, -77
        db.commit()
    result = get_stats(harness, run["id"])
    assert result["totals"]["accepted"] == 1
    assert result["totals"]["mapped"] == 0
    assert result["map"]["features"] == []
    with harness.sessions() as db:
        item = db.get(Location, rows[1].id)
        item.geometry = {"type": "LineString", "coordinates": [[-77, -12], [-77.001, -12.001]]}
        db.commit()
    result = get_stats(harness, run["id"])
    assert result["totals"]["mapped"] == 1
    assert result["map"]["features"][0]["geometry"]["type"] == "LineString"
    assert result["map"]["features"][0]["properties"]["layer"] == "reference"


def test_manual_layer_and_conflicting_district_names_are_explicit(harness):
    run = harness.run()
    with harness.sessions() as db:
        rows = list(db.scalars(select(Location).where(Location.run_id == run["id"])))
        for index, item in enumerate(rows):
            item.normalized = {"district": f"NOMBRE {index}"}
            item.resolution, item.manual = "ACEPTADO_MANUAL", True
            item.method, item.precision = "COORD_ORIGINAL", "COORDENADA"
            item.latitude, item.longitude = -12, -77
        db.commit()
    result = get_stats(harness, run["id"])
    assert result["map"]["layers"] == {"manual": 2}
    assert result["districts"][0]["district"] is None
    assert result["districts"][0]["name_conflict"] is True


def test_flag10_stays_excluded_and_other_runs_never_leak(harness):
    run, other = harness.run(), harness.run()
    with harness.sessions() as db:
        item = db.scalar(select(Location).where(Location.run_id == run["id"]))
        item.quality_flag, item.review_state, item.resolution = 10, "excluded", "EXCLUIDO_FLAG_10"
        item.latitude, item.longitude = -12, -77
        db.commit()
    result = get_stats(harness, run["id"])
    assert result["run_id"] != other["id"]
    assert result["totals"]["units"] == 2
    assert result["totals"]["excluded"] == 1
    assert result["totals"]["mapped"] == 0
    assert {"flag": 10, "units": 1} in result["flags"]


def test_statistics_requires_session_and_bounded_map_limit(harness):
    run = harness.run()
    assert harness.client.get(f"/api/runs/{run['id']}/statistics").status_code == 401
    for limit in (0, 5001):
        response = harness.client.get(
            f"/api/runs/{run['id']}/statistics?map_limit={limit}", headers=harness.headers["analyst"]
        )
        assert response.status_code == 422
