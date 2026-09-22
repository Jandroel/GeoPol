"""2026.3 precision, independent CRS and guarded similarity contracts."""

import pytest

from geopol.domain.matching import resolve_location
from geopol.domain.normalization import normalize_record
from test_domain_matching import boundary, door, normalized

LINE = {"type": "LineString", "coordinates": [[-77.11, -12.05], [-77.09, -12.05]]}
AREA = {
    "type": "Polygon",
    "coordinates": [
        [[-77.11, -12.06], [-77.09, -12.06], [-77.09, -12.04], [-77.11, -12.04], [-77.11, -12.06]]
    ],
}


def reference(kind, **extra):
    return door(id=kind, kind=kind, geometry=LINE if kind in {"street", "block"} else AREA, **extra)


@pytest.mark.parametrize("input_crs", [None, "EPSG:3857"])
def test_reference_door_uses_catalogue_crs_even_with_unconfirmed_source_point(input_crs):
    result = resolve_location(
        normalized(crs=input_crs, latitude=-11.9, longitude=-77), [door(), boundary()], True
    )
    assert result["resolution"] == "ACEPTADO_AUTOMATICO"
    assert result["method"] == "PUERTA_CON_TIPO"
    assert result["geometry"] == door()["geometry"]
    assert result["latitude"] == -12.05
    assert any("CRS_NO_CONFIRMADO" in c["evidence"] for c in result["candidates"])


@pytest.mark.parametrize(
    "extra", [{"crs": None}, {"crs": "EPSG:3857"}, {"source": None}, {"version": None}, {"geometry": None}]
)
def test_reference_requires_geometry_crs_and_provenance(extra):
    result = resolve_location(normalized(), [door(**extra), boundary()], True)
    assert result["resolution"] == "REVISION_REQUERIDA"
    assert result["geometry"] is result["latitude"] is None


def test_reference_requires_valid_relevant_boundary():
    for bounds in ([], [boundary(ubigeo="150102")], [boundary(crs=None)]):
        result = resolve_location(normalized(), [door(), *bounds], True)
        assert result["resolution"] == "REVISION_REQUERIDA"


@pytest.mark.parametrize(
    "kind,location,extra,precision",
    [
        ("street", "AV LAS FLORES 123", {}, "VIA"),
        ("block", "AV LAS FLORES CUADRA 5", {"block_number": "5"}, "CUADRA"),
        (
            "manzana",
            "URB LOS JARDINES MZ A LOTE 12",
            {"manzana_code": "A", "urban_core": "LOS JARDINES"},
            "MANZANA",
        ),
        ("nucleus", "URB LOS JARDINES", {"name": "LOS JARDINES"}, "NUCLEO"),
        ("site", "PARQUE DEL AMANECER", {"name": "PARQUE DEL AMANECER"}, "SITIO"),
    ],
)
def test_real_geometry_is_accepted_at_declared_precision_without_a_fabricated_point(
    kind, location, extra, precision
):
    feature = reference(kind, **extra)
    result = resolve_location(normalized(location_original=location, crs=None), [feature, boundary()], True)
    assert result["resolution"] == "ACEPTADO_AUTOMATICO", result["reason"]
    assert result["precision"] == precision
    assert result["product"] == "AREA_TRAMO"
    assert result["geometry"] == feature["geometry"]
    assert result["latitude"] is result["longitude"] is None
    assert all(c["latitude"] is c["longitude"] is None for c in result["candidates"])


def test_site_requires_actual_poi_node_or_entrance_and_never_a_centroid():
    query = normalized(location_original="PARQUE DEL AMANECER")
    for role, expected in [
        (None, "REVISION_REQUERIDA"),
        ("centroid", "REVISION_REQUERIDA"),
        ("mapped_poi", "ACEPTADO_AUTOMATICO"),
        ("entrance", "ACEPTADO_AUTOMATICO"),
    ]:
        result = resolve_location(
            query, [door(kind="site", name="PARQUE DEL AMANECER", point_role=role), boundary()], True
        )
        assert result["resolution"] == expected


def test_manzana_requires_context_not_just_common_letter_in_district():
    result = resolve_location(
        normalized(location_original="MZ A LOTE 12"),
        [reference("manzana", manzana_code="A"), boundary()],
        True,
    )
    assert result["resolution"] == "REVISION_REQUERIDA"
    assert "CONTEXTO_MANZANA_NO_CONFIRMADO" in result["reason"]


