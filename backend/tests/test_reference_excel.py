"""Synthetic reference workbooks: no datum inference, no fabricated geometry."""

from copy import deepcopy
import io

from openpyxl import Workbook
import pytest
from sqlalchemy import func, select

from geopol.models import Catalog, Feature, Upload
from geopol.reference_excel import build_reference_bundle, parse_reference_excel, preview_reference_excel
from test_api import harness as harness

EVIDENCE = "Ficha técnica sintética, versión de prueba: WGS84 / EPSG:4326"
POLYGON = "POLYGON ((-78 -13, -76 -13, -76 -11, -78 -11, -78 -13))"
DOOR_HEADERS = ["ID", "UBIGEO", "CATVIA", "NOMVIA", "P17", "P17_A", "P13_1", "P13_2"]
DOOR = ["puerta-1", "010101", "AVENIDA", "DEMOSTRACION", "0012", "B", -12.1, -77.1]


def workbook_bytes(headers, rows, *, sheet="Referencia", second=None):
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = sheet
    worksheet.append(headers)
    for row in rows:
        worksheet.append(row)
    if second:
        worksheet = workbook.create_sheet(second[0])
        for row in second[1]:
            worksheet.append(row)
    stream = io.BytesIO()
    workbook.save(stream)
    return stream.getvalue()


def parse(tmp_path, headers=DOOR_HEADERS, rows=None, **options):
    path = tmp_path / "source.xlsx"
    path.write_bytes(workbook_bytes(headers, [DOOR] if rows is None else rows))
    return parse_reference_excel(
        path,
        path.name,
        kind=options.pop("kind", "doors"),
        source="Fuente sintética",
        version="Prueba-1",
        mapping=options.pop("mapping", {}),
        crs=options.pop("crs", "EPSG:4326"),
        crs_evidence=options.pop("crs_evidence", EVIDENCE),
        **options,
    )


def test_preview_dictionary_mapping_and_explicit_sheet(tmp_path):
    path = tmp_path / "source.xlsx"
    path.write_bytes(workbook_bytes(["Nota"], [["Metadatos"]], second=("Puertas", [DOOR_HEADERS, DOOR])))
    preview = preview_reference_excel(path, path.name, kind="doors", sheet="Puertas")
    assert preview["sheets"] == ["Referencia", "Puertas"]
    assert preview["sheet"] == "Puertas"
    assert preview["suggested_mapping"]["latitude"] == "P13_1"
    assert preview["suggested_mapping"]["longitude"] == "P13_2"
    assert "sample" not in preview
    with pytest.raises(ValueError, match="No existe"):
        preview_reference_excel(path, path.name, kind="doors", sheet="Ausente")


def test_valid_door_keeps_number_suffix_ubigeo_and_provenance(tmp_path):
    features, report = parse(tmp_path)
    assert report["readiness"] == "ready"
    assert report["row_count"] == report["ready_rows"] == 1
    assert report["staged_rows"] == 0
    feature = features[0]
    assert feature["ubigeo"] == "010101"
    assert feature["door_number"] == "0012B"
    assert feature["geometry"] == {"type": "Point", "coordinates": [-77.1, -12.1]}
    assert feature["source"] == "Fuente sintética" and feature["version"] == "Prueba-1"


def test_coordinates_never_confirm_crs_and_metadata_evidence_is_required(tmp_path):
    features, report = parse(tmp_path, crs=None, crs_evidence=None)
    assert features == []
    assert report["readiness"] == "staged"
    assert report["issue_counts"] == {"CRS_NO_CONFIRMADO": 1}
    with pytest.raises(ValueError, match="fuente que confirma"):
        parse(tmp_path, crs_evidence="")
    with pytest.raises(ValueError, match="Transforme"):
        parse(tmp_path, crs="EPSG:32718")


def test_numeric_catvia_is_not_guessed(tmp_path):
    row = [*DOOR]
    row[2] = 1
    features, report = parse(tmp_path, rows=[row])
    assert not features and report["issue_counts"]["CAT_VIA_DOMAIN_UNCONFIRMED"] == 1
    features, report = parse(tmp_path, rows=[row], street_types={"1": "AVENIDA"})
    assert report["readiness"] == "ready"
    assert features[0]["street_type"] == "AVENIDA"


