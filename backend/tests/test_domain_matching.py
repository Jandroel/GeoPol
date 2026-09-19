import pytest

from geopol.domain.matching import resolve_location
from geopol.domain.normalization import normalize_record


def normalized(**overrides):
    raw = {"location_original": "AV. LAS FLORES 123", "ubigeo": "150101", "crs": "EPSG:4326", **overrides}
    return normalize_record(raw)


def door(**overrides):
    return {
        "id": "d1",
        "kind": "door",
        "ubigeo": "150101",
        "street_type": "AVENIDA",
        "street_name": "LAS FLORES",
        "door_number": "123",
        "latitude": -12.05,
        "longitude": -77.1,
        "source": "SINTETICO",
        "version": "1",
        **overrides,
    }


def boundary(**overrides):
    return {
        "id": "b1",
        "kind": "boundary",
        "ubigeo": "150101",
        "source": "SINTETICO",
        "version": "1",
        "geometry": {
            "type": "Polygon",
            "coordinates": [[[-78, -13], [-76, -13], [-76, -11], [-78, -11], [-78, -13]]],
        },
        **overrides,
    }


def test_unique_exact_door_has_explainable_acceptance():
    result = resolve_location(normalized(), [door()], True)
    assert result["resolution"] == "ACEPTADO_AUTOMATICO"
    assert result["latitude"] == -12.05
    assert result["method"] == "PUERTA_CON_TIPO"
    assert "UBIGEO_COINCIDENTE" in result["candidates"][0]["evidence"]
    assert result["candidates"][0]["score_type"] == "SIMILITUD_TEXTUAL_NO_PROBABILIDAD"


@pytest.mark.parametrize("change", [{"crs": None}, {"ubigeo": None}])
def test_unknown_crs_or_territory_cannot_autoaccept(change):
    result = resolve_location(normalized(**change), [door()], True)
    assert result["resolution"] == "REVISION_REQUERIDA"
    assert result["latitude"] is result["longitude"] is None


def test_missing_reference_differs_from_complete_search_without_match():
    absent = resolve_location(normalized(), [], False)
    assert absent["resolution"] == "NO_EVALUABLE_REFERENCIA"
    missing_layer = resolve_location(normalized(), [boundary()], True)
    assert missing_layer["resolution"] == "NO_EVALUABLE_REFERENCIA"
    query = normalized()
    query["available_reference_kinds"] = ["door", "boundary"]
    no_match = resolve_location(query, [], True)
    assert no_match["resolution"] == "SIN_COINCIDENCIA"


def test_door_ambiguity_does_not_take_first_reference():
    result = resolve_location(normalized(), [door(), door(id="d2", latitude=-12.06)], True)
    assert result["resolution"] == "REVISION_REQUERIDA"
    assert "MULTIPLES_CANDIDATOS" in result["reason"]
    assert len(result["candidates"]) == 2


def test_fuzzy_ranking_always_requires_human_review():
    result = resolve_location(normalized(location_original="AV LAS FLOREZ 123"), [door()], True)
    assert result["resolution"] == "REVISION_REQUERIDA"
    assert result["candidates"][0]["score"] < 100


def test_number_name_equivalence_is_not_assumed():
    result = resolve_location(
        normalized(location_original="CALLE UNO 12"),
        [door(street_type="CALLE", street_name="1", door_number="12")],
        True,
    )
    assert result["resolution"] == "SIN_COINCIDENCIA"


def test_original_coordinate_without_boundary_is_review_even_without_catalogue():
    source = normalized(location_original="", latitude=-12.05, longitude=-77.1)
    result = resolve_location(source, [], False)
    assert result["resolution"] == "REVISION_REQUERIDA"
    assert "LIMITE_TERRITORIAL_NO_DISPONIBLE" in result["reason"]
    assert result["candidates"][0]["latitude"] == -12.05


def test_boundary_corroborates_original_coordinate_and_rejects_conflict():
    source = normalized(location_original="", latitude=-12.05, longitude=-77.1)
    assert resolve_location(source, [boundary()], True)["resolution"] == "ACEPTADO_AUTOMATICO"
    source["longitude"] = -70
    assert resolve_location(source, [boundary()], True)["resolution"] == "REVISION_REQUERIDA"


def test_boundary_edge_is_review():
    source = normalized(location_original="", latitude=-13, longitude=-77)
    result = resolve_location(source, [boundary()], True)
    assert result["resolution"] == "REVISION_REQUERIDA"
    assert "PUNTO_EN_LIMITE_TERRITORIAL" in result["reason"]


def test_reference_point_outside_declared_territory_cannot_autoaccept():
    result = resolve_location(normalized(), [door(latitude=-9), boundary()], True)
    assert result["resolution"] == "REVISION_REQUERIDA"
    assert "PUNTO_FUERA_UBIGEO" in result["reason"]


def test_truncated_lookup_never_autoaccepts_apparent_unique_candidate():
    source = normalized()
    source["reference_truncated"] = True
    result = resolve_location(source, [door()], True)
    assert result["resolution"] == "REVISION_REQUERIDA"
    assert "BUSQUEDA_REFERENCIAL_TRUNCADA" in result["reason"]


def test_block_result_preserves_approximate_precision():
    result = resolve_location(
        normalized(location_original="AV LAS FLORES CUADRA 5"),
        [door(kind="block", block_number="5", door_number=None)],
        True,
    )
    assert result["resolution"] == "REVISION_REQUERIDA"
    assert result["precision"] == "CUADRA"
    assert result["product"] == "DIRECCION_SIN_PUNTO"
    assert result["candidates"][0]["product"] == "AREA_TRAMO"


def test_cross_matches_reversed_order_but_connection_needs_verification():
    source = normalized(location_original="AV LAS FLORES CON JR LOS PINOS")
    feature = door(kind="intersection", street_name="LOS PINOS", cross_street="LAS FLORES", door_number=None)
    assert resolve_location(source, [feature], True)["resolution"] == "REVISION_REQUERIDA"
    feature["connects_at_grade"] = True
    assert resolve_location(source, [feature], True)["resolution"] == "ACEPTADO_AUTOMATICO"


def test_relative_site_is_never_precise_automatic_location():
    source = normalized(location_original="FRENTE AL MERCADO LA UNION")
    feature = door(kind="site", name="MERCADO LA UNION", street_name=None, door_number=None)
    result = resolve_location(source, [feature], True)
    assert result["resolution"] == "REVISION_REQUERIDA"
    assert "REFERENCIA_RELATIVA" in result["reason"]


def test_legacy_centroid_never_appears_in_accepted_coordinates():
    source = normalized(
        location_original="", latitude=-12.05, longitude=-77.1, coordinate_origin="CENTROIDE_FORZADO"
    )
    result = resolve_location(source, [boundary()], True)
    assert result["resolution"] == "REVISION_REQUERIDA"
    assert result["latitude"] is result["longitude"] is None
    assert result["candidates"] == []


def test_structured_components_conflicting_with_text_block_automatic_match():
    source = normalized(
        location_original="CALLE LOS PINOS 124",
        street_type="AVENIDA",
        street_name="LAS FLORES",
        door_number="123",
    )
    assert "COMPONENTES_CONTRADICTORIOS" in source["decision_constraints"]
    result = resolve_location(source, [door()], True)
    assert result["resolution"] != "ACEPTADO_AUTOMATICO"
