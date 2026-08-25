"""Authentication, authorization and audit helpers."""

from __future__ import annotations

import hashlib
import hmac
import re
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from functools import wraps
from typing import Any
from urllib.parse import urljoin, urlsplit

from flask import abort, current_app, g, request
from flask_login import current_user

from app.extensions import db
from app.models import AuditLog, LoginLog

USERNAME_PATTERN = re.compile(r"[a-z0-9][a-z0-9_.-]{2,49}")
EMAIL_PATTERN = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,189}$")


def normalize_username(value: str) -> str:
    username = value.strip().lower()
    if not USERNAME_PATTERN.fullmatch(username):
        raise ValueError("用户名需为3至50位小写字母、数字、点、下划线或连字符。")
    return username


def normalize_email(value: str) -> str:
    email = value.strip().lower()
    if not EMAIL_PATTERN.fullmatch(email):
        raise ValueError("请输入有效的电子邮箱地址。")
    return email


def validate_password(password: str, username: str = "") -> None:
    if len(password) < 12:
        raise ValueError("密码至少需要12个字符。")
    lowered = password.casefold()
    if username and username.casefold() in lowered:
        raise ValueError("密码不能包含用户名。")
    if not any(character.isalpha() for character in password):
        raise ValueError("密码至少需要包含一个字母。")
    if not any(character.isdigit() for character in password):
        raise ValueError("密码至少需要包含一个数字。")


def permission_required(code: str) -> Callable:
    def decorator(view: Callable) -> Callable:
        @wraps(view)
        def wrapped(*args: Any, **kwargs: Any):
            if not current_user.is_authenticated:
                return current_app.login_manager.unauthorized()
            if not current_user.has_permission(code):
                abort(403)
            return view(*args, **kwargs)

        return wrapped

    return decorator


def request_fingerprint(scope: str) -> str:
    secret = str(current_app.config["SECRET_KEY"]).encode()
    value = f"{scope}|{request.remote_addr or 'unknown'}".encode()
    return hmac.new(secret, value, hashlib.sha256).hexdigest()


def login_is_rate_limited(username: str) -> bool:
    window = datetime.now(UTC) - timedelta(
        seconds=int(current_app.config["LOGIN_RATE_WINDOW_SECONDS"])
    )
    count = db.session.scalar(
        db.select(db.func.count())
        .select_from(LoginLog)
        .where(
            LoginLog.success.is_(False),
            LoginLog.created_at >= window,
            db.or_(
                LoginLog.username == username,
                LoginLog.ip_hash == request_fingerprint("login"),
            ),
        )
    )
    return (count or 0) >= int(current_app.config["LOGIN_RATE_LIMIT"])


def record_audit(action: str, target_type: str, target_id: str = "", summary: str = "") -> None:
    actor_id = current_user.id if current_user.is_authenticated else None
    db.session.add(
        AuditLog(
            actor_id=actor_id,
            action=action,
            target_type=target_type,
            target_id=str(target_id)[:80],
            summary=summary[:255],
            request_id=str(g.get("request_id", ""))[:64],
            ip_hash=request_fingerprint("audit"),
        )
    )


def is_safe_next_url(target: str | None) -> bool:
    if not target:
        return False
    host = urlsplit(request.host_url)
    destination = urlsplit(urljoin(request.host_url, target))
    return destination.scheme in {"http", "https"} and host.netloc == destination.netloc
