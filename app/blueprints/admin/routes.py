"""Identity administration routes."""

import shutil

from flask import abort, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy.exc import IntegrityError

from app.blueprints.admin import admin_bp
from app.extensions import db
from app.forms import (
    DialogAppearanceForm,
    EmptyForm,
    MaintenanceForm,
    RoleForm,
    TransitionSettingsForm,
    UserAdminForm,
)
from app.models import (
    Album,
    ApiToken,
    AuditLog,
    ImageAsset,
    ImageFavorite,
    ImageVariant,
    LoginLog,
    OperationRecord,
    Permission,
    Role,
    SiteSetting,
    SystemEvent,
    User,
    UserSession,
    utc_now,
)
from app.security import normalize_email, permission_required, record_audit
from app.services.api_tokens import revoke_api_token, revoke_user_api_tokens
from app.services.appearance import (
    DIALOG_APPEARANCE_DEFAULTS,
    DIALOG_SHADOW_CHOICES,
    DIALOG_SHADOW_VALUES,
    DIALOG_STYLE_CHOICES,
    DIALOG_STYLE_VALUES,
    PAGE_TRANSITION_CHOICES,
    PAGE_TRANSITION_COLOR_DEFAULTS,
    PAGE_TRANSITION_VALUES,
)
from app.services.auth import revoke_other_sessions
from app.services.identity import assert_not_last_superadmin, get_setting, set_setting
from app.services.labels import audit_action
from app.services.media import delete_storage_keys, image_storage_keys, storage_usage
from app.services.operations import (
    OperationError,
    create_backup,
    list_backups,
    system_diagnostics,
    verify_backup,
)


@admin_bp.before_request
def protect_admin():
    if current_user.is_authenticated and current_user.has_permission("admin.access"):
        return None
    if current_user.is_authenticated:
        abort(403)
    next_target = request.full_path if request.query_string else request.path
    return redirect(
        url_for(
            "auth.login",
            next=next_target,
        )
    )


@admin_bp.get("/")
@permission_required("admin.access")
def dashboard():
    return render_template(
        "admin/dashboard.html",
        settings_count=SiteSetting.query.count(),
        recent_events=SystemEvent.query.order_by(SystemEvent.created_at.desc()).limit(5).all(),
        user_count=User.query.count(),
        active_session_count=UserSession.query.filter_by(revoked_at=None).count(),
        image_count=ImageAsset.query.count(),
        album_count=Album.query.count(),
        public_image_count=ImageAsset.query.filter_by(
            status="active",
            moderation_status="approved",
            visibility="public",
        ).count(),
        active_token_count=ApiToken.query.filter(
            ApiToken.revoked_at.is_(None),
            ApiToken.expires_at > utc_now(),
        ).count(),
        favorite_count=ImageFavorite.query.count(),
        stored_bytes=(
            db.session.scalar(db.select(db.func.coalesce(db.func.sum(ImageAsset.byte_size), 0)))
            or 0
        )
        + (
            db.session.scalar(db.select(db.func.coalesce(db.func.sum(ImageVariant.byte_size), 0)))
            or 0
        ),
    )


@admin_bp.get("/users/")
@permission_required("users.view")
def users():
    query = request.args.get("q", "").strip()
    statement = db.select(User).order_by(User.created_at.desc())
    if query:
        term = f"%{query}%"
        statement = statement.where(
            db.or_(
                User.username.ilike(term),
                User.email.ilike(term),
                User.display_name.ilike(term),
            )
        )
    return render_template(
        "admin/users.html",
        users=db.session.scalars(statement).unique().all(),
        query=query,
    )


