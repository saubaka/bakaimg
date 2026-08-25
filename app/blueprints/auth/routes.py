"""Public authentication and self-service account routes."""

from __future__ import annotations

from flask import (
    abort,
    flash,
    make_response,
    redirect,
    render_template,
    session,
    url_for,
)
from flask_login import current_user
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError

from app.blueprints.auth import auth_bp
from app.extensions import db
from app.forms import (
    ApiTokenForm,
    EmptyForm,
    LocalAdminSetupForm,
)
from app.models import (
    ApiToken,
    Role,
    SystemEvent,
    User,
    utc_now,
)
from app.security import (
    normalize_email,
    normalize_username,
    permission_required,
    record_audit,
    validate_password,
)
from app.services.api_tokens import (
    create_api_token,
    revoke_api_token,
)
from app.services.auth import establish_session, log_login
from app.services.identity import sync_identity_foundation
from app.services.local_recovery import (
    claim_local_recovery_token,
    request_is_loopback,
    validate_local_recovery_token,
)


def _active_superadmin() -> User | None:
    return next(
        (
            user
            for user in db.session.scalars(db.select(User).where(User.status == "active"))
            .unique()
            .all()
            if user.has_role("superadmin")
        ),
        None,
    )


def _establish_local_recovery(user: User, reason: str) -> None:
    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = utc_now()
    user.last_seen_at = utc_now()
    establish_session(user)
    session["local_recovery"] = True
    log_login(user, "local-recovery", True, reason)
    record_audit(
        "auth.local_recovery",
        "user",
        str(user.id),
        "本机一次性恢复入口建立管理员会话",
    )


@auth_bp.get("/recovery/local/<token>/")
def local_recovery(token: str):
    if not request_is_loopback() or not claim_local_recovery_token(token):
        abort(404)
    user = _active_superadmin()
    if user is None:
        abort(409)
    _establish_local_recovery(user, "local-recovery")
    db.session.commit()
    flash("本机恢复会话已建立，请及时检查管理员账号安全。", "info")
    return redirect(url_for("admin.dashboard"))


@auth_bp.route("/recovery/local/setup/<token>/", methods=["GET", "POST"])
def local_recovery_setup(token: str):
    if not request_is_loopback() or not validate_local_recovery_token(token):
        abort(404)
    existing = _active_superadmin()
    if existing is not None:
        if not claim_local_recovery_token(token):
            abort(404)
        _establish_local_recovery(existing, "local-recovery")
        db.session.commit()
        flash("检测到已有超级管理员，已建立本机恢复会话。", "info")
        return redirect(url_for("admin.dashboard"))

    form = LocalAdminSetupForm()
    if form.validate_on_submit():
        try:
            username = normalize_username(form.username.data)
            email = normalize_email(form.email.data)
            validate_password(form.password.data, username)
            duplicate = db.session.scalar(
                db.select(User).where(or_(User.username == username, User.email == email))
            )
            if duplicate is not None:
                raise ValueError("用户名或邮箱已被使用。")
            if not claim_local_recovery_token(token):
                abort(404)
            sync_identity_foundation()
            role = db.session.scalar(db.select(Role).where(Role.code == "superadmin"))
            if role is None:
                raise RuntimeError("内置超级管理员角色初始化失败。")
            user = User(
                username=username,
                email=email,
                display_name=form.display_name.data.strip(),
                status="active",
                roles=[role],
            )
            user.set_password(form.password.data)
            db.session.add(user)
            db.session.flush()
            _establish_local_recovery(user, "local-recovery-setup")
            db.session.add(
                SystemEvent(
                    category="security",
                    message="已通过本机一次性入口创建首位超级管理员",
                )
            )
            db.session.commit()
            flash("首位超级管理员已创建，本机恢复票据已经失效。", "success")
            return redirect(url_for("admin.dashboard"))
        except (ValueError, IntegrityError) as error:
            db.session.rollback()
            message = str(error) if isinstance(error, ValueError) else "用户名或邮箱已被使用。"
            flash(message, "error")
    response = make_response(render_template("auth/local_recovery_setup.html", form=form))
    response.headers["Cache-Control"] = "no-store"
    return response


@auth_bp.route("/account/api-tokens/", methods=["GET", "POST"])
@permission_required("api.tokens.manage")
def api_tokens():
    form = ApiTokenForm()
    new_token = None
    if form.validate_on_submit():
        try:
            new_token, token = create_api_token(
                current_user,
                name=form.name.data,
                scopes=set(form.scopes.data),
                expires_days=form.expires_days.data,
            )
            db.session.flush()
            record_audit("api.token.create", "api_token", str(token.id), "创建API令牌")
            db.session.commit()
            flash("应用钥匙已创建，请现在复制保存。", "success")
            form = ApiTokenForm()
        except (ValueError, RuntimeError, IntegrityError) as error:
            db.session.rollback()
            message = (
                str(error)
                if not isinstance(error, IntegrityError)
                else "暂时无法创建，请再试一次。"
            )
            flash(message, "error")
    tokens = db.session.scalars(
        db.select(ApiToken)
        .where(ApiToken.user_id == current_user.id)
        .order_by(ApiToken.created_at.desc())
    ).all()
    response = make_response(
        render_template(
            "auth/api_tokens.html",
            form=form,
            tokens=tokens,
            new_token=new_token,
            now=utc_now(),
            empty_form=EmptyForm(),
        )
    )
    response.headers["Cache-Control"] = "private, no-store"
    return response


@auth_bp.post("/account/api-tokens/<int:token_id>/revoke/")
@permission_required("api.tokens.manage")
def revoke_token(token_id: int):
    form = EmptyForm()
    if not form.validate_on_submit():
        abort(400)
    token = db.session.scalar(
        db.select(ApiToken).where(
            ApiToken.id == token_id,
            ApiToken.user_id == current_user.id,
        )
    )
    if token is None:
        abort(404)
    revoke_api_token(token)
    record_audit("api.token.revoke", "api_token", str(token.id), "用户撤销API令牌")
    db.session.commit()
    flash("应用钥匙已收回。", "success")
    return redirect(url_for("auth.api_tokens"))
