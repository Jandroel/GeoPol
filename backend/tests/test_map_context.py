import json

from geopol.api import map_context
from test_api import harness as harness


def seed_context(harness, extra_features=()):
    def feature(identifier, kind, ubigeo, geometry):
        return {
            "type": "Feature",
            "id": identifier,
            "geometry": geometry,
            "properties": {"kind": kind, "ubigeo": ubigeo, "name": "CONTEXTO SINTÉTICO"},
        }

    polygon = {
        "type": "Polygon",
        "coordinates": [[[-78, -13], [-76, -13], [-76, -11], [-78, -11], [-78, -13]]],
    }
    line = {"type": "LineString", "coordinates": [[-77, -12], [-77.01, -12.01]]}
    document = {
        "type": "FeatureCollection",
        "features": [
            feature("boundary", "boundary", "150101", polygon),
            feature("street", "street", "150101", line),
            feature("other-district", "boundary", "150102", polygon),
            *extra_features,
        ],
    }
    response = harness.client.post(
        "/api/references",
        headers=harness.headers["admin"],
        data={"name": "Contexto sintético", "version": "test", "source": "OpenStreetMap SINTÉTICO"},
        files={"file": ("context.geojson", json.dumps(document).encode(), "application/geo+json")},
    )
    assert response.status_code == 201, response.text
    catalog_id = response.json()["id"]
    return harness.run(reference_id=catalog_id), catalog_id


def test_context_requires_auth_and_uses_the_run_catalog_and_district(harness):
    run, catalog_id = seed_context(harness)
    url = f"/api/runs/{run['id']}/map-context?ubigeo=150101"
    assert harness.client.get(url).status_code == 401
    response = harness.client.get(url, headers=harness.headers["analyst"])
    assert response.status_code == 200
    data = response.json()
    assert data["reference_id"] == catalog_id
    assert data["context_only"] is True
    assert data["truncated"] is False
    assert {item["id"] for item in data["features"]} == {"boundary", "street"}
    assert data["sources"] == ["OpenStreetMap SINTÉTICO"]
    assert "person_name" not in response.text
    assert "complaint_id" not in response.text


def test_missing_reference_and_display_limits_are_explicit(harness, monkeypatch):
    no_reference = harness.run()
    empty = harness.client.get(
        f"/api/runs/{no_reference['id']}/map-context?ubigeo=150101", headers=harness.headers["admin"]
    ).json()
    assert empty["features"] == [] and empty["reference_id"] is None
    run, _ = seed_context(harness)
    url = f"/api/runs/{run['id']}/map-context?ubigeo=150101"
    monkeypatch.setattr(map_context, "MAX_CONTEXT_FEATURES", 1)
    data = harness.client.get(url, headers=harness.headers["admin"]).json()
    assert len(data["features"]) == 1 and data["truncated"] is True
    monkeypatch.setattr(map_context, "MAX_CONTEXT_BYTES", 1)
    data = harness.client.get(url, headers=harness.headers["admin"]).json()
    assert data["features"] == [] and data["truncated"] is True


def test_point_sites_do_not_consume_the_visible_geometry_limit(harness, monkeypatch):
    points = [
        {
            "type": "Feature",
            "id": f"a-site-{index:04}",
            "geometry": {"type": "Point", "coordinates": [-77, -12]},
            "properties": {"kind": "site", "ubigeo": "150101", "name": "SITIO SINTÉTICO"},
        }
        for index in range(505)
    ]
    run, _ = seed_context(harness, points)
    monkeypatch.setattr(map_context, "MAX_CONTEXT_FEATURES", 2)
    data = harness.client.get(
        f"/api/runs/{run['id']}/map-context?ubigeo=150101", headers=harness.headers["admin"]
    ).json()
    assert {item["id"] for item in data["features"]} == {"boundary", "street"}
    assert data["truncated"] is False
