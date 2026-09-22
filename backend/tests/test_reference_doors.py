"""Synthetic integration of dictionary staging, explicit metadata and catalog output."""

import csv
import hashlib
import json

import pytest

from geopol.catalogs import read_catalog
from geopol.domain.matching import resolve_location
from geopol.reference_doors import main, prepare_doors


def record(**changes):
    return {
        "UBIGEO": "010101",
        "CODCCPP": "0001",
        "AREA": "1",
        "CATVIA": "4",
        "NOMVIA": "Prueba sintética",
        "P17": "0012",
        "P17_A": "B",
        "P13_1": "-6.25",
        "P13_2": "-77.85",
        **changes,
    }


def fixture(tmp_path, rows=None):
    rows = rows or [record()]
    source = tmp_path / "synthetic.csv"
    fields = list(dict.fromkeys(field for row in rows for field in row))
    with source.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    dictionary = tmp_path / "synthetic-dictionary.txt"
    dictionary.write_text("Synthetic field dictionary", encoding="utf-8")
    return source, {
        "dictionary_path": dictionary,
        "street_types": {"4": "CALLE"},
        "source": "SYNTHETIC PROVIDER",
        "version": "synthetic-v1",
        "crs": "EPSG:4326",
    }


def staged(output):
    return [json.loads(line) for line in (output / "staging.jsonl").read_text(encoding="utf-8").splitlines()]


def test_missing_crs_preserves_every_row_and_never_emits_geojson(tmp_path):
    source, options = fixture(tmp_path, [record(EXTRA="preserved"), record(P17="<Null>")])
    options["crs"] = None
    output = tmp_path / "prepared"
    before = source.read_bytes()
    report = prepare_doors(source, output, **options)
    rows = staged(output)
    assert report["source_rows"] == len(rows) == 2
    assert report["numbered_address_rows"] == 1
    assert report["metadata_blockers"] == ["CRS_NOT_CONFIRMED"]
    assert report["catalog_features"] == 0
    assert not (output / "catalog.geojson").exists()
    assert rows[0]["raw"]["EXTRA"] == "preserved"
    assert rows[1]["raw"]["P17"] == "<Null>"
    assert [r["source_ordinal"] for r in rows] == [1, 2]
    assert all(not r["catalog_eligible"] for r in rows)
    assert rows[0]["normalized"]["latitude"] == -6.25
    assert rows[0]["normalized"]["longitude"] == -77.85
    assert "geometry" not in rows[0]
    assert source.read_bytes() == before
    assert hashlib.sha256(before).hexdigest() == report["input_sha256"]


def test_explicit_metadata_exports_point_with_provenance_and_domain_compatibility(tmp_path):
    source, options = fixture(tmp_path)
    output = tmp_path / "prepared"
    report = prepare_doors(source, output, **options)
    payload = (output / "catalog.geojson").read_bytes()
    features = list(read_catalog(payload, "catalog.geojson", "fallback", "fallback"))
    assert report["catalog_features"] == len(features) == 1
    assert hashlib.sha256(payload).hexdigest() == report["catalog_sha256"]
    door = features[0]
    assert door["door_number"] == "0012B"
    assert door["geometry"] == {"type": "Point", "coordinates": [-77.85, -6.25]}
    assert door["source"] == options["source"]
    assert door["version"] == options["version"]
    assert door["source_sha256"] == report["input_sha256"]
    assert door["dictionary_sha256"] == report["dictionary_sha256"]
    assert door["source_ordinal"] == 1
    boundary = {
        "id": "synthetic-boundary",
        "kind": "boundary",
        "ubigeo": "010101",
        "geometry": {
            "type": "Polygon",
            "coordinates": [[[-78, -7], [-77, -7], [-77, -6], [-78, -6], [-78, -7]]],
        },
        "crs": "EPSG:4326",
        "source": "SYNTHETIC",
        "version": "1",
    }
    result = resolve_location(
        {
            "ubigeo": "010101",
            "street_name": "PRUEBA SINTETICA",
            "street_type": "CALLE",
            "door_number": "0012B",
        },
        [boundary, door],
        True,
    )
    assert result["resolution"] == "ACEPTADO_AUTOMATICO"
    assert result["precision"] == "PUERTA" and result["geometry"] == door["geometry"]
    assert not report["geocoding_performed"] and not report["database_imported"]


