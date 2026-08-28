"""profiles.email is no longer unique

Revision ID: 0004_email_not_unique
Revises: 0003_app_role_rls
Create Date: 2026-07-27

Found by tests/test_auth_jwt.py::test_provisioning_never_merges_accounts_by_email:
a unique index on profiles.email made email a de facto identity key, which
contradicts the spec's "no utilizar el email como identificador permanente"
— and threw a raw IntegrityError (500) rather than provisioning a distinct
profile whenever a dev-login and a real-JWT login (or, in principle, two
different Supabase auth subjects) happened to share an email address.
Identity is profiles.id (the Supabase-issued UUID) only. Kept indexed
(non-unique) for lookup performance.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0004_email_not_unique"
down_revision: Union[str, None] = "0003_app_role_rls"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index("ix_profiles_email", table_name="profiles")
    op.create_index("ix_profiles_email", "profiles", ["email"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_profiles_email", table_name="profiles")
    op.create_index("ix_profiles_email", "profiles", ["email"], unique=True)
