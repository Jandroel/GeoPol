"""Exercise the Bash installer in temporary projects with a fake Docker CLI."""

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
GIT_BASH = Path("C:/Program Files/Git/bin/bash.exe")
BASH = str(GIT_BASH) if os.name == "nt" and GIT_BASH.is_file() else shutil.which("bash")
pytestmark = pytest.mark.skipif(not BASH, reason="Bash is required for installer checks")
PASSWORD = "Synthetic account password 2026!"

FAKE_DOCKER = r'''#!/usr/bin/env bash
set -euo pipefail
state="$FAKE_STATE_DIR"
count=0
[[ ! -f "$state/count" ]] || count="$(cat "$state/count")"
count=$((count + 1))
printf '%s' "$count" > "$state/count"
printf '%s\0' "$@" > "$state/$count.args"
printf '%s\n' "${POSTGRES_PASSWORD-}" "${GEOPOL_WEB_PORT-}" "${GEOPOL_API_PORT-}" "${GEOPOL_ALLOWED_ORIGINS-}" > "$state/$count.env"
failure() { [[ "${FAKE_FAIL:-}" != "$1" ]] || { printf 'Synthetic Docker failure: %s\n' "$1" >&2; exit 29; }; }
case "${1:-}" in
    info) failure info; printf 'linux\n'; exit 0 ;;
    volume)
        [[ ! -f "$state/volumes" ]] || printf 'geopol-local_database\n'
        exit 0 ;;
    compose) shift ;;
    *) printf 'Unexpected Docker command\n' >&2; exit 90 ;;
esac
if [[ "${1:-}" == version ]]; then printf '2.30.0\n'; exit 0; fi
while [[ "${1:-}" == --* ]]; do
    case "$1" in
        --project-name|--env-file|--file) shift 2 ;;
        *) printf 'Unexpected Compose option: %s\n' "$1" >&2; exit 91 ;;
    esac
done
command="${1:-}"
shift
# Compose can create its persistent volumes before a port binding fails.
[[ "$command" != up ]] || touch "$state/volumes"
failure "$command"
case "$command" in
    config|build|stop|up) ;;
    exec)
        case "$*" in
            *bootstrap-user*)
                failure auth
                received="$(cat)"
                [[ "$received" == "$FAKE_EXPECTED_PASSWORD" ]] || { printf 'Incorrect password input\n' >&2; exit 92; }
                touch "$state/user"
                printf 'Administrador inicial creado: administrador.\n'
                ;;
            *'from geopol.models import User'*)
                failure users
                if [[ -f "$state/user" ]]; then printf 'yes\n'; else printf 'no\n'; fi
                ;;
            *Heartbeat*) failure heartbeat ;;
            *) printf 'Unexpected container command\n' >&2; exit 93 ;;
        esac
        ;;
    *) printf 'Unexpected Compose command: %s\n' "$command" >&2; exit 94 ;;
esac
'''


class Installation:
    def __init__(self, directory):
        self.root = directory / "project with spaces"
        self.root.mkdir()
        self.state = directory / "fake state"
        self.state.mkdir()
        self.bin = directory / "fake bin"
        self.bin.mkdir()
        for relative in (
            "instalar.sh", "iniciar.sh", "detener.sh", "scripts/local-compose.sh", "compose.yaml",
        ):
            destination = self.root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text((ROOT / relative).read_text(encoding="utf-8"), encoding="utf-8", newline="\n")
        docker = self.bin / "docker"
        docker.write_text(FAKE_DOCKER, encoding="utf-8", newline="\n")
        docker.chmod(0o755)
        self.environment = os.environ.copy()
        for name in ("POSTGRES_PASSWORD", "GEOPOL_WEB_PORT", "GEOPOL_API_PORT", "GEOPOL_ALLOWED_ORIGINS"):
            self.environment.pop(name, None)
        self.environment.update(
            PATH=str(self.bin) + os.pathsep + self.environment.get("PATH", ""),
            FAKE_STATE_DIR=self.state.as_posix(),
            FAKE_EXPECTED_PASSWORD=PASSWORD,
        )

    @property
    def config(self):
        return self.root / ".local/compose.env"

    def run(self, script="instalar.sh", *, args=(), input_text="", **environment):
        # Run outside the project to also check wrapper-relative paths.
        result = subprocess.run(
            [BASH, (self.root / script).as_posix(), *args],
            cwd=self.root.parent,
            env={**self.environment, **environment},
            # Binary stdin avoids Python translating LF to CRLF on Windows;
            # an interactive Git Bash terminal supplies LF to Bash's read.
            input=input_text.encode("utf-8"),
            capture_output=True,
            check=False,
            timeout=30,
        )
        return subprocess.CompletedProcess(
            result.args, result.returncode, result.stdout.decode("utf-8"), result.stderr.decode("utf-8"),
        )

    def calls(self):
        return [
            (int(path.stem), path.read_bytes().decode("utf-8").rstrip("\0").split("\0"))
            for path in sorted(self.state.glob("*.args"), key=lambda item: int(item.stem))
        ]

    def compose_calls(self):
        return [(number, args) for number, args in self.calls() if args[:2] == ["compose", "--project-name"]]


