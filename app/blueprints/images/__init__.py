"""Authenticated image library and delivery blueprint."""

from flask import Blueprint

images_bp = Blueprint("images", __name__)

from app.blueprints.images import routes  # noqa: E402,F401
