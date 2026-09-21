"""Reproducible local synthetic load check, using HTTP and bounded streaming I/O.

Run with backend/.venv Python. A real Uvicorn process, worker processes and SQLite
use an isolated directory under .local. No institutional data or remote service.
"""

from __future__ import annotations

import argparse
import csv
import ctypes
import hashlib
import json
import os
import platform
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def process_memory(pid: int) -> tuple[int, int]:
    """Current and peak resident bytes from the OS, without instrumenting allocations."""
    if os.name == "nt":
        from ctypes import wintypes

        class Counters(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD)] + [
                (name, ctypes.c_size_t)
                for name in (
                    "PeakWorkingSetSize",
                    "WorkingSetSize",
                    "QuotaPeakPagedPoolUsage",
                    "QuotaPagedPoolUsage",
                    "QuotaPeakNonPagedPoolUsage",
                    "QuotaNonPagedPoolUsage",
                    "PagefileUsage",
                    "PeakPagefileUsage",
                )
            ]

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        psapi = ctypes.WinDLL("psapi", use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        psapi.GetProcessMemoryInfo.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(Counters),
            wintypes.DWORD,
        ]
        handle = kernel.OpenProcess(0x0400 | 0x0010, False, pid)
        if not handle:
            return 0, 0
        try:
            counters = Counters()
            counters.cb = ctypes.sizeof(counters)
            if psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb):
                return counters.WorkingSetSize, counters.PeakWorkingSetSize
        finally:
            kernel.CloseHandle(handle)
    elif Path(f"/proc/{pid}/status").exists():
        fields = {}
        try:
            status = Path(f"/proc/{pid}/status").read_text()
        except (FileNotFoundError, ProcessLookupError):
            # A worker may exit between discovery and reading its status.
            return 0, 0
        for line in status.splitlines():
            if line.startswith(("VmRSS:", "VmHWM:")):
                name, value = line.split(":", 1)
                fields[name] = int(value.split()[0]) * 1024
        return fields.get("VmRSS", 0), fields.get("VmHWM", 0)
    return 0, 0


class MemoryMonitor:
    def __init__(self):
        self.pids = {"driver": os.getpid()}
        self.peaks = {}
        self.total_peak = 0
        self.sample_count = 0
        self.error_count = 0
        self.recent_errors = []
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self._sample, daemon=True)

    def _sample(self):
        while not self.stop.is_set():
            try:
                self._sample_once()
            except (OSError, ValueError) as error:
                # Memory telemetry must not silently stop when /proc permissions
                # or OS process enumeration change during a long-running job.
                self.error_count += 1
                self.recent_errors = (self.recent_errors + [type(error).__name__])[-10:]
            self.stop.wait(0.25)

    def _sample_once(self):
        total, counted = 0, set()
        descendants = process_children()
        for name, pid in list(self.pids.items()):
            tree, pending = {pid}, [pid] if name != "driver" else []
            while pending:
                for child in descendants.get(pending.pop(), []):
                    if child not in tree:
                        tree.add(child)
                        pending.append(child)
            peak_sum = 0
            for child in tree:
                current, peak = process_memory(child)
                peak_sum += peak
                if child not in counted:
                    total += current
                    counted.add(child)
            self.peaks[name] = max(self.peaks.get(name, 0), peak_sum)
        self.total_peak = max(self.total_peak, total)
        self.sample_count += 1


