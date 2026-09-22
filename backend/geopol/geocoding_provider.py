"""Opt-in ArcGIS batch pilot, separate from automatic decisions and operational data.

Only an explicitly prepared address file can enter this adapter. No worker or API
calls it automatically. Responses retain provider precision and are never promoted
to door reference features or accepted locations by this module.
"""

from __future__ import annotations

import argparse
import json
import math
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

MAX_BATCH = 100
MAX_RESPONSE_BYTES = 4 * 1024 * 1024
ADDRESS_FIELDS = frozenset({"address", "district", "province", "department"})


class ProviderError(ValueError):
    """A sanitized provider failure; never contains requests, tokens or addresses."""


@dataclass(frozen=True)
class ProviderConfig:
    enabled: bool = False
    endpoint: str = ""
    token: str = field(default="", repr=False)
    storage_authorization: str = ""

    @classmethod
    def from_environment(cls):
        return cls(
            enabled=os.environ.get("GEOPOL_ARCGIS_ENABLED", "").lower() == "true",
            endpoint=os.environ.get("GEOPOL_ARCGIS_ENDPOINT", ""),
            token=os.environ.get("GEOPOL_ARCGIS_TOKEN", ""),
            storage_authorization=os.environ.get("GEOPOL_ARCGIS_STORAGE_AUTHORIZATION", ""),
        )

    def validated_endpoint(self):
        message = "Configure una URL HTTPS de GeocodeServer, sin credenciales ni parámetros"
        try:
            parsed = urlsplit(self.endpoint)
            valid = (
                parsed.scheme == "https"
                and parsed.hostname
                and not parsed.username
                and not parsed.password
                and not parsed.query
                and not parsed.fragment
                and parsed.path.rstrip("/").endswith("/GeocodeServer")
                and (parsed.port is None or 1 <= parsed.port <= 65535)
            )
        except (ValueError, TypeError):
            # urlsplit and port validation can fail before our explicit checks.
            # Keep malformed configuration in the same sanitized status contract.
            raise ProviderError(message) from None
        if not valid:
            raise ProviderError(message)
        return self.endpoint.rstrip("/")

    def require_ready(self):
        if not self.enabled:
            raise ProviderError("La geocodificación externa está desactivada")
        endpoint = self.validated_endpoint()
        if not self.token.strip():
            raise ProviderError("Falta la credencial del servicio autorizado")
        if len(self.storage_authorization.strip()) < 8:
            raise ProviderError("Documente el permiso para almacenar resultados del servicio")
        return endpoint


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Authentication and address data must never follow a redirected request.
        return None


def provider_status(config=None):
    config = config or ProviderConfig.from_environment()
    try:
        config.require_ready()
        ready, reason = True, "Preparado para un piloto explícito; no activo en el procesamiento"
    except ProviderError as exc:
        ready, reason = False, str(exc)
    return {
        "provider": "arcgis",
        "configured": ready,
        "automatic_processing": False,
        "status": "pilot_ready" if ready else "disabled_or_incomplete",
        "reason": reason,
        "max_batch": MAX_BATCH,
    }


def address_records(addresses):
    if not isinstance(addresses, list) or not 1 <= len(addresses) <= MAX_BATCH:
        raise ProviderError(f"El piloto admite de 1 a {MAX_BATCH} direcciones por solicitud")
    records = []
    for index, address in enumerate(addresses, 1):
        if not isinstance(address, dict) or set(address) - ADDRESS_FIELDS:
            raise ProviderError(
                "Use solo address, district, province y department; no incluya datos de denuncia"
            )
        values = {}
        for name in ADDRESS_FIELDS:
            value = address.get(name, "")
            if not isinstance(value, str) or len(value) > 200:
                raise ProviderError("Los componentes de dirección deben ser textos de hasta 200 caracteres")
            values[name] = value.strip()
        if not values["address"] or not values["district"]:
            raise ProviderError("Cada dirección necesita al menos address y district")
        records.append(
            {
                "attributes": {
                    "OBJECTID": index,
                    "Address": values["address"],
                    "District": values["district"],
                    "Subregion": values["province"],
                    "Region": values["department"],
                    "CountryCode": "PER",
                }
            }
        )
    return records