@admin_bp.route("/users/<int:user_id>/", methods=["GET", "POST"])
@permission_required("users.manage")
def edit_user(user_id: int):
    user = db.get_or_404(User, user_id)
    roles = db.session.scalars(db.select(Role).order_by(Role.id)).all()
    form = UserAdminForm(obj=user)
    form.role_ids.choices = [(role.id, role.name) for role in roles]
    if request.method == "GET":
        form.role_ids.data = [role.id for role in user.roles]
        form.storage_quota_mb.data = user.storage_quota_bytes // (1024 * 1024)
        form.image_quota_count.data = user.image_quota_count
    if form.validate_on_submit():
        selected_roles = [role for role in roles if role.id in form.role_ids.data]
        try:
            if form.status.data not in {"active", "disabled"}:
                raise ValueError("账号状态不合法。")
            assert_not_last_superadmin(
                user,
                new_status=form.status.data,
                new_role_codes={role.code for role in selected_roles},
            )
            email = normalize_email(form.email.data)
            duplicate = db.session.scalar(
                db.select(User).where(User.email == email, User.id != user.id)
            )
            if duplicate:
                raise ValueError("该邮箱已被其他账号使用。")
            user.display_name = form.display_name.data.strip()
            user.email = email
            user.status = form.status.data
            user.roles = selected_roles
            user.storage_quota_bytes = form.storage_quota_mb.data * 1024 * 1024
            user.image_quota_count = form.image_quota_count.data
            if user.status != "active":
                revoke_other_sessions(user)
                revoke_user_api_tokens(user)
            record_audit("admin.user.update", "user", str(user.id), "更新账号与角色")
            db.session.commit()
            flash("账号设置已保存。", "success")
            return redirect(url_for("admin.edit_user", user_id=user.id))
        except (ValueError, IntegrityError) as error:
            db.session.rollback()
            message = str(error) if isinstance(error, ValueError) else "账号信息存在冲突。"
            flash(message, "error")
    used_bytes, used_count = storage_usage(user.id)
    return render_template(
        "admin/user_edit.html",
        form=form,
        user=user,
        used_bytes=used_bytes,
        used_count=used_count,
    )


@admin_bp.get("/roles/")
@permission_required("roles.manage")
def roles():
    return render_template(
        "admin/roles.html",
        roles=db.session.scalars(db.select(Role).order_by(Role.id)).all(),
    )


@admin_bp.route("/roles/<int:role_id>/", methods=["GET", "POST"])
@permission_required("roles.manage")
def edit_role(role_id: int):
    role = db.get_or_404(Role, role_id)
    permissions = db.session.scalars(db.select(Permission).order_by(Permission.code)).all()
    form = RoleForm(obj=role)
    form.permission_ids.choices = [(permission.id, permission.name) for permission in permissions]
    if request.method == "GET":
        form.permission_ids.data = [permission.id for permission in role.permissions]
    if form.validate_on_submit():
        if role.code == "superadmin":
            flash("超级管理员权限由系统完整维护，不能缩减。", "error")
        else:
            role.name = form.name.data.strip()
            role.description = form.description.data.strip()
            role.permissions = [
                permission
                for permission in permissions
                if permission.id in form.permission_ids.data
            ]
            record_audit("admin.role.update", "role", str(role.id), "更新角色权限")
            db.session.commit()
            flash("角色权限已保存。", "success")
            return redirect(url_for("admin.edit_role", role_id=role.id))
    return render_template("admin/role_edit.html", form=form, role=role)


@admin_bp.get("/operations/")
@permission_required("system.maintain")
def operations():
    maintenance_form = MaintenanceForm()
    maintenance_form.enabled.data = get_setting("maintenance_mode", "false") == "true"
    maintenance_form.message.data = get_setting(
        "maintenance_message",
        "正在整理图片，请稍后再来。",
    )
    backup_rows = [
        {
            "name": path.name,
            "size": path.stat().st_size,
            "modified_at": path.stat().st_mtime,
        }
        for path in list_backups()
    ]
    disk = shutil.disk_usage(current_app.instance_path)
    return render_template(
        "admin/operations.html",
        diagnostics=system_diagnostics(),
        maintenance_form=maintenance_form,
        empty_form=EmptyForm(),
        backups=backup_rows,
        disk=disk,
        records=db.session.scalars(
            db.select(OperationRecord).order_by(OperationRecord.created_at.desc()).limit(50)
        )
        .unique()
        .all(),
    )


