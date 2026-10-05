"""Windows launcher integration checks; only temporary SQLite data and free ports."""

import contextlib
import json
import os
import secrets
import socket
import subprocess
import time
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PYTHON = ROOT / "backend/.venv/Scripts/python.exe"
pytestmark = pytest.mark.skipif(os.name != "nt", reason="Windows local launcher")


def free_port():
    with socket.socket() as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def reachable(port):
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.2):
            return True
    except OSError:
        return False


def wait_until(predicate, timeout=45):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.15)
    raise AssertionError("El servicio aislado no alcanzo el estado esperado.")


@pytest.fixture
def installation(tmp_path):
    env = os.environ.copy()
    env.update(
        GEOPOL_DATABASE_URL="sqlite:///" + (tmp_path / "test.db").as_posix(),
        GEOPOL_STORAGE_PATH=str(tmp_path / "storage"),
        GEOPOL_BOOTSTRAP_PASSWORD=secrets.token_urlsafe(24),
    )
    for args in (
        ["init-db"],
        ["create-user", "--username", "test_local", "--role", "admin"],
    ):
        subprocess.run(
            [str(PYTHON), "-m", "geopol.cli", *args],
            cwd=ROOT,
            env=env,
            capture_output=True,
            check=True,
            timeout=30,
        )
    api_port, port = free_port(), free_port()
    while port == api_port:
        port = free_port()
    command = [
        str(PYTHON),
        str(ROOT / "scripts/run_local.py"),
        "--no-browser",
        "--api-port",
        str(api_port),
        "--port",
        str(port),
        "--runtime-dir",
        str(tmp_path / "logs with spaces"),
    ]
    return command, env, api_port, port


@contextlib.contextmanager
def launcher(command, env):
    process = subprocess.Popen(
        command,
        cwd=ROOT,
        env=env,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    try:
        yield process
    finally:
        if process.poll() is None:
            try:
                process.communicate(b"salir\n", timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()
                process.communicate(timeout=10)


def test_start_proxy_worker_and_stop_all_services_then_restart(installation):
    command, env, api_port, port = installation
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    for _ in range(2):
        with launcher(command, env) as process:
            wait_until(lambda: reachable(port) or process.poll() is not None)
            assert process.poll() is None, process.communicate()[0].decode(
                errors="replace"
            )
            with opener.open(
                f"http://127.0.0.1:{port}/api/health", timeout=10
            ) as response:
                assert json.load(response)["status"] == "ok"
            with opener.open(f"http://127.0.0.1:{port}", timeout=10) as response:
                assert (
                    response.read() == (ROOT / "frontend/dist/index.html").read_bytes()
                )
            request = urllib.request.Request(
                f"http://127.0.0.1:{port}/api/auth/login",
                data=json.dumps(
                    {
                        "username": "test_local",
                        "password": env["GEOPOL_BOOTSTRAP_PASSWORD"],
                    }
                ).encode(),
                headers={"Content-Type": "application/json"},
            )
            with opener.open(request, timeout=10) as response:
                token = json.load(response)["token"]
            request = urllib.request.Request(
                f"http://127.0.0.1:{port}/api/health/worker",
                headers={"Authorization": "Bearer " + token},
            )
            with opener.open(request, timeout=10) as response:
                assert json.load(response)["status"] == "ok"
            output, _ = process.communicate(b"salir\n", timeout=15)
            assert process.returncode == 0, output.decode(errors="replace")
        wait_until(lambda: not reachable(api_port) and not reachable(port), timeout=10)


def test_second_launcher_cannot_start_another_worker(installation):
    command, env, api_port, port = installation
    with launcher(command, env) as process:
        wait_until(lambda: reachable(port) or process.poll() is not None)
        assert process.poll() is None, process.communicate()[0].decode(errors="replace")
        result = subprocess.run(
            command, cwd=ROOT, env=env, capture_output=True, timeout=10, check=False
        )
        assert result.returncode == 1
        assert b"ya esta iniciado" in result.stderr
        assert reachable(api_port) and reachable(port)


def test_occupied_port_is_left_untouched(installation):
    command, env, api_port, port = installation
    with socket.socket() as owner:
        owner.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        owner.bind(("127.0.0.1", api_port))
        owner.listen()
        result = subprocess.run(
            command, cwd=ROOT, env=env, capture_output=True, timeout=10, check=False
        )
        assert result.returncode == 1
        assert b"esta ocupado" in result.stderr
        assert reachable(api_port)
        assert not reachable(port)
