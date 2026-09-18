"""Migraciones numeradas. Cada versión se registra en la misma transacción DDL."""

from sqlalchemy import select, text

from .db import Base
from .models import SchemaVersion


def migrate(engine):
    with engine.begin() as conn:
        if engine.dialect.name == "postgresql":
            conn.execute(text("SELECT pg_advisory_xact_lock(791043211)"))
        Base.metadata.create_all(conn)
        if conn.scalar(select(SchemaVersion.version).where(SchemaVersion.version == 1)):
            return
        if engine.dialect.name == "postgresql":
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
                text(
                    "CREATE INDEX IF NOT EXISTS ix_features_trgm ON features USING gin(search_key gin_trgm_ops)"
                )
            )
        conn.execute(SchemaVersion.__table__.insert().values(version=1))