def test_entire_reference_geometry_must_fit_boundary():
    feature = reference("street")
    feature["geometry"] = {"type": "LineString", "coordinates": [[-77.1, -12], [-75, -12]]}
    result = resolve_location(normalized(), [feature, boundary()], True)
    assert result["resolution"] == "REVISION_REQUERIDA"
    assert "GEOMETRIA_EXCEDE_UBIGEO" in result["reason"]


@pytest.mark.parametrize("kind", ["street", "block", "manzana", "nucleus"])
def test_representative_points_cannot_impersonate_areas_or_segments(kind):
    query = normalized(
        location_original="URB LOS JARDINES MZ A LOTE 12", street_name="LAS FLORES", block_number="5"
    )
    feature = door(
        kind=kind, name="LOS JARDINES", block_number="5", manzana_code="A", urban_core="LOS JARDINES"
    )
    result = resolve_location(query, [feature, boundary()], True)
    assert result["resolution"] == "REVISION_REQUERIDA"
    assert result["geometry"] is result["latitude"] is result["longitude"] is None


def test_district_geometry_is_never_successful_location_precision():
    result = resolve_location(normalized(location_original="", district="DISTRITO DEMO"), [boundary()], True)
    assert result["resolution"] == "INFORMACION_INSUFICIENTE"
    assert not result["candidates"]


def test_ambiguous_doors_cannot_be_hidden_by_unique_street_fallback():
    result = resolve_location(
        normalized(), [door(), door(id="d2", latitude=-12.06), reference("street"), boundary()], True
    )
    assert result["resolution"] == "REVISION_REQUERIDA"
    assert result["precision"] == "PUERTA"
    assert "MULTIPLES_CANDIDATOS" in result["reason"]


def test_fine_point_wins_over_unambiguous_coarser_geometry():
    result = resolve_location(normalized(), [door(), reference("street"), boundary()], True)
    assert result["resolution"] == "ACEPTADO_AUTOMATICO"
    assert result["precision"] == "PUERTA"
    assert len(result["candidates"]) == 2


def test_original_and_exact_reference_point_disagreement_stays_review():
    result = resolve_location(normalized(latitude=-12.050001, longitude=-77.1), [door(), boundary()], True)
    assert result["resolution"] == "REVISION_REQUERIDA"
    assert "COORDENADA_Y_REFERENCIA_CONTRADICTORIAS" in result["reason"]


def test_long_name_typo_with_exact_door_type_and_territory_can_be_automatic():
    query = normalized(location_original="AV LOS EXPERIMENTOS SINTETIKOS 123")
    result = resolve_location(query, [door(street_name="LOS EXPERIMENTOS SINTETICOS"), boundary()], True)
    assert result["resolution"] == "ACEPTADO_AUTOMATICO"
    assert result["reason"] == "COINCIDENCIA_APROXIMADA_FUERTE_CON_EVIDENCIA_INDEPENDIENTE"
    assert result["candidates"][0]["score"] < 100
    assert result["candidates"][0]["score_type"] == "SIMILITUD_TEXTUAL_NO_PROBABILIDAD"


def test_fuzzy_requires_independent_components_and_runner_up_margin():
    query = normalized(location_original="AV LOS EXPERIMENTOS SINTETIKOS 123")
    feature = door(street_name="LOS EXPERIMENTOS SINTETICOS")
    rival = door(id="d2", street_name="LOS EXPERIMENTOS SINTETIXOS", latitude=-12.06)
    result = resolve_location(query, [feature, rival, boundary()], True)
    assert result["resolution"] == "REVISION_REQUERIDA"
    assert "MARGEN_SIMILITUD_INSUFICIENTE" in result["reason"]
    query["street_type"] = None
    assert resolve_location(query, [feature, boundary()], True)["resolution"] == "REVISION_REQUERIDA"
    query = normalized(location_original="AV LOS EXPERIMENTOS SINTETIKOS")
    assert (
        resolve_location(
            query, [reference("street", street_name="LOS EXPERIMENTOS SINTETICOS"), boundary()], True
        )["resolution"]
        == "REVISION_REQUERIDA"
    )


def test_fuzzy_cannot_change_numeric_street_tokens_or_door_suffix():
    for location, feature in [
        ("AV LOS EXPERIMENTOS 201 123", door(street_name="LOS EXPERIMENTOS 202")),
        (
            "AV LOS EXPERIMENTOS SINTETIKOS 123-A",
            door(street_name="LOS EXPERIMENTOS SINTETICOS", door_number="123-B"),
        ),
    ]:
        result = resolve_location(normalized(location_original=location), [feature, boundary()], True)
        assert result["resolution"] == "SIN_COINCIDENCIA"
        assert not result["candidates"]


