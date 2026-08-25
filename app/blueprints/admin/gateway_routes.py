"""Cloudgate connection administration and local administrator binding."""

from __future__ import annotations

import ipaddress
from urllib.parse import urlsplit, urlunsplit

from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import current_user

from app.blueprints.admin import admin_bp
from app.extensions import db
from app.forms import EmptyForm, GatewayConnectionForm
from app.models import GatewayConfiguration, GatewayIdentitySession
from app.security import permission_required, record_audit
from app.services.gateway import (
    GatewayError,
    encrypt_gateway_client_secret,
    gateway_admin_is_bound,
    gateway_callback_url,
    gateway_connection_is_configured,
    gateway_is_enabled,
    gateway_portal_url,
    get_discovery,
    get_gateway_configuration,
    reset_gateway_admin_binding_and_sessions,
    reset_gateway_binding_and_sessions,
    revoke_gateway_sessions,
)


def _loopback_hostname(hostname: str | None) -> bool:
    if not hostname:
        return False
    if hostname.casefold() == "localhost":
        return True
    try:
        return ipaddress.ip_address(hostname).is_loopback
    except ValueError:
        return False


def _normalize_http_url(
    value: str,
    *,
    label: str,
    callback: bool = False,
) -> str:
    parts = urlsplit(value.strip())
    if (
        parts.scheme not in {"http", "https"}
        or not parts.hostname
        or parts.username
        or parts.password
        or parts.query
        or parts.fragment
    ):
        raise ValueError(f"{label}必须是完整的HTTP(S)地址，且不能包含账号、查询或片段。")
    if parts.scheme == "http" and not _loopback_hostname(parts.hostname):
        raise ValueError(f"{label}只有本机回环地址可以使用HTTP，其他地址必须使用HTTPS。")
    path = parts.path or ""
    if callback and not path.endswith("/auth/callback/"):
        raise ValueError("回调地址必须以/auth/callback/结尾。")
    normalized_path = path.rstrip("/") if not callback else path
    return urlunsplit((parts.scheme, parts.netloc, normalized_path, "", ""))


def _populate_connection_form(
    form: GatewayConnectionForm,
    configuration: GatewayConfiguration | None,
) -> None:
    if configuration is None:
        form.issuer.data = "http://127.0.0.1:5100"
        return
    form.issuer.data = configuration.issuer
    form.client_id.data = configuration.client_id


def _render_gateway_settings():
    configuration = get_gateway_configuration()
    configured = gateway_connection_is_configured()
    bound = gateway_admin_is_bound()
    connection_form = GatewayConnectionForm()
    if request.method == "GET":
        _populate_connection_form(connection_form, configuration)

    discovery = None
    discovery_error = None
    if configured:
        try:
            discovery = get_discovery(force=True)
        except GatewayError as error:
            discovery_error = str(error)
    return render_template(
        "admin/gateway.html",
        connection_form=connection_form,
        delete_form=EmptyForm(),
        configuration=configuration,
        configured=configured,
        bound=bound,
        enabled=gateway_is_enabled(),
        callback_url=gateway_callback_url(),
        portal_url=gateway_portal_url() if configured else "",
        discovery=discovery,
        discovery_error=discovery_error,
    )


@admin_bp.get("/gateway/")
@permission_required("system.maintain")
def gateway_settings():
    return _render_gateway_settings()


