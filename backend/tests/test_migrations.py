"""Incremental queue migration and successful-run lineage, using synthetic databases."""

import time

import pytest
from sqlalchemy import inspect, select, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.schema import CreateTable

from geopol import migrations, worker
from geopol.db import Base, make_engine
from geopol.domain import RULES_VERSION
from geopol.models import Job, Location, Revision, Run, SchemaVersion, SourceRow, Upload, User
from geopol.review_workflow import classify_review


ORIGINAL_WITHOUT_BOUNDARY = {
    "id": "coord_original:source",
    "method": "COORD_ORIGINAL",
    "evidence": ["PNP_ORIGINAL", "LIMITE_TERRITORIAL_NO_DISPONIBLE"],
}


@pytest.mark.parametrize(
    "resolution,manual,candidates,reason,action,expected",
    [
        ("ACEPTADO_AUTOMATICO", False, [], "", None, ("CLOSED", "none")),
        ("ACEPTADO_MANUAL", True, [], "", "manual_point", ("CLOSED", "none")),
        ("SIN_COINCIDENCIA", True, [], "", "unresolved", ("CLOSED", "none")),
        ("NO_EVALUABLE_REFERENCIA", True, [], "", None, ("CLOSED", "none")),
        ("ACEPTADO_MANUAL", True, [], "", "reopen", ("OPEN", "needs_data")),
        ("NO_EVALUABLE_REFERENCIA", False, [], "", None, ("OPEN", "needs_reference")),
        ("ERROR_TECNICO", False, [], "", None, ("OPEN", "technical")),
        ("REVISION_REQUERIDA", False, [], "BUSQUEDA_REFERENCIAL_TRUNCADA", None, ("OPEN", "technical")),
        (
            "REVISION_REQUERIDA",
            False,
            [{"method": "COORD_ORIGINAL", "evidence": ["CRS_NO_CONFIRMADO"]}],
            "",
            None,
            ("OPEN", "needs_reference"),
        ),
        ("INFORMACION_INSUFICIENTE", False, [], "", None, ("OPEN", "needs_data")),
        ("SIN_COINCIDENCIA", False, None, None, None, ("OPEN", "needs_data")),
        ("REVISION_REQUERIDA", False, [{"method": "PUERTA"}], "", None, ("OPEN", "actionable")),
        (
            "REVISION_REQUERIDA",
            False,
            [ORIGINAL_WITHOUT_BOUNDARY],
            "MULTIPLES_CANDIDATOS; CRS_NO_CONFIRMADO",
            None,
            ("OPEN", "needs_reference"),
        ),
        (
            "REVISION_REQUERIDA",
            True,
            [ORIGINAL_WITHOUT_BOUNDARY],
            "Reapertura humana",
            "reopen",
            ("OPEN", "needs_reference"),
        ),
        (
            "REVISION_REQUERIDA",
            False,
            [{"method": "COORD_TEXTO"}],
            "LIMITE_TERRITORIAL_INVALIDO",
            None,
            ("OPEN", "needs_reference"),
        ),
        (
            "REVISION_REQUERIDA",
            False,
            [{"method": "COORD_ORIGINAL", "evidence": ["PUNTO_FUERA_UBIGEO"]}],
            "PUNTO_FUERA_UBIGEO",
            None,
            ("OPEN", "actionable"),
        ),
    ],
)
def test_review_classification(resolution, manual, candidates, reason, action, expected):
    assert classify_review(resolution, manual, candidates, reason, action) == expected


@pytest.mark.parametrize("malformed", [None, 12, "legacy text", {"legacy": True}, [None, "legacy", []]])
def test_classification_tolerates_invalid_legacy_candidate_shapes(malformed):
    assert classify_review("REVISION_REQUERIDA", False, malformed, None) == ("OPEN", "needs_data")


def test_classification_tolerates_malformed_evidence_without_mutation():
    candidates = [
        {"method": ["legacy"], "evidence": {}},
        {"method": "COORD_ORIGINAL", "evidence": [{"legacy": True}, "LIMITE_TERRITORIAL_INVALIDO"]},
    ]
    assert classify_review("REVISION_REQUERIDA", False, candidates, "") == ("OPEN", "needs_reference")
    assert candidates[1]["evidence"] == [{"legacy": True}, "LIMITE_TERRITORIAL_INVALIDO"]