def test_omitting_known_dictionary_columns_does_not_discard_safety_context(tmp_path):
    row = [*DOOR]
    row[2] = 1
    explicit = {
        "id": "ID",
        "ubigeo": "UBIGEO",
        "street_name": "NOMVIA",
        "door_number": "P17",
        "latitude": "P13_1",
        "longitude": "P13_2",
    }
    features, report = parse(tmp_path, rows=[row], mapping=explicit)
    assert not features and report["issue_counts"]["CAT_VIA_DOMAIN_UNCONFIRMED"] == 1
    features, report = parse(tmp_path, rows=[row], mapping=explicit, street_types={"1": "AVENIDA"})
    assert features[0]["door_number"] == "0012B"


def test_formulas_and_alt_address_fields_are_staged(tmp_path):
    formula = [*DOOR]
    formula[0] = "formula"
    formula[4] = "=10+2"
    alternate = [*DOOR]
    alternate[0] = "alternativa"
    features, report = parse(
        tmp_path, headers=[*DOOR_HEADERS, "P22"], rows=[[*formula, None], [*alternate, "7"]]
    )
    assert not features
    assert report["staged_rows"] == 2
    assert report["issue_counts"]["FILA_ORIGEN_CON_INCIDENCIA"] == 1
    assert report["issue_counts"]["MANZANA_LOT_CONTEXT_REQUIRES_MAPPING"] == 1


@pytest.mark.parametrize("bad_value", ["NaN", "Infinity", 100, "=1+2"])
def test_invalid_coordinate_rows_cannot_enter_catalog(tmp_path, bad_value):
    bad = [*DOOR]
    bad[0] = "bad"
    bad[6] = bad_value
    features, report = parse(tmp_path, rows=[DOOR, bad])
    assert len(features) == 1 and report["staged_rows"] == 1
    assert report["readiness"] == "partial"


def test_duplicate_identifiers_and_mapping_rejected_without_omission(tmp_path):
    with pytest.raises(ValueError, match="duplicado"):
        parse(tmp_path, rows=[DOOR, DOOR])
    with pytest.raises(ValueError, match="mapeo"):
        parse(tmp_path, mapping={"latitude": "MISSING"})
    with pytest.raises(ValueError, match="mapeo"):
        parse(tmp_path, mapping={"arbitrary": "UBIGEO"})


def test_street_table_does_not_manufacture_line_from_point(tmp_path):
    features, report = parse(
        tmp_path, headers=["UBIGEO", "NOMVIA", "X", "Y"], rows=[["150101", "AV DEMO", -77, -12]], kind="roads"
    )
    assert not features
    assert report["issue_counts"] == {"GEOMETRIA_NO_DISPONIBLE": 1}


@pytest.mark.parametrize("category,street_types", [(1, {"1": "AVENIDA"}), ("AVENIDA", {})])
@pytest.mark.parametrize("feature_kind", ["street", "block"])
def test_road_type_conflict_stays_staged_and_cannot_supply_auto_quality(
    tmp_path, category, street_types, feature_kind
):
    from geopol.domain.normalization import normalize_record
    from geopol.domain.quality import resolve_quality_stage

    features, report = parse(
        tmp_path,
        headers=["UBIGEO", "CATVIA", "NOMVIA", "kind", "CUADRA", "WKT"],
        rows=[["150101", category, "JR LIBERTAD", feature_kind, 2, "LINESTRING (-77.1 -12.1, -77.2 -12.1)"]],
        kind="roads",
        street_types=street_types,
    )
    assert features == []
    assert report["readiness"] == "staged"
    assert report["issue_counts"] == {"STREET_TYPE_CONFLICT": 1}
    normalized = normalize_record({"location_original": "AV LIBERTAD CUADRA 2", "ubigeo": "150101"})
    result = resolve_quality_stage(
        normalized,
        features,
        reference_available=True,
        stage="block" if feature_kind == "block" else "street",
        available_reference_kinds=[],
    )
    assert result["resolution"] != "ACEPTADO_AUTOMATICO"
    assert result["quality_code"] is None
    assert result["geometry"] is None


def test_road_type_agreement_keeps_explicit_valid_reference(tmp_path):
    features, report = parse(
        tmp_path,
        headers=["UBIGEO", "CATVIA", "NOMVIA", "kind", "CUADRA", "WKT"],
        rows=[["150101", 1, "AV LIBERTAD", "block", 2, "LINESTRING (-77.1 -12.1, -77.2 -12.1)"]],
        kind="roads",
        street_types={"1": "AVENIDA"},
    )
    assert report["readiness"] == "ready"
    assert features[0]["street_type"] == "AVENIDA"
    assert features[0]["street_name"] == "LIBERTAD"


