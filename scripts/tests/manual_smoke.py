"""Verify the documented two-terminal workflow on a disposable CI runner."""

import contextlib
import json
import os
import secrets
import signal
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
PYTHON = BACKEND / ".venv/bin/python"


def stop(process):
    if process is None:
        return
    if process.poll() is None:
        process.send_signal(signal.SIGINT)
        try:
            process.wait(timeout=25)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=10)
            raise AssertionError("The development command did not stop on Ctrl+C") from None


def main():
    if os.environ.get("GITHUB_ACTIONS") != "true" or os.name == "nt":
        raise SystemExit("Run this smoke only on the disposable Ubuntu CI runner.")
    os.chdir(ROOT)
    assert not (BACKEND / ".env").exists() and not Path(".env").exists()
    Path(".local").mkdir(exist_ok=True)
    # A legacy root configuration must not replace the file the user edits in backend.
    legacy = "GEOPOL_DATABASE_URL=sqlite:///data/must-not-be-created.db\n"
    Path(".env").write_text(legacy, encoding="utf-8")
    password = "Contraseña-" + secrets.token_urlsafe(20)
    config_file = BACKEND / ".env"
    config_file.write_text(
        "GEOPOL_DATABASE_URL=postgresql+psycopg://geopol_app:synthetic-ci-app-password@127.0.0.1:5432/geopol_manual_ci\n"
        "GEOPOL_STORAGE_PATH=../data/storage\n"
        f"GEOPOL_BOOTSTRAP_PASSWORD={password}\n",
        encoding="utf-8",
    )
    before = config_file.read_bytes()
    environment = {key: value for key, value in os.environ.items() if not key.startswith("GEOPOL_")}
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def request(path, payload=None, token=None):
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = "Bearer " + token
        data = json.dumps(payload).encode() if payload is not None else None
        with opener.open(
            urllib.request.Request("http://127.0.0.1:5173" + path, data=data, headers=headers), timeout=3
        ) as response:
            return json.load(response)

    marker = ROOT / "data/storage/manual-smoke.txt"
    frontend = backend = None
    try:
        with Path(".local/manual-smoke-frontend.log").open("wb") as frontend_log:
            frontend = subprocess.Popen(
                ["npm", "run", "dev", "--", "--port", "5173", "--strictPort"],
                cwd=ROOT / "frontend", env=environment, stdin=subprocess.DEVNULL,
                stdout=frontend_log, stderr=subprocess.STDOUT, start_new_session=True,
            )
            for attempt in range(2):
                with Path(f".local/manual-smoke-backend-{attempt}.log").open("wb") as backend_log:
                    backend = subprocess.Popen(
                        [PYTHON, "-m", "geopol.dev"],
                        cwd=BACKEND, env=environment, stdin=subprocess.DEVNULL,
                        stdout=backend_log, stderr=subprocess.STDOUT, start_new_session=True,
                    )
                    try:
                        deadline = time.monotonic() + 60
                        token = None
                        while True:
                            assert backend.poll() is None and frontend.poll() is None, "A dev process exited"
                            assert time.monotonic() < deadline, "The dev API/worker did not become ready"
                            try:
                                health = request("/api/health")
                                assert health["status"] == "ok" and health["schema_version"] == 6
                                if token is None:
                                    token = request("/api/auth/login", {"username": "administrador", "password": password})["token"]
                                if request("/api/health/worker", token=token)["status"] == "ok":
                                    break
                            except (OSError, urllib.error.URLError, ValueError):
                                pass
                            time.sleep(0.5)
                        if attempt == 0:
                            marker.parent.mkdir(parents=True, exist_ok=True)
                            marker.write_text("synthetic persisted file", encoding="utf-8")
                        else:
                            assert marker.read_text(encoding="utf-8") == "synthetic persisted file"
                    finally:
                        stop(backend)
                    assert backend.returncode == 0
        assert not Path("data/must-not-be-created.db").exists()
        assert not (BACKEND / "data/geopol.db").exists()
        assert not Path(".local/native.json").exists()
        assert config_file.read_bytes() == before
        assert Path(".env").read_text(encoding="utf-8") == legacy
        subprocess.run(
            [PYTHON, "-c", (
                "from geopol.db import SessionLocal; from sqlalchemy import text; "
                "db=SessionLocal(); assert db.scalar(text('SELECT count(*) FROM users')) == 1; "
                "assert db.scalar(text('SELECT count(*) FROM heartbeats')) == 0; "
                "assert db.scalar(text('SELECT PostGIS_Version()')); "
                "assert tuple(db.execute(text('SELECT rolsuper, rolcreatedb, rolcreaterole FROM pg_roles "
                "WHERE rolname=current_user')).one()) == (False, False, False); db.close()"
            )],
            cwd=BACKEND, env=environment, check=True,
        )
        print("Manual smoke passed: backend .env, automatic tables, UTF-8 login, worker, frontend dev and restart.")
    finally:
        stop(backend)
        if frontend is not None:
            # npm owns a separate group; stop only the npm/Vite processes started here.
            with contextlib.suppress(ProcessLookupError):
                os.killpg(frontend.pid, signal.SIGTERM)
            frontend.wait(timeout=10)


if __name__ == "__main__":
    main()
