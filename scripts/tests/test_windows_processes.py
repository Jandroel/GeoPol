"""Run with ``python -m unittest discover -s scripts/tests -p test_windows_processes.py``."""

from __future__ import annotations

import ctypes
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from ctypes import wintypes
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from windows_processes import WindowsProcessScope


@unittest.skipUnless(os.name == "nt", "La prueba de Job Objects requiere Windows")
class WindowsProcessScopeTests(unittest.TestCase):
    def test_closing_scope_terminates_its_tree_and_preserves_an_unrelated_process(self):
        for interrupt in (False, True):
            with self.subTest(interrupt=interrupt), tempfile.TemporaryDirectory() as temp:
                self._check_tree(Path(temp), interrupt)

    def _check_tree(self, directory: Path, interrupt: bool) -> None:
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel.WaitForSingleObject.restype = wintypes.DWORD
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel.CloseHandle.restype = wintypes.BOOL

        # This witness is also synthetic and owned by the test, but not by the
        # scope under test. It must stay alive when the scope's job is closed.
        witness = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(60)"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        ready = directory / "tree.json"
        log_path = directory / "child.log"
        script = (
            "import json, os, subprocess, sys, time\n"
            "from pathlib import Path\n"
            "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
            "print('arbol sintetico preparado', flush=True)\n"
            "Path(sys.argv[1]).write_text(json.dumps([os.getpid(), child.pid]), encoding='utf-8')\n"
            "time.sleep(60)\n"
        )
        handles = []
        scope = WindowsProcessScope()
        process = None
        try:
            try:
                with scope:
                    process = scope.start(
                        [sys.executable, "-c", script, str(ready)],
                        cwd=directory,
                        env=os.environ.copy(),
                        log_path=log_path,
                    )
                    deadline = time.monotonic() + 10
                    pids = None
                    while time.monotonic() < deadline:
                        self.assertIsNone(process.poll(), log_path.read_text(errors="replace"))
                        try:
                            pids = json.loads(ready.read_text(encoding="utf-8"))
                            break
                        except (FileNotFoundError, json.JSONDecodeError):
                            time.sleep(0.025)
                    self.assertIsNotNone(pids, "El árbol sintético no llegó a iniciarse")
                    # A venv executable may be a redirector: retain handles to
                    # the returned process, script process, and its descendant.
                    for pid in dict.fromkeys([process.pid, *pids]):
                        handle = kernel.OpenProcess(0x00100000, False, pid)  # SYNCHRONIZE
                        self.assertTrue(handle, "No se pudo observar el proceso sintético")
                        handles.append(handle)
                        self.assertEqual(kernel.WaitForSingleObject(handle, 0), 0x102)
                    if interrupt:
                        raise KeyboardInterrupt
                    scope.close()
            except KeyboardInterrupt:
                if not interrupt:
                    raise
            for handle in handles:
                self.assertEqual(
                    kernel.WaitForSingleObject(handle, 5000),
                    0,
                    "Un proceso del árbol sigue vivo después de cerrar el grupo",
                )
            self.assertIsNotNone(process.poll())
            self.assertIsNone(witness.poll(), "El cierre afectó a un proceso ajeno al grupo")
            scope.close()  # Repeated close and context exit must remain harmless.
            self.assertIn("arbol sintetico preparado", log_path.read_text())
            log_path.unlink()  # The scope released its file handle on Windows.
        finally:
            scope.close()
            for handle in handles:
                kernel.CloseHandle(handle)
            if witness.poll() is None:
                witness.kill()
            witness.wait(timeout=10)


if __name__ == "__main__":
    unittest.main()
