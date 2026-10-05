"""Start the Windows local installation and own its complete process tree."""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import shutil
import signal
import socket
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

from windows_processes import WindowsProcessScope

ROOT = Path(__file__).resolve().parents[1]


class StartupError(RuntimeError):
    pass


def available_port(port):
    with socket.socket() as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        try:
            probe.bind(("127.0.0.1", port))
        except OSError as error:
            raise StartupError(
                f"El puerto {port} esta ocupado. Cierra tu instancia anterior o elige "
                "otros puertos con --api-port y --port. No se detuvo ningun proceso."
            ) from error


def database_ready():
    from geopol.db import SessionLocal
    from geopol.migrations import SCHEMA_VERSION
    from geopol.models import Heartbeat, User
    from sqlalchemy import select, text
    from sqlalchemy.exc import SQLAlchemyError

    try:
        with SessionLocal() as db:
            db.execute(
                text("SELECT version FROM schema_versions WHERE version = :version"),
                {"version": SCHEMA_VERSION},
            ).scalar_one()
            if db.scalar(select(User.id).limit(1)) is None:
                raise StartupError(
                    "Falta la cuenta inicial. Ejecuta .\\instalar.cmd primero."
                )
            if db.scalar(
                select(Heartbeat.id)
                .where(Heartbeat.seen_at > time.time() - 60)
                .limit(1)
            ):
                raise StartupError(
                    "Ya hay actividad de un worker en esta base. Utiliza la instancia abierta. "
                    "Si acabas de cerrar su ventana, espera un minuto antes de volver a iniciar."
                )
    except SQLAlchemyError as error:
        raise StartupError(
            "La base no esta lista. Ejecuta .\\instalar.cmd primero."
        ) from error


def worker_healthy(identifier):
    from geopol.db import SessionLocal
    from geopol.models import Heartbeat

    if not identifier.is_file():
        return False
    with SessionLocal() as db:
        beat = db.get(Heartbeat, identifier.read_text(encoding="utf-8"))
        return beat is not None and beat.seen_at > time.time() - 60


def clear_owned_heartbeat(identifier):
    from geopol.db import SessionLocal
    from geopol.models import Heartbeat
    from sqlalchemy import delete

    if identifier.is_file():
        with SessionLocal() as db:
            db.execute(
                delete(Heartbeat).where(
                    Heartbeat.id == identifier.read_text(encoding="utf-8")
                )
            )
            db.commit()
        identifier.unlink()


@contextlib.contextmanager
def single_launcher(runtime):
    import msvcrt

    runtime.mkdir(parents=True, exist_ok=True)
    with (runtime / "launcher.lock").open("a+b") as stream:
        stream.seek(0, 2)
        if stream.tell() == 0:
            stream.write(b"0")
            stream.flush()
        stream.seek(0)
        try:
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as error:
            raise StartupError("GeoPol ya esta iniciado desde esta carpeta.") from error
        try:
            yield
        finally:
            stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)


