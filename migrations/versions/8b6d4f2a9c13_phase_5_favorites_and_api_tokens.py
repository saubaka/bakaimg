"""phase 5 favorites and api tokens

Revision ID: 8b6d4f2a9c13
Revises: 5e8a92b4c1d7
Create Date: 2026-07-28 17:00:00

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "8b6d4f2a9c13"
down_revision = "5e8a92b4c1d7"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "api_tokens",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("token_prefix", sa.String(length=16), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("scopes", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_api_tokens_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_api_tokens")),
    )
    with op.batch_alter_table("api_tokens", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_api_tokens_expires_at"), ["expires_at"], unique=False)
        batch_op.create_index(
            batch_op.f("ix_api_tokens_last_used_at"),
            ["last_used_at"],
            unique=False,
        )
        batch_op.create_index(batch_op.f("ix_api_tokens_revoked_at"), ["revoked_at"], unique=False)
        batch_op.create_index(
            batch_op.f("ix_api_tokens_token_hash"),
            ["token_hash"],
            unique=True,
        )
        batch_op.create_index(
            batch_op.f("ix_api_tokens_token_prefix"),
            ["token_prefix"],
            unique=True,
        )
        batch_op.create_index(batch_op.f("ix_api_tokens_user_id"), ["user_id"], unique=False)
        batch_op.create_index(
            "ix_api_tokens_user_active",
            ["user_id", "revoked_at", "expires_at"],
            unique=False,
        )

    op.create_table(
        "image_favorites",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("image_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["image_id"],
            ["image_assets.id"],
            name=op.f("fk_image_favorites_image_id_image_assets"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_image_favorites_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_image_favorites")),
        sa.UniqueConstraint("user_id", "image_id", name="uq_image_favorites_user_image"),
    )
    with op.batch_alter_table("image_favorites", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_image_favorites_image_id"), ["image_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_image_favorites_user_id"), ["user_id"], unique=False)
        batch_op.create_index(
            "ix_image_favorites_user_created",
            ["user_id", "created_at"],
            unique=False,
        )


def downgrade():
    with op.batch_alter_table("image_favorites", schema=None) as batch_op:
        batch_op.drop_index("ix_image_favorites_user_created")
        batch_op.drop_index(batch_op.f("ix_image_favorites_user_id"))
        batch_op.drop_index(batch_op.f("ix_image_favorites_image_id"))
    op.drop_table("image_favorites")

    with op.batch_alter_table("api_tokens", schema=None) as batch_op:
        batch_op.drop_index("ix_api_tokens_user_active")
        batch_op.drop_index(batch_op.f("ix_api_tokens_user_id"))
        batch_op.drop_index(batch_op.f("ix_api_tokens_token_prefix"))
        batch_op.drop_index(batch_op.f("ix_api_tokens_token_hash"))
        batch_op.drop_index(batch_op.f("ix_api_tokens_revoked_at"))
        batch_op.drop_index(batch_op.f("ix_api_tokens_last_used_at"))
        batch_op.drop_index(batch_op.f("ix_api_tokens_expires_at"))
    op.drop_table("api_tokens")
