import io
import json
from urllib.error import URLError
from urllib.parse import parse_qs

import pytest
from test_api import harness as harness

from geopol.geocoding_provider import (
    NoRedirects,
    ProviderConfig,
    ProviderError,
    address_records,
    geocode_batch,
    parse_response,
    provider_status,
)

ENDPOINT = "https://geocoder.example.org/arcgis/rest/services/Demo/GeocodeServer"
CONFIG = ProviderConfig(True, ENDPOINT, "synthetic-secret", "Permiso sintético de almacenamiento")
ADDRESS = {"address": "CALLE DEMOSTRACION 10", "district": "DISTRITO FICTICIO"}


def response_for(match_type="PointAddress", status="M", result_id=1):
    return {
        "spatialReference": {"wkid": 4326},
        "locations": [
            {
                "address": "CALLE DEMOSTRACION 10",
                "location": {"x": -77, "y": -12},
                "attributes": {
                    "ResultID": result_id,
                    "Status": status,
                    "Addr_type": match_type,
                    "Score": 100,
                },
            }
        ],
    }


class FakeService:
    def __init__(self, document):
        self.document = document
        self.request = None

    def open(self, request, timeout):
        self.request = request
        assert timeout == 30
        return io.BytesIO(json.dumps(self.document).encode())


def test_disabled_configuration_cannot_send_anything():
    fake = FakeService(response_for())
    with pytest.raises(ProviderError, match="desactivada"):
        geocode_batch([ADDRESS], ProviderConfig(), opener=fake)
    assert fake.request is None
    assert provider_status(ProviderConfig())["automatic_processing"] is False
    assert "synthetic-secret" not in repr(CONFIG)
    assert "synthetic-secret" not in json.dumps(provider_status(CONFIG))


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://geocoder.example.org/GeocodeServer",
        "https://user:secret@example.org/GeocodeServer",
        ENDPOINT + "?token=secret",
        ENDPOINT + "#fragment",
        "https://example.org/not-a-geocoder",
    ],
)
def test_configuration_rejects_insecure_or_credential_bearing_urls(endpoint):
    with pytest.raises(ProviderError):
        ProviderConfig(True, endpoint, "token", "Autorización sintética").require_ready()


@pytest.mark.parametrize(
    "endpoint",
    [
        "https://[invalid/GeocodeServer",
        "https://geocoder.example.org:not-a-port/GeocodeServer",
        "https://geocoder.example.org:99999/GeocodeServer",
    ],
)
def test_malformed_endpoint_is_a_sanitized_disabled_status(endpoint):
    config = ProviderConfig(True, endpoint, "synthetic-secret", "Permiso sintético")
    status = provider_status(config)
    assert status["status"] == "disabled_or_incomplete"
    assert status["configured"] is False
    assert endpoint not in status["reason"]
    assert "synthetic-secret" not in json.dumps(status)
    fake = FakeService(response_for())
    with pytest.raises(ProviderError, match="URL HTTPS"):
        geocode_batch([ADDRESS], config, opener=fake)
    assert fake.request is None


def test_status_endpoint_handles_malformed_configuration_without_server_error(harness, monkeypatch):
    monkeypatch.setenv("GEOPOL_ARCGIS_ENABLED", "true")
    monkeypatch.setenv("GEOPOL_ARCGIS_ENDPOINT", "https://[invalid/GeocodeServer")
    monkeypatch.setenv("GEOPOL_ARCGIS_TOKEN", "synthetic-secret")
    monkeypatch.setenv("GEOPOL_ARCGIS_STORAGE_AUTHORIZATION", "Permiso sintético")
    response = harness.client.get("/api/geocoding-provider", headers=harness.headers["analyst"])
    assert response.status_code == 200
    assert response.json()["status"] == "disabled_or_incomplete"
    assert "synthetic-secret" not in response.text


def test_prepared_input_rejects_whole_complaint_records_and_large_batches():
    with pytest.raises(ProviderError, match="datos de denuncia"):
        address_records([{**ADDRESS, "complaint_id": "PRIVATE", "person_name": "PRIVATE"}])
    with pytest.raises(ProviderError):
        address_records([ADDRESS] * 101)
    with pytest.raises(ProviderError):
        address_records([{"address": "SIN DISTRITO"}])


