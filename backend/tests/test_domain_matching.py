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
        "crs": "EPSG:4326",
        "geometry": {
            "type": "Point",
            "coordinates": [overrides.get("longitude", -77.1), overrides.get("latitude", -12.05)],
        },
        **overrides,
    }


def boundary(**overrides):
    return {
        "id": "b1",
        "kind": "boundary",
        "ubigeo": "150101",
        "source": "SINTETICO",
        "version": "1",
        "crs": "EPSG:4326",
        "geometry": {
            "type": "Polygon",
            "coordinates": [[[-78, -13], [-76, -13], [-76, -11], [-78, -11], [-78, -13]]],
        },
        **overrides,
    }


def test_unique_exact_door_has_explainable_acceptance():
    result = resolve_location(normalized(), [door(), boundary()], True)
    assert result["resolution"] == "ACEPTADO_AUTOMATICO"
    assert result["latitude"] == -12.05
    assert result["method"] == "PUERTA_CON_TIPO"
    assert "UBIGEO_COINCIDENTE" in result["candidates"][0]["evidence"]
    assert result["candidates"][0]["score_type"] == "SIMILITUD_TEXTUAL_NO_PROBABILIDAD"


@pytest.mark.parametrize("change", [{"ubigeo": None}])
def test_unknown_territory_cannot_autoaccept(change):
    result = resolve_location(normalized(**change), [door(), boundary()], True)
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
    result = resolve_location(normalized(), [door(), door(id="d2", latitude=-12.06), boundary()], True)
    assert result["resolution"] == "REVISION_REQUERIDA"
    assert "MULTIPLES_CANDIDATOS" in result["reason"]
    assert len(result["candidates"]) == 2


def test_equivalent_exact_points_preserve_all_provenance_and_explain_acceptance():
    result = resolve_location(
        normalized(), [door(), door(id="d2", source="OTRA_FUENTE", version="2"), boundary()], True
    )
    assert result["resolution"] == "ACEPTADO_AUTOMATICO"
    assert result["reason"] == "EVIDENCIAS_EQUIVALENTES_MISMO_PUNTO"
    assert (result["latitude"], result["longitude"]) == (-12.05, -77.1)
    assert {(c["id"], c["source"], c["version"]) for c in result["candidates"]} == {
        ("d1", "SINTETICO", "1"),
        ("d2", "OTRA_FUENTE", "2"),
    }
    assert all("EVIDENCIAS_EQUIVALENTES_MISMO_PUNTO" in c["evidence"] for c in result["candidates"])
    assert result["attempts"][-1]["candidate_count"] == 2


def test_nearby_points_are_never_rounded_into_equivalent_evidence():
    result = resolve_location(
        normalized(), [door(), door(id="d2", latitude=-12.05 + 1e-12), boundary()], True
    )
    assert result["resolution"] == "REVISION_REQUERIDA"
    assert "MULTIPLES_CANDIDATOS" in result["reason"]


@pytest.mark.parametrize("repeated_id", [False, True])
def test_coincident_fuzzy_evidence_cannot_borrow_an_exact_candidates_eligibility(repeated_id):
    approximate = door(id="d1" if repeated_id else "d2", street_name="LAS FLOREZ")
    result = resolve_location(normalized(), [approximate, door(), boundary()], True)
    assert result["resolution"] == "ACEPTADO_AUTOMATICO"
    assert result["reason"] != "EVIDENCIAS_EQUIVALENTES_MISMO_PUNTO"
    assert (
        "SIMILITUD_TEXTUAL_REQUIERE_REVISION"
        in next(c for c in result["candidates"] if c["score"] < 100)["evidence"]
    )
    assert any(c["score"] < 100 for c in result["candidates"])


@pytest.mark.parametrize("change", [{"ubigeo": None}])
def test_repeated_points_do_not_resolve_unknown_territory(change):
    result = resolve_location(normalized(**change), [door(), door(id="d2"), boundary()], True)
    assert result["resolution"] == "REVISION_REQUERIDA"
    assert result["latitude"] is result["longitude"] is None


@pytest.mark.parametrize("latitude", [-9, -13])
def test_repeated_points_outside_or_on_boundary_remain_review(latitude):
    result = resolve_location(
        normalized(), [door(latitude=latitude), door(id="d2", latitude=latitude), boundary()], True
    )
    assert result["resolution"] == "REVISION_REQUERIDA"


def test_exactly_coincident_original_and_door_evidence_agree():
    source = normalized(latitude=-12.05, longitude=-77.1)
    result = resolve_location(source, [door(), boundary()], True)
    assert {candidate["method"] for candidate in result["candidates"]} == {
        "COORD_ORIGINAL",
        "PUERTA_CON_TIPO",
    }
    assert result["resolution"] == "ACEPTADO_AUTOMATICO"
    assert "COORDENADA_Y_REFERENCIA_CONCORDANTES" in result["candidates"][0]["evidence"]


def test_repeated_approximate_blocks_do_not_become_precise_points():
    first = door(kind="block", block_number="5", door_number=None)
    second = {**first, "id": "b2"}
    result = resolve_location(normalized(location_original="AV LAS FLORES CUADRA 5"), [first, second], True)
    assert result["resolution"] == "REVISION_REQUERIDA"
    assert all(c["product"] == "AREA_TRAMO" for c in result["candidates"])


