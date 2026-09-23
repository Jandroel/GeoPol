"""Explicit incident geography survives ingestion and does not merge locations."""

from geopol.domain.normalization import normalize_record
from geopol.domain.quality import resolve_quality_stage
from geopol.worker import unit_key
from test_domain_quality import boundary, center, jurisdiction


def test_explicit_center_mapping_reaches_reference_point_with_its_own_precision():
    query = normalize_record(
        {"complaint_id": "QA", "UBIGEO": "150101", "CC_LOCAL": "Los Pinos"}, {"center_name": "CC_LOCAL"}
    )
    result = resolve_quality_stage(query, [center(), boundary()], True, "nucleus")
    assert result["quality_status"] == "resolved"
    assert result["precision"] == "CENTRO_POBLADO"
    assert result["quality_code"] is None
    assert "LOS PINOS" in query["search_names"]
    other = normalize_record(
        {"complaint_id": "QA", "UBIGEO": "150101", "CC_LOCAL": "Otro centro"}, {"center_name": "CC_LOCAL"}
    )
    assert unit_key(query, 1) != unit_key(other, 2)


def test_station_jurisdiction_is_not_implicitly_used_as_incident_jurisdiction():
    raw = {"complaint_id": "QA", "UBIGEO": "150101", "jurisdiccion": "COMISARIA DEL PARQUE"}
    absent = normalize_record(raw)
    result = resolve_quality_stage(absent, [jurisdiction(), boundary()], True, "jurisdiction")
    assert result["quality_status"] != "resolved"
    explicit = normalize_record(raw, {"jurisdiction_name": "jurisdiccion"})
    result = resolve_quality_stage(explicit, [jurisdiction(), boundary()], True, "jurisdiction")
    assert result["quality_status"] == "resolved"
    assert result["product"] == "AREA_TRAMO"
    assert result["latitude"] is None and result["longitude"] is None
