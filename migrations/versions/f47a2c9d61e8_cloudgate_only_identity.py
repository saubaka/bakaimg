"""Replace public local credentials with Cloudgate OIDC identity."""

import sqlalchemy as sa
from alembic import op

revision = "f47a2c9d61e8"
down_revision = "c6a1f4e9d2b7"
branch_labels = None
depends_on = None


def _drop_superadmin_triggers() -> None:
    op.execute("DROP TRIGGER IF EXISTS protect_last_superadmin_delete")
    op.execute("DROP TRIGGER IF EXISTS protect_last_superadmin_role")
    op.execute("DROP TRIGGER IF EXISTS protect_last_superadmin_status")


def _create_superadmin_triggers() -> None:
    op.execute(
        """
        CREATE TRIGGER protect_last_superadmin_status
        BEFORE UPDATE OF status ON users
        WHEN OLD.status = 'active'
          AND NEW.status <> 'active'
          AND EXISTS (
            SELECT 1 FROM user_roles ur
            JOIN roles r ON r.id = ur.role_id
            WHERE ur.user_id = OLD.id AND r.code = 'superadmin'
          )
          AND (
            SELECT COUNT(*) FROM users u
            JOIN user_roles ur ON ur.user_id = u.id
            JOIN roles r ON r.id = ur.role_id
            WHERE u.status = 'active' AND r.code = 'superadmin'
          ) <= 1
        BEGIN
          SELECT RAISE(ABORT, 'cannot disable the last active superadmin');
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER protect_last_superadmin_role
        BEFORE DELETE ON user_roles
        WHEN EXISTS (
            SELECT 1 FROM roles r
            WHERE r.id = OLD.role_id AND r.code = 'superadmin'
          )
          AND EXISTS (
            SELECT 1 FROM users u
            WHERE u.id = OLD.user_id AND u.status = 'active'
          )
          AND (
            SELECT COUNT(*) FROM users u
            JOIN user_roles ur ON ur.user_id = u.id
            JOIN roles r ON r.id = ur.role_id
            WHERE u.status = 'active' AND r.code = 'superadmin'
          ) <= 1
        BEGIN
          SELECT RAISE(ABORT, 'cannot remove the last active superadmin role');
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER protect_last_superadmin_delete
        BEFORE DELETE ON users
        WHEN OLD.status = 'active'
          AND EXISTS (
            SELECT 1 FROM user_roles ur
            JOIN roles r ON r.id = ur.role_id
            WHERE ur.user_id = OLD.id AND r.code = 'superadmin'
          )
          AND (
            SELECT COUNT(*) FROM users u
            JOIN user_roles ur ON ur.user_id = u.id
            JOIN roles r ON r.id = ur.role_id
            WHERE u.status = 'active' AND r.code = 'superadmin'
          ) <= 1
        BEGIN
          SELECT RAISE(ABORT, 'cannot delete the last active superadmin');
        END
        """
    )


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("gateway_subject", sa.String(length=100), nullable=True),
    )
    op.create_index(
        "ix_users_gateway_subject",
        "users",
        ["gateway_subject"],
        unique=True,
    )

    op.create_table(
        "gateway_configurations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("issuer", sa.String(length=500), nullable=False),
        sa.Column("client_id", sa.String(length=200), nullable=False),
        sa.Column("client_secret_encrypted", sa.Text(), nullable=False),
        sa.Column("redirect_uri", sa.String(length=500), nullable=False),
        sa.Column("scopes", sa.String(length=300), nullable=False),
        sa.Column("application_name", sa.String(length=100), nullable=False),
        sa.Column("application_description", sa.String(length=240), nullable=False),
        sa.Column("application_homepage_url", sa.String(length=500), nullable=False),
        sa.Column("privacy_policy_url", sa.String(length=500), nullable=False),
        sa.Column("application_icon_url", sa.String(length=500), nullable=False),
        sa.Column(
            "http_timeout_seconds",
            sa.Integer(),
            nullable=False,
            server_default="8",
        ),
        sa.Column(
            "introspection_interval_seconds",
            sa.Integer(),
            nullable=False,
            server_default="300",
        ),
        sa.Column(
            "refresh_token_ttl_days",
            sa.Integer(),
            nullable=False,
            server_default="30",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "http_timeout_seconds BETWEEN 2 AND 30",
            name="ck_gateway_configurations_gateway_config_timeout",
        ),
        sa.CheckConstraint(
            "introspection_interval_seconds BETWEEN 60 AND 3600",
            name="ck_gateway_configurations_gateway_config_introspection",
        ),
        sa.CheckConstraint(
            "refresh_token_ttl_days BETWEEN 1 AND 90",
            name="ck_gateway_configurations_gateway_config_refresh_days",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "gateway_identity_sessions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("gateway_subject", sa.String(length=100), nullable=False),
        sa.Column("preferred_username", sa.String(length=80), nullable=False),
        sa.Column("display_name", sa.String(length=120), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=False, server_default=""),
        sa.Column(
            "email_verified",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("avatar_url", sa.String(length=800), nullable=False, server_default=""),
        sa.Column(
            "scope",
            sa.String(length=300),
            nullable=False,
            server_default="openid profile email avatar",
        ),
        sa.Column("access_token_encrypted", sa.Text(), nullable=False),
        sa.Column("refresh_token_encrypted", sa.Text(), nullable=False),
        sa.Column("linked_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_validated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("refresh_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["linked_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index(
        "ix_gateway_identity_sessions_token_hash",
        "gateway_identity_sessions",
        ["token_hash"],
        unique=True,
    )
    op.create_index(
        "ix_gateway_identity_sessions_gateway_subject",
        "gateway_identity_sessions",
        ["gateway_subject"],
        unique=False,
    )
    op.create_index(
        "ix_gateway_identity_sessions_linked_user_id",
        "gateway_identity_sessions",
        ["linked_user_id"],
        unique=False,
    )
    op.create_index(
        "ix_gateway_identity_sessions_expires_at",
        "gateway_identity_sessions",
        ["expires_at"],
        unique=False,
    )
    op.create_index(
        "ix_gateway_identity_sessions_revoked_at",
        "gateway_identity_sessions",
        ["revoked_at"],
        unique=False,
    )
    op.create_index(
        "ix_gateway_identity_sessions_subject_active",
        "gateway_identity_sessions",
        ["gateway_subject", "revoked_at", "expires_at"],
        unique=False,
    )
    op.execute("DELETE FROM site_settings WHERE key = 'registration_open'")


def downgrade() -> None:
    op.drop_table("gateway_identity_sessions")
    op.drop_table("gateway_configurations")
    _drop_superadmin_triggers()
    with op.batch_alter_table("users") as batch:
        batch.drop_index("ix_users_gateway_subject")
        batch.drop_column("gateway_subject")
    _create_superadmin_triggers()
    op.execute(
        "INSERT OR IGNORE INTO site_settings (key, value, updated_at) "
        "VALUES ('registration_open', 'false', CURRENT_TIMESTAMP)"
    )
