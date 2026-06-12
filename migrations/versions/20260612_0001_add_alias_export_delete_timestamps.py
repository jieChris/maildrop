from alembic import op
import sqlalchemy as sa


revision = "20260612_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("aliases", sa.Column("exported_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("aliases", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("aliases", "deleted_at")
    op.drop_column("aliases", "exported_at")
