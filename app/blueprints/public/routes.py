"""Public home, discovery, sharing and album routes."""

from __future__ import annotations

from datetime import UTC, datetime, time, timedelta
from pathlib import Path

from flask import abort, current_app, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import text

from app.blueprints.public import public_bp
from app.extensions import db
from app.forms import EmptyForm
from app.models import Album, AlbumItem, ImageAsset, ImageFavorite, SystemEvent, User
from app.security import permission_required, record_audit
from app.services.discovery import (
    can_view_album,
    can_view_image,
    increment_view_count,
    public_album_conditions,
    public_image_conditions,
)
from app.services.identity import get_setting
from app.services.media import storage_usage


@public_bp.get("/")
def home():
    recent_images = (
        db.session.scalars(
            db.select(ImageAsset)
            .where(*public_image_conditions())
            .order_by(ImageAsset.published_at.desc(), ImageAsset.created_at.desc())
            .limit(12)
        )
        .unique()
        .all()
    )
    featured_albums = (
        db.session.scalars(
            db.select(Album)
            .where(*public_album_conditions())
            .order_by(Album.is_featured.desc(), Album.created_at.desc())
            .limit(4)
        )
        .unique()
        .all()
    )
    return render_template(
        "public/home.html",
        recent_images=recent_images,
        featured_albums=featured_albums,
        overview=_home_overview(),
        wall_columns=_wall_columns(recent_images),
    )


_WALL_RATIOS = ("tall", "square", "wide")


def _wall_columns(images: list[ImageAsset], columns: int = 3, rows: int = 4) -> list[list[dict]]:
    """Spread public images over the tilted wall; short lists repeat, shapes rotate by position."""
    if not images:
        return []
    return [
        [
            {
                "image": images[(column + columns * row) % len(images)],
                "ratio": _WALL_RATIOS[(column + row) % 3],
            }
            for row in range(rows)
        ]
        for column in range(columns)
    ]


def _upload_chart(days: int = 14) -> dict[str, object]:
    """Public images added per day for the last `days` days, as ready-to-draw SVG numbers."""
    today = datetime.now(UTC).date()
    first = today - timedelta(days=days - 1)
    start = datetime.combine(first, time.min, tzinfo=UTC)
    rows = db.session.execute(
        db.select(db.func.date(ImageAsset.created_at), db.func.count())
        .where(*public_image_conditions(), ImageAsset.created_at >= start)
        .group_by(db.func.date(ImageAsset.created_at))
    ).all()
    per_day = {str(day): int(total) for day, total in rows}
    dates = [first + timedelta(days=offset) for offset in range(days)]
    counts = [per_day.get(day.isoformat(), 0) for day in dates]
    width, height, left, right, top, bottom = 520, 200, 12, 12, 30, 34
    peak = max(counts) if max(counts) > 0 else 1
    step = (width - left - right) / (days - 1)
    points = [
        {
            "x": round(left + index * step, 1),
            "y": round(top + (1 - value / peak) * (height - top - bottom), 1),
            "count": value,
            "label": f"{day.month}月{day.day}日",
            "short": f"{day.month}/{day.day}",
        }
        for index, (day, value) in enumerate(zip(dates, counts, strict=True))
    ]
    path = f"M {points[0]['x']} {points[0]['y']}"
    for before, after in zip(points, points[1:], strict=False):
        middle = round((before["x"] + after["x"]) / 2, 1)
        path += f" C {middle} {before['y']}, {middle} {after['y']}, {after['x']} {after['y']}"
    return {
        "points": points,
        "path": path,
        "total": sum(counts),
        "peak": max(counts),
        "ticks": [index for index in range(days) if index in (0, 4, 8, 13) or index == days - 1],
        "width": width,
        "height": height,
        "days": days,
    }


def _home_overview() -> dict[str, object]:
    """Four site-wide numbers and the recent-upload line for the home page."""
    count = db.func.count()
    return {
        "chart": _upload_chart(),
        "images": db.session.scalar(
            db.select(count).select_from(ImageAsset).where(*public_image_conditions())
        ),
        "albums": db.session.scalar(
            db.select(count).select_from(Album).where(*public_album_conditions())
        ),
        "creators": db.session.scalar(
            db.select(db.func.count(db.distinct(ImageAsset.owner_id))).where(
                *public_image_conditions()
            )
        ),
        "views": db.session.scalar(
            db.select(db.func.coalesce(db.func.sum(ImageAsset.view_count), 0)).where(
                *public_image_conditions()
            )
        ),
    }