@admin_bp.post("/operations/maintenance/")
@permission_required("system.maintain")
def update_maintenance():
    form = MaintenanceForm()
    if not form.validate_on_submit():
        flash("维护状态未保存，请检查提示文字。", "error")
        return redirect(url_for("admin.operations"))
    enabled = bool(form.enabled.data)
    set_setting("maintenance_mode", "true" if enabled else "false")
    set_setting("maintenance_message", form.message.data.strip())
    record_audit(
        "admin.maintenance.update",
        "site_setting",
        "maintenance_mode",
        "开启维护模式" if enabled else "关闭维护模式",
    )
    db.session.add(
        OperationRecord(
            actor_id=current_user.id,
            action="maintenance",
            status="success",
            summary="维护模式已开启" if enabled else "维护模式已关闭",
        )
    )
    db.session.commit()
    flash("维护状态已保存。", "success")
    return redirect(url_for("admin.operations"))


@admin_bp.route("/appearance/hints/", methods=["GET", "POST"])
@permission_required("system.maintain")
def appearance_hints():
    form = EmptyForm()
    if form.validate_on_submit():
        visible = request.form.get("admin_menu_subtitles_visible") == "y"
        set_setting("admin_menu_subtitles_visible", "true" if visible else "false")
        record_audit(
            "admin.appearance.hints",
            "site_setting",
            "admin_menu_subtitles_visible",
            "显示菜单小标题" if visible else "隐藏菜单小标题",
        )
        db.session.commit()
        flash("菜单小标题设置已保存。", "success")
        return redirect(url_for("admin.appearance_hints"))
    subtitles_visible = get_setting("admin_menu_subtitles_visible", "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    return render_template(
        "admin/appearance_hints.html",
        form=form,
        subtitles_visible=subtitles_visible,
    )


@admin_bp.route("/appearance/transitions/", methods=["GET", "POST"])
@permission_required("system.maintain")
def transition_settings():
    form = TransitionSettingsForm()
    form.transition_style.choices = list(PAGE_TRANSITION_CHOICES)
    if request.method == "GET":
        style = get_setting("page_transition_style", "stretch")
        form.transition_style.data = style if style in PAGE_TRANSITION_VALUES else "stretch"
        try:
            form.transition_duration.data = max(
                300, min(2400, int(get_setting("page_transition_duration", "720")))
            )
        except (TypeError, ValueError):
            form.transition_duration.data = 720
        for key, default in PAGE_TRANSITION_COLOR_DEFAULTS.items():
            getattr(form, key.removeprefix("page_")).data = get_setting(key, default)
    if form.validate_on_submit():
        if form.transition_style.data not in PAGE_TRANSITION_VALUES:
            abort(400)
        duration = max(300, min(2400, int(form.transition_duration.data)))
        set_setting("page_transition_style", form.transition_style.data)
        set_setting("page_transition_duration", str(duration))
        for key in PAGE_TRANSITION_COLOR_DEFAULTS:
            field = getattr(form, key.removeprefix("page_"))
            set_setting(key, field.data.lower())
        record_audit(
            "admin.appearance.transitions",
            "site_setting",
            "page_transition_style",
            f"{form.transition_style.data} / {duration}ms",
        )
        db.session.commit()
        flash("页面动画设置已保存。", "success")
        return redirect(url_for("admin.transition_settings"))
    return render_template("admin/transition_settings.html", form=form)


