"""Complete per-run aggregates and a bounded map of accepted local results."""

import json
import math
import time
from collections import Counter, defaultdict

from fastapi import APIRouter, Depends, Query
from shapely.geometry import shape
from shapely.errors import ShapelyError
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Location, Run, User
from ..security import current_user
from ..serialization import iso
from .common import require

router = APIRouter()
MAP_BYTES = 3 * 1024 * 1024
ACCEPTED = {"ACEPTADO_AUTOMATICO", "ACEPTADO_MANUAL"}
AREA_PRECISIONS = {"VIA", "CUADRA", "MANZANA", "NUCLEO", "JURISDICCION"}
REFERENCE_METHODS = {
    "PUERTA_CON_TIPO",
    "PUERTA_SIN_TIPO",
    "CUADRA_CON_TIPO",
    "CUADRA_SIN_TIPO",
    "CRUCE",
    "VIA_JURISDICCION",
    "NUCLEO",
    "CCPP_PUNTO_REFERENCIA",
    "JURISDICCION",
    "MANZANA_LOTE",
    "MANZANA",
    "SITIO",
    "VIA",
}


def result_geometry(geometry, latitude, longitude, precision):
    """Validate display geometry; never invent points from an area or line."""
    if geometry:
        try:
            parsed = shape(geometry)
            if (
                parsed.geom_type
                in {"Point", "MultiPoint", "LineString", "MultiLineString", "Polygon", "MultiPolygon"}
                and not parsed.is_empty
                and parsed.is_valid
                and all(math.isfinite(value) for value in parsed.bounds)
                and -180 <= parsed.bounds[0] <= parsed.bounds[2] <= 180
                and -90 <= parsed.bounds[1] <= parsed.bounds[3] <= 90
                and not (precision in AREA_PRECISIONS and parsed.geom_type in {"Point", "MultiPoint"})
            ):
                return geometry
        except (ValueError, TypeError, KeyError, ShapelyError):
            pass
        return None
    if (
        precision not in AREA_PRECISIONS
        and all(isinstance(value, (int, float)) and math.isfinite(value) for value in (latitude, longitude))
        and -90 <= latitude <= 90
        and -180 <= longitude <= 180
    ):
        return {"type": "Point", "coordinates": [longitude, latitude]}
    return None


def result_layer(resolution, manual, method):
    if resolution == "ACEPTADO_MANUAL" or manual:
        return "manual"
    if method in {"COORD_ORIGINAL", "COORD_TEXTO"}:
        return "original"
    if method in REFERENCE_METHODS:
        return "reference"
    return "other"


@router.get("/api/runs/{identifier}/statistics")
def statistics(
    identifier: str,
    map_limit: int = Query(2000, ge=1, le=5000),
    db: Session = Depends(get_db),
    _: User = Depends(current_user),
):
    run = require(db, Run, identifier)
    resolutions, flags, review_states, layers = Counter(), Counter(), Counter(), Counter()
    districts = defaultdict(lambda: {"units": 0, "source_rows": 0, "mapped": 0, "names": set()})
    features, used_bytes, mapped, accepted, units = [], 0, 0, 0, 0
    # Iterate a narrow projection in bounded batches. Totals include every location,
    # even after the display-only map budget is exhausted.
    rows = db.execute(
        select(
            Location.id,
            Location.ubigeo,
            Location.normalized["district"].as_string(),
            Location.resolution,
            Location.method,
            Location.precision,
            Location.manual,
            Location.source_row_count,
            Location.quality_flag,
            Location.review_state,
            Location.latitude,
            Location.longitude,
            Location.geometry,
        )
        .where(Location.run_id == identifier)
        .order_by(Location.id)
        .execution_options(yield_per=100)
    )
    try:
        for (
            identifier_,
            ubigeo,
            district,
            resolution,
            method,
            precision,
            manual,
            row_count,
            flag,
            review_state,
            lat,
            lon,
            geometry,
        ) in rows:
            units += 1
            resolutions[resolution] += 1
            flags[flag] += 1
            review_states[review_state] += 1
            group = districts[ubigeo or ""]
            group["units"] += 1
            group["source_rows"] += row_count
            if district and len(group["names"]) < 2:
                group["names"].add(district)
            if resolution not in ACCEPTED:
                continue
            accepted += 1
            drawable = result_geometry(geometry, lat, lon, precision)
            if not drawable:
                continue
            mapped += 1
            group["mapped"] += 1
            layer = result_layer(resolution, manual, method)
            layers[layer] += 1
            if len(features) >= map_limit:
                continue
            feature = {
                "type": "Feature",
                "id": identifier_,
                "geometry": drawable,
                "properties": {
                    "id": identifier_,
                    "ubigeo": ubigeo or "",
                    "method": method or "SIN_METODO",
                    "precision": precision,
                    "layer": layer,
                },
            }
            size = len(json.dumps(feature, ensure_ascii=False).encode("utf-8"))
            if used_bytes + size <= MAP_BYTES:
                features.append(feature)
                used_bytes += size
    finally:
        rows.close()
    return {
        "run_id": run.id,
        "generated_at": iso(time.time()),
        "scope": "selected_run_current_results",
        "totals": {
            "units": units,
            "source_rows": run.source_rows,
            "accepted": accepted,
            "mapped": mapped,
            "without_accepted_geometry": units - mapped,
            "excluded": resolutions.get("EXCLUIDO_FLAG_10", 0),
            "issue_rows": run.issue_rows,
        },
        "resolutions": [{"resolution": key, "units": value} for key, value in sorted(resolutions.items())],
        "flags": [
            {"flag": key, "units": value}
            for key, value in sorted(flags.items(), key=lambda pair: (pair[0] is None, pair[0] or 0))
        ],
        "review_states": [
            {"state": key, "units": value}
            for key, value in sorted(review_states.items(), key=lambda pair: pair[0] or "")
        ],
        "districts": [
            {
                "ubigeo": key,
                "district": next(iter(value["names"])) if len(value["names"]) == 1 else None,
                "name_conflict": len(value["names"]) > 1,
                "units": value["units"],
                "source_rows": value["source_rows"],
                "mapped": value["mapped"],
            }
            for key, value in sorted(districts.items(), key=lambda pair: (-pair[1]["units"], pair[0]))
        ],
        "map": {
            "type": "FeatureCollection",
            "features": features,
            "total": mapped,
            "shown": len(features),
            "limit": map_limit,
            "truncated": len(features) < mapped,
            "layers": dict(layers),
        },
    }