@public_bp.get("/dashboard/")
@login_required
def dashboard():
    count = db.func.count()
    mine = ImageAsset.owner_id == current_user.id
    used_bytes, used_count = storage_usage(current_user.id)
    by_visibility = {"private": 0, "unlisted": 0, "public": 0}
    by_visibility.update(
        dict(
            db.session.execute(
                db.select(ImageAsset.visibility, count)
                .where(mine, ImageAsset.status == "active")
                .group_by(ImageAsset.visibility)
            ).all()
        )
    )
    my_images = (
        db.session.scalars(
            db.select(ImageAsset)
            .where(mine, ImageAsset.status == "active")
            .order_by(ImageAsset.created_at.desc())
            .limit(8)
        )
        .unique()
        .all()
    )
    my_albums = (
        db.session.scalars(
            db.select(Album)
            .where(Album.owner_id == current_user.id, Album.status == "active")
            .order_by(Album.created_at.desc())
            .limit(4)
        )
        .unique()
        .all()
    )
    favorites = (
        db.session.scalars(
            db.select(ImageFavorite)
            .join(ImageAsset, ImageAsset.id == ImageFavorite.image_id)
            .where(ImageFavorite.user_id == current_user.id, *public_image_conditions())
            .order_by(ImageFavorite.created_at.desc())
            .limit(4)
        )
        .unique()
        .all()
    )
    quota_bytes = int(current_user.storage_quota_bytes or 0)
    quota_count = int(current_user.image_quota_count or 0)
    return render_template(
        "public/dashboard.html",
        stats={
            "images": by_visibility["private"]
            + by_visibility["unlisted"]
            + by_visibility["public"],
            "albums": db.session.scalar(
                db.select(count)
                .select_from(Album)
                .where(Album.owner_id == current_user.id, Album.status == "active")
            ),
            "favorites": db.session.scalar(
                db.select(count)
                .select_from(ImageFavorite)
                .where(ImageFavorite.user_id == current_user.id)
            ),
            "bytes": used_bytes,
        },
        by_visibility=by_visibility,
        my_images=my_images,
        my_albums=my_albums,
        favorites=favorites,
        used_bytes=used_bytes,
        used_count=used_count,
        quota_bytes=quota_bytes,
        quota_count=quota_count,
    )


@public_bp.get("/discover/")
def discover():
    query = request.args.get("q", "").strip()
    sort = request.args.get("sort", "newest")
    if sort not in {"newest", "popular"}:
        sort = "newest"
    image_statement = db.select(ImageAsset).where(*public_image_conditions())
    album_statement = db.select(Album).where(*public_album_conditions())
    if query:
        term = f"%{query}%"
        image_statement = image_statement.join(User, User.id == ImageAsset.owner_id).where(
            db.or_(
                ImageAsset.title.ilike(term),
                ImageAsset.alt_text.ilike(term),
                User.display_name.ilike(term),
                User.username.ilike(term),
            )
        )
        album_statement = album_statement.join(User, User.id == Album.owner_id).where(
            db.or_(
                Album.title.ilike(term),
                Album.description.ilike(term),
                User.display_name.ilike(term),
                User.username.ilike(term),
            )
        )
    if sort == "popular":
        image_statement = image_statement.order_by(
            ImageAsset.view_count.desc(), ImageAsset.published_at.desc()
        )
        album_statement = album_statement.order_by(
            Album.is_featured.desc(), Album.view_count.desc(), Album.created_at.desc()
        )
    else:
        image_statement = image_statement.order_by(
            ImageAsset.published_at.desc(), ImageAsset.created_at.desc()
        )
        album_statement = album_statement.order_by(
            Album.is_featured.desc(), Album.created_at.desc()
        )
    favorite_ids: set[int] = set()
    if current_user.is_authenticated:
        favorite_ids = set(
            db.session.scalars(
                db.select(ImageFavorite.image_id).where(ImageFavorite.user_id == current_user.id)
            ).all()
        )
    return render_template(
        "public/discover.html",
        images=db.session.scalars(image_statement.limit(60)).unique().all(),
        albums=db.session.scalars(album_statement.limit(24)).unique().all(),
        query=query,
        sort=sort,
        favorite_ids=favorite_ids,
    )


@public_bp.get("/share/<string:public_id>/")
def share_image(public_id: str):
    image = db.session.scalar(db.select(ImageAsset).where(ImageAsset.public_id == public_id))
    if image is None or not can_view_image(image):
        abort(404)
    increment_view_count(image)
    related_albums = (
        db.session.scalars(
            db.select(Album)
            .join(AlbumItem, AlbumItem.album_id == Album.id)
            .where(
                AlbumItem.image_id == image.id,
                *public_album_conditions(),
            )
            .order_by(Album.is_featured.desc(), Album.created_at.desc())
            .limit(6)
        )
        .unique()
        .all()
    )
    return render_template(
        "public/share.html",
        image=image,
        related_albums=related_albums,
        is_favorite=(
            current_user.is_authenticated
            and db.session.scalar(
                db.select(ImageFavorite.id).where(
                    ImageFavorite.user_id == current_user.id,
                    ImageFavorite.image_id == image.id,
                )
            )
            is not None
        ),
        empty_form=EmptyForm(),
    )


