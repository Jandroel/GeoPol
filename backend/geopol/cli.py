import argparse
import getpass
import os

from sqlalchemy import select, text

from .db import SessionLocal, engine
from .migrations import SCHEMA_VERSION, migrate
from .models import User
from .security import password_hash


def main(argv=None):
    parser = argparse.ArgumentParser(description="Administración local de GeoPol")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("init-db", help="Aplicar migraciones pendientes")
    user = commands.add_parser(
        "create-user", help="Crear un usuario; contraseña por prompt o variable de entorno"
    )
    user.add_argument("--username", required=True)
    user.add_argument("--role", choices=["admin", "operator", "reviewer", "analyst"], required=True)
    user.add_argument("--password-env", default="GEOPOL_BOOTSTRAP_PASSWORD")
    bootstrap = commands.add_parser(
        "bootstrap-user", help="Crear el administrador inicial únicamente cuando no exista ningún usuario"
    )
    bootstrap.add_argument("--username", default="administrador")
    bootstrap.add_argument("--password-env", default="GEOPOL_BOOTSTRAP_PASSWORD")
    bootstrap.set_defaults(role="admin")
    args = parser.parse_args(argv)
    if args.command == "init-db":
        migrate(engine)
        print(f"Base de datos actualizada (versión {SCHEMA_VERSION}).")
        return
    initial_user = args.command == "bootstrap-user"
    skipped_message = "Ya existen usuarios; no se crearon ni modificaron cuentas."
    if initial_user:
        with SessionLocal() as db:
            if db.scalar(select(User.id).limit(1)) is not None:
                print(skipped_message)
                return
    args.username = args.username.strip()
    if not args.username or len(args.username) > 100:
        parser.error("El nombre de usuario debe tener entre 1 y 100 caracteres")
    try:
        password = os.environ.get(args.password_env) or getpass.getpass(
            "Contraseña (mínimo 12 caracteres): "
        )
        encoded_password = password_hash(password)
    except ValueError as error:
        parser.error(str(error))
    except EOFError:
        parser.error(f"No se recibió una contraseña; use una terminal interactiva o {args.password_env}")
    with SessionLocal() as db:
        if initial_user:
            # Another installer or operator may have created a user while the
            # password prompt was open. Serialize the final check and insert.
            dialect = db.get_bind().dialect.name
            if dialect == "sqlite":
                db.execute(text("BEGIN IMMEDIATE"))
            elif dialect == "postgresql":
                db.execute(text("LOCK TABLE users IN SHARE ROW EXCLUSIVE MODE"))
            if db.scalar(select(User.id).limit(1)) is not None:
                print(skipped_message)
                return
        elif db.scalar(select(User).where(User.username == args.username)):
            parser.error("El usuario ya existe; no se modificó su contraseña")
        db.add(User(username=args.username, password_hash=encoded_password, role=args.role))
        db.commit()
    print(f"Administrador inicial creado: {args.username}." if initial_user else "Usuario creado.")


if __name__ == "__main__":
    main()
