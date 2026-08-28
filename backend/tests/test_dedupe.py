from datetime import datetime, timezone

from app.services.dedupe import compute_dedupe_hash, normalize_title, normalize_url


def test_normalize_url_strips_tracking_and_www_and_trailing_slash():
    a = normalize_url("https://www.reddit.com/r/agency/comments/abc123/some_title/")
    b = normalize_url("https://reddit.com/r/agency/comments/abc123/some_title")
    assert a == b


def test_normalize_title_lowercases_and_strips_punctuation():
    assert normalize_title("¿Cómo, consigo clientes?!") == normalize_title("como consigo clientes")


def test_dedupe_hash_stable_for_same_subreddit_title_date():
    d = datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)
    h1 = compute_dedupe_hash("agency", "Need help finding clients", d)
    h2 = compute_dedupe_hash("agency", "need help finding clients", d)
    assert h1 == h2


def test_dedupe_hash_differs_for_different_titles():
    d = datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)
    h1 = compute_dedupe_hash("agency", "Need help finding clients", d)
    h2 = compute_dedupe_hash("agency", "Need help with pricing", d)
    assert h1 != h2


async def test_manual_import_is_idempotent(client, auth_headers):
    payload = {
        "url": "https://reddit.com/r/agency/comments/xyz999/duplicate_test/",
        "subreddit": "agency",
        "title": "Necesito priorizar leads para mi agencia, alguna herramienta?",
        "body": "Tengo muchos leads y no se cual contactar primero",
        "num_comments": 2,
        "language": "es",
    }
    r1 = await client.post("/api/conversations/manual", json=payload, headers=auth_headers)
    r2 = await client.post("/api/conversations/manual", json=payload, headers=auth_headers)
    assert r1.status_code == 201
    assert r2.status_code == 201
    assert r1.json()["id"] == r2.json()["id"]

    listing = await client.get("/api/conversations", headers=auth_headers)
    assert len(listing.json()) == 1


async def test_manual_import_dedupes_via_title_hash_without_url(client, auth_headers):
    payload_no_url = {
        "subreddit": "agency",
        "title": "Same conversation title for hash dedupe test",
        "body": "some body text with tool request",
        "num_comments": 0,
        "language": "en",
    }
    r1 = await client.post("/api/conversations/manual", json=payload_no_url, headers=auth_headers)
    r2 = await client.post("/api/conversations/manual", json=payload_no_url, headers=auth_headers)
    assert r1.json()["id"] == r2.json()["id"]
