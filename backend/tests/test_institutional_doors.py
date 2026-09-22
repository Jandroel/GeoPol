"""Synthetic records only: dictionary mappings do not establish a CRS or provenance."""

from copy import deepcopy
from decimal import Decimal

import pytest

from geopol.domain.institutional_doors import map_door_record


def record(**changes):
    return {
        "UBIGEO": "010101",
        "CODCCPP": "0001",
        "AREA": 1,
        "CATVIA": 4,
        "NOMVIA": "Prueba sintética",
        "P17": "0012",
        "P17_A": "B",
        "P13_1": -6.25,
        "P13_2": -77.85,
        **changes,
    }


def codes(result):
    return {item["code"] for item in result["issues"]}


def test_maps_confirmed_dictionary_preserving_raw_and_distinct_manzanas():
    raw = record(MANZANA="0007", P21="A", P22="03", P23_K="001.5", NUCLEO="Núcleo sintético")
    before = deepcopy(raw)
    result = map_door_record(raw, 8, {4: "CALLE"})
    normalized = result["normalized"]
    assert result["raw"] == before == raw
    assert result["raw"] is not raw
    assert result["source_ordinal"] == 8
    assert normalized["reference_manzana_code"] == "0007"
    assert normalized["manzana_code"] == "A"
    assert normalized["lot_number"] == "03"
    assert normalized["kilometer"] == "001.5"
    assert normalized["door_number"] == "0012B"
    assert normalized["street_name"] == "PRUEBA SINTETICA"
    assert normalized["urban_core"] == "NUCLEO SINTETICO"
    assert normalized["latitude"] == -6.25
    assert normalized["longitude"] == -77.85
    assert "crs" not in normalized and "geometry" not in result
    assert not result["address_ready"]
    result["raw"]["P21"] = "modified copy"
    assert raw == before


def test_structure_can_be_ready_without_claiming_geographic_acceptance():
    result = map_door_record(record(MANZANA="0007"), 1, {4: "CL."})
    assert result["address_ready"]
    assert not result["issues"]
    assert result["normalized"]["street_type"] == "CALLE"
    assert "status" not in result and "crs" not in result


@pytest.mark.parametrize("missing", [None, "", "NULL", "<Null>", " < Null > ", "N/A", float("nan")])
def test_absence_markers_do_not_become_address_components(missing):
    result = map_door_record(record(P17=missing, P17_A=missing, NOM_VIA_R=missing), 1, {4: "CALLE"})
    assert result["normalized"]["door_number"] is None
    assert result["normalized"]["address_alternative_r"]["NOM_VIA_R"] is None
    assert not result["address_ready"]


@pytest.mark.parametrize(
    "value,expected", [(10101, "010101"), (10101.0, "010101"), ("10101.0", "010101"), ("010101", "010101")]
)
def test_restores_only_integral_identifiers(value, expected):
    result = map_door_record(record(UBIGEO=value, CODCCPP=1.0), 1, {4: "CALLE"})
    assert result["normalized"]["ubigeo"] == expected
    assert result["normalized"]["center_code"] == "0001"
    assert result["raw"]["UBIGEO"] == value


@pytest.mark.parametrize("value", [True, 10101.5, "0101017", "010A01", "-10101", "1E4"])
def test_rejects_ambiguous_or_invalid_ubigeo_without_truncation(value):
    result = map_door_record(record(UBIGEO=value), 1, {4: "CALLE"})
    assert result["normalized"]["ubigeo"] is None
    assert "UBIGEO_MISSING_OR_INVALID" in codes(result)
    assert not result["address_ready"]


def test_category_codes_are_not_inferred_from_sample_or_from_explicit_name():
    result = map_door_record(record(NOMVIA="Av. Prueba sintética"), 1)
    assert result["normalized"]["street_type"] == "AVENIDA"
    assert result["normalized"]["street_type_code"] == "4"
    assert "CAT_VIA_DOMAIN_UNCONFIRMED" in codes(result)
    assert not result["address_ready"]
    assert map_door_record(record(CATVIA=None, NOMVIA="Av. Prueba sintética"), 1)["address_ready"]


def test_conflicting_or_invalid_category_mapping_blocks_eligibility():
    conflict = map_door_record(record(NOMVIA="Av. Prueba sintética"), 1, {4: "CALLE"})
    assert "STREET_TYPE_CONFLICT" in codes(conflict)
    assert not conflict["address_ready"]
    invalid = map_door_record(record(), 1, {4: "22"})
    assert "STREET_TYPE_MAPPING_INVALID" in codes(invalid)
    assert not invalid["address_ready"]


@pytest.mark.parametrize("mapped_type", ["INVALIDO", "CAMINO", "OTROS", "OTRO", "BOULEVARD"])
def test_unsupported_textual_category_mapping_never_becomes_ready(mapped_type):
    result = map_door_record(record(), 1, {4: mapped_type})
    assert "STREET_TYPE_MAPPING_INVALID" in codes(result)
    assert result["normalized"]["street_type"] is None
    assert not result["address_ready"]


