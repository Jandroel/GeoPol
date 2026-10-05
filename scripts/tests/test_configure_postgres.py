"""Installer contracts with a fake cluster; never connects to a real database."""

import copy
import importlib.util
import json
import re
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import unquote, urlsplit

import psycopg
import pytest

SPEC = importlib.util.spec_from_file_location(
    "configure_postgres", Path(__file__).resolve().parents[1] / "configure_postgres.py"
)
setup = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(setup)


class Result:
    def __init__(self, rows):
        self.rows = rows

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return self.rows


class Cluster:
    def __init__(self):
        self.roles = {}
        self.databases = {}
        self.extensions = {}
        self.available = {"postgis", "pg_trgm", "plpgsql"}
        self.version = 160006
        self.connections = []
        self.statements = []
        self.extension_failure = False
        self.create_database_failure = False
        self.connection_failure = None

    def connect(self, **kwargs):
        self.connections.append(kwargs.copy())
        assert kwargs["autocommit"] is True
        assert kwargs["connect_timeout"] == 5
        if self.connection_failure:
            raise self.connection_failure
        if kwargs["user"] != "postgres":
            role = self.roles[kwargs["user"]]
            assert kwargs["password"] == role["password"]
            assert self.databases[kwargs["dbname"]] == kwargs["user"]
        return Connection(self, kwargs["dbname"])


class Connection:
    def __init__(self, cluster, database):
        self.cluster = cluster
        self.database = database
        self.info = SimpleNamespace(server_version=cluster.version)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    @contextmanager
    def transaction(self):
        before = copy.deepcopy((self.cluster.roles, self.cluster.extensions))
        try:
            yield
        except Exception:
            self.cluster.roles, self.cluster.extensions = before
            raise

    def execute(self, statement, parameters=None):
        query = statement if isinstance(statement, str) else statement.as_string()
        self.cluster.statements.append((query, parameters))
        if query == "SELECT name FROM pg_available_extensions":
            return Result([(name,) for name in self.cluster.available])
        if query == "SELECT extname FROM pg_extension":
            return Result(
                [(name,) for name in self.cluster.extensions.get(self.database, set())]
            )
        if query.startswith("SELECT pg_get_userbyid"):
            owner = self.cluster.databases.get(parameters[0])
            return Result([] if owner is None else [(owner,)])
        if query.startswith("SELECT shobj_description"):
            role = self.cluster.roles.get(parameters[0])
            return Result([] if role is None else [(role["marker"],)])
        identifiers = re.findall(r'"([^"]+)"', query)
        literals = [
            literal.replace("''", "'")
            for literal in re.findall(r"'((?:[^']|'')*)'", query)
        ]
        if query.startswith("CREATE ROLE"):
            assert identifiers[0] not in self.cluster.roles
            self.cluster.roles[identifiers[0]] = {
                "marker": None,
                "password": literals[-1],
            }
        elif query.startswith("COMMENT ON ROLE"):
            self.cluster.roles[identifiers[0]]["marker"] = literals[-1]
        elif query.startswith("CREATE DATABASE"):
            if self.cluster.create_database_failure:
                raise psycopg.OperationalError("connection lost before CREATE DATABASE")
            assert identifiers[0] not in self.cluster.databases
            self.cluster.databases[identifiers[0]] = identifiers[1]
        elif query.startswith("CREATE EXTENSION"):
            if self.cluster.extension_failure:
                raise psycopg.errors.UndefinedFile(
                    "missing postgis shared library; secret must not be printed"
                )
            self.cluster.extensions.setdefault(self.database, set()).add(identifiers[0])
        else:
            raise AssertionError(f"Unexpected SQL: {query}")
        return Result([])


@pytest.fixture
def installation(tmp_path, monkeypatch):
    root = tmp_path / "workspace"
    root.mkdir()
    (root / ".env").write_text(
        "GEOPOL_DATABASE_URL=sqlite:///existing.db\n", encoding="utf-8"
    )
    monkeypatch.setattr(setup, "ROOT", root)
    cluster = Cluster()
    environment = {
        "GEOPOL_SETUP_PGHOST": "127.0.0.1",
        "GEOPOL_SETUP_PGPORT": "5432",
        "GEOPOL_SETUP_PGDATABASE": "geopol_test",
        "GEOPOL_SETUP_PGUSER": "postgres",
        "GEOPOL_SETUP_PGPASSWORD": "admin-secret-do-not-save",
    }
    path = root / ".local" / "native.json"

    def unexpected_prompt(*args):
        raise AssertionError("An environment-driven run must never prompt")

    def configure(**kwargs):
        return setup.configure(
            path,
            environ=environment,
            input_fn=unexpected_prompt,
            password_fn=unexpected_prompt,
            connect=cluster.connect,
            **kwargs,
        )

    return SimpleNamespace(
        cluster=cluster,
        environment=environment,
        path=path,
        root=root,
        configure=configure,
        pending=path.with_name("native.pending.json"),
    )


