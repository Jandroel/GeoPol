import hashlib
import os
import time
from contextlib import contextmanager
from pathlib import Path

from fastapi import HTTPException

from .config import settings


def storage_file(kind: str, identifier: str, suffix="") -> Path:
    # Identifiers are generated internally, never constructed from uploaded names.
    if kind not in {"uploads", "exports", "references"} or any(
        c not in "0123456789abcdef-" for c in identifier
    ):
        raise ValueError("Identificador de almacenamiento inválido")
    directory = settings.storage_path.resolve() / kind
    directory.mkdir(parents=True, exist_ok=True)
    return directory / f"{identifier}{suffix}"


def checksum(path: Path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


@contextmanager
def upload_lock(identifier):
    lock = storage_file("uploads", identifier, ".lock")
    try:
        handle = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        # Never steal a potentially live writer. An abandoned lock needs operator inspection.
        raise HTTPException(
            409, "La carga está ocupada. Si persiste, revise el bloqueo de carga en el servidor"
        )
    try:
        os.write(handle, f"{os.getpid()} {time.time()}".encode())
        yield
    finally:
        os.close(handle)
        lock.unlink(missing_ok=True)
