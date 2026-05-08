from __future__ import annotations

import base64
import hashlib
import hmac
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt

from app.core.config import get_settings


def hash_secret(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def verify_secret(plain_value: str, hashed_value: str) -> bool:
    digest = hash_secret(plain_value)
    return hmac.compare_digest(digest, hashed_value)


def create_access_token(subject: str, extra: dict[str, Any] | None = None) -> str:
    settings = get_settings()
    expire_at = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
    payload: dict[str, Any] = {"sub": subject, "exp": expire_at}
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def decode_access_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    return jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])


def encrypt_text(value: str) -> str:
    settings = get_settings()
    key = settings.encrypt_secret.encode("utf-8")
    raw = value.encode("utf-8")
    result = bytes(b ^ key[i % len(key)] for i, b in enumerate(raw))
    return base64.urlsafe_b64encode(result).decode("utf-8")


def decrypt_text(value: str) -> str:
    settings = get_settings()
    key = settings.encrypt_secret.encode("utf-8")
    raw = base64.urlsafe_b64decode(value.encode("utf-8"))
    result = bytes(b ^ key[i % len(key)] for i, b in enumerate(raw))
    return result.decode("utf-8")
