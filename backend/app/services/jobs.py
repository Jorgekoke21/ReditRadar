"""The eight scheduled/background jobs from spec section 18.

Each public `run_*` function is idempotent and wrapped by `_with_job_lock`,
which writes a ScheduledJobRun row and refuses to start a job that already
has a `running` row younger than STALE_LOCK_MINUTES â€” the DB-backed lock
that keeps two workers from double-processing the same job.
"""

from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db import remember_rls_context
from app.models.account import Account
from app.models.alerts import AlertDelivery, AlertSettings
from app.models.community import Community, WatchProfile, WatchProfileCommunity
from app.models.conversation import (
    Conversation,
    ConversationAction,
    ConversationAnalysis,
    ConversationOutcome,
    ConversationScore,
    ReplyDraft,
)
from app.models.enums import ConversationState, DraftVariant, OutcomeResult, Priority, RecommendedAction, SourceMode
from app.models.jobs import ScheduledJobRun
from app.models.reddit import RedditConnection
from app.models.topic import Topic
from app.services import drafts as drafts_service, reddit_client
from app.services.analyzer import ConversationForAnalysis, TopicForMatching, get_analyzer
from app.services.email_provider import get_email_provider
from app.services.email_templates import DigestItem, build_daily_digest, build_urgent_alert, build_weekly_digest
from app.services.initial_filter import DEFAULT_MAX_AGE_HOURS, run_initial_filter
from app.services.scoring import ScoreInput, compute_score
from app.services.crypto import decrypt_token, encrypt_token
from app.services.dedupe import compute_dedupe_hash, normalize_url
from app.services.text_utils import normalize, normalize_subreddit, subreddits_match

logger = logging.getLogger("radarin.jobs")

STALE_LOCK_MINUTES = 30

JOB_FREQUENCIES = {
    "fetch_reddit_conversations": "every 15 minutes",
    "analyze_pending_conversations": "every 5 minutes",
    "recalculate_scores": "every 6 hours",
    "send_urgent_alerts": "every 30 minutes",
    "send_daily_digest": "daily at 09:00",
    "send_weekly_digest": "mondays at 09:00",
    "purge_expired_reddit_content": "every hour",
    "sync_deleted_reddit_content": "every 6 hours",
}


def _as_aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


async def _set_account_context(session: AsyncSession, account_id) -> None:
    """Scopes every subsequent query on this session to one account, via the
    same RLS-backed context app/core/security.py sets per request (see
    app/db.py::remember_rls_context for why a plain set_config isn't
    enough). Every job below that loops "for each account" calls this
    before touching that account's rows â€” required now that the worker
    connects as radar_worker (RLS-bound), not as the table owner. Safe to
    call repeatedly across a loop of accounts on the same session: each
    call simply overwrites the previous value."""
    await remember_rls_context(session, account_id=str(account_id))


async def _with_job_lock(session: AsyncSession, job_name: str, fn):
    stale_before = datetime.now(timezone.utc) - timedelta(minutes=STALE_LOCK_MINUTES)
    running = (
        await session.execute(
            select(ScheduledJobRun).where(
                ScheduledJobRun.job_name == job_name,
                ScheduledJobRun.status == "running",
                ScheduledJobRun.started_at > stale_before,
            )
        )
    ).scalars().first()
    if running:
        logger.info("job_skip job=%s reason=already_running started_at=%s", job_name, running.started_at)
        return {"skipped": True, "reason": "already_running"}

    run = ScheduledJobRun(job_name=job_name, status="running", metrics={})
    session.add(run)
    await session.commit()
    await session.refresh(run)
    started = time.monotonic()
    result_metrics: dict = {}
    try:
        result = await fn()
        if len(result) == 3:
            processed, errors, result_metrics = result
        else:
            processed, errors = result
        run.status = "success" if errors == 0 else "failed"
        run.processed_count = processed
        run.error_count = errors
        run.metrics = result_metrics
    except Exception as exc:
        logger.exception("job_failed job=%s", job_name)
        run.status = "failed"
        run.error_count = 1
        run.error_message = str(exc)[:2000]
        run.metrics = result_metrics
    finally:
        run.finished_at = datetime.now(timezone.utc)
        run.duration_ms = int((time.monotonic() - started) * 1000)
        await session.commit()

    logger.info(
        "job_finished job=%s status=%s processed=%s errors=%s duration_ms=%s metrics=%s",
        job_name, run.status, run.processed_count, run.error_count, run.duration_ms, run.metrics,
    )
    return {
        "skipped": False,
        "status": run.status,
        "processed": run.processed_count,
        "errors": run.error_count,
        "error_message": run.error_message,
        "duration_ms": run.duration_ms,
        "metrics": run.metrics or {},
    }


# ---------------------------------------------------------------------------
# 1. fetch_reddit_conversations
# ---------------------------------------------------------------------------
TOKEN_REFRESH_MARGIN_SECONDS = 300


