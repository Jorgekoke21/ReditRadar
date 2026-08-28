"""Single-use, account-bound CSRF state for the Reddit OAuth callback."""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "0006_reddit_oauth_state"
down_revision: Union[str, None] = "0005_reddit_ingestion"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ROLES = ("radar_app", "radar_worker")


def upgrade() -> None:
    op.create_table(
        "reddit_oauth_states",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("state", sa.String(length=128), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_reddit_oauth_states_account_id", "reddit_oauth_states", ["account_id"])
    op.create_index("ix_reddit_oauth_states_state", "reddit_oauth_states", ["state"], unique=True)

    # Postgres-only hardening. The SQLite test database has no roles or RLS;
    # the same isolation is asserted there by the ownership tests instead.
    if op.get_bind().dialect.name != "postgresql":
        return

    for role in _ROLES:
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON reddit_oauth_states TO {role}")

    op.execute("ALTER TABLE reddit_oauth_states ENABLE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS account_isolation ON reddit_oauth_states")
    op.execute(
        """
        CREATE POLICY account_isolation ON reddit_oauth_states
        FOR ALL
        USING (account_id = current_setting('app.account_id', true)::uuid)
        WITH CHECK (account_id = current_setting('app.account_id', true)::uuid)
        """
    )
    op.execute("ALTER TABLE reddit_oauth_states FORCE ROW LEVEL SECURITY")


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("ALTER TABLE reddit_oauth_states NO FORCE ROW LEVEL SECURITY")
        op.execute("DROP POLICY IF EXISTS account_isolation ON reddit_oauth_states")
    op.drop_index("ix_reddit_oauth_states_state", table_name="reddit_oauth_states")
    op.drop_index("ix_reddit_oauth_states_account_id", table_name="reddit_oauth_states")
    op.drop_table("reddit_oauth_states")