@pytest.mark.parametrize("truncated", [False, True])
def test_equivalent_candidates_do_not_bypass_conflicts_or_truncated_search(truncated):
    source = normalized(location_original="FRENTE A AV LAS FLORES 123")
    if truncated:
        source = normalized()
        source["reference_truncated"] = True
    result = resolve_location(source, [door(), door(id="d2")], True)
    assert result["resolution"] == "REVISION_REQUERIDA"
    assert ("BUSQUEDA_REFERENCIAL_TRUNCADA" if truncated else "REFERENCIA_RELATIVA") in result["reason"]


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


def test_validated_original_coordinate_is_independent_of_a_manzana_lote_parser_limitation():
    source = normalized(location_original="MANZANA A LOTE 2", latitude=-12.05, longitude=-77.1)
    original_warnings = list(source["warnings"])
    result = resolve_location(source, [boundary()], True)
    assert result["resolution"] == "ACEPTADO_AUTOMATICO"
    assert result["reason"] == "COORDENADA_ORIGINAL_VALIDADA_INDEPENDIENTE_DE_MANZANA_LOTE"
    assert result["method"] == "COORD_ORIGINAL"
    assert "MANZANA_LOTE_NO_LIMITA_COORDENADA_ORIGINAL_VALIDADA" in result["candidates"][0]["evidence"]
    assert source["warnings"] == original_warnings
    assert "MANZANA_LOTE_REQUIERE_REFERENCIA" in source["decision_constraints"]


@pytest.mark.parametrize(
    "change,features",
    [
        ({"crs": None}, [boundary()]),
        ({"ubigeo": None}, [boundary()]),
        ({}, []),
        ({"latitude": -13}, [boundary()]),
        ({"latitude": -9}, [boundary()]),
        ({"coordinate_origin": "NO_CONFIRMADA"}, [boundary()]),
        ({"FLAG_GEOREF": 2}, [boundary()]),
    ],
)
def test_manzana_original_coordinate_still_requires_valid_crs_territory_and_provenance(change, features):
    source = normalized(
        **{"location_original": "MANZANA A LOTE 2", "latitude": -12.05, "longitude": -77.1, **change}
    )
    result = resolve_location(source, features, bool(features))
    assert result["resolution"] == "REVISION_REQUERIDA"
    assert result["latitude"] is result["longitude"] is None


@pytest.mark.parametrize("extra", [{}, {"FLAG_GEOREF": 3, "xx": -12.2, "yy": -77.2}])
def test_textual_coordinate_does_not_bypass_manzana_lote_even_when_recovering_a_centroid(extra):
    source = normalized(location_original="MANZANA A LOTE 2 LAT: -12.05 LONG: -77.1", **extra)
    result = resolve_location(source, [boundary()], True)
    assert result["method"] == "COORD_TEXTO"
    assert result["resolution"] == "REVISION_REQUERIDA"
    assert "MANZANA_LOTE_REQUIERE_REFERENCIA" in result["reason"]


def test_legacy_centroid_in_a_manzana_is_never_an_original_coordinate():
    source = normalized(
        location_original="MANZANA A LOTE 2", latitude=-12.05, longitude=-77.1, coordinate_origin="CENTROIDE"
    )
    result = resolve_location(source, [boundary()], True)
    assert result["resolution"] == "NO_EVALUABLE_REFERENCIA"
    assert result["latitude"] is result["longitude"] is None
    assert not result["candidates"]


@pytest.mark.parametrize(
    "location",
    [
        "FRENTE A MANZANA A LOTE 2",
        "MANZANA A LOTE 2 LAT: -12.06 LONG: -77.1",
    ],
)
def test_original_coordinate_does_not_bypass_relative_reference_or_coordinate_conflicts(location):
    source = normalized(location_original=location, latitude=-12.05, longitude=-77.1)
    result = resolve_location(source, [boundary()], True)
    assert result["resolution"] == "REVISION_REQUERIDA"
    assert "REFERENCIA_RELATIVA" in result["reason"] or "COORDENADAS_CONTRADICTORIAS" in result["reason"]


def test_original_coordinate_manzana_exception_does_not_hide_structured_component_conflicts():
    source = normalized(
        location_original="AV LAS FLORES MZ A LOTE 2",
        street_name="OTRA VIA",
        latitude=-12.05,
        longitude=-77.1,
    )
    result = resolve_location(source, [boundary()], True)
    assert result["resolution"] == "REVISION_REQUERIDA"
    assert "COMPONENTES_CONTRADICTORIOS" in result["reason"]


def test_text_coordinate_at_a_relative_reference_remains_review():
    source = normalized(location_original="FRENTE AL PARQUE DEMO LAT: -12.05 LONG: -77.1")
    result = resolve_location(source, [boundary()], True)
    assert result["method"] == "COORD_TEXTO"
    assert result["resolution"] == "REVISION_REQUERIDA"
    assert "REFERENCIA_RELATIVA" in result["reason"]


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
    assert resolve_location(source, [feature, boundary()], True)["resolution"] == "REVISION_REQUERIDA"
    feature["connects_at_grade"] = True
    assert resolve_location(source, [feature, boundary()], True)["resolution"] == "ACEPTADO_AUTOMATICO"


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
