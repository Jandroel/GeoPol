"""Start the local installation and supervise only GeoPol's own processes."""

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

if os.name == "nt":
    from windows_processes import WindowsProcessScope as ProcessScope
else:
    from posix_processes import PosixProcessScope as ProcessScope

ROOT = Path(__file__).resolve().parents[1]


class StartupError(RuntimeError):
    pass


class LauncherRunning(StartupError):
    pass


class StopRequested(Exception):
    pass


def configure(args):
    """Load native settings before importing any module that constructs the DB engine."""
    args.install_command = "bash instalar.sh" if args.native or os.name != "nt" else ".\\instalar.cmd"
    config = {}
    if args.native:
        try:
            config = json.loads((ROOT / ".local/native.json").read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise StartupError(
                "Falta la configuracion nativa o no es valida. Ejecuta bash instalar.sh."
            ) from error
        if not isinstance(config, dict):
            raise StartupError("La configuracion nativa no es valida. Ejecuta bash instalar.sh.")
        database_url = config.get("database_url")
        storage_path = config.get("storage_path")
        if not isinstance(database_url, str) or not database_url.startswith("postgresql+psycopg://"):
            raise StartupError(
                "La instalacion nativa requiere PostgreSQL con postgresql+psycopg://. "
                "Ejecuta bash instalar.sh."
            )
        if not isinstance(storage_path, str) or not storage_path.strip():
            raise StartupError("Falta storage_path en la configuracion nativa. Ejecuta bash instalar.sh.")
        storage = Path(storage_path)
        if not storage.is_absolute():
            storage = ROOT / storage
        os.environ["GEOPOL_DATABASE_URL"] = database_url
        os.environ["GEOPOL_STORAGE_PATH"] = str(storage.resolve())
    args.api_port = args.api_port if args.api_port is not None else config.get("api_port", 8000)
    args.port = args.port if args.port is not None else config.get("web_port", 5173)
    if any(type(port) is not int or not 1 <= port <= 65535 for port in (args.port, args.api_port)):
        raise StartupError("Los puertos deben ser numeros enteros entre 1 y 65535.")
    if args.api_port == args.port:
        raise StartupError("La API y la web necesitan puertos distintos.")
    if args.runtime_dir is None:
        args.runtime_dir = ROOT / (".local/native-runtime" if args.native else ".local/runtime")
    if args.native:
        os.environ["GEOPOL_ALLOWED_ORIGINS"] = (
            f"http://localhost:{args.port},http://127.0.0.1:{args.port}"
        )


def available_port(port):
    with socket.socket() as probe:
        if os.name == "nt":
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        else:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind(("127.0.0.1", port))
        except OSError as error:
            raise StartupError(
                f"El puerto {port} esta ocupado. Cierra tu instancia anterior o elige "
                "otros puertos con --api-port y --port. No se detuvo ningun proceso."
            ) from error


def database_ready(install_command=".\\instalar.cmd"):
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
                    f"Falta la cuenta inicial. Ejecuta {install_command} primero."
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
            f"La base no esta lista. Ejecuta {install_command} primero."
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
    runtime.mkdir(parents=True, exist_ok=True)
    with (runtime / "launcher.lock").open("a+b") as stream:
        stream.seek(0, 2)
        if stream.tell() == 0:
            stream.write(b"0")
            stream.flush()
        stream.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            raise LauncherRunning("GeoPol ya esta iniciado desde esta carpeta.") from error
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == "nt":
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def request_stop(runtime):
    """Ask the owning supervisor to stop; never signal a PID from a file."""
    try:
        with single_launcher(runtime):
            print("GeoPol nativo ya esta detenido. PostgreSQL sigue disponible.", flush=True)
            return
    except LauncherRunning:
        pass
    (runtime / "stop.request").touch()
    deadline = time.monotonic() + 25
    while time.monotonic() < deadline:
        try:
            with single_launcher(runtime):
                (runtime / "stop.request").unlink(missing_ok=True)
                print("GeoPol detenido. Tus datos y PostgreSQL se conservan.", flush=True)
                return
        except LauncherRunning:
            time.sleep(0.2)
    raise StartupError(
        "Se solicito la parada, pero GeoPol aun no confirmo el cierre. "
        "Revisa la terminal de iniciar.sh y sus registros."
    )


def run(args):
    os.chdir(ROOT)
    runtime = args.runtime_dir.resolve()
    if args.stop:
        request_stop(runtime)
        return
    python = ROOT / ("backend/.venv/Scripts/python.exe" if os.name == "nt" else "backend/.venv/bin/python")
    vite = ROOT / "frontend/node_modules/vite/bin/vite.js"
    index = ROOT / "frontend/dist/index.html"
    node = shutil.which("node")
    if not all(path.is_file() for path in (python, vite, index)) or node is None:
        raise StartupError(
            f"Faltan dependencias o la interfaz compilada. Ejecuta {args.install_command}."
        )
    api_url = f"http://127.0.0.1:{args.api_port}"
    url = f"http://127.0.0.1:{args.port}"
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    stop = threading.Event()
    stop_request = runtime / "stop.request"

    def read_stop():
        # Read the descriptor directly: a blocked daemon must not hold Python's
        # buffered-stdin lock when Ctrl+C shuts down the main interpreter.
        pending = b""
        while True:
            try:
                block = os.read(sys.stdin.fileno(), 1024)
            except (OSError, ValueError):
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
        # An old request must not stop a new instance that acquired this lock.
        stop_request.unlink(missing_ok=True)
        available_port(args.api_port)
        available_port(args.port)
        database_ready(args.install_command)
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
            if stop.is_set() or (args.native and stop_request.is_file()):
                raise StopRequested
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
            with ProcessScope() as scope:
                env = os.environ.copy()
                env["PYTHONUNBUFFERED"] = "1"
                threading.Thread(target=read_stop, daemon=True).start()
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
                while not stop.wait(0.5):
                    check_children()
        except StopRequested:
            pass
        finally:
            # The process scope has stopped this launcher's children before DB cleanup.
            with contextlib.suppress(Exception):
                clear_owned_heartbeat(identifier)
            stop_request.unlink(missing_ok=True)
    print("GeoPol detenido. Tus datos se conservan.", flush=True)


def main():
    parser = argparse.ArgumentParser(
        description="Iniciar GeoPol local en una sola terminal."
    )
    parser.add_argument("--native", action="store_true", help="Usar la instalacion Bash con PostgreSQL local.")
    parser.add_argument("--stop", action="store_true", help="Detener la instancia nativa desde otra terminal.")
    parser.add_argument("--api-port", type=int)
    parser.add_argument("--port", type=int)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument(
        "--runtime-dir",
        type=Path,
        help=argparse.SUPPRESS,
    )
    args = parser.parse_args()
    if args.stop and not args.native:
        parser.error("--stop requiere --native.")
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    if os.name != "nt":
        signal.signal(signal.SIGHUP, lambda *_: sys.exit(0))
    try:
        configure(args)
        run(args)
    except KeyboardInterrupt:
        print("\nGeoPol detenido. Tus datos se conservan.", flush=True)
        return 0
    except ImportError:
        print(
            f"\nFaltan dependencias de Python. Ejecuta {args.install_command}.",
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