def run(args):
    if os.name != "nt":
        raise StartupError(
            "Este inicio es para Windows. En Linux/macOS usa scripts/dev.sh."
        )
    os.chdir(ROOT)
    python = ROOT / "backend/.venv/Scripts/python.exe"
    vite = ROOT / "frontend/node_modules/vite/bin/vite.js"
    index = ROOT / "frontend/dist/index.html"
    node = shutil.which("node")
    if not all(path.is_file() for path in (python, vite, index)) or node is None:
        raise StartupError(
            "Faltan dependencias o la interfaz compilada. Ejecuta .\\instalar.cmd."
        )
    if args.api_port == args.port:
        raise StartupError("La API y la web necesitan puertos distintos.")
    runtime = args.runtime_dir.resolve()
    api_url = f"http://127.0.0.1:{args.api_port}"
    url = f"http://127.0.0.1:{args.port}"
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    stop = threading.Event()

    def read_stop():
        # Read the descriptor directly: a blocked daemon must not hold Python's
        # buffered-stdin lock when Ctrl+C shuts down the main interpreter.
        pending = b""
        while True:
            try:
                block = os.read(sys.stdin.fileno(), 1024)
            except OSError:
                return
            if not block:
                return
            pending += block
            while b"\n" in pending:
                line, pending = pending.split(b"\n", 1)
                if line.strip().lower() in {b"salir", b"q"}:
                    stop.set()
                    return

    def health(address):
        try:
            with opener.open(address + "/api/health", timeout=2) as response:
                return json.load(response).get("status") == "ok"
        except (OSError, ValueError, urllib.error.URLError):
            return False

    with single_launcher(runtime):
        available_port(args.api_port)
        available_port(args.port)
        database_ready()
        config = runtime / "preview.config.mjs"
        proxy = {"/api": api_url}
        config.write_text(
            "export default "
            + json.dumps({"server": {"proxy": proxy}, "preview": {"proxy": proxy}})
            + ";\n",
            encoding="utf-8",
        )
        identifier = runtime / "worker-id.txt"
        identifier.unlink(missing_ok=True)
        processes = {}

        def check_children():
            for name, child in processes.items():
                if child.poll() is not None:
                    raise StartupError(
                        f"El servicio {name} se detuvo. Revisa {runtime / (name + '.log')}"
                    )

        def wait_for(label, ready):
            deadline = time.monotonic() + 40
            while time.monotonic() < deadline:
                check_children()
                if ready():
                    return
                time.sleep(0.25)
            raise StartupError(
                f"No se pudo iniciar {label}. Revisa los registros en {runtime}"
            )

        try:
            with WindowsProcessScope() as scope:
                env = os.environ.copy()
                env["PYTHONUNBUFFERED"] = "1"
                print("Iniciando GeoPol...", flush=True)
                processes["api"] = scope.start(
                    [
                        python,
                        "-m",
                        "uvicorn",
                        "geopol.main:app",
                        "--host",
                        "127.0.0.1",
                        "--port",
                        str(args.api_port),
                        "--no-access-log",
                    ],
                    cwd=ROOT,
                    env=env,
                    log_path=runtime / "api.log",
                )
                wait_for("la API", lambda: health(api_url))
                # The virtualenv launcher may spawn a child; record the worker's own identity.
                worker_entry = (
                    "from pathlib import Path; import sys; target=Path(sys.argv.pop()); "
                    "from geopol.worker import main, WORKER_ID; "
                    "target.write_text(WORKER_ID, encoding='utf-8'); main()"
                )
                processes["worker"] = scope.start(
                    [python, "-c", worker_entry, identifier],
                    cwd=ROOT,
                    env=env,
                    log_path=runtime / "worker.log",
                )
                wait_for("el worker", lambda: worker_healthy(identifier))
                processes["frontend"] = scope.start(
                    [
                        node,
                        vite,
                        "preview",
                        "--config",
                        config,
                        "--host",
                        "127.0.0.1",
                        "--port",
                        str(args.port),
                        "--strictPort",
                    ],
                    cwd=ROOT / "frontend",
                    env=env,
                    log_path=runtime / "frontend.log",
                )
                wait_for("la web", lambda: health(url))
                print(f"\nGeoPol disponible: {url}\n", flush=True)
                print(
                    "Deja esta ventana abierta. Ctrl+C o escribe salir para detener GeoPol.",
                    flush=True,
                )
                print(f"Registros: {runtime}", flush=True)
                if not args.no_browser:
                    webbrowser.open(url)
                threading.Thread(target=read_stop, daemon=True).start()
                while not stop.wait(0.5):
                    check_children()
        finally:
            # The Job Object has already stopped the owned process tree before this cleanup.
            with contextlib.suppress(Exception):
                clear_owned_heartbeat(identifier)
    print("GeoPol detenido. Tus datos se conservan.", flush=True)


def main():
    parser = argparse.ArgumentParser(
        description="Iniciar GeoPol local en una sola terminal."
    )
    parser.add_argument("--api-port", type=int, default=8000)
    parser.add_argument("--port", type=int, default=5173)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument(
        "--runtime-dir",
        type=Path,
        default=ROOT / ".local/runtime",
        help=argparse.SUPPRESS,
    )
    args = parser.parse_args()
    if not all(1 <= port <= 65535 for port in (args.port, args.api_port)):
        parser.error("Los puertos deben estar entre 1 y 65535.")
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    try:
        run(args)
    except KeyboardInterrupt:
        print("\nGeoPol detenido. Tus datos se conservan.", flush=True)
        return 0
    except ImportError:
        print(
            "\nFaltan dependencias de Python. Ejecuta .\\instalar.cmd.",
            file=sys.stderr,
            flush=True,
        )
        return 1
    except (StartupError, OSError, RuntimeError) as error:
        print(f"\nNo se pudo iniciar GeoPol: {error}", file=sys.stderr, flush=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
