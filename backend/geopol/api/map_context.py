"""Bounded, local reference geometry for orientation; never a geographic decision."""

import json

from fastapi import APIRouter, Depends, Query
from sqlalchemy import case, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Feature, Run, User
from ..security import current_user
from .common import require

router = APIRouter()
MAX_CONTEXT_FEATURES = 500
MAX_CONTEXT_BYTES = 2 * 1024 * 1024
CONTEXT_KINDS = {"boundary", "street", "block", "manzana", "nucleus", "site"}
AREA_GEOMETRIES = {"LineString", "MultiLineString", "Polygon", "MultiPolygon"}


@router.get("/api/runs/{identifier}/map-context")
def map_context(
    identifier: str,
    ubigeo: str = Query(pattern=r"^\d{6}$"),
    db: Session = Depends(get_db),
    _: User = Depends(current_user),
):
    run = require(db, Run, identifier)
    collection = {
        "type": "FeatureCollection",
        "features": [],
        "truncated": False,
        "reference_id": run.reference_id,
        "sources": [],
        "context_only": True,
    }
    if not run.reference_id:
        return collection
    query = (
        select(Feature)
        .where(
            Feature.catalog_id == run.reference_id,
            Feature.ubigeo == ubigeo,
            Feature.kind.in_(CONTEXT_KINDS),
            # Filter before LIMIT: point sites cannot consume the display budget
            # and hide actual streets. SQLAlchemy renders this JSON access for
            # SQLite and PostgreSQL; the cursor still fetches one row at a time.
            Feature.payload["geometry"]["type"].as_string().in_(sorted(AREA_GEOMETRIES)),
        )
        .order_by(case((Feature.kind == "boundary", 0), else_=1), Feature.external_id)
        .limit(MAX_CONTEXT_FEATURES + 1)
        .execution_options(yield_per=1)
    )
    used_bytes, sources = 0, set()
    rows = db.scalars(query)
    try:
        for index, row in enumerate(rows):
            if index >= MAX_CONTEXT_FEATURES:
                collection["truncated"] = True
                break
            payload = row.payload
            geometry = payload.get("geometry")
            if not geometry or geometry.get("type") not in AREA_GEOMETRIES:
                continue
            feature = {
                "type": "Feature",
                "id": row.external_id,
                "geometry": geometry,
                "properties": {
                    "kind": row.kind,
                    "name": payload.get("street_name") or payload.get("name") or "",
                    "source": payload.get("source") or "",
                    "version": payload.get("version") or "",
                },
            }
            size = len(json.dumps(feature, ensure_ascii=False).encode("utf-8"))
            if used_bytes + size > MAX_CONTEXT_BYTES:
                collection["truncated"] = True
                continue
            collection["features"].append(feature)
            used_bytes += size
            if feature["properties"]["source"]:
                sources.add(feature["properties"]["source"])
    finally:
        rows.close()
    collection["sources"] = sorted(sources)
    return collection
