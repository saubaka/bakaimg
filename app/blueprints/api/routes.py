"""Programmatic image access backed by hashed, scoped API tokens."""

from __future__ import annotations

import secrets
from pathlib import Path

from flask import g, jsonify, request, send_file, url_for
from sqlalchemy.exc import IntegrityError

from app.blueprints.api import api_bp
from app.extensions import db
from app.models import ImageAsset, ImageVariant, utc_now
from app.services.api_tokens import record_api_audit, token_required
from app.services.media import (
    MediaValidationError,
    QuotaExceededError,
    clean_original_name,
    delete_storage_keys,
    ensure_quota,
    safe_storage_path,
    storage_usage,
    store_upload,
)


def _image_payload(image: ImageAsset) -> dict[str, object]:
    return {
        "id": image.public_id,
        "name": image.original_name,
        "title": image.title,
        "alt_text": image.alt_text,
        "visibility": image.visibility,
        "status": image.status,
        "moderation_status": image.moderation_status,
        "format": image.image_format,
        "width": image.width,
        "height": image.height,
        "frames": image.frame_count,
        "bytes": image.byte_size,
        "sha256": image.checksum_sha256,
        "created_at": image.created_at.isoformat(),
        "urls": {
            "metadata": url_for("api.image_detail", public_id=image.public_id, _external=True),
            "original": url_for(
                "api.image_content",
                public_id=image.public_id,
                variant="original",
                _external=True,
            ),
            "thumbnail": url_for(
                "api.image_content",
                public_id=image.public_id,
                variant="thumbnail",
                _external=True,
            ),
            "share": url_for("public.share_image", public_id=image.public_id, _external=True),
        },
    }


def _owned_api_image(public_id: str) -> ImageAsset | None:
    return db.session.scalar(
        db.select(ImageAsset).where(
            ImageAsset.public_id == public_id,
            ImageAsset.owner_id == g.api_user.id,
        )
    )


@api_bp.get("/me")
@token_required("images:read")
def me():
    used_bytes, used_count = storage_usage(g.api_user.id)
    return jsonify(
        user={
            "username": g.api_user.username,
            "display_name": g.api_user.display_name,
        },
        token={
            "name": g.api_token.name,
            "prefix": g.api_token.token_prefix,
            "scopes": sorted(g.api_token.scope_set),
            "expires_at": g.api_token.expires_at.isoformat(),
        },
        quota={
            "used_bytes": used_bytes,
            "limit_bytes": g.api_user.storage_quota_bytes,
            "used_images": used_count,
            "limit_images": g.api_user.image_quota_count,
        },
    )


@api_bp.get("/images/")
@token_required("images:read")
def images():
    status = request.args.get("status", "active")
    if status not in {"active", "trashed", "quarantined", "all"}:
        return jsonify(error="invalid_status", message="图片状态筛选不合法。"), 400
    try:
        limit = min(100, max(1, int(request.args.get("limit", "50"))))
    except ValueError:
        return jsonify(error="invalid_limit", message="limit必须是整数。"), 400
    statement = (
        db.select(ImageAsset)
        .where(ImageAsset.owner_id == g.api_user.id)
        .order_by(ImageAsset.created_at.desc())
        .limit(limit)
    )
    if status != "all":
        statement = statement.where(ImageAsset.status == status)
    items = db.session.scalars(statement).unique().all()
    return jsonify(images=[_image_payload(image) for image in items], count=len(items))