async def _ensure_fresh_access_token(session: AsyncSession, settings: Settings, connection, adapter) -> str:
    """Return a usable access token for `connection`, refreshing it if needed.

    Reddit access tokens expire in an hour, so a long-running worker that only
    ever decrypts the stored token would ingest for one hour and then fail
    every tick forever. Refreshing when the token is expired or within
    TOKEN_REFRESH_MARGIN_SECONDS of expiry keeps ingestion sustained without
    a refresh on every single tick.

    A connection with no recorded expiry is treated as still valid: rows
    created before this column was populated should not be forced through a
    refresh they may not need.

    Raises RedditTokenRefreshError when the token cannot be renewed. Callers
    record that against the account and move on — the worker stays alive and
    the next scheduled run tries again.
    """
    access_token = decrypt_token(settings, connection.access_token_encrypted)
    expires_at = _as_aware(connection.token_expires_at)
    if expires_at is not None:
        margin = timedelta(seconds=TOKEN_REFRESH_MARGIN_SECONDS)
        needs_refresh = expires_at - margin <= datetime.now(timezone.utc)
    else:
        needs_refresh = not access_token

    if not needs_refresh:
        return access_token

    refresh_token = decrypt_token(settings, connection.refresh_token_encrypted) if connection.refresh_token_encrypted else ""
    logger.info(
        "reddit_token_refresh_start account_id=%s expires_at=%s", connection.account_id, expires_at
    )
    # Test adapters may only implement the listing surface; fall back to the
    # real client, which is itself gated by REDDIT_API_ENABLED.
    refresh = getattr(adapter, "refresh_access_token", reddit_client.refresh_access_token)
    payload = await refresh(settings, refresh_token)

    new_access = payload.get("access_token") or ""
    if not new_access:
        raise reddit_client.RedditTokenRefreshError("Reddit token refresh returned no access_token")

    connection.access_token_encrypted = encrypt_token(settings, new_access)
    # Reddit omits refresh_token on most refreshes; overwriting with "" there
    # would strand the connection with no way back.
    rotated = payload.get("refresh_token")
    if rotated:
        connection.refresh_token_encrypted = encrypt_token(settings, rotated)
    expires_in = payload.get("expires_in")
    try:
        lifetime = int(expires_in) if expires_in is not None else 3600
    except (TypeError, ValueError):
        lifetime = 3600
    connection.token_expires_at = datetime.now(timezone.utc) + timedelta(seconds=lifetime)
    if payload.get("scope"):
        connection.scopes = payload["scope"]
    await session.commit()
    await _set_account_context(session, connection.account_id)
    logger.info(
        "reddit_token_refreshed account_id=%s expires_at=%s rotated_refresh_token=%s",
        connection.account_id, connection.token_expires_at, bool(rotated),
    )
    return new_access


async def _watch_age_by_community(session: AsyncSession, account_id, default: int) -> dict:
    rows = (
        await session.execute(
            select(WatchProfileCommunity.community_id, WatchProfile.max_age_hours)
            .join(WatchProfile, WatchProfile.id == WatchProfileCommunity.watch_profile_id)
            .where(
                WatchProfile.account_id == account_id,
                WatchProfile.is_active.is_(True),
            )
        )
    ).all()
    ages: dict = {}
    for community_id, age in rows:
        ages[community_id] = min(ages.get(community_id, default), age or default)
    return ages


async def _fetch_listing(adapter, settings, access_token: str, subreddit: str, *, after: str | None):
    if hasattr(adapter, "fetch_new_posts_page"):
        return await adapter.fetch_new_posts_page(
            settings, access_token, subreddit, limit=settings.reddit_fetch_limit, after=after
        )
    posts = await adapter.fetch_new_posts(settings, access_token, subreddit, limit=settings.reddit_fetch_limit)
    return reddit_client.RedditListingPage(posts=posts, after=None, rate_limit=reddit_client.RateLimitInfo())


