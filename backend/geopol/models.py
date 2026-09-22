"""Persistencia explícita: fuentes, unidades, revisiones y trabajos separados."""

import time
import uuid

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base
from .domain import RULES_VERSION


def uid():
    return str(uuid.uuid4())


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    username: Mapped[str] = mapped_column(String(100), unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(String(20))
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class LoginSession(Base):
    __tablename__ = "login_sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    expires_at: Mapped[float] = mapped_column(Float)


class Upload(Base):
    __tablename__ = "uploads"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    filename: Mapped[str] = mapped_column(String(255))
    size: Mapped[int] = mapped_column(BigInteger)
    offset: Mapped[int] = mapped_column(BigInteger, default=0)
    status: Mapped[str] = mapped_column(String(24), default="UPLOADING")
    sha256: Mapped[str | None] = mapped_column(String(64))
    profile: Mapped[dict] = mapped_column(JSON, default=dict)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[float] = mapped_column(Float, default=time.time)


class Catalog(Base):
    __tablename__ = "catalogs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String(200))
    version: Mapped[str] = mapped_column(String(100))
    source: Mapped[str] = mapped_column(String(500))
    sha256: Mapped[str] = mapped_column(String(64))
    feature_count: Mapped[int] = mapped_column(Integer, default=0)
    kinds: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[float] = mapped_column(Float, default=time.time)


class ProcessingDefaults(Base):
    """Workspace defaults; each run still records its own catalog version."""

    __tablename__ = "processing_defaults"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    reference_id: Mapped[str | None] = mapped_column(ForeignKey("catalogs.id"))
    updated_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    updated_at: Mapped[float | None] = mapped_column(Float)


class Feature(Base):
    __tablename__ = "features"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    catalog_id: Mapped[str] = mapped_column(ForeignKey("catalogs.id"), index=True)
    external_id: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(24))
    ubigeo: Mapped[str] = mapped_column(String(6), index=True)
    search_key: Mapped[str] = mapped_column(String(500))
    payload: Mapped[dict] = mapped_column(JSON)
    __table_args__ = (
        UniqueConstraint("catalog_id", "external_id"),
        Index("ix_feature_lookup", "catalog_id", "ubigeo", "search_key"),
    )


class Run(Base):
    __tablename__ = "runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    upload_id: Mapped[str] = mapped_column(ForeignKey("uploads.id"))
    name: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(32), default="QUEUED", index=True)
    reference_id: Mapped[str | None] = mapped_column(ForeignKey("catalogs.id"))
    parent_run_id: Mapped[str | None] = mapped_column(ForeignKey("runs.id"))
    superseded_by: Mapped[str | None] = mapped_column(ForeignKey("runs.id"))
    rules_version: Mapped[str] = mapped_column(String(32), default=RULES_VERSION)
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[float] = mapped_column(Float, default=time.time)
    started_at: Mapped[float | None] = mapped_column(Float)
    finished_at: Mapped[float | None] = mapped_column(Float)
    source_rows: Mapped[int] = mapped_column(Integer, default=0)
    location_units: Mapped[int] = mapped_column(Integer, default=0)
    processed_units: Mapped[int] = mapped_column(Integer, default=0)
    issue_rows: Mapped[int] = mapped_column(Integer, default=0)
    ingested: Mapped[bool] = mapped_column(Boolean, default=False)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    error: Mapped[str | None] = mapped_column(Text)


