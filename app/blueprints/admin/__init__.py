"""Administration blueprint.

The back office lives under a path the owner can change (``/bakaadmin/`` by default). The path is
stored in the site settings and injected into every admin URL, so templates and redirects keep
using ``url_for('admin.…')`` and never hard-code it.
"""

from __future__ import annotations

import re

from flask import Blueprint, abort, current_app, g, has_request_context
from sqlalchemy.exc import SQLAlchemyError

DEFAULT_ADMIN_PATH = "bakaadmin"
ADMIN_PATH_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{2,31}$")
# 站点自己用到的第一级路径，不能拿来当后台路径。
EXTRA_RESERVED_PATHS = {"static", "setup", "admin", "api", "media", "login", "logout", "register"}

admin_bp = Blueprint("admin", __name__, url_prefix="/<admin_path>")


def valid_admin_path(value: str | None) -> bool:
    return bool(value and ADMIN_PATH_PATTERN.fullmatch(value))


def reserved_admin_paths() -> set[str]:
    """First path segments already used by public pages, so the admin path never shadows them."""
    reserved = set(EXTRA_RESERVED_PATHS)
    for rule in current_app.url_map.iter_rules():
        parts = rule.rule.split("/")
        if len(parts) > 1 and parts[1] and not parts[1].startswith("<"):
            reserved.add(parts[1])
    reserved.discard(DEFAULT_ADMIN_PATH)
    return reserved


def current_admin_path() -> str:
    """The configured admin path; falls back to the default when nothing valid is stored."""
    if has_request_context() and hasattr(g, "admin_path_cache"):
        return g.admin_path_cache
    from app.extensions import db
    from app.services.identity import get_setting

    try:
        value = get_setting("admin_path", DEFAULT_ADMIN_PATH)
    except SQLAlchemyError:
        db.session.rollback()
        value = DEFAULT_ADMIN_PATH
    if not valid_admin_path(value):
        value = DEFAULT_ADMIN_PATH
    if has_request_context():
        g.admin_path_cache = value
    return value


def refresh_admin_path(value: str) -> None:
    if has_request_context():
        g.admin_path_cache = value


def is_admin_target(target: str | None) -> bool:
    """Whether a local redirect target points into the back office."""
    return bool(target and target.startswith(f"/{current_admin_path()}/"))


@admin_bp.url_defaults
def _inject_admin_path(endpoint: str, values: dict) -> None:
    values.setdefault("admin_path", current_admin_path())


@admin_bp.url_value_preprocessor
def _check_admin_path(endpoint: str | None, values: dict | None) -> None:
    requested = (values or {}).pop("admin_path", None)
    if requested != current_admin_path():
        abort(404)


from app.blueprints.admin import gateway_routes, routes  # noqa: E402, F401
