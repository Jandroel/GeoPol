"""Run maintenance commands against the explicitly configured native database."""

import os
import sys
from pathlib import Path

from configure_postgres import SetupError, load_config

ROOT = Path(__file__).resolve().parents[1]


def main():
    os.chdir(ROOT)
    try:
        config = load_config()
    except (SetupError, OSError, ValueError):
        raise SystemExit("Primero configura PostgreSQL con bash instalar.sh.") from None
    # Set before importing geopol; preserve the unrelated legacy .env file.
    os.environ["GEOPOL_DATABASE_URL"] = config["database_url"]
    os.environ["GEOPOL_STORAGE_PATH"] = config["storage_path"]
    if sys.argv[1:] == ["has-users"]:
        from geopol.db import SessionLocal
        from geopol.models import User
        from sqlalchemy import select

        with SessionLocal() as db:
            print("yes" if db.scalar(select(User.id).limit(1)) else "no")
        return
    if "--password-stdin" in sys.argv:
        sys.argv.remove("--password-stdin")
        # Git Bash writes UTF-8 to the pipe; Windows Python otherwise decodes
        # redirected stdin using the system code page (often cp1252).
        try:
            password = sys.stdin.buffer.read().decode("utf-8")
        except UnicodeDecodeError:
            raise SystemExit("La contraseña recibida debe usar codificación UTF-8.") from None
        os.environ["GEOPOL_BOOTSTRAP_PASSWORD"] = password
    from geopol.cli import main as cli_main

    cli_main()


if __name__ == "__main__":
    main()
