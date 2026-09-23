"""Migraciones numeradas. Cada versión se registra en la misma transacción DDL."""

from sqlalchemy import bindparam, inspect, select, text, update

from .db import Base
from .models import Location, ProcessingDefaults, Revision, SchemaVersion
from .review_workflow import classify_review

BACKFILL_BATCH_SIZE = 500
SCHEMA_VERSION = 6


def migrate(engine):
    with engine.begin() as conn:
        if engine.dialect.name == "postgresql":
            conn.execute(text("SELECT pg_advisory_xact_lock(791043211)"))
        elif engine.dialect.name == "sqlite":
            # sqlite3 otherwise defers BEGIN until DML; keep additive DDL and the
            # schema marker atomic and serialize local migration callers.
            conn.exec_driver_sql("BEGIN IMMEDIATE")
        Base.metadata.create_all(conn)
        versions = set(conn.scalars(select(SchemaVersion.version)))
        if 1 not in versions:
            _version_one(conn)
            conn.execute(SchemaVersion.__table__.insert().values(version=1))
        if 2 not in versions:
            _version_two(conn)
            conn.execute(SchemaVersion.__table__.insert().values(version=2))
        if 3 not in versions:
            _version_three(conn)
            conn.execute(SchemaVersion.__table__.insert().values(version=3))
        if 4 not in versions:
            _version_four(conn)
            conn.execute(SchemaVersion.__table__.insert().values(version=4))
        if 5 not in versions:
            _version_five(conn)
            conn.execute(SchemaVersion.__table__.insert().values(version=5))
        if 6 not in versions:
            _version_six(conn)
            conn.execute(SchemaVersion.__table__.insert().values(version=6))


def _version_six(conn):
    """Separate location-format flags from the review decision, without backfill."""
    existing = {column["name"] for column in inspect(conn).get_columns("locations")}
    for name, definition in {
        "quality_flag": "INTEGER",
        "quality_flag_reason": "TEXT",
        "review_state": "VARCHAR(24)",
    }.items():
        if name not in existing:
            conn.execute(text(f"ALTER TABLE locations ADD COLUMN {name} {definition}"))
    conn.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_location_quality_flag "
            "ON locations (run_id, quality_flag, review_state)"
        )
    )


def _version_five(conn):
    """Quality workflow is opt-in; historical decisions and snapshots remain intact."""
    additions = {
        "catalogs": {"config": "JSON NOT NULL DEFAULT '{}'"},
        "locations": {
            "quality_code": "INTEGER",
            "quality_stage": "VARCHAR(24)",
            "quality_status": "VARCHAR(24)",
            "quality_reason": "TEXT",
            "quality_policy_version": "VARCHAR(32)",
            "quality_history": "JSON NOT NULL DEFAULT '[]'",
        },
    }
    for table, columns in additions.items():
        existing = {column["name"] for column in inspect(conn).get_columns(table)}
        for name, definition in columns.items():
            if name not in existing:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {definition}"))
    conn.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_location_quality "
            "ON locations (run_id, quality_stage, quality_status, quality_code)"
        )
    )


def _version_four(conn):
    """Add a default catalog without changing any historical run configuration."""
    table = ProcessingDefaults.__table__
    table.create(conn, checkfirst=True)
    if conn.scalar(select(table.c.id).where(table.c.id == "global")) is None:
        conn.execute(table.insert().values(id="global"))


def _version_three(conn):
    """Preserve area/line results without rewriting historical point snapshots."""
    existing = {column["name"] for column in inspect(conn).get_columns("locations")}
    if "geometry" not in existing:
        conn.execute(text("ALTER TABLE locations ADD COLUMN geometry JSON"))


def _version_one(conn):
    if conn.dialect.name == "postgresql":
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
        conn.execute(
            text("""ALTER TABLE locations ADD COLUMN IF NOT EXISTS geom geometry(Point,4326)
            GENERATED ALWAYS AS (CASE WHEN latitude IS NOT NULL AND longitude IS NOT NULL
            THEN ST_SetSRID(ST_MakePoint(longitude, latitude),4326) END) STORED""")
        )
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_locations_geom ON locations USING gist(geom)"))
        conn.execute(
            text("""ALTER TABLE features ADD COLUMN IF NOT EXISTS geom geometry(Geometry,4326)
            GENERATED ALWAYS AS (CASE WHEN payload->>'geometry' IS NOT NULL
            AND payload->>'geometry' <> 'null' THEN ST_SetSRID(ST_GeomFromGeoJSON(payload->>'geometry'),4326)
            WHEN payload->>'latitude' IS NOT NULL AND payload->>'longitude' IS NOT NULL
            THEN ST_SetSRID(ST_MakePoint((payload->>'longitude')::float8,(payload->>'latitude')::float8),4326) END) STORED""")
        )
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_features_geom ON features USING gist(geom)"))
        conn.execute(
            text("CREATE INDEX IF NOT EXISTS ix_features_trgm ON features USING gin(search_key gin_trgm_ops)")
        )


def _version_two(conn):
    """Add queue state and lineage, retaining every v1 row and revision."""
    additions = {
        "locations": {
            "review_status": "VARCHAR(12) NOT NULL DEFAULT 'OPEN'",
            "review_bucket": "VARCHAR(24) NOT NULL DEFAULT 'none'",
        },
        "runs": {
            "parent_run_id": "VARCHAR(36) REFERENCES runs(id)",
            "superseded_by": "VARCHAR(36) REFERENCES runs(id)",
        },
    }
    for table, columns in additions.items():
        existing = {column["name"] for column in inspect(conn).get_columns(table)}
        for name, definition in columns.items():
            if name not in existing:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {definition}"))
    conn.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_location_review_queue "
            "ON locations (run_id, review_status, review_bucket, id)"
        )
    )
    locations, revisions = Location.__table__, Revision.__table__
    latest_action = (
        select(revisions.c.action)
        .where(revisions.c.location_id == locations.c.id)
        .order_by(revisions.c.revision.desc())
        .limit(1)
        .scalar_subquery()
    )
    statement = (
        update(locations)
        .where(locations.c.id == bindparam("location_identifier"))
        .values(review_status=bindparam("queue_status"), review_bucket=bindparam("queue_bucket"))
    )
    cursor = None
    while True:
        query = (
            select(
                locations.c.id,
                locations.c.resolution,
                locations.c.manual,
                locations.c.candidates,
                locations.c.reason,
                latest_action.label("latest_action"),
            )
            .order_by(locations.c.id)
            .limit(BACKFILL_BATCH_SIZE)
        )
        if cursor is not None:
            query = query.where(locations.c.id > cursor)
        rows = conn.execute(query).mappings().all()
        if not rows:
            break
        updates = []
        for row in rows:
            status, bucket = classify_review(
                row["resolution"], row["manual"], row["candidates"], row["reason"], row["latest_action"]
            )
            updates.append(dict(location_identifier=row["id"], queue_status=status, queue_bucket=bucket))
        conn.execute(statement, updates)
        cursor = rows[-1]["id"]