@pytest.mark.parametrize(
    "kind,headers,row,expected_kind",
    [
        (
            "roads",
            ["UBIGEO", "NOMVIA", "WKT"],
            ["150101", "AV DEMO", "LINESTRING (-77 -12, -77.01 -12.01)"],
            "street",
        ),
        (
            "roads",
            ["UBIGEO", "NOMVIA", "kind", "CUADRA", "WKT"],
            ["150101", "AV DEMO", "CUADRA", 4, "LINESTRING (-77 -12, -77.01 -12.01)"],
            "block",
        ),
        ("boundaries", ["UBIGEO", "NOMBDIST", "WKT"], ["150101", "DISTRITO DEMO", POLYGON], "boundary"),
        (
            "jurisdictions",
            ["UBIGEO", "jurisdiccion", "WKT"],
            ["150101", "JURISDICCION DEMO", POLYGON],
            "jurisdiction",
        ),
    ],
)
def test_real_geometry_types_are_kept(tmp_path, kind, headers, row, expected_kind):
    features, report = parse(tmp_path, headers=headers, rows=[row], kind=kind)
    assert report["readiness"] == "ready"
    assert features[0]["kind"] == expected_kind
    assert features[0]["geometry"]["type"] in {"LineString", "Polygon"}
    assert "latitude" not in features[0]


def test_centers_are_reference_points_not_poi_or_doors(tmp_path):
    features, report = parse(
        tmp_path,
        headers=["UBIGEO", "CODCCPP", "NOMBCCPP", "latitud", "longitud"],
        rows=[["150101", "0001", "CENTRO DEMO", -12, -77]],
        kind="centers",
    )
    assert report["readiness"] == "ready"
    assert features[0]["kind"] == "site"
    assert features[0]["point_role"] == "settlement_reference"
    assert features[0]["reference_precision"] == "centro_poblado"
    assert features[0]["center_code"] == "0001"


@pytest.mark.parametrize(
    "code,level", [("15", None), ("1501", None), ("150101", "PROVINCIA"), ("10101", None)]
)
def test_upper_level_boundaries_never_become_district_boundaries(tmp_path, code, level):
    features, report = parse(
        tmp_path, headers=["UBIGEO", "nivel", "WKT"], rows=[[code, level, POLYGON]], kind="boundaries"
    )
    assert not features and report["staged_rows"] == 1


@pytest.mark.parametrize(
    "geometry",
    [
        "POINT (-77 -12)",
        "POLYGON Z ((-78 -13 1, -76 -13 1, -76 -11 1, -78 -13 1))",
        "POLYGON ((-200 -13, -76 -13, -76 -11, -200 -13))",
    ],
)
def test_incompatible_or_invalid_geometries_stay_staged(tmp_path, geometry):
    features, report = parse(
        tmp_path, headers=["UBIGEO", "WKT"], rows=[["150101", geometry]], kind="boundaries"
    )
    assert not features and report["staged_rows"] == 1


def test_declared_source_crs_conflict_stays_staged(tmp_path):
    features, report = parse(tmp_path, headers=[*DOOR_HEADERS, "SRID"], rows=[[*DOOR, "EPSG:32718"]])
    assert not features
    assert report["issue_counts"]["CRS_DECLARADO_EN_FILA_CONTRADICTORIO"] == 1


def import_excel(harness, *, rows=None, crs="EPSG:4326"):
    upload_id = harness.upload(
        workbook_bytes(DOOR_HEADERS, [DOOR] if rows is None else rows), "reference.xlsx"
    )
    payload = {
        "upload_id": upload_id,
        "kind": "doors",
        "name": "Puertas sintéticas",
        "source": "Institución sintética",
        "version": "2025-demo",
        "crs": crs,
        "crs_evidence": EVIDENCE if crs else None,
    }
    response = harness.client.post("/api/reference-excels", json=payload, headers=harness.headers["admin"])
    assert response.status_code == 201, response.text
    return response.json(), upload_id


