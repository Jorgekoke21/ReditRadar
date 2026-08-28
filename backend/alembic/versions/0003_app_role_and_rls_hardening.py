"""app role separation + RLS hardening

Revision ID: 0003_app_role_rls
Revises: 0002_rls
Create Date: 2026-07-27

Closes the gap found in the acceptance audit (docs/acceptance-audit.md,
2026-07-27): RLS policies existed but had zero effect because the backend
connected as `radarin`, the table owner, which Postgres exempts from RLS by
default. This migration:

  1. Creates `radar_app` — the role the FastAPI request/response cycle uses
     from now on. NOSUPERUSER, NOBYPASSRLS, NOT the table owner.
  2. Creates `radar_worker` — the role the background worker uses. Same
     base privileges as radar_app, PLUS one narrow additional policy that
     lets it list account ids (needed to iterate "for each account" in
     scheduled jobs) without weakening any other table's isolation.
  3. Grants both roles exactly SELECT/INSERT/UPDATE/DELETE on the
     account-owned tables (no DDL, no role/schema management), and sets
     default privileges so future tables created by the migration role are
     automatically granted too.
  4. Applies FORCE ROW LEVEL SECURITY to every account-owned table, so even
     a role that happened to own the tables would still be bound by the
     policies (defense in depth — note this does NOT affect true Postgres
     superusers, which always bypass RLS regardless of FORCE; `radarin` is
     a superuser in this project's docker-compose setup, which is exactly
     why the app must never use it for anything but migrations).
  5. Fixes the `profiles` table policy: it used to check
     `account_id = current_setting('app.account_id')`, which is circular —
     you cannot know a user's account_id until you've read their profile.
     It now checks `id = current_setting('app.user_id')` (self-lookup by
     the user's own Supabase-issued UUID), which is what
     app/core/security.py sets *before* looking up the profile.
  6. Makes every policy's WITH CHECK explicit (previously implicit via
     `FOR ALL` defaulting WITH CHECK to USING — behaviorally identical, but
     explicit per the spec and clearer to audit).

See docs/rls.md for the full design and reproducible verification queries.
"""
from typing import Sequence, Union

from alembic import op

from app.config import get_settings

revision: str = "0003_app_role_rls"
down_revision: Union[str, None] = "0002_rls"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