def parse_response(document, count, endpoint, acquired_at):
    if not isinstance(document, dict) or document.get("error"):
        raise ProviderError("El servicio rechazó la solicitud; compruebe acceso, permisos y disponibilidad")
    locations = document.get("locations")
    spatial_reference = document.get("spatialReference", {})
    if (
        not isinstance(spatial_reference, dict)
        or spatial_reference.get("latestWkid", spatial_reference.get("wkid")) != 4326
    ):
        raise ProviderError("El servicio no declaró coordenadas EPSG:4326")
    if not isinstance(locations, list) or len(locations) != count:
        raise ProviderError("El servicio devolvió un lote incompleto; no se guardaron resultados parciales")
    seen, output = set(), []
    for location in locations:
        if not isinstance(location, dict) or not isinstance(location.get("attributes"), dict):
            raise ProviderError("Respuesta geográfica no interpretable")
        attrs = location["attributes"]
        result_id = attrs.get("ResultID")
        if type(result_id) is not int or not 1 <= result_id <= count or result_id in seen:
            raise ProviderError("Identificadores de respuesta duplicados o ajenos al lote")
        seen.add(result_id)
        match_type, status = str(attrs.get("Addr_type", "")), attrs.get("Status")
        if status not in {"M", "T", "U"}:
            raise ProviderError("Estado de coincidencia desconocido")
        score = attrs.get("Score", location.get("score"))
        if score is not None and (
            isinstance(score, bool)
            or not isinstance(score, (int, float))
            or not 0 <= score <= 100
            or not math.isfinite(score)
        ):
            raise ProviderError("Puntaje inválido en la respuesta")
        geometry = None
        if status != "U":
            point = location.get("location")
            if not isinstance(point, dict):
                raise ProviderError("Falta la geometría de un candidato")
            x, y = point.get("x"), point.get("y")
            if (
                isinstance(x, bool)
                or isinstance(y, bool)
                or not isinstance(x, (int, float))
                or not isinstance(y, (int, float))
                or not math.isfinite(x)
                or not math.isfinite(y)
                or not -180 <= x <= 180
                or not -90 <= y <= 90
            ):
                raise ProviderError("Coordenadas inválidas en la respuesta")
            geometry = {"type": "Point", "coordinates": [x, y]}
        role = {
            "PointAddress": "address_reference_point",
            "Subaddress": "subaddress_reference_point",
            "StreetAddress": "interpolated_point",
            "PointAddressInt": "interpolated_point",
            "StreetAddressExt": "extrapolated_point",
            "StreetInt": "intersection_candidate",
            "StreetName": "street_representative_point",
            "Locality": "locality_representative_point",
            "POI": "place_candidate",
        }.get(match_type, "unclassified")
        output.append(
            {
                "input_ordinal": result_id,
                "provider": "arcgis",
                "endpoint": endpoint,
                "acquired_at": acquired_at,
                "crs": "EPSG:4326",
                "status": status,
                "matched_address": location.get("address"),
                "match_type": match_type,
                "provider_score": score,
                "score_is_probability": False,
                "geometry": geometry,
                "point_role": role,
                "attributes": {
                    key: attrs.get(key)
                    for key in (
                        "Match_addr",
                        "Addr_type",
                        "Status",
                        "AddNum",
                        "StName",
                        "StType",
                        "District",
                        "City",
                        "Subregion",
                        "Region",
                        "Country",
                        "Type",
                    )
                },
                "accepted": False,
                "required_checks": ["territory", "address_components", "precision", "conflicting_evidence"],
            }
        )
    return sorted(output, key=lambda item: item["input_ordinal"])


def geocode_batch(addresses, config, *, opener=None):
    endpoint = config.require_ready()
    records = address_records(addresses)
    data = urlencode(
        {
            "f": "json",
            "addresses": json.dumps({"records": records}),
            "sourceCountry": "PER",
            "outSR": "4326",
            "outFields": "*",
            "matchOutOfRange": "false",
            "locationType": "street",
            "comprehensiveZoneMatch": "false",
            "interpolatePointAddress": "false",
        }
    ).encode("utf-8")
    request = Request(
        endpoint + "/geocodeAddresses",
        data=data,
        method="POST",
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "X-Esri-Authorization": "Bearer " + config.token,
            "User-Agent": "GeoPol/0.1 institutional-geocoding-pilot",
        },
    )
    try:
        with (opener or build_opener(NoRedirects())).open(request, timeout=30) as response:
            content = response.read(MAX_RESPONSE_BYTES + 1)
        if len(content) > MAX_RESPONSE_BYTES:
            raise ProviderError("La respuesta supera el límite del piloto")
        document = json.loads(content)
    except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
        if isinstance(exc, ProviderError):
            raise
        raise ProviderError("No se pudo completar la consulta al servicio autorizado") from None
    return parse_response(document, len(records), endpoint, datetime.now(timezone.utc).isoformat())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, help="JSON con lista de componentes de dirección preparados")
    parser.add_argument("--output", type=Path, help="Archivo nuevo de candidatos para evaluación local")
    parser.add_argument("--allow-network", action="store_true", help="Ejecutar el piloto externo configurado")
    args = parser.parse_args()
    if not args.allow_network:
        print(json.dumps(provider_status(), ensure_ascii=False))
        return 0
    try:
        if not args.input or not args.output:
            raise ProviderError("Indique archivo de direcciones preparado y salida nueva")
        if args.output.exists():
            raise ProviderError("La salida ya existe; elija un archivo nuevo")
        addresses = json.loads(args.input.read_text(encoding="utf-8-sig"))
        config = ProviderConfig.from_environment()
        candidates = geocode_batch(addresses, config)
        with args.output.open("x", encoding="utf-8") as stream:
            json.dump({"candidates": candidates, "automatic_acceptance": False}, stream, ensure_ascii=False)
        print(json.dumps({"candidates": len(candidates), "automatic_acceptance": False}))
        return 0
    except (ProviderError, OSError, json.JSONDecodeError):
        print("No se completó el piloto. Revise configuración, archivos, permiso y respuesta del servicio.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
