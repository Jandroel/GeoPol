"""Explicit reviewer-approved addresses; no automatic promotion of model output."""

import hashlib
import json

from shapely.geometry import Point, mapping, shape
from sqlalchemy import select, update

from .domain.normalization import DECISION_WARNINGS, key, valid_pair
from .models import AddressMemory, Location


def address_signature(normalized):
    address, ubigeo = key(normalized.get("location_normalized")), normalized.get("ubigeo")
    if not address or not ubigeo or len(str(ubigeo)) != 6:
        return None
    fields = (
        "street_type",
        "street_name",
        "door_number",
        "block_number",
        "cross_street",
        "manzana_code",
        "lot_number",
        "site_name",
        "urban_core",
        "district",
    )
    value = [address, str(ubigeo), *[key(normalized.get(field)) for field in fields]]
    return hashlib.sha256(json.dumps(value, ensure_ascii=False).encode()).hexdigest()


def usable_geometry(value, product):
    try:
        geometry = shape(value)
        allowed = (
            {"Point"} if product == "PUNTO" else {"LineString", "MultiLineString", "Polygon", "MultiPolygon"}
        )
        west, south, east, north = geometry.bounds
        return bool(
            geometry.geom_type in allowed
            and geometry.is_valid
            and not geometry.is_empty
            and not geometry.has_z
            and -180 <= west <= east <= 180
            and -90 <= south <= north <= 90
        )
    except (ValueError, TypeError, AttributeError, KeyError):
        return False


def retire_memory(db, location_id):
    db.execute(update(AddressMemory).where(AddressMemory.location_id == location_id).values(active=False))


def remember_address(db, item, user, source_candidate=None):
    signature = address_signature(item.normalized)
    if memory_constraints(item.normalized):
        raise ValueError("Resuelva los conflictos de origen o la referencia relativa antes de reutilizar")
    if not signature or item.precision == "DESCONOCIDA" or item.product not in {"PUNTO", "AREA_TRAMO"}:
        raise ValueError("Reutilizar requiere dirección, UBIGEO y precisión geográfica confirmados")
    geometry = item.geometry
    if item.product == "PUNTO" and valid_pair(item.latitude, item.longitude):
        geometry = mapping(Point(item.longitude, item.latitude))
    if not usable_geometry(geometry, item.product):
        raise ValueError("Reutilizar requiere una geometría válida y una precisión explícita")
    provenance = (source_candidate or {}).get("source_provenance") or [
        {
            "source": (source_candidate or {}).get("source") or "REVISION_HUMANA",
            "version": (source_candidate or {}).get("version") or str(item.revision),
            "feature_id": (source_candidate or {}).get("id"),
            "evidence": (source_candidate or {}).get("evidence", []),
        }
    ]
    entry = AddressMemory(
        signature=signature,
        location_id=item.id,
        source_revision=item.revision,
        created_by=user.id,
        payload={
            "geometry": geometry,
            "latitude": item.latitude,
            "longitude": item.longitude,
            "product": item.product,
            "precision": item.precision,
            "ubigeo": item.ubigeo,
            "source_provenance": provenance,
        },
    )
    db.add(entry)
    db.flush()
    item.normalized = {**item.normalized, "learned_reference_id": entry.id}
    return entry.id


def memory_constraints(normalized):
    unsafe = (DECISION_WARNINGS - {"MANZANA_LOTE_REQUIERE_REFERENCIA"}) | {
        "CRS_CONFLICTIVO",
        "FILA_ORIGEN_CON_INCIDENCIA",
    }
    return set(normalized.get("warnings") or []) & unsafe