def test_api_import_preserves_upload_and_includes_readiness(harness):
    catalog, upload_id = import_excel(harness)
    assert catalog["feature_count"] == 1
    report = catalog["config"]["reference_excel"]
    assert report["readiness"] == "ready" and report["upload_id"] == upload_id
    with harness.sessions() as db:
        upload = db.get(Upload, upload_id)
        assert catalog["sha256"] == upload.sha256
        feature = db.scalar(select(Feature).where(Feature.catalog_id == catalog["id"]))
        assert feature.payload["source_upload_id"] == upload_id
        assert feature.payload["crs_evidence"] == EVIDENCE
    saved = harness.client.get(f"/api/references/{catalog['id']}", headers=harness.headers["analyst"])
    assert saved.json()["config"]["reference_excel"] == report


def test_api_staged_reference_remains_downloadable_and_has_no_features(harness):
    catalog, upload_id = import_excel(harness, crs=None)
    assert catalog["feature_count"] == 0 and catalog["kinds"] == []
    assert catalog["config"]["reference_excel"]["readiness"] == "staged"
    downloaded = harness.client.get(f"/api/uploads/{upload_id}/download", headers=harness.headers["admin"])
    assert downloaded.status_code == 200 and downloaded.content.startswith(b"PK")


def test_api_reference_permissions_and_completed_upload_contract(harness):
    upload_id = harness.upload(workbook_bytes(DOOR_HEADERS, [DOOR]), "reference.xlsx")
    payload = {"upload_id": upload_id, "kind": "doors"}
    for role in ("analyst", "reviewer", "operator"):
        response = harness.client.post(
            "/api/reference-excels/preview", json=payload, headers=harness.headers[role]
        )
        assert response.status_code == 403
    response = harness.client.post(
        "/api/reference-excels/preview", json=payload, headers=harness.headers["admin"]
    )
    assert response.status_code == 200
    payload["upload_id"] = harness.upload()
    response = harness.client.post(
        "/api/reference-excels/preview", json=payload, headers=harness.headers["admin"]
    )
    assert response.status_code == 422


def test_duplicate_import_failure_creates_no_catalog_or_feature(harness):
    upload_id = harness.upload(workbook_bytes(DOOR_HEADERS, [DOOR, DOOR]), "duplicate.xlsx")
    with harness.sessions() as db:
        before = db.scalar(select(func.count()).select_from(Catalog))
    response = harness.client.post(
        "/api/reference-excels",
        json={
            "upload_id": upload_id,
            "kind": "doors",
            "name": "Duplicado",
            "source": "Sintético",
            "version": "1",
            "crs": "EPSG:4326",
            "crs_evidence": EVIDENCE,
        },
        headers=harness.headers["admin"],
    )
    assert response.status_code == 422
    with harness.sessions() as db:
        assert db.scalar(select(func.count()).select_from(Catalog)) == before


def test_bundle_keeps_versions_namespaced_identifiers_and_staged_layers(harness):
    first, _ = import_excel(harness)
    second, _ = import_excel(harness)
    staged, _ = import_excel(harness, crs=None)
    with harness.sessions() as db:
        originals = list(
            db.scalars(select(Feature).where(Feature.catalog_id.in_([first["id"], second["id"]])))
        )
        payloads = [deepcopy(feature.payload) for feature in originals]
        combined = build_reference_bundle(db, [first["id"], second["id"], staged["id"]], "test-admin")
        db.commit()
        assert combined.feature_count == 2
        selections = combined.config["reference_bundle"]["catalogs"]
        assert len(selections) == 3 and combined.config["reference_bundle"]["readiness"] == "partial"
        features = list(db.scalars(select(Feature).where(Feature.catalog_id == combined.id)))
        assert len({feature.external_id for feature in features}) == 2
        assert all(feature.payload["version"] == "2025-demo" for feature in features)
        assert {feature.payload["origin_catalog_id"] for feature in features} == {first["id"], second["id"]}
        assert [feature.payload for feature in originals] == payloads


def test_row_and_payload_limits_fail_explicitly(tmp_path, monkeypatch):
    from geopol import reference_excel

    monkeypatch.setattr(reference_excel, "MAX_ROWS", 1)
    second = [*DOOR]
    second[0] = "second"
    with pytest.raises(ValueError, match="100 000"):
        parse(tmp_path, rows=[DOOR, second])
    monkeypatch.setattr(reference_excel, "MAX_ROWS", 100_000)
    monkeypatch.setattr(reference_excel, "MAX_PAYLOAD_BYTES", 10)
    with pytest.raises(ValueError, match="24 MiB"):
        parse(tmp_path)
