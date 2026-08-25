"""Safe local image decoding, sanitizing, storage and quota helpers."""

from __future__ import annotations

import hashlib
import os
import secrets
import warnings
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from flask import current_app
from PIL import Image, ImageOps, ImageSequence, UnidentifiedImageError
from werkzeug.datastructures import FileStorage

from app.extensions import db
from app.models import ImageAsset, ImageVariant, User


class MediaValidationError(ValueError):
    """Raised when an upload cannot safely enter the image library."""


class QuotaExceededError(ValueError):
    """Raised when an upload would exceed a user's configured quota."""


@dataclass(frozen=True)
class StoredMedia:
    original_key: str
    thumbnail_key: str
    mime_type: str
    image_format: str
    width: int
    height: int
    frame_count: int
    thumbnail_width: int
    thumbnail_height: int
    original_bytes: int
    thumbnail_bytes: int
    checksum_sha256: str

    @property
    def total_bytes(self) -> int:
        return self.original_bytes + self.thumbnail_bytes


@dataclass(frozen=True)
class MediaConsistency:
    records: int
    missing_keys: tuple[str, ...]
    untracked_keys: tuple[str, ...]

    @property
    def status(self) -> str:
        return "ok" if not self.missing_keys and not self.untracked_keys else "error"


FORMATS = {
    "JPEG": (".jpg", "image/jpeg"),
    "PNG": (".png", "image/png"),
    "WEBP": (".webp", "image/webp"),
    "GIF": (".gif", "image/gif"),
}


def clean_original_name(value: str | None) -> str:
    name = (value or "").replace("\\", "/").rsplit("/", 1)[-1].strip()
    name = "".join(character for character in name if character.isprintable())
    return name[:255] or "image"


def storage_usage(user_id: int) -> tuple[int, int]:
    original_bytes = db.session.scalar(
        db.select(db.func.coalesce(db.func.sum(ImageAsset.byte_size), 0)).where(
            ImageAsset.owner_id == user_id
        )
    )
    variant_bytes = db.session.scalar(
        db.select(db.func.coalesce(db.func.sum(ImageVariant.byte_size), 0))
        .join(ImageAsset, ImageAsset.id == ImageVariant.image_id)
        .where(ImageAsset.owner_id == user_id)
    )
    image_count = db.session.scalar(
        db.select(db.func.count()).select_from(ImageAsset).where(ImageAsset.owner_id == user_id)
    )
    return int(original_bytes or 0) + int(variant_bytes or 0), int(image_count or 0)


def ensure_quota(user: User, incoming_bytes: int = 0, incoming_count: int = 1) -> None:
    used_bytes, used_count = storage_usage(user.id)
    if used_count + incoming_count > user.image_quota_count:
        raise QuotaExceededError("可保存的图片数量已满，请先整理回收站。")
    if used_bytes + incoming_bytes > user.storage_quota_bytes:
        raise QuotaExceededError("可用容量不足，请先整理回收站。")


def store_upload(upload: FileStorage) -> StoredMedia:
    """Decode and re-encode an image before atomically moving it into storage."""

    if not upload.filename:
        raise MediaValidationError("请选择要上传的图片。")
    root = Path(current_app.instance_path)
    temp_dir = root / "tmp"
    upload_root = root / "uploads"
    temp_dir.mkdir(parents=True, exist_ok=True)
    upload_root.mkdir(parents=True, exist_ok=True)

    input_path = temp_dir / f"incoming-{uuid4().hex}.bin"
    original_temp = temp_dir / f"sanitized-{uuid4().hex}.tmp"
    thumbnail_temp = temp_dir / f"thumbnail-{uuid4().hex}.tmp"
    moved_paths: list[Path] = []
    try:
        _copy_limited(upload, input_path)
        image_format, width, height, frame_count = _probe_image(input_path)
        extension, mime_type = FORMATS[image_format]
        token = secrets.token_hex(16)
        prefix = token[:2]
        original_key = f"originals/{prefix}/{token}{extension}"
        thumbnail_key = f"thumbnails/{prefix}/{token}.webp"
        original_path = safe_storage_path(original_key)
        thumbnail_path = safe_storage_path(thumbnail_key)
        original_path.parent.mkdir(parents=True, exist_ok=True)
        thumbnail_path.parent.mkdir(parents=True, exist_ok=True)

        with Image.open(input_path) as source:
            _save_sanitized(source, original_temp, image_format, frame_count)
        with Image.open(original_temp) as clean_source:
            width, height = clean_source.size
            _save_thumbnail(clean_source, thumbnail_temp)
        with Image.open(thumbnail_temp) as thumbnail_probe:
            thumbnail_width, thumbnail_height = thumbnail_probe.size

        os.replace(original_temp, original_path)
        moved_paths.append(original_path)
        os.replace(thumbnail_temp, thumbnail_path)
        moved_paths.append(thumbnail_path)
        checksum = _sha256_file(original_path)
        return StoredMedia(
            original_key=original_key,
            thumbnail_key=thumbnail_key,
            mime_type=mime_type,
            image_format=image_format,
            width=width,
            height=height,
            frame_count=frame_count,
            thumbnail_width=thumbnail_width,
            thumbnail_height=thumbnail_height,
            original_bytes=original_path.stat().st_size,
            thumbnail_bytes=thumbnail_path.stat().st_size,
            checksum_sha256=checksum,
        )
    except Exception:
        for path in moved_paths:
            path.unlink(missing_ok=True)
        raise
    finally:
        input_path.unlink(missing_ok=True)
        original_temp.unlink(missing_ok=True)
        thumbnail_temp.unlink(missing_ok=True)


