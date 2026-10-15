"""User-owned image upload, management, recycle bin and delivery routes."""

from __future__ import annotations

import secrets
from pathlib import Path

from flask import (
    abort,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)
from flask_login import current_user
from sqlalchemy.exc import IntegrityError

from app.blueprints.images import images_bp
from app.extensions import db
from app.forms import AlbumForm, EmptyForm, ImageEditForm, ImageUploadForm
from app.models import Album, AlbumItem, ImageAsset, ImageFavorite, ImageVariant, utc_now
from app.security import permission_required, record_audit
from app.services.discovery import compatible_album_image
from app.services.media import (
    MediaValidationError,
    QuotaExceededError,
    clean_original_name,
    delete_storage_keys,
    ensure_quota,
    image_storage_keys,
    safe_storage_path,
    storage_usage,
    store_upload,
)


def _can_moderate() -> bool:
    return current_user.is_authenticated and current_user.has_permission("images.moderate")


def _owned_image(public_id: str, *, status: str | None = None) -> ImageAsset:
    statement = db.select(ImageAsset).where(
        ImageAsset.public_id == public_id,
        ImageAsset.owner_id == current_user.id,
    )
    if status:
        statement = statement.where(ImageAsset.status == status)
    image = db.session.scalar(statement)
    if image is None:
        abort(404)
    return image


def _owned_album(public_id: str) -> Album:
    album = db.session.scalar(
        db.select(Album).where(
            Album.public_id == public_id,
            Album.owner_id == current_user.id,
        )
    )
    if album is None:
        abort(404)
    return album


def _album_form(album: Album | None = None) -> tuple[AlbumForm, list[ImageAsset]]:
    images = (
        db.session.scalars(
            db.select(ImageAsset)
            .where(
                ImageAsset.owner_id == current_user.id,
                ImageAsset.status == "active",
                ImageAsset.moderation_status == "approved",
            )
            .order_by(ImageAsset.created_at.desc())
        )
        .unique()
        .all()
    )
    if album:
        ordered = [item.image for item in album.items]
        images = ordered + [image for image in images if image not in ordered]
    form = AlbumForm(obj=album)
    form.image_ids.choices = [
        (image.id, f"{image.title or image.original_name} · {image.visibility}") for image in images
    ]
    return form, images


@images_bp.get("/images/")
@permission_required("images.manage_own")
def library():
    status = request.args.get("status", "active")
    if status not in {"active", "trashed", "quarantined"}:
        status = "active"
    page = max(1, request.args.get("page", 1, type=int))
    page_size = 15
    image_rows = (
        db.session.scalars(
            db.select(ImageAsset)
            .where(ImageAsset.owner_id == current_user.id, ImageAsset.status == status)
            .order_by(ImageAsset.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size + 1)
        )
        .unique()
        .all()
    )
    has_more = len(image_rows) > page_size
    images = image_rows[:page_size]
    empty_form = EmptyForm()
    used_bytes, used_count = storage_usage(current_user.id)
    status_counts = {"active": 0, "quarantined": 0, "trashed": 0}
    status_counts.update(
        dict(
            db.session.execute(
                db.select(ImageAsset.status, db.func.count(ImageAsset.id))
                .where(ImageAsset.owner_id == current_user.id)
                .group_by(ImageAsset.status)
            ).all()
        )
    )
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return jsonify(
            ok=True,
            status=status,
            html=render_template(
                "images/_library_cards.html",
                images=images,
                status=status,
                page=page,
                empty_form=empty_form,
            ),
            has_more=has_more,
            next_page=page + 1 if has_more else None,
            stats={
                "total": used_count,
                "bytes": used_bytes,
                "active": status_counts["active"],
                "quarantined": status_counts["quarantined"],
                "trashed": status_counts["trashed"],
            },
        )
    return render_template(
        "images/library.html",
        images=images,
        status=status,
        page=page,
        has_more=has_more,
        next_page=page + 1 if has_more else page,
        used_bytes=used_bytes,
        used_count=used_count,
        status_counts=status_counts,
        empty_form=empty_form,
    )


