import argparse
import getpass
import os

from sqlalchemy import select

from .db import SessionLocal, engine
from .migrations import migrate
from .models import User
from .security import password_hash


def main():
    parser = argparse.ArgumentParser(description="Administración local de GeoPol")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("init-db", help="Aplicar migraciones pendientes")
    user = commands.add_parser(
        "create-user", help="Crear un usuario; contraseña por prompt o variable de entorno"
    )
    user.add_argument("--username", required=True)
    user.add_argument("--role", choices=["admin", "operator", "reviewer", "analyst"], required=True)
    user.add_argument("--password-env", default="GEOPOL_BOOTSTRAP_PASSWORD")
    args = parser.parse_args()
    if args.command == "init-db":
        migrate(engine)
        print("Base de datos actualizada (versión 1).")
        return
    args.username = args.username.strip()
    if not args.username or len(args.username) > 100:
        parser.error("El nombre de usuario debe tener entre 1 y 100 caracteres")
    password = os.environ.get(args.password_env) or getpass.getpass("Contraseña (mínimo 12 caracteres): ")
    with SessionLocal() as db:
        if db.scalar(select(User).where(User.username == args.username)):
            parser.error("El usuario ya existe; no se modificó su contraseña")
        db.add(User(username=args.username, password_hash=password_hash(password), role=args.role))
        db.commit()
    print("Usuario creado.")


if __name__ == "__main__":
    main()