def resolve_memory(db, normalized, resolved, cutoff):
    signature = address_signature(normalized)
    if not signature:
        return resolved
    rows = list(
        db.scalars(
            select(AddressMemory)
            .join(Location, Location.id == AddressMemory.location_id)
            .where(
                AddressMemory.signature == signature,
                AddressMemory.active.is_(True),
                AddressMemory.created_at <= cutoff,
                Location.revision == AddressMemory.source_revision,
                Location.resolution == "ACEPTADO_MANUAL",
            )
            .order_by(AddressMemory.id)
            .limit(101)
        )
    )
    if not rows:
        return resolved
    candidates = []
    for entry in rows[:100]:
        payload = entry.payload
        if not usable_geometry(payload.get("geometry"), payload.get("product")):
            continue
        candidates.append(
            {
                **payload,
                "id": f"memory:{entry.id}",
                "label": "Dirección validada previamente",
                "method": "DIRECCION_VALIDADA",
                "score": None,
                "score_type": "VALIDACION_HUMANA_PREVIA",
                "source": "CATALOGO_DIRECCIONES_VALIDADAS",
                "version": str(entry.source_revision),
                "evidence": [
                    "MEMORIA_DIRECCION_VALIDADA",
                    f"MEMORIA:{entry.id}",
                    f"REVISION_ORIGEN:{entry.source_revision}",
                    *[
                        f"PROCEDENCIA_ORIGEN:{source.get('source')}; VERSION:{source.get('version')}"
                        for source in payload.get("source_provenance", [])
                    ],
                ],
            }
        )
    if not candidates:
        return resolved
    unsafe = memory_constraints(normalized)
    chosen = candidates[0]
    conflict = (
        bool(normalized.get("reference_truncated"))
        or len(rows) > 100
        or any(
            candidate["precision"] != chosen["precision"]
            or candidate["product"] != chosen["product"]
            or not shape(candidate["geometry"]).equals(shape(chosen["geometry"]))
            for candidate in candidates[1:]
        )
    )
    # Compare independently validated evidence at its own precision. A road's
    # centreline is not a building entrance and cannot require exact point overlap.
    evidence_items = []
    if key(normalized.get("crs")) == "EPSG:4326":
        evidence_items.extend(
            c for c in resolved.get("candidates", []) if c.get("method") in {"COORD_ORIGINAL", "COORD_TEXTO"}
        )
    if resolved.get("resolution") == "ACEPTADO_AUTOMATICO":
        evidence_items.append(resolved)
    cached = shape(chosen["geometry"])
    for candidate in evidence_items:
        geometry = candidate.get("geometry")
        if not geometry:
            continue
        current = shape(geometry)
        if "PUNTO_FUERA_UBIGEO" in candidate.get("evidence", []):
            conflict = True
        elif "LineString" in current.geom_type and "LineString" in cached.geom_type:
            conflict |= not current.equals(cached)
        elif (current.geom_type == "Point" and "LineString" in cached.geom_type) or (
            cached.geom_type == "Point" and "LineString" in current.geom_type
        ):
            pass  # A building entrance need not overlap its street's centreline.
        elif current.geom_type == "Point" and cached.geom_type == "Point":
            conflict |= not current.equals(cached)
        else:
            conflict |= not (current.covers(cached) or cached.covers(current))
    result = {**resolved, "candidates": [*resolved.get("candidates", []), *candidates]}
    result["attempts"] = [
        *resolved.get("attempts", []),
        {
            "method": "DIRECCION_VALIDADA",
            "status": "CANDIDATOS_ENCONTRADOS",
            "reason": "MEMORIA_CONFLICTIVA" if conflict or unsafe else "MEMORIA_DIRECCION_VALIDADA",
            "candidate_count": len(candidates),
        },
    ]
    if conflict or unsafe:
        result.update(
            resolution="REVISION_REQUERIDA",
            latitude=None,
            longitude=None,
            geometry=None,
            product="DIRECCION_SIN_PUNTO",
            evidence_band="REVISION",
            reason="MEMORIA_CONFLICTIVA_O_DATOS_CONTRADICTORIOS",
        )
        return result
    if (
        resolved.get("resolution") == "ACEPTADO_AUTOMATICO"
        and resolved.get("product") == "PUNTO"
        and chosen["product"] == "AREA_TRAMO"
    ):
        return result  # A compatible, newly verified point improves a cached area.
    result.update(
        {
            field: chosen[field]
            for field in ("latitude", "longitude", "geometry", "precision", "product", "method")
        }
    )
    result.update(resolution="ACEPTADO_AUTOMATICO", evidence_band="ALTA", reason="MEMORIA_DIRECCION_VALIDADA")
    return result