@public_bp.post("/share/<string:public_id>/favorite/")
@permission_required("favorites.manage")
def toggle_favorite(public_id: str):
    form = EmptyForm()
    if not form.validate_on_submit():
        abort(400)
    image = db.session.scalar(
        db.select(ImageAsset).where(
            ImageAsset.public_id == public_id,
            *public_image_conditions(),
        )
    )
    if image is None:
        abort(404)
    favorite = db.session.scalar(
        db.select(ImageFavorite).where(
            ImageFavorite.user_id == current_user.id,
            ImageFavorite.image_id == image.id,
        )
    )
    is_async = request.headers.get("X-Requested-With") == "XMLHttpRequest"
    desired = request.form.get("favorite_state") if is_async else None
    if is_async and desired not in ("add", "remove"):
        abort(400)
    should_remove = desired == "remove" if is_async else favorite is not None
    if should_remove:
        if favorite:
            db.session.delete(favorite)
        action = "favorite.remove"
        message = "已从收藏夹移除。"
    else:
        if not favorite:
            favorite = ImageFavorite(user_id=current_user.id, image_id=image.id)
            db.session.add(favorite)
        action = "favorite.add"
        message = "已经收藏这张图片。"
    record_audit(action, "image_asset", str(image.id), message)
    db.session.commit()
    if is_async:
        return jsonify(ok=True, is_favorite=not should_remove, message=message)
    flash(message, "success")
    return redirect(url_for("public.share_image", public_id=image.public_id))


@public_bp.get("/favorites/")
@permission_required("favorites.manage")
def favorites():
    items = (
        db.session.scalars(
            db.select(ImageFavorite)
            .join(ImageAsset, ImageAsset.id == ImageFavorite.image_id)
            .where(
                ImageFavorite.user_id == current_user.id,
                *public_image_conditions(),
            )
            .order_by(ImageFavorite.created_at.desc())
        )
        .unique()
        .all()
    )
    return render_template("public/favorites.html", favorites=items, empty_form=EmptyForm())


@public_bp.get("/albums/<string:public_id>/")
def album_detail(public_id: str):
    album = db.session.scalar(db.select(Album).where(Album.public_id == public_id))
    if album is None or not can_view_album(album):
        abort(404)
    increment_view_count(album)
    images = [item.image for item in album.items if can_view_image(item.image)]
    return render_template("public/album.html", album=album, images=images)


@public_bp.get("/terms/")
def terms():
    return render_template("public/terms.html")


@public_bp.get("/privacy/")
def privacy():
    return render_template("public/privacy.html")


@public_bp.get("/healthz")
def healthcheck():
    return jsonify(
        {
            "status": "ok",
            "service": current_app.config["HEALTH_SERVICE_NAME"],
            "version": current_app.config["APP_VERSION"],
        }
    )


@public_bp.get("/readyz")
def readiness_check():
    checks: dict[str, str] = {}
    status_code = 200
    try:
        quick_check = db.session.execute(text("PRAGMA quick_check")).scalar_one()
        checks["database"] = "ok" if quick_check == "ok" else "error"
        revision = db.session.execute(
            text("SELECT version_num FROM alembic_version LIMIT 1")
        ).scalar_one()
        checks["migration"] = (
            "ok" if revision == current_app.config["EXPECTED_MIGRATION"] else "outdated"
        )
        if checks["database"] != "ok" or checks["migration"] != "ok":
            status_code = 503
    except Exception:
        db.session.rollback()
        checks["database"] = "error"
        status_code = 503

    for name in ("data", "uploads", "tmp"):
        directory = Path(current_app.instance_path) / name
        checks[name] = "ok" if directory.exists() and directory.is_dir() else "missing"
        if checks[name] != "ok":
            status_code = 503
    maintenance = get_setting("maintenance_mode", "false") == "true"
    checks["maintenance"] = "on" if maintenance else "off"
    if maintenance:
        status_code = 503

    return (
        jsonify(
            {
                "status": "ready" if status_code == 200 else "not-ready",
                "version": current_app.config["APP_VERSION"],
                "checks": checks,
            }
        ),
        status_code,
    )


@public_bp.get("/api/foundation-status/")
def foundation_status():
    event_count = SystemEvent.query.count()
    return jsonify(
        {
            "phase": 6,
            "status": "operations-ready",
            "system_events": event_count,
            "uploads_enabled": True,
            "upload_requires_login": True,
        }
    )
