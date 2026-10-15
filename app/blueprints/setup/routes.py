"""The first-run initialisation page."""

from __future__ import annotations

from flask import current_app, flash, make_response, redirect, render_template, url_for
from sqlalchemy.exc import IntegrityError

from app.blueprints.admin import DEFAULT_ADMIN_PATH, reserved_admin_paths
from app.blueprints.setup import setup_bp
from app.extensions import db
from app.forms import SetupForm
from app.models import Role, User
from app.security import normalize_email, normalize_username, record_audit, validate_password
from app.services.auth import establish_session, log_login
from app.services.identity import seed_settings, set_setting, sync_identity_foundation
from app.services.setup import setup_needed


def _page(form: SetupForm):
    response = make_response(render_template("setup/index.html", form=form))
    response.headers["Cache-Control"] = "no-store"
    return response


@setup_bp.route("/", methods=["GET", "POST"])
def index():
    if not setup_needed():
        return redirect(url_for("public.home"))
    form = SetupForm()
    if form.is_submitted() and form.validate():
        try:
            admin_path = form.admin_path.data.strip().lower()
            if admin_path in reserved_admin_paths():
                raise ValueError("这个路径已经被站点其他页面使用，请换一个。")
            username = normalize_username(form.username.data)
            email = normalize_email(form.email.data)
            validate_password(form.password.data, username)
            seed_settings()
            sync_identity_foundation()
            role = db.session.scalar(db.select(Role).where(Role.code == "superadmin"))
            if role is None:
                raise RuntimeError("内置角色初始化失败，请稍后再试。")
            set_setting("site_name", form.site_name.data.strip())
            set_setting("admin_path", admin_path)
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
            establish_session(user)
            log_login(user, username, True, "setup")
            record_audit("setup.complete", "user", str(user.id), "完成初始化并创建管理员")
            db.session.commit()
            current_app.extensions["setup_complete"] = True
            flash(f"初始化完成，欢迎你，{user.display_name}。", "success")
            return redirect(url_for("admin.dashboard", admin_path=admin_path))
        except (ValueError, RuntimeError, IntegrityError) as error:
            db.session.rollback()
            flash(
                "用户名或邮箱已被使用。" if isinstance(error, IntegrityError) else str(error),
                "error",
            )
    elif not form.is_submitted():
        form.admin_path.data = DEFAULT_ADMIN_PATH
    return _page(form)