def test_explicit_source_alias_is_auditable_but_numeric_name_is_not_inferred():
    query = normalized(location_original="CALLE UNO 123")
    feature = door(street_type="CALLE", street_name="1")
    assert resolve_location(query, [feature, boundary()], True)["resolution"] == "SIN_COINCIDENCIA"
    feature["aliases"] = ["Calle Uno"]
    result = resolve_location(query, [feature, boundary()], True)
    assert result["resolution"] == "ACEPTADO_AUTOMATICO"
    assert "ALIAS_EXPLICITO_COINCIDENTE" in result["candidates"][0]["evidence"]


def test_missing_requested_layer_still_appears_in_attempts_when_fallback_search_fails():
    result = resolve_location(normalized(), [reference("street", street_name="OTRA VIA"), boundary()], True)
    assert result["resolution"] == "SIN_COINCIDENCIA"
    assert any(
        a["method"] == "PUERTA_CON_TIPO" and a["status"] == "NO_EVALUABLE_REFERENCIA"
        for a in result["attempts"]
    )


def test_new_manzana_lote_normalization_preserves_components_and_conflicts():
    raw = {"location_original": "URB. LOS JARDINES MZ A-2 LT 12B", "CUADRA": "NULL", "VIA": "OTROS"}
    result = normalize_record(raw)
    assert result["manzana_code"] == "A-2"
    assert result["lot_number"] == "12B"
    assert result["urban_core"] == "LOS JARDINES"
    assert result["door_number"] is result["block_number"] is result["street_name"] is None
    assert "TIPO_VIA_ESTRUCTURADO_NO_RECONOCIDO" not in result["warnings"]
    assert raw["CUADRA"] == "NULL"
    conflict = normalize_record({**raw, "manzana_code": "B"})
    assert "COMPONENTES_CONTRADICTORIOS" in conflict["warnings"]


@pytest.mark.parametrize("prefix,expected", [("JIR", "JIRON"), ("PSJ", "PASAJE"), ("CTRA", "CARRETERA")])
def test_safe_type_aliases_do_not_change_name_or_number(prefix, expected):
    result = normalize_record({"location_original": f"{prefix}. UNO 12"})
    assert (result["street_type"], result["street_name"], result["door_number"]) == (expected, "UNO", "12")


@pytest.mark.parametrize(
    "location",
    [
        "JR. LOS PINOS 123 URB. LOS JARDINES",
        "URB. LOS JARDINES JR. LOS PINOS 123",
        "JR LOS PINOS 123 URBANIZACION LOS JARDINES - DISTRITO DEMO - PROVINCIA DEMO",
    ],
)
def test_explicit_urban_and_administrative_context_do_not_pollute_street(location):
    result = normalize_record({"location_original": location, "district": "DISTRITO DEMO"})
    assert (result["street_type"], result["street_name"], result["door_number"]) == (
        "JIRON",
        "LOS PINOS",
        "123",
    )
    assert result["urban_core"] == "LOS JARDINES"
    assert result["location_original"] == location


def test_internal_dotted_type_is_extracted_without_losing_relative_warning():
    result = normalize_record({"location_original": "FRENTE A AV. LOS PINOS 123"})
    assert result["street_type"] == "AVENIDA"
    assert result["street_name"] == "LOS PINOS"
    assert "REFERENCIA_RELATIVA" in result["decision_constraints"]


@pytest.mark.parametrize("prefix", ["MZA", "MZA.", "MZ.", "MANZANA"])
def test_manzana_prefix_does_not_capture_its_own_last_letter(prefix):
    result = normalize_record({"location_original": f"A.H. LOS JARDINES {prefix} B LOTE 12"})
    assert result["manzana_code"] == "B"
    assert result["lot_number"] == "12"
    assert result["urban_core"] == "LOS JARDINES"


def test_explicit_urban_context_conflict_is_retained():
    result = normalize_record(
        {"location_original": "AV. LAS FLORES 123 URB. LOS JARDINES", "urban_core": "OTRO NUCLEO"}
    )
    assert "COMPONENTES_CONTRADICTORIOS" in result["warnings"]
    result = resolve_location(
        normalized(urban_core="LOS JARDINES"), [door(urban_core="OTRO NUCLEO"), boundary()], True
    )
    assert result["resolution"] == "REVISION_REQUERIDA"
    assert "NUCLEO_URBANO_CONTRADICTORIO_REFERENCIA" in result["reason"]