def test_new_installation_owns_database_and_encodes_only_application_secret(
    installation, monkeypatch
):
    app_secret = "application +:/?#@%&' password"
    monkeypatch.setattr(setup.secrets, "token_urlsafe", lambda size: app_secret)
    config = installation.configure()
    parsed = urlsplit(config["database_url"])
    assert parsed.scheme == "postgresql+psycopg"
    assert parsed.username == "geopol_test_app"
    assert unquote(parsed.password) == app_secret
    assert not parsed.query and not parsed.fragment
    assert installation.cluster.databases == {"geopol_test": "geopol_test_app"}
    assert installation.cluster.extensions == {"geopol_test": {"postgis", "pg_trgm"}}
    assert installation.cluster.roles["geopol_test_app"]["password"] == app_secret
    assert "NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION" in next(
        query
        for query, _ in installation.cluster.statements
        if query.startswith("CREATE ROLE")
    )
    assert config["storage_path"] == str(
        (installation.root / "data/storage-native").resolve()
    )
    assert Path(config["storage_path"]).is_dir()
    assert (config["web_port"], config["api_port"]) == (5173, 8000)
    assert setup.load_config(installation.path) == config
    assert installation.environment[
        "GEOPOL_SETUP_PGPASSWORD"
    ] not in installation.path.read_text(encoding="utf-8")
    assert not installation.pending.exists()
    assert (
        installation.root / ".env"
    ).read_text() == "GEOPOL_DATABASE_URL=sqlite:///existing.db\n"


def test_repeat_preserves_credentials_and_does_read_only_validation_without_admin(
    installation,
):
    original = installation.configure(web_port=5190, api_port=8090)
    raw = installation.path.read_bytes()
    roles = copy.deepcopy(installation.cluster.roles)
    installation.cluster.connections.clear()
    installation.cluster.statements.clear()
    installation.environment.clear()
    assert installation.configure() == original
    assert installation.path.read_bytes() == raw
    assert installation.cluster.roles == roles
    assert len(installation.cluster.connections) == 1
    assert installation.cluster.connections[0]["user"] == "geopol_test_app"
    assert all(
        query.startswith("SELECT ") for query, _ in installation.cluster.statements
    )


def test_explicit_port_change_preserves_database_url(installation):
    original = installation.configure()
    updated = installation.configure(web_port=5191)
    assert updated["database_url"] == original["database_url"]
    assert (updated["web_port"], updated["api_port"]) == (5191, 8000)
    assert setup.load_config(installation.path) == updated


@pytest.mark.parametrize("collision", ["database", "role"])
def test_existing_unrelated_database_or_role_is_never_modified(installation, collision):
    if collision == "database":
        installation.cluster.databases["geopol_test"] = "existing_owner"
    else:
        installation.cluster.roles["geopol_test_app"] = {
            "marker": None,
            "password": "existing-password",
        }
    before = copy.deepcopy((installation.cluster.databases, installation.cluster.roles))
    with pytest.raises(setup.SetupError, match="Elige otro nombre"):
        installation.configure()
    assert (installation.cluster.databases, installation.cluster.roles) == before
    assert not installation.path.exists() and not installation.pending.exists()
    assert all(
        query.startswith("SELECT ") for query, _ in installation.cluster.statements
    )


def test_missing_postgis_is_reported_before_creating_resources(installation):
    installation.cluster.available.remove("postgis")
    with pytest.raises(setup.SetupError, match="Instala PostGIS"):
        installation.configure()
    assert not installation.cluster.databases and not installation.cluster.roles
    assert not installation.pending.exists()


def test_postgres_15_is_rejected_before_creating_resources(installation):
    installation.cluster.version = 150010
    with pytest.raises(setup.SetupError, match="PostgreSQL 16"):
        installation.configure()
    assert not installation.cluster.databases and not installation.cluster.roles
    assert not installation.pending.exists()


def test_partial_installation_resumes_without_recreating_role_or_changing_secret(
    installation,
):
    installation.cluster.extension_failure = True
    with pytest.raises(setup.SetupError, match="No se pudo habilitar PostGIS"):
        installation.configure()
    pending = json.loads(installation.pending.read_text(encoding="utf-8"))
    assert not installation.path.exists()
    assert installation.environment[
        "GEOPOL_SETUP_PGPASSWORD"
    ] not in installation.pending.read_text(encoding="utf-8")
    original_roles = copy.deepcopy(installation.cluster.roles)
    original_databases = copy.deepcopy(installation.cluster.databases)
    installation.cluster.extension_failure = False
    installation.cluster.statements.clear()
    config = installation.configure()
    assert config["database_url"] == pending["config"]["database_url"]
    assert installation.cluster.roles == original_roles
    assert installation.cluster.databases == original_databases
    assert not any(
        query.startswith(("CREATE ROLE", "CREATE DATABASE", "ALTER "))
        for query, _ in installation.cluster.statements
    )
    assert not installation.pending.exists()


