"""First-run initialisation: the owner creates the administrator and picks the back-office path."""

from flask import Blueprint

setup_bp = Blueprint("setup", __name__, url_prefix="/setup")

from app.blueprints.setup import routes  # noqa: E402, F401
