"""Administration blueprint."""

from flask import Blueprint

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")

from app.blueprints.admin import gateway_routes, routes  # noqa: E402, F401
