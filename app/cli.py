"""Local management commands used by the Windows launcher and tests."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import click
from flask import Flask, current_app
from flask.cli import with_appcontext
from sqlalchemy import text

from app.extensions import db
from app.models import ImageAsset, Role, SystemEvent, User
from app.security import normalize_email, normalize_username, validate_password
from app.services.identity import seed_settings, sync_identity_foundation
from app.services.local_recovery import create_local_recovery_token
from app.services.media import delete_storage_keys, image_storage_keys, media_consistency
from app.services.operations import (
    OperationError,
    create_backup,
    list_backups,
    restore_backup,
    system_diagnostics,
    verify_backup,
)


def register_commands(app: Flask) -> None:
    @app.cli.command("init-site")
    def init_site() -> None:
        """Seed safe site defaults and the built-in permission matrix."""

        created_settings = seed_settings()
        created_permissions, created_roles = sync_identity_foundation()
        if (
            SystemEvent.query.filter_by(
                category="system",
                message="第六阶段安全运维与备份恢复已初始化",
            ).first()
            is None
        ):
            db.session.add(
                SystemEvent(
                    category="system",
                    message="第六阶段安全运维与备份恢复已初始化",
                )
            )
        db.session.commit()
        click.echo(
            f"initialized_settings={created_settings} "
            f"permissions={created_permissions} roles={created_roles}"
        )

    @app.cli.command("system-check")
    def system_check() -> None:
        """Verify the local database and required writable directories."""

        quick_check = db.session.execute(text("PRAGMA quick_check")).scalar_one()
        if quick_check != "ok":
            raise click.ClickException("SQLite完整性检查未通过。")
        revision = db.session.execute(
            text("SELECT version_num FROM alembic_version LIMIT 1")
        ).scalar_one()
        if revision != current_app.config["EXPECTED_MIGRATION"]:
            raise click.ClickException("数据库迁移版本不是当前发布版本。")

        checked: list[str] = []
        for name in ("data", "uploads", "cache", "logs", "backups", "tmp"):
            directory = Path(current_app.instance_path) / name
            directory.mkdir(parents=True, exist_ok=True)
            probe = directory / ".cloudnest-write-check"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
            checked.append(name)

        result = {
            "env": current_app.config["ENV_NAME"],
            "version": current_app.config["APP_VERSION"],
            "migration": revision,
            "sqlite": "ok",
            "directories": checked,
        }
        click.echo(json.dumps(result, ensure_ascii=False))

    app.cli.add_command(create_admin)
    app.cli.add_command(media_check)
    app.cli.add_command(purge_trash)
    app.cli.add_command(operations_check)
    app.cli.add_command(backup_create)
    app.cli.add_command(backup_list)
    app.cli.add_command(backup_verify)
    app.cli.add_command(restore_check)
    app.cli.add_command(restore_backup_command)
    app.cli.add_command(local_recovery_link)


@click.command("create-admin")
@click.option("--username", prompt="管理员用户名")
@click.option("--email", prompt="管理员邮箱")
@click.option("--display-name", prompt="显示名称", default="站点管理员")
@click.password_option(confirmation_prompt=True)
@with_appcontext
def create_admin(username: str, email: str, display_name: str, password: str) -> None:
    """Create the first or an additional local super administrator."""

    try:
        username = normalize_username(username)
        email = normalize_email(email)
        validate_password(password, username)
    except ValueError as error:
        raise click.ClickException(str(error)) from error
    sync_identity_foundation()
    role = db.session.scalar(db.select(Role).where(Role.code == "superadmin"))
    user = db.session.scalar(
        db.select(User).where(db.or_(User.username == username, User.email == email))
    )
    if user is None:
        user = User(username=username, email=email, display_name=display_name.strip())
        db.session.add(user)
    elif user.username != username or user.email != email:
        raise click.ClickException("用户名或邮箱已被其他账号使用。")
    if role is None:
        raise click.ClickException("内置角色初始化失败。")
    user.email = email
    user.display_name = display_name.strip()
    user.status = "active"
    user.roles = [role]
    user.set_password(password)
    db.session.commit()
    click.echo(f"administrator={user.username}")


@click.command("local-recovery-link")
@with_appcontext
def local_recovery_link() -> None:
    """Create a five-minute, one-use administrator URL for this computer."""

    has_superadmin = any(
        user.status == "active" and user.has_role("superadmin")
        for user in db.session.scalars(db.select(User)).unique().all()
    )
    raw_token = create_local_recovery_token()
    route = "recovery/local" if has_superadmin else "recovery/local/setup"
    click.echo(f"RECOVERY_URL=http://127.0.0.1:5200/auth/{route}/{raw_token}/")


@click.command("media-check")
@with_appcontext
def media_check() -> None:
    """Report missing and untracked image files without modifying them."""

    consistency = media_consistency()
    result = {
        "records": consistency.records,
        "missing": len(consistency.missing_keys),
        "untracked": len(consistency.untracked_keys),
        "status": consistency.status,
    }
    click.echo(json.dumps(result, ensure_ascii=False))
    if consistency.status != "ok":
        raise click.ClickException("图片数据库记录与磁盘文件不一致。")


@click.command("purge-trash")
@click.option("--days", type=click.IntRange(min=1, max=3650), default=None)
@with_appcontext
def purge_trash(days: int | None) -> None:
    """Permanently remove recycle-bin images older than the retention window."""

    retention = days or int(current_app.config["TRASH_RETENTION_DAYS"])
    cutoff = datetime.now(UTC) - timedelta(days=retention)
    images = (
        db.session.scalars(
            db.select(ImageAsset).where(
                ImageAsset.status == "trashed",
                ImageAsset.trashed_at.is_not(None),
                ImageAsset.trashed_at <= cutoff,
            )
        )
        .unique()
        .all()
    )
    keys = [key for image in images for key in image_storage_keys(image)]
    for image in images:
        db.session.delete(image)
    db.session.commit()
    delete_storage_keys(keys)
    click.echo(f"purged_images={len(images)} retention_days={retention}")


@click.command("operations-check")
@with_appcontext
def operations_check() -> None:
    """Run database, migration and media consistency diagnostics."""

    result = system_diagnostics()
    click.echo(
        json.dumps(
            {
                "status": result.status,
                "database": result.database,
                "migration": result.migration,
                "media": {
                    "status": result.media_status,
                    "records": result.media_records,
                    "missing": result.media_missing,
                    "untracked": result.media_untracked,
                },
            },
            ensure_ascii=False,
        )
    )
    if result.status != "ok":
        raise click.ClickException("运维一致性检查未通过。")


@click.command("backup-create")
@with_appcontext
def backup_create() -> None:
    """Create and immediately verify a local backup archive."""

    try:
        report = create_backup()
    except OperationError as error:
        raise click.ClickException(str(error)) from error
    click.echo(json.dumps(_backup_payload(report), ensure_ascii=False))


@click.command("backup-list")
@with_appcontext
def backup_list() -> None:
    """List managed local backup archives."""

    click.echo(
        json.dumps(
            [
                {
                    "archive": path.name,
                    "size_bytes": path.stat().st_size,
                    "modified_at": datetime.fromtimestamp(
                        path.stat().st_mtime,
                        UTC,
                    ).isoformat(),
                }
                for path in list_backups()
            ],
            ensure_ascii=False,
        )
    )


@click.command("backup-verify")
@click.argument("archive_name")
@with_appcontext
def backup_verify(archive_name: str) -> None:
    """Verify an existing backup without changing live data."""

    try:
        report = verify_backup(archive_name)
    except OperationError as error:
        raise click.ClickException(str(error)) from error
    click.echo(json.dumps(_backup_payload(report), ensure_ascii=False))


@click.command("restore-check")
@click.argument("archive_name")
@with_appcontext
def restore_check(archive_name: str) -> None:
    """Run the complete non-mutating restore preflight."""

    try:
        report = verify_backup(archive_name)
    except OperationError as error:
        raise click.ClickException(str(error)) from error
    payload = _backup_payload(report)
    payload["restore_ready"] = True
    click.echo(json.dumps(payload, ensure_ascii=False))


@click.command("restore-backup")
@click.argument("archive_name")
@click.option(
    "--confirm",
    required=True,
    help="必须明确传入RESTORE。",
)
@click.option(
    "--offline",
    is_flag=True,
    help="确认Web服务已经停止。",
)
@with_appcontext
def restore_backup_command(archive_name: str, confirm: str, offline: bool) -> None:
    """Restore a verified backup after explicit offline confirmation."""

    if confirm != "RESTORE" or not offline:
        raise click.ClickException("恢复只允许在服务停止后使用--offline --confirm RESTORE。")
    try:
        restored, rollback = restore_backup(archive_name)
    except (OperationError, OSError) as error:
        raise click.ClickException(str(error)) from error
    click.echo(
        json.dumps(
            {
                "restored": _backup_payload(restored),
                "rollback_backup": _backup_payload(rollback),
            },
            ensure_ascii=False,
        )
    )


def _backup_payload(report) -> dict[str, object]:  # type: ignore[no-untyped-def]
    return {
        "archive": report.archive_name,
        "sha256": report.checksum_sha256,
        "size_bytes": report.size_bytes,
        "migration": report.migration,
        "media_files": report.media_files,
        "created_at": report.created_at,
    }
