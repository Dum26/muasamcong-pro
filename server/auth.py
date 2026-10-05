"""Account passwords and opaque, database-backed browser sessions."""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import re
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import insert, select, update, delete
from sqlalchemy.exc import IntegrityError

from server.config import production
from server.database import get_db, now, sessions, users

ITERATIONS = 600_000
SESSION_DAYS = 7
_DEV_SECRET = secrets.token_bytes(32)


def _secret() -> bytes:
    configured = os.environ.get("SESSION_SECRET", "")
    if production() and len(configured) < 32:
        raise RuntimeError("Production requires SESSION_SECRET with at least 32 characters.")
    return configured.encode("utf-8") if configured else _DEV_SECRET


def validate_session_config() -> None:
    _secret()


def hash_password(password: str) -> str:
    salt = os.urandom(24)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, ITERATIONS)
    return f"pbkdf2_sha256${ITERATIONS}${base64.b64encode(salt).decode()}${base64.b64encode(digest).decode()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algorithm, rounds, salt, expected = stored.split("$")
        if algorithm != "pbkdf2_sha256" or not 100_000 <= int(rounds) <= 2_000_000:
            return False
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"),
                                     base64.b64decode(salt, validate=True), int(rounds))
        return hmac.compare_digest(actual, base64.b64decode(expected, validate=True))
    except (ValueError, TypeError):
        return False


def public_user(row) -> dict:
    return {"id": row["id"], "email": row["email"], "role": row["role"],
            "created_at": row["created_at"], "last_login_at": row["last_login_at"]}


def register(email: str, password: str) -> dict:
    email = str(email or "").strip().lower()
    if len(email) > 320 or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        raise ValueError("Email không hợp lệ.")
    if not 12 <= len(password) <= 128:
        raise ValueError("Mật khẩu cần từ 12 đến 128 ký tự.")
    import uuid
    item = {"id": uuid.uuid4().hex, "email": email, "password_hash": hash_password(password),
            "role": "user", "created_at": now(), "updated_at": now(),
            "last_login_at": None, "is_active": True}
    try:
        with get_db().engine.begin() as conn:
            conn.execute(insert(users).values(**item))
    except IntegrityError as exc:
        raise ValueError("Email đã được đăng ký.") from exc
    return public_user(item)


def login(email: str, password: str) -> tuple[dict, str]:
    email = str(email or "").strip().lower()
    with get_db().engine.connect() as conn:
        row = conn.execute(select(users).where(users.c.email == email)).mappings().first()
    if not row or not row["is_active"] or not verify_password(password, row["password_hash"]):
        raise ValueError("Email hoặc mật khẩu không đúng.")
    token = secrets.token_urlsafe(32)
    stamp = now()
    expiry = (datetime.now(timezone.utc) + timedelta(days=SESSION_DAYS)).isoformat(timespec="seconds")
    with get_db().engine.begin() as conn:
        conn.execute(insert(sessions).values(token_hash=_token_hash(token), user_id=row["id"],
                                             created_at=stamp, expires_at=expiry))
        conn.execute(update(users).where(users.c.id == row["id"]).values(last_login_at=stamp))
    return {**public_user(row), "last_login_at": stamp}, token


def _token_hash(token: str) -> str:
    return hmac.new(_secret(), token.encode("utf-8"), hashlib.sha256).hexdigest()


def session_user(token: str) -> dict | None:
    if not token or len(token) > 128:
        return None
    with get_db().engine.connect() as conn:
        row = conn.execute(
            select(users, sessions.c.expires_at).join(sessions, sessions.c.user_id == users.c.id)
            .where(sessions.c.token_hash == _token_hash(token), users.c.is_active.is_(True),
                   sessions.c.expires_at > now())
        ).mappings().first()
    return public_user(row) if row else None


def logout(token: str) -> None:
    if token:
        with get_db().engine.begin() as conn:
            conn.execute(delete(sessions).where(sessions.c.token_hash == _token_hash(token)))
