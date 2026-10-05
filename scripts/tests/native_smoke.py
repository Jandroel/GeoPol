"""Exercise the documented native installation on a disposable Ubuntu CI runner."""

import json
import os
import secrets
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PYTHON = ROOT / "backend/.venv/bin/python"


def main():
    if os.environ.get("GITHUB_ACTIONS") != "true":
        raise SystemExit("Run this smoke only on the disposable GitHub Actions runner.")
    os.chdir(ROOT)
    config_file = Path(".local/native.json")
    assert not config_file.exists() and not Path(".env").exists()
    legacy = "GEOPOL_DATABASE_URL=sqlite:///data/must-not-be-created.db\n"
    Path(".env").write_text(legacy, encoding="utf-8")
    password = secrets.token_urlsafe(24)
    env = {**os.environ, "GEOPOL_BOOTSTRAP_PASSWORD": password}
    subprocess.run(["bash", "instalar.sh"], env=env, check=True, timeout=900)
    before = config_file.read_bytes()
    config = json.loads(before)
    assert os.environ["GEOPOL_SETUP_PGPASSWORD"] not in config["database_url"]
    assert not Path("data/must-not-be-created.db").exists()
    env.pop("GEOPOL_BOOTSTRAP_PASSWORD")
    env.pop("GEOPOL_SETUP_PGPASSWORD")
    url = f"http://127.0.0.1:{config['web_port']}"
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def healthy():
        try:
            with opener.open(url + "/api/health", timeout=2) as response:
                data = json.load(response)
                return data["status"] == "ok" and data["schema_version"] == 6
        except (OSError, urllib.error.URLError):
            return False

    def login_and_worker():
        request = urllib.request.Request(
            url + "/api/auth/login",
            data=json.dumps(
                {"username": "administrador", "password": password}
            ).encode(),
            headers={"Content-Type": "application/json"},
        )
        with opener.open(request, timeout=10) as response:
            token = json.load(response)["token"]
        request = urllib.request.Request(
            url + "/api/health/worker", headers={"Authorization": "Bearer " + token}
        )
        with opener.open(request, timeout=10) as response:
            assert json.load(response)["status"] == "ok"

    marker = Path(config["storage_path"]) / "native-smoke.txt"
    for attempt in range(2):
        with Path(f".local/native-smoke-{attempt}.log").open("wb") as log:
            process = subprocess.Popen(
                ["bash", "iniciar.sh"],
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
            )
            try:
                deadline = time.monotonic() + 60
                while not healthy():
                    assert process.poll() is None, (
                        "The native launcher exited before readiness"
                    )
                    assert time.monotonic() < deadline, (
                        "The native app did not become ready"
                    )
                    time.sleep(0.3)
                login_and_worker()
                if attempt == 0:
                    marker.write_text("synthetic persisted file", encoding="utf-8")
                else:
                    assert (
                        marker.read_text(encoding="utf-8") == "synthetic persisted file"
                    )
            finally:
                subprocess.run(["bash", "detener.sh"], env=env, check=True, timeout=40)
                process.wait(timeout=20)
            assert process.returncode == 0
    assert config_file.read_bytes() == before
    assert Path(".env").read_text(encoding="utf-8") == legacy
    subprocess.run(
        [PYTHON, "scripts/configure_postgres.py"], env=env, check=True, timeout=20
    )
    assert config_file.read_bytes() == before
    # Exercise the limited application role, not the PostgreSQL administrator.
    subprocess.run(
        [
            PYTHON,
            "-c",
            (
                "import json, os; from pathlib import Path; "
                "c=json.loads(Path('.local/native.json').read_text()); "
                "os.environ['GEOPOL_DATABASE_URL']=c['database_url']; "
                "from geopol.db import SessionLocal; from sqlalchemy import text; "
                "db=SessionLocal(); assert db.scalar(text('SELECT count(*) FROM users')) == 1; "
                "assert db.scalar(text('SELECT PostGIS_Version()')); "
                "assert tuple(db.execute(text('SELECT rolsuper, rolcreatedb, rolcreaterole FROM pg_roles "
                "WHERE rolname=current_user')).one()) == (False, False, False); db.close()"
            ),
        ],
        env=env,
        check=True,
    )
    print(
        "Native smoke passed: Bash install, PostgreSQL/PostGIS, limited role, login, restart and persistence."
    )


if __name__ == "__main__":
    main()