@images_bp.route("/images/upload/", methods=["GET", "POST"])
@permission_required("images.upload")
def upload():
    form = ImageUploadForm()
    is_async_upload = request.headers.get("X-Requested-With") == "XMLHttpRequest"
    if form.validate_on_submit():
        uploads = [item for item in form.images.data if item and item.filename]
        stored_keys: list[str] = []
        try:
            if not uploads:
                raise MediaValidationError("请选择至少一张图片。")
            if len(uploads) > int(current_app.config["MAX_IMAGE_BATCH"]):
                raise MediaValidationError(
                    f"每次最多上传{current_app.config['MAX_IMAGE_BATCH']}张图片。"
                )
            ensure_quota(current_user, incoming_count=len(uploads))
            used_bytes, used_count = storage_usage(current_user.id)
            incoming_bytes = 0
            seen_checksums: set[str] = set()
            created: list[ImageAsset] = []
            for uploaded in uploads:
                stored = store_upload(uploaded)
                stored_keys.extend([stored.original_key, stored.thumbnail_key])
                incoming_bytes += stored.total_bytes
                if used_bytes + incoming_bytes > current_user.storage_quota_bytes:
                    raise QuotaExceededError("这些图片会超过可用容量，请少选几张。")
                if used_count + len(created) + 1 > current_user.image_quota_count:
                    raise QuotaExceededError("这些图片会超过可保存数量，请少选几张。")
                duplicate = db.session.scalar(
                    db.select(ImageAsset).where(
                        ImageAsset.owner_id == current_user.id,
                        ImageAsset.checksum_sha256 == stored.checksum_sha256,
                    )
                )
                if duplicate or stored.checksum_sha256 in seen_checksums:
                    raise MediaValidationError("上传队列中包含已经存在的相同图片。")
                seen_checksums.add(stored.checksum_sha256)
                original_name = clean_original_name(uploaded.filename)
                image = ImageAsset(
                    public_id=secrets.token_urlsafe(16),
                    owner_id=current_user.id,
                    original_name=original_name,
                    storage_key=stored.original_key,
                    mime_type=stored.mime_type,
                    image_format=stored.image_format,
                    width=stored.width,
                    height=stored.height,
                    frame_count=stored.frame_count,
                    byte_size=stored.original_bytes,
                    checksum_sha256=stored.checksum_sha256,
                    title=Path(original_name).stem[:160],
                    alt_text="",
                    visibility=form.visibility.data,
                    status="active",
                    moderation_status="approved",
                    published_at=utc_now() if form.visibility.data == "public" else None,
                    variants=[
                        ImageVariant(
                            kind="thumbnail",
                            storage_key=stored.thumbnail_key,
                            mime_type="image/webp",
                            image_format="WEBP",
                            width=stored.thumbnail_width,
                            height=stored.thumbnail_height,
                            byte_size=stored.thumbnail_bytes,
                        )
                    ],
                )
                db.session.add(image)
                created.append(image)
            record_audit(
                "image.upload",
                "image_asset",
                summary=f"安全上传{len(created)}张图片",
            )
            db.session.commit()
            flash(f"{len(created)}张图片已放进图库。", "success")
            library_url = url_for("images.library")
            if is_async_upload:
                return jsonify(ok=True, redirect=library_url, uploaded=len(created)), 201
            return redirect(library_url)
        except (MediaValidationError, QuotaExceededError, IntegrityError) as error:
            db.session.rollback()
            delete_storage_keys(stored_keys)
            message = (
                str(error) if not isinstance(error, IntegrityError) else "图片记录冲突，请重试。"
            )
            if is_async_upload:
                return jsonify(ok=False, message=message), 422
            flash(message, "error")
    elif is_async_upload and request.method == "POST":
        message = next(
            (error for errors in form.errors.values() for error in errors),
            "请检查选择的图片后再试一次。",
        )
        return jsonify(ok=False, message=message), 400
    return render_template("images/upload.html", form=form)


