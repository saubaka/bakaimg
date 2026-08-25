"""bakaimg Flask application factory."""

from __future__ import annotations

import os
import re
from pathlib import Path
from uuid import uuid4

from flask import Flask, g, jsonify, redirect, render_template, request, session, url_for
from flask_login import current_user
from sqlalchemy import event
from sqlalchemy.engine import Engine
from werkzeug.middleware.proxy_fix import ProxyFix

from app.config import CONFIGS, BaseConfig
from app.extensions import csrf, db, login_manager, migrate


@event.listens_for(Engine, "connect")
def _configure_sqlite(connection, _record) -> None:  # type: ignore[no-untyped-def]
    if not connection.__class__.__module__.startswith("sqlite3"):
        return
    cursor = connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.close()


def create_app(
    config_name: str | None = None,
    test_config: dict[str, object] | None = None,
    instance_path: str | None = None,
) -> Flask:
    selected = config_name or os.getenv("CLOUDNEST_ENV", "development")
    config_class = CONFIGS.get(selected, BaseConfig)
    instance_path = instance_path or os.getenv("CLOUDNEST_INSTANCE_PATH")

    app = Flask(__name__, instance_relative_config=True, instance_path=instance_path)
    app.config.from_object(config_class)

    runtime_secret = os.getenv("CLOUDNEST_SECRET_KEY")
    if runtime_secret:
        app.config["SECRET_KEY"] = runtime_secret
    runtime_site_url = os.getenv("CLOUDNEST_SITE_URL")
    if runtime_site_url:
        app.config["SITE_URL"] = runtime_site_url.rstrip("/")
    runtime_proxy_hops = os.getenv("CLOUDNEST_TRUST_PROXY_HOPS")
    if runtime_proxy_hops:
        try:
            app.config["TRUST_PROXY_HOPS"] = int(runtime_proxy_hops)
        except ValueError as error:
            raise RuntimeError("CLOUDNEST_TRUST_PROXY_HOPS必须是0到3的整数。") from error

    instance_config = Path(app.instance_path) / "config.py"
    if instance_config.exists():
        app.config.from_pyfile("config.py", silent=False)
    if test_config:
        app.config.update(test_config)

    _ensure_instance_directories(app)
    if not app.config.get("SQLALCHEMY_DATABASE_URI"):
        database_path = (Path(app.instance_path) / "data" / "cloudnest.db").resolve()
        app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{database_path.as_posix()}"

    _validate_production_config(app)
    trusted_hops = int(app.config["TRUST_PROXY_HOPS"])
    if trusted_hops:
        app.wsgi_app = ProxyFix(
            app.wsgi_app,
            x_for=trusted_hops,
            x_proto=trusted_hops,
            x_host=trusted_hops,
        )
    db.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)
    login_manager.init_app(app)

    from app.blueprints.admin import admin_bp
    from app.blueprints.api import api_bp
    from app.blueprints.auth import auth_bp
    from app.blueprints.gateway import gateway_bp
    from app.blueprints.images import images_bp
    from app.blueprints.public import public_bp
    from app.cli import register_commands

    app.register_blueprint(public_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(gateway_bp)
    app.register_blueprint(images_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(admin_bp)
    csrf.exempt(api_bp)
    register_commands(app)
    _register_hooks(app)
    _register_context(app)
    _register_errors(app)
    return app


def _ensure_instance_directories(app: Flask) -> None:
    for name in ("data", "uploads", "cache", "logs", "backups", "tmp"):
        (Path(app.instance_path) / name).mkdir(parents=True, exist_ok=True)


def _validate_production_config(app: Flask) -> None:
    trusted_hops = app.config.get("TRUST_PROXY_HOPS", 0)
    if not isinstance(trusted_hops, int) or not 0 <= trusted_hops <= 3:
        raise RuntimeError("CLOUDNEST_TRUST_PROXY_HOPS必须是0到3的整数。")
    if not app.config.get("TESTING") and app.config["ENV_NAME"] == "production":
        if app.config["SECRET_KEY"] == app.config["DEFAULT_SECRET_KEY"]:
            raise RuntimeError("生产环境必须设置独立的CLOUDNEST_SECRET_KEY。")
        if not str(app.config["SITE_URL"]).startswith("https://"):
            raise RuntimeError("生产环境CLOUDNEST_SITE_URL必须使用HTTPS。")


def _register_hooks(app: Flask) -> None:
    from app.models import User, utc_now
    from app.services.auth import validate_browser_session

    @login_manager.user_loader
    def load_user(user_id: str) -> User | None:
        return db.session.get(User, int(user_id)) if user_id.isdigit() else None

    @app.before_request
    def begin_request() -> None:
        from flask_login import logout_user

        from app.services.auth import current_session
        from app.services.gateway import current_gateway_session, gateway_is_enabled

        supplied = request.headers.get("X-Request-ID", "")
        g.request_id = supplied[:64] if supplied.isascii() and supplied.isalnum() else uuid4().hex
        validate_browser_session()
        g.gateway_session = current_gateway_session(validate_remote=True)
        if (
            current_user.is_authenticated
            and gateway_is_enabled()
            and not session.get("local_recovery")
            and (g.gateway_session is None or g.gateway_session.linked_user_id != current_user.id)
        ):
            local_session = current_session()
            if local_session is not None:
                local_session.revoked_at = utc_now()
                db.session.commit()
            logout_user()
            session.clear()
            return redirect(
                url_for(
                    "gateway.login",
                    intent=("admin" if request.path.startswith("/admin/") else "frontend"),
                    next=request.full_path if request.query_string else request.path,
                )
            )
        maintenance_response = _maintenance_response()
        if maintenance_response is not None:
            return maintenance_response
        return None

    @app.after_request
    def secure_response(response):  # type: ignore[no-untyped-def]
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=(), payment=(), usb=()"
        )
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "base-uri 'self'; "
            "form-action 'self'; "
            "frame-ancestors 'none'; "
            "img-src 'self' data: blob:; "
            "style-src 'self'; "
            "script-src 'self'; "
            "font-src 'self'"
        )
        response.headers["X-Request-ID"] = g.get("request_id", uuid4().hex)
        if app.config["ENV_NAME"] == "production":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response