@admin_bp.route("/appearance/dialogs/", methods=["GET", "POST"])
@permission_required("system.maintain")
def dialog_appearance():
    form = DialogAppearanceForm()
    form.dialog_style.choices = list(DIALOG_STYLE_CHOICES)
    form.dialog_shadow.choices = list(DIALOG_SHADOW_CHOICES)
    if request.method == "GET":
        style = get_setting("dialog_style", DIALOG_APPEARANCE_DEFAULTS["dialog_style"])
        form.dialog_style.data = style if style in DIALOG_STYLE_VALUES else "soft"
        shadow = get_setting("dialog_shadow", DIALOG_APPEARANCE_DEFAULTS["dialog_shadow"])
        form.dialog_shadow.data = shadow if shadow in DIALOG_SHADOW_VALUES else "soft"
        for key in ("dialog_color_start", "dialog_color_end", "dialog_accent"):
            getattr(form, key).data = get_setting(key, DIALOG_APPEARANCE_DEFAULTS[key])
        for key, minimum, maximum in (
            ("dialog_radius", 14, 42),
            ("dialog_width", 360, 720),
            ("dialog_backdrop_blur", 0, 30),
        ):
            try:
                value = int(get_setting(key, DIALOG_APPEARANCE_DEFAULTS[key]))
            except (TypeError, ValueError):
                value = int(DIALOG_APPEARANCE_DEFAULTS[key])
            getattr(form, key).data = max(minimum, min(maximum, value))
    if form.validate_on_submit():
        if form.dialog_style.data not in DIALOG_STYLE_VALUES:
            abort(400)
        if form.dialog_shadow.data not in DIALOG_SHADOW_VALUES:
            abort(400)
        set_setting("dialog_style", form.dialog_style.data)
        set_setting("dialog_shadow", form.dialog_shadow.data)
        for key in ("dialog_color_start", "dialog_color_end", "dialog_accent"):
            set_setting(key, getattr(form, key).data.lower())
        for key in ("dialog_radius", "dialog_width", "dialog_backdrop_blur"):
            set_setting(key, str(getattr(form, key).data))
        record_audit(
            "admin.appearance.dialogs",
            "site_setting",
            "dialog_style",
            f"{form.dialog_style.data} / {form.dialog_width.data}px / {form.dialog_shadow.data}",
        )
        db.session.commit()
        flash("弹窗外观已保存。", "success")
        return redirect(url_for("admin.dialog_appearance"))
    return render_template("admin/dialog_appearance.html", form=form)


@admin_bp.post("/operations/backups/")
@permission_required("system.maintain")
def create_backup_admin():
    form = EmptyForm()
    if not form.validate_on_submit():
        abort(400)
    try:
        report = create_backup()
        db.session.add(
            OperationRecord(
                actor_id=current_user.id,
                action="backup.create",
                status="success",
                archive_name=report.archive_name,
                checksum_sha256=report.checksum_sha256,
                summary=f"已创建并验证备份，媒体文件{report.media_files}个",
            )
        )
        record_audit(
            "admin.backup.create",
            "backup",
            report.archive_name,
            "创建并验证本地备份",
        )
        db.session.commit()
        flash("备份已经创建，并完成清单、摘要和数据库一致性校验。", "success")
    except OperationError as error:
        db.session.rollback()
        db.session.add(
            OperationRecord(
                actor_id=current_user.id,
                action="backup.create",
                status="failed",
                summary=str(error)[:255],
            )
        )
        db.session.commit()
        flash(str(error), "error")
    return redirect(url_for("admin.operations"))


@admin_bp.post("/operations/backups/<string:archive_name>/verify/")
@permission_required("system.maintain")
def verify_backup_admin(archive_name: str):
    form = EmptyForm()
    if not form.validate_on_submit():
        abort(400)
    try:
        report = verify_backup(archive_name)
        db.session.add(
            OperationRecord(
                actor_id=current_user.id,
                action="backup.verify",
                status="success",
                archive_name=report.archive_name,
                checksum_sha256=report.checksum_sha256,
                summary=f"恢复预检通过，媒体文件{report.media_files}个",
            )
        )
        record_audit(
            "admin.backup.verify",
            "backup",
            report.archive_name,
            "备份恢复预检通过",
        )
        db.session.commit()
        flash("备份恢复预检通过。", "success")
    except OperationError as error:
        db.session.rollback()
        db.session.add(
            OperationRecord(
                actor_id=current_user.id,
                action="backup.verify",
                status="failed",
                archive_name=archive_name[:255],
                summary=str(error)[:255],
            )
        )
        db.session.commit()
        flash(str(error), "error")
    return redirect(url_for("admin.operations"))


@admin_bp.get("/audit/")
@permission_required("audit.view")
def audit():
    return render_template(
        "admin/audit.html",
        audits=db.session.scalars(
            db.select(AuditLog).order_by(AuditLog.created_at.desc()).limit(100)
        ).all(),
        logins=db.session.scalars(
            db.select(LoginLog).order_by(LoginLog.created_at.desc()).limit(100)
        ).all(),
    )


