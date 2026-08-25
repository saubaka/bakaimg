"""Built-in role, permission and account policies."""

from __future__ import annotations

from app.extensions import db
from app.models import Permission, Role, SiteSetting, User

PERMISSIONS = {
    "admin.access": ("进入管理后台", "允许进入管理区。"),
    "users.view": ("查看用户", "查看账号与设备会话。"),
    "users.manage": ("管理用户", "编辑账号状态与角色。"),
    "roles.manage": ("管理角色", "编辑角色与权限映射。"),
    "audit.view": ("查看安全日志", "查看登录及操作审计。"),
    "system.maintain": ("维护系统", "修改身份安全设置。"),
    "images.upload": ("上传图片", "上传经过安全处理的图片。"),
    "images.manage_own": ("管理自己的图片", "管理个人图片、分享方式与相册。"),
    "images.moderate": ("审核图片", "治理全站图片、相册与存储。"),
    "favorites.manage": ("管理收藏", "收藏和整理公开图片。"),
    "api.tokens.manage": ("管理API令牌", "创建和撤销自己的程序化访问令牌。"),
    "api.tokens.admin": ("治理API令牌", "查看并撤销全站API令牌。"),
}

ROLE_DEFINITIONS = {
    "member": {
        "name": "普通用户",
        "description": "拥有个人上传、图片、分享与相册管理能力。",
        "permissions": {
            "images.upload",
            "images.manage_own",
            "favorites.manage",
            "api.tokens.manage",
        },
    },
    "moderator": {
        "name": "内容审核员",
        "description": "可进入后台处理图片审核和相册治理。",
        "permissions": {
            "admin.access",
            "users.view",
            "images.upload",
            "images.manage_own",
            "images.moderate",
            "favorites.manage",
            "api.tokens.manage",
        },
    },
    "administrator": {
        "name": "管理员",
        "description": "可管理用户、查看日志和维护常规安全设置。",
        "permissions": {
            "admin.access",
            "users.view",
            "users.manage",
            "audit.view",
            "system.maintain",
            "images.upload",
            "images.manage_own",
            "images.moderate",
            "favorites.manage",
            "api.tokens.manage",
            "api.tokens.admin",
        },
    },
    "superadmin": {
        "name": "超级管理员",
        "description": "拥有全部权限，并受最后管理员保护。",
        "permissions": set(PERMISSIONS),
    },
}

DEFAULT_SETTINGS = {
    "site_name": "baka图床",
    "site_tagline": "把喜欢的画面认真收藏起来",
    "page_transition_style": "stretch",
    "page_transition_duration": "720",
    "page_transition_color_start": "#eaf6ff",
    "page_transition_color_middle": "#f9fbff",
    "page_transition_color_end": "#fceef6",
    "admin_menu_subtitles_visible": "false",
    "dialog_style": "soft",
    "dialog_color_start": "#ffffff",
    "dialog_color_end": "#fff1f7",
    "dialog_accent": "#7eaed0",
    "dialog_radius": "30",
    "dialog_width": "510",
    "dialog_backdrop_blur": "6",
    "dialog_shadow": "soft",
    "maintenance_mode": "false",
    "maintenance_message": "正在整理图片，请稍后再来。",
}


def sync_identity_foundation() -> tuple[int, int]:
    created_permissions = 0
    permission_models: dict[str, Permission] = {}
    for code, (name, description) in PERMISSIONS.items():
        item = db.session.scalar(db.select(Permission).where(Permission.code == code))
        if item is None:
            item = Permission(code=code)
            db.session.add(item)
            created_permissions += 1
        item.name = name
        item.description = description
        permission_models[code] = item

    created_roles = 0
    for code, definition in ROLE_DEFINITIONS.items():
        role = db.session.scalar(db.select(Role).where(Role.code == code))
        if role is None:
            role = Role(code=code)
            db.session.add(role)
            created_roles += 1
        role.name = str(definition["name"])
        role.description = str(definition["description"])
        role.is_system = True
        role.permissions = [
            permission_models[permission_code]
            for permission_code in sorted(definition["permissions"])
        ]
    db.session.flush()
    return created_permissions, created_roles


def seed_settings() -> int:
    created = 0
    for key, value in DEFAULT_SETTINGS.items():
        if db.session.scalar(db.select(SiteSetting).where(SiteSetting.key == key)) is None:
            db.session.add(SiteSetting(key=key, value=value))
            created += 1
    return created


def get_setting(key: str, default: str = "") -> str:
    item = db.session.scalar(db.select(SiteSetting).where(SiteSetting.key == key))
    return item.value if item is not None else default


def set_setting(key: str, value: str) -> None:
    item = db.session.scalar(db.select(SiteSetting).where(SiteSetting.key == key))
    if item is None:
        item = SiteSetting(key=key, value=value)
        db.session.add(item)
    else:
        item.value = value


def active_superadmin_count(excluding_user_id: int | None = None) -> int:
    users = db.session.scalars(db.select(User).where(User.status == "active")).unique().all()
    return sum(1 for user in users if user.id != excluding_user_id and user.has_role("superadmin"))


def assert_not_last_superadmin(
    user: User,
    *,
    new_status: str | None = None,
    new_role_codes: set[str] | None = None,
) -> None:
    if not user.has_role("superadmin") or user.status != "active":
        return
    removes_access = new_status not in {None, "active"} or (
        new_role_codes is not None and "superadmin" not in new_role_codes
    )
    if removes_access and active_superadmin_count(excluding_user_id=user.id) == 0:
        raise ValueError("不能停用或移除最后一个有效超级管理员。")