@pytest.mark.parametrize("number", ["SN", "S/N", "SIN NÚMERO", "S N"])
def test_no_number_is_not_a_door(number):
    result = map_door_record(record(P17=number), 1, {4: "CALLE"})
    assert result["normalized"]["door_number"] is None
    assert {"DOOR_NUMBER_ABSENT", "DOOR_LETTER_WITHOUT_NUMBER"} <= codes(result)
    assert not result["address_ready"]


@pytest.mark.parametrize(
    "base,letter,expected",
    [("0012-A", "A", "0012A"), ("0012A", None, "0012A"), (12.0, "A", "12A"), ("0012", "AB", "0012AB")],
)
def test_preserves_leading_zeros_and_door_suffix_without_duplication(base, letter, expected):
    result = map_door_record(record(P17=base, P17_A=letter), 1, {4: "CALLE"})
    assert result["normalized"]["door_number"] == expected
    assert result["address_ready"]


@pytest.mark.parametrize(
    "base,letter,issue",
    [
        ("0012A", "B", "DOOR_LETTER_CONFLICT"),
        (None, "A", "DOOR_LETTER_WITHOUT_NUMBER"),
        ("12", "A-1", "DOOR_LETTER_INVALID"),
        ("12/14", None, "DOOR_NUMBER_INVALID"),
    ],
)
def test_does_not_fabricate_a_door_from_conflicting_or_ambiguous_fields(base, letter, issue):
    result = map_door_record(record(P17=base, P17_A=letter), 1, {4: "CALLE"})
    assert result["normalized"]["door_number"] is None
    assert issue in codes(result)
    assert not result["address_ready"]


def test_coordinate_axes_are_explicit_and_out_of_range_values_remain_auditable():
    result = map_door_record(record(P13_1="-6,25", P13_2=Decimal("-77.85")), 1, {4: "CALLE"})
    assert result["normalized"]["coordinates_valid"]
    assert result["normalized"]["latitude"] == -6.25
    assert result["normalized"]["longitude"] == -77.85
    outside = map_door_record(record(P13_1=900001), 1, {4: "CALLE"})
    assert outside["normalized"]["latitude"] == 900001
    assert not outside["normalized"]["coordinates_valid"]
    assert "COORDINATE_OUT_OF_RANGE" in codes(outside)
    assert not outside["address_ready"]


@pytest.mark.parametrize("value", [True, "not a coordinate", "Infinity", float("inf")])
def test_nonfinite_or_non_numeric_axes_are_not_coordinates(value):
    result = map_door_record(record(P13_1=value), 1, {4: "CALLE"})
    assert result["normalized"]["latitude"] is None
    assert not result["normalized"]["coordinates_valid"]
    assert "COORDINATE_MISSING_OR_INVALID" in codes(result)


@pytest.mark.parametrize(
    "fields,issue",
    [
        ({"NOM_VIA_R": "Vía alternativa", "CATEGORIA_VIA_R": 1}, "ALTERNATIVE_R_REQUIRES_MAPPING"),
        ({"NOMVIA_RES": "Vía residencial", "CATVIA_RES": 2}, "RESIDENTIAL_ADDRESS_REQUIRES_MAPPING"),
        ({"CATVIA_O": "Otro tipo"}, "OTHER_STREET_TYPE_REQUIRES_MAPPING"),
        ({"P21": "A"}, "MANZANA_LOT_CONTEXT_REQUIRES_MAPPING"),
        ({"P22": "01"}, "MANZANA_LOT_CONTEXT_REQUIRES_MAPPING"),
        ({"P23_K": "003"}, "KILOMETER_CONTEXT_REQUIRES_MAPPING"),
        ({"REFERENCIA": "Frente al parque sintético"}, "RELATIVE_ADDRESS_REQUIRES_MAPPING"),
        ({"AREA": 2}, "RURAL_CONTEXT_REQUIRES_MAPPING"),
    ],
)
def test_retains_alternate_components_without_choosing_or_silently_discarding_them(fields, issue):
    result = map_door_record(record(**fields), 1, {4: "CALLE"})
    assert issue in codes(result)
    assert not result["address_ready"]
    assert result["normalized"]["street_name"] == "PRUEBA SINTETICA"
    for field, value in fields.items():
        assert result["raw"][field] == value


def test_alternative_groups_never_fill_missing_nomvia_and_keep_source_fieldnames():
    result = map_door_record(record(NOMVIA=None, NOM_VIA_R="Una vía", NOMVIA_RES="Otra vía"), 1, {4: "CALLE"})
    normalized = result["normalized"]
    assert normalized["street_name"] is None
    assert normalized["address_alternative_r"]["NOM_VIA_R"] == "UNA VIA"
    assert normalized["residential_address"]["NOMVIA_RES"] == "OTRA VIA"
    assert not result["address_ready"]


def test_issues_do_not_echo_source_values():
    result = map_door_record(record(P17="private sentinel", NOMVIA="Frente al private sentinel"), 1)
    assert "sentinel" not in str(result["issues"])


@pytest.mark.parametrize("ordinal", [0, -1, True, 1.5])
def test_rejects_invalid_source_ordinals(ordinal):
    with pytest.raises(ValueError, match="positive integer"):
        map_door_record(record(), ordinal)