@admin_bp.get("/images/")
@permission_required("images.moderate")
def images():
    status = request.args.get("status", "active")
    if status not in {"active", "trashed", "quarantined", "all"}:
        status = "active"
    query = request.args.get("q", "").strip()
    statement = db.select(ImageAsset).order_by(ImageAsset.created_at.desc())
    if status != "all":
        statement = statement.where(ImageAsset.status == status)
    if query:
        term = f"%{query}%"
        statement = statement.join(User, User.id == ImageAsset.owner_id).where(
            db.or_(
                ImageAsset.title.ilike(term),
                ImageAsset.original_name.ilike(term),
                User.username.ilike(term),
            )
        )
    return render_template(
        "admin/images.html",
        images=db.session.scalars(statement).unique().all(),
        status=status,
        query=query,
        empty_form=EmptyForm(),
    )


@admin_bp.get("/albums/")
@permission_required("images.moderate")
def albums():
    status = request.args.get("status", "all")
    if status not in {"active", "hidden", "all"}:
        status = "all"
    query = request.args.get("q", "").strip()
    statement = db.select(Album).order_by(Album.created_at.desc())
    if status != "all":
        statement = statement.where(Album.status == status)
    if query:
        term = f"%{query}%"
        statement = statement.join(User, User.id == Album.owner_id).where(
            db.or_(
                Album.title.ilike(term),
                Album.description.ilike(term),
                User.username.ilike(term),
            )
        )
    return render_template(
        "admin/albums.html",
        albums=db.session.scalars(statement).unique().all(),
        status=status,
        query=query,
        empty_form=EmptyForm(),
    )


@admin_bp.get("/api-tokens/")
@permission_required("api.tokens.admin")
def api_tokens():
    status = request.args.get("status", "active")
    if status not in {"active", "revoked", "expired", "all"}:
        status = "active"
    query = request.args.get("q", "").strip()
    statement = db.select(ApiToken).join(User, User.id == ApiToken.user_id)
    now = utc_now()
    if status == "active":
        statement = statement.where(
            ApiToken.revoked_at.is_(None),
            ApiToken.expires_at > now,
        )
    elif status == "revoked":
        statement = statement.where(ApiToken.revoked_at.is_not(None))
    elif status == "expired":
        statement = statement.where(
            ApiToken.revoked_at.is_(None),
            ApiToken.expires_at <= now,
        )
    if query:
        term = f"%{query}%"
        statement = statement.where(
            db.or_(
                ApiToken.name.ilike(term),
                ApiToken.token_prefix.ilike(term),
                User.username.ilike(term),
            )
        )
    return render_template(
        "admin/api_tokens.html",
        tokens=db.session.scalars(statement.order_by(ApiToken.created_at.desc())).unique().all(),
        status=status,
        query=query,
        now=now,
        empty_form=EmptyForm(),
    )


@admin_bp.post("/api-tokens/<int:token_id>/revoke/")
@permission_required("api.tokens.admin")
def revoke_api_token_admin(token_id: int):
    form = EmptyForm()
    if not form.validate_on_submit():
        abort(400)
    token = db.get_or_404(ApiToken, token_id)
    revoke_api_token(token)
    record_audit("admin.api_token.revoke", "api_token", str(token.id), "管理员收回应用钥匙")
    db.session.commit()
    flash("应用钥匙已收回。", "success")
    return redirect(url_for("admin.api_tokens", status=request.args.get("status", "active")))


@admin_bp.get("/favorites/")
@permission_required("images.moderate")
def favorites():
    query = request.args.get("q", "").strip()
    statement = (
        db.select(ImageFavorite)
        .join(User, User.id == ImageFavorite.user_id)
        .join(ImageAsset, ImageAsset.id == ImageFavorite.image_id)
    )
    if query:
        term = f"%{query}%"
        statement = statement.where(
            db.or_(
                User.username.ilike(term),
                ImageAsset.title.ilike(term),
                ImageAsset.original_name.ilike(term),
            )
        )
    return render_template(
        "admin/favorites.html",
        favorites=db.session.scalars(statement.order_by(ImageFavorite.created_at.desc()).limit(200))
        .unique()
        .all(),
        query=query,
        empty_form=EmptyForm(),
    )