async def run_fetch_reddit_conversations(
    session: AsyncSession,
    settings: Settings,
    adapter=None,
) -> dict:
    adapter = adapter or reddit_client

    async def _do():
        if not settings.reddit_api_enabled:
            logger.info("job_disabled job=fetch_reddit_conversations integration=reddit")
            return 0, 0, {"integration": "reddit", "enabled": False, "external_calls": 0}

        if not settings.reddit_client_id or not settings.reddit_client_secret:
            raise RuntimeError(
                "Reddit is enabled but REDDIT_CLIENT_ID/REDDIT_CLIENT_SECRET are missing; "
                "configure OAuth credentials before starting ingestion."
            )
        if not settings.reddit_encryption_key_is_safe:
            raise RuntimeError(
                "Reddit is enabled but REDDIT_TOKEN_ENCRYPTION_KEY is empty or uses the known development fallback."
            )

        accounts = (await session.execute(select(Account))).scalars().all()
        account_ids = [account.id for account in accounts]
        metrics = {
            "integration": "reddit",
            "enabled": True,
            "external_calls": 0,
            "communities_reviewed": 0,
            "posts_retrieved": 0,
            "new_conversations": 0,
            "duplicates": 0,
            "discarded_before_analysis": 0,
            "analyzed": 0,
            "saved": 0,
            "recommended": 0,
            "errors_by_community": 0,
            "token_refresh_failures": 0,
            "rate_remaining": None,
            "rate_used": None,
            "rate_reset_seconds": None,
        }
        errors = 0
        for account_id in account_ids:
            await _set_account_context(session, account_id)
            connection = (
                await session.execute(
                    select(RedditConnection).where(
                        RedditConnection.account_id == account_id,
                        RedditConnection.is_active.is_(True),
                    )
                )
            ).scalars().first()
            communities = (
                await session.execute(
                    select(Community).where(
                        Community.account_id == account_id,
                        Community.is_active.is_(True),
                    ).order_by(Community.name)
                )
            ).scalars().all()
            if not connection:
                errors += 1
                logger.error("reddit_account_error account_id=%s reason=oauth_connection_missing", account_id)
                continue
            try:
                access_token = await _ensure_fresh_access_token(session, settings, connection, adapter)
            except Exception as exc:
                errors += 1
                metrics["token_refresh_failures"] += 1
                await session.rollback()
                await _set_account_context(session, account_id)
                # type/message only — never the token itself.
                logger.error(
                    "reddit_account_error account_id=%s reason=oauth_token_unusable type=%s detail=%s",
                    account_id, type(exc).__name__, str(exc)[:200],
                )
                continue
            ages = await _watch_age_by_community(session, account_id, settings.reddit_default_max_age_hours)
            # The listing path is /r/{name}/new, so the stored name has to be
            # canonical before it is used as a URL segment: a row still holding
            # "r/agency" would request /r/r/agency/new and 404 every cycle.
            community_specs = [
                (c.id, normalize_subreddit(c.name), c.primary_language) for c in communities
            ]
            for community_id, subreddit_name, community_language in community_specs:
                community = (
                    await session.execute(select(Community).where(Community.id == community_id))
                ).scalars().one()
                metrics["communities_reviewed"] += 1
                fetched_at = datetime.now(timezone.utc)
                community.reddit_last_fetch_at = fetched_at
                community.reddit_last_error = ""
                try:
                    watermark = _as_aware(community.reddit_watermark_at)
                    after = None
                    newest = None
                    page_count = 0
                    while page_count < settings.reddit_max_pages_per_community:
                        page = await _fetch_listing(
                            adapter, settings, access_token, subreddit_name, after=after
                        )
                        metrics["external_calls"] += 1
                        page_count += 1
                        metrics["posts_retrieved"] += len(page.posts)
                        community.reddit_rate_remaining = page.rate_limit.remaining
                        community.reddit_rate_used = page.rate_limit.used
                        community.reddit_rate_reset_seconds = page.rate_limit.reset_seconds
                        metrics["rate_remaining"] = page.rate_limit.remaining
                        metrics["rate_used"] = page.rate_limit.used
                        metrics["rate_reset_seconds"] = page.rate_limit.reset_seconds
                        for post in page.posts:
                            published_at = datetime.fromtimestamp(post.created_utc, tz=timezone.utc) if post.created_utc else None
                            if newest is None or (published_at and published_at > newest[0]):
                                newest = (published_at, post.id)
                            if watermark and published_at and published_at <= watermark:
                                metrics["duplicates"] += 1
                                continue
                            if not post.id or not published_at:
                                continue
                            from app.api.conversations import _create_and_analyze, _dedupe_lookup
                            url_norm = normalize_url(post.url)
                            dedupe_hash = compute_dedupe_hash(post.subreddit or community.name, post.title, published_at, post.id)
                            existing = await _dedupe_lookup(
                                session, account_id, post.id, url_norm, dedupe_hash
                            )
                            if existing:
                                metrics["duplicates"] += 1
                                continue
                            convo = await _create_and_analyze(
                                session,
                                settings,
                                account_id=account_id,
                                source_mode=SourceMode.reddit_api,
                                url=post.url,
                                subreddit=post.subreddit or community.name,
                                title=post.title,
                                body=post.selftext,
                                published_at=published_at,
                                num_comments=post.num_comments,
                                language=community_language or "en",
                                reddit_post_id=post.id,
                                community_id=community.id,
                                raw_author=post.author,
                                is_removed_upstream=post.removed,
                                max_age_hours=ages.get(community_id, settings.reddit_default_max_age_hours),
                            )
                            metrics["new_conversations"] += 1
                            metrics["analyzed"] += 1
                            metrics["saved"] += 1
                            if convo.state == ConversationState.discarded:
                                metrics["discarded_before_analysis"] += 1
                            else:
                                metrics["recommended"] += 1
                        if not page.after or len(page.posts) < settings.reddit_fetch_limit:
                            break
                        after = page.after
                    if newest and newest[0] and (watermark is None or newest[0] > watermark):
                        community.reddit_watermark_at = newest[0]
                        community.reddit_watermark_id = newest[1]
                    community.reddit_last_success_at = fetched_at
                    await session.commit()
                    await _set_account_context(session, account_id)
                except Exception as exc:
                    errors += 1
                    metrics["errors_by_community"] += 1
                    await session.rollback()
                    await _set_account_context(session, account_id)
                    fresh = (
                        await session.execute(select(Community).where(Community.id == community_id))
                    ).scalars().first()
                    if fresh:
                        fresh.reddit_last_fetch_at = fetched_at
                        fresh.reddit_last_error = f"{type(exc).__name__}: {str(exc)[:500]}"
                        await session.commit()
                        await _set_account_context(session, account_id)
                    logger.exception("reddit_community_failed account_id=%s subreddit=%s", account_id, subreddit_name)
        return metrics["posts_retrieved"], errors, metrics

    return await _with_job_lock(session, "fetch_reddit_conversations", _do)


