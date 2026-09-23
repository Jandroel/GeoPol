"""Cola SQL con arrendamiento, checkpoints transaccionales e ingesta acotada."""

import argparse
import csv
import hashlib
import json
import logging
import os
import signal
import socket
import time

from sqlalchemy import and_, func, insert, or_, select, update

from .catalogs import search_key
from .address_memory import resolve_memory
from .reference_search import ReferenceSearch
from .config import settings
from .domain.coordinate_context import apply_coordinate_declaration
from .db import SessionLocal
from .domain import RULES_VERSION
from .domain.ingestion import iter_records
from .domain.matching import resolve_location
from .domain.quality import resolve_quality_stage
from .quality_workflow import QUALITY_FIELDS, stage_scope
from .domain.normalization import normalize_record
from .excel_export import ExcelExportError, write_xlsx
from .models import (
    Catalog,
    Export,
    ExportItem,
    Heartbeat,
    Job,
    Location,
    Run,
    SourceRow,
    Upload,
    uid,
)
from .serialization import add_revision, audit, export_format, iso
from .review_workflow import classify_review
from .storage import checksum, storage_file

logger = logging.getLogger("geopol.worker")
WORKER_ID = f"{socket.gethostname()}:{os.getpid()}"


class LeaseLost(Exception):
    pass


class Cancelled(Exception):
    pass


def heartbeat(db, job_id=None):
    item = db.get(Heartbeat, WORKER_ID)
    if item is None:
        db.add(Heartbeat(id=WORKER_ID, seen_at=time.time(), job_id=job_id))
    else:
        item.seen_at, item.job_id = time.time(), job_id


def renew(db, job_id, token):
    now = time.time()
    changed = db.execute(
        update(Job)
        .where(Job.id == job_id, Job.lease_token == token, Job.status == "RUNNING", Job.lease_until > now)
        .values(lease_until=now + settings.lease_seconds)
    ).rowcount
    if changed != 1:
        raise LeaseLost()
    heartbeat(db, job_id)


def claim_job():
    with SessionLocal() as db:
        now = time.time()
        eligible = or_(Job.status == "QUEUED", and_(Job.status == "RUNNING", Job.lease_until < now))
        query = select(Job).where(eligible).order_by(Job.created_at).limit(1)
        if db.bind.dialect.name == "postgresql":
            query = query.with_for_update(skip_locked=True)
        job = db.scalar(query)
        if job is None:
            heartbeat(db)
            db.commit()
            return None
        token = uid()
        changed = db.execute(
            update(Job)
            .where(Job.id == job.id, eligible)
            .values(
                status="RUNNING",
                lease_token=token,
                lease_until=now + settings.lease_seconds,
                attempts=Job.attempts + 1,
            )
        ).rowcount
        if changed != 1:
            db.rollback()
            return None
        heartbeat(db, job.id)
        db.commit()
        return job.id, token, job.kind, job.target_id


