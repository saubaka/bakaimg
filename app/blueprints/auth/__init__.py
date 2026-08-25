"""Public authentication and account blueprint."""

from flask import Blueprint

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")

from app.blueprints.auth import routes  # noqa: E402,F401
