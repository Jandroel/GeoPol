import pytest

from geopol.domain.normalization import normalize_record, suggest_mapping, valid_pair


def test_sidpol_mapping_does_not_misidentify_police_station_or_legacy_axes():
    mapping = suggest_mapping(["DIRECCION", "UBICACION", "xx", "yy", "lat_hecho", "long_hecho", "UBIGEO_CIA", "UBIGEO_HECHO", "VIA"])
    assert mapping["location_original"] == "UBICACION"
    assert mapping["latitude"] == "xx"
    assert mapping["longitude"] == "yy"
    assert mapping["ubigeo"] == "UBIGEO_HECHO"
    assert mapping["street_type"] == "VIA"
    assert "street_name" not in mapping
    assert "DIRECCION" not in mapping.values()


def test_normalizes_without_destroying_original_or_assuming_numeric_name_policy():
    raw = {"ID_DENUNCIA": 12, "UBICACION": "  Av. Uno   124-B ", "UBIGEO_HECHO": 40112}
    result = normalize_record(raw)
    assert result["complaint_id"] == "12"
    assert result["location_original"] == raw["UBICACION"]
    assert result["street_type"] == "AVENIDA"
    assert result["street_name"] == "UNO"
    assert result["door_number"] == "124-B"
    assert result["ubigeo"] == "040112"
    assert "UBIGEO_REQUIERE_VALIDACION_CATALOGO" in result["warnings"]
    assert raw["UBICACION"] == "  Av. Uno   124-B "


def test_calle_one_is_street_name_and_not_door_one():
    result = normalize_record({"UBICACION": "CALLE 1"})
    assert result["street_name"] == "1"
    assert result["door_number"] is None


def test_sidpol_category_and_invalid_block_do_not_obstruct_text_extraction():
    result = normalize_record({"UBICACION": "CALLE LOS PINOS 123", "VIA": "Otros", "CUADRA": "NULL"})
    assert result["street_name"] == "LOS PINOS"
    assert result["street_type"] == "CALLE"
    assert result["door_number"] == "123"
    assert result["block_number"] is None
    assert result["legacy"]["block_number_original"] == "NULL"
    assert result["legacy"]["street_type_original"] == "Otros"


def test_block_never_infers_door_and_sn_never_becomes_zero():
    block = normalize_record({"UBICACION": "AV. LAS FLORES CUADRA 5"})
    assert block["street_name"] == "LAS FLORES"
    assert block["block_number"] == "5"
    assert block["door_number"] is None
    sn = normalize_record({"UBICACION": "JR LOS PINOS S/N"})
    assert sn["street_name"] == "LOS PINOS"
    assert sn["door_number"] is None
    assert "PUERTA_SIN_NUMERO" in sn["warnings"]


@pytest.mark.parametrize("latitude,longitude,expected", [
    ("-12.05", "-77.10", (-12.05, -77.1)),
    ("-12° 3' 0\" S", "77° 6' 0\" O", (-12.05, -77.1)),
    ("12° 3' 0 S", "-77° 6' 0 W", (-12.05, -77.1)),
    ("-12 N", "-77 W", None),
    ("12° 61' 0 S", "77 W", None),
    ("nan", "-77", None),
    (float("inf"), -77, None),
    (-91, -77, None),
    (-12, -181, None),
    (1e-6, "-7.7E+1", (1e-6, -77)),
])
def test_coordinate_signs_ranges_and_hemispheres(latitude, longitude, expected):
    assert valid_pair(latitude, longitude) == expected


@pytest.mark.parametrize("location", [
    "LAT: -12.05 LONG: -77.1",
    "LUGAR (-12.05, -77.1)",
    "12° 3' 0\" S 77° 6' 0\" O",
])
def test_extracts_textual_coordinates(location):
    result = normalize_record({"UBICACION": location})
    assert result["latitude"] == -12.05
    assert result["longitude"] == -77.1
    assert result["coordinate_origin"] == "TEXTO_SIDPOL"


def test_xx_is_latitude_and_yy_longitude():
    result = normalize_record({"xx": -12.05, "yy": -77.1})
    assert (result["latitude"], result["longitude"]) == (-12.05, -77.1)
    assert result["coordinate_origin"] == "PNP_ORIGINAL"


def test_forced_centroid_is_never_an_original_coordinate():
    result = normalize_record({"xx": -12.05, "yy": -77.1, "lat_hecho": -12.05,
                               "long_hecho": -77.1, "OBSERVACION": "GEO FORZADA AL CENTROIDE DE COMISARIA"})
    assert result["latitude"] is result["longitude"] is None
    assert result["coordinate_origin"] == "SUSTITUTO_HEREDADO"
    assert result["legacy"]["lat_hecho"] == -12.05
    assert "COORDENADA_SUSTITUTA" in result["warnings"]


