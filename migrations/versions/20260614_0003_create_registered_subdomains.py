from alembic import op
import sqlalchemy as sa


revision = "20260614_0003"
down_revision = "20260612_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "registered_subdomains",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("domain", sa.String(length=320), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_registered_subdomains_domain",
        "registered_subdomains",
        ["domain"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_registered_subdomains_domain", table_name="registered_subdomains")
    op.drop_table("registered_subdomains")
