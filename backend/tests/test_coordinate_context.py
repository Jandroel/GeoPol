from geopol.domain.coordinate_context import apply_coordinate_declaration


def test_legacy_browser_assumption_and_bare_source_column_are_not_confirmations():
    legacy = {"crs": "EPSG:4326", "source_crs": None, "latitude": -12, "longitude": -77}
    result = apply_coordinate_declaration(legacy, {"crs": "EPSG:4326"})
    assert result["crs"] is None
    assert result["source_crs"] is None
    assert legacy["crs"] == "EPSG:4326"
    source = apply_coordinate_declaration({"crs": "EPSG:4326"}, {})
    assert source["crs"] is None
    assert source["source_crs"] == "EPSG:4326"


def test_documented_declaration_is_applied_without_losing_source_conflicts():
    source = {"crs": "EPSG:32718", "warnings": ["OTHER"]}
    config = {"crs": "EPSG:4326", "crs_evidence": " Ficha técnica sintética 2026 "}
    result = apply_coordinate_declaration(source, config)
    assert result["crs"] == "EPSG:4326"
    assert result["source_crs"] == "EPSG:32718"
    assert result["crs_evidence"] == "Ficha técnica sintética 2026"
    assert result["warnings"] == ["OTHER", "CRS_CONFLICTIVO"]
    assert result["decision_constraints"] == ["CRS_CONFLICTIVO"]
    assert apply_coordinate_declaration(result, config) == result
    assert source == {"crs": "EPSG:32718", "warnings": ["OTHER"]}
