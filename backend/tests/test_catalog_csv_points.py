"""CSV reference axes preserve the same real-point contract as GeoJSON."""

import csv
import io
import json

import pytest

from geopol.catalogs import read_catalog
from geopol.domain.matching import resolve_location
from test_domain_matching import boundary, normalized


def load(**overrides):
    values = {
        "id": "synthetic-csv",
        "kind": "door",
        "ubigeo": "150101",
        "street_type": "AVENIDA",
        "street_name": "LAS FLORES",
        "door_number": "123",
        "latitude": "-12.05",
        "longitude": "-77.1",
        **overrides,
    }
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=list(values))
    writer.writeheader()
    writer.writerow(values)
    return list(read_catalog(stream.getvalue().encode(), "synthetic.csv", "SYNTHETIC", "1"))[0]


@pytest.mark.parametrize("kind", ["door", "intersection"])
def test_explicit_csv_point_reference_becomes_exact_source_geometry(kind):
    feature = load(kind=kind)
    assert feature["geometry"] == {"type": "Point", "coordinates": [-77.1, -12.05]}
    assert feature["geometry_transform"] == "point_from_explicit_reference_coordinates"
    assert (feature["source"], feature["version"], feature["crs"]) == ("SYNTHETIC", "1", "EPSG:4326")


def test_csv_door_is_usable_without_input_crs_confirmation():
    result = resolve_location(normalized(crs=None), [load(), boundary()], True)
    assert result["resolution"] == "ACEPTADO_AUTOMATICO"
    assert result["product"] == "PUNTO"
    assert result["latitude"] == -12.05
    assert result["geometry"] == load()["geometry"]


@pytest.mark.parametrize("role", ["mapped_poi", "entrance"])
def test_csv_site_requires_explicit_actual_point_role(role):
    feature = load(kind="site", point_role=role, name="PARQUE SINTETICO")
    result = resolve_location(normalized(location_original="PARQUE SINTETICO"), [feature, boundary()], True)
    assert result["resolution"] == "ACEPTADO_AUTOMATICO"
    assert result["product"] == "PUNTO"


@pytest.mark.parametrize("kind,role", [("block", ""), ("nucleus", ""), ("site", ""), ("site", "centroid")])
def test_csv_axes_do_not_manufacture_geometry_for_areas_or_unconfirmed_sites(kind, role):
    feature = load(kind=kind, point_role=role)
    assert "geometry" not in feature


@pytest.mark.parametrize(
    "axes",
    [{"latitude": "nan"}, {"latitude": "inf"}, {"longitude": "181"}, {"latitude": "-91"}, {"longitude": ""}],
)
def test_invalid_or_incomplete_axes_never_generate_point(axes):
    with pytest.raises(ValueError):
        load(**axes)


def test_explicit_geometry_and_per_feature_provenance_remain_intact():
    geometry = {"type": "Point", "coordinates": [-77.1, -12.05]}
    feature = load(geometry=json.dumps(geometry), source="SYNTHETIC_PROVIDER", version="provider-v2")
    assert feature["geometry"] == geometry
    assert "geometry_transform" not in feature
    assert (feature["source"], feature["version"]) == ("SYNTHETIC_PROVIDER", "provider-v2")