def process_children() -> dict[int, list[int]]:
    """Include the actual Python child of Windows virtualenv launchers."""
    children: dict[int, list[int]] = {}
    if os.name == "nt":
        from ctypes import wintypes

        class ProcessEntry(ctypes.Structure):
            _fields_ = [
                ("dwSize", wintypes.DWORD),
                ("cntUsage", wintypes.DWORD),
                ("th32ProcessID", wintypes.DWORD),
                ("th32DefaultHeapID", ctypes.c_size_t),
                ("th32ModuleID", wintypes.DWORD),
                ("cntThreads", wintypes.DWORD),
                ("th32ParentProcessID", wintypes.DWORD),
                ("pcPriClassBase", wintypes.LONG),
                ("dwFlags", wintypes.DWORD),
                ("szExeFile", wintypes.WCHAR * 260),
            ]

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
        kernel.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
        kernel.Process32FirstW.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(ProcessEntry),
        ]
        kernel.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessEntry)]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        snapshot = kernel.CreateToolhelp32Snapshot(0x00000002, 0)
        if snapshot == ctypes.c_void_p(-1).value:
            return children
        try:
            entry = ProcessEntry()
            entry.dwSize = ctypes.sizeof(entry)
            okay = kernel.Process32FirstW(snapshot, ctypes.byref(entry))
            while okay:
                children.setdefault(entry.th32ParentProcessID, []).append(
                    entry.th32ProcessID
                )
                okay = kernel.Process32NextW(snapshot, ctypes.byref(entry))
        finally:
            kernel.CloseHandle(snapshot)
    elif Path("/proc").exists():
        for process in Path("/proc").glob("[0-9]*/status"):
            try:
                parent = next(
                    line
                    for line in process.read_text().splitlines()
                    if line.startswith("PPid:")
                )
                children.setdefault(int(parent.split()[1]), []).append(
                    int(process.parent.name)
                )
            except (FileNotFoundError, PermissionError, StopIteration):
                pass
    return children


