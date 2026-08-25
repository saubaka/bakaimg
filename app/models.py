"""bakaimg persistence models."""

from __future__ import annotations

from datetime import UTC, datetime

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db


def utc_now() -> datetime:
    return datetime.now(UTC)


role_permissions = db.Table(
    "role_permissions",
    db.Column(
        "role_id",
        db.Integer,
        db.ForeignKey("roles.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    db.Column(
        "permission_id",
        db.Integer,
        db.ForeignKey("permissions.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)

user_roles = db.Table(
    "user_roles",
    db.Column(
        "user_id",
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    db.Column(
        "role_id",
        db.Integer,
        db.ForeignKey("roles.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class SiteSetting(db.Model):
    """Persisted product and security settings."""

    __tablename__ = "site_settings"

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(100), nullable=False, unique=True, index=True)
    value = db.Column(db.Text, nullable=False, default="")
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )


class SystemEvent(db.Model):
    """Non-sensitive operational events."""

    __tablename__ = "system_events"
    __table_args__ = (db.Index("ix_system_events_created_category", "created_at", "category"),)

    id = db.Column(db.Integer, primary_key=True)
    level = db.Column(db.String(20), nullable=False, default="info")
    category = db.Column(db.String(50), nullable=False, default="system")
    message = db.Column(db.String(255), nullable=False)
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        index=True,
    )


class OperationRecord(db.Model):
    """Non-sensitive history for operator-triggered maintenance work."""

    __tablename__ = "operation_records"
    __table_args__ = (
        db.Index("ix_operation_records_created_action", "created_at", "action"),
        db.CheckConstraint(
            "status IN ('success', 'failed')",
            name="operation_record_status",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    actor_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
    )
    action = db.Column(db.String(50), nullable=False)
    status = db.Column(db.String(20), nullable=False)
    archive_name = db.Column(db.String(255), nullable=False, default="")
    checksum_sha256 = db.Column(db.String(64), nullable=False, default="")
    summary = db.Column(db.String(255), nullable=False, default="")
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)
    actor = db.relationship("User", lazy="joined")


class Permission(db.Model):
    __tablename__ = "permissions"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(80), nullable=False, unique=True, index=True)
    name = db.Column(db.String(80), nullable=False)
    description = db.Column(db.String(255), nullable=False, default="")


class Role(db.Model):
    __tablename__ = "roles"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(50), nullable=False, unique=True, index=True)
    name = db.Column(db.String(80), nullable=False)
    description = db.Column(db.String(255), nullable=False, default="")
    is_system = db.Column(db.Boolean, nullable=False, default=True)
    permissions = db.relationship(
        "Permission",
        secondary=role_permissions,
        lazy="selectin",
        backref=db.backref("roles", lazy="selectin"),
    )


class User(UserMixin, db.Model):
    __tablename__ = "users"
    __table_args__ = (
        db.Index("ix_users_status_created", "status", "created_at"),
        db.CheckConstraint(
            "status IN ('active', 'disabled')",
            name="user_status",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), nullable=False, unique=True, index=True)
    email = db.Column(db.String(254), nullable=False, unique=True, index=True)
    display_name = db.Column(db.String(80), nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    status = db.Column(db.String(20), nullable=False, default="active")
    failed_login_count = db.Column(db.Integer, nullable=False, default=0)
    locked_until = db.Column(db.DateTime(timezone=True))
    password_changed_at = db.Column(db.DateTime(timezone=True))
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )
    last_login_at = db.Column(db.DateTime(timezone=True))
    last_seen_at = db.Column(db.DateTime(timezone=True))
    gateway_subject = db.Column(db.String(100), unique=True, index=True)
    storage_quota_bytes = db.Column(
        db.BigInteger,
        nullable=False,
        default=512 * 1024 * 1024,
        server_default=str(512 * 1024 * 1024),
    )
    image_quota_count = db.Column(
        db.Integer,
        nullable=False,
        default=1_000,
        server_default="1000",
    )
    roles = db.relationship(
        "Role",
        secondary=user_roles,
        lazy="selectin",
        backref=db.backref("users", lazy="selectin"),
    )
    profile = db.relationship(
        "UserProfile",
        cascade="all, delete-orphan",
        lazy="joined",
        back_populates="user",
        uselist=False,
    )
    api_tokens = db.relationship(
        "ApiToken",
        cascade="all, delete-orphan",
        lazy="selectin",
        back_populates="user",
    )
    favorites = db.relationship(
        "ImageFavorite",
        cascade="all, delete-orphan",
        lazy="selectin",
        back_populates="user",
    )

    @property
    def is_active(self) -> bool:
        return self.status == "active"

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)
        self.password_changed_at = utc_now()

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    def has_permission(self, code: str) -> bool:
        return any(
            permission.code in {code, "*"} for role in self.roles for permission in role.permissions
        )

    def has_role(self, code: str) -> bool:
        return any(role.code == code for role in self.roles)


class UserProfile(db.Model):
    __tablename__ = "user_profiles"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    bio = db.Column(db.String(500), nullable=False, default="")
    is_public = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )
    user = db.relationship("User", lazy="joined", back_populates="profile")


class UserSession(db.Model):
    __tablename__ = "user_sessions"
    __table_args__ = (
        db.Index("ix_user_sessions_user_active", "user_id", "revoked_at", "expires_at"),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    token_hash = db.Column(db.String(64), nullable=False, unique=True, index=True)
    ip_hash = db.Column(db.String(64), nullable=False, default="")
    user_agent = db.Column(db.String(255), nullable=False, default="")
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)
    last_seen_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)
    expires_at = db.Column(db.DateTime(timezone=True), nullable=False, index=True)
    revoked_at = db.Column(db.DateTime(timezone=True), index=True)
    user = db.relationship("User", lazy="joined")