def seed_v1(engine):
    """Create the complete old schema by removing only the four additive v2 columns."""
    Base.metadata.create_all(engine)
    sessions = sessionmaker(engine)
    with sessions() as db:
        db.add(User(id="user", username="synthetic", password_hash="unusable", role="admin"))
        db.flush()
        db.add(Upload(id="upload", filename="synthetic.csv", size=1, created_by="user"))
        db.flush()
        db.add(Run(id="parent", upload_id="upload", name="Original", created_by="user", status="COMPLETED"))
        db.flush()
        cases = [
            ("accepted", "ACEPTADO_AUTOMATICO", False, [], []),
            ("manual", "ACEPTADO_MANUAL", True, [], ["manual_point"]),
            ("unresolved", "SIN_COINCIDENCIA", True, [], ["unresolved"]),
            ("reopened", "REVISION_REQUERIDA", True, [ORIGINAL_WITHOUT_BOUNDARY], ["unresolved", "reopen"]),
            ("reclosed", "SIN_COINCIDENCIA", True, [], ["reopen", "unresolved"]),
            ("no-reference", "NO_EVALUABLE_REFERENCIA", False, [], []),
            ("technical", "ERROR_TECNICO", False, [], []),
            ("data", "INFORMACION_INSUFICIENTE", False, [], []),
            ("actionable", "REVISION_REQUERIDA", False, [{"method": "PUERTA"}], []),
        ]
        for identifier, resolution, manual, candidates, actions in cases:
            db.add(
                Location(
                    id=identifier,
                    run_id="parent",
                    unit_key=identifier,
                    resolution=resolution,
                    manual=manual,
                    candidates=candidates,
                    reason="Evidencia sintética conservada",
                    normalized={"original_marker": identifier},
                    revision=len(actions),
                )
            )
            db.flush()
            for version, action in enumerate(actions, 1):
                db.add(
                    Revision(
                        id=f"{identifier}-{version}",
                        location_id=identifier,
                        revision=version,
                        actor="test",
                        action=action,
                        created_at=100 - version,
                        reason="Historia sintética",
                        snapshot={"synthetic": identifier, "revision": version},
                    )
                )
        db.add(SourceRow(run_id="parent", ordinal=1, location_id="reopened", raw={"preserve": "000001"}))
        db.add(SchemaVersion(version=1, applied_at=123456))
        db.commit()
    # SQLite cannot DROP a column named by a table-level foreign key. Rebuild
    # only this synthetic fixture table with the exact v1 column/constraint DDL.
    ddl = str(CreateTable(Run.__table__).compile(engine))
    ddl = "\n".join(
        line
        for line in ddl.splitlines()
        if not any(column in line for column in ("parent_run_id", "superseded_by"))
    )
    ddl = ddl.replace("CREATE TABLE runs (", "CREATE TABLE runs_v1 (")
    ddl = ddl[: ddl.rfind(")")].rstrip().rstrip(",") + "\n)"
    old_columns = ", ".join(
        column.name
        for column in Run.__table__.columns
        if column.name not in {"parent_run_id", "superseded_by"}
    )
    with engine.connect() as conn:
        conn.exec_driver_sql("PRAGMA foreign_keys=OFF")
        conn.commit()
        conn.execute(text(ddl))
        conn.execute(text(f"INSERT INTO runs_v1 ({old_columns}) SELECT {old_columns} FROM runs"))
        conn.execute(text("DROP TABLE runs"))
        conn.execute(text("ALTER TABLE runs_v1 RENAME TO runs"))
        conn.execute(text("CREATE INDEX ix_runs_status ON runs (status)"))
        conn.execute(text("DROP INDEX ix_location_review_queue"))
        for table, column in (
            ("locations", "review_status"),
            ("locations", "review_bucket"),
        ):
            conn.execute(text(f"ALTER TABLE {table} DROP COLUMN {column}"))
        conn.commit()
        conn.exec_driver_sql("PRAGMA foreign_keys=ON")
        assert not conn.execute(text("PRAGMA foreign_key_check")).all()


def contents(engine):
    with engine.connect() as conn:
        return {
            table: [dict(row) for row in conn.execute(text(f"SELECT * FROM {table} ORDER BY id")).mappings()]
            for table in ("locations", "runs", "revisions", "source_rows", "uploads", "users")
        }


