"""Prepare an isolated native PostgreSQL database without changing existing data.

Only GEOPOL_SETUP_PGPASSWORD or a masked terminal prompt supplies the administrator
password. Neither PostgreSQL errors nor connection strings are printed because
they can contain secrets. The application uses its own generated login.
"""

from __future__ import annotations

import argparse
import csv
import getpass
import json
import os
import re
import secrets
import subprocess
import sys
import tempfile
import warnings
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit

import psycopg
from psycopg import sql

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / ".local" / "native.json"
REQUIRED_EXTENSIONS = {"postgis", "pg_trgm"}
DATABASE_NAME = re.compile(r"[a-z][a-z0-9_]{0,49}\Z")


class SetupError(Exception):
    """An actionable error that is safe to show without leaking credentials."""


def _port(value, label):
    try:
        port = int(value)
    except (TypeError, ValueError):
        raise SetupError(f"{label}: usa un número entre 1 y 65535.") from None
    if isinstance(value, bool) or not 1 <= port <= 65535:
        raise SetupError(f"{label}: usa un número entre 1 y 65535.")
    return port


def _read_json(path):
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise SetupError(
            f"No se pudo leer la configuración {path}. Consérvala para recuperar la instalación."
        ) from None
    if not isinstance(value, dict):
        raise SetupError(f"La configuración {path} no es un objeto JSON válido.")
    return value