class GatewayIdentitySession(db.Model):
    __tablename__ = "gateway_identity_sessions"
    __table_args__ = (
        db.Index(
            "ix_gateway_identity_sessions_subject_active",
            "gateway_subject",
            "revoked_at",
            "expires_at",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    token_hash = db.Column(db.String(64), unique=True, nullable=False, index=True)
    gateway_subject = db.Column(db.String(100), nullable=False, index=True)
    preferred_username = db.Column(db.String(80), nullable=False)
    display_name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(254), nullable=False, default="")
    email_verified = db.Column(db.Boolean, nullable=False, default=False)
    avatar_url = db.Column(db.String(800), nullable=False, default="")
    scope = db.Column(
        db.String(300),
        nullable=False,
        default="openid profile email avatar",
    )
    access_token_encrypted = db.Column(db.Text, nullable=False)
    refresh_token_encrypted = db.Column(db.Text, nullable=False)
    linked_user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
    )
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)
    last_seen_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)
    last_validated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
    expires_at = db.Column(db.DateTime(timezone=True), nullable=False, index=True)
    refresh_expires_at = db.Column(db.DateTime(timezone=True), nullable=False)
    revoked_at = db.Column(db.DateTime(timezone=True), index=True)
    linked_user = db.relationship("User", lazy="joined")


class GatewayConfiguration(db.Model):
    """The single Cloudgate OIDC connection managed from the local admin."""

    __tablename__ = "gateway_configurations"
    __table_args__ = (
        db.CheckConstraint(
            "http_timeout_seconds BETWEEN 2 AND 30",
            name="gateway_config_timeout",
        ),
        db.CheckConstraint(
            "introspection_interval_seconds BETWEEN 60 AND 3600",
            name="gateway_config_introspection",
        ),
        db.CheckConstraint(
            "refresh_token_ttl_days BETWEEN 1 AND 90",
            name="gateway_config_refresh_days",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False, default="统一登录")
    issuer = db.Column(db.String(500), nullable=False)
    client_id = db.Column(db.String(200), nullable=False)
    client_secret_encrypted = db.Column(db.Text, nullable=False)
    redirect_uri = db.Column(db.String(500), nullable=False)
    scopes = db.Column(
        db.String(300),
        nullable=False,
        default="openid profile email avatar",
    )
    application_name = db.Column(
        db.String(100),
        nullable=False,
        default="bakaimg",
    )
    application_description = db.Column(db.String(240), nullable=False, default="")
    application_homepage_url = db.Column(db.String(500), nullable=False, default="")
    privacy_policy_url = db.Column(db.String(500), nullable=False, default="")
    application_icon_url = db.Column(db.String(500), nullable=False, default="")
    http_timeout_seconds = db.Column(db.Integer, nullable=False, default=8)
    introspection_interval_seconds = db.Column(db.Integer, nullable=False, default=300)
    refresh_token_ttl_days = db.Column(db.Integer, nullable=False, default=30)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )


class LoginLog(db.Model):
    __tablename__ = "login_logs"
    __table_args__ = (
        db.Index("ix_login_logs_identity_created", "username", "created_at"),
        db.Index("ix_login_logs_ip_created", "ip_hash", "created_at"),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
    )
    username = db.Column(db.String(80), nullable=False, default="")
    success = db.Column(db.Boolean, nullable=False, default=False)
    reason = db.Column(db.String(80), nullable=False, default="")
    request_id = db.Column(db.String(64), nullable=False, default="")
    ip_hash = db.Column(db.String(64), nullable=False, default="")
    user_agent = db.Column(db.String(255), nullable=False, default="")
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)
    user = db.relationship("User", lazy="joined")


class AuditLog(db.Model):
    __tablename__ = "audit_logs"
    __table_args__ = (db.Index("ix_audit_logs_created_action", "created_at", "action"),)

    id = db.Column(db.Integer, primary_key=True)
    actor_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
    )
    action = db.Column(db.String(100), nullable=False)
    target_type = db.Column(db.String(80), nullable=False)
    target_id = db.Column(db.String(80), nullable=False, default="")
    summary = db.Column(db.String(255), nullable=False, default="")
    request_id = db.Column(db.String(64), nullable=False, default="")
    ip_hash = db.Column(db.String(64), nullable=False, default="")
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)
    actor = db.relationship("User", lazy="joined")


