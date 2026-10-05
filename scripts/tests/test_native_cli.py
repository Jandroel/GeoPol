"""Run the real native CLI entry point with an isolated, mocked backend."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DRIVER = r'''
import json
import os
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path.cwd() / "scripts"))
import native_cli

# Exercise the actual pipe reader with the Windows default code page even on
# Linux CI. No database engine or application code is imported by this test.
sys.stdin.reconfigure(encoding="cp1252", errors="strict")
native_cli.load_config = lambda: {
    "database_url": "postgresql+psycopg://synthetic_app:unused@127.0.0.1/unused",
    "storage_path": str(Path.cwd() / "unused-storage"),
}
backend_cli = types.ModuleType("geopol.cli")
def capture():
    print(json.dumps({
        "password": os.environ["GEOPOL_BOOTSTRAP_PASSWORD"],
        "stdin_encoding": sys.stdin.encoding,
        "args": sys.argv[1:],
        "database_url": os.environ["GEOPOL_DATABASE_URL"],
    }))
backend_cli.main = capture
sys.modules["geopol.cli"] = backend_cli
sys.argv = ["native_cli.py", "bootstrap-user", "--password-stdin"]
native_cli.main()
'''


def invoke(password_bytes):
    environment = {key: value for key, value in os.environ.items() if not key.startswith("GEOPOL_")}
    return subprocess.run(
        [sys.executable, "-c", DRIVER],
        cwd=ROOT,
        input=password_bytes,
        capture_output=True,
        env=environment,
        check=False,
        timeout=20,
    )


@pytest.mark.parametrize("password", ["Contraseña-única-2026", "Clavé-ñ-🔑-completa"])
def test_bootstrap_preserves_utf8_password_when_stdin_uses_windows_code_page(password):
    result = invoke(password.encode("utf-8"))
    assert result.returncode == 0, result.stderr.decode(errors="replace")
    captured = json.loads(result.stdout)
    assert captured["stdin_encoding"] == "cp1252"
    assert captured["password"] == password
    assert captured["args"] == ["bootstrap-user"]
    assert captured["database_url"].startswith("postgresql+psycopg://synthetic_app:")


def test_bootstrap_rejects_non_utf8_input_without_echoing_password_or_traceback():
    result = invoke(b"secret-invalid-\xff-password")
    assert result.returncode != 0
    assert b"UTF-8" in result.stderr
    assert b"secret-invalid" not in result.stderr
    assert b"Traceback" not in result.stderr
    assert result.stdout == b""
