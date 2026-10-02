"""Password hashing, signed da'i tokens and anonymous seeker sessions (standard library only)."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time

from .config import settings

PBKDF2_ROUNDS = 240_000
DAAI_TOKEN_TTL = 12 * 3600


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ROUNDS)
    return f"pbkdf2${PBKDF2_ROUNDS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, rounds, salt, digest = stored.split("$")
        calc = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(rounds))
        return hmac.compare_digest(calc.hex(), digest)
    except (ValueError, TypeError):
        return False


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def sign(payload: dict, ttl: int = DAAI_TOKEN_TTL) -> str:
    body = dict(payload, exp=int(time.time()) + ttl)
    raw = _b64(json.dumps(body, separators=(",", ":")).encode())
    mac = hmac.new(settings.secret_key.encode(), raw.encode(), hashlib.sha256).digest()
    return f"{raw}.{_b64(mac)}"


def unsign(token: str) -> dict | None:
    try:
        raw, mac = token.split(".", 1)
        good = hmac.new(settings.secret_key.encode(), raw.encode(), hashlib.sha256).digest()
        if not hmac.compare_digest(_b64(good), mac):
            return None
        body = json.loads(_unb64(raw))
        if body.get("exp", 0) < time.time():
            return None
        return body
    except (ValueError, json.JSONDecodeError):
        return None


def new_seeker_token() -> str:
    return secrets.token_urlsafe(32)


def seeker_id(token: str) -> str:
    """Sessions are stored by hash, so a database leak does not expose live tokens."""
    return hashlib.sha256(token.encode()).hexdigest()


def booking_code() -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(secrets.choice(alphabet) for _ in range(8))