def safe_storage_path(storage_key: str) -> Path:
    upload_root = (Path(current_app.instance_path) / "uploads").resolve()
    candidate = (upload_root / storage_key).resolve()
    if candidate == upload_root or upload_root not in candidate.parents:
        raise MediaValidationError("图片存储路径不合法。")
    return candidate


def delete_storage_keys(keys: list[str]) -> None:
    for key in keys:
        safe_storage_path(key).unlink(missing_ok=True)


def image_storage_keys(image: ImageAsset) -> list[str]:
    return [image.storage_key, *(variant.storage_key for variant in image.variants)]


def media_consistency() -> MediaConsistency:
    """Compare database storage keys with managed files without changing either."""

    keys = {
        *db.session.scalars(db.select(ImageAsset.storage_key)).all(),
        *db.session.scalars(db.select(ImageVariant.storage_key)).all(),
    }
    missing = tuple(sorted(key for key in keys if not safe_storage_path(key).is_file()))
    upload_root = Path(current_app.instance_path) / "uploads"
    actual = {
        path.relative_to(upload_root).as_posix()
        for folder in ("originals", "thumbnails")
        if (upload_root / folder).exists()
        for path in (upload_root / folder).rglob("*")
        if path.is_file()
    }
    return MediaConsistency(
        records=len(keys),
        missing_keys=missing,
        untracked_keys=tuple(sorted(actual - keys)),
    )


def _copy_limited(upload: FileStorage, target: Path) -> None:
    limit = int(current_app.config["MAX_IMAGE_UPLOAD_BYTES"])
    total = 0
    upload.stream.seek(0)
    with target.open("wb") as destination:
        while chunk := upload.stream.read(1024 * 1024):
            total += len(chunk)
            if total > limit:
                raise MediaValidationError("这张图片太大，请选择小于20 MB的图片。")
            destination.write(chunk)
    if total == 0:
        raise MediaValidationError("上传文件为空。")


def _probe_image(path: Path) -> tuple[str, int, int, int]:
    Image.MAX_IMAGE_PIXELS = int(current_app.config["MAX_IMAGE_PIXELS"])
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(path) as probe:
                image_format = str(probe.format or "").upper()
                width, height = probe.size
                frame_count = int(getattr(probe, "n_frames", 1))
                probe.verify()
    except (Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise MediaValidationError("这张图片的尺寸太大，请换一张。") from None
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError):
        raise MediaValidationError("这不是可以使用的图片，请换一张。") from None
    if image_format not in FORMATS:
        raise MediaValidationError("暂时不支持这种图片，请换一张常见格式的图片。")
    max_dimension = int(current_app.config["MAX_IMAGE_DIMENSION"])
    if min(width, height) < 1 or max(width, height) > max_dimension:
        raise MediaValidationError("这张图片的尺寸太大，请换一张。")
    max_frames = int(current_app.config["MAX_ANIMATION_FRAMES"])
    if frame_count > max_frames:
        raise MediaValidationError("这张动图太长，请换一张。")
    if frame_count > 1 and image_format != "GIF":
        raise MediaValidationError("暂时不支持这种动图，请换一张。")
    if width * height * frame_count > int(current_app.config["MAX_IMAGE_PIXELS"]):
        raise MediaValidationError("这张动图的尺寸太大，请换一张。")
    return image_format, width, height, frame_count


def _save_sanitized(source: Image.Image, target: Path, image_format: str, frames: int) -> None:
    if image_format == "GIF" and frames > 1:
        sanitized_frames: list[Image.Image] = []
        durations: list[int] = []
        for frame in ImageSequence.Iterator(source):
            clean = (
                frame.copy()
                .convert("RGBA")
                .convert(
                    "P",
                    palette=Image.Palette.ADAPTIVE,
                    colors=256,
                )
            )
            sanitized_frames.append(clean)
            durations.append(max(20, min(10_000, int(frame.info.get("duration", 100)))))
        sanitized_frames[0].save(
            target,
            format="GIF",
            save_all=True,
            append_images=sanitized_frames[1:],
            duration=durations,
            loop=0,
            disposal=2,
            optimize=True,
        )
        return

    image = ImageOps.exif_transpose(source)
    image.load()
    if image_format == "JPEG":
        if image.mode != "RGB":
            image = image.convert("RGB")
        image.save(target, format="JPEG", quality=90, optimize=True, progressive=True)
    elif image_format == "PNG":
        if image.mode not in {"RGB", "RGBA", "L", "LA", "P"}:
            image = image.convert("RGBA")
        image.save(target, format="PNG", optimize=True)
    elif image_format == "WEBP":
        if image.mode not in {"RGB", "RGBA"}:
            image = image.convert("RGBA" if "A" in image.getbands() else "RGB")
        image.save(target, format="WEBP", quality=90, method=4)
    else:
        if image.mode not in {"P", "L"}:
            image = image.convert("P", palette=Image.Palette.ADAPTIVE, colors=256)
        image.save(target, format="GIF", optimize=True)


def _save_thumbnail(source: Image.Image, target: Path) -> None:
    frame = ImageOps.exif_transpose(source)
    frame.seek(0)
    thumbnail = frame.convert("RGBA" if "A" in frame.getbands() else "RGB")
    size = int(current_app.config["THUMBNAIL_SIZE"])
    thumbnail.thumbnail((size, size), Image.Resampling.LANCZOS)
    thumbnail.save(target, format="WEBP", quality=82, method=4)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()
