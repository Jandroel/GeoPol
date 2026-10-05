"""Portable launcher checks; only temporary files, SQLite data, and free ports."""

import contextlib
import json
import os
import secrets
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
PYTHON = ROOT / ("backend/.venv/Scripts/python.exe" if os.name == "nt" else "backend/.venv/bin/python")
sys.path.insert(0, str(ROOT / "scripts"))
import run_local


def free_port():
    with socket.socket() as sock:
        if os.name == "nt":
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
    if not PYTHON.is_file() or not (ROOT / "frontend/dist/index.html").is_file():
        pytest.skip("Install backend dependencies and build the frontend for lifecycle checks")
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
        if os.name == "nt":
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


@pytest.fixture
def native_config(tmp_path, monkeypatch):
    monkeypatch.setattr(run_local, "ROOT", tmp_path)
    for name in ("GEOPOL_DATABASE_URL", "GEOPOL_STORAGE_PATH", "GEOPOL_ALLOWED_ORIGINS"):
        monkeypatch.setenv(name, "previous-value")
    config = {
        "database_url": "postgresql+psycopg://test_user:synthetic-password@127.0.0.1/geopol_test",
        "storage_path": "data with spaces/storage",
        "api_port": 8800,
        "web_port": 5517,
    }
    config_path = tmp_path / ".local/native.json"
    config_path.parent.mkdir()
    config_path.write_text(json.dumps(config), encoding="utf-8")
    return config_path, config


def arguments(**overrides):
    return SimpleNamespace(
        **({"native": True, "api_port": None, "port": None, "runtime_dir": None} | overrides)
    )


def test_native_settings_replace_inherited_database_before_startup(native_config):
    config_path, config = native_config
    args = arguments()
    run_local.configure(args)
    assert os.environ["GEOPOL_DATABASE_URL"] == config["database_url"]
    assert os.environ["GEOPOL_STORAGE_PATH"] == str(
        (config_path.parents[1] / config["storage_path"]).resolve()
    )
    assert os.environ["GEOPOL_ALLOWED_ORIGINS"] == "http://localhost:5517,http://127.0.0.1:5517"
    assert (args.api_port, args.port) == (8800, 5517)
    assert args.runtime_dir == config_path.parent / "native-runtime"


def test_native_explicit_ports_override_saved_ports(native_config):
    args = arguments()
    args.api_port, args.port = 8100, 5200
    run_local.configure(args)
    assert (args.api_port, args.port) == (8100, 5200)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("database_url", "sqlite:///operational.db"),
        ("database_url", "postgresql://localhost/geopol"),
        ("storage_path", ""),
        ("api_port", 0),
        ("web_port", 65536),
        ("web_port", True),
        ("web_port", "5173"),
        ("web_port", 8800),
    ],
)
def test_native_invalid_config_is_rejected(native_config, field, value):
    path, config = native_config
    config[field] = value
    path.write_text(json.dumps(config), encoding="utf-8")
    with pytest.raises(run_local.StartupError):
        run_local.configure(arguments())


def test_missing_native_config_has_bash_install_instruction(tmp_path, monkeypatch):
    monkeypatch.setattr(run_local, "ROOT", tmp_path)
    with pytest.raises(run_local.StartupError, match="bash instalar.sh"):
        run_local.configure(arguments())


def test_legacy_defaults_keep_environment_and_runtime(native_config):
    args = arguments()
    args.native = False
    run_local.configure(args)
    assert (args.api_port, args.port) == (8000, 5173)
    assert args.runtime_dir == native_config[0].parent / "runtime"
    assert os.environ["GEOPOL_DATABASE_URL"] == "previous-value"


def test_stop_request_waits_for_owning_supervisor_to_release_lock(tmp_path):
    runtime = tmp_path / "native runtime"
    ready = tmp_path / "ready"
    entry = (
        "import sys, time; from pathlib import Path; "
        "sys.path.insert(0, sys.argv[1]); from run_local import single_launcher\n"
        "runtime = Path(sys.argv[2])\n"
        "with single_launcher(runtime):\n"
        "    Path(sys.argv[3]).touch()\n"
        "    while not (runtime / 'stop.request').exists():\n"
        "        time.sleep(0.05)\n"
    )
    owner = subprocess.Popen(
        [sys.executable, "-c", entry, str(ROOT / "scripts"), str(runtime), str(ready)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    try:
        wait_until(lambda: ready.is_file() or owner.poll() is not None, timeout=10)
        assert owner.poll() is None, owner.communicate()[0].decode(errors="replace")
        with pytest.raises(run_local.LauncherRunning), run_local.single_launcher(runtime):
            pass
        run_local.request_stop(runtime)
        assert owner.wait(timeout=5) == 0
        assert not (runtime / "stop.request").exists()
        run_local.request_stop(runtime)  # A repeated stop has no process to signal.
    finally:
        if owner.poll() is None:
            owner.kill()
        owner.communicate(timeout=5)


@pytest.mark.skipif(os.name == "nt", reason="POSIX process groups")
def test_posix_scope_stops_owned_descendants_and_preserves_other_processes(tmp_path):
    from posix_processes import PosixProcessScope

    descendant_port = free_port()
    descendant = (
        "import signal,socket,time; "
        "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
        "sock=socket.socket(); "
        f"sock.bind(('127.0.0.1',{descendant_port})); sock.listen(); time.sleep(60)"
    )
    entry = (
        "import subprocess,sys,time; "
        "subprocess.Popen([sys.executable, '-c', sys.argv[1]]); time.sleep(60)"
    )
    witness = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    try:
        scope = PosixProcessScope()
        with pytest.raises(KeyboardInterrupt), scope:
            child = scope.start(
                [sys.executable, "-c", entry, descendant],
                cwd=tmp_path,
                env=os.environ.copy(),
                log_path=tmp_path / "tree.log",
            )
            wait_until(lambda: reachable(descendant_port), timeout=10)
            raise KeyboardInterrupt
        scope.close()
        assert child.poll() is not None
        wait_until(lambda: not reachable(descendant_port), timeout=5)
        assert witness.poll() is None
    finally:
        witness.kill()
        witness.wait(timeout=5)
