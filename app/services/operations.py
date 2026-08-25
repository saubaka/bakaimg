"""Verifiable local backup, restore preflight and operator diagnostics."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sqlite3
import stat
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from uuid import uuid4

from flask import current_app
from sqlalchemy import text

from app.extensions import db
from app.services.media import media_consistency

MANIFEST_NAME = "manifest.json"
DATABASE_MEMBER = "data/cloudnest.db"
BACKUP_NAME = re.compile(r"^(?:cloudnest|pre-restore)-\d{8}T\d{6}Z-[0-9a-f]{8}\.zip$")


class OperationError(ValueError):
    """Raised when a backup or restore cannot be trusted."""


@dataclass(frozen=True)
class BackupReport:
    archive_name: str
    checksum_sha256: str
    size_bytes: int
    migration: str
    media_files: int
    created_at: str


@dataclass(frozen=True)
class SystemDiagnostics:
    database: str
    migration: str
    media_status: str
    media_records: int
    media_missing: int
    media_untracked: int

    @property
    def status(self) -> str:
        return (
            "ok"
            if self.database == "ok"
            and self.migration == current_app.config["EXPECTED_MIGRATION"]
            and self.media_status == "ok"
            else "error"
        )


def backup_directory() -> Path:
    directory = (Path(current_app.instance_path) / "backups").resolve()
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def list_backups() -> list[Path]:
    return sorted(
        (
            path
            for path in backup_directory().iterdir()
            if path.is_file() and BACKUP_NAME.fullmatch(path.name)
        ),
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    )


def resolve_backup(archive_name: str) -> Path:
    if not BACKUP_NAME.fullmatch(archive_name):
        raise OperationError("备份文件名不合法。")
    root = backup_directory()
    candidate = (root / archive_name).resolve()
    if candidate.parent != root or not candidate.is_file():
        raise OperationError("备份文件不存在。")
    return candidate


def system_diagnostics() -> SystemDiagnostics:
    database_status = "error"
    revision = ""
    try:
        quick_check = db.session.execute(text("PRAGMA quick_check")).scalar_one()
        database_status = "ok" if quick_check == "ok" else str(quick_check)
        revision = db.session.execute(
            text("SELECT version_num FROM alembic_version LIMIT 1")
        ).scalar_one()
    except Exception:
        db.session.rollback()
    media = media_consistency()
    return SystemDiagnostics(
        database=database_status,
        migration=revision,
        media_status=media.status,
        media_records=media.records,
        media_missing=len(media.missing_keys),
        media_untracked=len(media.untracked_keys),
    )


def create_backup(*, prefix: str = "cloudnest") -> BackupReport:
    """Create an atomic ZIP containing an online SQLite snapshot and tracked media."""

    if prefix not in {"cloudnest", "pre-restore"}:
        raise OperationError("备份类型不合法。")
    diagnostics = system_diagnostics()
    if diagnostics.status != "ok":
        raise OperationError("系统一致性检查未通过，已停止创建备份。")

    instance_root = Path(current_app.instance_path).resolve()
    temp_root = instance_root / "tmp"
    temp_root.mkdir(parents=True, exist_ok=True)
    workspace = Path(tempfile.mkdtemp(prefix="backup-", dir=temp_root))
    snapshot = workspace / "cloudnest.db"
    partial_archive = workspace / "archive.partial"
    created_at = datetime.now(UTC)
    archive_name = f"{prefix}-{created_at.strftime('%Y%m%dT%H%M%SZ')}-{uuid4().hex[:8]}.zip"
    target = backup_directory() / archive_name
    try:
        _snapshot_database(snapshot)
        revision, storage_keys = _inspect_snapshot(snapshot)
        if revision != current_app.config["EXPECTED_MIGRATION"]:
            raise OperationError("数据库迁移版本不是当前发布版本，已停止备份。")

        files: list[dict[str, object]] = [
            _file_manifest(snapshot, DATABASE_MEMBER),
        ]
        media_paths: list[tuple[Path, str]] = []
        for storage_key in storage_keys:
            source = _safe_upload_path(instance_root, storage_key)
            if not source.is_file():
                raise OperationError("备份期间图片文件发生变化，请稍后重试。")
            member = f"uploads/{storage_key}"
            files.append(_file_manifest(source, member))
            media_paths.append((source, member))

        manifest = {
            "format": "cloudnest-backup",
            "format_version": int(current_app.config["BACKUP_FORMAT_VERSION"]),
            "created_at": created_at.isoformat(),
            "app_version": current_app.config["APP_VERSION"],
            "migration": revision,
            "database_member": DATABASE_MEMBER,
            "media_files": len(media_paths),
            "files": files,
        }
        with zipfile.ZipFile(
            partial_archive,
            "w",
            compression=zipfile.ZIP_DEFLATED,
            compresslevel=6,
            strict_timestamps=True,
        ) as archive:
            archive.write(snapshot, DATABASE_MEMBER)
            for source, member in media_paths:
                archive.write(source, member)
            archive.writestr(
                MANIFEST_NAME,
                json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8"),
            )
        os.replace(partial_archive, target)
        report = verify_backup(target.name)
        _trim_system_backups()
        return report
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


def verify_backup(archive_name: str) -> BackupReport:
    """Validate paths, checksums, SQLite integrity, revision and media membership."""

    archive_path = resolve_backup(archive_name)
    max_members = int(current_app.config["BACKUP_MAX_MEMBERS"])
    max_bytes = int(current_app.config["BACKUP_MAX_UNCOMPRESSED_BYTES"])
    temp_root = Path(current_app.instance_path) / "tmp"
    temp_root.mkdir(parents=True, exist_ok=True)
    database_copy = temp_root / f"verify-{uuid4().hex}.db"
    try:
        with zipfile.ZipFile(archive_path, "r") as archive:
            infos = archive.infolist()
            if len(infos) > max_members:
                raise OperationError("备份成员数量超过安全限制。")
            names = [item.filename for item in infos]
            if len(names) != len(set(names)):
                raise OperationError("备份包含重复成员。")
            if sum(item.file_size for item in infos) > max_bytes:
                raise OperationError("备份解压后大小超过安全限制。")
            for info in infos:
                _validate_member(info)
            if MANIFEST_NAME not in names:
                raise OperationError("备份缺少清单。")
            manifest_info = archive.getinfo(MANIFEST_NAME)
            if manifest_info.file_size > 2 * 1024 * 1024:
                raise OperationError("备份清单过大。")
            try:
                manifest = json.loads(archive.read(MANIFEST_NAME).decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise OperationError("备份清单无法解析。") from error
            entries = _validate_manifest(manifest)
            if set(names) != {MANIFEST_NAME, *entries}:
                raise OperationError("备份成员与清单不一致。")
            for member, expected in entries.items():
                info = archive.getinfo(member)
                if info.file_size != expected["size"]:
                    raise OperationError(f"备份成员大小校验失败：{member}")
                with archive.open(info, "r") as source:
                    checksum = _sha256_stream(source)
                if checksum != expected["sha256"]:
                    raise OperationError(f"备份成员摘要校验失败：{member}")

            with archive.open(DATABASE_MEMBER, "r") as source, database_copy.open("wb") as target:
                shutil.copyfileobj(source, target, length=1024 * 1024)

        revision, storage_keys = _inspect_snapshot(database_copy, integrity_check=True)
        if revision != manifest["migration"]:
            raise OperationError("数据库迁移版本与清单不一致。")
        if revision != current_app.config["EXPECTED_MIGRATION"]:
            raise OperationError("备份并非当前发布版本，不能恢复。")
        archived_media = sorted(
            member.removeprefix("uploads/") for member in entries if member.startswith("uploads/")
        )
        if archived_media != storage_keys:
            raise OperationError("数据库图片记录与备份媒体成员不一致。")
        if int(manifest["media_files"]) != len(storage_keys):
            raise OperationError("备份媒体计数不一致。")
        return BackupReport(
            archive_name=archive_path.name,
            checksum_sha256=_sha256_file(archive_path),
            size_bytes=archive_path.stat().st_size,
            migration=revision,
            media_files=len(storage_keys),
            created_at=str(manifest["created_at"]),
        )
    except (OSError, zipfile.BadZipFile, KeyError, TypeError) as error:
        if isinstance(error, OperationError):
            raise
        raise OperationError("备份文件损坏或结构不完整。") from error
    finally:
        database_copy.unlink(missing_ok=True)


def restore_backup(archive_name: str) -> tuple[BackupReport, BackupReport]:
    """Restore a verified current-format backup; intended for an offline CLI only."""

    verified = verify_backup(archive_name)
    archive_path = resolve_backup(archive_name)
    instance_root = Path(current_app.instance_path).resolve()
    temp_root = instance_root / "tmp"
    staging = Path(tempfile.mkdtemp(prefix="restore-stage-", dir=temp_root))
    rollback = Path(tempfile.mkdtemp(prefix="restore-old-", dir=temp_root))
    database_path = instance_root / "data" / "cloudnest.db"
    uploads_path = instance_root / "uploads"
    configured_database = Path(str(db.engine.url.database or "")).resolve()
    if configured_database != database_path.resolve():
        raise OperationError("恢复只允许用于实例目录中的标准SQLite数据库。")
    rollback_backup = create_backup(prefix="pre-restore")
    replaced_database = False
    replaced_uploads = False
    try:
        with zipfile.ZipFile(archive_path, "r") as archive:
            for info in archive.infolist():
                if info.filename == MANIFEST_NAME:
                    continue
                target = staging.joinpath(*PurePosixPath(info.filename).parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(info, "r") as source, target.open("wb") as destination:
                    shutil.copyfileobj(source, destination, length=1024 * 1024)
        (staging / "uploads").mkdir(parents=True, exist_ok=True)
        _invalidate_restored_credentials(staging / DATABASE_MEMBER)

        db.session.remove()
        db.engine.dispose()
        rollback_data = rollback / "data"
        rollback_data.mkdir(parents=True, exist_ok=True)
        if database_path.exists():
            os.replace(database_path, rollback_data / database_path.name)
            replaced_database = True
        for suffix in ("-wal", "-shm"):
            sidecar = Path(f"{database_path}{suffix}")
            if sidecar.exists():
                os.replace(sidecar, rollback_data / sidecar.name)
        if uploads_path.exists():
            os.replace(uploads_path, rollback / "uploads")
            replaced_uploads = True

        database_path.parent.mkdir(parents=True, exist_ok=True)
        os.replace(staging / DATABASE_MEMBER, database_path)
        os.replace(staging / "uploads", uploads_path)
        return verified, rollback_backup
    except Exception:
        database_path.unlink(missing_ok=True)
        if uploads_path.exists():
            shutil.rmtree(uploads_path, ignore_errors=True)
        if replaced_database and (rollback / "data" / database_path.name).exists():
            os.replace(rollback / "data" / database_path.name, database_path)
        if replaced_uploads and (rollback / "uploads").exists():
            os.replace(rollback / "uploads", uploads_path)
        raise
    finally:
        shutil.rmtree(staging, ignore_errors=True)
        shutil.rmtree(rollback, ignore_errors=True)


def _snapshot_database(target: Path) -> None:
    raw = db.engine.raw_connection()
    destination = sqlite3.connect(target)
    try:
        source = raw.driver_connection
        if not isinstance(source, sqlite3.Connection):
            raise OperationError("当前数据库不是受支持的SQLite实例。")
        source.backup(destination)
    finally:
        destination.close()
        raw.close()


def _inspect_snapshot(path: Path, *, integrity_check: bool = False) -> tuple[str, list[str]]:
    connection = sqlite3.connect(path)
    try:
        pragma = "integrity_check" if integrity_check else "quick_check"
        result = connection.execute(f"PRAGMA {pragma}").fetchone()
        if result is None or result[0] != "ok":
            raise OperationError("SQLite完整性检查未通过。")
        revision_row = connection.execute(
            "SELECT version_num FROM alembic_version LIMIT 1"
        ).fetchone()
        if revision_row is None:
            raise OperationError("数据库缺少迁移版本。")
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        required = {"users", "image_assets", "image_variants", "operation_records"}
        if not required.issubset(tables):
            raise OperationError("数据库缺少当前版本必需的数据表。")
        keys = sorted(
            row[0]
            for row in connection.execute(
                "SELECT storage_key FROM image_assets UNION SELECT storage_key FROM image_variants"
            ).fetchall()
        )
        return str(revision_row[0]), keys
    except sqlite3.DatabaseError as error:
        raise OperationError("SQLite快照无法读取。") from error
    finally:
        connection.close()


def _invalidate_restored_credentials(path: Path) -> None:
    """Prevent a restore from resurrecting browser sessions or live API tokens."""

    connection = sqlite3.connect(path)
    try:
        now = datetime.now(UTC).isoformat()
        connection.execute("DELETE FROM user_sessions")
        connection.execute(
            "UPDATE api_tokens SET revoked_at = ? WHERE revoked_at IS NULL",
            (now,),
        )
        result = connection.execute("PRAGMA integrity_check").fetchone()
        if result is None or result[0] != "ok":
            raise OperationError("恢复副本的凭据失效处理未通过完整性检查。")
        connection.commit()
    except sqlite3.DatabaseError as error:
        connection.rollback()
        raise OperationError("无法安全失效恢复副本中的会话与API令牌。") from error
    finally:
        connection.close()


def _validate_manifest(manifest: object) -> dict[str, dict[str, object]]:
    if not isinstance(manifest, dict):
        raise OperationError("备份清单结构不合法。")
    if manifest.get("format") != "cloudnest-backup":
        raise OperationError("备份格式标识不合法。")
    if manifest.get("format_version") != current_app.config["BACKUP_FORMAT_VERSION"]:
        raise OperationError("备份格式版本不受支持。")
    if manifest.get("database_member") != DATABASE_MEMBER:
        raise OperationError("备份数据库位置不合法。")
    files = manifest.get("files")
    if not isinstance(files, list):
        raise OperationError("备份文件清单不合法。")
    entries: dict[str, dict[str, object]] = {}
    for item in files:
        if not isinstance(item, dict):
            raise OperationError("备份文件条目不合法。")
        path = item.get("path")
        size = item.get("size")
        checksum = item.get("sha256")
        if (
            not isinstance(path, str)
            or not isinstance(size, int)
            or size < 0
            or not isinstance(checksum, str)
            or not re.fullmatch(r"[0-9a-f]{64}", checksum)
            or path in entries
        ):
            raise OperationError("备份文件条目字段不合法。")
        entries[path] = {"size": size, "sha256": checksum}
    if DATABASE_MEMBER not in entries:
        raise OperationError("备份清单缺少数据库。")
    return entries


def _validate_member(info: zipfile.ZipInfo) -> None:
    name = info.filename
    path = PurePosixPath(name)
    mode = (info.external_attr >> 16) & 0o170000
    if (
        not name
        or "\\" in name
        or path.is_absolute()
        or ".." in path.parts
        or "." in path.parts
        or info.is_dir()
        or mode == stat.S_IFLNK
        or info.flag_bits & 0x1
    ):
        raise OperationError("备份包含不安全的成员路径或类型。")
    if name != MANIFEST_NAME and name != DATABASE_MEMBER and not name.startswith("uploads/"):
        raise OperationError("备份包含未授权的成员。")


def _safe_upload_path(instance_root: Path, storage_key: str) -> Path:
    upload_root = (instance_root / "uploads").resolve()
    candidate = (upload_root / storage_key).resolve()
    if candidate == upload_root or upload_root not in candidate.parents:
        raise OperationError("数据库包含不安全的图片存储键。")
    return candidate


def _file_manifest(path: Path, member: str) -> dict[str, object]:
    return {
        "path": member,
        "size": path.stat().st_size,
        "sha256": _sha256_file(path),
    }


def _sha256_file(path: Path) -> str:
    with path.open("rb") as source:
        return _sha256_stream(source)


def _sha256_stream(source) -> str:  # type: ignore[no-untyped-def]
    digest = hashlib.sha256()
    while chunk := source.read(1024 * 1024):
        digest.update(chunk)
    return digest.hexdigest()


def _trim_system_backups() -> None:
    keep = int(current_app.config["BACKUP_RETENTION_COUNT"])
    system_backups = [path for path in list_backups() if path.name.startswith("cloudnest-")]
    for path in system_backups[keep:]:
        path.unlink(missing_ok=True)