def test_legacy_final_axes_do_not_silently_fill_original_axes():
    result = normalize_record({"lat_hecho": -12.05, "long_hecho": -77.1})
    assert result["latitude"] is result["longitude"] is None
    assert "COORDENADA_FINAL_LEGADA_NO_ORIGINAL" in result["warnings"]


def test_text_coordinates_can_recover_after_ignoring_legacy_centroid():
    result = normalize_record({"UBICACION": "LAT: -12.05 LONG: -77.1", "FLAG_GEOREF": 3,
                               "xx": -12.2, "yy": -77.2})
    assert result["latitude"] == -12.05
    assert result["coordinate_origin"] == "TEXTO_SIDPOL"
    assert result["legacy"]["FLAG_GEOREF"] == 3


def test_preserves_conflicting_textual_coordinate_and_legacy_flags():
    result = normalize_record({"xx": -12.1, "yy": -77.1, "UBICACION": "-12.2, -77.2",
                               "FLAG_GEOREF": 1, "FLAG_CALIDAD": 2, "NIVEL_CRUCE": 3})
    assert result["text_coordinates"] == {"latitude": -12.2, "longitude": -77.2}
    assert "COORDENADAS_CONTRADICTORIAS" in result["warnings"]
    assert result["legacy"] == {"FLAG_GEOREF": 1, "FLAG_CALIDAD": 2, "NIVEL_CRUCE": 3}


def test_cross_and_relative_site_remain_explicit():
    cross = normalize_record({"UBICACION": "AV. LAS FLORES CON JR. LOS PINOS"})
    assert cross["street_name"] == "LAS FLORES"
    assert cross["cross_street"] == "LOS PINOS"
    site = normalize_record({"UBICACION": "FRENTE AL MERCADO LA UNION"})
    assert site["site_name"] == "MERCADO LA UNION"
    assert "REFERENCIA_RELATIVA" in site["warnings"]


@pytest.mark.parametrize("location,district,street,door", [
    ("FRONTIS DEL INMUEBLE EN CALLE LA PAZ NRO. 110 URB EL SOL", "", "LA PAZ", "110"),
    ("AV. NUEVA N°.1734 - DISTRITO AZUL", "DISTRITO AZUL", "NUEVA", "1734"),
    ("PROLONGACION LUNA 337 DISTRITO AZUL", "DISTRITO AZUL", "LUNA", "337"),
    ("ALFA BETA 201, CIUDAD 15079", "", "ALFA BETA", "201"),
    ("AV 28 DE JULIO 567", "", "28 DE JULIO", "567"),
])
def test_address_with_prefix_or_declared_district_keeps_street_components(location, district, street, door):
    result = normalize_record({"location_original": location, "district": district})
    assert result["street_name"] == street
    assert result["door_number"] == door


def test_multiple_textual_points_require_review_and_cross_separator_is_contextual():
    result = normalize_record({"location_original": "-12.1, -77.1 y -12.2, -77.2"})
    assert "COORDENADAS_CONTRADICTORIAS" in result["warnings"]
    cross = normalize_record({"location_original": "AV ALFA Y JR BETA"})
    assert cross["street_name"] == "ALFA"
    assert cross["cross_street"] == "BETA"


def test_origin_conflict_cannot_disappear_when_deduplicating_normalized_locations():
    valid = normalize_record({"xx": -12.1, "yy": -77.1, "FLAG_GEOREF": 1})
    conflict = normalize_record({"xx": -12.1, "yy": -77.1, "FLAG_GEOREF": 2})
    assert valid["decision_constraints"] == []
    assert conflict["decision_constraints"] == ["UBIGEO_CONFLICTIVO_ORIGEN"]


def test_worker_unit_key_keeps_decision_constraints_and_merges_only_compatible_evidence():
    from geopol.worker import unit_key

    original = normalize_record({"ID_DENUNCIA": "SYNTHETIC-A", "xx": -12.1, "yy": -77.1, "FLAG_GEOREF": 1})
    duplicate = normalize_record({"ID_DENUNCIA": "SYNTHETIC-A", "xx": -12.1, "yy": -77.1, "FLAG_GEOREF": 1, "PERSONA": "Otra relación sintética"})
    conflict = normalize_record({"ID_DENUNCIA": "SYNTHETIC-A", "xx": -12.1, "yy": -77.1, "FLAG_GEOREF": 2})
    assert unit_key(original, 1) == unit_key(duplicate, 2)
    assert unit_key(original, 1) != unit_key(conflict, 3)
