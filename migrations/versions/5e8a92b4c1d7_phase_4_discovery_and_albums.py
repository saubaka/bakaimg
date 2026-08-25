"""phase 4 discovery and albums

Revision ID: 5e8a92b4c1d7
Revises: 1c047d8380b8
Create Date: 2026-07-28 16:10:00

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "5e8a92b4c1d7"
down_revision = "1c047d8380b8"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "user_profiles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("bio", sa.String(length=500), nullable=False),
        sa.Column("is_public", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_user_profiles_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_profiles")),
        sa.UniqueConstraint("user_id", name=op.f("uq_user_profiles_user_id")),
    )
    with op.batch_alter_table("user_profiles", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_user_profiles_user_id"), ["user_id"], unique=True)

    with op.batch_alter_table("image_assets", schema=None, recreate="always") as batch_op:
        batch_op.drop_constraint(
            batch_op.f("ck_image_assets_image_visibility"),
            type_="check",
        )
        batch_op.add_column(
            sa.Column("view_count", sa.Integer(), server_default="0", nullable=False)
        )
        batch_op.add_column(sa.Column("published_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.create_check_constraint(
            "image_visibility",
            "visibility IN ('private', 'unlisted', 'public')",
        )
        batch_op.create_index(
            batch_op.f("ix_image_assets_published_at"),
            ["published_at"],
            unique=False,
        )

    op.create_table(
        "albums",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("public_id", sa.String(length=32), nullable=False),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=False),
        sa.Column("visibility", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("is_featured", sa.Boolean(), nullable=False),
        sa.Column("view_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('active', 'hidden')",
            name=op.f("ck_albums_album_status"),
        ),
        sa.CheckConstraint(
            "visibility IN ('private', 'unlisted', 'public')",
            name=op.f("ck_albums_album_visibility"),
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["users.id"],
            name=op.f("fk_albums_owner_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_albums")),
    )
    with op.batch_alter_table("albums", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_albums_is_featured"), ["is_featured"], unique=False)
        batch_op.create_index(batch_op.f("ix_albums_owner_id"), ["owner_id"], unique=False)
        batch_op.create_index(
            "ix_albums_owner_status_created",
            ["owner_id", "status", "created_at"],
            unique=False,
        )
        batch_op.create_index(batch_op.f("ix_albums_public_id"), ["public_id"], unique=True)
        batch_op.create_index(
            "ix_albums_visibility_status",
            ["visibility", "status"],
            unique=False,
        )

    op.create_table(
        "album_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("album_id", sa.Integer(), nullable=False),
        sa.Column("image_id", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("added_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["album_id"],
            ["albums.id"],
            name=op.f("fk_album_items_album_id_albums"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["image_id"],
            ["image_assets.id"],
            name=op.f("fk_album_items_image_id_image_assets"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_album_items")),
        sa.UniqueConstraint("album_id", "image_id", name="uq_album_items_album_image"),
        sa.UniqueConstraint("album_id", "position", name="uq_album_items_album_position"),
    )
    with op.batch_alter_table("album_items", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_album_items_album_id"), ["album_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_album_items_image_id"), ["image_id"], unique=False)


def downgrade():
    with op.batch_alter_table("album_items", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_album_items_image_id"))
        batch_op.drop_index(batch_op.f("ix_album_items_album_id"))
    op.drop_table("album_items")

    with op.batch_alter_table("albums", schema=None) as batch_op:
        batch_op.drop_index("ix_albums_visibility_status")
        batch_op.drop_index(batch_op.f("ix_albums_public_id"))
        batch_op.drop_index("ix_albums_owner_status_created")
        batch_op.drop_index(batch_op.f("ix_albums_owner_id"))
        batch_op.drop_index(batch_op.f("ix_albums_is_featured"))
    op.drop_table("albums")

    op.execute("UPDATE image_assets SET visibility = 'unlisted' WHERE visibility = 'public'")
    with op.batch_alter_table("image_assets", schema=None, recreate="always") as batch_op:
        batch_op.drop_index(batch_op.f("ix_image_assets_published_at"))
        batch_op.drop_constraint(
            batch_op.f("ck_image_assets_image_visibility"),
            type_="check",
        )
        batch_op.create_check_constraint(
            "image_visibility",
            "visibility IN ('private', 'unlisted')",
        )
        batch_op.drop_column("published_at")
        batch_op.drop_column("view_count")

    with op.batch_alter_table("user_profiles", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_user_profiles_user_id"))
    op.drop_table("user_profiles")
