"""后台里显示给人看的中文名称：把内部代码换成直接的说法。"""

from __future__ import annotations

AUDIT_ACTIONS = {
    "auth.local_login": "登录",
    "auth.local_logout": "退出登录",
    "auth.local_register": "创建账号",
    "auth.local_recovery": "本机恢复登录",
    "image.upload": "上传图片",
    "image.update": "修改图片信息",
    "image.trash": "移入回收站",
    "image.restore": "从回收站恢复",
    "image.purge": "永久删除图片",
    "favorite.add": "收藏图片",
    "favorite.remove": "取消收藏",
    "album.create": "创建相册",
    "album.update": "修改相册",
    "album.reorder": "调整相册顺序",
    "album.delete": "删除相册",
    "api.token.create": "创建应用钥匙",
    "api.token.revoke": "收回应用钥匙",
    "admin.api_token.revoke": "后台收回应用钥匙",
    "admin.user.update": "修改账号",
    "admin.role.update": "修改角色权限",
    "admin.favorite.delete": "清理收藏关系",
    "admin.image.approve": "通过图片",
    "admin.image.quarantine": "隔离图片",
    "admin.image.trash": "回收图片",
    "admin.image.restore": "恢复图片",
    "admin.image.purge": "永久删除图片",
    "admin.album.hide": "隐藏相册",
    "admin.album.restore": "恢复相册",
    "admin.album.feature": "设为精选相册",
    "admin.album.unfeature": "取消精选相册",
    "admin.album.delete": "删除相册",
    "admin.appearance.hints": "修改菜单提示设置",
    "admin.appearance.transitions": "修改页面动画设置",
    "admin.appearance.dialogs": "修改弹窗设置",
    "admin.backup.create": "创建备份",
    "admin.backup.verify": "检查备份",
    "admin.maintenance.update": "修改维护模式",
    "gateway.connection.delete": "删除外部登录方式",
    "gateway.identity.link": "绑定外部账号",
    "gateway.identity.unlink": "解除外部账号",
    "gateway.user.provision": "创建外部登录账号",
}

LOGIN_REASONS = {
    "local": "账号登录",
    "local-invalid": "用户名或密码不正确",
    "local-register": "新账号登录",
    "local-recovery": "本机恢复",
    "cloudgate": "外部登录",
    "admin-not-bound": "外部账号没有后台权限",
}

OPERATION_ACTIONS = {
    "backup.create": "创建备份",
    "backup.verify": "检查备份",
    "maintenance": "维护模式",
}

OPERATION_STATUSES = {"success": "成功", "failed": "失败", "ok": "正常", "error": "出错"}

HEALTH = {
    "ok": "正常",
    "error": "异常",
    "outdated": "需要更新",
    "missing": "缺失",
    "warning": "需留意",
}

SCOPES = {"images:read": "查看自己的图片", "images:write": "上传和整理图片"}

ROLES = {
    "member": "普通用户",
    "moderator": "审核员",
    "administrator": "管理员",
    "superadmin": "超级管理员",
}


def audit_action(code: str) -> str:
    return AUDIT_ACTIONS.get(code, code)


def login_reason(code: str) -> str:
    return LOGIN_REASONS.get(code, code)


def operation_action(code: str) -> str:
    return OPERATION_ACTIONS.get(code, code)


def operation_status(code: str) -> str:
    return OPERATION_STATUSES.get(code, code)


def scope_labels(scopes: str) -> str:
    return " · ".join(SCOPES.get(item, item) for item in scopes.split(",") if item)


def role_name(code: str) -> str:
    return ROLES.get(code, code)


def health(code: str) -> str:
    return HEALTH.get(str(code), str(code))
