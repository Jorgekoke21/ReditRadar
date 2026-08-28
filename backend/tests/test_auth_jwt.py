"""JWT verification + provisioning tests, run against a LOCAL JWT test
provider (tests/jwt_helpers.py) that mints tokens matching the exact same
contract app/core/security.py::verify_supabase_jwt checks. This is real
signature/issuer/audience/expiry verification code being exercised — not a
mock of it — just without a real Supabase project's servers. See
docs/acceptance-audit.md for why this is classified as "tested with a local
JWT provider" rather than "tested against Supabase" (no such project exists
in this environment).
"""

import uuid

from tests.jwt_helpers import TEST_ISSUER, TEST_JWT_SECRET, make_supabase_jwt


async def test_valid_jwt_is_accepted_and_provisions_a_new_account(client):
    user_id = str(uuid.uuid4())
    token = make_supabase_jwt(sub=user_id, email="valid-jwt@example.com")
    resp = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["id"] == user_id
    assert body["email"] == "valid-jwt@example.com"


async def test_jwt_with_wrong_signature_is_rejected(client):
    token = make_supabase_jwt(secret="a-completely-different-secret-that-does-not-match")
    resp = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401


async def test_expired_jwt_is_rejected(client):
    token = make_supabase_jwt(expires_in=-3600)  # expired one hour ago
    resp = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401


async def test_jwt_with_wrong_issuer_is_rejected(client):
    token = make_supabase_jwt(issuer="https://a-completely-different-project.supabase.co/auth/v1")
    resp = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401


async def test_jwt_without_subject_is_rejected(client):
    token = make_supabase_jwt(include_sub=False)
    resp = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401


async def test_jwt_with_wrong_audience_is_rejected(client):
    token = make_supabase_jwt(audience="some-other-audience")
    resp = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401


async def test_malformed_token_is_rejected(client):
    resp = await client.get("/api/auth/me", headers={"Authorization": "Bearer not-a-real-jwt-at-all"})
    assert resp.status_code == 401


async def test_missing_token_is_rejected(client):
    resp = await client.get("/api/auth/me")
    assert resp.status_code == 401


async def test_valid_user_without_a_profile_gets_provisioned_on_first_login(client, db_session):
    """'Usuario válido sin perfil' from the audit's required test list —
    a brand new Supabase user_id that has never logged in before must be
    auto-provisioned (idempotently), not rejected."""
    from sqlalchemy import select

    from app.models.account import Account, Profile

    user_id = str(uuid.uuid4())
    token = make_supabase_jwt(sub=user_id, email="first-login@example.com")

    resp = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    account_id = resp.json()["account_id"]

    profile = (await db_session.execute(select(Profile).where(Profile.id == uuid.UUID(user_id)))).scalars().first()
    assert profile is not None
    assert str(profile.account_id) == account_id
    account = (await db_session.execute(select(Account).where(Account.id == uuid.UUID(account_id)))).scalars().first()
    assert account is not None


async def test_provisioning_is_idempotent_across_repeated_logins(client):
    """Same JWT subject logging in twice must resolve to the SAME account,
    never create a second one."""
    user_id = str(uuid.uuid4())
    token1 = make_supabase_jwt(sub=user_id, email="repeat-login@example.com")
    token2 = make_supabase_jwt(sub=user_id, email="repeat-login@example.com")

    resp1 = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token1}"})
    resp2 = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token2}"})

    assert resp1.json()["account_id"] == resp2.json()["account_id"]
    assert resp1.json()["id"] == resp2.json()["id"]


async def test_provisioning_never_merges_accounts_by_email(client):
    """A dev-login and a real-JWT login sharing the same email address must
    NOT be treated as the same user — identity is the Supabase UUID, never
    the email (spec: 'no utilizar el email como identificador permanente')."""
    shared_email = "same-email-different-identity@example.com"

    dev_resp = await client.post("/api/auth/dev-login", json={"email": shared_email})
    dev_account_id = dev_resp.json()["profile"]["account_id"]

    jwt_user_id = str(uuid.uuid4())
    token = make_supabase_jwt(sub=jwt_user_id, email=shared_email)
    jwt_resp = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert jwt_resp.json()["account_id"] != dev_account_id
    assert jwt_resp.json()["id"] == jwt_user_id


async def test_backend_ignores_client_supplied_account_id(client, db_session):
    """The client must never be able to pick which account a write lands in
    — account_id always comes from the validated token
    (get_current_account_id), never from the request body. Sends a manual
    conversation payload with a spoofed account_id targeting an account the
    caller does not own, and asserts it's silently ignored (the resulting
    row belongs to the caller's own account, not the injected one).
    ConversationListItemOut doesn't even expose account_id, so this is
    verified directly against the database row."""
    from sqlalchemy import select

    from app.models.conversation import Conversation

    user_id = str(uuid.uuid4())
    token = make_supabase_jwt(sub=user_id, email="spoof-attempt@example.com")
    me = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    own_account_id = me.json()["account_id"]

    spoofed_account_id = str(uuid.uuid4())
    resp = await client.post(
        "/api/conversations/manual",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "subreddit": "test",
            "title": "spoof attempt",
            "account_id": spoofed_account_id,
        },
    )
    assert resp.status_code == 201, resp.text
    convo_id = resp.json()["id"]

    convo = (await db_session.execute(select(Conversation).where(Conversation.id == uuid.UUID(convo_id)))).scalars().first()
    assert convo is not None
    assert str(convo.account_id) == own_account_id
    assert str(convo.account_id) != spoofed_account_id


def test_local_jwt_fixture_self_check():
    """Sanity check on the test fixture itself: the token really is signed
    with the secret/issuer the app is configured to expect."""
    from jose import jwt as jose_jwt

    token = make_supabase_jwt(sub=str(uuid.uuid4()))
    payload = jose_jwt.decode(token, TEST_JWT_SECRET, algorithms=["HS256"], audience="authenticated")
    assert payload["iss"] == TEST_ISSUER
