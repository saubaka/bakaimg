"""Whether the site still has to be initialised (no account exists yet)."""

from __future__ import annotations

from flask import current_app
from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db
from app.models import User


def setup_needed() -> bool:
    """True until the first account exists; set ``SETUP_REQUIRED = False`` to skip the wizard."""
    if not current_app.config.get("SETUP_REQUIRED", True):
        return False
    if current_app.extensions.get("setup_complete"):
        return False
    try:
        total = db.session.scalar(db.select(db.func.count(User.id)))
    except SQLAlchemyError:
        db.session.rollback()
        return False
    if total:
        current_app.extensions["setup_complete"] = True
        return False
    return True