@images_bp.route("/images/<string:public_id>/", methods=["GET", "POST"])
@permission_required("images.manage_own")
def detail(public_id: str):
    image = _owned_image(public_id)
    form = ImageEditForm(obj=image)
    if form.validate_on_submit():
        previous_visibility = image.visibility
        image.title = form.title.data.strip()
        image.alt_text = form.alt_text.data.strip()
        image.visibility = form.visibility.data
        if image.visibility == "public" and previous_visibility != "public":
            image.published_at = utc_now()
        elif image.visibility != "public":
            image.published_at = None
            db.session.execute(db.delete(ImageFavorite).where(ImageFavorite.image_id == image.id))
        removed = 0
        for item in list(image.album_items):
            if not compatible_album_image(image, item.album.visibility):
                db.session.delete(item)
                removed += 1
        record_audit("image.update", "image_asset", str(image.id), "更新图片信息")
        db.session.commit()
        message = "图片信息已保存。"
        if removed:
            message += f" 因访问方式变化，已从{removed}个不兼容相册移除。"
        flash(message, "success")
        return redirect(url_for("images.detail", public_id=image.public_id))
    return render_template("images/detail.html", image=image, form=form, empty_form=EmptyForm())


@images_bp.post("/images/<string:public_id>/trash/")
@permission_required("images.manage_own")
def trash(public_id: str):
    form = EmptyForm()
    if not form.validate_on_submit():
        abort(400)
    image = _owned_image(public_id)
    if image.status not in {"active", "quarantined"}:
        abort(404)
    image.status = "trashed"
    image.trashed_at = utc_now()
    record_audit("image.trash", "image_asset", str(image.id), "移入回收站")
    db.session.commit()
    flash("图片已移入回收站，仍会占用容量。", "success")
    return redirect(url_for("images.library"))


@images_bp.post("/images/<string:public_id>/restore/")
@permission_required("images.manage_own")
def restore(public_id: str):
    form = EmptyForm()
    if not form.validate_on_submit():
        abort(400)
    image = _owned_image(public_id, status="trashed")
    image.status = "quarantined" if image.moderation_status == "rejected" else "active"
    image.trashed_at = None
    record_audit("image.restore", "image_asset", str(image.id), "从回收站恢复")
    db.session.commit()
    flash("图片已恢复。", "success")
    return redirect(url_for("images.detail", public_id=image.public_id))


@images_bp.post("/images/<string:public_id>/purge/")
@permission_required("images.manage_own")
def purge(public_id: str):
    form = EmptyForm()
    if not form.validate_on_submit():
        abort(400)
    image = _owned_image(public_id, status="trashed")
    keys = image_storage_keys(image)
    record_audit("image.purge", "image_asset", str(image.id), "永久删除图片")
    db.session.delete(image)
    db.session.commit()
    delete_storage_keys(keys)
    flash("图片已永久删除，存储容量已经释放。", "success")
    return redirect(url_for("images.library", status="trashed"))


@images_bp.get("/albums/")
@permission_required("images.manage_own")
def albums():
    items = (
        db.session.scalars(
            db.select(Album)
            .where(Album.owner_id == current_user.id)
            .order_by(Album.created_at.desc())
        )
        .unique()
        .all()
    )
    return render_template("images/albums.html", albums=items, empty_form=EmptyForm())


@images_bp.route("/albums/new/", methods=["GET", "POST"])
@permission_required("images.manage_own")
def create_album():
    form, available_images = _album_form()
    if form.validate_on_submit():
        selected = [image for image in available_images if image.id in form.image_ids.data]
        incompatible = [
            image for image in selected if not compatible_album_image(image, form.visibility.data)
        ]
        if incompatible:
            flash("有些图片不适合当前公开范围，请重新选择。", "error")
        else:
            album = Album(
                public_id=secrets.token_urlsafe(16),
                owner_id=current_user.id,
                title=form.title.data.strip(),
                description=form.description.data.strip(),
                visibility=form.visibility.data,
                items=[
                    AlbumItem(image=image, position=index) for index, image in enumerate(selected)
                ],
            )
            db.session.add(album)
            db.session.flush()
            record_audit("album.create", "album", str(album.id), "创建相册")
            db.session.commit()
            flash("相册已经创建。", "success")
            return redirect(url_for("images.edit_album", public_id=album.public_id))
    return render_template(
        "images/album_edit.html",
        form=form,
        album=None,
        available_images=available_images,
        empty_form=EmptyForm(),
    )


