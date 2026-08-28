"""Reddit ingestion watermark, rate-limit and job metrics fields."""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "0005_reddit_ingestion"
down_revision: Union[str, None] = "0004_email_not_unique"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("communities", sa.Column("reddit_watermark_id", sa.String(length=32), nullable=True))
    op.add_column("communities", sa.Column("reddit_watermark_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("communities", sa.Column("reddit_last_fetch_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("communities", sa.Column("reddit_last_success_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("communities", sa.Column("reddit_last_error", sa.Text(), nullable=False, server_default=""))
    op.add_column("communities", sa.Column("reddit_rate_remaining", sa.Float(), nullable=True))
    op.add_column("communities", sa.Column("reddit_rate_used", sa.Float(), nullable=True))
    op.add_column("communities", sa.Column("reddit_rate_reset_seconds", sa.Float(), nullable=True))
    op.add_column("watch_profiles", sa.Column("max_age_hours", sa.Integer(), nullable=False, server_default="72"))
    op.add_column("scheduled_job_runs", sa.Column("metrics", sa.JSON(), nullable=False, server_default="{}"))


def downgrade() -> None:
    op.drop_column("scheduled_job_runs", "metrics")
    op.drop_column("watch_profiles", "max_age_hours")
    for name in (
        "reddit_rate_reset_seconds",
        "reddit_rate_used",
        "reddit_rate_remaining",
        "reddit_last_error",
        "reddit_last_success_at",
        "reddit_last_fetch_at",
        "reddit_watermark_at",
        "reddit_watermark_id",
    ):
        op.drop_column("communities", name)
