from copy import deepcopy

import pytest

from geopol.domain.matching import resolve_location
from geopol.domain.normalization import normalize_record
from geopol.domain.quality import (
    POLICY_VERSION,
    STAGE_KEYS,
    classify_quality,
    is_quality_resolved,
    location_quality_flag,
    quality_after_review,
    quality_review_state,
    resolve_quality_stage,
)


def normalized(**overrides):
    return normalize_record({"location_original": "AV. LAS FLORES 123", "ubigeo": "150101", **overrides})


def door(**overrides):
    return {
        "id": "d1",
        "kind": "door",
        "ubigeo": "150101",
        "street_type": "AVENIDA",
        "street_name": "LAS FLORES",
        "door_number": "123",
        "source": "SINTETICO",
        "version": "1",
        "crs": "EPSG:4326",
        "geometry": {"type": "Point", "coordinates": [-77.1, -12.05]},
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


def center(**overrides):
    base = dict(
        id="c1",
        kind="site",
        street_type=None,
        street_name=None,
        door_number=None,
        name="LOS PINOS",
        center_code="0001",
        point_role="settlement_reference",
        reference_precision="centro_poblado",
    )
    return door(**(base | overrides))


def jurisdiction(**overrides):
    base = dict(
        id="j1",
        kind="jurisdiction",
        name="COMISARIA DEL PARQUE",
        jurisdiction_code="J001",
        geometry={
            "type": "Polygon",
            "coordinates": [[[-77.5, -12.5], [-76.5, -12.5], [-76.5, -11.5], [-77.5, -11.5], [-77.5, -12.5]]],
        },
    )
    return boundary(**(base | overrides))


def test_stages_have_explicit_order_and_version():
    assert STAGE_KEYS == ("door", "block", "intersection", "street", "nucleus", "jurisdiction")
    assert POLICY_VERSION
    with pytest.raises(ValueError, match="desconocida"):
        resolve_quality_stage(normalized(), [], False, "unknown")


def test_exact_door_is_quality_one_and_does_not_mutate_inputs():
    query, features = normalized(), [door(), boundary()]
    before = deepcopy((query, features))
    result = resolve_quality_stage(query, features, True, "door")
    assert result["quality_code"] == 1
    assert result["quality_status"] == "resolved"
    assert result["resolution"] == "ACEPTADO_AUTOMATICO"
    assert result["precision"] == "PUERTA"
    assert result["latitude"] == -12.05
    assert result["quality_policy_version"] == POLICY_VERSION
    assert (query, features) == before


def test_known_alias_can_be_an_exact_corroborated_door():
    result = resolve_quality_stage(
        normalized(), [door(street_name="OTRO NOMBRE", aliases=["LAS FLORES"]), boundary()], True, "door"
    )
    assert result["quality_code"] == 1
    assert "ALIAS_EXPLICITO_COINCIDENTE" in result["candidates"][0]["evidence"]


@pytest.mark.parametrize(
    "address,name",
    [
        ("AV LAS FLOREZ 123", "LAS FLORES"),
        ("AV REPUBLICA DEMOCRATICA DEL PERO 123", "REPUBLICA DEMOCRATICA DEL PERU"),
    ],
)
def test_fuzzy_door_is_quick_review_even_when_legacy_engine_would_accept(address, name):
    query = normalized(location_original=address)
    result = resolve_quality_stage(query, [door(street_name=name), boundary()], True, "door")
    assert result["quality_code"] == 2
    assert result["quality_status"] == "review"
    assert result["resolution"] == "REVISION_REQUERIDA"
    assert result["latitude"] is result["longitude"] is result["geometry"] is None
    assert not any(attempt["status"] == "ACEPTADO" for attempt in result["attempts"])
    if name == "REPUBLICA DEMOCRATICA DEL PERU":
        assert (
            resolve_location(query, [door(street_name=name), boundary()], True)["resolution"]
            == "ACEPTADO_AUTOMATICO"
        )


def test_two_distinct_exact_doors_require_detailed_review():
    result = resolve_quality_stage(
        normalized(),
        [door(), door(id="d2", geometry={"type": "Point", "coordinates": [-77.2, -12.05]}), boundary()],
        True,
        "door",
    )
    assert result["quality_code"] == 3
    assert result["quality_status"] == "review"
    assert "MULTIPLES_CANDIDATOS" in result["reason"]


def test_equivalent_exact_points_preserve_provenance_without_false_ambiguity():
    result = resolve_quality_stage(
        normalized(), [door(), door(id="d2", source="OTRA_FUENTE"), boundary()], True, "door"
    )
    assert result["quality_code"] == 1
    assert len(result["candidates"]) == 2


@pytest.mark.parametrize(
    "change",
    [
        {"crs": None},
        {"source": None},
        {"version": None},
        {"geometry": None},
        {"geometry": {"type": "Point", "coordinates": [-75, -12.05]}},
    ],
)
def test_unsafe_exact_door_is_never_quality_one(change):
    result = resolve_quality_stage(normalized(), [door(**change), boundary()], True, "door")
    assert result["quality_code"] == 3
    assert result["quality_status"] == "review"
    assert result["geometry"] is None


def test_missing_boundary_is_detailed_review_not_quick():
    result = resolve_quality_stage(normalized(location_original="AV LAS FLOREZ 123"), [door()], True, "door")
    assert result["quality_code"] == 3
    assert "LIMITE_TERRITORIAL_NO_DISPONIBLE" in result["reason"]


def test_multiple_fuzzy_points_are_not_quick_review():
    result = resolve_quality_stage(
        normalized(location_original="AV LAS FLOREZ 123"),
        [door(), door(id="d2", geometry={"type": "Point", "coordinates": [-77.2, -12.05]}), boundary()],
        True,
        "door",
    )
    assert result["quality_code"] == 3


@pytest.mark.parametrize("overrides", [{"reference_truncated": True}, {"warnings": ["REFERENCIA_RELATIVA"]}])
def test_quick_review_cannot_hide_warnings_or_truncated_search(overrides):
    query = {**normalized(location_original="AV LAS FLOREZ 123"), **overrides}
    result = resolve_quality_stage(query, [door(), boundary()], True, "door")
    assert result["quality_code"] == 3
    assert result["quality_status"] == "review"


def test_no_match_can_advance_but_unavailable_layer_is_blocked():
    query = {**normalized(), "available_reference_kinds": ["door", "boundary"]}
    unmatched = resolve_quality_stage(query, [door(street_name="OTRA CALLE"), boundary()], True, "door")
    blocked = resolve_quality_stage(normalized(), [boundary()], True, "door")
    absent = resolve_quality_stage(query, [], False, "door")
    assert unmatched["quality_status"] == "unmatched"
    assert unmatched["quality_code"] is None
    assert blocked["quality_status"] == absent["quality_status"] == "blocked"


def test_confirmed_source_coordinate_without_door_match_is_not_quality_one():
    query = normalized(latitude=-12.05, longitude=-77.1, crs="EPSG:4326")
    result = resolve_quality_stage(query, [door(street_name="OTRA CALLE"), boundary()], True, "door")
    assert result["quality_status"] == "unmatched"
    assert result["quality_code"] is None
    assert not result["candidates"]


@pytest.mark.parametrize("address", ["AV LAS FLORES 123", "AV LAS FLOREZ 123"])
def test_confirmed_source_conflict_prevents_both_automatic_and_quick_classification(address):
    query = normalized(location_original=address, latitude=-12.1, longitude=-77.1, crs="EPSG:4326")
    result = resolve_quality_stage(query, [door(), boundary()], True, "door")
    assert result["quality_code"] == 3
    assert result["quality_status"] == "review"
    assert "COORDENADA_Y_REFERENCIA_CONTRADICTORIAS" in result["reason"]


def test_matching_confirmed_source_does_not_lose_door_precision():
    query = normalized(latitude=-12.05, longitude=-77.1, crs="EPSG:4326")
    result = resolve_quality_stage(query, [door(), boundary()], True, "door")
    assert result["quality_code"] == 1
    assert result["precision"] == "PUERTA"


def test_unconfirmed_source_crs_does_not_veto_independent_reference():
    query = normalized(latitude=-12.1, longitude=-77.1)
    result = resolve_quality_stage(query, [door(), boundary()], True, "door")
    assert result["quality_code"] == 1


def test_stage_does_not_automatically_fall_back_to_street():
    street = door(
        kind="street",
        door_number=None,
        geometry={"type": "LineString", "coordinates": [[-77.2, -12.05], [-77.1, -12.05]]},
    )
    result = resolve_quality_stage(
        normalized(), [door(street_name="OTRA CALLE"), street, boundary()], True, "door"
    )
    assert result["quality_status"] == "unmatched"
    assert not result["candidates"]


def test_block_is_quality_four_and_never_an_invented_point():
    block = door(
        kind="block",
        block_number="5",
        door_number=None,
        geometry={"type": "LineString", "coordinates": [[-77.2, -12.05], [-77.1, -12.05]]},
    )
    result = resolve_quality_stage(
        normalized(location_original="AV LAS FLORES CUADRA 5"), [block, boundary()], True, "block"
    )
    assert result["quality_code"] == 4
    assert result["quality_status"] == "resolved"
    assert result["product"] == "AREA_TRAMO"
    assert result["latitude"] is result["longitude"] is None


def test_block_number_is_not_inferred_from_door():
    block = door(
        kind="block",
        block_number="1",
        geometry={"type": "LineString", "coordinates": [[-77.2, -12.05], [-77.1, -12.05]]},
    )
    result = resolve_quality_stage(normalized(), [block, boundary()], True, "block")
    assert result["quality_status"] == "unmatched"


def test_resolved_stage_is_not_reprocessed_or_downgraded():
    previous = resolve_quality_stage(normalized(), [door(), boundary()], True, "door")
    before = deepcopy(previous)
    result = resolve_quality_stage(normalized(), [], False, "block", previous_result=previous)
    assert is_quality_resolved(result)
    assert result["quality_stage"] == "door"
    assert result["quality_code"] == 1
    assert result["quality_skipped"] is True
    assert {key: value for key, value in result.items() if key != "quality_skipped"} == before
    assert previous == before


@pytest.mark.parametrize("quality", [2, 3])
def test_manual_acceptance_preserves_review_quality_and_is_skipped_later(quality):
    previous = {
        "quality_stage": "door",
        "quality_code": quality,
        "quality_status": "review",
        "resolution": "REVISION_REQUERIDA",
        "candidates": [],
    }
    reviewed = {
        "resolution": "ACEPTADO_MANUAL",
        "product": "PUNTO",
        "precision": "PUERTA",
        "reason": "Puerta confirmada por operador",
    }
    result = quality_after_review(previous, reviewed, action="accept_candidate")
    assert result["quality_code"] == quality
    assert result["quality_status"] == "resolved"
    assert is_quality_resolved(result)


def test_manual_unresolved_can_advance_and_reopen_restores_review():
    previous = {
        "quality_stage": "door",
        "quality_code": 2,
        "quality_status": "review",
        "resolution": "REVISION_REQUERIDA",
        "candidates": [door()],
    }
    unresolved = quality_after_review(
        previous, {"resolution": "SIN_COINCIDENCIA", "product": "NINGUNO"}, action="unresolved"
    )
    assert unresolved["quality_status"] == "unmatched"
    assert unresolved["quality_code"] is None
    reopened = quality_after_review(previous, {"resolution": "REVISION_REQUERIDA"}, action="reopen")
    assert reopened["quality_status"] == "review"
    assert not is_quality_resolved(reopened)


def test_reopened_quality_one_is_no_longer_classified_as_automatic():
    previous = resolve_quality_stage(normalized(), [door(), boundary()], True, "door")
    reopened = quality_after_review(
        previous, {"resolution": "REVISION_REQUERIDA", "product": "NINGUNO"}, action="reopen"
    )
    assert reopened["quality_status"] == "review"
    assert reopened["quality_code"] == 3
    assert not is_quality_resolved(reopened)


def test_center_point_retains_real_coordinates_and_explicit_coarse_precision():
    query = {**normalized(location_original="CENTRO POBLADO LOS PINOS"), "urban_core": "LOS PINOS"}
    result = resolve_quality_stage(query, [center(), boundary()], True, "nucleus")
    assert result["quality_status"] == "resolved"
    assert result["quality_code"] is None
    assert result["precision"] == "CENTRO_POBLADO"
    assert result["method"] == "CCPP_PUNTO_REFERENCIA"
    assert result["geometry"] == center()["geometry"]
    assert result["latitude"] == -12.05
    assert "NO_DOMICILIO_EXACTO" in result["reason"]


def test_unmarked_site_is_not_promoted_to_center_or_door():
    query = {**normalized(), "urban_core": "LOS PINOS"}
    result = resolve_quality_stage(query, [center(point_role="mapped_poi"), boundary()], True, "nucleus")
    assert result["quality_status"] == "unmatched"
    assert not result["candidates"]


def test_center_needs_explicit_point_geometry_and_confirmed_metadata():
    query = {**normalized(), "urban_core": "LOS PINOS"}
    result = resolve_quality_stage(query, [center(geometry=None), boundary()], True, "nucleus")
    assert result["quality_status"] == "review"
    assert result["latitude"] is None


def test_two_centers_with_same_name_are_not_automatically_chosen():
    query = {**normalized(), "urban_core": "LOS PINOS"}
    result = resolve_quality_stage(
        query,
        [center(), center(id="c2", geometry={"type": "Point", "coordinates": [-77.2, -12.1]}), boundary()],
        True,
        "nucleus",
    )
    assert result["quality_status"] == "review"
    assert "MULTIPLES_CANDIDATOS" in result["reason"]


def test_named_jurisdiction_matches_real_polygon_without_centroid():
    query = {**normalized(), "jurisdiction_name": "COMISARIA DEL PARQUE"}
    result = resolve_quality_stage(query, [jurisdiction(), boundary()], True, "jurisdiction")
    assert result["quality_status"] == "resolved"
    assert result["quality_code"] is None
    assert result["product"] == "AREA_TRAMO"
    assert result["precision"] == "JURISDICCION"
    assert result["latitude"] is result["longitude"] is None


def test_confirmed_source_point_can_find_containing_jurisdiction():
    query = normalized(latitude=-12.05, longitude=-77.1, crs="EPSG:4326")
    result = resolve_quality_stage(query, [jurisdiction(), boundary()], True, "jurisdiction")
    assert result["quality_status"] == "resolved"
    assert "COORDENADA_CONFIRMADA_DENTRO_JURISDICCION" in result["candidates"][0]["evidence"]


def test_ubigeo_alone_cannot_choose_jurisdiction():
    result = resolve_quality_stage(normalized(), [jurisdiction(), boundary()], True, "jurisdiction")
    assert result["quality_status"] == "unmatched"


def test_overlapping_jurisdictions_need_review():
    query = normalized(latitude=-12.05, longitude=-77.1, crs="EPSG:4326")
    other = jurisdiction(
        id="j2",
        geometry={
            "type": "Polygon",
            "coordinates": [[[-77.4, -12.4], [-76.6, -12.4], [-76.6, -11.6], [-77.4, -11.6], [-77.4, -12.4]]],
        },
    )
    result = resolve_quality_stage(query, [jurisdiction(), other, boundary()], True, "jurisdiction")
    assert result["quality_status"] == "review"


@pytest.mark.parametrize("stage", ["nucleus", "jurisdiction"])
def test_extended_stages_still_require_boundary_and_complete_search(stage):
    query = {**normalized(), "urban_core": "LOS PINOS", "jurisdiction_name": "COMISARIA DEL PARQUE"}
    feature = center() if stage == "nucleus" else jurisdiction()
    missing = resolve_quality_stage(query, [feature], True, stage)
    truncated = resolve_quality_stage(query, [feature, boundary()], True, stage, reference_truncated=True)
    assert missing["quality_status"] == truncated["quality_status"] == "review"
    assert "LIMITE_TERRITORIAL_NO_DISPONIBLE" in missing["reason"]
    assert "BUSQUEDA_REFERENCIAL_TRUNCADA" in truncated["reason"]


def test_classifier_never_labels_manual_door_as_automatic_quality_one():
    fields = classify_quality(
        {"resolution": "ACEPTADO_MANUAL", "precision": "PUERTA", "product": "PUNTO"}, "door"
    )
    assert fields["quality_code"] == 3
    assert fields["quality_status"] == "resolved"


@pytest.mark.parametrize(
    "fields,reason",
    [
        ({"location_original": "AV LAS FLORES 123"}, "FLAG_1_PUERTA_DISTRITO"),
        ({"location_original": "AV LAS FLOREZ 123"}, "FLAG_1_PUERTA_DISTRITO"),
        ({"location_original": "AV LAS FLORES CUADRA 5"}, "FLAG_1_CUADRA_DISTRITO"),
        ({"location_original": "AV LAS FLORES CON CALLE LOS PINOS"}, "FLAG_1_CRUCE_DISTRITO"),
        (
            {"location_original": "COORDENADAS", "latitude": -12.05, "longitude": -77.1},
            "FLAG_1_COORDENADAS_DECLARADAS",
        ),
    ],
)
def test_public_flag_one_follows_location_format_not_matching_quality(fields, reason):
    query = normalized(**fields)
    before = deepcopy(query)
    assert location_quality_flag(query) == {"quality_flag": 1, "quality_flag_reason": reason}
    assert query == before


@pytest.mark.parametrize(
    "fields,reason",
    [
        ({"location_original": "URBANIZACION LOS PINOS"}, "FLAG_2_NUCLEO_DISTRITO"),
        ({"location_original": "CENTRO POBLADO LOS PINOS"}, "FLAG_2_NUCLEO_DISTRITO"),
        ({"location_original": "", "center_name": "LOS PINOS"}, "FLAG_2_NUCLEO_DISTRITO"),
        (
            {"location_original": "AV LAS FLORES", "jurisdiction_name": "COMISARIA DEL PARQUE"},
            "FLAG_2_VIA_JURISDICCION",
        ),
        (
            {"location_original": "AV LAS FLORES", "jurisdiction_code": "J001", "ubigeo": None},
            "FLAG_2_VIA_JURISDICCION",
        ),
    ],
)
def test_public_flag_two_requires_explicit_general_location_context(fields, reason):
    assert location_quality_flag(normalized(**fields)) == {"quality_flag": 2, "quality_flag_reason": reason}


def test_flag_one_takes_priority_when_both_location_formats_are_present():
    query = normalized(
        location_original="AV LAS FLORES 123",
        urban_core="LOS PINOS",
        jurisdiction_name="COMISARIA DEL PARQUE",
    )
    assert location_quality_flag(query)["quality_flag_reason"] == "FLAG_1_PUERTA_DISTRITO"
    query.update(latitude=-12.05, longitude=-77.1)
    assert location_quality_flag(query)["quality_flag_reason"] == "FLAG_1_COORDENADAS_DECLARADAS"


def test_flag_one_coordinate_format_does_not_require_declared_crs_or_reference():
    query = normalized(location_original="", latitude=-12.05, longitude=-77.1, ubigeo=None)
    assert query["crs"] is None
    assert location_quality_flag(query)["quality_flag"] == 1
    resolved = resolve_quality_stage(query, [], False, "door")
    assert resolved["resolution"] == "NO_EVALUABLE_REFERENCIA"
    assert quality_review_state(resolved) == "reference_pending"
    assert resolved["latitude"] is None


def test_flag_does_not_change_after_coarser_resolution_or_candidate_selection():
    query = normalized()
    assert location_quality_flag(query)["quality_flag"] == 1
    changed = {
        **query,
        "resolution": "ACEPTADO_AUTOMATICO",
        "precision": "NUCLEO",
        "quality_code": None,
        "candidates": [center()],
    }
    assert location_quality_flag(changed) == location_quality_flag(query)


@pytest.mark.parametrize(
    "fields",
    [
        {"location_original": "LAS FLORES 123"},
        {"location_original": "AV LAS FLORES S/N"},
        {"location_original": "AV LAS FLORES"},
        {"location_original": "AV LAS FLORES 123", "ubigeo": None},
        {"location_original": "AV LAS FLORES 123", "ubigeo": "000000"},
        {"location_original": "AV LAS FLORES 123", "ubigeo": "999999"},
        {"location_original": "AV LAS FLORES 123", "ubigeo": "1"},
        {"location_original": "URBANIZACION LOS PINOS", "ubigeo": None},
        {"location_original": "AV LAS FLORES CON AV LAS FLORES"},
        {"location_original": "", "latitude": 912, "longitude": -77},
        {"location_original": "", "latitude": -12, "longitude": None},
        {
            "location_original": "",
            "latitude": -12,
            "longitude": -77,
            "coordinate_origin": "CENTROIDE SUSTITUTO",
        },
    ],
)
def test_incomplete_or_unsupported_input_format_has_no_public_flag(fields):
    assert location_quality_flag(normalized(**fields))["quality_flag"] is None


@pytest.mark.parametrize("district", ["MIRAFLORES", "SAN JUAN DE LURIGANCHO"])
def test_explicit_district_can_identify_the_format_without_proving_geographic_territory(district):
    query = normalized(ubigeo=None, district=district)
    assert location_quality_flag(query)["quality_flag"] == 1
    result = resolve_quality_stage(query, [door(), boundary()], True, "door")
    assert result["resolution"] == "REVISION_REQUERIDA"


@pytest.mark.parametrize(
    "district", ["N/A", "SIN DATO", "MIRAFLORES / SAN ISIDRO", "LIMA, CALLAO", "123", "?"]
)
def test_absent_or_multiple_district_labels_do_not_complete_a_flag(district):
    assert location_quality_flag(normalized(ubigeo=None, district=district))["quality_flag"] is None


@pytest.mark.parametrize(
    "warning",
    [
        "COMPONENTES_CONTRADICTORIOS",
        "COORDENADAS_CONTRADICTORIAS",
        "UBIGEO_CONFLICTIVO_ORIGEN",
        "CRS_CONFLICTIVO",
        "FILA_ORIGEN_CON_INCIDENCIA",
    ],
)
def test_ambiguous_source_fields_do_not_get_a_public_flag(warning):
    query = normalized(latitude=-12.05, longitude=-77.1)
    query["warnings"] = [warning]
    assert location_quality_flag(query) == {
        "quality_flag": None,
        "quality_flag_reason": "FLAG_SIN_ASIGNAR_COMPONENTES_CONTRADICTORIOS",
    }


def test_relative_address_is_not_assumed_to_be_the_door_format():
    query = normalized(location_original="FRENTE A AV LAS FLORES 123")
    assert location_quality_flag(query)["quality_flag"] is None


@pytest.mark.parametrize(
    "result,expected",
    [
        ({"resolution": "PENDIENTE", "quality_flag": 1}, "unprocessed"),
        ({}, "unprocessed"),
        ({"resolution": "ACEPTADO_AUTOMATICO", "quality_flag": None}, "automatic"),
        ({"resolution": "ACEPTADO_AUTOMATICO", "quality_flag": 2}, "automatic"),
        ({"resolution": "ACEPTADO_MANUAL", "product": "PUNTO", "quality_code": 2}, "accepted_manual"),
        ({"resolution": "ACEPTADO_MANUAL", "product": "AREA_TRAMO", "quality_code": 4}, "accepted_manual"),
        (
            {
                "resolution": "ACEPTADO_MANUAL",
                "product": "DIRECCION_SIN_PUNTO",
                "quality_status": "unmatched",
            },
            "unmatched",
        ),
        ({"resolution": "SIN_COINCIDENCIA", "quality_flag": 1, "quality_code": 2}, "unmatched"),
        ({"resolution": "INFORMACION_INSUFICIENTE"}, "unmatched"),
        ({"resolution": "NO_EVALUABLE_REFERENCIA", "quality_flag": 1}, "reference_pending"),
        ({"resolution": "REVISION_REQUERIDA", "quality_code": 2}, "quick_review"),
        ({"resolution": "REVISION_REQUERIDA", "quality_code": 3}, "detailed_review"),
        (
            {
                "resolution": "REVISION_REQUERIDA",
                "quality_code": 3,
                "reason": "LIMITE_TERRITORIAL_NO_DISPONIBLE",
            },
            "reference_pending",
        ),
        (
            {
                "resolution": "REVISION_REQUERIDA",
                "quality_code": 2,
                "candidates": [{"evidence": ["CRS_REFERENCIA_NO_CONFIRMADO"]}],
            },
            "reference_pending",
        ),
        ({"resolution": "ERROR_TECNICO"}, "detailed_review"),
    ],
)
def test_review_state_is_independent_of_public_flag(result, expected):
    assert quality_review_state(result) == expected