def unit_key(normalized, ordinal):
    # Location evidence, not person/modalidad columns, defines a compatible unit.
    keys = (
        "complaint_id",
        "location_normalized",
        "ubigeo",
        "district",
        "street_type",
        "street_name",
        "door_number",
        "block_number",
        "manzana_code",
        "lot_number",
        "cross_street",
        "site_name",
        "urban_core",
        "latitude",
        "longitude",
        "coordinate_origin",
        "decision_constraints",
        "crs",
        "source_crs",
    )
    canonical = {k: normalized.get(k) for k in keys}
    for extra in ("center_name", "center_code", "jurisdiction_name", "jurisdiction_code"):
        if normalized.get(extra):
            canonical[extra] = normalized[extra]
    if not canonical["complaint_id"]:
        canonical["source_ordinal"] = ordinal
    return hashlib.sha256(json.dumps(canonical, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def ingest_batch(run_id, batch, job_id, token):
    with SessionLocal() as db:
        renew(db, job_id, token)
        run = db.get(Run, run_id)
        if run.cancel_requested:
            raise Cancelled()
        entries = []
        for ordinal, raw, issue in batch:
            normalized = apply_coordinate_declaration(
                normalize_record(raw, run.config.get("mapping")), run.config
            )
            key = unit_key(normalized, ordinal)
            entries.append((ordinal, raw, issue, normalized, key))
        existing = {
            x.unit_key: x
            for x in db.scalars(
                select(Location).where(
                    Location.run_id == run_id, Location.unit_key.in_([e[4] for e in entries])
                )
            )
        }
        source_rows = []
        for ordinal, raw, issue, normalized, key in entries:
            item = existing.get(key)
            if item is None:
                item = Location(
                    id=uid(),
                    run_id=run_id,
                    unit_key=key,
                    complaint_id=normalized.get("complaint_id"),
                    location_original=normalized.get("location_original") or "",
                    location_normalized=normalized.get("location_normalized") or "",
                    ubigeo=normalized.get("ubigeo"),
                    normalized=normalized,
                    source_row_count=0,
                )
                db.add(item)
                existing[key] = item
                run.location_units += 1
            item.source_row_count += 1
            if issue:
                copy = dict(item.normalized)
                copy["warnings"] = list(set(copy.get("warnings", []) + ["FILA_ORIGEN_CON_INCIDENCIA"]))
                item.normalized = copy
            source_rows.append(
                dict(run_id=run_id, ordinal=ordinal, raw=raw, issue=issue, location_id=item.id)
            )
            run.source_rows = ordinal
            run.issue_rows += int(bool(issue))
        db.flush()
        db.execute(insert(SourceRow), source_rows)
        renew(db, job_id, token)
        db.commit()


def supersede_parent(db, run):
    """Publish a successful reprocessing run without hiding a newer successful child."""
    if not run.parent_run_id or run.status not in {"COMPLETED", "COMPLETED_WITH_ISSUES"}:
        return
    # The parent lock serializes concurrent PostgreSQL children. SQLite's lease
    # renewal already holds its write lock for this completion transaction.
    parent = db.scalar(select(Run).where(Run.id == run.parent_run_id).with_for_update())
    if parent is None:
        return
    current = db.get(Run, parent.superseded_by) if parent.superseded_by else None
    if current is None or (run.created_at, run.id) > (current.created_at, current.id):
        parent.superseded_by = run.id
        if current is not None:
            current.superseded_by = run.id
    elif current.id != run.id:
        # A late older sibling remains history, never a second current queue.
        run.superseded_by = current.id


def process_run(run_id, job_id, token):
    with SessionLocal() as db:
        renew(db, job_id, token)
        run = db.get(Run, run_id)
        upload = db.get(Upload, run.upload_id)
        if run.rules_version != RULES_VERSION:
            raise ValueError("La versión de reglas del lote no está disponible en este worker")
        if run.cancel_requested:
            raise Cancelled()
        run.started_at = run.started_at or time.time()
        run.status = "PROCESSING" if run.ingested else "INGESTING"
        config, filename, upload_id, skip, ingested = (
            run.config,
            upload.filename,
            upload.id,
            run.source_rows,
            run.ingested,
        )
        db.commit()
    if not ingested:
        batch = []
        batch_bytes = 0
        last_touch = time.monotonic()
        for ordinal, raw, issue in iter_records(
            storage_file("uploads", upload_id),
            filename,
            sheet=config.get("sheet"),
            delimiter=config.get("delimiter", ","),
            encoding=config.get("encoding", "utf-8-sig"),
        ):
            if ordinal <= skip:
                if time.monotonic() - last_touch > 15:
                    with SessionLocal() as db:
                        renew(db, job_id, token)
                        if db.get(Run, run_id).cancel_requested:
                            raise Cancelled()
                        db.commit()
                    last_touch = time.monotonic()
                continue
            record_bytes = len(json.dumps(raw, ensure_ascii=False).encode("utf-8"))
            if batch and batch_bytes + record_bytes > 16 * 1024 * 1024:
                ingest_batch(run_id, batch, job_id, token)
                batch, batch_bytes = [], 0
            batch.append((ordinal, raw, issue))
            batch_bytes += record_bytes
            if len(batch) >= settings.batch_size:
                ingest_batch(run_id, batch, job_id, token)
                batch, batch_bytes = [], 0
        if batch:
            ingest_batch(run_id, batch, job_id, token)
        with SessionLocal() as db:
            renew(db, job_id, token)
            run = db.get(Run, run_id)
            run.ingested, run.status = True, "PROCESSING"
            db.commit()

    references = ReferenceSearch(SessionLocal)

    while True:
        with SessionLocal() as db:
            renew(db, job_id, token)
            run = db.get(Run, run_id)
            if run.cancel_requested:
                raise Cancelled()
            items, normalized_bytes = [], 0
            quality_mode = run.config.get("workflow") == "quality_v1"
            quality_stage = run.config.get("quality_target_stage", "door")
            pending = (
                stage_scope(run_id, quality_stage)
                if quality_mode
                else select(Location).where(Location.run_id == run_id, Location.resolution == "PENDIENTE")
            )
            selected = db.scalars(
                pending.order_by(Location.id).limit(settings.batch_size).execution_options(yield_per=1)
            )
            try:
                for item in selected:
                    items.append(item)
                    normalized_bytes += len(json.dumps(item.normalized, ensure_ascii=False).encode("utf-8"))
                    if normalized_bytes >= 16 * 1024 * 1024:
                        break
            finally:
                selected.close()
            if not items:
                run.status = "COMPLETED_WITH_ISSUES" if run.issue_rows else "COMPLETED"
                run.finished_at = time.time()
                supersede_parent(db, run)
                audit(
                    db,
                    "worker",
                    "run.completed",
                    run_id,
                    {"source_rows": run.source_rows, "location_units": run.location_units},
                )
                db.commit()
                return
            catalog = db.get(Catalog, run.reference_id) if run.reference_id else None
            complaint_ids = [x.complaint_id for x in items if x.complaint_id]
            conflicts = set(
                db.scalars(
                    select(Location.complaint_id)
                    .where(Location.run_id == run_id, Location.complaint_id.in_(complaint_ids))
                    .group_by(Location.complaint_id)
                    .having(func.count() > 1)
                )
            )
            result_bytes, batch_started = 0, time.monotonic()
            for item in items:
                # Resumed, already-ingested legacy work must not revive a CRS
                # assigned by an old browser without a documented declaration.
                normalized = apply_coordinate_declaration(item.normalized, run.config)
                names = tuple(search_key(n) for n in normalized.get("search_names", []) if n)
                features, truncated = references.lookup(
                    run.reference_id,
                    item.ubigeo,
                    names,
                    normalized.get("manzana_code"),
                    ("jurisdiction",)
                    if quality_mode and quality_stage == "jurisdiction"
                    else ("site", "nucleus")
                    if quality_mode and quality_stage == "nucleus" and normalized.get("center_code")
                    else (),
                )
                normalized["reference_truncated"] = truncated
                normalized["available_reference_kinds"] = catalog.kinds if catalog else []
                if quality_mode:
                    resolved = resolve_quality_stage(
                        normalized, features, reference_available=bool(catalog), stage=quality_stage
                    )
                else:
                    resolved = resolve_location(normalized, features, reference_available=bool(catalog))
                    resolved = resolve_memory(db, normalized, resolved, run.created_at)
                if item.complaint_id in conflicts or {"FILA_ORIGEN_CON_INCIDENCIA", "CRS_CONFLICTIVO"} & set(
                    normalized.get("warnings", [])
                ):
                    resolved.update(
                        resolution="REVISION_REQUERIDA",
                        latitude=None,
                        longitude=None,
                        geometry=None,
                        product="DIRECCION_SIN_PUNTO" if item.location_normalized else "NINGUNO",
                        evidence_band="REVISION",
                        reason="Ubicaciones contradictorias, CRS en conflicto o incidencia en la fila de origen; requiere conciliación",
                    )
                    if quality_mode:
                        resolved.update(
                            quality_status="review",
                            quality_code=3 if quality_stage == "door" else None,
                            quality_reason=resolved["reason"],
                        )
                for key in (
                    "resolution",
                    "method",
                    "precision",
                    "evidence_band",
                    "product",
                    "latitude",
                    "longitude",
                    "geometry",
                    "reason",
                    "candidates",
                    "attempts",
                ) + (QUALITY_FIELDS if quality_mode else ()):
                    if key in resolved:
                        setattr(item, key, resolved[key])
                initial = item.revision == 0
                item.normalized, item.revision = normalized, item.revision + 1
                if quality_mode:
                    item.manual, item.review_owner, item.review_expires_at = False, None, None
                item.review_status, item.review_bucket = classify_review(
                    item.resolution, item.manual, item.candidates, item.reason
                )
                add_revision(db, item, "worker", "automatic_resolution")
                if initial:
                    run.processed_units += 1
                result_bytes += len(json.dumps(resolved, ensure_ascii=False).encode("utf-8"))
                if result_bytes >= 16 * 1024 * 1024 or time.monotonic() - batch_started > 15:
                    break
            renew(db, job_id, token)
            db.commit()


EXPORT_COLUMNS_V1 = (
    "id",
    "complaint_id",
    "location_original",
    "location_normalized",
    "ubigeo",
    "resolution",
    "method",
    "precision",
    "evidence_band",
    "product",
    "latitude",
    "longitude",
    "reason",
    "revision",
    "source_row_count",
)
EXPORT_COLUMNS_V2 = EXPORT_COLUMNS_V1 + ("review_status", "review_bucket")
EXPORT_COLUMNS = EXPORT_COLUMNS_V2 + ("geometry",)
EXPORT_COLUMNS_V4 = EXPORT_COLUMNS + QUALITY_FIELDS
EXPORT_COLUMNS_V5 = EXPORT_COLUMNS + (
    "quality_flag",
    "review_state",
    "quality_flag_reason",
    "quality_stage",
    "quality_reason",
    "quality_policy_version",
)


def safe_cell(value, safe):
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False)
    if safe and isinstance(value, str) and value.lstrip(" \t\r\n\ufeff").startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def process_export(export_id, job_id, token):
    with SessionLocal() as db:
        renew(db, job_id, token)
        export = db.get(Export, export_id)
        export.status = "PROCESSING"
        run = db.get(Run, export.run_id)
        upload = db.get(Upload, run.upload_id)
        profile, safe, run_id = export.profile, export.safe_spreadsheet, run.id
        file_format = export_format(export)
        manifest = dict(export.manifest)
        source_columns = list(
            manifest.get(
                "source_columns", run.config.get("source_columns", upload.profile.get("columns", []))
            )
        )
        extra_column = "__extra_columns__"
        while extra_column in source_columns:
            extra_column += "_"
        source_columns.append(extra_column)
        metadata = {
            "profile": profile,
            "source_columns": source_columns,
            "run_name": manifest.get("run_name", run.name),
            "filename": manifest.get("filename", upload.filename),
            "expected_rows": manifest["expected_rows"],
            "snapshot_at": manifest.get("snapshot_at"),
            "rules_version": manifest.get("rules_version"),
            "reference": manifest.get("reference"),
        }
        db.commit()
    path = storage_file("exports", export_id, f".{token}.{file_format}.part")
    row_count = 0
    schema = manifest.get("schema_version", 1)
    columns = (
        EXPORT_COLUMNS_V5
        if schema >= 5
        else EXPORT_COLUMNS_V4
        if schema >= 4
        else EXPORT_COLUMNS
        if schema >= 3
        else EXPORT_COLUMNS_V2
        if schema == 2
        else EXPORT_COLUMNS_V1
    )

    def records():
        nonlocal row_count
        cursor = 0 if profile == "source_rows" else ""
        while True:
            with SessionLocal() as db:
                renew(db, job_id, token)
                batch_count = 0
                if profile == "source_rows":
                    rows = db.execute(
                        select(SourceRow, ExportItem.snapshot)
                        .outerjoin(
                            ExportItem,
                            and_(
                                SourceRow.location_id == ExportItem.location_id,
                                ExportItem.export_id == export_id,
                            ),
                        )
                        .where(
                            SourceRow.run_id == run_id,
                            SourceRow.ordinal > cursor,
                            ExportItem.location_id.is_not(None) if manifest.get("quality_filter") else True,
                        )
                        .order_by(SourceRow.ordinal)
                        .limit(settings.batch_size)
                    ).yield_per(1)
                    for source_row, snapshot in rows:
                        cursor = source_row.ordinal
                        batch_count += 1
                        row_count += 1
                        yield {
                            "ordinal": source_row.ordinal,
                            "issue": source_row.issue,
                            "raw": source_row.raw,
                            "snapshot": snapshot or {},
                        }
                    rows.close()
                else:
                    rows = db.scalars(
                        select(ExportItem)
                        .where(ExportItem.export_id == export_id, ExportItem.location_id > cursor)
                        .order_by(ExportItem.location_id)
                        .limit(settings.batch_size)
                    ).yield_per(1)
                    for item in rows:
                        cursor = item.location_id
                        batch_count += 1
                        row_count += 1
                        yield {"ordinal": None, "issue": None, "raw": None, "snapshot": item.snapshot}
                    rows.close()
                db.commit()
                if not batch_count:
                    break

    record_stream = records()
    try:
        if file_format == "xlsx":
            workbook = write_xlsx(path, record_stream, columns=columns, metadata=metadata)
            if workbook["row_count"] != row_count:
                raise ValueError("El libro no coincide con las filas de la instantánea")
            manifest.update(workbook_schema_version=1, workbook=workbook, safe_spreadsheet=True)
            with path.open("r+b") as stream:
                os.fsync(stream.fileno())
        else:
            with path.open("w", encoding="utf-8-sig", newline="") as stream:
                writer = csv.writer(stream)
                headers = [f"GEOPOL_{x}" for x in columns]
                if profile == "source_rows":
                    headers = ["SOURCE_ORDINAL", "SOURCE_ISSUE"] + source_columns + headers
                writer.writerow([safe_cell(header, safe) for header in headers])
                for record in record_stream:
                    values = [record["snapshot"].get(key) for key in columns]
                    if profile == "source_rows":
                        values = (
                            [record["ordinal"], record["issue"]]
                            + [record["raw"].get(key) for key in source_columns]
                            + values
                        )
                    writer.writerow([safe_cell(value, safe) for value in values])
                stream.flush()
                os.fsync(stream.fileno())
            manifest.update(encoding="utf-8-sig", safe_spreadsheet=safe)
        digest = checksum(path)
        with SessionLocal() as db:
            renew(db, job_id, token)
            export = db.get(Export, export_id)
            if row_count != manifest["expected_rows"]:
                raise ValueError("La exportación no coincide con la cardinalidad de la instantánea")
            # Lease guards publication; an expired worker cannot publish another worker's file.
            path.replace(storage_file("exports", export_id, f".{file_format}"))
            export.status, export.row_count, export.sha256 = "COMPLETED", row_count, digest
            manifest.update(row_count=row_count, sha256=digest, completed_at=iso(time.time()))
            export.manifest = manifest
            audit(
                db, "worker", "export.completed", export_id, {"row_count": row_count, "format": file_format}
            )
            db.commit()
    finally:
        record_stream.close()
        if file_format == "xlsx":
            # Only this lease's unpublished XLSX is removed after errors or stale ownership.
            path.unlink(missing_ok=True)


def work_once():
    claim = claim_job()
    if claim is None:
        return False
    job_id, token, kind, target_id = claim
    status, error = "COMPLETED", None
    try:
        if kind == "RUN":
            process_run(target_id, job_id, token)
        elif kind == "EXPORT":
            process_export(target_id, job_id, token)
        else:
            raise ValueError("Tipo de trabajo desconocido")
    except LeaseLost:
        logger.warning("Arrendamiento perdido para trabajo %s", job_id)
        return True
    except Cancelled:
        status = "CANCELLED"
    except ExcelExportError as exc:
        # This dedicated exception contains only fixed, public-safe guidance.
        status, error = "FAILED", str(exc)
        logger.error("Trabajo %s falló: %s", job_id, type(exc).__name__)
    except Exception as exc:
        status = "FAILED"
        # Exception payloads may include raw fields; persist only category, never source data.
        error = f"Error de procesamiento ({type(exc).__name__}). Revise formato, mapeo y límites; reintente desde el checkpoint."
        logger.error("Trabajo %s falló: %s", job_id, type(exc).__name__)
    with SessionLocal() as db:
        try:
            renew(db, job_id, token)
        except LeaseLost:
            return True
        job = db.get(Job, job_id)
        job.status, job.error, job.lease_until = status, error, None
        if status != "COMPLETED":
            target = db.get(Run if kind == "RUN" else Export, target_id)
            target.status, target.error = status, error
            if kind == "RUN":
                target.finished_at = time.time()
            audit(db, "worker", f"job.{status.lower()}", target_id, {"kind": kind, "error": error})
        heartbeat(db)
        db.commit()
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="Procesar como máximo un trabajo")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    stopped = False

    def stop(*_):
        nonlocal stopped
        stopped = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    logger.info("Worker iniciado: %s", WORKER_ID)
    while not stopped:
        worked = work_once()
        if args.once:
            break
        if not worked:
            time.sleep(2)


if __name__ == "__main__":
    main()