# ---------------------------------------------------------------------------
# 2. analyze_pending_conversations
# ---------------------------------------------------------------------------
async def run_analyze_pending_conversations(session: AsyncSession, settings: Settings) -> dict:
    async def _do():
        # RLS means a plain cross-account query here would silently return
        # nothing once app.account_id isn't set to a specific value â€” so we
        # enumerate accounts first (radar_worker's one extra grant) and set
        # the context before each account's slice of the work.
        accounts = (await session.execute(select(Account))).scalars().all()

        processed, errors = 0, 0
        for account in accounts:
            account_id = account.id
            await _set_account_context(session, account_id)
            pending = (
                await session.execute(
                    select(Conversation).where(
                        Conversation.account_id == account.id, Conversation.is_analyzed.is_(False)
                    )
                )
            ).scalars().all()
            for convo in pending:
                try:
                    await _analyze_one(session, convo, settings)
                    processed += 1
                except Exception:
                    logger.exception("failed to analyze conversation %s", convo.id)
                    errors += 1
        await session.commit()
        return processed, errors

    return await _with_job_lock(session, "analyze_pending_conversations", _do)


async def _analyze_one(session: AsyncSession, convo: Conversation, settings: Settings, max_age_hours: int | None = None) -> None:
    topics = (await session.execute(select(Topic).where(Topic.account_id == convo.account_id, Topic.is_active.is_(True)))).scalars().all()
    communities = (
        await session.execute(select(Community).where(Community.account_id == convo.account_id))
    ).scalars().all()
    # subreddits_match tolerates "r/SaaS" vs "SaaS" on either side, so a
    # community saved in display form still matches what Reddit returns.
    community = next((c for c in communities if subreddits_match(c.name, convo.subreddit)), None)

    topic_matchers = []
    for t in topics:
        kw_result = await session.execute(select(Topic).where(Topic.id == t.id))
        topic_obj = kw_result.scalar_one()
        await session.refresh(topic_obj, attribute_names=["keywords", "exclusions"])
        topic_matchers.append(
            TopicForMatching(
                id=str(t.id),
                name=t.name,
                description=t.description,
                keywords=[k.phrase for k in topic_obj.keywords],
                exclusions=[e.phrase for e in topic_obj.exclusions],
            )
        )

    title = convo.raw_title or ""
    body = convo.raw_body or ""
    normalized_text = normalize(f"{title}\n{body}")
    has_topic_match = any(any(normalize(kw) in normalized_text for kw in tm.keywords) for tm in topic_matchers)

    # The watch-list check only makes sense for automated Reddit API fetching
    # (only pull from subreddits the user chose to watch). Manual/CSV/Demo
    # entries are explicit user input â€” spec 4B requires Manual mode to work
    # with zero pre-configuration, so an unregistered subreddit doesn't block
    # analysis there; it only blocks if the user registered the community AND
    # explicitly deactivated it.
    if convo.source_mode == SourceMode.reddit_api:
        is_watched_community = community.is_active if community else False
    else:
        is_watched_community = community.is_active if community else True

    filter_result = run_initial_filter(
        title=title,
        body=body,
        subreddit=convo.subreddit,
        published_at=convo.published_at,
        is_watched_community=is_watched_community,
        has_topic_match=has_topic_match,
        already_analyzed=convo.is_analyzed,
        is_removed_upstream=convo.is_removed_upstream,
        max_age_hours=(
            max_age_hours
            if max_age_hours is not None
            else (
                settings.reddit_default_max_age_hours
                if convo.source_mode == SourceMode.reddit_api
                else DEFAULT_MAX_AGE_HOURS
            )
        ),
    )

    convo.is_analyzed = True
    if not filter_result.passed:
        convo.state = ConversationState.discarded
        convo.score_total = 0
        convo.recommended_action = None
        session.add(
            ConversationAction(
                conversation_id=convo.id,
                account_id=convo.account_id,
                action_type="analyzed",
                payload={"filtered_out": True, "reasons": filter_result.reasons},
            )
        )
        return

    analyzer = get_analyzer(settings)
    result = await analyzer.analyze(
        ConversationForAnalysis(
            subreddit=convo.subreddit,
            title=title,
            body=body,
            language=convo.language,
            num_comments=convo.num_comments,
            self_promo_policy=community.allows_self_promo if community else None,
        ),
        topic_matchers,
    )

    analysis = ConversationAnalysis(
        conversation_id=convo.id,
        analyzer=result.analyzer_name,
        audience_type=result.audience_type,
        problem_detected=result.problem_detected,
        intent=result.intent,
        topic_ids=result.topic_ids,
        can_add_value=result.can_add_value,
        value_angle=result.value_angle,
        tool_request=result.tool_request,
        radarin_fit=result.radarin_fit,
        promotion_risk=result.promotion_risk,
        recommended_action=result.recommended_action,
        mention_radarin=result.mention_radarin,
        reasoning_summary=result.reasoning_summary,
        confidence=result.confidence,
    )
    session.add(analysis)

    convo.problem_detected = result.problem_detected
    convo.summary = result.value_angle or result.problem_detected
    convo.promotion_risk = result.promotion_risk
    if result.topic_ids:
        convo.topic_id = uuid.UUID(result.topic_ids[0])
    if community:
        convo.community_id = community.id

    breakdown = compute_score(
        ScoreInput(
            audience_fit=bool(result.topic_ids) and result.radarin_fit in ("high", "medium"),
            problem_fit=bool(result.topic_ids),
            requests_advice_or_tool=result.tool_request or result.intent == "seeking_advice",
            can_offer_concrete_value=result.can_add_value,
            published_at=convo.published_at,
            num_comments=convo.num_comments,
            community_priority=community.priority if community else Priority.medium,
            promotion_risk=result.promotion_risk,
        )
    )
    session.add(
        ConversationScore(
            conversation_id=convo.id,
            total=breakdown.total,
            audience_fit=breakdown.audience_fit,
            problem_fit=breakdown.problem_fit,
            request_intent=breakdown.request_intent,
            value_potential=breakdown.value_potential,
            recency=breakdown.recency,
            low_competition=breakdown.low_competition,
            community_priority=breakdown.community_priority,
            promotion_risk_penalty=breakdown.promotion_risk_penalty,
            classification=breakdown.classification,
        )
    )
    convo.score_total = breakdown.total
    convo.recommended_action = RecommendedAction(breakdown.classification)
    convo.state = ConversationState.discarded if breakdown.classification == "discard" else ConversationState.recommended

    if community:
        community.opportunities_found = (community.opportunities_found or 0) + 1

    if breakdown.classification not in ("discard", "observe"):
        variant_bodies = drafts_service.generate_drafts(
            language=convo.language, tool_request=result.tool_request, promotion_risk=result.promotion_risk.value,
            topic_name=topic_matchers[0].name if topic_matchers else "",
        )
        recommended = drafts_service.recommended_variant(
            tool_request=result.tool_request, promotion_risk=result.promotion_risk.value
        )
        for variant, body_text in variant_bodies.items():
            session.add(
                ReplyDraft(
                    conversation_id=convo.id,
                    variant=variant,
                    language=convo.language,
                    body=body_text,
                    is_recommended=(variant == recommended),
                )
            )

    session.add(
        ConversationAction(
            conversation_id=convo.id,
            account_id=convo.account_id,
            action_type="analyzed",
            payload={"score": breakdown.total, "classification": breakdown.classification},
        )
    )


