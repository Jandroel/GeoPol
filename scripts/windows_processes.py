"""Own Windows child processes without affecting existing local services.

Each child starts suspended, joins a private kill-on-close Job Object, and only
then resumes. Descendants inherit that job. Windows closes its non-inheritable
handle if the supervisor exits or its console is closed, including abrupt exits.
"""

from __future__ import annotations

import contextlib
import ctypes
import os
import subprocess
import time
from collections.abc import Mapping, Sequence
from ctypes import wintypes
from pathlib import Path
from typing import BinaryIO, Self


class WindowsProcessError(RuntimeError):
    """A child could not be started or contained safely."""


class _BasicLimit(ctypes.Structure):
    _fields_ = [
        ("process_time", ctypes.c_int64),
        ("job_time", ctypes.c_int64),
        ("flags", wintypes.DWORD),
        ("min_working", ctypes.c_size_t),
        ("max_working", ctypes.c_size_t),
        ("active", wintypes.DWORD),
        ("affinity", ctypes.c_size_t),
        ("priority", wintypes.DWORD),
        ("scheduling", wintypes.DWORD),
    ]


class _IoCounters(ctypes.Structure):
    _fields_ = [
        (name, ctypes.c_uint64) for name in ("read_ops", "write_ops", "other_ops", "read", "write", "other")
    ]


class _ExtendedLimit(ctypes.Structure):
    _fields_ = [
        ("basic", _BasicLimit),
        ("io", _IoCounters),
        ("process_memory", ctypes.c_size_t),
        ("job_memory", ctypes.c_size_t),
        ("peak_process", ctypes.c_size_t),
        ("peak_job", ctypes.c_size_t),
    ]


class _ThreadEntry(ctypes.Structure):
    _fields_ = [
        ("size", wintypes.DWORD),
        ("usage", wintypes.DWORD),
        ("thread", wintypes.DWORD),
        ("owner", wintypes.DWORD),
        ("base_priority", wintypes.LONG),
        ("delta_priority", wintypes.LONG),
        ("flags", wintypes.DWORD),
    ]


class _BasicAccounting(ctypes.Structure):
    _fields_ = [
        ("user_time", ctypes.c_int64),
        ("kernel_time", ctypes.c_int64),
        ("period_user_time", ctypes.c_int64),
        ("period_kernel_time", ctypes.c_int64),
        ("page_faults", wintypes.DWORD),
        ("total_processes", wintypes.DWORD),
        ("active_processes", wintypes.DWORD),
        ("terminated_processes", wintypes.DWORD),
    ]


