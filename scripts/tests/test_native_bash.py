"""Exercise the public Bash wrappers in disposable copies with synthetic tools."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
BASH = Path("C:/Program Files/Git/bin/bash.exe") if os.name == "nt" else shutil.which("bash")
pytestmark = pytest.mark.skipif(not BASH or not Path(BASH).is_file(), reason="Bash is not installed")

DRIVER = r'''
import json
import os
import sys
from pathlib import Path

root = Path(os.environ["NATIVE_TEST_ROOT"])
kind, *args = sys.argv[1:]
event = {"kind": kind, "args": args}
if kind == "python" and args and args[0] == "scripts/configure_postgres.py":
    event["admin_password_present"] = bool(os.environ.get("GEOPOL_SETUP_PGPASSWORD"))
    event["setup_settings"] = {
        field: os.environ.get("GEOPOL_SETUP_" + field)
        for field in ("PGHOST", "PGPORT", "PGDATABASE", "PGUSER")
    }
if kind == "python" and "bootstrap-user" in args:
    event["stdin"] = sys.stdin.read()
if kind == "python" and args[:2] == ["scripts/native_cli.py", "init-db"]:
    event["admin_password_present"] = "GEOPOL_SETUP_PGPASSWORD" in os.environ
with (root / "events.jsonl").open("a", encoding="utf-8") as stream:
    stream.write(json.dumps(event) + "\n")

if kind == "docker":
    raise SystemExit("Docker must never be used by the native installer")
if kind != "python":
    raise SystemExit(0)
if args and args[0] == "-c":
    exec(args[1], {"__name__": "__main__"})
elif args[:2] == ["-m", "venv"]:
    for relative in ("backend/.venv/Scripts/python.exe", "backend/.venv/bin/python"):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((root / "fake-bin/python").read_bytes())
        path.chmod(0o755)
elif args and args[0] == "scripts/configure_postgres.py":
    path = root / ".local/native.json"
    pending_path = root / ".local/native.pending.json"
    path.parent.mkdir(exist_ok=True)
    recovering = not path.exists() and pending_path.exists()
    if path.exists():
        config = json.loads(path.read_text())
    elif recovering:
        config = json.loads(pending_path.read_text())["config"]
    else:
        config = {
            "database_url": "postgresql+psycopg://geopol_app:synthetic-secret@127.0.0.1/geopol_test",
            "storage_path": str(root / "data/storage-native"),
            "api_port": 8000,
            "web_port": 5173,
        }
    for flag, value in zip(args[1::2], args[2::2]):
        config[{"--web-port": "web_port", "--api-port": "api_port"}[flag]] = int(value)
    path.write_text(json.dumps(config), encoding="utf-8")
    if recovering:
        pending_path.unlink()
elif args[:2] == ["scripts/native_cli.py", "has-users"]:
    print("yes" if (root / ".local/test-user").exists() else "no")
elif args[:2] == ["scripts/native_cli.py", "bootstrap-user"]:
    (root / ".local/test-user").write_text("administrador", encoding="utf-8")
'''


@pytest.fixture
def workspace(tmp_path):
    root = tmp_path / "GeoPol synthetic with spaces"
    (root / "scripts").mkdir(parents=True)
    (root / "backend").mkdir()
    (root / "frontend").mkdir()
    for name in ("instalar.sh", "iniciar.sh", "detener.sh"):
        shutil.copyfile(ROOT / name, root / name)
    shutil.copyfile(ROOT / "scripts/native.sh", root / "scripts/native.sh")
    (root / ".env").write_text("GEOPOL_DATABASE_URL=sqlite:///untouched-synthetic.db\n", encoding="utf-8")
    (root / "fake-driver.py").write_text(textwrap.dedent(DRIVER), encoding="utf-8")
    binary_dir = root / "fake-bin"
    binary_dir.mkdir()
    for name in ("python", "python3", "node", "npm", "docker"):
        command = binary_dir / name
        kind = "python" if name == "python3" else name
        command.write_text(
            '#!/usr/bin/env bash\nexec "$NATIVE_TEST_PYTHON" "$NATIVE_TEST_DRIVER" '
            + kind
            + ' "$@"\n',
            encoding="utf-8",
            newline="\n",
        )
        command.chmod(0o755)
    env = {key: value for key, value in os.environ.items() if not key.startswith("GEOPOL_")}
    env.update(
        PATH=str(binary_dir) + os.pathsep + env.get("PATH", ""),
        PYTHON=(binary_dir / "python").as_posix(),
        NATIVE_TEST_ROOT=root.as_posix(),
        NATIVE_TEST_PYTHON=Path(sys.executable).as_posix(),
        NATIVE_TEST_DRIVER=(root / "fake-driver.py").as_posix(),
    )
    return root, env


def invoke(workspace, script, *args, input_text="", extra_env=None):
    root, env = workspace
    result = subprocess.run(
        [str(BASH), str(root / script), *args],
        cwd=root.parent,
        env=env | (extra_env or {}),
        input=input_text.encode("utf-8"),
        capture_output=True,
        timeout=30,
        check=False,
    )
    # Bash terminal input uses LF; text-mode pipes would rewrite it as CRLF on Windows.
    result.stdout = result.stdout.decode("utf-8", errors="replace")
    result.stderr = result.stderr.decode("utf-8", errors="replace")
    return result


def events(root):
    path = root / "events.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()] if path.exists() else []


def credentials():
    return {
        "GEOPOL_SETUP_PGHOST": "127.0.0.1",
        "GEOPOL_SETUP_PGPORT": "5432",
        "GEOPOL_SETUP_PGDATABASE": "synthetic_geopol",
        "GEOPOL_SETUP_PGUSER": "synthetic_admin",
        "GEOPOL_SETUP_PGPASSWORD": "synthetic-pg-password",
        "GEOPOL_BOOTSTRAP_PASSWORD": "synthetic-web-password",
    }


def test_install_and_repeat_preserve_configuration_and_pass_secrets_privately(workspace):
    root, _ = workspace
    original_env = (root / ".env").read_bytes()
    result = invoke(workspace, "instalar.sh", "--puertos", "5517", "8800", extra_env=credentials())
    assert result.returncode == 0, result.stdout + result.stderr
    recorded = events(root)
    assert not any(event["kind"] == "docker" for event in recorded)
    configure = next(event for event in recorded if "scripts/configure_postgres.py" in event["args"])
    assert configure["args"] == ["scripts/configure_postgres.py", "--web-port", "5517", "--api-port", "8800"]
    assert configure["admin_password_present"]
    initialize = next(event for event in recorded if event["args"][:2] == ["scripts/native_cli.py", "init-db"])
    assert not initialize["admin_password_present"]
    bootstrap = next(event for event in recorded if "bootstrap-user" in event["args"])
    assert bootstrap["args"] == ["scripts/native_cli.py", "bootstrap-user", "--password-stdin"]
    assert bootstrap["stdin"] == credentials()["GEOPOL_BOOTSTRAP_PASSWORD"]
    command_text = json.dumps([event["args"] for event in recorded])
    for secret in (credentials()["GEOPOL_SETUP_PGPASSWORD"], credentials()["GEOPOL_BOOTSTRAP_PASSWORD"]):
        assert secret not in command_text
        assert secret not in result.stdout + result.stderr
    saved_config = (root / ".local/native.json").read_bytes()
    before_repeat = len(recorded)
    # No input or credentials are available on the repeated installation.
    repeated = invoke(workspace, "instalar.sh")
    assert repeated.returncode == 0, repeated.stdout + repeated.stderr
    assert "Se conservan las cuentas existentes." in repeated.stdout
    assert (root / ".local/native.json").read_bytes() == saved_config
    assert (root / ".env").read_bytes() == original_env
    assert not any("bootstrap-user" in event["args"] for event in events(root)[before_repeat:])


def test_start_saves_ports_then_forwards_and_stop_only_signals_native_supervisor(workspace):
    root, _ = workspace
    installed = invoke(workspace, "instalar.sh", extra_env=credentials())
    assert installed.returncode == 0, installed.stdout + installed.stderr
    configuration = json.loads((root / ".local/native.json").read_text())
    original_env = (root / ".env").read_bytes()
    first_event = len(events(root))
    for script, args in (
        ("iniciar.sh", ("--puertos", "5518", "8801")),
        ("iniciar.sh", ()),
        ("detener.sh", ()),
    ):
        result = invoke(workspace, script, *args)
        assert result.returncode == 0, result.stdout + result.stderr
    assert [event["args"] for event in events(root)[first_event:]] == [
        ["scripts/configure_postgres.py", "--web-port", "5518", "--api-port", "8801"],
        ["-u", "scripts/run_local.py", "--native", "--port", "5518", "--api-port", "8801"],
        ["-u", "scripts/run_local.py", "--native"],
        ["scripts/run_local.py", "--native", "--stop"],
    ]
    assert json.loads((root / ".local/native.json").read_text()) == configuration | {
        "web_port": 5518,
        "api_port": 8801,
    }
    assert (root / ".env").read_bytes() == original_env


def test_interactive_install_accepts_defaults_and_retries_password_confirmation(workspace):
    root, _ = workspace
    postgres_password, web_password = "synthetic-postgres-secret", "synthetic-web-secret"
    answers = ["", "", "", "", postgres_password, "short", web_password, "mismatch", web_password, web_password]
    result = invoke(workspace, "instalar.sh", input_text="\n".join(answers) + "\n")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Utiliza al menos 12 caracteres." in result.stdout
    assert "Las contraseñas no coinciden." in result.stdout
    bootstrap = next(event for event in events(root) if "bootstrap-user" in event["args"])
    assert bootstrap["stdin"] == web_password
    for secret in (postgres_password, web_password):
        assert secret not in result.stdout + result.stderr
        assert all(secret not in json.dumps(event["args"]) for event in events(root))


def test_pending_recovery_asks_only_for_admin_credentials_and_uses_saved_admin(workspace):
    root, _ = workspace
    pending = {
        "admin_user": "dueño_guardado",
        "config": {
            "database_url": "postgresql+psycopg://pending_app:private-pending-secret@127.0.0.1:5440/pending",
            "storage_path": str(root / "data/storage-native"),
            "api_port": 8101,
            "web_port": 5519,
        },
    }
    pending_path = root / ".local/native.pending.json"
    pending_path.parent.mkdir()
    pending_path.write_text(json.dumps(pending), encoding="utf-8")
    original_env = (root / ".env").read_bytes()
    result = invoke(
        workspace,
        "instalar.sh",
        input_text="\nsynthetic-recovery-password\n",
        extra_env={"GEOPOL_BOOTSTRAP_PASSWORD": "synthetic-web-password"},
    )
    assert result.returncode == 0, result.stdout + result.stderr
    configure = next(event for event in events(root) if "scripts/configure_postgres.py" in event["args"])
    assert configure["setup_settings"] == {
        "PGHOST": None,
        "PGPORT": None,
        "PGDATABASE": None,
        "PGUSER": "dueño_guardado",
    }
    assert configure["admin_password_present"]
    assert json.loads((root / ".local/native.json").read_text()) == pending["config"]
    assert (root / ".env").read_bytes() == original_env
    assert not pending_path.exists()
    for secret in ("private-pending-secret", "synthetic-recovery-password"):
        assert secret not in result.stdout + result.stderr
        assert all(secret not in json.dumps(event["args"]) for event in events(root))


def test_configured_install_ignores_leftover_pending_without_asking_for_admin(workspace):
    root, _ = workspace
    installed = invoke(workspace, "instalar.sh", extra_env=credentials())
    assert installed.returncode == 0, installed.stdout + installed.stderr
    config_path = root / ".local/native.json"
    saved_config = config_path.read_bytes()
    pending_path = root / ".local/native.pending.json"
    # Existing native.json wins even if the interrupted cleanup left invalid JSON.
    pending_path.write_text("synthetic-invalid-pending-secret", encoding="utf-8")
    first_event = len(events(root))
    result = invoke(workspace, "instalar.sh")
    assert result.returncode == 0, result.stdout + result.stderr
    repeated_events = events(root)[first_event:]
    configure = next(event for event in repeated_events if "scripts/configure_postgres.py" in event["args"])
    assert not configure["admin_password_present"]
    assert configure["setup_settings"]["PGUSER"] is None
    assert not any("native.pending.json" in json.dumps(event["args"]) for event in repeated_events)
    assert config_path.read_bytes() == saved_config
    assert "synthetic-invalid-pending-secret" not in result.stdout + result.stderr


def test_pending_admin_is_validated_without_exposing_pending_contents(workspace):
    root, _ = workspace
    pending_path = root / ".local/native.pending.json"
    pending_path.parent.mkdir()
    pending_path.write_text(
        json.dumps({"admin_user": ["invalid"], "password": "private-pending-secret"}),
        encoding="utf-8",
    )
    pending_bytes = pending_path.read_bytes()
    result = invoke(workspace, "instalar.sh")
    assert result.returncode != 0
    assert "no contiene un administrador" in result.stderr
    assert "private-pending-secret" not in result.stdout + result.stderr
    assert pending_path.read_bytes() == pending_bytes
    assert not any("scripts/configure_postgres.py" in event["args"] for event in events(root))


@pytest.mark.parametrize(
    ("script", "args"),
    [
        ("instalar.sh", ("--unknown",)),
        ("instalar.sh", ("--puertos", "0", "8000")),
        ("instalar.sh", ("--puertos", "5173", "65536")),
        ("instalar.sh", ("--puertos", "5173", "5173")),
        ("iniciar.sh", ("--puertos", "05173", "8000")),
        ("detener.sh", ("--puertos", "5173", "8000")),
    ],
)
def test_bad_flags_fail_before_dependencies_or_configuration(workspace, script, args):
    root, _ = workspace
    original_env = (root / ".env").read_bytes()
    result = invoke(workspace, script, *args)
    assert result.returncode != 0
    assert not events(root)
    assert not (root / "backend/.venv").exists()
    assert not (root / ".local/native.json").exists()
    assert (root / ".env").read_bytes() == original_env