# ---------------------------------------------------------------------------
# 3. recalculate_scores
# ---------------------------------------------------------------------------
async def run_recalculate_scores(session: AsyncSession, settings: Settings) -> dict:
    async def _do():
        accounts = (await session.execute(select(Account))).scalars().all()
        processed = 0
        for account in accounts:
            account_id = account.id
            await _set_account_context(session, account_id)
            convos = (
                await session.execute(
                    select(Conversation).where(
                        Conversation.account_id == account.id,
                        Conversation.is_analyzed.is_(True),
                        Conversation.state.notin_([ConversationState.discarded, ConversationState.expired]),
                    )
                )
            ).scalars().all()
            for convo in convos:
                analysis = (
                    await session.execute(select(ConversationAnalysis).where(ConversationAnalysis.conversation_id == convo.id))
                ).scalars().first()
                if not analysis:
                    continue
                community = (
                    await session.execute(select(Community).where(Community.id == convo.community_id))
                ).scalars().first() if convo.community_id else None
                breakdown = compute_score(
                    ScoreInput(
                        audience_fit=bool(analysis.topic_ids) and analysis.radarin_fit in ("high", "medium"),
                        problem_fit=bool(analysis.topic_ids),
                        requests_advice_or_tool=analysis.tool_request or analysis.intent == "seeking_advice",
                        can_offer_concrete_value=analysis.can_add_value,
                        published_at=convo.published_at,
                        num_comments=convo.num_comments,
                        community_priority=community.priority if community else Priority.medium,
                        promotion_risk=analysis.promotion_risk,
                    )
                )
                session.add(
                    ConversationScore(
                        conversation_id=convo.id,
                        total=breakdown.total,
                        audience_fit=breakdown.audience_fit,
                        problem_fit=breakdown.problem_fit,
                        request_intent=breakdown.request_intent,
                        value_potential=breakdown.value_potential,
                        recency=breakdown.recency,
                        low_competition=breakdown.low_competition,
                        community_priority=breakdown.community_priority,
                        promotion_risk_penalty=breakdown.promotion_risk_penalty,
                        classification=breakdown.classification,
                    )
                )
                convo.score_total = breakdown.total
                convo.recommended_action = RecommendedAction(breakdown.classification)
                processed += 1
        await session.commit()
        return processed, 0

    return await _with_job_lock(session, "recalculate_scores", _do)


