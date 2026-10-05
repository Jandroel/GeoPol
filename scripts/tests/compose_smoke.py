"""Full Bash/PostgreSQL smoke for the disposable GitHub Actions runner only."""

import json
import os
import secrets
import subprocess
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main():
    if os.environ.get("GITHUB_ACTIONS") != "true":
        raise SystemExit("Run this smoke only on the disposable GitHub Actions runner.")
    os.chdir(ROOT)
    assert not Path(".local/compose.env").exists(), "A fresh installation is required"
    password = secrets.token_urlsafe(24)
    subprocess.run(
        ["bash", "instalar.sh"],
        input=f"{password}\n{password}\n",
        text=True,
        check=True,
        timeout=900,
    )
    config_before = Path(".local/compose.env").read_bytes()
    compose = [
        "docker",
        "compose",
        "-p",
        "geopol-local",
        "--env-file",
        ".local/compose.env",
        "-f",
        "compose.yaml",
    ]
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def login_and_health():
        with opener.open("http://localhost:8080/api/health", timeout=10) as response:
            health = json.load(response)
            assert health["database"] == "ok"
            assert health["schema_version"] == 6
        request = urllib.request.Request(
            "http://localhost:8080/api/auth/login",
            data=json.dumps(
                {"username": "administrador", "password": password}
            ).encode(),
            headers={"Content-Type": "application/json"},
        )
        with opener.open(request, timeout=10) as response:
            token = json.load(response)["token"]
        request = urllib.request.Request(
            "http://localhost:8080/api/health/worker",
            headers={"Authorization": "Bearer " + token},
        )
        with opener.open(request, timeout=10) as response:
            assert json.load(response)["status"] == "ok"

    login_and_health()
    subprocess.run(
        [
            *compose,
            "exec",
            "-T",
            "api",
            "python",
            "-c",
            "from pathlib import Path; Path('/app/data/storage/bash-smoke.txt').write_text('synthetic')",
        ],
        check=True,
    )
    subprocess.run(["bash", "detener.sh"], check=True, timeout=90)
    subprocess.run(["bash", "iniciar.sh"], input="", text=True, check=True, timeout=240)
    login_and_health()
    assert Path(".local/compose.env").read_bytes() == config_before
    subprocess.run(
        [
            *compose,
            "exec",
            "-T",
            "api",
            "python",
            "-c",
            (
                "from pathlib import Path; from geopol.db import SessionLocal; "
                "from geopol.models import User; from sqlalchemy import select, func, text; "
                "db=SessionLocal(); assert db.scalar(select(func.count()).select_from(User)) == 1; "
                "assert db.scalar(text('SELECT PostGIS_Version()')); "
                "assert Path('/app/data/storage/bash-smoke.txt').read_text() == 'synthetic'; db.close()"
            ),
        ],
        check=True,
    )
    print(
        "Bash/PostgreSQL smoke passed: login, worker, PostGIS, account and file persistence."
    )


if __name__ == "__main__":
    main()
