"""Run the development API and its SQL worker from the backend directory."""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import getpass
import logging
import multiprocessing
import os
import signal
import socket
import sys
import threading
import warnings
from pathlib import Path

from pydantic import Field, SecretStr, ValidationError

from .config import Settings


class DevelopmentError(RuntimeError):
    """A development prerequisite is missing; messages never include secrets."""


class DevelopmentSettings(Settings):
    # Never silently choose the legacy SQLite default for a new installation.
    database_url: str = Field(min_length=1)
    bootstrap_password: SecretStr | None = None


def load_settings():
    try:
        return DevelopmentSettings(_env_file=Path.cwd() / ".env", _env_file_encoding="utf-8")
    except ValidationError:
        raise DevelopmentError(
            "Configura GEOPOL_DATABASE_URL en el archivo .env de esta carpeta "
            "con la base de datos que creaste. Revisa también los demás valores del archivo."
        ) from None


def can_prompt():
    if not sys.stdin.isatty():
        return False
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.GetStdHandle.argtypes = [wintypes.DWORD]
        kernel.GetStdHandle.restype = wintypes.HANDLE
        kernel.GetConsoleMode.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        mode = wintypes.DWORD()
        # Windows reports NUL as a tty, but getpass would wait forever for a
        # console key. MinTTY pipes likewise need the explicit .env fallback.
        return bool(kernel.GetConsoleMode(kernel.GetStdHandle(-10), ctypes.byref(mode)))
    return True