def test_request_uses_body_opaque_ordinals_and_conservative_parameters():
    fake = FakeService(response_for())
    result = geocode_batch([ADDRESS], CONFIG, opener=fake)
    request = fake.request
    assert request.method == "POST"
    assert request.full_url == ENDPOINT + "/geocodeAddresses"
    assert request.get_header("X-esri-authorization") == "Bearer synthetic-secret"
    values = parse_qs(request.data.decode())
    assert values["sourceCountry"] == ["PER"]
    assert values["matchOutOfRange"] == ["false"]
    assert values["interpolatePointAddress"] == ["false"]
    assert values["comprehensiveZoneMatch"] == ["false"]
    assert "token" not in values
    record = json.loads(values["addresses"][0])["records"][0]["attributes"]
    assert record["OBJECTID"] == 1
    assert record["District"] == ADDRESS["district"]
    assert result[0]["accepted"] is False
    assert result[0]["point_role"] == "address_reference_point"
    assert result[0]["score_is_probability"] is False


@pytest.mark.parametrize(
    "match_type,role",
    [
        ("StreetAddress", "interpolated_point"),
        ("Locality", "locality_representative_point"),
        ("StreetName", "street_representative_point"),
        ("Unknown", "unclassified"),
    ],
)
def test_lower_precision_and_unknown_results_are_never_promoted_to_doors(match_type, role):
    result = parse_response(response_for(match_type), 1, ENDPOINT, "synthetic-time")[0]
    assert result["point_role"] == role
    assert result["match_type"] == match_type
    assert result["accepted"] is False
    assert "territory" in result["required_checks"]
    assert "kind" not in result


def test_partial_duplicate_and_wrong_crs_responses_are_rejected():
    with pytest.raises(ProviderError, match="incompleto"):
        parse_response(response_for(), 2, ENDPOINT, "time")
    duplicate = response_for()
    duplicate["locations"] *= 2
    with pytest.raises(ProviderError, match="duplicados"):
        parse_response(duplicate, 2, ENDPOINT, "time")
    wrong_crs = response_for()
    wrong_crs["spatialReference"] = {"wkid": 3857}
    with pytest.raises(ProviderError, match="EPSG:4326"):
        parse_response(wrong_crs, 1, ENDPOINT, "time")


@pytest.mark.parametrize("score", [float("nan"), float("inf"), -float("inf"), -1, 101, True, "100", 10**400])
@pytest.mark.parametrize("in_attributes", [True, False])
def test_invalid_provider_scores_cannot_create_nonstandard_json(score, in_attributes):
    document = response_for()
    location = document["locations"][0]
    del location["attributes"]["Score"]
    target = location["attributes"] if in_attributes else location
    target["Score" if in_attributes else "score"] = score
    with pytest.raises(ProviderError, match="Puntaje"):
        geocode_batch([ADDRESS], CONFIG, opener=FakeService(document))


@pytest.mark.parametrize("score", [None, 0, 99.5, 100])
def test_supported_scores_preserve_the_provider_value_and_strict_json(score):
    document = response_for()
    document["locations"][0]["attributes"]["Score"] = score
    result = parse_response(document, 1, ENDPOINT, "time")
    assert result[0]["provider_score"] == score
    assert result[0]["accepted"] is False
    json.dumps(result, allow_nan=False)


def test_unmatched_has_no_point_and_failures_do_not_echo_sensitive_payloads():
    unmatched = parse_response(response_for(status="U"), 1, ENDPOINT, "time")[0]
    assert unmatched["geometry"] is None

    class BrokenService:
        def open(self, request, timeout):
            raise URLError("synthetic-secret and private address")

    with pytest.raises(ProviderError) as error:
        geocode_batch([ADDRESS], CONFIG, opener=BrokenService())
    assert "synthetic-secret" not in str(error.value)
    assert "private address" not in str(error.value)
    assert NoRedirects().redirect_request(None, None, 302, None, None, "https://other.invalid") is None