def stop_owned_process(process: subprocess.Popen | None) -> None:
    """Stop only a live process launched by this driver, including its Windows child."""
    if process is None or process.poll() is not None:
        return
    if os.name == "nt":
        try:
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=15,
                check=False,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        except (OSError, subprocess.TimeoutExpired):
            if process.poll() is None:
                process.kill()
    else:
        process.terminate()
    try:
        process.wait(timeout=15)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rows", type=int, default=10_000)
    parser.add_argument(
        "--padding",
        type=int,
        default=3072,
        help="ASCII bytes in a non-location source column",
    )
    parser.add_argument("--timeout", type=int, default=7200)
    parser.add_argument(
        "--resume-runtime",
        type=Path,
        help="Resume one interrupted synthetic run under this project's .local directory",
    )
    parser.add_argument(
        "--database-path",
        type=Path,
        help="With --resume-runtime, use an existing consistent SQLite backup on another local disk; source/storage stay in the original runtime",
    )
    parser.add_argument(
        "--profile-worker",
        action="store_true",
        help="Write private cProfile statistics for the processing worker",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=None,
        help="Override GEOPOL_BATCH_SIZE for this private run",
    )
    args = parser.parse_args()
    if args.rows < 1 or not 0 <= args.padding <= 32_768:
        parser.error("rows must be positive; padding must be between 0 and 32768")
    private = ROOT / ".local"
    private.mkdir(exist_ok=True)
    estimated = args.rows * (args.padding + 12_000)
    free = shutil.disk_usage(private).free
    if free < estimated * 2:
        raise RuntimeError(
            "Insufficient free disk for source, immutable upload, database and export"
        )
    if args.resume_runtime:
        runtime = args.resume_runtime.resolve()
        if runtime.parent != private.resolve() or not runtime.name.startswith("load-"):
            parser.error(
                "Resume is restricted to a load-* folder directly under this project's .local"
            )
        if (
            not (runtime / "benchmark.db").is_file()
            or not (runtime / "synthetic-source.csv").is_file()
        ):
            parser.error(
                "The interrupted run must retain its database and synthetic source"
            )
    else:
        runtime = Path(tempfile.mkdtemp(prefix=f"load-{args.rows}-", dir=private))
    database_path = (
        args.database_path.resolve() if args.database_path else runtime / "benchmark.db"
    )
    if args.database_path and (not args.resume_runtime or not database_path.is_file()):
        parser.error(
            "database-path requires resume-runtime and an existing SQLite backup"
        )
    environment = os.environ.copy()
    environment.update(
        GEOPOL_DATABASE_URL="sqlite:///" + str(database_path),
        GEOPOL_STORAGE_PATH=str(runtime / "storage"),
        GEOPOL_ENV="test",
    )
    if args.batch_size is not None:
        if not 1 <= args.batch_size <= 10_000:
            parser.error("batch-size must be between 1 and 10000")
        environment["GEOPOL_BATCH_SIZE"] = str(args.batch_size)
    os.environ.update({k: v for k, v in environment.items() if k.startswith("GEOPOL_")})
    sys.path.insert(0, str(ROOT / "backend"))
    import httpx
    from geopol.config import settings
    from geopol.db import SessionLocal, engine
    from geopol.domain import RULES_VERSION
    from geopol.migrations import migrate
    from geopol.models import Job, Run, User
    from geopol.security import password_hash
    from sqlalchemy import select

    migrate(engine)
    with engine.connect() as connection:
        sqlite_parameters = {
            name: connection.exec_driver_sql(f"PRAGMA {name}").scalar()
            for name in (
                "cache_size",
                "wal_autocheckpoint",
                "synchronous",
                "page_size",
                "journal_mode",
            )
        }
    password = secrets.token_urlsafe(32)
    resume = None
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.username == "synthetic-load"))
        if user is None:
            user = User(
                username="synthetic-load",
                password_hash=password_hash(password),
                role="admin",
            )
            db.add(user)
        else:
            user.password_hash = password_hash(password)
        if args.resume_runtime:
            runs = list(db.scalars(select(Run)))
            if len(runs) != 1:
                raise RuntimeError(
                    "Resume requires exactly one previously created synthetic run"
                )
            item = runs[0]
            job = db.scalar(
                select(Job).where(Job.kind == "RUN", Job.target_id == item.id)
            )
            resume = {
                "id": item.id,
                "upload_id": item.upload_id,
                "reference_id": item.reference_id,
                "source_rows_at_resume": item.source_rows,
                "processed_units_at_resume": item.processed_units,
                "lease_until": job.lease_until or 0,
                "status": item.status,
            }
        db.commit()
    engine.dispose()
    monitor = MemoryMonitor()
    monitor.thread.start()
    timings = {}
    stage_start = time.perf_counter()
    source = runtime / "synthetic-source.csv"
    filler = "X" * args.padding
    if not resume:
        with source.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(
                ["complaint_id", "location_original", "ubigeo", "synthetic_padding"]
            )
            for index in range(args.rows):
                writer.writerow(
                    [f"SYNTHETIC-{index:09d}", "AVENIDA PRUEBA 120", "150101", filler]
                )
        timings["generate_seconds"] = time.perf_counter() - stage_start
    size = source.stat().st_size
    print(
        json.dumps(
            {
                "stage": "resumed_source" if resume else "generated",
                "rows": args.rows,
                "bytes": size,
                "runtime": str(runtime),
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    server_log = (runtime / "api.log").open("a", encoding="utf-8")
    creation_flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    server = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "geopol.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--no-access-log",
        ],
        cwd=ROOT / "backend",
        env=environment,
        stdout=server_log,
        stderr=subprocess.STDOUT,
        creationflags=creation_flags,
    )
    monitor.pids["api"] = server.pid
    benchmark_start = time.monotonic()
    deadline = benchmark_start + args.timeout
    client = httpx.Client(
        base_url=f"http://127.0.0.1:{port}",
        timeout=600,
        trust_env=False,
        limits=httpx.Limits(max_keepalive_connections=0),
    )
    worker_process = None

    def request(method, path, **kwargs):
        for attempt in range(4):
            try:
                response = client.request(method, path, **kwargs)
                break
            except httpx.TransportError:
                # Retry only idempotent reads; mutations remain explicit and auditable.
                if method != "GET" or attempt == 3:
                    raise
                time.sleep(min(2**attempt, 4))
        if response.status_code >= 400:
            raise RuntimeError(
                f"HTTP {response.status_code} on {method} {path}: {response.text[:200]}"
            )
        return response.json()

    def run_job(name, status_path):
        nonlocal worker_process
        with (runtime / f"{name}.log").open("a", encoding="utf-8") as log:
            command = [sys.executable, "-m", "geopol.worker", "--once"]
            if args.profile_worker and name == "processing_worker":
                command = [
                    sys.executable,
                    "-m",
                    "cProfile",
                    "-o",
                    str(runtime / "worker-profile.pstats"),
                    "-m",
                    "geopol.worker",
                    "--once",
                ]
            worker_process = subprocess.Popen(
                command,
                cwd=ROOT / "backend",
                env=environment,
                stdout=log,
                stderr=subprocess.STDOUT,
                creationflags=creation_flags,
            )
            monitor.pids[name] = worker_process.pid
            last_print = 0.0
            ingestion_done = None
            while worker_process.poll() is None:
                if time.monotonic() > deadline:
                    raise RuntimeError(
                        "Benchmark timeout; private artifacts retained for diagnosis"
                    )
                now = time.perf_counter()
                if now - last_print >= 5:
                    status = request("GET", status_path)
                    checkpoint = {
                        "passed": False,
                        "evidence": "Progress checkpoint; final export verification still required",
                        "date_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                        "elapsed_seconds": round(time.monotonic() - benchmark_start, 3),
                        "stage": name,
                        "status": status.get("status"),
                        "source_rows": status.get("source_rows"),
                        "processed_units": status.get("processed_units"),
                        "peak_rss_bytes_by_process_tree": dict(monitor.peaks),
                        "process_tree_peak_metric": "Upper bound: sum of individual process historical RSS maxima; not simultaneous",
                        "peak_combined_sampled_rss_bytes": monitor.total_peak,
                        "memory_monitor_samples": monitor.sample_count,
                        "memory_monitor_errors": monitor.error_count,
                        "memory_monitor_thread_alive": monitor.thread.is_alive(),
                    }
                    checkpoint_temp = runtime / "last-checkpoint.json.tmp"
                    checkpoint_temp.write_text(
                        json.dumps(checkpoint, indent=2), encoding="utf-8"
                    )
                    checkpoint_temp.replace(runtime / "last-checkpoint.json")
                    print(
                        json.dumps(
                            {
                                "stage": name,
                                "status": status.get("status"),
                                "source_rows": status.get("source_rows"),
                                "processed_units": status.get("processed_units"),
                            }
                        ),
                        flush=True,
                    )
                    if status.get("status") == "PROCESSING" and ingestion_done is None:
                        ingestion_done = now
                    last_print = now
                time.sleep(0.25)
            if worker_process.returncode:
                raise RuntimeError(
                    f"Worker {name} exited {worker_process.returncode}; inspect private log"
                )
            status = request("GET", status_path)
            if status["status"] not in {"COMPLETED", "COMPLETED_WITH_ISSUES"}:
                raise RuntimeError(
                    f"Worker {name} finished with status {status['status']}"
                )
            return status, ingestion_done

    try:
        ready_until = time.monotonic() + 30
        while True:
            try:
                request("GET", "/api/health")
                break
            except (httpx.ConnectError, RuntimeError):
                if time.monotonic() >= ready_until or server.poll() is not None:
                    raise RuntimeError("API did not start; inspect private api.log")
                time.sleep(0.2)
        credentials = request(
            "POST",
            "/api/auth/login",
            json={"username": "synthetic-load", "password": password},
        )
        client.headers["Authorization"] = "Bearer " + credentials["token"]
        reference_document = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "id": "synthetic-door",
                    "properties": {
                        "kind": "door",
                        "ubigeo": "150101",
                        "street_type": "AVENIDA",
                        "street_name": "PRUEBA",
                        "door_number": "120",
                    },
                    "geometry": {"type": "Point", "coordinates": [-77.1, -12.05]},
                }
            ],
        }
        catalog = (
            {"id": resume["reference_id"]}
            if resume
            else request(
                "POST",
                "/api/references",
                data={
                    "name": "Carga sintética",
                    "source": "BENCHMARK FICTICIO",
                    "version": "synthetic-1",
                },
                files={
                    "file": (
                        "synthetic.geojson",
                        json.dumps(reference_document).encode(),
                        "application/geo+json",
                    )
                },
            )
        )
        stage_start = time.perf_counter()
        upload = (
            {"id": resume["upload_id"]}
            if resume
            else request(
                "POST", "/api/uploads", json={"filename": source.name, "size": size}
            )
        )
        digest = hashlib.sha256()
        offset = 0
        with source.open("rb") as stream:
            while block := stream.read(8 * 1024 * 1024):
                digest.update(block)
                if not resume:
                    response = request(
                        "PATCH",
                        f"/api/uploads/{upload['id']}",
                        content=block,
                        headers={
                            "Upload-Offset": str(offset),
                            "Content-Type": "application/octet-stream",
                        },
                    )
                offset += len(block)
                if not resume:
                    assert response["offset"] == offset
        uploaded = (
            request("GET", f"/api/uploads/{upload['id']}")
            if resume
            else request("POST", f"/api/uploads/{upload['id']}/complete")
        )
        assert uploaded["sha256"] == digest.hexdigest()
        input_timing = (
            "existing_source_verify_seconds" if resume else "upload_and_profile_seconds"
        )
        timings[input_timing] = time.perf_counter() - stage_start
        print(
            json.dumps(
                {
                    "stage": "existing_upload_verified" if resume else "uploaded",
                    "seconds": round(timings[input_timing], 3),
                }
            ),
            flush=True,
        )
        run = (
            request("GET", f"/api/runs/{resume['id']}")
            if resume
            else request(
                "POST",
                "/api/runs",
                json={
                    "upload_id": upload["id"],
                    "name": "Carga sintética reproducible",
                    "reference_id": catalog["id"],
                    "crs": "EPSG:4326",
                },
            )
        )
        stage_start = time.perf_counter()
        if resume:
            if run["status"] in {"FAILED", "CANCELLED"}:
                request("POST", f"/api/runs/{run['id']}/retry")
            while time.time() <= resume["lease_until"] and run["status"] not in {
                "COMPLETED",
                "COMPLETED_WITH_ISSUES",
            }:
                print(
                    json.dumps(
                        {
                            "stage": "waiting_expired_worker_lease",
                            "seconds": round(resume["lease_until"] - time.time()),
                        }
                    ),
                    flush=True,
                )
                time.sleep(min(5, max(0.1, resume["lease_until"] - time.time())))
        completed, ingestion_done = run_job(
            "processing_worker", f"/api/runs/{run['id']}"
        )
        processing_timing = (
            "recovery_ingest_and_process_seconds"
            if resume
            else "ingest_and_process_seconds"
        )
        timings[processing_timing] = time.perf_counter() - stage_start
        timings["ingest_seconds_approx"] = (
            None if ingestion_done is None else ingestion_done - stage_start
        )
        timings["process_seconds_approx"] = (
            None if ingestion_done is None else time.perf_counter() - ingestion_done
        )
        assert (
            completed["source_rows"]
            == completed["location_units"]
            == completed["processed_units"]
            == args.rows
        )
        assert completed["counts"] == {"ACEPTADO_AUTOMATICO": args.rows}
        stage_start = time.perf_counter()
        export = request(
            "POST",
            f"/api/runs/{run['id']}/exports",
            json={"profile": "source_rows", "safe_spreadsheet": True},
        )
        timings["export_snapshot_seconds"] = time.perf_counter() - stage_start
        stage_start = time.perf_counter()
        exported, _ = run_job("export_worker", f"/api/exports/{export['id']}")
        timings["export_seconds"] = time.perf_counter() - stage_start
        assert exported["row_count"] == args.rows
        stage_start = time.perf_counter()
        download_path = runtime / "downloaded-export.csv"
        digest = hashlib.sha256()
        with client.stream("GET", f"/api/exports/{export['id']}/download") as response:
            response.raise_for_status()
            with download_path.open("wb") as stream:
                for block in response.iter_bytes(1024 * 1024):
                    digest.update(block)
                    stream.write(block)
        assert digest.hexdigest() == exported["sha256"]
        count = 0
        with download_path.open("r", encoding="utf-8-sig", newline="") as stream:
            for row in csv.DictReader(stream):
                assert int(row["SOURCE_ORDINAL"]) == count + 1
                assert row["complaint_id"] == f"SYNTHETIC-{count:09d}"
                assert row["GEOPOL_resolution"] == "ACEPTADO_AUTOMATICO"
                assert row["GEOPOL_latitude"] and row["GEOPOL_longitude"]
                assert len(row["synthetic_padding"]) == args.padding
                count += 1
        assert count == args.rows
        timings["download_and_verify_seconds"] = time.perf_counter() - stage_start
        manifest = request("GET", f"/api/exports/{export['id']}/manifest")
        assert manifest["row_count"] == args.rows
        report = {
            "passed": True,
            "date_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "platform": platform.platform(),
            "python": platform.python_version(),
            "database": "SQLite",
            "rules_version": RULES_VERSION,
            "sqlite_parameters": sqlite_parameters,
            "batch_size": settings.batch_size,
            "profiled": args.profile_worker,
            "resumed_after_interruption": bool(resume),
            "source_rows_at_resume": resume["source_rows_at_resume"] if resume else 0,
            "processed_units_at_resume": resume["processed_units_at_resume"]
            if resume
            else 0,
            "timing_and_memory_scope": "Recovery segment and subsequent export only; earlier interrupted segment not included"
            if resume
            else "Continuous completed run",
            "rows": args.rows,
            "location_units": completed["location_units"],
            "input_bytes": size,
            "padding_bytes_per_row": args.padding,
            "source_sha256": uploaded["sha256"],
            "export_rows": count,
            "export_bytes": download_path.stat().st_size,
            "export_sha256": exported["sha256"],
            "export_ordinals_and_identifiers_verified": True,
            "resolutions": completed["counts"],
            "issue_rows": completed["issue_rows"],
            "timings_seconds": {
                k: round(v, 3) if v is not None else None for k, v in timings.items()
            },
            "peak_rss_bytes_by_process_tree": dict(monitor.peaks),
            "process_tree_peak_metric": "Upper bound: sum of individual process historical RSS maxima; not a simultaneous tree peak",
            "peak_combined_sampled_rss_bytes": monitor.total_peak,
            "memory_sampling_seconds": 0.25,
            "memory_monitor": {
                "healthy": monitor.error_count == 0
                and monitor.sample_count > 0
                and monitor.thread.is_alive(),
                "successful_samples": monitor.sample_count,
                "error_count": monitor.error_count,
                "recent_error_types": list(monitor.recent_errors),
            },
            "ingestion_timing_sampling_seconds": 5,
            "workload": "Unique synthetic complaint per row; one exact street and reference point; no fuzzy search; ASCII padding only in source field",
        }
        (runtime / "summary.json").write_text(
            json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print(
            json.dumps({"stage": "complete", "report": report}, ensure_ascii=False),
            flush=True,
        )
    finally:
        client.close()
        stop_owned_process(worker_process)
        stop_owned_process(server)
        server_log.close()
        monitor.stop.set()
        monitor.thread.join(timeout=2)


if __name__ == "__main__":
    main()