@admin_bp.post("/favorites/<int:favorite_id>/delete/")
@permission_required("images.moderate")
def delete_favorite(favorite_id: int):
    form = EmptyForm()
    if not form.validate_on_submit():
        abort(400)
    favorite = db.get_or_404(ImageFavorite, favorite_id)
    record_audit(
        "admin.favorite.delete",
        "image_favorite",
        str(favorite.id),
        "管理员清理收藏关系",
    )
    db.session.delete(favorite)
    db.session.commit()
    flash("收藏关系已清理，图片文件没有受到影响。", "success")
    return redirect(url_for("admin.favorites"))


@admin_bp.post("/albums/<int:album_id>/<string:action>/")
@permission_required("images.moderate")
def album_action(album_id: int, action: str):
    form = EmptyForm()
    if not form.validate_on_submit():
        abort(400)
    album = db.get_or_404(Album, album_id)
    messages = {
        "hide": "相册已隐藏，公开交付已经停止。",
        "restore": "相册已恢复公开交付。",
        "feature": "相册已加入精选。",
        "unfeature": "相册已取消精选。",
        "delete": "相册已删除，图片文件没有受到影响。",
    }
    if action == "hide":
        album.status = "hidden"
        album.is_featured = False
    elif action == "restore":
        album.status = "active"
    elif action == "feature":
        if album.status != "active" or album.visibility != "public":
            abort(400)
        album.is_featured = True
    elif action == "unfeature":
        album.is_featured = False
    elif action == "delete":
        db.session.delete(album)
    else:
        abort(404)
    record_audit(f"admin.album.{action}", "album", str(album_id), messages[action])
    db.session.commit()
    flash(messages[action], "success")
    return redirect(url_for("admin.albums", status=request.args.get("status", "all")))


@admin_bp.post("/images/<int:image_id>/<string:action>/")
@permission_required("images.moderate")
def image_action(image_id: int, action: str):
    form = EmptyForm()
    if not form.validate_on_submit():
        abort(400)
    image = db.get_or_404(ImageAsset, image_id)
    keys: list[str] = []
    messages = {
        "approve": "图片已通过审核并恢复交付。",
        "quarantine": "图片已隔离，所有公开交付已经停止。",
        "trash": "图片已移入所有者回收站。",
        "restore": "图片已恢复。",
        "purge": "图片及其变体已永久删除。",
    }
    if action == "approve":
        image.status = "active"
        image.moderation_status = "approved"
        image.trashed_at = None
    elif action == "quarantine":
        image.status = "quarantined"
        image.moderation_status = "rejected"
        image.trashed_at = None
    elif action == "trash":
        image.status = "trashed"
        image.trashed_at = utc_now()
    elif action == "restore":
        image.status = "active"
        image.moderation_status = "approved"
        image.trashed_at = None
    elif action == "purge":
        keys = image_storage_keys(image)
        db.session.delete(image)
    else:
        abort(404)
    record_audit(
        f"admin.image.{action}",
        "image_asset",
        str(image_id),
        f"管理员执行图片操作：{audit_action(f'admin.image.{action}')}",
    )
    db.session.commit()
    if keys:
        delete_storage_keys(keys)
    flash(messages[action], "success")
    return redirect(url_for("admin.images", status=request.args.get("status", "all")))


@admin_bp.get("/storage/")
@permission_required("images.moderate")
def storage():
    original_bytes = (
        db.session.scalar(db.select(db.func.coalesce(db.func.sum(ImageAsset.byte_size), 0))) or 0
    )
    variant_bytes = (
        db.session.scalar(db.select(db.func.coalesce(db.func.sum(ImageVariant.byte_size), 0))) or 0
    )
    users = db.session.scalars(db.select(User).order_by(User.username)).unique().all()
    usage_rows = []
    for user in users:
        used_bytes, used_count = storage_usage(user.id)
        usage_rows.append((user, used_bytes, used_count))
    return render_template(
        "admin/storage.html",
        image_count=ImageAsset.query.count(),
        trashed_count=ImageAsset.query.filter_by(status="trashed").count(),
        quarantined_count=ImageAsset.query.filter_by(status="quarantined").count(),
        original_bytes=original_bytes,
        variant_bytes=variant_bytes,
        usage_rows=usage_rows,
    )
