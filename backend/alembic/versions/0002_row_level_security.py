"""row level security policies

Revision ID: 0002_rls
Revises: 27e66f7e965c
Create Date: 2026-07-27

Declares RLS on every account-owned table so that any direct Postgres/
Supabase client (anon or authenticated key, e.g. PostgREST) can only ever
see rows belonging to the account referenced by the `request.jwt.claims`-
derived `app.account_id` setting. See docs/data-model.md ('Retention &
RLS model') for why the FastAPI backend itself connects as the table
owner (a privileged role, analogous to Supabase's service_role) and is
therefore NOT subject to these policies — it enforces the same account_id
boundary explicitly in every query instead (get_current_account_id is a
dependency on every router). This mirrors Supabase's own architecture,
where RLS protects anon/authenticated access and service-role access is
trusted server-side code.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0002_rls"
down_revision: Union[str, None] = "27e66f7e965c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

DIRECT_ACCOUNT_TABLES = [
    "profiles",
    "communities",
    "watch_profiles",
    "topics",
    "conversations",
    "conversation_actions",
    "alert_settings",
    "alert_deliveries",
    "reddit_connections",
    "audit_logs",
]

# (table, join_column, parent_table)
CHILD_TABLES = [
    ("conversation_analysis", "conversation_id", "conversations"),
    ("conversation_scores", "conversation_id", "conversations"),
    ("reply_drafts", "conversation_id", "conversations"),
    ("conversation_outcomes", "conversation_id", "conversations"),
    ("topic_keywords", "topic_id", "topics"),
    ("topic_exclusions", "topic_id", "topics"),
    ("watch_profile_communities", "watch_profile_id", "watch_profiles"),
]


def upgrade() -> None:
    op.execute("ALTER TABLE accounts ENABLE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY account_isolation ON accounts
        USING (id = current_setting('app.account_id', true)::uuid)
        """
    )

    for table in DIRECT_ACCOUNT_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY account_isolation ON {table}
            USING (account_id = current_setting('app.account_id', true)::uuid)
            """
        )

    for table, join_column, parent in CHILD_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY account_isolation ON {table}
            USING (EXISTS (
                SELECT 1 FROM {parent}
                WHERE {parent}.id = {table}.{join_column}
                AND {parent}.account_id = current_setting('app.account_id', true)::uuid
            ))
            """
        )


def downgrade() -> None:
    for table, _, _ in CHILD_TABLES:
        op.execute(f"DROP POLICY IF EXISTS account_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
    for table in DIRECT_ACCOUNT_TABLES:
        op.execute(f"DROP POLICY IF EXISTS account_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS account_isolation ON accounts")
    op.execute("ALTER TABLE accounts DISABLE ROW LEVEL SECURITY")
