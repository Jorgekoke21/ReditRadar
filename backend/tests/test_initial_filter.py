from datetime import datetime, timedelta, timezone

from app.services.initial_filter import is_job_offer, is_spam, run_initial_filter


def test_job_offer_detected():
    assert is_job_offer("We are hiring a developer, send your CV") is True
    assert is_job_offer("How do I hire more clients for my agency") is False


def test_spam_and_crypto_detected():
    assert is_spam("Thinking about accepting bitcoin at my bakery") is True
    assert is_spam("Looking for CRM recommendations") is False


def test_filter_rejects_too_old_posts():
    result = run_initial_filter(
        title="Need help prioritizing leads",
        body="Any tool you recommend to prioritize leads for my agency?",
        subreddit="agency",
        published_at=datetime.now(timezone.utc) - timedelta(days=10),
        is_watched_community=True,
        has_topic_match=True,
        already_analyzed=False,
        is_removed_upstream=False,
        max_age_hours=72,
    )
    assert result.passed is False
    assert "too_old" in result.reasons


def test_filter_passes_fresh_relevant_post():
    result = run_initial_filter(
        title="Need help prioritizing leads",
        body="Any tool you recommend to prioritize leads for my agency, we have too many to contact?",
        subreddit="agency",
        published_at=datetime.now(timezone.utc),
        is_watched_community=True,
        has_topic_match=True,
        already_analyzed=False,
        is_removed_upstream=False,
    )
    assert result.passed is True
    assert result.reasons == []


def test_filter_rejects_when_no_topic_match():
    result = run_initial_filter(
        title="Random unrelated post",
        body="This has nothing to do with our topics but is long enough to pass the length check",
        subreddit="agency",
        published_at=datetime.now(timezone.utc),
        is_watched_community=True,
        has_topic_match=False,
        already_analyzed=False,
        is_removed_upstream=False,
    )
    assert result.passed is False
    assert "no_topic_match" in result.reasons