@pytest.fixture
def installation(tmp_path):
    return Installation(tmp_path)


def assert_success(result):
    assert result.returncode == 0, result.stdout + result.stderr


def test_install_restart_and_stop_preserve_configuration_and_accounts(installation):
    legacy_env = installation.root / ".env"
    legacy_env.write_text("GEOPOL_DATABASE_URL=sqlite:///existing.db\n", encoding="utf-8")
    first = installation.run(input_text=f"{PASSWORD}\n{PASSWORD}\n")
    assert_success(first)
    assert "GeoPol está listo: http://localhost:8080" in first.stdout
    original = installation.config.read_bytes()
    assert re.search(rb"^POSTGRES_PASSWORD=[a-f0-9]{64}\n", original)
    assert PASSWORD.encode() not in original
    assert legacy_env.read_text(encoding="utf-8") == "GEOPOL_DATABASE_URL=sqlite:///existing.db\n"

    inherited = {
        "POSTGRES_PASSWORD": "wrong-inherited-secret", "GEOPOL_WEB_PORT": "19080", "GEOPOL_API_PORT": "19000",
    }
    for script in ("instalar.sh", "iniciar.sh"):
        result = installation.run(script, **inherited)
        assert_success(result)
        assert "Crea tu acceso" not in result.stdout
        assert "http://localhost:8080" in result.stdout
        assert installation.config.read_bytes() == original
    result = installation.run("detener.sh", **inherited)
    assert_success(result)
    assert installation.config.read_bytes() == original
    calls = installation.compose_calls()
    assert calls
    for number, arguments in calls:
        assert arguments[:7] == [
            "compose", "--project-name", "geopol-local", "--env-file", ".local/compose.env", "--file", "compose.yaml",
        ]
        assert (installation.state / f"{number}.env").read_text(encoding="utf-8").splitlines() == ["", "", "", ""]
        assert PASSWORD not in " ".join(arguments)
        assert "down" not in arguments and "rm" not in arguments
    bootstrap = [arguments for _, arguments in calls if any("bootstrap-user" in item for item in arguments)]
    assert len(bootstrap) == 1
    assert bootstrap[0][7:11] == ["exec", "-T", "api", "python"]
    assert calls[-1][1][7:] == ["stop"]
    assert PASSWORD not in first.stdout + first.stderr


def test_new_installation_saves_requested_ports_once(installation):
    (installation.state / "user").touch()
    result = installation.run(GEOPOL_WEB_PORT="18080", GEOPOL_API_PORT="18000")
    assert_success(result)
    assert "http://localhost:18080" in result.stdout
    config = installation.config.read_text(encoding="utf-8")
    assert "GEOPOL_WEB_PORT=18080\n" in config
    assert "GEOPOL_API_PORT=18000\n" in config
    result = installation.run("iniciar.sh", GEOPOL_WEB_PORT="8080", GEOPOL_API_PORT="8000")
    assert_success(result)
    assert "http://localhost:18080" in result.stdout
    assert installation.config.read_text(encoding="utf-8") == config


