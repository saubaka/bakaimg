"""Optional external identity routes."""

from flask import Blueprint

gateway_bp = Blueprint("gateway", __name__, url_prefix="/auth")

from app.blueprints.gateway import routes  # noqa: E402, F401