def _connection_parameters(database_url):
    try:
        parsed = urlsplit(database_url)
        if (
            parsed.scheme not in {"postgresql+psycopg", "postgresql"}
            or not parsed.hostname
            or not parsed.username
            or not parsed.password
            or not parsed.path.strip("/")
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError
        return {
            "host": parsed.hostname,
            "port": parsed.port or 5432,
            "dbname": unquote(parsed.path[1:]),
            "user": unquote(parsed.username),
            "password": unquote(parsed.password),
        }
    except (TypeError, ValueError, AttributeError):
        raise SetupError(
            "La configuración necesita una URL PostgreSQL válida con el usuario de GeoPol."
        ) from None


def _validate_config(config):
    _connection_parameters(config.get("database_url"))
    storage = config.get("storage_path")
    if not isinstance(storage, str) or not Path(storage).is_absolute():
        raise SetupError(
            "storage_path debe ser una ruta absoluta en la configuración nativa."
        )
    for key in ("web_port", "api_port"):
        _port(config.get(key), key)
    if config["web_port"] == config["api_port"]:
        raise SetupError("Los puertos web y API deben ser distintos.")
    return config


def load_config(path=DEFAULT_CONFIG):
    """Read the private native configuration without consulting .env or SQLite."""
    return _validate_config(_read_json(path))


def _restrict_file(path):
    """Restrict Windows ACLs too: chmod(0600) alone does not do that on NTFS."""
    if os.name != "nt":
        os.chmod(path, 0o600)
        return
    system32 = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32"
    options = {
        "capture_output": True,
        "text": True,
        "creationflags": subprocess.CREATE_NO_WINDOW,
    }
    try:
        identity = subprocess.run(
            [str(system32 / "whoami.exe"), "/user", "/fo", "csv", "/nh"],
            check=True,
            **options,
        )
        sid = next(csv.reader(identity.stdout.strip().splitlines()))[1]
        if not re.fullmatch(r"S-1-[0-9-]+", sid):
            raise ValueError
        subprocess.run(
            [
                str(system32 / "icacls.exe"),
                str(path),
                "/inheritance:r",
                "/grant:r",
                f"*{sid}:(F)",
            ],
            check=True,
            **options,
        )
    except (OSError, subprocess.SubprocessError, ValueError, IndexError, StopIteration):
        raise SetupError(
            "No se pudieron proteger las credenciales locales con los permisos de Windows."
        ) from None


def _write_json(path, value, *, exclusive=False):
    """Write before database mutations, allowing access only to the current user."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = None
    created = False
    try:
        if exclusive:
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            created = True
        else:
            descriptor, name = tempfile.mkstemp(
                prefix=f".{path.name}.", dir=path.parent
            )
            temporary = Path(name)
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            _restrict_file(path if exclusive else temporary)
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        if temporary is not None:
            os.replace(temporary, path)
    except FileExistsError:
        raise SetupError(
            "Ya hay una configuración pendiente. Vuelve a ejecutar el instalador para retomarla."
        ) from None
    except (OSError, SetupError) as error:
        # No PostgreSQL mutation has begun if the initial pending write fails.
        if created:
            path.unlink(missing_ok=True)
        if isinstance(error, SetupError):
            raise
        raise SetupError(
            f"No se pudo guardar la configuración privada en {path}. Revisa los permisos."
        ) from None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _ask(environ, variable, prompt, default, input_fn):
    if variable in environ:
        return environ[variable].strip() or default
    return input_fn(f"{prompt} [{default}]: ").strip() or default


def _admin_password(environ, password_fn):
    if "GEOPOL_SETUP_PGPASSWORD" in environ:
        return environ["GEOPOL_SETUP_PGPASSWORD"]
    # getpass normally falls back to echoing input when no terminal is present.
    # Stop that fallback before it can expose a password.
    with warnings.catch_warnings():
        warnings.simplefilter("error", getpass.GetPassWarning)
        try:
            return password_fn(
                "Contraseña del administrador PostgreSQL (no se mostrará): "
            )
        except getpass.GetPassWarning:
            raise SetupError(
                "No hay una terminal para ocultar la contraseña. Ejecuta instalar.sh en una terminal "
                "o proporciona GEOPOL_SETUP_PGPASSWORD en el entorno."
            ) from None


def _require_version(connection):
    if connection.info.server_version < 160000:
        raise SetupError(
            "GeoPol necesita PostgreSQL 16 o posterior y PostGIS instalado para esa versión."
        )


def _extensions(connection, *, available=False):
    query = (
        "SELECT name FROM pg_available_extensions"
        if available
        else "SELECT extname FROM pg_extension"
    )
    found = {row[0] for row in connection.execute(query).fetchall()}
    missing = REQUIRED_EXTENSIONS - found
    if missing:
        if available:
            raise SetupError(
                "Faltan extensiones de PostgreSQL: "
                + ", ".join(sorted(missing))
                + ". Instala PostGIS y las extensiones contrib para tu PostgreSQL y vuelve a ejecutar instalar.sh."
            )
        raise SetupError(
            "La base configurada no tiene las extensiones: "
            + ", ".join(sorted(missing))
            + ". Pide al administrador habilitarlas en esta base; las credenciales y los datos se conservaron."
        )


def _connect(connect, parameters):
    return connect(**parameters, connect_timeout=5, autocommit=True)


def validate_database(config, *, connect=None):
    """Check connectivity, PostgreSQL version and extensions, without any DDL."""
    connect = connect or psycopg.connect
    with _connect(
        connect, _connection_parameters(config["database_url"])
    ) as connection:
        _require_version(connection)
        _extensions(connection)


def _database_owner(connection, name):
    row = connection.execute(
        "SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname = %s", (name,)
    ).fetchone()
    return row[0] if row else None


def _role_marker(connection, name):
    row = connection.execute(
        "SELECT shobj_description(oid, 'pg_authid') FROM pg_roles WHERE rolname = %s",
        (name,),
    ).fetchone()
    return (row is not None, row[0] if row else None)


def _collision(name):
    raise SetupError(
        f"La base o el rol para '{name}' ya existe sin pertenecer a esta instalación. "
        "No se modificó. Elige otro nombre de base nueva."
    )


def _prepare_database(connection, pending):
    parameters = _connection_parameters(pending["config"]["database_url"])
    name, role = parameters["dbname"], parameters["user"]
    owner = _database_owner(connection, name)
    role_exists, marker = _role_marker(connection, role)
    if (role_exists and marker != pending["marker"]) or (
        owner is not None and owner != role
    ):
        _collision(name)
    if owner is not None and not role_exists:
        _collision(name)
    if not role_exists:
        # Role creation and ownership marker commit together, so an interrupted
        # retry can never claim an unrelated login or reset its password.
        with connection.transaction():
            connection.execute(
                sql.SQL(
                    "CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION PASSWORD {}"
                ).format(sql.Identifier(role), sql.Literal(parameters["password"]))
            )
            connection.execute(
                sql.SQL("COMMENT ON ROLE {} IS {}").format(
                    sql.Identifier(role), sql.Literal(pending["marker"])
                )
            )
    if owner is None:
        # CREATE DATABASE cannot run in a transaction. Its unique, marked owner
        # identifies our database even if the process stops immediately after it.
        connection.execute(
            sql.SQL(
                "CREATE DATABASE {} OWNER {} TEMPLATE template0 ENCODING 'UTF8'"
            ).format(sql.Identifier(name), sql.Identifier(role))
        )


def _load_pending(path):
    pending = _read_json(path)
    try:
        _validate_config(pending["config"])
        marker = pending["marker"]
        parameters = _connection_parameters(pending["config"]["database_url"])
        if (
            not isinstance(marker, str)
            or not re.fullmatch(r"geopol-native:[0-9a-f]{32}", marker)
            or not DATABASE_NAME.fullmatch(parameters["dbname"])
            or parameters["user"] != parameters["dbname"] + "_app"
            or not isinstance(pending["admin_user"], str)
        ):
            raise ValueError
    except (KeyError, TypeError, ValueError):
        raise SetupError(
            f"La configuración pendiente {path} no es válida. Consérvala para recuperar la instalación."
        ) from None
    return pending


def _postgres_error(error):
    state = getattr(error, "sqlstate", None)
    description = str(error).lower()  # Classify only; never print server-supplied text.
    if (
        state == "28P01"
        or "password authentication failed" in description
        or "autenticación password" in description
    ):
        return SetupError(
            "PostgreSQL rechazó las credenciales. Revisa el usuario y la contraseña del administrador o de la configuración guardada."
        )
    if state in {"42710", "42P04"}:
        return SetupError(
            "El nombre de base o rol ya está ocupado. No se reemplazó ni se cambió su contraseña; elige otro nombre."
        )
    if state == "42501":
        return SetupError(
            "El usuario PostgreSQL no tiene permisos suficientes. Usa un administrador para crear la base, su rol y PostGIS."
        )
    if state in {"0A000", "58P01"} or "postgis" in description:
        return SetupError(
            "No se pudo habilitar PostGIS. Instálalo para la versión activa de PostgreSQL y repite instalar.sh; se conservará la instalación pendiente."
        )
    return SetupError(
        "No se pudo completar la conexión/configuración de PostgreSQL. Comprueba que el servicio esté iniciado, "
        "el host y puerto sean correctos y las credenciales sean válidas. Vuelve a ejecutar instalar.sh; "
        "las credenciales guardadas y los datos se conservaron."
    )


def configure(
    path=DEFAULT_CONFIG,
    *,
    web_port=None,
    api_port=None,
    environ=None,
    input_fn=None,
    password_fn=None,
    connect=None,
):
    """Provision a new database, or verify/resume exactly this installation."""
    path = Path(path)
    pending_path = path.with_name(path.stem + ".pending" + path.suffix)
    environ = os.environ if environ is None else environ
    input_fn = input if input_fn is None else input_fn
    password_fn = getpass.getpass if password_fn is None else password_fn
    connect = connect or psycopg.connect
    try:
        if path.exists():
            config = load_config(path)
            validate_database(config, connect=connect)
            updated = dict(config)
            if web_port is not None:
                updated["web_port"] = _port(web_port, "Puerto web")
            if api_port is not None:
                updated["api_port"] = _port(api_port, "Puerto API")
            _validate_config(updated)
            if updated != config:
                _write_json(path, updated)
            return updated

        pending = _load_pending(pending_path) if pending_path.exists() else None
        if pending:
            parameters = _connection_parameters(pending["config"]["database_url"])
            host, port, name = (
                parameters["host"],
                parameters["port"],
                parameters["dbname"],
            )
            admin_default = pending["admin_user"]
        else:
            host = _ask(
                environ, "GEOPOL_SETUP_PGHOST", "Host PostgreSQL", "127.0.0.1", input_fn
            )
            port = _port(
                _ask(
                    environ,
                    "GEOPOL_SETUP_PGPORT",
                    "Puerto PostgreSQL",
                    "5432",
                    input_fn,
                ),
                "Puerto PostgreSQL",
            )
            name = _ask(
                environ,
                "GEOPOL_SETUP_PGDATABASE",
                "Nombre de una base NUEVA para GeoPol",
                "geopol",
                input_fn,
            )
            if not DATABASE_NAME.fullmatch(name):
                raise SetupError(
                    "Usa un nombre de base de hasta 50 caracteres: letras minúsculas, números y guion bajo, empezando por letra."
                )
            if (
                not host
                or any(character.isspace() for character in host)
                or any(c in host for c in "/@?#")
            ):
                raise SetupError(
                    "Usa un host PostgreSQL válido, por ejemplo 127.0.0.1."
                )
            admin_default = "postgres"
        admin_user = _ask(
            environ,
            "GEOPOL_SETUP_PGUSER",
            "Usuario administrador PostgreSQL",
            admin_default,
            input_fn,
        )
        password = _admin_password(environ, password_fn)
        admin = {
            "host": host,
            "port": port,
            "dbname": "postgres",
            "user": admin_user,
            "password": password,
        }
        with _connect(connect, admin) as connection:
            _require_version(connection)
            _extensions(connection, available=True)
            if pending is None:
                role = name + "_app"
                if (
                    _database_owner(connection, name) is not None
                    or _role_marker(connection, role)[0]
                ):
                    _collision(name)
                application_password = secrets.token_urlsafe(32)
                url_host = (
                    f"[{host}]" if ":" in host and not host.startswith("[") else host
                )
                config = {
                    "database_url": f"postgresql+psycopg://{quote(role, safe='')}:{quote(application_password, safe='')}@{url_host}:{port}/{quote(name, safe='')}",
                    "storage_path": str((ROOT / "data" / "storage-native").resolve()),
                    "web_port": _port(
                        5173 if web_port is None else web_port, "Puerto web"
                    ),
                    "api_port": _port(
                        8000 if api_port is None else api_port, "Puerto API"
                    ),
                }
                _validate_config(config)
                pending = {
                    "config": config,
                    "marker": "geopol-native:" + secrets.token_hex(16),
                    "admin_user": admin_user,
                }
                _write_json(pending_path, pending, exclusive=True)
            _prepare_database(connection, pending)
        admin["dbname"] = name
        with _connect(connect, admin) as connection, connection.transaction():
            for extension in sorted(REQUIRED_EXTENSIONS):
                connection.execute(
                    sql.SQL(
                        "CREATE EXTENSION IF NOT EXISTS {} WITH SCHEMA public"
                    ).format(sql.Identifier(extension))
                )
        config = pending["config"]
        if web_port is not None:
            config["web_port"] = _port(web_port, "Puerto web")
        if api_port is not None:
            config["api_port"] = _port(api_port, "Puerto API")
        _validate_config(config)
        validate_database(config, connect=connect)
        Path(config["storage_path"]).mkdir(parents=True, exist_ok=True)
        _write_json(path, config)
        pending_path.unlink()
        return config
    except psycopg.Error as error:
        raise _postgres_error(error) from None


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Configura PostgreSQL local para GeoPol sin modificar bases existentes."
    )
    parser.add_argument(
        "--config", type=Path, default=DEFAULT_CONFIG, help=argparse.SUPPRESS
    )
    parser.add_argument(
        "--web-port", type=int, help="Puerto de la web (primera instalación: 5173)"
    )
    parser.add_argument(
        "--api-port", type=int, help="Puerto de la API (primera instalación: 8000)"
    )
    args = parser.parse_args(argv)
    try:
        configure(args.config, web_port=args.web_port, api_port=args.api_port)
    except (SetupError, OSError, EOFError) as error:
        message = (
            str(error)
            if isinstance(error, SetupError)
            else "No se pudo completar la configuración. Revisa los permisos y ejecuta instalar.sh en una terminal."
        )
        print(f"ERROR: {message}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print(
            "\nConfiguración interrumpida. Puedes repetir instalar.sh para continuar.",
            file=sys.stderr,
        )
        return 130
    print("PostgreSQL y PostGIS verificados. Configuración privada de GeoPol lista.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
