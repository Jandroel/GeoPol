"""Development entry point; all subprocesses use synthetic, temporary databases."""

import asyncio
import contextlib
import ctypes
import json
import os
import signal
import socket
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

import pytest

from geopol import dev


BACKEND = Path(__file__).resolve().parents[1]
PASSWORD = "Contraseña-sintética-2026"


def environment():
    result = {key: value for key, value in os.environ.items() if not key.startswith("GEOPOL_")}
    result["PYTHONPATH"] = str(BACKEND)
    result["PYTHONUTF8"] = "1"
    return result


def write_configuration(directory, password=PASSWORD):
    (directory / ".env").write_text(
        f"GEOPOL_DATABASE_URL=sqlite:///{(directory / 'synthetic.db').as_posix()}\n"
        f"GEOPOL_STORAGE_PATH={(directory / 'storage').as_posix()}\n"
        f"GEOPOL_BOOTSTRAP_PASSWORD={password}\n",
        encoding="utf-8",
    )


def available_port():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def request(port, path, payload=None, token=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(payload).encode() if payload is not None else None
    call = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=data, headers=headers)
    with urllib.request.urlopen(call, timeout=2) as response:
        return json.load(response)


def wait_until(check, timeout=30):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            result = check()
            if result:
                return result
        except (OSError, urllib.error.URLError, sqlite3.Error):
            pass
        time.sleep(0.1)
    raise AssertionError("The temporary development server did not reach the expected state")


def pid_running(pid):
    if os.name == "nt":
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
        kernel.OpenProcess.restype = ctypes.c_void_p
        kernel.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
        kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        handle = kernel.OpenProcess(0x00100000, False, pid)
        if not handle:
            return False
        try:
            return kernel.WaitForSingleObject(handle, 0) == 258
        finally:
            kernel.CloseHandle(handle)
    state = Path(f"/proc/{pid}/status")
    if state.exists() and "State:\tZ" in state.read_text():
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False


def worker_pid(directory):
    with sqlite3.connect(directory / "synthetic.db") as connection:
        row = connection.execute("SELECT id FROM heartbeats ORDER BY seen_at DESC LIMIT 1").fetchone()
        return int(row[0].rsplit(":", 1)[1]) if row else None


@contextlib.contextmanager
def running_server(directory, port):
    with (directory / f"server-{port}.log").open("wb") as output:
        process = subprocess.Popen(
            [sys.executable, "-m", "geopol.dev", "--port", str(port)],
            cwd=directory,
            env=environment(),
            stdin=subprocess.DEVNULL,
            stdout=output,
            stderr=subprocess.STDOUT,
        )
        try:

            def health():
                assert process.poll() is None, (directory / f"server-{port}.log").read_text(encoding="utf-8")
                return request(port, "/api/health")

            wait_until(health)
            yield process
        finally:
            if process.poll() is None:
                process.terminate()
            process.wait(timeout=15)


def run_cli(directory, *arguments):
    if "--port" not in arguments:
        arguments = (*arguments, "--port", str(available_port()))
    return subprocess.run(
        [sys.executable, "-m", "geopol.dev", *arguments],
        cwd=directory,
        env=environment(),
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=20,
    )


def test_missing_explicit_database_never_uses_parent_env_native_config_or_sqlite_default(tmp_path):
    (tmp_path / ".env").write_text("GEOPOL_DATABASE_URL=sqlite:///wrong-parent.db\n")
    backend = tmp_path / "backend"
    backend.mkdir()
    (backend / ".local").mkdir()
    (backend / ".local" / "native.json").write_text('{"database_url": "sqlite:///wrong-native.db"}')

    result = run_cli(backend)

    assert result.returncode == 1
    assert "GEOPOL_DATABASE_URL" in result.stderr
    assert "Traceback" not in result.stderr
    assert not list(tmp_path.rglob("*.db"))


def test_occupied_port_aborts_before_migrating_or_starting_worker(tmp_path):
    write_configuration(tmp_path)
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        result = run_cli(tmp_path, "--port", str(listener.getsockname()[1]))

    assert result.returncode == 1
    assert "puerto" in result.stderr
    assert not (tmp_path / "synthetic.db").exists()


def test_first_login_utf8_password_restart_preserves_account_and_worker_stops(tmp_path):
    write_configuration(tmp_path)
    port = available_port()
    with running_server(tmp_path, port):
        login = request(port, "/api/auth/login", {"username": "administrador", "password": PASSWORD})
        token = login["token"]
        wait_until(lambda: request(port, "/api/health/worker", token=token)["status"] == "ok")
        initial_worker = worker_pid(tmp_path)
        with sqlite3.connect(tmp_path / "synthetic.db") as connection:
            initial_users = connection.execute(
                "SELECT id, username, password_hash, role FROM users"
            ).fetchall()
            assert len(initial_users) == 1
            assert initial_users[0][1] == "administrador"
            assert initial_users[0][3] == "admin"
            assert len(connection.execute("SELECT version FROM schema_versions").fetchall()) >= 6

    wait_until(lambda: not pid_running(initial_worker))
    # Even an unusable new bootstrap password cannot reset an existing account.
    write_configuration(tmp_path, password="short")
    with running_server(tmp_path, port):
        login = request(port, "/api/auth/login", {"username": "administrador", "password": PASSWORD})
        wait_until(lambda: request(port, "/api/health/worker", token=login["token"])["status"] == "ok")
        final_worker = wait_until(
            lambda: (pid := worker_pid(tmp_path)) and pid != initial_worker and pid_running(pid) and pid
        )
        with sqlite3.connect(tmp_path / "synthetic.db") as connection:
            assert (
                connection.execute("SELECT id, username, password_hash, role FROM users").fetchall()
                == initial_users
            )
    wait_until(lambda: not pid_running(final_worker))


