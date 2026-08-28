"""App-layer ownership isolation (every router filters by account_id, see
get_current_account_id). Postgres RLS (migration 0002) adds defense in depth
for direct DB/Supabase client access and is exercised manually against the
docker-compose Postgres — see docs/testing.md."""

import uuid


async def _login(client, email: str) -> dict:
    resp = await client.post("/api/auth/dev-login", json={"email": email})
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def test_account_cannot_read_another_accounts_conversation(client):
    headers_a = await _login(client, f"a-{uuid.uuid4()}@example.com")
    headers_b = await _login(client, f"b-{uuid.uuid4()}@example.com")

    create = await client.post(
        "/api/conversations/manual",
        json={"subreddit": "agency", "title": "Private to account A about crm leads", "body": "", "language": "en"},
        headers=headers_a,
    )
    convo_id = create.json()["id"]

    same_account = await client.get(f"/api/conversations/{convo_id}", headers=headers_a)
    other_account = await client.get(f"/api/conversations/{convo_id}", headers=headers_b)

    assert same_account.status_code == 200
    assert other_account.status_code == 404


async def test_account_conversation_lists_are_isolated(client):
    headers_a = await _login(client, f"a-{uuid.uuid4()}@example.com")
    headers_b = await _login(client, f"b-{uuid.uuid4()}@example.com")

    await client.post(
        "/api/conversations/manual",
        json={"subreddit": "agency", "title": "Account A only conversation", "body": "", "language": "en"},
        headers=headers_a,
    )

    list_a = (await client.get("/api/conversations", headers=headers_a)).json()
    list_b = (await client.get("/api/conversations", headers=headers_b)).json()
    assert len(list_a) == 1
    assert len(list_b) == 0


async def test_community_cannot_be_edited_by_another_account(client):
    headers_a = await _login(client, f"a-{uuid.uuid4()}@example.com")
    headers_b = await _login(client, f"b-{uuid.uuid4()}@example.com")

    created = await client.post("/api/communities", json={"name": "agency"}, headers=headers_a)
    community_id = created.json()["id"]

    patch = await client.patch(
        f"/api/communities/{community_id}", json={"name": "agency", "priority": "high"}, headers=headers_b
    )
    assert patch.status_code == 404
