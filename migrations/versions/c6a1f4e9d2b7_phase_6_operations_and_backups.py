"""phase 6 operations and backups

Revision ID: c6a1f4e9d2b7
Revises: 8b6d4f2a9c13
Create Date: 2026-07-28 18:00:00

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "c6a1f4e9d2b7"
down_revision = "8b6d4f2a9c13"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "operation_records",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("actor_id", sa.Integer(), nullable=True),
        sa.Column("action", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("archive_name", sa.String(length=255), nullable=False),
        sa.Column("checksum_sha256", sa.String(length=64), nullable=False),
        sa.Column("summary", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('success', 'failed')",
            name="operation_record_status",
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["users.id"],
            name=op.f("fk_operation_records_actor_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_operation_records")),
    )
    with op.batch_alter_table("operation_records", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_operation_records_actor_id"),
            ["actor_id"],
            unique=False,
        )
        batch_op.create_index(
            "ix_operation_records_created_action",
            ["created_at", "action"],
            unique=False,
        )


def downgrade():
    with op.batch_alter_table("operation_records", schema=None) as batch_op:
        batch_op.drop_index("ix_operation_records_created_action")
        batch_op.drop_index(batch_op.f("ix_operation_records_actor_id"))
    op.drop_table("operation_records")
