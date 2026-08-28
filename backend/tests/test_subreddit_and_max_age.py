"""Regressions for two silent-discard bugs in the ingestion path.

1. The watch profile's max_age_hours was computed per community and then
   dropped on the way into the analyzer, so every ingested post was judged
   against the global default instead.
2. A community saved as "r/SaaS" never matched the bare "SaaS" that Reddit's
   API returns, so every post from it was filtered out as
   `community_not_watched` before it could be scored.

Both failed silently - nothing errored, the posts just never appeared.
"""

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.models.community import Community, WatchProfile, WatchProfileCommunity
from app.models.conversation import Conversation
from app.models.enums import ConversationState
from app.services.text_utils import normalize_subreddit, subreddits_match

from tests.test_reddit_ingestion import _post, _settings, _setup_account
from tests.test_reddit_oauth import RefreshingAdapter


# --- normalization unit ---------------------------------------------------
def test_normalize_subreddit_strips_prefix_and_whitespace():
    assert normalize_subreddit("SaaS") == "SaaS"
    assert normalize_subreddit("r/SaaS") == "SaaS"
    assert normalize_subreddit("/r/SaaS") == "SaaS"
    assert normalize_subreddit("  r/SaaS  ") == "SaaS"
    assert normalize_subreddit("SaaS/") == "SaaS"
    assert normalize_subreddit("") == ""


def test_subreddits_match_is_case_insensitive_across_input_forms():
    for candidate in ("SaaS", "r/SaaS", "r/saas", "/r/SAAS", "  saas  "):
        assert subreddits_match(candidate, "SaaS"), candidate
    assert not subreddits_match("SaaS", "sales")


async def test_community_names_are_stored_canonically(client, auth_headers):
    """SaaS, r/SaaS and r/saas must all name the same community."""
    first = await client.post("/api/communities", json={"name": "r/SaaS"}, headers=auth_headers)
    assert first.status_code == 201, first.text
    assert first.json()["name"] == "SaaS"

    # The unique constraint is on (account_id, name), so a canonically equal
    # name must collide rather than create a second row.
    duplicate = await client.post("/api/communities", json={"name": "/r/SaaS"}, headers=auth_headers)
    assert duplicate.status_code >= 400

    listed = (await client.get("/api/communities", headers=auth_headers)).json()
    assert [c["name"] for c in listed] == ["SaaS"]


async def test_manual_import_of_prefixed_subreddit_matches_the_plain_community(client, auth_headers):
    """A post pasted as "r/agency" must land in the "agency" community."""
    await client.post(
        "/api/topics",
        json={
            "name": "Prioritize leads",
            "description": "lead prioritization",
            "keywords": ["prioritize leads"],
            "exclusions": [],
            "priority": "high",
        },
        headers=auth_headers,
    )
    await client.post("/api/communities", json={"name": "agency", "priority": "high"}, headers=auth_headers)

    resp = await client.post(
        "/api/conversations/manual",
        json={
            "url": "",
            "subreddit": "r/agency",
            "title": "How do I prioritize leads for my agency?",
            "body": "I need a practical way to prioritize leads based on real signals for a small agency.",
            "language": "en",
            "num_comments": 3,
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["subreddit"] == "agency"


async def test_reddit_fetch_matches_a_community_saved_with_the_r_prefix(client, auth_headers, db_session):
    """Reddit returns "agency"; the watch list holds "r/agency"."""
    account_id, settings = await _setup_account(client, db_session, auth_headers)

    community = (
        await db_session.execute(select(Community).where(Community.account_id == account_id))
    ).scalars().one()
    # Simulate a row stored before normalization existed.
    community.name = "r/agency"
    await db_session.commit()

    adapter = RefreshingAdapter(payload={"access_token": "x"}, pages={"agency": [_post()]})
    result = await run_fetch(db_session, settings, adapter)

    assert result["status"] == "success"
    assert result["metrics"]["new_conversations"] == 1
    convo = (await db_session.execute(select(Conversation))).scalars().one()
    # Not discarded => the community was recognised as watched.
    assert convo.state == ConversationState.recommended
    assert convo.subreddit == "agency"


async def run_fetch(db_session, settings, adapter):
    from app.services.jobs import run_fetch_reddit_conversations

    return await run_fetch_reddit_conversations(db_session, settings, adapter=adapter)


# --- max_age_hours --------------------------------------------------------
async def _set_watch_max_age(db_session, account_id, hours):
    community = (
        await db_session.execute(select(Community).where(Community.account_id == account_id))
    ).scalars().one()
    profile = WatchProfile(account_id=account_id, name="Vigilancia", is_active=True, max_age_hours=hours)
    db_session.add(profile)
    await db_session.flush()
    db_session.add(WatchProfileCommunity(watch_profile_id=profile.id, community_id=community.id))
    await db_session.commit()


async def test_watch_profile_max_age_is_honoured_and_discards_older_posts(client, auth_headers, db_session):
    """A 24h watch profile must reject a 30h-old post.

    The global default is 72h, so before the fix this post was accepted -
    proving the per-community window was being ignored.
    """
    account_id, settings = await _setup_account(client, db_session, auth_headers)
    await _set_watch_max_age(db_session, account_id, 24)

    adapter = RefreshingAdapter(payload={"access_token": "x"}, pages={"agency": [_post(post_id="old1", hours=30)]})
    result = await run_fetch(db_session, settings, adapter)

    assert result["status"] == "success"
    convo = (await db_session.execute(select(Conversation))).scalars().one()
    assert convo.state == ConversationState.discarded
    assert result["metrics"]["discarded_before_analysis"] == 1


async def test_watch_profile_max_age_still_accepts_posts_inside_the_window(client, auth_headers, db_session):
    account_id, settings = await _setup_account(client, db_session, auth_headers)
    await _set_watch_max_age(db_session, account_id, 24)

    adapter = RefreshingAdapter(payload={"access_token": "x"}, pages={"agency": [_post(post_id="new1", hours=2)]})
    result = await run_fetch(db_session, settings, adapter)

    assert result["status"] == "success"
    convo = (await db_session.execute(select(Conversation))).scalars().one()
    assert convo.state == ConversationState.recommended
    assert result["metrics"]["discarded_before_analysis"] == 0


async def test_manual_import_is_unaffected_by_the_reddit_window(client, auth_headers, db_session):
    """Manual entry keeps its own default - the fix must not leak the Reddit
    window into a path the user drove explicitly."""
    await client.post(
        "/api/topics",
        json={
            "name": "Prioritize leads",
            "description": "lead prioritization",
            "keywords": ["prioritize leads"],
            "exclusions": [],
            "priority": "high",
        },
        headers=auth_headers,
    )
    published = (datetime.now(timezone.utc) - timedelta(hours=30)).isoformat()
    resp = await client.post(
        "/api/conversations/manual",
        json={
            "url": "",
            "subreddit": "agency",
            "title": "How do I prioritize leads for my agency?",
            "body": "I need a practical way to prioritize leads based on real signals for a small agency.",
            "language": "en",
            "num_comments": 3,
            "published_at": published,
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    # 30h old is inside the 72h manual default, so it is still analyzed.
    assert resp.json()["state"] != "discarded"
