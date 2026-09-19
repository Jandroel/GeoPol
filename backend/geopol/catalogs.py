import csv
import io
import json
import math
import re
import unicodedata

from shapely.geometry import shape
from shapely.errors import ShapelyError

from .domain.normalization import canonical_street_type, street_parts

KINDS = {"door", "block", "intersection", "site", "nucleus", "jurisdiction", "boundary"}


def search_key(value):
    value = unicodedata.normalize("NFKD", str(value or ""))
    value = "".join(c for c in value if not unicodedata.combining(c))
    return " ".join(value.upper().split())


def read_catalog(data: bytes, filename: str, source: str, version: str):
    text = data.decode("utf-8-sig")
    if filename.lower().endswith((".geojson", ".json")):
        document = json.loads(text)
        if document.get("type") != "FeatureCollection" or not isinstance(document.get("features"), list):
            raise ValueError("Se requiere GeoJSON FeatureCollection en EPSG:4326")
        if document.get("crs"):
            raise ValueError("No incluya CRS heredados: transforme el catálogo a EPSG:4326")
        records = []
        for feature in document["features"]:
            props = dict(feature.get("properties") or {})
            props["geometry"] = feature.get("geometry")
            if "id" not in props and feature.get("id") is not None:
                props["id"] = str(feature["id"])
            if props["geometry"] and props["geometry"].get("type") == "Point":
                props["longitude"], props["latitude"] = props["geometry"]["coordinates"][:2]
            records.append(props)
    else:
        reader = csv.DictReader(io.StringIO(text))
        if not reader.fieldnames or len(reader.fieldnames) != len(set(reader.fieldnames)):
            raise ValueError("Encabezados vacíos o duplicados")
        records = reader
    seen = set()
    for ordinal, raw in enumerate(records, 1):
        if ordinal > 100_000:
            raise ValueError("Máximo 100 000 entidades por catálogo en este MVP")
        feature = {str(k): v for k, v in raw.items() if v is not None and v != ""}
        identifier = str(feature.get("id") or ordinal)
        if identifier in seen or len(identifier) > 200:
            raise ValueError(f"Identificador duplicado o demasiado largo en entidad {ordinal}")
        seen.add(identifier)
        feature["id"] = identifier
        if feature.get("kind") not in KINDS:
            raise ValueError(f"Tipo de entidad inválido en {ordinal}")
        ubigeo = str(feature.get("ubigeo", "")).strip()
        if not re.fullmatch(r"\d{6}", ubigeo):
            raise ValueError(f"UBIGEO debe tener seis dígitos en entidad {ordinal}")
        feature["ubigeo"] = ubigeo
        declared_crs = search_key(feature.get("crs") or "EPSG:4326")
        if declared_crs not in {"EPSG:4326", "4326", "WGS84", "WGS 84"}:
            raise ValueError(f"Transforme la entidad {ordinal} a EPSG:4326 antes de importarla")
        for key in ("name", "street_type", "street_name", "cross_street"):
            if key in feature:
                feature[key] = search_key(feature[key])
        if "street_type" in feature:
            feature["street_type"] = canonical_street_type(feature["street_type"]) or feature["street_type"]
        for key in ("street_name", "cross_street"):
            if key in feature:
                inferred_type, street = street_parts(feature[key])
                feature[key] = street
                if key == "street_name" and inferred_type and not feature.get("street_type"):
                    feature["street_type"] = inferred_type
        if isinstance(feature.get("geometry"), str):
            feature["geometry"] = json.loads(feature["geometry"])
        geometry = feature.get("geometry")
        if geometry:
            try:
                parsed = shape(geometry)
            except ShapelyError as exc:
                raise ValueError(f"Geometría no interpretable en entidad {ordinal}") from exc
            if parsed.is_empty or not parsed.is_valid:
                raise ValueError(f"Geometría inválida en entidad {ordinal}")
            if parsed.has_z:
                raise ValueError(f"Convierta la geometría a dos dimensiones en entidad {ordinal}")
            bounds = parsed.bounds
            if (
                not all(math.isfinite(x) for x in bounds)
                or bounds[0] < -180
                or bounds[2] > 180
                or bounds[1] < -90
                or bounds[3] > 90
            ):
                raise ValueError(f"Geometría fuera de EPSG:4326 en entidad {ordinal}")
            if feature["kind"] == "boundary" and parsed.geom_type not in {"Polygon", "MultiPolygon"}:
                raise ValueError("Los límites territoriales deben ser polígonos")
        if feature["kind"] == "boundary" and not geometry:
            raise ValueError("Un límite territorial requiere geometría GeoJSON")
        if ("latitude" in feature) != ("longitude" in feature):
            raise ValueError(f"Par de coordenadas incompleto en entidad {ordinal}")
        if "latitude" in feature:
            lat, lon = float(feature["latitude"]), float(feature["longitude"])
            if (
                not math.isfinite(lat)
                or not math.isfinite(lon)
                or not -90 <= lat <= 90
                or not -180 <= lon <= 180
            ):
                raise ValueError(f"Coordenadas inválidas en entidad {ordinal}")
            feature.update(latitude=lat, longitude=lon)
        if "connects_at_grade" in feature:
            feature["connects_at_grade"] = str(feature["connects_at_grade"]).lower() in {"true", "1"}
        feature.update(source=source, version=version, crs="EPSG:4326")
        yield feature
    if not seen:
        raise ValueError("El catálogo no contiene entidades")