@images_bp.route("/albums/<string:public_id>/", methods=["POST"])
@images_bp.route("/albums/<string:public_id>/edit/", methods=["GET", "POST"])
@permission_required("images.manage_own")
def edit_album(public_id: str):
    album = _owned_album(public_id)
    form, available_images = _album_form(album)
    if request.method == "GET":
        form.image_ids.data = [item.image_id for item in album.items]
    if form.validate_on_submit():
        by_id = {image.id: image for image in available_images}
        selected = [by_id[image_id] for image_id in form.image_ids.data if image_id in by_id]
        incompatible = [
            image for image in selected if not compatible_album_image(image, form.visibility.data)
        ]
        if incompatible:
            flash("有些图片不适合当前公开范围，请重新选择。", "error")
        else:
            album.title = form.title.data.strip()
            album.description = form.description.data.strip()
            album.visibility = form.visibility.data
            album.items.clear()
            db.session.flush()
            album.items = [
                AlbumItem(image=image, position=index) for index, image in enumerate(selected)
            ]
            record_audit("album.update", "album", str(album.id), "更新相册与图片编排")
            db.session.commit()
            flash("相册内容和顺序已经保存。", "success")
            return redirect(url_for("images.edit_album", public_id=album.public_id))
    return render_template(
        "images/album_edit.html",
        form=form,
        album=album,
        available_images=available_images,
        empty_form=EmptyForm(),
    )


@images_bp.post("/albums/<string:public_id>/items/<int:item_id>/<string:direction>/")
@permission_required("images.manage_own")
def move_album_item(public_id: str, item_id: int, direction: str):
    album = _owned_album(public_id)
    if direction not in {"up", "down"}:
        abort(404)
    ordered = list(album.items)
    current_index = next((index for index, item in enumerate(ordered) if item.id == item_id), None)
    if current_index is None:
        abort(404)
    target_index = current_index + (-1 if direction == "up" else 1)
    if 0 <= target_index < len(ordered):
        current_item = ordered[current_index]
        target_item = ordered[target_index]
        current_item.position = -(current_index + 1)
        target_item.position = -(target_index + 1)
        db.session.flush()
        target_item.position = current_index
        current_item.position = target_index
        record_audit("album.reorder", "album", str(album.id), "调整相册图片顺序")
        db.session.commit()
    return redirect(url_for("images.edit_album", public_id=album.public_id))


@images_bp.post("/albums/<string:public_id>/delete/")
@permission_required("images.manage_own")
def delete_album(public_id: str):
    form = EmptyForm()
    if not form.validate_on_submit():
        abort(400)
    album = _owned_album(public_id)
    record_audit("album.delete", "album", str(album.id), "删除相册但保留图片")
    db.session.delete(album)
    db.session.commit()
    flash("相册已删除，里面的图片仍保留在图库。", "success")
    return redirect(url_for("images.albums"))


@images_bp.get("/media/<string:public_id>/<string:variant>/")
def media(public_id: str, variant: str):
    image = db.session.scalar(db.select(ImageAsset).where(ImageAsset.public_id == public_id))
    if image is None:
        abort(404)
    privileged = _can_moderate() or (
        current_user.is_authenticated and current_user.id == image.owner_id
    )
    if image.status != "active" or image.moderation_status != "approved":
        if not privileged:
            abort(404)
    if image.visibility == "private" and not privileged:
        abort(404)
    if variant == "original":
        storage_key = image.storage_key
        mime_type = image.mime_type
        download_name = image.original_name
    elif variant == "thumbnail":
        thumbnail = image.variant("thumbnail")
        if thumbnail is None:
            abort(404)
        storage_key = thumbnail.storage_key
        mime_type = thumbnail.mime_type
        download_name = f"{Path(image.original_name).stem}-thumbnail.webp"
    else:
        abort(404)
    path = safe_storage_path(storage_key)
    if not path.is_file():
        abort(404)
    response = send_file(
        path,
        mimetype=mime_type,
        conditional=True,
        download_name=download_name,
        max_age=3600 if image.visibility in {"unlisted", "public"} else 0,
    )
    if image.visibility == "private":
        response.headers["Cache-Control"] = "private, no-store"
    else:
        response.headers["Cache-Control"] = "public, max-age=3600"
    return response