@api_bp.post("/images/")
@token_required("images:write")
def upload_image():
    uploads = [item for item in request.files.getlist("image") if item and item.filename]
    uploaded = uploads[0] if len(uploads) == 1 else None
    visibility = request.form.get("visibility", "private")
    title = request.form.get("title", "").strip()
    alt_text = request.form.get("alt_text", "").strip()
    if uploaded is None:
        return jsonify(error="missing_image", message="请使用image字段上传且仅上传一张图片。"), 400
    if visibility not in {"private", "unlisted", "public"}:
        return jsonify(error="invalid_visibility", message="图片访问方式不合法。"), 400
    if len(title) > 160 or len(alt_text) > 240:
        return jsonify(error="invalid_metadata", message="图片标题或替代文字过长。"), 400

    stored_keys: list[str] = []
    try:
        ensure_quota(g.api_user, incoming_count=1)
        stored = store_upload(uploaded)
        stored_keys.extend([stored.original_key, stored.thumbnail_key])
        ensure_quota(g.api_user, incoming_bytes=stored.total_bytes, incoming_count=1)
        duplicate = db.session.scalar(
            db.select(ImageAsset).where(
                ImageAsset.owner_id == g.api_user.id,
                ImageAsset.checksum_sha256 == stored.checksum_sha256,
            )
        )
        if duplicate:
            raise MediaValidationError("相同图片已经存在于当前账号。")
        original_name = clean_original_name(uploaded.filename)
        image = ImageAsset(
            public_id=secrets.token_urlsafe(16),
            owner_id=g.api_user.id,
            original_name=original_name,
            storage_key=stored.original_key,
            mime_type=stored.mime_type,
            image_format=stored.image_format,
            width=stored.width,
            height=stored.height,
            frame_count=stored.frame_count,
            byte_size=stored.original_bytes,
            checksum_sha256=stored.checksum_sha256,
            title=title or Path(original_name).stem[:160],
            alt_text=alt_text,
            visibility=visibility,
            status="active",
            moderation_status="approved",
            published_at=utc_now() if visibility == "public" else None,
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
        db.session.flush()
        record_api_audit("api.image.upload", "image_asset", str(image.id), "API安全上传图片")
        db.session.commit()
        return jsonify(image=_image_payload(image)), 201
    except (MediaValidationError, QuotaExceededError, IntegrityError) as error:
        db.session.rollback()
        delete_storage_keys(stored_keys)
        message = str(error) if not isinstance(error, IntegrityError) else "图片记录冲突，请重试。"
        return jsonify(error="upload_rejected", message=message), 400


@api_bp.get("/images/<string:public_id>/")
@token_required("images:read")
def image_detail(public_id: str):
    image = _owned_api_image(public_id)
    if image is None:
        return jsonify(error="not_found", message="图片不存在。"), 404
    return jsonify(image=_image_payload(image))


@api_bp.get("/images/<string:public_id>/content/<string:variant>/")
@token_required("images:read")
def image_content(public_id: str, variant: str):
    image = _owned_api_image(public_id)
    if image is None:
        return jsonify(error="not_found", message="图片不存在。"), 404
    if variant == "original":
        storage_key = image.storage_key
        mime_type = image.mime_type
        download_name = image.original_name
    elif variant == "thumbnail":
        thumbnail = image.variant("thumbnail")
        if thumbnail is None:
            return jsonify(error="not_found", message="缩略图不存在。"), 404
        storage_key = thumbnail.storage_key
        mime_type = thumbnail.mime_type
        download_name = f"{Path(image.original_name).stem}-thumbnail.webp"
    else:
        return jsonify(error="not_found", message="图片变体不存在。"), 404
    path = safe_storage_path(storage_key)
    if not path.is_file():
        return jsonify(error="not_found", message="图片文件不存在。"), 404
    response = send_file(
        path,
        mimetype=mime_type,
        conditional=True,
        download_name=download_name,
        max_age=0,
    )
    response.headers["Cache-Control"] = "private, no-store"
    return response


@api_bp.delete("/images/<string:public_id>/")
@token_required("images:write")
def trash_image(public_id: str):
    image = _owned_api_image(public_id)
    if image is None or image.status not in {"active", "quarantined"}:
        return jsonify(error="not_found", message="可回收的图片不存在。"), 404
    image.status = "trashed"
    image.trashed_at = utc_now()
    record_api_audit("api.image.trash", "image_asset", str(image.id), "API移入回收站")
    db.session.commit()
    return jsonify(status="trashed", id=image.public_id)


@api_bp.errorhandler(413)
def request_too_large(_error):
    return jsonify(error="request_too_large", message="上传请求超过服务器限制。"), 413