@admin_bp.post("/gateway/connection/")
@permission_required("system.maintain")
def gateway_connection_save():
    form = GatewayConnectionForm()
    configuration = get_gateway_configuration()
    if not form.validate_on_submit():
        for field in form:
            if field.errors:
                flash(field.errors[0], "error")
                break
        return redirect(url_for("admin.gateway_settings"))
    if configuration is None and not form.client_secret.data:
        flash("首次创建连接时必须填写Client Secret。", "error")
        return redirect(url_for("admin.gateway_settings"))
    try:
        issuer = _normalize_http_url(form.issuer.data, label="发行者地址")
        redirect_uri = _normalize_http_url(
            url_for("gateway.callback", _external=True),
            label="回调地址",
            callback=True,
        )
    except ValueError as error:
        flash(str(error), "error")
        return redirect(url_for("admin.gateway_settings"))

    previous_protocol = (
        (
            configuration.issuer,
            configuration.client_id,
            configuration.redirect_uri,
        )
        if configuration
        else None
    )
    if configuration is None:
        configuration = GatewayConfiguration()
        db.session.add(configuration)
        action = "gateway.connection.create"
        connection_created = True
    else:
        action = "gateway.connection.update"
        connection_created = False
    configuration.name = "统一登录"
    configuration.issuer = issuer
    configuration.client_id = form.client_id.data.strip()
    if form.client_secret.data:
        configuration.client_secret_encrypted = encrypt_gateway_client_secret(
            form.client_secret.data
        )
    configuration.redirect_uri = redirect_uri
    configuration.scopes = "openid profile email avatar"
    configuration.application_name = ""
    configuration.application_description = ""
    configuration.application_homepage_url = ""
    configuration.privacy_policy_url = ""
    configuration.application_icon_url = ""
    if connection_created:
        configuration.http_timeout_seconds = 8
        configuration.introspection_interval_seconds = 300
        configuration.refresh_token_ttl_days = 30

    protocol_changed = bool(
        previous_protocol
        and previous_protocol
        != (
            configuration.issuer,
            configuration.client_id,
            configuration.redirect_uri,
        )
    )
    credentials_changed = bool(previous_protocol and form.client_secret.data)
    binding_reset = gateway_admin_is_bound() and protocol_changed
    if connection_created or binding_reset:
        reset_gateway_binding_and_sessions()
    elif credentials_changed:
        revoke_gateway_sessions()
    record_audit(
        action,
        "gateway",
        "primary",
        f"{configuration.name} · {configuration.issuer}",
    )
    db.session.commit()

    try:
        get_discovery(force=True)
    except GatewayError as error:
        flash(f"连接已保存，但实时验证未通过：{error}", "warning")
    else:
        if binding_reset:
            flash("连接已更新并验证通过。协议参数发生变化，请重新绑定管理员。", "success")
        elif credentials_changed:
            flash("连接密钥已更新并验证通过，旧登录会话已经撤销。", "success")
        elif current_user.gateway_subject:
            flash("网关连接已更新并验证通过。", "success")
        else:
            flash("连接已创建并验证通过。下一步请先绑定当前管理员。", "success")
    return redirect(url_for("admin.gateway_settings"))


@admin_bp.post("/gateway/connection/delete/")
@permission_required("system.maintain")
def gateway_connection_delete():
    form = EmptyForm()
    if not form.validate_on_submit():
        abort(400)
    configuration = get_gateway_configuration()
    if configuration is None:
        abort(404)
    reset_gateway_admin_binding_and_sessions()
    db.session.execute(db.delete(GatewayIdentitySession))
    db.session.delete(configuration)
    record_audit(
        "gateway.connection.delete",
        "gateway",
        "primary",
        f"删除连接 {configuration.name}",
    )
    db.session.commit()
    flash("网关连接、管理员绑定和本地网关会话已经删除。", "info")
    return redirect(url_for("admin.gateway_settings"))


@admin_bp.post("/gateway/unlink/")
@permission_required("system.maintain")
def gateway_unlink():
    if not current_user.gateway_subject:
        abort(404)
    previous = current_user.gateway_subject
    reset_gateway_binding_and_sessions()
    record_audit(
        "gateway.identity.unlink",
        "user",
        str(current_user.id),
        f"解除统一登录身份 {previous}",
    )
    db.session.commit()
    flash("管理员绑定已解除，统一登录与管理员识别已经关闭。", "info")
    return redirect(url_for("admin.gateway_settings"))
