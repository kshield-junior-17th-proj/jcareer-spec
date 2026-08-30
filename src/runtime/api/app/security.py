from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from .database import get_db
from .models import User


TOKEN_SECRET = os.getenv("SESSION_SIGNING_KEY", "synthetic-local-session-key-change-me")
TOKEN_TTL_SECONDS = int(os.getenv("SESSION_TTL_SECONDS", "43200"))


def hash_password(password: str, salt: str | None = None) -> str:
    salt_bytes = bytes.fromhex(salt) if salt else secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt_bytes, 210_000)
    return f"pbkdf2_sha256${salt_bytes.hex()}${digest.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        _, salt, expected = encoded.split("$", 2)
    except ValueError:
        return False
    actual = hash_password(password, salt).split("$", 2)[2]
    return hmac.compare_digest(actual, expected)


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def issue_token(user: User) -> str:
    payload = {
        "sub": user.id,
        "role": user.role,
        "exp": int(time.time()) + TOKEN_TTL_SECONDS,
    }
    body = _b64(json.dumps(payload, separators=(",", ":")).encode())
    signature = _b64(hmac.new(TOKEN_SECRET.encode(), body.encode(), hashlib.sha256).digest())
    return f"{body}.{signature}"


def parse_token(token: str) -> dict[str, object]:
    try:
        body, supplied_signature = token.split(".", 1)
        expected = _b64(hmac.new(TOKEN_SECRET.encode(), body.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(expected, supplied_signature):
            raise ValueError("signature")
        payload = json.loads(_unb64(body))
        if int(payload["exp"]) < int(time.time()):
            raise ValueError("expired")
        return payload
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        raise HTTPException(status_code=401, detail="유효하지 않거나 만료된 세션입니다")


def current_user(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> User:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="로그인이 필요합니다")
    payload = parse_token(authorization.removeprefix("Bearer ").strip())
    user = db.get(User, str(payload["sub"]))
    if not user or not user.active:
        raise HTTPException(status_code=401, detail="사용할 수 없는 계정입니다")
    return user


def require_role(*roles: str):
    def dependency(user: User = Depends(current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status_code=403, detail="이 작업을 수행할 권한이 없습니다")
        return user

    return dependency