# ---------------------------------------------------------------------------
# 4 & 5. alerts
# ---------------------------------------------------------------------------
async def run_send_urgent_alerts(session: AsyncSession, settings: Settings) -> dict:
    async def _do():
        accounts = (await session.execute(select(Account))).scalars().all()
        processed = 0
        for account in accounts:
            account_id = account.id
            await _set_account_context(session, account_id)
            alert_settings = (
                await session.execute(select(AlertSettings).where(AlertSettings.account_id == account.id))
            ).scalars().first()
            if not alert_settings or not alert_settings.urgent_alerts_enabled or not alert_settings.email_recipient:
                continue

            today_start = datetime.combine(datetime.now(timezone.utc).date(), datetime.min.time())
            already_sent_today = (
                await session.execute(
                    select(AlertDelivery).where(
                        AlertDelivery.account_id == account.id,
                        AlertDelivery.kind == "urgent",
                        AlertDelivery.created_at >= today_start,
                    )
                )
            ).scalars().all()
            if len(already_sent_today) >= alert_settings.max_urgent_per_day:
                continue
            already_alerted_ids = {d.conversation_id for d in already_sent_today}

            candidates = (
                await session.execute(
                    select(Conversation).where(
                        Conversation.account_id == account.id,
                        Conversation.score_total >= alert_settings.urgent_score_threshold,
                        Conversation.state.notin_([ConversationState.discarded, ConversationState.expired, ConversationState.responded]),
                    )
                )
            ).scalars().all()

            provider = get_email_provider(settings)
            for convo in candidates:
                if convo.id in already_alerted_ids:
                    continue
                if len(already_sent_today) >= alert_settings.max_urgent_per_day:
                    break
                item = DigestItem(
                    id=str(convo.id), subreddit=convo.subreddit, title=convo.display_title,
                    score=convo.score_total or 0, summary=convo.summary,
                    recommended_action=(convo.recommended_action.value if convo.recommended_action else ""),
                    promotion_risk=(convo.promotion_risk.value if convo.promotion_risk else ""),
                )
                subject, html = build_urgent_alert(item=item, app_url=settings.app_url)
                sent = await provider.send(to=alert_settings.email_recipient, subject=subject, html=html)
                session.add(
                    AlertDelivery(
                        account_id=account.id, kind="urgent", conversation_id=convo.id, subject=subject,
                        body_html=html, to_address=alert_settings.email_recipient, provider=settings.email_provider,
                        sent=sent,
                    )
                )
                already_sent_today.append(object())
                processed += 1
        await session.commit()
        return processed, 0

    return await _with_job_lock(session, "send_urgent_alerts", _do)


