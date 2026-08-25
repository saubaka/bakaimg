"""Public discovery and sharing rules."""

from __future__ import annotations

from flask_login import current_user

from app.extensions import db
from app.models import Album, ImageAsset


def public_image_conditions() -> tuple[object, ...]:
    return (
        ImageAsset.status == "active",
        ImageAsset.moderation_status == "approved",
        ImageAsset.visibility == "public",
    )


def public_album_conditions() -> tuple[object, ...]:
    return (
        Album.status == "active",
        Album.visibility == "public",
    )


def can_moderate() -> bool:
    return current_user.is_authenticated and current_user.has_permission("images.moderate")


def can_view_image(image: ImageAsset) -> bool:
    privileged = can_moderate() or (
        current_user.is_authenticated and current_user.id == image.owner_id
    )
    if image.status != "active" or image.moderation_status != "approved":
        return privileged
    return image.visibility != "private" or privileged


def can_view_album(album: Album) -> bool:
    privileged = can_moderate() or (
        current_user.is_authenticated and current_user.id == album.owner_id
    )
    if album.status != "active":
        return privileged
    return album.visibility != "private" or privileged


def compatible_album_image(image: ImageAsset, album_visibility: str) -> bool:
    if image.status != "active" or image.moderation_status != "approved":
        return False
    required = {
        "private": {"private", "unlisted", "public"},
        "unlisted": {"unlisted", "public"},
        "public": {"public"},
    }
    return image.visibility in required[album_visibility]


def increment_view_count(item: ImageAsset | Album) -> None:
    owner_id = item.owner_id
    if current_user.is_authenticated and current_user.id == owner_id:
        return
    item.view_count += 1
    db.session.commit()
