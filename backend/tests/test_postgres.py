"""Optional PostGIS integration; requires a dedicated, empty test database."""

import os
import uuid

import pytest
from sqlalchemy import create_engine, text

from geopol.migrations import migrate


def test_postgis_migration_is_idempotent_and_coordinates_generate_geometry():
    database_url = os.environ.get("GEOPOL_TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("Set GEOPOL_TEST_DATABASE_URL to run the PostGIS integration test")
    schema = "test_geopol_" + uuid.uuid4().hex
    admin_engine = create_engine(database_url)
    engine = None
    try:
        with admin_engine.begin() as conn:
            if conn.scalar(text("SELECT to_regclass('public.users')")):
                pytest.fail("Use a dedicated test database without existing GeoPol tables")
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis WITH SCHEMA public"))
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm WITH SCHEMA public"))
            conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        engine = create_engine(database_url, connect_args={"options": f"-csearch_path={schema},public"})
        migrate(engine)
        migrate(engine)
        with engine.begin() as conn:
            assert conn.scalar(text("SELECT count(*) FROM schema_versions WHERE version=1")) == 1
            conn.execute(
                text("""
                INSERT INTO users (id, username, password_hash, role, active)
                VALUES ('test-user', 'synthetic-postgis', 'unusable-test-hash', 'admin', true)
            """)
            )
            conn.execute(
                text("""
                INSERT INTO uploads (id, filename, size, "offset", status, profile, created_by, created_at)
                VALUES ('test-upload', 'synthetic.csv', 1, 1, 'COMPLETED', '{}', 'test-user', 0)
            """)
            )
            conn.execute(
                text("""
                INSERT INTO runs (id, upload_id, name, status, rules_version, config, created_by, created_at,
                    source_rows, location_units, processed_units, issue_rows, ingested, cancel_requested)
                VALUES ('test-run', 'test-upload', 'Synthetic PostGIS', 'COMPLETED', 'test', '{}', 'test-user', 0,
                    1, 1, 1, 0, true, false)
            """)
            )
            conn.execute(
                text("""
                INSERT INTO locations (id, run_id, unit_key, location_original, location_normalized, normalized,
                    source_row_count, resolution, precision, evidence_band, product, latitude, longitude,
                    reason, candidates, attempts, revision, manual)
                VALUES ('test-location', 'test-run', 'synthetic-unit', 'FICTICIA', 'FICTICIA', '{}',
                    1, 'ACEPTADO_MANUAL', 'PUERTA', 'REVISION', 'PUNTO', -12.04, -77.03,
                    'Synthetic test', '[]', '[]', 1, true)
            """)
            )
            point = conn.execute(
                text("SELECT ST_X(geom), ST_Y(geom), ST_SRID(geom) FROM locations WHERE id='test-location'")
            ).one()
            assert tuple(point) == (-77.03, -12.04, 4326)
            conn.execute(text("UPDATE locations SET latitude=NULL, longitude=NULL WHERE id='test-location'"))
            assert conn.scalar(text("SELECT geom IS NULL FROM locations WHERE id='test-location'")) is True
            indexes = conn.scalars(
                text("SELECT indexdef FROM pg_indexes WHERE schemaname=:schema"), {"schema": schema}
            ).all()
            assert sum("USING gist" in definition for definition in indexes) >= 2
    finally:
        if engine is not None:
            engine.dispose()
        with admin_engine.begin() as conn:
            conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        admin_engine.dispose()
