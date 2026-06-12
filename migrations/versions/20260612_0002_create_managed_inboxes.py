from alembic import op
import sqlalchemy as sa


revision = "20260612_0002"
down_revision = "20260612_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "managed_inboxes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("api_url", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("note", sa.Text(), nullable=False, server_default=""),
        sa.Column("last_preview", sa.Text(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_managed_inboxes_email", "managed_inboxes", ["email"], unique=True)
    op.create_index("ix_managed_inboxes_status", "managed_inboxes", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_managed_inboxes_status", table_name="managed_inboxes")
    op.drop_index("ix_managed_inboxes_email", table_name="managed_inboxes")
    op.drop_table("managed_inboxes")