@pytest.fixture
def legacy_engine(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    seed_v1(engine)
    try:
        yield engine
    finally:
        engine.dispose()


def test_v1_upgrade_preserves_data_and_latest_manual_action(legacy_engine, monkeypatch):
    monkeypatch.setattr(migrations, "BACKFILL_BATCH_SIZE", 2)
    before = contents(legacy_engine)
    migrations.migrate(legacy_engine)
    after = contents(legacy_engine)
    for table, rows in before.items():
        for old, new in zip(rows, after[table], strict=True):
            assert {key: new[key] for key in old} == old
    with legacy_engine.connect() as conn:
        expected = {
            "accepted": ("CLOSED", "none"),
            "manual": ("CLOSED", "none"),
            "unresolved": ("CLOSED", "none"),
            "reclosed": ("CLOSED", "none"),
            "reopened": ("OPEN", "needs_reference"),
            "no-reference": ("OPEN", "needs_reference"),
            "technical": ("OPEN", "technical"),
            "data": ("OPEN", "needs_data"),
            "actionable": ("OPEN", "actionable"),
        }
        actual = {
            row.id: (row.review_status, row.review_bucket)
            for row in conn.execute(text("SELECT id, review_status, review_bucket FROM locations"))
        }
        assert actual == expected
        assert conn.execute(text("SELECT version FROM schema_versions ORDER BY version")).scalars().all() == [
            1,
            2,
            3,
            4,
            5,
            6,
        ]
        assert conn.scalar(text("SELECT applied_at FROM schema_versions WHERE version=1")) == 123456
        assert conn.scalar(text("SELECT manual FROM locations WHERE id='reopened'")) == 1
        assert conn.scalar(text("SELECT parent_run_id FROM runs WHERE id='parent'")) is None
    indexes = {
        index["name"]: index["column_names"] for index in inspect(legacy_engine).get_indexes("locations")
    }
    assert indexes["ix_location_review_queue"] == ["run_id", "review_status", "review_bucket", "id"]
    foreign_keys = {
        tuple(fk["constrained_columns"]) for fk in inspect(legacy_engine).get_foreign_keys("runs")
    }
    assert {("parent_run_id",), ("superseded_by",)} <= foreign_keys
    # An already migrated database must not overwrite newer workflow decisions.
    with legacy_engine.begin() as conn:
        conn.execute(
            text("UPDATE locations SET review_status='CLOSED', review_bucket='none' WHERE id='data'")
        )
    changed = contents(legacy_engine)
    migrations.migrate(legacy_engine)
    assert contents(legacy_engine) == changed


def test_failed_upgrade_rolls_back_schema_and_backfill(legacy_engine, monkeypatch):
    before = contents(legacy_engine)
    monkeypatch.setattr(migrations, "BACKFILL_BATCH_SIZE", 2)
    original = migrations.classify_review
    calls = 0

    def fail_later(*args):
        nonlocal calls
        calls += 1
        if calls == 4:
            raise RuntimeError("Synthetic interrupted migration")
        return original(*args)

    monkeypatch.setattr(migrations, "classify_review", fail_later)
    with pytest.raises(RuntimeError, match="interrupted migration"):
        migrations.migrate(legacy_engine)
    assert contents(legacy_engine) == before
    assert "review_status" not in {c["name"] for c in inspect(legacy_engine).get_columns("locations")}
    with legacy_engine.connect() as conn:
        assert list(conn.scalars(select(SchemaVersion.version))) == [1]
    monkeypatch.setattr(migrations, "classify_review", original)
    migrations.migrate(legacy_engine)


def test_fresh_database_versions_and_defaults(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'new.db'}")
    try:
        migrations.migrate(engine)
        migrations.migrate(engine)
        with engine.connect() as conn:
            assert list(conn.scalars(select(SchemaVersion.version).order_by(SchemaVersion.version))) == [
                1,
                2,
                3,
                4,
                5,
                6,
            ]
        columns = {column["name"]: column for column in inspect(engine).get_columns("locations")}
        assert columns["review_status"]["default"] == "'OPEN'"
        assert columns["review_bucket"]["default"] == "'none'"
    finally:
        engine.dispose()


def test_v2_geometry_upgrade_is_additive_and_preserves_closed_queue(legacy_engine):
    migrations.migrate(legacy_engine)
    with legacy_engine.begin() as conn:
        conn.execute(text("DROP TABLE address_memory"))
        conn.execute(text("ALTER TABLE locations DROP COLUMN geometry"))
        conn.execute(text("DELETE FROM schema_versions WHERE version=3"))
        conn.execute(
            text("UPDATE locations SET review_status='CLOSED', review_bucket='none' WHERE id='data'")
        )
    before = contents(legacy_engine)
    migrations.migrate(legacy_engine)
    after = contents(legacy_engine)
    for table, rows in before.items():
        for old, new in zip(rows, after[table], strict=True):
            assert {key: new[key] for key in old} == old
    with legacy_engine.connect() as conn:
        assert conn.scalar(text("SELECT review_status FROM locations WHERE id='data'")) == "CLOSED"
        assert conn.scalar(text("SELECT count(*) FROM locations WHERE geometry IS NOT NULL")) == 0
    assert "address_memory" in inspect(legacy_engine).get_table_names()


def test_worker_supersedes_parent_only_after_success_and_keeps_newest_child(legacy_engine, monkeypatch):
    migrations.migrate(legacy_engine)
    sessions = sessionmaker(legacy_engine, expire_on_commit=False)
    monkeypatch.setattr(worker, "SessionLocal", sessions)
    with sessions() as db:
        for identifier, created_at, rules_version, cancelled in (
            ("older", 1, RULES_VERSION, False),
            ("newer", 2, RULES_VERSION, False),
            ("failed", 3, "unavailable-test-version", False),
            ("cancelled", 4, RULES_VERSION, True),
        ):
            db.add(
                Run(
                    id=identifier,
                    upload_id="upload",
                    name=identifier,
                    created_by="user",
                    parent_run_id="parent",
                    created_at=created_at,
                    rules_version=rules_version,
                    ingested=True,
                    cancel_requested=cancelled,
                    issue_rows=int(identifier == "newer"),
                )
            )
        db.flush()
        # Failed/cancelled children must leave the original visible. Then a
        # newer successful child finishes before an older successful child.
        for order, identifier in enumerate(("failed", "cancelled", "newer", "older")):
            db.add(Job(kind="RUN", target_id=identifier, created_at=order))
        db.commit()
    with sessions() as db:
        assert db.get(Run, "parent").superseded_by is None
    for identifier, expected_status, expected_successor in (
        ("failed", "FAILED", None),
        ("cancelled", "CANCELLED", None),
        ("newer", "COMPLETED_WITH_ISSUES", "newer"),
        ("older", "COMPLETED", "newer"),
    ):
        assert worker.work_once()
        with sessions() as db:
            assert db.get(Run, identifier).status == expected_status
            assert db.get(Run, "parent").superseded_by == expected_successor
    with sessions() as db:
        assert db.get(Run, "older").superseded_by == "newer"
        assert db.get(Run, "newer").superseded_by is None
        db.add(
            Run(
                id="newest",
                upload_id="upload",
                name="Newest",
                created_by="user",
                parent_run_id="parent",
                created_at=5,
                rules_version=RULES_VERSION,
                ingested=True,
            )
        )
        db.add(Job(kind="RUN", target_id="newest", created_at=5))
        db.commit()
    assert worker.work_once()
    with sessions() as db:
        assert db.get(Run, "parent").superseded_by == "newest"
        assert db.get(Run, "newer").superseded_by == "newest"
        assert db.get(Run, "older").superseded_by == "newer"
        current = list(
            db.scalars(
                select(Run.id).where(
                    Run.parent_run_id == "parent",
                    Run.status.in_(["COMPLETED", "COMPLETED_WITH_ISSUES"]),
                    Run.superseded_by.is_(None),
                )
            )
        )
        assert current == ["newest"]


def test_worker_assigns_queue_classification_before_revision(legacy_engine, monkeypatch):
    migrations.migrate(legacy_engine)
    sessions = sessionmaker(legacy_engine, expire_on_commit=False)
    monkeypatch.setattr(worker, "SessionLocal", sessions)
    with sessions() as db:
        db.add(
            Run(id="classify", upload_id="upload", name="Classification", created_by="user", ingested=True)
        )
        db.flush()
        db.add(Location(id="pending", run_id="classify", unit_key="pending", normalized={}))
        db.add(Job(kind="RUN", target_id="classify", created_at=time.time()))
        db.commit()
    assert worker.work_once()
    with sessions() as db:
        item = db.get(Location, "pending")
        assert item.review_status == "OPEN"
        assert item.review_bucket == "needs_data"
        revision = db.scalar(select(Revision).where(Revision.location_id == "pending"))
        assert revision.snapshot["review_status"] == "OPEN"
        assert revision.snapshot["review_bucket"] == "needs_data"


def test_version_four_creates_unconfigured_default_and_preserves_version_three_runs(legacy_engine):
    migrations.migrate(legacy_engine)
    with legacy_engine.begin() as conn:
        before = list(conn.execute(text("SELECT id, reference_id, config FROM runs ORDER BY id")))
        conn.execute(text("DROP TABLE processing_defaults"))
        conn.execute(text("DELETE FROM schema_versions WHERE version=4"))
    migrations.migrate(legacy_engine)
    migrations.migrate(legacy_engine)
    with legacy_engine.connect() as conn:
        assert list(conn.execute(text("SELECT id, reference_id, config FROM runs ORDER BY id"))) == before
        assert conn.execute(
            text("SELECT id, reference_id, updated_by, updated_at FROM processing_defaults")
        ).all() == [("global", None, None, None)]