def test_nucleus_polygon_can_corroborate_street_but_cannot_be_ignored_when_contradictory():
    query = normalized(urban_core="LOS JARDINES")
    nucleus = reference("nucleus", name="LOS JARDINES")
    result = resolve_location(query, [door(), nucleus, boundary()], True)
    assert result["resolution"] == "ACEPTADO_AUTOMATICO"
    assert result["precision"] == "PUERTA"
    assert "GEOMETRIA_DENTRO_NUCLEO_DECLARADO" in result["candidates"][0]["evidence"]
    result = resolve_location(query, [door(latitude=-12.5), nucleus, boundary()], True)
    # Coarser nucleus geometry remains a legitimate result, never the wrong door.
    assert result["precision"] == "NUCLEO"
    assert result["geometry"] == AREA
    assert any("GEOMETRIA_FUERA_NUCLEO_DECLARADO" in c["evidence"] for c in result["candidates"])


def test_homonymous_disconnected_lines_cannot_be_accepted_as_one_street():
    feature = reference("street")
    feature["geometry"] = {
        "type": "MultiLineString",
        "coordinates": [LINE["coordinates"], [[-77.3, -12.3], [-77.2, -12.3]]],
    }
    result = resolve_location(normalized(), [feature, boundary()], True)
    assert result["resolution"] == "REVISION_REQUERIDA"
    assert "VIA_RAMIFICADA_O_AMBIGUA" in result["reason"]
    feature["geometry"] = {
        "type": "MultiLineString",
        "coordinates": [[[-77.11, -12.05], [-77.1, -12.05]], [[-77.1, -12.05], [-77.09, -12.05]]],
    }
    assert resolve_location(normalized(), [feature, boundary()], True)["resolution"] == "ACEPTADO_AUTOMATICO"


def test_verified_clipped_line_uses_only_bounded_double_precision_guard():
    feature = reference("street")
    feature.update(
        geometry={"type": "LineString", "coordinates": [[-77, -12], [-76 + 3e-13, -12]]},
        geometry_transform="clip_to_boundary: exact intersection",
        clip_boundary_id="b1",
        clip_boundary_version="1",
    )
    original_geometry = json_copy(feature["geometry"])
    result = resolve_location(normalized(), [feature, boundary()], True)
    assert result["resolution"] == "ACEPTADO_AUTOMATICO"
    assert "RECORTE_VERIFICADO_RESIDUO_NUMERICO_ULP" in result["candidates"][0]["evidence"]
    assert result["geometry"] == original_geometry
    for change in (
        {"clip_boundary_id": "unknown"},
        {"clip_boundary_version": "2"},
        {"geometry_transform": "none"},
        {"geometry": {"type": "LineString", "coordinates": [[-77, -12], [-76 + 1e-8, -12]]}},
    ):
        rejected = resolve_location(normalized(), [{**feature, **change}, boundary()], True)
        assert rejected["resolution"] == "REVISION_REQUERIDA"
        assert rejected["geometry"] is None
    point = door(
        longitude=-76,
        geometry_transform=feature["geometry_transform"],
        clip_boundary_id="b1",
        clip_boundary_version="1",
    )
    rejected = resolve_location(normalized(), [point, boundary()], True)
    assert rejected["resolution"] == "REVISION_REQUERIDA"
    assert "PUNTO_EN_LIMITE_TERRITORIAL" in rejected["reason"]


def json_copy(value):
    import copy

    return copy.deepcopy(value)


def test_original_point_does_not_need_to_lie_on_road_centreline():
    query = normalized(latitude=-12.05001, longitude=-77.1)
    result = resolve_location(query, [reference("street"), boundary()], True)
    assert result["resolution"] == "ACEPTADO_AUTOMATICO"
    assert result["method"] == "COORD_ORIGINAL"


def test_coarse_nucleus_resolution_states_that_manzana_and_lot_remain_unresolved():
    query = normalized(location_original="URB LOS JARDINES MZ A LOTE 12")
    result = resolve_location(query, [reference("nucleus", name="LOS JARDINES"), boundary()], True)
    assert result["resolution"] == "ACEPTADO_AUTOMATICO"
    assert result["precision"] == "NUCLEO"
    assert result["product"] == "AREA_TRAMO"
    assert "MANZANA_LOTE_NO_RESUELTOS_PRECISION_NUCLEO" in result["candidates"][0]["evidence"]
    assert "MANZANA_LOTE_REQUIERE_REFERENCIA" in query["decision_constraints"]