def test_worker_exits_if_parent_is_killed_without_cleanup(tmp_path):
    write_configuration(tmp_path)
    with running_server(tmp_path, available_port()) as process:
        pid = wait_until(lambda: worker_pid(tmp_path))
        assert pid_running(pid)
        process.kill()
        process.wait(timeout=10)
        wait_until(lambda: not pid_running(pid))


def test_worker_failure_stops_api(tmp_path):
    write_configuration(tmp_path)
    with running_server(tmp_path, available_port()) as process:
        pid = wait_until(lambda: worker_pid(tmp_path))
        if os.name == "nt":
            kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
            kernel.OpenProcess.restype = ctypes.c_void_p
            kernel.TerminateProcess.argtypes = [ctypes.c_void_p, ctypes.c_uint]
            kernel.CloseHandle.argtypes = [ctypes.c_void_p]
            handle = kernel.OpenProcess(1, False, pid)
            assert handle
            try:
                assert kernel.TerminateProcess(handle, 1)
            finally:
                kernel.CloseHandle(handle)
        else:
            os.kill(pid, signal.SIGKILL)
        assert process.wait(timeout=15) == 1


@pytest.mark.skipif(os.name == "nt", reason="Windows uses the parent-death pipe; POSIX signals tested on CI")
@pytest.mark.parametrize("kind", [signal.SIGTERM, signal.SIGINT])
def test_signals_gracefully_stop_api_and_worker(tmp_path, kind):
    write_configuration(tmp_path)
    with running_server(tmp_path, available_port()) as process:
        pid = wait_until(lambda: worker_pid(tmp_path))
        process.send_signal(kind)
        assert process.wait(timeout=15) == 0
        wait_until(lambda: not pid_running(pid))
    with sqlite3.connect(tmp_path / "synthetic.db") as connection:
        assert connection.execute("SELECT count(*) FROM heartbeats").fetchone()[0] == 0


@pytest.mark.parametrize("bootstrap", [None, ""])
def test_masked_password_unavailable_fails_without_echo_or_worker(tmp_path, bootstrap):
    write_configuration(tmp_path)
    path = tmp_path / ".env"
    path.write_text("\n".join(path.read_text(encoding="utf-8").splitlines()[:-1]), encoding="utf-8")
    if bootstrap is not None:
        with path.open("a", encoding="utf-8") as target:
            target.write(f"\nGEOPOL_BOOTSTRAP_PASSWORD={bootstrap}\n")

    result = run_cli(tmp_path)

    assert result.returncode != 0
    assert "GEOPOL_BOOTSTRAP_PASSWORD" in result.stderr
    assert "echoed" not in result.stderr
    assert "Worker iniciado" not in result.stdout


def test_configuration_errors_do_not_expose_database_credentials(tmp_path):
    (tmp_path / ".env").write_text("GEOPOL_DATABASE_URL=unsupported://private-password@invalid/database\n")
    result = run_cli(tmp_path)
    assert result.returncode == 1
    assert "private-password" not in result.stdout + result.stderr
    assert "Traceback" not in result.stderr


def test_server_exception_cancels_monitor():
    class BrokenServer:
        should_exit = False

        async def serve(self, **_):
            raise RuntimeError("synthetic startup failure")

    with pytest.raises(RuntimeError, match="synthetic startup failure"):
        asyncio.run(dev.serve(BrokenServer(), Mock(), SimpleNamespace(is_alive=lambda: True)))


def postgres_connection(extensions=("postgis", "pg_trgm"), locked=True):
    connection = MagicMock()
    connection.scalars.return_value = extensions
    connection.scalar.return_value = locked
    engine = SimpleNamespace(dialect=SimpleNamespace(name="postgresql"), connect=MagicMock())
    engine.connect.return_value.__enter__.return_value = connection
    return engine, connection


def test_missing_postgis_is_explained_without_creating_extensions():
    engine, connection = postgres_connection(extensions=("pg_trgm",))
    with pytest.raises(dev.DevelopmentError, match="postgis y pg_trgm"):
        with dev.database_guard(engine):
            pytest.fail("Must not start or migrate the application")
    connection.scalar.assert_not_called()
    connection.execute.assert_not_called()


def test_postgres_guard_prevents_second_worker_and_releases_own_lock_on_error():
    engine, connection = postgres_connection(locked=False)
    with pytest.raises(dev.DevelopmentError, match="otra ejecución"):
        with dev.database_guard(engine):
            pytest.fail("Must not start another worker")
    connection.execute.assert_not_called()

    engine, connection = postgres_connection()
    with pytest.raises(ValueError, match="synthetic failure"):
        with dev.database_guard(engine):
            raise ValueError("synthetic failure")
    assert "pg_advisory_unlock" in str(connection.execute.call_args.args[0])