async def run_send_daily_digest(session: AsyncSession, settings: Settings) -> dict:
    async def _do():
        accounts = (await session.execute(select(Account))).scalars().all()
        processed = 0
        for account in accounts:
            account_id = account.id
            await _set_account_context(session, account_id)
            alert_settings = (
                await session.execute(select(AlertSettings).where(AlertSettings.account_id == account.id))
            ).scalars().first()
            if not alert_settings or not alert_settings.daily_digest_enabled or not alert_settings.email_recipient:
                continue

            convos = (
                await session.execute(
                    select(Conversation).where(
                        Conversation.account_id == account.id,
                        Conversation.score_total >= alert_settings.min_score_threshold,
                        Conversation.state.notin_([ConversationState.discarded, ConversationState.expired, ConversationState.responded]),
                    ).order_by(Conversation.score_total.desc())
                )
            ).scalars().all()
            if not convos:
                continue
            urgent_count = sum(1 for c in convos if (c.score_total or 0) >= alert_settings.urgent_score_threshold)
            items = [
                DigestItem(
                    id=str(c.id), subreddit=c.subreddit, title=c.display_title, score=c.score_total or 0,
                    summary=c.summary, recommended_action=(c.recommended_action.value if c.recommended_action else ""),
                    promotion_risk=(c.promotion_risk.value if c.promotion_risk else ""),
                )
                for c in convos
            ]
            subject, html = build_daily_digest(
                total_found=len(convos), urgent_count=urgent_count, items=items, app_url=settings.app_url
            )
            provider = get_email_provider(settings)
            sent = await provider.send(to=alert_settings.email_recipient, subject=subject, html=html)
            session.add(
                AlertDelivery(
                    account_id=account.id, kind="daily_digest", subject=subject, body_html=html,
                    to_address=alert_settings.email_recipient, provider=settings.email_provider, sent=sent,
                )
            )
            processed += 1
        await session.commit()
        return processed, 0

    return await _with_job_lock(session, "send_daily_digest", _do)


async def run_send_weekly_digest(session: AsyncSession, settings: Settings) -> dict:
    async def _do():
        accounts = (await session.execute(select(Account))).scalars().all()
        processed = 0
        week_ago = datetime.now(timezone.utc) - timedelta(days=7)
        for account in accounts:
            account_id = account.id
            await _set_account_context(session, account_id)
            alert_settings = (
                await session.execute(select(AlertSettings).where(AlertSettings.account_id == account.id))
            ).scalars().first()
            if not alert_settings or not alert_settings.weekly_digest_enabled or not alert_settings.email_recipient:
                continue

            analyzed = (
                await session.execute(
                    select(Conversation).where(Conversation.account_id == account.id, Conversation.detected_at >= week_ago)
                )
            ).scalars().all()
            recommended = [c for c in analyzed if c.state == ConversationState.recommended]
            responded = [c for c in analyzed if c.state == ConversationState.responded]
            outcomes = (
                await session.execute(
                    select(ConversationOutcome).where(
                        ConversationOutcome.conversation_id.in_([c.id for c in analyzed]) if analyzed else False
                    )
                )
            ).scalars().all() if analyzed else []
            started = sum(1 for o in outcomes if o.result == OutcomeResult.conversation_started)

            communities = {}
            for c in analyzed:
                communities[c.subreddit] = communities.get(c.subreddit, 0) + 1
            best_community = max(communities, key=communities.get) if communities else ""

            topics_seen = {}
            for c in analyzed:
                if c.topic_id:
                    topics_seen[str(c.topic_id)] = topics_seen.get(str(c.topic_id), 0) + 1
            top_topic_id = max(topics_seen, key=topics_seen.get) if topics_seen else None
            top_topic_name = ""
            if top_topic_id:
                topic = (
                    await session.execute(select(Topic).where(Topic.id == uuid.UUID(top_topic_id)))
                ).scalars().first()
                top_topic_name = topic.name if topic else ""

            subject, html = build_weekly_digest(
                analyzed=len(analyzed), recommended=len(recommended), responded=len(responded),
                conversations_started=started, best_community=best_community, top_topic=top_topic_name,
                app_url=settings.app_url,
            )
            provider = get_email_provider(settings)
            sent = await provider.send(to=alert_settings.email_recipient, subject=subject, html=html)
            session.add(
                AlertDelivery(
                    account_id=account.id, kind="weekly_digest", subject=subject, body_html=html,
                    to_address=alert_settings.email_recipient, provider=settings.email_provider, sent=sent,
                )
            )
            processed += 1
        await session.commit()
        return processed, 0

    return await _with_job_lock(session, "send_weekly_digest", _do)


# ---------------------------------------------------------------------------
# 6. purge_expired_reddit_content
# ---------------------------------------------------------------------------
async def run_purge_expired_reddit_content(session: AsyncSession, settings: Settings) -> dict:
    async def _do():
        now = datetime.now(timezone.utc)
        accounts = (await session.execute(select(Account))).scalars().all()
        total_expired = 0
        for account in accounts:
            account_id = account.id
            await _set_account_context(session, account_id)
            expired = (
                await session.execute(
                    select(Conversation).where(
                        Conversation.account_id == account.id,
                        Conversation.expires_at.is_not(None),
                        Conversation.expires_at <= now,
                        Conversation.raw_purged_at.is_(None),
                    )
                )
            ).scalars().all()
            for convo in expired:
                convo.raw_title = None
                convo.raw_body = None
                convo.raw_author = None
                convo.raw_purged_at = now
                session.add(
                    ConversationAction(
                        conversation_id=convo.id, account_id=convo.account_id, action_type="purged", payload={}
                    )
                )
            total_expired += len(expired)
        await session.commit()
        return total_expired, 0

    return await _with_job_lock(session, "purge_expired_reddit_content", _do)