@contextlib.contextmanager
def reserve_port(port):
    """Reserve the actual socket before migrations or a worker can start."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        if os.name == "nt":
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        else:
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            listener.bind(("127.0.0.1", port))
            listener.listen(128)
        except OSError:
            raise DevelopmentError(
                f"No se pudo abrir el puerto {port}. Cierra la otra ejecución o elige otro con --port."
            ) from None
        yield listener


@contextlib.contextmanager
def database_guard(engine):
    """Keep one development worker per PostgreSQL database, without creating it."""
    from sqlalchemy import text

    with engine.connect() as connection:
        locked = False
        if engine.dialect.name == "postgresql":
            extensions = set(connection.scalars(text("SELECT extname FROM pg_extension")))
            if not {"postgis", "pg_trgm"} <= extensions:
                raise DevelopmentError(
                    "Activa las extensiones postgis y pg_trgm en tu base de PostgreSQL "
                    "antes de iniciar GeoPol. Consulta INSTALACION_LOCAL.md."
                )
            locked = connection.scalar(text("SELECT pg_try_advisory_lock(791043212)"))
            if not locked:
                raise DevelopmentError("Ya hay otra ejecución de geopol.dev usando esta base de datos.")
            connection.commit()
        try:
            yield
        finally:
            if locked:
                with contextlib.suppress(Exception):
                    connection.execute(text("SELECT pg_advisory_unlock(791043212)"))
                    connection.commit()


def prepare_database(engine, configuration):
    from sqlalchemy import select

    from . import cli
    from .db import SessionLocal
    from .migrations import migrate
    from .models import User

    migrate(engine)
    with SessionLocal() as session:
        if session.scalar(select(User.id).limit(1)) is not None:
            return
    bootstrap_password = (
        configuration.bootstrap_password.get_secret_value() if configuration.bootstrap_password else None
    )
    if not bootstrap_password and not can_prompt():
        raise DevelopmentError(
            "Esta terminal no permite escribir una contraseña oculta. Define "
            "GEOPOL_BOOTSTRAP_PASSWORD en backend/.env para crear la cuenta inicial."
        )
    print("Primera ejecución: crea la contraseña de la cuenta administrador.", flush=True)
    previous = os.environ.get("GEOPOL_BOOTSTRAP_PASSWORD")
    if bootstrap_password:
        os.environ["GEOPOL_BOOTSTRAP_PASSWORD"] = bootstrap_password
    try:
        # getpass must fail rather than fall back to echoing the password.
        with warnings.catch_warnings():
            warnings.simplefilter("error", getpass.GetPassWarning)
            cli.main(["bootstrap-user"])
    except (getpass.GetPassWarning, EOFError):
        raise DevelopmentError(
            "Esta terminal no permite escribir una contraseña oculta. Define "
            "GEOPOL_BOOTSTRAP_PASSWORD en backend/.env para crear la cuenta inicial."
        ) from None
    finally:
        if previous is None:
            os.environ.pop("GEOPOL_BOOTSTRAP_PASSWORD", None)
        else:
            os.environ["GEOPOL_BOOTSTRAP_PASSWORD"] = previous


def worker_process(lifetime):
    """The private pipe also stops the child if its parent abruptly disappears."""
    stopped = threading.Event()

    def watch_parent():
        try:
            lifetime.recv()
            stopped.set()
        except (EOFError, OSError):
            os._exit(1)

    threading.Thread(target=watch_parent, name="geopol-parent-watch", daemon=True).start()
    for kind in (signal.SIGINT, signal.SIGTERM):
        signal.signal(kind, lambda *_: stopped.set())
    from .worker import WORKER_ID, work_once

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.info("Worker iniciado: %s", WORKER_ID)
    try:
        while not stopped.is_set():
            if not work_once():
                stopped.wait(2)
    finally:
        lifetime.close()


@contextlib.contextmanager
def owned_worker():
    context = multiprocessing.get_context("spawn")
    receiver, sender = context.Pipe(duplex=False)
    worker = context.Process(target=worker_process, args=(receiver,), name="geopol-worker", daemon=True)
    started = False
    try:
        worker.start()
        started = True
        receiver.close()
        yield worker
    finally:
        receiver.close()
        if started:
            with contextlib.suppress(BrokenPipeError, EOFError, OSError):
                sender.send("stop")
            worker.join(timeout=8)
            if worker.is_alive():
                worker.terminate()
                worker.join(timeout=3)
            if worker.is_alive():
                worker.kill()
                worker.join(timeout=3)
            # Remove only this process's heartbeat after it has really exited.
            if not worker.is_alive():
                from .db import SessionLocal
                from .models import Heartbeat

                with contextlib.suppress(Exception), SessionLocal() as session:
                    item = session.get(Heartbeat, f"{socket.gethostname()}:{worker.pid}")
                    if item is not None:
                        session.delete(item)
                        session.commit()
                worker.close()
        sender.close()


async def serve(server, listener, worker):
    worker_failed = False

    async def monitor():
        nonlocal worker_failed
        while not server.should_exit:
            if not worker.is_alive():
                worker_failed = True
                server.should_exit = True
                return
            await asyncio.sleep(0.2)

    monitor_task = asyncio.create_task(monitor())
    try:
        await server.serve(sockets=[listener])
    finally:
        monitor_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await monitor_task
    if worker_failed:
        raise DevelopmentError("El worker se detuvo; se cerró también la API. Revisa el error anterior.")


@contextlib.contextmanager
def shutdown_signals(server):
    def stop(*_):
        if server.should_exit:
            server.force_exit = True
        server.should_exit = True

    kinds = [signal.SIGINT, signal.SIGTERM]
    if hasattr(signal, "SIGHUP"):
        kinds.append(signal.SIGHUP)
    previous = {kind: signal.signal(kind, stop) for kind in kinds}
    try:
        yield
    finally:
        for kind, handler in previous.items():
            signal.signal(kind, handler)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Iniciar API y worker de desarrollo desde backend/.env")
    parser.add_argument("--port", type=int, default=8000, help="Puerto de la API (8000 por defecto)")
    args = parser.parse_args(argv)
    if not 1 <= args.port <= 65535:
        parser.error("El puerto debe estar entre 1 y 65535")
    try:
        configuration = load_settings()
        # Defer persistence imports until an explicit configuration and free port exist.
        with reserve_port(args.port) as listener:
            import uvicorn

            from .db import engine

            with database_guard(engine):
                prepare_database(engine, configuration)
                server = uvicorn.Server(
                    uvicorn.Config(
                        "geopol.main:app",
                        host="127.0.0.1",
                        port=args.port,
                        log_level="info",
                        access_log=False,
                    )
                )
                # Own signal cleanup: uvicorn otherwise re-raises SIGTERM before
                # our worker context can close on Unix.
                server.capture_signals = contextlib.nullcontext
                with shutdown_signals(server), owned_worker() as worker:
                    print(f"GeoPol API: http://127.0.0.1:{args.port} · Ctrl+C para detener.", flush=True)
                    asyncio.run(serve(server, listener, worker))
            engine.dispose()
        return 0
    except KeyboardInterrupt:
        return 0
    except DevelopmentError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    except Exception as error:
        # Driver errors can contain credentials, SQL, or imported row values.
        print(
            f"No se pudo iniciar GeoPol ({type(error).__name__}). Revisa backend/.env, "
            "la conexión a PostgreSQL y los permisos de tu usuario.",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
