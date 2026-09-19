"""HTTP endpoints for auth."""

import secrets
import time
from collections import defaultdict, deque

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..models import (
    LoginSession,
    User,
)
from ..schemas import LoginInput
from ..security import bearer, current_user, password_hash, token_hash, verify_password
from ..serialization import audit

router = APIRouter()


_login_failures = defaultdict(deque)


_dummy_hash = password_hash(secrets.token_urlsafe(24))


@router.post("/api/auth/login")
def login(payload: LoginInput, request: Request, db: Session = Depends(get_db)):
    key = request.client.host if request.client else "local"
    failures = _login_failures[key]
    now = time.time()
    while failures and failures[0] < now - 60:
        failures.popleft()
    if len(failures) >= 10:
        raise HTTPException(429, "Demasiados intentos. Espere un minuto")
    user = db.scalar(select(User).where(User.username == payload.username))
    valid = verify_password(payload.password, user.password_hash if user else _dummy_hash)
    if not user or not user.active or not valid:
        failures.append(now)
        if len(_login_failures) > 5000:
            _login_failures.clear()
        raise HTTPException(401, "Usuario o contraseña incorrectos")
    token = secrets.token_urlsafe(48)
    db.execute(delete(LoginSession).where(LoginSession.expires_at < now))
    db.add(
        LoginSession(
            token_hash=token_hash(token), user_id=user.id, expires_at=now + settings.session_hours * 3600
        )
    )
    audit(db, user.username, "auth.login", user.id)
    db.commit()
    return {"token": token, "user": {"id": user.id, "username": user.username, "role": user.role}}


@router.get("/api/auth/me")
def me(user: User = Depends(current_user)):
    return {"id": user.id, "username": user.username, "role": user.role}


@router.post("/api/auth/logout")
def logout(credentials=Depends(bearer), user: User = Depends(current_user), db: Session = Depends(get_db)):
    db.execute(delete(LoginSession).where(LoginSession.token_hash == token_hash(credentials.credentials)))
    audit(db, user.username, "auth.logout", user.id)
    db.commit()
    return {"ok": True}
