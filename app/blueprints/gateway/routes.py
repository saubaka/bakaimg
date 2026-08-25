"""Cloudgate-only login, callback, avatar and logout routes."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from flask import (
    Response,
    abort,
    flash,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_login import current_user, logout_user

from app.blueprints.gateway import gateway_bp
from app.extensions import db
from app.models import LoginLog, Role, User
from app.security import (
    normalize_email,
    normalize_username,
    record_audit,
    request_fingerprint,
)
from app.services.auth import current_session, establish_session
from app.services.gateway import (
    GATEWAY_SESSION_KEY,
    GatewayError,
    begin_authorization,
    complete_authorization,
    establish_gateway_session,
    gateway_intent_is_allowed,
    gateway_is_enabled,
    gateway_picture_url_is_safe,
    gateway_portal_url,
    safe_local_target,
    terminate_gateway_session,
)
from app.services.identity import sync_identity_foundation


def _available_username(preferred: str, subject: str) -> str:
    try:
        base = normalize_username(preferred)
    except ValueError:
        base = f"cloud_{hashlib.sha256(subject.encode()).hexdigest()[:12]}"
    candidate = base
    suffix = 2
    while db.session.scalar(db.select(User.id).where(User.username == candidate)):
        tail = f"-{suffix}"
        candidate = f"{base[: 50 - len(tail)]}{tail}"
        suffix += 1
    return candidate


def _available_email(value: str, subject: str) -> str:
    try:
        candidate = normalize_email(value)
    except ValueError:
        candidate = ""
    if candidate and not db.session.scalar(db.select(User.id).where(User.email == candidate)):
        return candidate
    digest = hashlib.sha256(subject.encode()).hexdigest()[:24]
    return f"gateway-{digest}@cloudnest.invalid"


def _local_user_for_gateway(identity) -> User:  # type: ignore[no-untyped-def]
    user = db.session.scalar(
        db.select(User).where(User.gateway_subject == identity.gateway_subject)
    )
    if user is not None:
        if identity.display_name:
            user.display_name = identity.display_name[:80]
        if identity.email:
            try:
                email = normalize_email(identity.email)
            except ValueError:
                email = ""
            duplicate = (
                db.session.scalar(
                    db.select(User.id).where(
                        User.email == email,
                        User.id != user.id,
                    )
                )
                if email
                else None
            )
            if email and duplicate is None:
                user.email = email
        return user

    sync_identity_foundation()
    member = db.session.scalar(db.select(Role).where(Role.code == "member"))
    if member is None:
        raise GatewayError("账号基础尚未初始化。")
    user = User(
        username=_available_username(
            identity.preferred_username,
            identity.gateway_subject,
        ),
        email=_available_email(identity.email, identity.gateway_subject),
        display_name=identity.display_name[:80],
        password_hash="!",
        status="active",
        gateway_subject=identity.gateway_subject,
        roles=[member],
    )
    db.session.add(user)
    db.session.flush()
    record_audit(
        "gateway.user.provision",
        "user",
        str(user.id),
        f"从统一登录身份创建本地图片账号 {identity.preferred_username}",
    )
    return user


def _establish_local_session(user: User, identity) -> None:  # type: ignore[no-untyped-def]
    raw_gateway_session = session.get(GATEWAY_SESSION_KEY)
    establish_session(user)
    if raw_gateway_session:
        session[GATEWAY_SESSION_KEY] = raw_gateway_session
    identity.linked_user_id = user.id
    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = datetime.now(UTC)
    user.last_seen_at = datetime.now(UTC)
    log = LoginLog(
        user_id=user.id,
        username=f"gateway:{identity.preferred_username}"[:80],
        success=True,
        reason="cloudgate",
        request_id=str(g.get("request_id", ""))[:64],
        ip_hash=request_fingerprint("login"),
        user_agent=request.user_agent.string[:255],
    )
    db.session.add(log)


@gateway_bp.get("/login/")
def login():
    intent = request.args.get("intent", "frontend")
    if intent not in {"frontend", "admin", "link_admin"}:
        abort(400)
    if not gateway_intent_is_allowed(intent):
        abort(404)
    next_target = safe_local_target(request.args.get("next"), "/")
    if intent == "link_admin" and (
        not current_user.is_authenticated or not current_user.has_permission("admin.access")
    ):
        abort(403)
    if intent == "admin" and current_user.is_authenticated:
        return redirect(url_for("admin.dashboard"))
    if intent == "frontend" and g.get("gateway_session") is not None:
        return redirect(next_target)
    return render_template(
        "gateway/waiting.html",
        continue_url=url_for(
            "gateway.login_continue",
            intent=intent,
            next=next_target,
        ),
    )


@gateway_bp.get("/login/continue/")
def login_continue():
    intent = request.args.get("intent", "frontend")
    if intent not in {"frontend", "admin", "link_admin"}:
        abort(400)
    if not gateway_intent_is_allowed(intent):
        abort(404)
    next_target = safe_local_target(request.args.get("next"), "/")
    if intent == "link_admin" and (
        not current_user.is_authenticated or not current_user.has_permission("admin.access")
    ):
        abort(403)
    try:
        return redirect(begin_authorization(intent, next_target))
    except GatewayError:
        flash("暂时无法打开登录，请稍后再试。", "error")
        return redirect(
            url_for("admin.gateway_settings") if intent == "link_admin" else url_for("public.home")
        )


@gateway_bp.get("/callback/")
def callback():
    try:
        flow, tokens, userinfo = complete_authorization()
        if not gateway_intent_is_allowed(str(flow.get("intent", ""))):
            raise GatewayError("这个登录入口已经由管理员关闭。")
        identity = establish_gateway_session(tokens, userinfo)
    except GatewayError:
        db.session.rollback()
        flash("登录没有完成，请重新试一次。", "error")
        return redirect(url_for("public.home"))

    intent = str(flow["intent"])
    next_target = safe_local_target(str(flow.get("next") or ""), "/")
    if intent == "link_admin":
        if not current_user.is_authenticated or not current_user.has_permission("admin.access"):
            db.session.rollback()
            abort(403)
        conflict = db.session.scalar(
            db.select(User).where(
                User.gateway_subject == identity.gateway_subject,
                User.id != current_user.id,
            )
        )
        if conflict is not None:
            db.session.rollback()
            flash("这个账号已经绑定到另一位本地账号。", "error")
            return redirect(url_for("admin.gateway_settings"))
        current_user.gateway_subject = identity.gateway_subject
        identity.linked_user_id = current_user.id
        session.pop("local_recovery", None)
        record_audit(
            "gateway.identity.link",
            "user",
            str(current_user.id),
            f"绑定统一登录账号 {identity.preferred_username}",
        )
        db.session.commit()
        flash("登录账号已经与当前管理员绑定。", "success")
        return redirect(url_for("admin.gateway_settings"))

    user = db.session.scalar(
        db.select(User).where(User.gateway_subject == identity.gateway_subject)
    )
    if intent == "admin":
        success = bool(user and user.is_active and user.has_permission("admin.access"))
        if not success or user is None:
            db.session.add(
                LoginLog(
                    user_id=user.id if user else None,
                    username=f"gateway:{identity.preferred_username}"[:80],
                    success=False,
                    reason="admin-not-bound",
                    request_id=str(g.get("request_id", ""))[:64],
                    ip_hash=request_fingerprint("login"),
                    user_agent=request.user_agent.string[:255],
                )
            )
            db.session.commit()
            flash("这个账号还不能进入管理后台。", "error")
            return redirect(url_for("public.home"))
    else:
        user = _local_user_for_gateway(identity)

    if user is None or not user.is_active:
        db.session.commit()
        flash("这个账号暂时无法登录。", "error")
        return redirect(url_for("public.home"))
    _establish_local_session(user, identity)
    db.session.commit()
    flash(f"欢迎回来，{identity.display_name}。", "success")
    if intent == "admin":
        return redirect(
            next_target if next_target.startswith("/admin/") else url_for("admin.dashboard")
        )
    return redirect(next_target)


@gateway_bp.get("/portal/")
def portal():
    if not gateway_is_enabled():
        abort(404)
    return redirect(gateway_portal_url())


@gateway_bp.get("/avatar/")
def avatar():
    identity = g.get("gateway_session")
    if (
        identity is None
        or not identity.avatar_url
        or not gateway_picture_url_is_safe(identity.avatar_url)
    ):
        abort(404)
    outbound = Request(
        identity.avatar_url,
        headers={
            "Accept": "image/png,image/jpeg,image/webp",
            "User-Agent": "Cloudnest-Avatar-Proxy",
        },
    )
    try:
        with urlopen(outbound, timeout=4) as upstream:  # noqa: S310
            content_type = upstream.headers.get_content_type()
            if content_type not in {"image/png", "image/jpeg", "image/webp"}:
                abort(404)
            payload = upstream.read(2 * 1024 * 1024 + 1)
    except (HTTPError, URLError, TimeoutError, OSError):
        abort(404)
    if len(payload) > 2 * 1024 * 1024:
        abort(404)
    response = Response(payload, content_type=content_type)
    response.cache_control.private = True
    response.cache_control.max_age = 300
    return response


@gateway_bp.post("/logout/")
def logout():
    identity = g.get("gateway_session")
    local_session = current_session() if current_user.is_authenticated else None
    terminate_gateway_session(identity)
    if local_session is not None:
        local_session.revoked_at = datetime.now(UTC)
        db.session.commit()
    logout_user()
    session.clear()
    flash("已经退出登录。", "info")
    return redirect(url_for("public.home"))


@gateway_bp.get("/status/")
def status():
    identity = g.get("gateway_session")
    enabled = gateway_is_enabled()
    response = jsonify(
        {
            "ok": True,
            "enabled": enabled,
            "capabilities": {
                "frontend_login": enabled,
                "registration": False,
                "admin_login": enabled,
            },
            "authenticated": identity is not None,
            "identity": (
                {
                    "sub": identity.gateway_subject,
                    "preferred_username": identity.preferred_username,
                    "name": identity.display_name,
                    "email": identity.email,
                    "email_verified": identity.email_verified,
                    "picture": identity.avatar_url,
                    "linked_user": identity.linked_user_id is not None,
                }
                if identity is not None
                else None
            ),
        }
    )
    response.headers["Cache-Control"] = "no-store"
    return response