class WindowsProcessScope:
    """Context manager for a single private Windows process tree.

    Use ``with WindowsProcessScope() as scope`` before calling ``start``.
    ``close`` is idempotent; a closed scope cannot be reopened. No process is
    selected by executable name, port, or an externally supplied PID.
    """

    def __init__(self) -> None:
        if os.name != "nt":
            raise WindowsProcessError("Este supervisor de procesos requiere Windows.")
        self._kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self._handle = None
        self._closed = False
        self._children: list[subprocess.Popen[bytes]] = []
        self._streams: list[BinaryIO] = []
        signatures = {
            "CreateJobObjectW": ([ctypes.c_void_p, wintypes.LPCWSTR], wintypes.HANDLE),
            "SetInformationJobObject": (
                [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD],
                wintypes.BOOL,
            ),
            "AssignProcessToJobObject": (
                [wintypes.HANDLE, wintypes.HANDLE],
                wintypes.BOOL,
            ),
            "TerminateJobObject": ([wintypes.HANDLE, wintypes.UINT], wintypes.BOOL),
            "QueryInformationJobObject": (
                [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p],
                wintypes.BOOL,
            ),
            "CloseHandle": ([wintypes.HANDLE], wintypes.BOOL),
            "OpenProcess": (
                [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD],
                wintypes.HANDLE,
            ),
            "CreateToolhelp32Snapshot": (
                [wintypes.DWORD, wintypes.DWORD],
                wintypes.HANDLE,
            ),
            "Thread32First": ([wintypes.HANDLE, ctypes.c_void_p], wintypes.BOOL),
            "Thread32Next": ([wintypes.HANDLE, ctypes.c_void_p], wintypes.BOOL),
            "OpenThread": (
                [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD],
                wintypes.HANDLE,
            ),
            "ResumeThread": ([wintypes.HANDLE], wintypes.DWORD),
        }
        for name, (arguments, result) in signatures.items():
            function = getattr(self._kernel, name)
            function.argtypes, function.restype = arguments, result

    @staticmethod
    def _error(message: str) -> WindowsProcessError:
        code = ctypes.get_last_error()
        return WindowsProcessError(f"{message} (error de Windows {code}).")

    def __enter__(self) -> Self:
        if self._closed or self._handle:
            raise WindowsProcessError("El grupo de procesos ya fue abierto o cerrado.")
        self._handle = self._kernel.CreateJobObjectW(None, None)
        if not self._handle:
            raise self._error("No se pudo crear el grupo de procesos")
        limits = _ExtendedLimit()
        limits.basic.flags = 0x00002000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not self._kernel.SetInformationJobObject(
            self._handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)
        ):
            error = self._error("No se pudo garantizar el cierre de los procesos hijos")
            self.close()
            raise error
        return self

    def _resume(self, process: subprocess.Popen[bytes]) -> None:
        # Popen closes the initial thread handle, so find only this owned PID's
        # thread. The child is suspended and cannot have spawned descendants yet.
        snapshot = self._kernel.CreateToolhelp32Snapshot(0x00000004, 0)
        if snapshot == ctypes.c_void_p(-1).value:
            raise self._error("No se pudo localizar el hilo del proceso suspendido")
        try:
            entry = _ThreadEntry()
            entry.size = ctypes.sizeof(entry)
            found = self._kernel.Thread32First(snapshot, ctypes.byref(entry))
            while found:
                if entry.owner == process.pid:
                    thread = self._kernel.OpenThread(0x0002, False, entry.thread)
                    if not thread:
                        raise self._error("No se pudo abrir el hilo del proceso hijo")
                    try:
                        if self._kernel.ResumeThread(thread) == 0xFFFFFFFF:
                            raise self._error("No se pudo iniciar el proceso hijo")
                        return
                    finally:
                        self._kernel.CloseHandle(thread)
                found = self._kernel.Thread32Next(snapshot, ctypes.byref(entry))
            raise WindowsProcessError("No se encontró el hilo del proceso suspendido.")
        finally:
            self._kernel.CloseHandle(snapshot)

    def start(
        self,
        args: Sequence[str | os.PathLike[str]],
        cwd: str | os.PathLike[str],
        env: Mapping[str, str] | None,
        log_path: str | os.PathLike[str] | None,
    ) -> subprocess.Popen[bytes]:
        """Start an owned child; stdout/stderr go to the log or a caller-read PIPE."""
        if self._closed or not self._handle:
            raise WindowsProcessError("Abre el grupo con 'with' antes de iniciar procesos.")
        if isinstance(args, (str, bytes)) or not args:
            raise WindowsProcessError("La orden debe ser una lista de argumentos.")
        process = None
        process_handle = None
        try:
            # The scope keeps logs open until every child has exited, then close() releases them.
            stream = Path(log_path).open("wb") if log_path is not None else subprocess.PIPE  # noqa: SIM115
            if log_path is not None:
                self._streams.append(stream)
            process = subprocess.Popen(
                [os.fspath(argument) for argument in args],
                cwd=cwd,
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=stream,
                stderr=subprocess.STDOUT,
                shell=False,
                creationflags=subprocess.CREATE_NO_WINDOW | 0x00000004,
            )  # CREATE_SUSPENDED: no child code executes before job assignment.
            self._children.append(process)
            process_handle = self._kernel.OpenProcess(0x0100 | 0x0001, False, process.pid)
            if not process_handle or not self._kernel.AssignProcessToJobObject(self._handle, process_handle):
                raise self._error("No se pudo aislar el proceso hijo; inicio cancelado")
            self._resume(process)
            return process
        except BaseException:
            # Assignment may have failed, leaving a suspended child outside the
            # job. Terminate that exact Popen child before closing the whole scope.
            if process is not None:
                with contextlib.suppress(OSError):
                    process.kill()
            self.close()
            raise
        finally:
            if process_handle:
                self._kernel.CloseHandle(process_handle)

    def close(self) -> None:
        """Terminate only this scope's processes and release its log files."""
        if self._closed:
            return
        self._closed = True
        error = None
        if self._handle:
            handle, self._handle = self._handle, None
            try:
                if not self._kernel.TerminateJobObject(handle, 1):
                    error = self._error("No se pudo detener el grupo de procesos")
                else:
                    # Waiting only for Popen misses descendants of wrappers such
                    # as the Python venv redirector. Keep the job handle until its
                    # full tree exits and releases inherited logs/file handles.
                    deadline = time.monotonic() + 10
                    while True:
                        accounting = _BasicAccounting()
                        if not self._kernel.QueryInformationJobObject(
                            handle, 1, ctypes.byref(accounting), ctypes.sizeof(accounting), None
                        ):
                            error = self._error("No se pudo comprobar el cierre de los procesos hijos")
                            break
                        if not accounting.active_processes:
                            break
                        if time.monotonic() >= deadline:
                            error = WindowsProcessError(
                                "El grupo de procesos no confirmó su cierre en diez segundos."
                            )
                            break
                        time.sleep(0.025)
            finally:
                # Kill-on-close remains the fallback, including abrupt supervisor
                # exit or console closure where Python cleanup cannot run.
                if not self._kernel.CloseHandle(handle) and error is None:
                    error = self._error("No se pudo cerrar el grupo de procesos")
        try:
            for process in self._children:
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    error = WindowsProcessError("Un proceso hijo no confirmó su cierre en diez segundos.")
        finally:
            for stream in self._streams:
                stream.close()
            self._streams.clear()
        if error is not None:
            raise error

    def __exit__(self, *_: object) -> None:
        self.close()