class Location(Base):
    __tablename__ = "locations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), index=True)
    unit_key: Mapped[str] = mapped_column(String(64))
    complaint_id: Mapped[str | None] = mapped_column(String(200), index=True)
    location_original: Mapped[str] = mapped_column(Text, default="")
    location_normalized: Mapped[str] = mapped_column(Text, default="")
    ubigeo: Mapped[str | None] = mapped_column(String(6))
    normalized: Mapped[dict] = mapped_column(JSON, default=dict)
    source_row_count: Mapped[int] = mapped_column(Integer, default=0)
    resolution: Mapped[str] = mapped_column(String(40), default="PENDIENTE", index=True)
    method: Mapped[str | None] = mapped_column(String(60))
    precision: Mapped[str] = mapped_column(String(40), default="DESCONOCIDA")
    evidence_band: Mapped[str] = mapped_column(String(20), default="SIN_EVIDENCIA")
    product: Mapped[str] = mapped_column(String(40), default="NINGUNO")
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    geometry: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    reason: Mapped[str] = mapped_column(Text, default="Pendiente de procesamiento")
    candidates: Mapped[list] = mapped_column(JSON, default=list)
    attempts: Mapped[list] = mapped_column(JSON, default=list)
    revision: Mapped[int] = mapped_column(Integer, default=0)
    manual: Mapped[bool] = mapped_column(Boolean, default=False)
    review_status: Mapped[str] = mapped_column(String(12), default="OPEN", server_default="OPEN")
    review_bucket: Mapped[str] = mapped_column(String(24), default="none", server_default="none")
    review_owner: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    review_expires_at: Mapped[float | None] = mapped_column(Float)
    __table_args__ = (
        UniqueConstraint("run_id", "unit_key"),
        Index("ix_location_queue", "run_id", "resolution", "id"),
        Index("ix_location_complaint", "run_id", "complaint_id"),
        Index("ix_location_review_queue", "run_id", "review_status", "review_bucket", "id"),
    )


class AddressMemory(Base):
    __tablename__ = "address_memory"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    signature: Mapped[str] = mapped_column(String(64), index=True)
    location_id: Mapped[str] = mapped_column(ForeignKey("locations.id"), index=True)
    source_revision: Mapped[int] = mapped_column(Integer)
    payload: Mapped[dict] = mapped_column(JSON)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[float] = mapped_column(Float, default=time.time)


class SourceRow(Base):
    __tablename__ = "source_rows"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), index=True)
    ordinal: Mapped[int] = mapped_column(Integer)
    location_id: Mapped[str | None] = mapped_column(ForeignKey("locations.id"), index=True)
    raw: Mapped[dict] = mapped_column(JSON)
    issue: Mapped[str | None] = mapped_column(Text)
    __table_args__ = (UniqueConstraint("run_id", "ordinal"),)


class Revision(Base):
    __tablename__ = "revisions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    location_id: Mapped[str] = mapped_column(ForeignKey("locations.id"), index=True)
    revision: Mapped[int] = mapped_column(Integer)
    actor: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[float] = mapped_column(Float, default=time.time)
    action: Mapped[str] = mapped_column(String(40))
    reason: Mapped[str] = mapped_column(Text)
    snapshot: Mapped[dict] = mapped_column(JSON)
    __table_args__ = (UniqueConstraint("location_id", "revision"),)


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    kind: Mapped[str] = mapped_column(String(20))
    target_id: Mapped[str] = mapped_column(String(36), index=True)
    status: Mapped[str] = mapped_column(String(20), default="QUEUED", index=True)
    lease_token: Mapped[str | None] = mapped_column(String(36))
    lease_until: Mapped[float | None] = mapped_column(Float)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[float] = mapped_column(Float, default=time.time)
    error: Mapped[str | None] = mapped_column(Text)


class Export(Base):
    __tablename__ = "exports"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), index=True)
    profile: Mapped[str] = mapped_column(String(20))
    safe_spreadsheet: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[str] = mapped_column(String(20), default="QUEUED")
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[float] = mapped_column(Float, default=time.time)
    row_count: Mapped[int] = mapped_column(Integer, default=0)
    sha256: Mapped[str | None] = mapped_column(String(64))
    manifest: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(Text)


class ExportItem(Base):
    __tablename__ = "export_items"
    export_id: Mapped[str] = mapped_column(ForeignKey("exports.id"), primary_key=True)
    location_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    snapshot: Mapped[dict] = mapped_column(JSON)


class Audit(Base):
    __tablename__ = "audit"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    actor: Mapped[str] = mapped_column(String(100))
    action: Mapped[str] = mapped_column(String(60))
    entity_id: Mapped[str] = mapped_column(String(36))
    created_at: Mapped[float] = mapped_column(Float, default=time.time, index=True)
    detail: Mapped[dict] = mapped_column(JSON, default=dict)


class Heartbeat(Base):
    __tablename__ = "heartbeats"
    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    seen_at: Mapped[float] = mapped_column(Float)
    job_id: Mapped[str | None] = mapped_column(String(36))


class SchemaVersion(Base):
    __tablename__ = "schema_versions"
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    applied_at: Mapped[float] = mapped_column(Float, default=time.time)