def _register_context(app: Flask) -> None:
    def format_bytes(value: int) -> str:
        amount = float(value)
        for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
            if amount < 1024 or unit == "TiB":
                return f"{amount:.0f} {unit}" if unit == "B" else f"{amount:.1f} {unit}"
            amount /= 1024
        return f"{amount:.1f} TiB"

    @app.context_processor
    def inject_site_context() -> dict[str, object]:
        from app.services.appearance import (
            DIALOG_APPEARANCE_DEFAULTS,
            DIALOG_SHADOW_VALUES,
            DIALOG_STYLE_VALUES,
            PAGE_TRANSITION_COLOR_DEFAULTS,
            PAGE_TRANSITION_VALUES,
        )
        from app.services.gateway import gateway_is_enabled
        from app.services.identity import get_setting

        def setting(key: str, default: str) -> str:
            try:
                return get_setting(key, default)
            except Exception:
                db.session.rollback()
                return default

        def safe_color(key: str, default: str) -> str:
            value = setting(key, default)
            return value if re.fullmatch(r"#[0-9A-Fa-f]{6}", value or "") else default

        def safe_number(key: str, default: int, minimum: int, maximum: int) -> int:
            try:
                value = int(setting(key, str(default)))
            except (TypeError, ValueError):
                value = default
            return max(minimum, min(maximum, value))

        transition_style = setting("page_transition_style", "stretch")
        if transition_style not in PAGE_TRANSITION_VALUES:
            transition_style = "stretch"
        dialog_style = setting("dialog_style", DIALOG_APPEARANCE_DEFAULTS["dialog_style"])
        if dialog_style not in DIALOG_STYLE_VALUES:
            dialog_style = "soft"
        dialog_shadow = setting("dialog_shadow", DIALOG_APPEARANCE_DEFAULTS["dialog_shadow"])
        if dialog_shadow not in DIALOG_SHADOW_VALUES:
            dialog_shadow = "soft"

        return {
            "app_version": app.config["APP_VERSION"],
            "system_name": app.config["SYSTEM_NAME"],
            "system_name_en": app.config["SYSTEM_NAME_EN"],
            "site_name": app.config["SITE_NAME"],
            "site_tagline": app.config["SITE_TAGLINE"],
            "page_transition_style": transition_style,
            "page_transition_duration": safe_number("page_transition_duration", 720, 300, 2400),
            "page_transition_color_start": safe_color(
                "page_transition_color_start",
                PAGE_TRANSITION_COLOR_DEFAULTS["page_transition_color_start"],
            ),
            "page_transition_color_middle": safe_color(
                "page_transition_color_middle",
                PAGE_TRANSITION_COLOR_DEFAULTS["page_transition_color_middle"],
            ),
            "page_transition_color_end": safe_color(
                "page_transition_color_end",
                PAGE_TRANSITION_COLOR_DEFAULTS["page_transition_color_end"],
            ),
            "admin_menu_subtitles_visible": setting("admin_menu_subtitles_visible", "false")
            .strip()
            .lower()
            in {"1", "true", "yes", "on"},
            "dialog_style": dialog_style,
            "dialog_color_start": safe_color(
                "dialog_color_start", DIALOG_APPEARANCE_DEFAULTS["dialog_color_start"]
            ),
            "dialog_color_end": safe_color(
                "dialog_color_end", DIALOG_APPEARANCE_DEFAULTS["dialog_color_end"]
            ),
            "dialog_accent": safe_color(
                "dialog_accent", DIALOG_APPEARANCE_DEFAULTS["dialog_accent"]
            ),
            "dialog_radius": safe_number("dialog_radius", 30, 14, 42),
            "dialog_width": safe_number("dialog_width", 510, 360, 720),
            "dialog_backdrop_blur": safe_number("dialog_backdrop_blur", 6, 0, 30),
            "dialog_shadow": dialog_shadow,
            "format_bytes": format_bytes,
            "gateway_identity": g.get("gateway_session"),
            "gateway_enabled": gateway_is_enabled(),
        }


def _register_errors(app: Flask) -> None:
    for status in (400, 403, 404, 413, 500):
        app.register_error_handler(
            status,
            lambda error, code=status: (
                render_template("errors/error.html", status_code=code),
                code,
            ),
        )


def _maintenance_response():  # type: ignore[no-untyped-def]
    """Keep operator, sign-in and probes reachable while pausing public delivery."""

    from app.services.identity import get_setting

    try:
        enabled = get_setting("maintenance_mode", "false") == "true"
    except Exception:
        db.session.rollback()
        return None
    if not enabled:
        return None
    if request.endpoint in {"static", "public.healthcheck", "public.readiness_check"}:
        return None
    if request.blueprint in {"admin", "auth", "gateway"}:
        return None
    if current_user.is_authenticated and current_user.has_permission("system.maintain"):
        return None
    message = get_setting(
        "maintenance_message",
        "正在整理图片，请稍后再来。",
    )
    if request.blueprint == "api" or request.path.startswith("/api/"):
        response = jsonify(error="maintenance", message=message)
    else:
        response = render_template("errors/maintenance.html", message=message)
    return response, 503, {"Retry-After": "300", "Cache-Control": "no-store"}