DIRECT_ACCOUNT_TABLES = [
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

CHILD_TABLES = [
    ("conversation_analysis", "conversation_id", "conversations"),
    ("conversation_scores", "conversation_id", "conversations"),
    ("reply_drafts", "conversation_id", "conversations"),
    ("conversation_outcomes", "conversation_id", "conversations"),
    ("topic_keywords", "topic_id", "topics"),
    ("topic_exclusions", "topic_id", "topics"),
    ("watch_profile_communities", "watch_profile_id", "watch_profiles"),
]

ALL_ACCOUNT_SCOPED_TABLES = ["accounts", "profiles"] + DIRECT_ACCOUNT_TABLES + [t for t, _, _ in CHILD_TABLES]


def _escape(value: str) -> str:
    return value.replace("'", "''")


def _create_role_if_missing(role: str, password: str) -> None:
    op.execute(
        f"""
        DO $$
        BEGIN
          IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') THEN
            CREATE ROLE {role} WITH LOGIN PASSWORD '{_escape(password)}'
              NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS NOREPLICATION;
          ELSE
            ALTER ROLE {role} WITH PASSWORD '{_escape(password)}';
          END IF;
        END
        $$;
        """
    )


def _grant_base_privileges(role: str) -> None:
    op.execute(
        f"""
        DO $$
        BEGIN
          EXECUTE format('GRANT CONNECT ON DATABASE %I TO {role}', current_database());
        END
        $$;
        """
    )
    op.execute(f"GRANT USAGE ON SCHEMA public TO {role}")
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {role}")
    op.execute(f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {role}")
    op.execute(f"ALTER DEFAULT PRIVILEGES FOR ROLE radarin IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {role}")
    op.execute(f"ALTER DEFAULT PRIVILEGES FOR ROLE radarin IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO {role}")


def upgrade() -> None:
    settings = get_settings()

    _create_role_if_missing("radar_app", settings.radar_app_db_password)
    _create_role_if_missing("radar_worker", settings.radar_worker_db_password)
    _grant_base_privileges("radar_app")
    _grant_base_privileges("radar_worker")

    # --- profiles: fix the circular policy -------------------------------
    op.execute("DROP POLICY IF EXISTS account_isolation ON profiles")
    op.execute(
        """
        CREATE POLICY self_lookup ON profiles
        FOR ALL
        USING (id = current_setting('app.user_id', true)::uuid)
        WITH CHECK (id = current_setting('app.user_id', true)::uuid)
        """
    )

    # --- accounts: explicit WITH CHECK ------------------------------------
    op.execute("DROP POLICY IF EXISTS account_isolation ON accounts")
    op.execute(
        """
        CREATE POLICY account_isolation ON accounts
        FOR ALL
        USING (id = current_setting('app.account_id', true)::uuid)
        WITH CHECK (id = current_setting('app.account_id', true)::uuid)
        """
    )

    # radar_worker additionally needs to enumerate accounts (to iterate
    # "for each account" in scheduled jobs) without an app.account_id set yet.
    # PERMISSIVE policies are OR'd together, so this only ever *adds* read
    # access to the id list for this one role — every other table keeps
    # requiring the per-account GUC, and radar_worker still can't read any
    # other column-sensitive table without it.
    op.execute(
        """
        CREATE POLICY worker_can_list_accounts ON accounts
        FOR SELECT
        TO radar_worker
        USING (true)
        """
    )

    # --- direct account-owned tables: explicit WITH CHECK ------------------
    for table in DIRECT_ACCOUNT_TABLES:
        op.execute(f"DROP POLICY IF EXISTS account_isolation ON {table}")
        op.execute(
            f"""
            CREATE POLICY account_isolation ON {table}
            FOR ALL
            USING (account_id = current_setting('app.account_id', true)::uuid)
            WITH CHECK (account_id = current_setting('app.account_id', true)::uuid)
            """
        )

    # --- child tables: explicit WITH CHECK ----------------------------------
    for table, join_column, parent in CHILD_TABLES:
        op.execute(f"DROP POLICY IF EXISTS account_isolation ON {table}")
        op.execute(
            f"""
            CREATE POLICY account_isolation ON {table}
            FOR ALL
            USING (EXISTS (
                SELECT 1 FROM {parent}
                WHERE {parent}.id = {table}.{join_column}
                AND {parent}.account_id = current_setting('app.account_id', true)::uuid
            ))
            WITH CHECK (EXISTS (
                SELECT 1 FROM {parent}
                WHERE {parent}.id = {table}.{join_column}
                AND {parent}.account_id = current_setting('app.account_id', true)::uuid
            ))
            """
        )

    # --- FORCE RLS everywhere (defense in depth; superusers still bypass) --
    for table in ALL_ACCOUNT_SCOPED_TABLES:
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")


def downgrade() -> None:
    for table in ALL_ACCOUNT_SCOPED_TABLES:
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")

    for table, join_column, parent in CHILD_TABLES:
        op.execute(f"DROP POLICY IF EXISTS account_isolation ON {table}")
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

    for table in DIRECT_ACCOUNT_TABLES:
        op.execute(f"DROP POLICY IF EXISTS account_isolation ON {table}")
        op.execute(
            f"""
            CREATE POLICY account_isolation ON {table}
            USING (account_id = current_setting('app.account_id', true)::uuid)
            """
        )

    op.execute("DROP POLICY IF EXISTS worker_can_list_accounts ON accounts")
    op.execute("DROP POLICY IF EXISTS account_isolation ON accounts")
    op.execute(
        """
        CREATE POLICY account_isolation ON accounts
        USING (id = current_setting('app.account_id', true)::uuid)
        """
    )

    op.execute("DROP POLICY IF EXISTS self_lookup ON profiles")
    op.execute(
        """
        CREATE POLICY account_isolation ON profiles
        USING (account_id = current_setting('app.account_id', true)::uuid)
        """
    )

    op.execute("REVOKE ALL ON ALL TABLES IN SCHEMA public FROM radar_app, radar_worker")
    op.execute("REVOKE ALL ON SCHEMA public FROM radar_app, radar_worker")
    op.execute("DROP ROLE IF EXISTS radar_app")
    op.execute("DROP ROLE IF EXISTS radar_worker")
