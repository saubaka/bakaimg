"""Hashed API-token lifecycle and bearer authentication."""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from functools import wraps
from typing import Any

from flask import current_app, g, jsonify, request

from app.extensions import db
from app.models import ApiToken, AuditLog, User, utc_now
from app.security import request_fingerprint

VALID_SCOPES = {"images:read", "images:write"}
SCOPE_PERMISSIONS = {
    "images:read": "images.manage_own",
    "images:write": "images.upload",
}


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def hash_token(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def create_api_token(
    user: User,
    *,
    name: str,
    scopes: set[str],
    expires_days: int,
) -> tuple[str, ApiToken]:
    if not scopes or not scopes <= VALID_SCOPES:
        raise ValueError("请选择这把钥匙可以做什么。")
    max_days = int(current_app.config["API_TOKEN_MAX_AGE_DAYS"])
    if not 1 <= expires_days <= max_days:
        raise ValueError(f"有效天数需要在1至{max_days}天之间。")
    now = utc_now()
    active_count = sum(
        1
        for token in user.api_tokens
        if token.revoked_at is None and _aware(token.expires_at) > now
    )
    if active_count >= int(current_app.config["MAX_API_TOKENS_PER_USER"]):
        raise ValueError("应用钥匙数量已满，请先收回不再使用的钥匙。")

    for _attempt in range(8):
        raw_token = f"cn_{secrets.token_urlsafe(32)}"
        prefix = raw_token[:14]
        if db.session.scalar(db.select(ApiToken).where(ApiToken.token_prefix == prefix)) is None:
            break
    else:
        raise RuntimeError("暂时无法创建，请再试一次。")
    token = ApiToken(
        user=user,
        name=name.strip(),
        token_prefix=prefix,
        token_hash=hash_token(raw_token),
        scopes=",".join(sorted(scopes)),
        expires_at=now + timedelta(days=expires_days),
    )
    db.session.add(token)
    return raw_token, token


def revoke_api_token(token: ApiToken) -> None:
    if token.revoked_at is None:
        token.revoked_at = utc_now()


def revoke_user_api_tokens(user: User) -> int:
    revoked = 0
    for token in user.api_tokens:
        if token.revoked_at is None:
            revoke_api_token(token)
            revoked += 1
    return revoked


def record_api_audit(action: str, target_type: str, target_id: str, summary: str) -> None:
    db.session.add(
        AuditLog(
            actor_id=g.api_user.id,
            action=action,
            target_type=target_type,
            target_id=str(target_id)[:80],
            summary=summary[:255],
            request_id=str(g.get("request_id", ""))[:64],
            ip_hash=request_fingerprint("audit"),
        )
    )


def token_required(*required_scopes: str):
    required = set(required_scopes)

    def decorator(view):
        @wraps(view)
        def wrapped(*args: Any, **kwargs: Any):
            header = request.headers.get("Authorization", "")
            scheme, separator, raw_token = header.partition(" ")
            if separator != " " or scheme.lower() != "bearer" or not raw_token:
                return jsonify(error="missing_token", message="请提供Bearer API令牌。"), 401
            digest = hash_token(raw_token)
            token = db.session.scalar(db.select(ApiToken).where(ApiToken.token_hash == digest))
            now = utc_now()
            if (
                token is None
                or not secrets.compare_digest(token.token_hash, digest)
                or token.revoked_at is not None
                or _aware(token.expires_at) <= now
                or not token.user.is_active
            ):
                return jsonify(error="invalid_token", message="API令牌无效或已经过期。"), 401
            if not required <= token.scope_set:
                return jsonify(error="insufficient_scope", message="API令牌缺少所需作用域。"), 403
            for scope in required:
                permission = SCOPE_PERMISSIONS.get(scope)
                if permission and not token.user.has_permission(permission):
                    return jsonify(error="permission_denied", message="账号权限不足。"), 403
            g.api_token = token
            g.api_user = token.user
            if token.last_used_at is None or _aware(token.last_used_at) < now - timedelta(
                minutes=5
            ):
                token.last_used_at = now
                db.session.commit()
            return view(*args, **kwargs)

        return wrapped

    return decorator