class ImageAsset(db.Model):
    __tablename__ = "image_assets"
    __table_args__ = (
        db.Index("ix_image_assets_owner_status_created", "owner_id", "status", "created_at"),
        db.Index("ix_image_assets_status_moderation", "status", "moderation_status"),
        db.Index("ix_image_assets_owner_checksum", "owner_id", "checksum_sha256"),
        db.CheckConstraint(
            "status IN ('active', 'trashed', 'quarantined')",
            name="image_status",
        ),
        db.CheckConstraint(
            "visibility IN ('private', 'unlisted', 'public')",
            name="image_visibility",
        ),
        db.CheckConstraint(
            "moderation_status IN ('pending', 'approved', 'rejected')",
            name="image_moderation",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    public_id = db.Column(db.String(32), nullable=False, unique=True, index=True)
    owner_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    original_name = db.Column(db.String(255), nullable=False)
    storage_key = db.Column(db.String(255), nullable=False, unique=True)
    mime_type = db.Column(db.String(80), nullable=False)
    image_format = db.Column(db.String(20), nullable=False)
    width = db.Column(db.Integer, nullable=False)
    height = db.Column(db.Integer, nullable=False)
    frame_count = db.Column(db.Integer, nullable=False, default=1)
    byte_size = db.Column(db.BigInteger, nullable=False)
    checksum_sha256 = db.Column(db.String(64), nullable=False, index=True)
    title = db.Column(db.String(160), nullable=False, default="")
    alt_text = db.Column(db.String(240), nullable=False, default="")
    visibility = db.Column(db.String(20), nullable=False, default="private")
    status = db.Column(db.String(20), nullable=False, default="active")
    moderation_status = db.Column(db.String(20), nullable=False, default="approved")
    view_count = db.Column(db.Integer, nullable=False, default=0)
    published_at = db.Column(db.DateTime(timezone=True), index=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )
    trashed_at = db.Column(db.DateTime(timezone=True), index=True)
    owner = db.relationship("User", lazy="joined", backref=db.backref("images", lazy="dynamic"))
    variants = db.relationship(
        "ImageVariant",
        cascade="all, delete-orphan",
        lazy="selectin",
        back_populates="image",
    )
    album_items = db.relationship(
        "AlbumItem",
        cascade="all, delete-orphan",
        lazy="selectin",
        back_populates="image",
    )
    favorites = db.relationship(
        "ImageFavorite",
        cascade="all, delete-orphan",
        lazy="selectin",
        back_populates="image",
    )

    def variant(self, kind: str) -> ImageVariant | None:
        return next((item for item in self.variants if item.kind == kind), None)


class ImageVariant(db.Model):
    __tablename__ = "image_variants"
    __table_args__ = (db.UniqueConstraint("image_id", "kind", name="uq_image_variants_image_kind"),)

    id = db.Column(db.Integer, primary_key=True)
    image_id = db.Column(
        db.Integer,
        db.ForeignKey("image_assets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    kind = db.Column(db.String(40), nullable=False)
    storage_key = db.Column(db.String(255), nullable=False, unique=True)
    mime_type = db.Column(db.String(80), nullable=False)
    image_format = db.Column(db.String(20), nullable=False)
    width = db.Column(db.Integer, nullable=False)
    height = db.Column(db.Integer, nullable=False)
    byte_size = db.Column(db.BigInteger, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)
    image = db.relationship("ImageAsset", lazy="joined", back_populates="variants")


class Album(db.Model):
    __tablename__ = "albums"
    __table_args__ = (
        db.Index("ix_albums_owner_status_created", "owner_id", "status", "created_at"),
        db.Index("ix_albums_visibility_status", "visibility", "status"),
        db.CheckConstraint(
            "visibility IN ('private', 'unlisted', 'public')",
            name="album_visibility",
        ),
        db.CheckConstraint(
            "status IN ('active', 'hidden')",
            name="album_status",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    public_id = db.Column(db.String(32), nullable=False, unique=True, index=True)
    owner_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title = db.Column(db.String(120), nullable=False)
    description = db.Column(db.String(500), nullable=False, default="")
    visibility = db.Column(db.String(20), nullable=False, default="private")
    status = db.Column(db.String(20), nullable=False, default="active")
    is_featured = db.Column(db.Boolean, nullable=False, default=False, index=True)
    view_count = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )
    owner = db.relationship("User", lazy="joined", backref=db.backref("albums", lazy="dynamic"))
    items = db.relationship(
        "AlbumItem",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="AlbumItem.position",
        back_populates="album",
    )

    @property
    def cover_image(self) -> ImageAsset | None:
        allowed = {
            "private": {"private", "unlisted", "public"},
            "unlisted": {"unlisted", "public"},
            "public": {"public"},
        }
        for item in self.items:
            image = item.image
            if (
                image.status == "active"
                and image.moderation_status == "approved"
                and image.visibility in allowed[self.visibility]
            ):
                return image
        return None


class AlbumItem(db.Model):
    __tablename__ = "album_items"
    __table_args__ = (
        db.UniqueConstraint("album_id", "image_id", name="uq_album_items_album_image"),
        db.UniqueConstraint("album_id", "position", name="uq_album_items_album_position"),
    )

    id = db.Column(db.Integer, primary_key=True)
    album_id = db.Column(
        db.Integer,
        db.ForeignKey("albums.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    image_id = db.Column(
        db.Integer,
        db.ForeignKey("image_assets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    position = db.Column(db.Integer, nullable=False)
    added_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)
    album = db.relationship("Album", lazy="joined", back_populates="items")
    image = db.relationship("ImageAsset", lazy="joined", back_populates="album_items")


class ImageFavorite(db.Model):
    __tablename__ = "image_favorites"
    __table_args__ = (
        db.UniqueConstraint("user_id", "image_id", name="uq_image_favorites_user_image"),
        db.Index("ix_image_favorites_user_created", "user_id", "created_at"),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    image_id = db.Column(
        db.Integer,
        db.ForeignKey("image_assets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)
    user = db.relationship("User", lazy="joined", back_populates="favorites")
    image = db.relationship("ImageAsset", lazy="joined", back_populates="favorites")


class ApiToken(db.Model):
    __tablename__ = "api_tokens"
    __table_args__ = (db.Index("ix_api_tokens_user_active", "user_id", "revoked_at", "expires_at"),)

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name = db.Column(db.String(80), nullable=False)
    token_prefix = db.Column(db.String(16), nullable=False, unique=True, index=True)
    token_hash = db.Column(db.String(64), nullable=False, unique=True, index=True)
    scopes = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)
    expires_at = db.Column(db.DateTime(timezone=True), nullable=False, index=True)
    last_used_at = db.Column(db.DateTime(timezone=True), index=True)
    revoked_at = db.Column(db.DateTime(timezone=True), index=True)
    user = db.relationship("User", lazy="joined", back_populates="api_tokens")

    @property
    def scope_set(self) -> set[str]:
        return {item for item in self.scopes.split(",") if item}

    @property
    def is_expired(self) -> bool:
        expires_at = self.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        return expires_at <= utc_now()

    @property
    def is_active(self) -> bool:
        return self.revoked_at is None and not self.is_expired and self.user.is_active
