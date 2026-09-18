import hashlib
import hmac
import secrets
import time

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import get_db
from .models import LoginSession, User

bearer = HTTPBearer(auto_error=False)


def password_hash(password: str) -> str:
    if len(password) < 12:
        raise ValueError("La contraseña debe tener al menos 12 caracteres")
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 600_000)
    return f"pbkdf2_sha256$600000${salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        _, iterations, salt, expected = encoded.split("$")
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(iterations))
        return hmac.compare_digest(actual.hex(), expected)
    except (ValueError, TypeError):
        return False


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer), db: Session = Depends(get_db)
) -> User:
    if not credentials:
        raise HTTPException(401, "Inicie sesión para continuar")
    session = db.get(LoginSession, token_hash(credentials.credentials))
    if session is None or session.expires_at <= time.time():
        raise HTTPException(401, "Sesión inválida o expirada")
    user = db.scalar(select(User).where(User.id == session.user_id, User.active.is_(True)))
    if not user:
        raise HTTPException(401, "Usuario inactivo")
    return user


def roles(*allowed):
    def dependency(user: User = Depends(current_user)):
        if user.role not in allowed:
            raise HTTPException(403, "Su rol no permite esta operación")
        return user

    return dependency