def test_letter_disambiguates_keys_but_conflicting_points_remain_staged(tmp_path):
    source, options = fixture(
        tmp_path,
        [record(P17_A="A"), record(P17_A="A", P13_2="-77.86"), record(P17_A="B")],
    )
    output = tmp_path / "prepared"
    report = prepare_doors(source, output, **options)
    rows = staged(output)
    assert report["source_rows"] == 3
    assert report["conflicting_address_keys"] == 1 and report["conflicting_address_rows"] == 2
    assert [r["status"] for r in rows] == ["ADDRESS_CONFLICT", "ADDRESS_CONFLICT", "CATALOG_ELIGIBLE"]
    assert report["catalog_features"] == 1
    assert rows[0]["conflict_group"] == rows[1]["conflict_group"]
    assert rows[0]["raw"]["P13_2"] != rows[1]["raw"]["P13_2"]
    document = json.loads((output / "catalog.geojson").read_text(encoding="utf-8"))
    assert document["features"][0]["properties"]["door_number"] == "0012B"


@pytest.mark.parametrize("field", ["source", "version", "dictionary_path", "street_types"])
def test_missing_metadata_or_domain_never_silently_activates_points(tmp_path, field):
    source, options = fixture(tmp_path)
    options[field] = None
    output = tmp_path / "prepared"
    report = prepare_doors(source, output, **options)
    assert report["catalog_features"] == 0
    assert not (output / "catalog.geojson").exists()
    if field == "street_types":
        assert report["issue_row_counts"]["CAT_VIA_DOMAIN_UNCONFIRMED"] == 1


@pytest.mark.parametrize("crs", ["EPSG:32718", "EPSG:4267", "4326", "WGS84"])
def test_unsupported_or_implicit_crs_does_not_write_output(tmp_path, crs):
    source, options = fixture(tmp_path)
    options["crs"] = crs
    output = tmp_path / "prepared"
    with pytest.raises(ValueError):
        prepare_doors(source, output, **options)
    assert not output.exists()


def test_existing_output_is_not_overwritten(tmp_path):
    source, options = fixture(tmp_path)
    output = tmp_path / "prepared"
    output.mkdir()
    marker = output / "prior.json"
    marker.write_text("prior output", encoding="utf-8")
    with pytest.raises(ValueError):
        prepare_doors(source, output, **options)
    assert marker.read_text(encoding="utf-8") == "prior output"


def test_unrelated_spreadsheet_schema_is_rejected_before_output(tmp_path):
    source = tmp_path / "unrelated.csv"
    source.write_text("UBIGEO,NAME\n010101,SYNTHETIC\n", encoding="utf-8")
    with pytest.raises(ValueError):
        prepare_doors(source, tmp_path / "prepared")
    assert not (tmp_path / "prepared").exists()


def test_schema_validation_and_mapper_use_the_same_header_rules(tmp_path):
    row = record()
    row["P13 1"] = row.pop("P13_1")
    source, options = fixture(tmp_path, [row])
    with pytest.raises(ValueError):
        prepare_doors(source, tmp_path / "prepared", **options)
    assert not (tmp_path / "prepared").exists()


def test_explicit_street_types_keep_distinct_address_keys(tmp_path):
    source, options = fixture(
        tmp_path,
        [
            record(CATVIA="", NOMVIA="AV. PRUEBA", P13_2="-77.84"),
            record(CATVIA="", NOMVIA="CALLE PRUEBA", P13_2="-77.85"),
        ],
    )
    options["street_types"] = None
    report = prepare_doors(source, tmp_path / "prepared", **options)
    assert report["conflicting_address_keys"] == 0
    assert report["catalog_features"] == 2


def test_console_output_contains_only_aggregates(tmp_path, capsys):
    source, options = fixture(tmp_path, [record(NOMVIA="Private synthetic street")])
    main(
        [
            "--input",
            str(source),
            "--output",
            str(tmp_path / "prepared"),
            "--dictionary",
            str(options["dictionary_path"]),
        ]
    )
    output = capsys.readouterr().out
    assert "Private synthetic street" not in output
    assert "-77.85" not in output
    assert "SYNTHETIC PROVIDER" not in output
    assert json.loads(output)["source_rows"] == 1