# ---------------------------------------------------------------------------
# 7. sync_deleted_reddit_content
# ---------------------------------------------------------------------------
async def run_sync_deleted_reddit_content(
    session: AsyncSession,
    settings: Settings,
    adapter=None,
) -> dict:
    adapter = adapter or reddit_client

    async def _do():
        if not settings.reddit_api_enabled:
            logger.info("job_disabled job=sync_deleted_reddit_content integration=reddit")
            return 0, 0, {"integration": "reddit", "enabled": False, "external_calls": 0}

        if not settings.reddit_client_id or not settings.reddit_client_secret:
            raise RuntimeError(
                "Reddit is enabled but OAuth client credentials are missing; deletion sync is not activated."
            )
        if not settings.reddit_encryption_key_is_safe:
            raise RuntimeError(
                "Reddit is enabled but REDDIT_TOKEN_ENCRYPTION_KEY is empty or uses the known development fallback."
            )
        accounts = (await session.execute(select(Account))).scalars().all()
        account_ids = [account.id for account in accounts]
        checked = 0
        deleted = 0
        errors = 0
        external_calls = 0
        token_refresh_failures = 0
        now = datetime.now(timezone.utc)
        for account_id in account_ids:
            await _set_account_context(session, account_id)
            connection = (
                await session.execute(
                    select(RedditConnection).where(
                        RedditConnection.account_id == account_id,
                        RedditConnection.is_active.is_(True),
                    )
                )
            ).scalars().first()
            if not connection:
                errors += 1
                continue
            try:
                access_token = await _ensure_fresh_access_token(session, settings, connection, adapter)
            except Exception as exc:
                errors += 1
                token_refresh_failures += 1
                await session.rollback()
                await _set_account_context(session, account_id)
                logger.error(
                    "reddit_deleted_sync_token_unusable account_id=%s type=%s detail=%s",
                    account_id, type(exc).__name__, str(exc)[:200],
                )
                continue
            rows = (
                await session.execute(
                    select(Conversation).where(
                        Conversation.account_id == account_id,
                        Conversation.source_mode == SourceMode.reddit_api,
                        Conversation.reddit_post_id.is_not(None),
                        Conversation.raw_purged_at.is_(None),
                        Conversation.is_removed_upstream.is_(False),
                    )
                )
            ).scalars().all()
            for offset in range(0, len(rows), 50):
                chunk = rows[offset:offset + 50]
                ids = [c.reddit_post_id for c in chunk if c.reddit_post_id]
                try:
                    if hasattr(adapter, "fetch_posts_by_ids"):
                        found, _rate = await adapter.fetch_posts_by_ids(settings, access_token, ids)
                    else:
                        raise RuntimeError("Reddit adapter does not support /api/info deletion checks")
                    external_calls += 1
                    checked += len(ids)
                    for convo in chunk:
                        post = found.get(convo.reddit_post_id)
                        if post is None or not post.removed:
                            continue
                        convo.is_removed_upstream = True
                        convo.raw_title = None
                        convo.raw_body = None
                        convo.raw_author = None
                        convo.raw_purged_at = now
                        convo.state = ConversationState.discarded
                        convo.summary = "Contenido eliminado en Reddit"
                        session.add(
                            ConversationAction(
                                conversation_id=convo.id,
                                account_id=convo.account_id,
                                action_type="reddit_deleted",
                                payload={"detected_at": now.isoformat()},
                            )
                        )
                        deleted += 1
                    await session.commit()
                    await _set_account_context(session, account_id)
                except Exception as exc:
                    errors += 1
                    await session.rollback()
                    await _set_account_context(session, account_id)
                    logger.exception("reddit_deleted_sync_failed account_id=%s chunk_size=%s type=%s", account_id, len(ids), type(exc).__name__)
        return checked, errors, {
            "integration": "reddit",
            "enabled": True,
            "external_calls": external_calls,
            "checked": checked,
            "deleted": deleted,
            "token_refresh_failures": token_refresh_failures,
            "not_confirmed_missing_response": "true",
        }

    return await _with_job_lock(session, "sync_deleted_reddit_content", _do)


JOB_REGISTRY = {
    "fetch_reddit_conversations": run_fetch_reddit_conversations,
    "analyze_pending_conversations": run_analyze_pending_conversations,
    "recalculate_scores": run_recalculate_scores,
    "send_urgent_alerts": run_send_urgent_alerts,
    "send_daily_digest": run_send_daily_digest,
    "send_weekly_digest": run_send_weekly_digest,
    "purge_expired_reddit_content": run_purge_expired_reddit_content,
    "sync_deleted_reddit_content": run_sync_deleted_reddit_content,
}


