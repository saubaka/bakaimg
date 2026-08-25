"""Database-backed browser sessions and login logging."""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from flask import current_app, g, request, session
from flask_login import login_user, logout_user

from app.extensions import db
from app.models import LoginLog, User, UserSession, utc_now
from app.security import request_fingerprint

SESSION_KEY = "cloudnest_user_session"


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def establish_session(user: User, *, remember: bool = False) -> UserSession:
    session.clear()
    session.permanent = True
    token = secrets.token_urlsafe(32)
    lifetime = current_app.permanent_session_lifetime
    if remember:
        lifetime = timedelta(days=30)
    item = UserSession(
        user_id=user.id,
        token_hash=hash_token(token),
        ip_hash=request_fingerprint("session"),
        user_agent=request.user_agent.string[:255],
        expires_at=utc_now() + lifetime,
    )
    db.session.add(item)
    db.session.flush()
    session[SESSION_KEY] = token
    session["user_session_id"] = item.id
    login_user(user, remember=False, fresh=True)
    return item


def current_session() -> UserSession | None:
    token = session.get(SESSION_KEY)
    if not isinstance(token, str) or not token:
        return None
    return db.session.scalar(
        db.select(UserSession).where(UserSession.token_hash == hash_token(token))
    )


def session_is_valid(item: UserSession | None) -> bool:
    return bool(
        item is not None
        and item.revoked_at is None
        and item.user.is_active
        and _aware(item.expires_at) > datetime.now(UTC)
    )


def validate_browser_session() -> UserSession | None:
    from flask_login import current_user

    if not current_user.is_authenticated:
        return None
    item = current_session()
    if not session_is_valid(item) or item is None or item.user_id != current_user.id:
        logout_user()
        session.clear()
        return None
    now = utc_now()
    interval = timedelta(seconds=int(current_app.config["SESSION_TOUCH_INTERVAL_SECONDS"]))
    if now - _aware(item.last_seen_at) >= interval:
        item.last_seen_at = now
        item.user.last_seen_at = now
        db.session.commit()
    g.user_session = item
    return item


def revoke_session(item: UserSession) -> None:
    if item.revoked_at is None:
        item.revoked_at = utc_now()


def revoke_other_sessions(user: User, current_id: int | None = None) -> int:
    items = db.session.scalars(
        db.select(UserSession).where(
            UserSession.user_id == user.id,
            UserSession.revoked_at.is_(None),
        )
    ).all()
    changed = 0
    for item in items:
        if item.id == current_id:
            continue
        revoke_session(item)
        changed += 1
    return changed


def end_current_session() -> None:
    item = current_session()
    if item is not None:
        revoke_session(item)
        db.session.commit()
    logout_user()
    session.clear()


def log_login(user: User | None, username: str, success: bool, reason: str) -> None:
    db.session.add(
        LoginLog(
            user_id=user.id if user else None,
            username=username[:80],
            success=success,
            reason=reason[:80],
            request_id=str(g.get("request_id", ""))[:64],
            ip_hash=request_fingerprint("login"),
            user_agent=request.user_agent.string[:255],
        )
    )
