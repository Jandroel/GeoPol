"""Supervise private POSIX process groups without touching existing services."""

from __future__ import annotations

import contextlib
import os
import signal
import subprocess
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import BinaryIO, Self


class PosixProcessScope:
    """Each child owns a new session; cleanup signals only groups started here."""

    def __init__(self) -> None:
        self._children: list[subprocess.Popen[bytes]] = []
        self._streams: list[BinaryIO] = []
        self._opened = False
        self._closed = False

    def __enter__(self) -> Self:
        if self._opened or self._closed:
            raise RuntimeError("El grupo de procesos ya fue abierto o cerrado.")
        self._opened = True
        return self

    def start(
        self,
        args: Sequence[str | os.PathLike[str]],
        cwd: str | os.PathLike[str],
        env: Mapping[str, str] | None,
        log_path: str | os.PathLike[str] | None,
    ) -> subprocess.Popen[bytes]:
        if not self._opened or self._closed:
            raise RuntimeError("Abre el grupo con 'with' antes de iniciar procesos.")
        if isinstance(args, (str, bytes)) or not args:
            raise RuntimeError("La orden debe ser una lista de argumentos.")
        try:
            stream = Path(log_path).open("wb") if log_path is not None else subprocess.PIPE  # noqa: SIM115
            if log_path is not None:
                self._streams.append(stream)
            child = subprocess.Popen(
                [os.fspath(argument) for argument in args],
                cwd=cwd,
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=stream,
                stderr=subprocess.STDOUT,
                shell=False,
                start_new_session=True,
            )
            self._children.append(child)
            return child
        except BaseException:
            self.close()
            raise

    def _signal_groups(self, signum: int) -> None:
        for child in reversed(self._children):
            # Popen(start_new_session=True) makes the owned child's PID its PGID.
            # Signal the group even if its leader exited: descendants can remain.
            with contextlib.suppress(ProcessLookupError):
                os.killpg(child.pid, signum)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self._signal_groups(signal.SIGTERM)
            deadline = time.monotonic() + 8
            for child in reversed(self._children):
                with contextlib.suppress(subprocess.TimeoutExpired):
                    child.wait(timeout=max(0, deadline - time.monotonic()))
            # Also stop descendants that ignored SIGTERM after their parent exited.
            self._signal_groups(signal.SIGKILL)
            for child in self._children:
                child.wait(timeout=5)
        finally:
            for stream in self._streams:
                stream.close()
            self._streams.clear()

    def __exit__(self, *_: object) -> None:
        self.close()
