"""Short-lived, loopback-only local administrator recovery tickets."""

from __future__ import annotations

import hashlib
import ipaddress
import json
import os
import secrets
import stat
import time
from contextlib import suppress
from pathlib import Path

from flask import current_app, request

RECOVERY_TTL_SECONDS = 5 * 60
RECOVERY_FILENAME = "local-admin-recovery.json"


def request_is_loopback() -> bool:
    addresses = [request.remote_addr or ""]
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        addresses.extend(part.strip() for part in forwarded.split(","))
    addresses = [address for address in addresses if address]
    try:
        return bool(addresses) and all(
            ipaddress.ip_address(address).is_loopback for address in addresses
        )
    except ValueError:
        return False


def _recovery_path() -> Path:
    directory = Path(current_app.instance_path) / "tmp"
    directory.mkdir(parents=True, exist_ok=True)
    return directory / RECOVERY_FILENAME


def _token_matches(raw_token: str, payload: object) -> bool:
    if not isinstance(payload, dict):
        return False
    try:
        expected = str(payload.get("token_hash") or "")
        expires_at = int(payload.get("expires_at") or 0)
    except (TypeError, ValueError):
        return False
    actual = hashlib.sha256(raw_token.encode()).hexdigest()
    return expires_at >= int(time.time()) and secrets.compare_digest(expected, actual)


def create_local_recovery_token() -> str:
    raw_token = secrets.token_urlsafe(36)
    payload = {
        "token_hash": hashlib.sha256(raw_token.encode()).hexdigest(),
        "expires_at": int(time.time()) + RECOVERY_TTL_SECONDS,
    }
    target = _recovery_path()
    temporary = target.with_name(f".{target.name}.{secrets.token_hex(6)}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=True, separators=(",", ":")),
        encoding="utf-8",
    )
    with suppress(OSError):
        temporary.chmod(stat.S_IRUSR | stat.S_IWUSR)
    os.replace(temporary, target)
    return raw_token


def validate_local_recovery_token(raw_token: str) -> bool:
    if not raw_token or len(raw_token) > 200:
        return False
    try:
        payload = json.loads(_recovery_path().read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return False
    return _token_matches(raw_token, payload)


def claim_local_recovery_token(raw_token: str) -> bool:
    if not raw_token or len(raw_token) > 200:
        return False
    target = _recovery_path()
    claimed = target.with_name(f".{target.name}.{secrets.token_hex(6)}.claimed")
    try:
        os.replace(target, claimed)
    except FileNotFoundError:
        return False
    try:
        payload = json.loads(claimed.read_text(encoding="utf-8"))
        return _token_matches(raw_token, payload)
    except (OSError, json.JSONDecodeError):
        return False
    finally:
        claimed.unlink(missing_ok=True)
