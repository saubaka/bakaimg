"""OpenID Connect client and encrypted Cloudgate identity sessions."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

from cryptography.exceptions import InvalidSignature
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from flask import current_app, request, session, url_for

from app.extensions import db
from app.models import GatewayConfiguration, GatewayIdentitySession, User, utc_now

GATEWAY_SESSION_KEY = "gateway_identity_token"
GATEWAY_FLOW_KEY = "gateway_oidc_flow"
VALID_INTENTS = {"frontend", "admin", "link_admin"}


class GatewayError(RuntimeError):
    """A safe, user-facing gateway integration failure."""


@dataclass(frozen=True)
class GatewayRuntimeConfiguration:
    id: int
    name: str
    issuer: str
    client_id: str
    client_secret: str
    redirect_uri: str
    scopes: str
    http_timeout_seconds: int
    introspection_interval_seconds: int
    refresh_token_ttl_days: int


def get_gateway_configuration() -> GatewayConfiguration | None:
    """Return the single local gateway connection, if one has been created."""

    return db.session.scalar(db.select(GatewayConfiguration).order_by(GatewayConfiguration.id))


def gateway_connection_is_configured() -> bool:
    item = get_gateway_configuration()
    return bool(
        item
        and item.issuer.strip()
        and item.client_id.strip()
        and item.client_secret_encrypted.strip()
        and item.redirect_uri.strip()
        and item.scopes.strip()
    )


def gateway_admin_is_bound() -> bool:
    users = (
        db.session.scalars(
            db.select(User).where(
                User.gateway_subject.is_not(None),
                User.status == "active",
            )
        )
        .unique()
        .all()
    )
    return any(user.has_permission("admin.access") for user in users)


def gateway_is_enabled() -> bool:
    """A gateway becomes operational only after a local administrator is bound."""

    return gateway_connection_is_configured() and gateway_admin_is_bound()


def gateway_callback_url() -> str:
    item = get_gateway_configuration()
    return item.redirect_uri.strip() if item else url_for("gateway.callback", _external=True)


def gateway_portal_url() -> str:
    item = get_gateway_configuration()
    if item is None:
        raise GatewayError("尚未创建登录连接。")
    return f"{item.issuer.rstrip('/')}/portal/"


def gateway_intent_is_allowed(intent: str) -> bool:
    if intent == "link_admin":
        return gateway_connection_is_configured()
    if not gateway_is_enabled():
        return False
    return intent in {"frontend", "admin"}


def revoke_gateway_sessions() -> None:
    """Revoke local OIDC sessions while preserving stable identity mappings."""
    now = utc_now()
    db.session.execute(
        db.update(GatewayIdentitySession)
        .where(GatewayIdentitySession.revoked_at.is_(None))
        .values(revoked_at=now)
    )
    session.pop(GATEWAY_SESSION_KEY, None)
    session.pop(GATEWAY_FLOW_KEY, None)
    current_app.extensions.pop("cloudnest_gateway_discovery", None)


def reset_gateway_admin_binding_and_sessions() -> None:
    """Disable unified login without orphaning ordinary image-owner mappings."""

    revoke_gateway_sessions()
    users = (
        db.session.scalars(db.select(User).where(User.gateway_subject.is_not(None))).unique().all()
    )
    for user in users:
        if user.has_permission("admin.access"):
            user.gateway_subject = None


def reset_gateway_binding_and_sessions() -> None:
    """Return the whole integration to its mandatory pre-binding state."""

    revoke_gateway_sessions()
    db.session.execute(
        db.update(User).where(User.gateway_subject.is_not(None)).values(gateway_subject=None)
    )


def safe_local_target(value: str | None, fallback: str = "/") -> str:
    if not value:
        return fallback
    target = urlsplit(value)
    if (
        target.scheme
        or target.netloc
        or not target.path.startswith("/")
        or target.path.startswith("//")
    ):
        return fallback
    return target.path + (f"?{target.query}" if target.query else "")


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _token_cipher() -> Fernet:
    material = f"{current_app.secret_key}|cloudnest-cloudgate-token-store".encode()
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(material).digest()))


def encrypt_gateway_client_secret(value: str) -> str:
    value = value.strip()
    if not value:
        raise GatewayError("Client Secret不能为空。")
    return _token_cipher().encrypt(value.encode()).decode()


def decrypt_gateway_client_secret(value: str) -> str:
    try:
        return _token_cipher().decrypt(value.encode()).decode()
    except (InvalidToken, UnicodeDecodeError) as error:
        raise GatewayError("保存的Client Secret无法解密，请重新创建网关连接。") from error


def get_gateway_runtime_configuration() -> GatewayRuntimeConfiguration:
    item = get_gateway_configuration()
    if item is None:
        raise GatewayError("尚未创建登录连接。")
    return GatewayRuntimeConfiguration(
        id=item.id,
        name=item.name,
        issuer=item.issuer.rstrip("/"),
        client_id=item.client_id,
        client_secret=decrypt_gateway_client_secret(item.client_secret_encrypted),
        redirect_uri=item.redirect_uri,
        scopes=item.scopes,
        http_timeout_seconds=item.http_timeout_seconds,
        introspection_interval_seconds=item.introspection_interval_seconds,
        refresh_token_ttl_days=item.refresh_token_ttl_days,
    )


def _encrypt_token(value: str) -> str:
    return _token_cipher().encrypt(value.encode()).decode()


def _decrypt_token(value: str) -> str:
    try:
        return _token_cipher().decrypt(value.encode()).decode()
    except (InvalidToken, UnicodeDecodeError) as error:
        raise GatewayError("本地网关会话无法解密，请重新登录。") from error


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _request_json(
    method: str,
    url: str,
    *,
    data: dict[str, str] | None = None,
    json_data: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
) -> dict:
    gateway_config = get_gateway_runtime_configuration()
    body = (
        json.dumps(json_data, ensure_ascii=False).encode("utf-8")
        if json_data is not None
        else (urlencode(data).encode() if data is not None else None)
    )
    request_headers = {
        "Accept": "application/json",
        "User-Agent": f"Cloudnest/{current_app.config['APP_VERSION']}",
        **(headers or {}),
    }
    if json_data is not None:
        request_headers["Content-Type"] = "application/json; charset=utf-8"
    elif body is not None:
        request_headers["Content-Type"] = "application/x-www-form-urlencoded"
    outbound = Request(url, data=body, headers=request_headers, method=method)
    try:
        with urlopen(  # noqa: S310 - the issuer is trusted deployment configuration
            outbound, timeout=float(gateway_config.http_timeout_seconds)
        ) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        try:
            payload = json.loads(error.read().decode("utf-8"))
            message = payload.get("error_description") or payload.get("error")
        except (UnicodeDecodeError, json.JSONDecodeError):
            message = None
        raise GatewayError(str(message or f"登录服务返回了HTTP {error.code}。")) from error
    except (URLError, TimeoutError, OSError) as error:
        raise GatewayError("暂时无法连接登录服务，请稍后重试。") from error
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise GatewayError("登录服务返回了无法识别的数据。") from error
    if not isinstance(payload, dict):
        raise GatewayError("登录服务返回的数据格式不正确。")
    return payload


def get_discovery(*, force: bool = False) -> dict:
    issuer = get_gateway_runtime_configuration().issuer
    cache = current_app.extensions.setdefault("cloudnest_gateway_discovery", {})
    cached = cache.get(issuer)
    now = datetime.now(UTC).timestamp()
    if not force and cached and now - cached["time"] < 300:
        return cached["payload"]
    payload = _request_json("GET", f"{issuer}/.well-known/openid-configuration")
    if payload.get("issuer") != issuer:
        raise GatewayError("登录服务的发行者地址不匹配。")
    required = (
        "authorization_endpoint",
        "token_endpoint",
        "userinfo_endpoint",
        "jwks_uri",
        "revocation_endpoint",
        "introspection_endpoint",
    )
    if any(not isinstance(payload.get(key), str) for key in required):
        raise GatewayError("登录服务缺少必要端点。")
    cache[issuer] = {"time": now, "payload": payload}
    return payload


def begin_authorization(
    intent: str,
    next_target: str | None = None,
    *,
    screen_hint: str = "login",
) -> str:
    if intent == "link_admin":
        if not gateway_connection_is_configured():
            raise GatewayError("请先在后台创建登录连接。")
    elif not gateway_is_enabled():
        raise GatewayError("统一登录尚未启用。")
    if intent not in VALID_INTENTS:
        raise GatewayError("无法识别登录用途。")
    if screen_hint not in {"login", "signup"}:
        raise GatewayError("无法识别登录界面。")
    verifier = secrets.token_urlsafe(48)
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    )
    flow = {
        "state": secrets.token_urlsafe(32),
        "nonce": secrets.token_urlsafe(24),
        "verifier": verifier,
        "intent": intent,
        "next": safe_local_target(next_target, "/"),
        "created_at": int(datetime.now(UTC).timestamp()),
    }
    session[GATEWAY_FLOW_KEY] = flow
    gateway_config = get_gateway_runtime_configuration()
    discovery = get_discovery()
    query = urlencode(
        {
            "response_type": "code",
            "client_id": gateway_config.client_id,
            "redirect_uri": gateway_callback_url(),
            "scope": gateway_config.scopes,
            "state": flow["state"],
            "nonce": flow["nonce"],
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "screen_hint": screen_hint,
        }
    )
    return f"{discovery['authorization_endpoint']}?{query}"


def _client_auth_header() -> str:
    gateway_config = get_gateway_runtime_configuration()
    credentials = f"{gateway_config.client_id}:{gateway_config.client_secret}"
    return "Basic " + base64.b64encode(credentials.encode()).decode()


def _verify_id_token(raw_token: str, nonce: str | None) -> dict:
    try:
        encoded_header, encoded_claims, encoded_signature = raw_token.split(".")
        header = json.loads(_b64decode(encoded_header))
        claims = json.loads(_b64decode(encoded_claims))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise GatewayError("身份令牌格式不正确。") from error
    if header.get("alg") != "RS256" or not header.get("kid"):
        raise GatewayError("身份令牌签名算法不受支持。")
    discovery = get_discovery()
    jwks = _request_json("GET", discovery["jwks_uri"])
    key = next(
        (
            item
            for item in jwks.get("keys", [])
            if isinstance(item, dict)
            and item.get("kid") == header["kid"]
            and item.get("kty") == "RSA"
        ),
        None,
    )
    if key is None:
        raise GatewayError("登录服务的签名密钥不可用。")
    try:
        public_key = rsa.RSAPublicNumbers(
            int.from_bytes(_b64decode(str(key["e"])), "big"),
            int.from_bytes(_b64decode(str(key["n"])), "big"),
        ).public_key()
        public_key.verify(
            _b64decode(encoded_signature),
            f"{encoded_header}.{encoded_claims}".encode(),
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
    except (KeyError, ValueError, InvalidSignature) as error:
        raise GatewayError("身份令牌签名验证失败。") from error
    now = int(datetime.now(UTC).timestamp())
    gateway_config = get_gateway_runtime_configuration()
    issuer = gateway_config.issuer
    audience = claims.get("aud")
    audience_ok = (
        gateway_config.client_id in audience
        if isinstance(audience, list)
        else audience == gateway_config.client_id
    )
    if claims.get("iss") != issuer or not audience_ok:
        raise GatewayError("身份令牌的发行者或接收方不匹配。")
    if int(claims.get("exp", 0)) < now - 60 or int(claims.get("iat", 0)) > now + 60:
        raise GatewayError("身份令牌已过期或时间无效。")
    if nonce is not None and not hmac.compare_digest(str(claims.get("nonce", "")), nonce):
        raise GatewayError("登录随机值不匹配。")
    if not str(claims.get("sub", "")):
        raise GatewayError("身份令牌缺少用户标识。")
    return claims


def complete_authorization() -> tuple[dict, dict, dict]:
    flow = session.pop(GATEWAY_FLOW_KEY, None)
    if not isinstance(flow, dict):
        raise GatewayError("登录流程已过期，请重新开始。")
    if int(flow.get("created_at", 0)) < int(datetime.now(UTC).timestamp()) - 600:
        raise GatewayError("登录流程已过期，请重新开始。")
    if request.args.get("error"):
        raise GatewayError("你取消了授权，本站没有获得账号信息。")
    state = str(request.args.get("state", ""))
    if not state or not hmac.compare_digest(state, str(flow.get("state", ""))):
        raise GatewayError("登录状态校验失败，请重新开始。")
    code = str(request.args.get("code", ""))
    if not code:
        raise GatewayError("登录服务没有返回授权码。")
    discovery = get_discovery()
    tokens = _request_json(
        "POST",
        discovery["token_endpoint"],
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": gateway_callback_url(),
            "code_verifier": str(flow["verifier"]),
        },
        headers={"Authorization": _client_auth_header()},
    )
    required = ("access_token", "refresh_token", "id_token")
    if any(not isinstance(tokens.get(key), str) or not tokens[key] for key in required):
        raise GatewayError("登录服务的令牌响应不完整。")
    claims = _verify_id_token(tokens["id_token"], str(flow["nonce"]))
    userinfo = _request_json(
        "GET",
        discovery["userinfo_endpoint"],
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    if str(userinfo.get("sub", "")) != str(claims["sub"]):
        raise GatewayError("用户信息与身份令牌不一致。")
    return flow, tokens, userinfo


def establish_gateway_session(tokens: dict, userinfo: dict) -> GatewayIdentitySession:
    existing = current_gateway_session(validate_remote=False)
    if existing is not None:
        existing.revoked_at = utc_now()
    raw_session = secrets.token_urlsafe(32)
    now = utc_now()
    expires_in = max(60, int(tokens.get("expires_in", 3600)))
    gateway_config = get_gateway_runtime_configuration()
    item = GatewayIdentitySession(
        token_hash=hashlib.sha256(raw_session.encode()).hexdigest(),
        gateway_subject=str(userinfo["sub"])[:100],
        preferred_username=str(userinfo.get("preferred_username") or userinfo["sub"])[:80],
        display_name=str(
            userinfo.get("name") or userinfo.get("preferred_username") or userinfo["sub"]
        )[:120],
        email=str(userinfo.get("email") or "")[:254],
        email_verified=bool(userinfo.get("email_verified")),
        avatar_url=_safe_gateway_picture_url(userinfo.get("picture")),
        scope=str(tokens.get("scope") or gateway_config.scopes)[:300],
        access_token_encrypted=_encrypt_token(str(tokens["access_token"])),
        refresh_token_encrypted=_encrypt_token(str(tokens["refresh_token"])),
        expires_at=now + timedelta(seconds=expires_in),
        refresh_expires_at=now + timedelta(days=gateway_config.refresh_token_ttl_days),
    )
    db.session.add(item)
    db.session.flush()
    session[GATEWAY_SESSION_KEY] = raw_session
    session.permanent = True
    return item


def _safe_gateway_picture_url(value: object) -> str:
    if not isinstance(value, str) or not value:
        return ""
    picture = urlsplit(value)
    issuer = urlsplit(get_gateway_runtime_configuration().issuer)
    if (
        picture.scheme != issuer.scheme
        or picture.netloc != issuer.netloc
        or not picture.path.startswith("/auth/media/avatar/")
        or picture.query
        or picture.fragment
    ):
        return ""
    return value[:800]


def gateway_picture_url_is_safe(value: str) -> bool:
    return bool(value and _safe_gateway_picture_url(value) == value)


def _sync_gateway_identity(item: GatewayIdentitySession, userinfo: dict) -> bool:
    if str(userinfo.get("sub", "")) != item.gateway_subject:
        raise GatewayError("用户信息与当前身份不一致。")
    values = {
        "preferred_username": str(userinfo.get("preferred_username") or item.gateway_subject)[:80],
        "display_name": str(
            userinfo.get("name") or userinfo.get("preferred_username") or item.gateway_subject
        )[:120],
        "email": str(userinfo.get("email") or "")[:254],
        "email_verified": bool(userinfo.get("email_verified")),
        "avatar_url": _safe_gateway_picture_url(userinfo.get("picture")),
    }
    changed = False
    for key, value in values.items():
        if getattr(item, key) != value:
            setattr(item, key, value)
            changed = True
    return changed


def _load_gateway_userinfo(item: GatewayIdentitySession) -> dict:
    discovery = get_discovery()
    return _request_json(
        "GET",
        discovery["userinfo_endpoint"],
        headers={"Authorization": f"Bearer {_decrypt_token(item.access_token_encrypted)}"},
    )


def _refresh_session(item: GatewayIdentitySession) -> None:
    discovery = get_discovery()
    tokens = _request_json(
        "POST",
        discovery["token_endpoint"],
        data={
            "grant_type": "refresh_token",
            "refresh_token": _decrypt_token(item.refresh_token_encrypted),
        },
        headers={"Authorization": _client_auth_header()},
    )
    _verify_id_token(str(tokens.get("id_token", "")), None)
    item.access_token_encrypted = _encrypt_token(str(tokens["access_token"]))
    item.refresh_token_encrypted = _encrypt_token(str(tokens["refresh_token"]))
    item.scope = str(tokens.get("scope") or item.scope)[:300]
    item.expires_at = utc_now() + timedelta(seconds=max(60, int(tokens.get("expires_in", 3600))))
    item.last_validated_at = utc_now()
    _sync_gateway_identity(item, _load_gateway_userinfo(item))


def _introspect_session(item: GatewayIdentitySession) -> bool:
    gateway_config = get_gateway_runtime_configuration()
    discovery = get_discovery()
    payload = _request_json(
        "POST",
        discovery["introspection_endpoint"],
        data={"token": _decrypt_token(item.access_token_encrypted)},
        headers={"Authorization": _client_auth_header()},
    )
    return bool(
        payload.get("active")
        and str(payload.get("sub", "")) == item.gateway_subject
        and str(payload.get("client_id", "")) == gateway_config.client_id
    )


def current_gateway_session(*, validate_remote: bool) -> GatewayIdentitySession | None:
    raw_session = session.get(GATEWAY_SESSION_KEY)
    if not isinstance(raw_session, str) or not raw_session:
        return None
    item = db.session.scalar(
        db.select(GatewayIdentitySession).where(
            GatewayIdentitySession.token_hash == hashlib.sha256(raw_session.encode()).hexdigest()
        )
    )
    now = utc_now()
    if item is None or item.revoked_at is not None or _aware(item.refresh_expires_at) <= now:
        session.pop(GATEWAY_SESSION_KEY, None)
        return None
    changed = False
    if validate_remote and gateway_is_enabled():
        try:
            if _aware(item.expires_at) <= now:
                _refresh_session(item)
                changed = True
            interval = get_gateway_runtime_configuration().introspection_interval_seconds
            if now - _aware(item.last_validated_at) >= timedelta(seconds=interval):
                if not _introspect_session(item):
                    item.revoked_at = now
                    session.pop(GATEWAY_SESSION_KEY, None)
                    db.session.commit()
                    return None
                if _sync_gateway_identity(item, _load_gateway_userinfo(item)):
                    changed = True
                item.last_validated_at = now
                changed = True
        except GatewayError:
            current_app.logger.warning("gateway session validation failed", exc_info=True)
            if _aware(item.expires_at) <= now:
                item.revoked_at = now
                session.pop(GATEWAY_SESSION_KEY, None)
                db.session.commit()
                return None
    if now - _aware(item.last_seen_at) >= timedelta(minutes=10):
        item.last_seen_at = now
        changed = True
    if changed:
        db.session.commit()
    return item


def terminate_gateway_session(item: GatewayIdentitySession | None = None) -> None:
    item = item or current_gateway_session(validate_remote=False)
    if item is None:
        session.pop(GATEWAY_SESSION_KEY, None)
        return
    if gateway_is_enabled():
        try:
            discovery = get_discovery()
            for encrypted in (item.access_token_encrypted, item.refresh_token_encrypted):
                _request_json(
                    "POST",
                    discovery["revocation_endpoint"],
                    data={"token": _decrypt_token(encrypted)},
                    headers={"Authorization": _client_auth_header()},
                )
        except GatewayError:
            current_app.logger.warning("gateway token revocation failed", exc_info=True)
    item.revoked_at = utc_now()
    db.session.commit()
    session.pop(GATEWAY_SESSION_KEY, None)
