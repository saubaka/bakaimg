"""Versioned bearer-token API."""

from flask import Blueprint

api_bp = Blueprint("api", __name__, url_prefix="/api/v1")

from app.blueprints.api import routes  # noqa: E402,F401