@pytest.mark.parametrize("script", ["instalar.sh", "iniciar.sh"])
def test_failed_first_start_recovers_with_explicit_ports_without_resetting_data(installation, script):
    legacy_env = installation.root / ".env"
    legacy_contents = b"GEOPOL_DATABASE_URL=sqlite:///existing.db\n"
    legacy_env.write_bytes(legacy_contents)
    first = installation.run(FAKE_FAIL="up")
    assert first.returncode != 0
    assert "GeoPol está listo" not in first.stdout
    original = installation.config.read_bytes()
    assert (installation.state / "volumes").exists()

    recovered = installation.run(
        script,
        args=("--puertos", "8081", "8003"),
        input_text=f"{PASSWORD}\n{PASSWORD}\n",
        POSTGRES_PASSWORD="wrong-inherited-secret",
        GEOPOL_WEB_PORT="19080",
        GEOPOL_API_PORT="19000",
    )
    assert_success(recovered)
    assert "GeoPol está listo: http://localhost:8081" in recovered.stdout
    expected = original.replace(b"GEOPOL_WEB_PORT=8080\n", b"GEOPOL_WEB_PORT=8081\n").replace(
        b"GEOPOL_API_PORT=8000\n", b"GEOPOL_API_PORT=8003\n",
    )
    assert installation.config.read_bytes() == expected
    assert legacy_env.read_bytes() == legacy_contents
    assert (installation.state / "volumes").exists()
    assert (installation.state / "user").exists()
    reopened = installation.run("iniciar.sh")
    assert_success(reopened)
    assert "http://localhost:8081" in reopened.stdout
    assert "Crea tu acceso" not in reopened.stdout
    assert installation.config.read_bytes() == expected
    assert not any("down" in arguments or "rm" in arguments for _, arguments in installation.calls())
    assert PASSWORD not in recovered.stdout + recovered.stderr


@pytest.mark.parametrize("ports", [("0", "8003"), ("8081", "65536"), ("08081", "8003"), ("8081", "8081")])
@pytest.mark.parametrize("existing_config", [False, True])
def test_invalid_explicit_ports_are_rejected_before_any_mutation(installation, ports, existing_config):
    original = b"POSTGRES_PASSWORD=" + b"a" * 64 + b"\nGEOPOL_WEB_PORT=8080\nGEOPOL_API_PORT=8000\n"
    if existing_config:
        installation.config.parent.mkdir()
        installation.config.write_bytes(original)
    result = installation.run(args=("--puertos", *ports))
    assert result.returncode != 0
    assert "puertos" in result.stderr
    assert "GeoPol está listo" not in result.stdout
    if existing_config:
        assert installation.config.read_bytes() == original
    else:
        assert not installation.config.parent.exists()
    assert not installation.calls()


def test_existing_volumes_without_configuration_refuse_new_credentials(installation):
    (installation.state / "volumes").touch()
    result = installation.run()
    assert result.returncode != 0
    assert "Recupera ese archivo" in result.stderr
    assert not installation.config.exists()
    assert not installation.compose_calls()


@pytest.mark.parametrize("script", ["iniciar.sh", "detener.sh"])
def test_start_and_stop_do_not_create_an_installation(installation, script):
    result = installation.run(script)
    assert result.returncode != 0
    assert "Primero ejecuta bash instalar.sh" in result.stderr
    assert not installation.config.exists()
    assert not installation.compose_calls()


@pytest.mark.parametrize("failure", ["info", "config", "build", "up", "users", "auth", "heartbeat"])
def test_setup_failure_never_reports_ready_and_keeps_existing_credentials(installation, failure):
    installation.config.parent.mkdir()
    original = b"POSTGRES_PASSWORD=" + b"a" * 64 + b"\nGEOPOL_WEB_PORT=8080\nGEOPOL_API_PORT=8000\n"
    installation.config.write_bytes(original)
    result = installation.run(input_text=f"{PASSWORD}\n{PASSWORD}\n", FAKE_FAIL=failure)
    assert result.returncode != 0
    assert "GeoPol está listo" not in result.stdout
    assert installation.config.read_bytes() == original
    assert PASSWORD not in result.stdout + result.stderr
    assert not any("down" in arguments or "rm" in arguments for _, arguments in installation.calls())


def test_missing_account_input_stops_without_claiming_success(installation):
    result = installation.run()
    assert result.returncode != 0
    assert "No se recibió la contraseña" in result.stderr
    assert "GeoPol está listo" not in result.stdout
    assert installation.config.exists()
    assert not (installation.state / "user").exists()


def test_password_confirmation_retries_before_creating_account(installation):
    result = installation.run(input_text=f"short\n{PASSWORD}\nnot matching\n{PASSWORD}\n{PASSWORD}\n")
    assert_success(result)
    assert "Utiliza al menos 12 caracteres" in result.stdout
    assert "Las contraseñas no coinciden" in result.stdout
    assert PASSWORD not in result.stdout + result.stderr
    assert (installation.state / "user").exists()