def test_resume_after_role_creation_preserves_secret_and_creates_missing_database(
    installation,
):
    installation.cluster.create_database_failure = True
    with pytest.raises(setup.SetupError):
        installation.configure()
    original_roles = copy.deepcopy(installation.cluster.roles)
    assert original_roles and not installation.cluster.databases
    installation.cluster.create_database_failure = False
    config = installation.configure(web_port=5290, api_port=8290)
    assert installation.cluster.roles == original_roles
    assert installation.cluster.databases == {"geopol_test": "geopol_test_app"}
    assert (config["web_port"], config["api_port"]) == (5290, 8290)
    assert not installation.pending.exists()


def test_private_file_permission_failure_prevents_postgresql_mutations(
    installation, monkeypatch
):
    def reject_file(path):
        raise setup.SetupError("No se pudieron proteger las credenciales")

    monkeypatch.setattr(setup, "_restrict_file", reject_file)
    with pytest.raises(setup.SetupError, match="proteger las credenciales"):
        installation.configure()
    assert not installation.cluster.roles and not installation.cluster.databases
    assert not installation.path.exists() and not installation.pending.exists()


@pytest.mark.parametrize("replacement", ["role_marker", "database_owner"])
def test_pending_installation_does_not_claim_resources_with_changed_ownership(
    installation, replacement
):
    installation.cluster.extension_failure = True
    with pytest.raises(setup.SetupError):
        installation.configure()
    if replacement == "role_marker":
        installation.cluster.roles["geopol_test_app"]["marker"] = "someone-else"
    else:
        installation.cluster.databases["geopol_test"] = "someone_else"
    before = copy.deepcopy((installation.cluster.roles, installation.cluster.databases))
    installation.cluster.statements.clear()
    with pytest.raises(setup.SetupError, match="No se modificó"):
        installation.configure()
    assert (installation.cluster.roles, installation.cluster.databases) == before
    assert all(
        query.startswith("SELECT ") for query, _ in installation.cluster.statements
    )
    assert installation.pending.exists() and not installation.path.exists()


def test_repeat_missing_extension_preserves_configuration_and_never_runs_ddl(
    installation,
):
    installation.configure()
    original = installation.path.read_bytes()
    installation.cluster.extensions["geopol_test"].remove("postgis")
    installation.cluster.statements.clear()
    with pytest.raises(setup.SetupError, match="administrador habilitarlas"):
        installation.configure()
    assert installation.path.read_bytes() == original
    assert all(
        query.startswith("SELECT ") for query, _ in installation.cluster.statements
    )


@pytest.mark.parametrize(
    "failure",
    [
        psycopg.OperationalError("connection refused with secret-payload"),
        psycopg.errors.InvalidPassword(
            "password authentication failed; secret-payload"
        ),
    ],
)
def test_cli_failures_hide_secrets_and_tracebacks(
    installation, monkeypatch, capsys, failure
):
    installation.cluster.connection_failure = failure
    monkeypatch.setattr(setup.psycopg, "connect", installation.cluster.connect)
    for key, value in installation.environment.items():
        monkeypatch.setenv(key, value)
    assert setup.main(["--config", str(installation.path)]) == 1
    output = capsys.readouterr()
    assert "ERROR:" in output.err
    assert "secret-payload" not in output.err
    assert "Traceback" not in output.err
    assert (
        installation.environment["GEOPOL_SETUP_PGPASSWORD"]
        not in output.err + output.out
    )
    assert not installation.pending.exists()


def test_existing_sqlite_config_is_rejected_without_fallback_or_overwrite(installation):
    installation.path.parent.mkdir()
    original = '{"database_url": "sqlite:///existing.db"}'
    installation.path.write_text(original, encoding="utf-8")
    with pytest.raises(setup.SetupError, match="URL PostgreSQL válida"):
        installation.configure()
    assert installation.path.read_text(encoding="utf-8") == original
    assert not installation.cluster.connections


def test_interactive_defaults_and_masked_password_callback(tmp_path, monkeypatch):
    cluster = Cluster()
    monkeypatch.setattr(setup, "ROOT", tmp_path)
    prompts = []
    password_prompts = []
    setup.configure(
        tmp_path / "native.json",
        environ={},
        connect=cluster.connect,
        input_fn=lambda prompt: prompts.append(prompt) or "",
        password_fn=lambda prompt: (
            password_prompts.append(prompt) or "masked-admin-secret"
        ),
    )
    assert len(prompts) == 4 and len(password_prompts) == 1
    assert "127.0.0.1" in prompts[0]
    assert "5432" in prompts[1]
    assert "geopol" in prompts[2]
    assert "postgres" in prompts[3]
    assert cluster.connections[0]["password"] == "masked-admin-secret"
    assert "masked-admin-secret" not in (tmp_path / "native.json").read_text(
        encoding="utf-8"
    )
