import csv
import io
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import Settings, get_settings
from app.core.security import get_current_account_id
from app.db import get_db
from app.models.community import Community
from app.models.conversation import (
    Conversation,
    ConversationAction,
    ConversationAnalysis,
    ConversationOutcome,
    ConversationScore,
    ReplyDraft,
)
from app.models.enums import ConversationState, DraftVariant, SourceMode
from app.models.topic import Topic
from app.schemas import (
    AnalysisOut,
    ConversationDetailOut,
    ConversationListItemOut,
    ConversationPatchIn,
    CSVImportResult,
    DraftOut,
    DraftPatchIn,
    ManualConversationIn,
    OutcomeIn,
    OutcomeOut,
    ScoreBreakdownOut,
)
from app.services import jobs as jobs_service
from app.services.dedupe import compute_dedupe_hash, normalize_url
from app.services.text_utils import normalize_subreddit

router = APIRouter(prefix="/api/conversations", tags=["conversations"])

RAW_RETENTION_HOURS_DEFAULT = 48


def _list_item(c: Conversation, topic_name: str | None = None) -> ConversationListItemOut:
    return ConversationListItemOut(
        id=c.id,
        subreddit=c.subreddit,
        title=c.display_title,
        summary=c.summary,
        problem_detected=c.problem_detected,
        language=c.language,
        state=c.state.value,
        score_total=c.score_total,
        recommended_action=c.recommended_action.value if c.recommended_action else None,
        promotion_risk=c.promotion_risk.value if c.promotion_risk else None,
        topic_id=c.topic_id,
        topic_name=topic_name,
        published_at=c.published_at,
        detected_at=c.detected_at,
        num_comments=c.num_comments,
        url=c.url,
        source_mode=c.source_mode.value,
        is_demo=c.is_demo,
        raw_purged=c.raw_purged_at is not None,
    )


@router.get("", response_model=list[ConversationListItemOut])
async def list_conversations(
    account_id: uuid.UUID = Depends(get_current_account_id),
    session: AsyncSession = Depends(get_db),
    q: str = Query("", description="Free-text search over title/summary"),
    state: str | None = None,
    min_score: int | None = None,
    subreddit: str | None = None,
    topic_id: uuid.UUID | None = None,
    language: str | None = None,
    sort: str = Query("score", pattern="^(score|recent)$"),
):
    stmt = select(Conversation).where(Conversation.account_id == account_id)
    if state:
        if state not in ConversationState.__members__:
            raise HTTPException(400, f"Invalid state '{state}'")
        stmt = stmt.where(Conversation.state == state)
    if min_score is not None:
        stmt = stmt.where(Conversation.score_total >= min_score)
    if subreddit:
        # Stored values are canonical, so canonicalize the filter too — a
        # user filtering by "r/agency" should still find r/agency's posts.
        stmt = stmt.where(Conversation.subreddit == normalize_subreddit(subreddit))
    if topic_id:
        stmt = stmt.where(Conversation.topic_id == topic_id)
    if language:
        stmt = stmt.where(Conversation.language == language)

    stmt = stmt.order_by(
        Conversation.score_total.desc().nullslast()
        if sort == "score"
        else Conversation.detected_at.desc()
    )
    rows = (await session.execute(stmt)).scalars().all()

    if q:
        needle = q.lower()
        rows = [c for c in rows if needle in (c.summary or "").lower() or needle in (c.raw_title or "").lower()]

    topic_ids = {c.topic_id for c in rows if c.topic_id}
    topics_by_id = {}
    if topic_ids:
        topic_rows = (await session.execute(select(Topic).where(Topic.id.in_(topic_ids)))).scalars().all()
        topics_by_id = {t.id: t.name for t in topic_rows}

    return [_list_item(c, topics_by_id.get(c.topic_id)) for c in rows]


async def _dedupe_lookup(session, account_id, reddit_post_id, url, dedupe_hash) -> Conversation | None:
    if reddit_post_id:
        existing = (
            await session.execute(
                select(Conversation).where(
                    Conversation.account_id == account_id, Conversation.reddit_post_id == reddit_post_id
                )
            )
        ).scalars().first()
        if existing:
            return existing
    if url:
        existing = (
            await session.execute(
                select(Conversation).where(
                    Conversation.account_id == account_id,
                    Conversation.url_normalized == url,
                )
            )
        ).scalars().first()
        if existing:
            return existing
    existing = (
        await session.execute(
            select(Conversation).where(Conversation.account_id == account_id, Conversation.dedupe_hash == dedupe_hash)
        )
    ).scalars().first()
    return existing


async def _create_and_analyze(
    session: AsyncSession,
    settings: Settings,
    *,
    account_id: uuid.UUID,
    source_mode: SourceMode,
    url: str,
    subreddit: str,
    title: str,
    body: str,
    published_at: datetime | None,
    num_comments: int,
    language: str,
    is_demo: bool = False,
    reddit_post_id: str | None = None,
    community_id: uuid.UUID | None = None,
    raw_author: str | None = None,
    is_removed_upstream: bool = False,
    max_age_hours: int | None = None,
) -> Conversation:
    # url_norm is a dedupe-only identifier — when the user didn't paste a URL we
    # synthesize one (manual://subreddit/title) so dedupe/uniqueness still work,
    # but it is NEVER a clickable link, so it must never end up in the
    # user-facing `url` field (that field feeds "Abrir en Reddit" — putting a
    # fake manual:// URI there would make that button silently dead).
    # Every ingestion path (manual, CSV, Reddit fetch) funnels through here,
    # so this is the one place that needs to canonicalize the subreddit —
    # doing it before the dedupe hash keeps "r/SaaS" and "SaaS" the same post.
    subreddit = normalize_subreddit(subreddit)
    url_norm = normalize_url(url) if url else f"manual://{subreddit}/{title}"
    dedupe_hash = compute_dedupe_hash(subreddit, title, published_at, reddit_post_id)

    existing = await _dedupe_lookup(session, account_id, reddit_post_id, url_norm, dedupe_hash)
    if existing:
        return existing

    now = datetime.now(timezone.utc)
    convo = Conversation(
        account_id=account_id,
        source_mode=source_mode,
        reddit_post_id=reddit_post_id,
        url=url,
        url_normalized=url_norm,
        dedupe_hash=dedupe_hash,
        subreddit=subreddit,
        community_id=community_id,
        language=language or "en",
        raw_title=title,
        raw_body=body,
        raw_author=raw_author,
        is_removed_upstream=is_removed_upstream,
        expires_at=now + timedelta(hours=settings.raw_content_retention_hours or RAW_RETENTION_HOURS_DEFAULT),
        published_at=published_at,
        detected_at=now,
        num_comments=num_comments,
        is_demo=is_demo,
    )
    session.add(convo)
    await session.flush()
    session.add(
        ConversationAction(
            conversation_id=convo.id, account_id=account_id, action_type="imported",
            payload={"source_mode": source_mode.value},
        )
    )
    # Pass the caller's window through: the Reddit fetch job resolves this
    # per community from the active watch profile, and dropping it here made
    # every ingested post fall back to the global default instead.
    await jobs_service._analyze_one(session, convo, settings, max_age_hours=max_age_hours)
    await session.commit()
    await session.refresh(convo)
    return convo


@router.post("/manual", response_model=ConversationListItemOut, status_code=201)
async def create_manual_conversation(
    body: ManualConversationIn,
    account_id: uuid.UUID = Depends(get_current_account_id),
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    convo = await _create_and_analyze(
        session, settings, account_id=account_id, source_mode=SourceMode.manual,
        url=body.url, subreddit=body.subreddit, title=body.title, body=body.body,
        published_at=body.published_at, num_comments=body.num_comments, language=body.language,
    )
    return _list_item(convo)


@router.post("/import", response_model=CSVImportResult)
async def import_csv(
    file: UploadFile,
    account_id: uuid.UUID = Depends(get_current_account_id),
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    raw = (await file.read()).decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(raw))
    imported, duplicates, errors = 0, 0, []

    for i, row in enumerate(reader, start=2):
        try:
            subreddit = (row.get("subreddit") or "").strip()
            title = (row.get("title") or "").strip()
            if not subreddit or not title:
                errors.append(f"Fila {i}: faltan subreddit o title")
                continue
            published_raw = (row.get("published_at") or row.get("fecha") or "").strip()
            published_at = None
            if published_raw:
                try:
                    published_at = datetime.fromisoformat(published_raw)
                except ValueError:
                    errors.append(f"Fila {i}: fecha inválida '{published_raw}'")

            before_count = (
                await session.execute(
                    select(Conversation.id).where(Conversation.account_id == account_id)
                )
            ).scalars().all()
            convo = await _create_and_analyze(
                session, settings, account_id=account_id, source_mode=SourceMode.manual,
                url=(row.get("url") or "").strip(), subreddit=subreddit, title=title,
                body=(row.get("body") or row.get("text") or "").strip(),
                published_at=published_at,
                num_comments=int(row.get("num_comments") or 0),
                language=(row.get("language") or "en").strip(),
            )
            if convo.id in before_count:
                duplicates += 1
            else:
                imported += 1
        except Exception as exc:  # noqa: BLE001
            errors.append(f"Fila {i}: {exc}")

    return CSVImportResult(imported=imported, duplicates=duplicates, errors=errors)


async def _get_owned_conversation(session, account_id, conversation_id) -> Conversation:
    convo = (
        await session.execute(
            select(Conversation).where(Conversation.id == conversation_id, Conversation.account_id == account_id)
        )
    ).scalars().first()
    if not convo:
        raise HTTPException(404, "Conversation not found")
    return convo


@router.get("/{conversation_id}", response_model=ConversationDetailOut)
async def get_conversation(
    conversation_id: uuid.UUID,
    account_id: uuid.UUID = Depends(get_current_account_id),
    session: AsyncSession = Depends(get_db),
):
    convo = await _get_owned_conversation(session, account_id, conversation_id)

    analysis = (
        await session.execute(select(ConversationAnalysis).where(ConversationAnalysis.conversation_id == convo.id))
    ).scalars().first()
    score = (
        await session.execute(
            select(ConversationScore)
            .where(ConversationScore.conversation_id == convo.id)
            .order_by(ConversationScore.created_at.desc())
        )
    ).scalars().first()
    drafts = (
        await session.execute(select(ReplyDraft).where(ReplyDraft.conversation_id == convo.id))
    ).scalars().all()
    outcome = (
        await session.execute(select(ConversationOutcome).where(ConversationOutcome.conversation_id == convo.id))
    ).scalars().first()
    community = (
        await session.execute(select(Community).where(Community.id == convo.community_id))
    ).scalars().first() if convo.community_id else None
    topic = (
        await session.execute(select(Topic).where(Topic.id == convo.topic_id))
    ).scalars().first() if convo.topic_id else None

    base = _list_item(convo, topic.name if topic else None)
    return ConversationDetailOut(
        **base.model_dump(),
        raw_title=convo.raw_title,
        raw_body=convo.raw_body,
        community_notes=community.notes if community else None,
        community_rules_url=community.rules_url if community else None,
        analysis=AnalysisOut(
            audience_type=analysis.audience_type, problem_detected=analysis.problem_detected,
            intent=analysis.intent, can_add_value=analysis.can_add_value, value_angle=analysis.value_angle,
            tool_request=analysis.tool_request, radarin_fit=analysis.radarin_fit,
            promotion_risk=analysis.promotion_risk.value, recommended_action=analysis.recommended_action.value,
            mention_radarin=analysis.mention_radarin.value, reasoning_summary=analysis.reasoning_summary,
            confidence=analysis.confidence,
        ) if analysis else None,
        score_breakdown=ScoreBreakdownOut(
            audience_fit=score.audience_fit, problem_fit=score.problem_fit, request_intent=score.request_intent,
            value_potential=score.value_potential, recency=score.recency, low_competition=score.low_competition,
            community_priority=score.community_priority, promotion_risk_penalty=score.promotion_risk_penalty,
            total=score.total, classification=score.classification,
        ) if score else None,
        drafts=[DraftOut.model_validate(d) for d in drafts],
        outcome=OutcomeOut(
            responded_at=outcome.responded_at, final_text_used=outcome.final_text_used, notes=outcome.notes,
            upvotes=outcome.upvotes, reply_count=outcome.reply_count, attributed_visits=outcome.attributed_visits,
            attributed_signups=outcome.attributed_signups, result=outcome.result.value,
        ) if outcome else None,
        expires_at=convo.expires_at,
    )


@router.patch("/{conversation_id}", response_model=ConversationListItemOut)
async def patch_conversation(
    conversation_id: uuid.UUID,
    body: ConversationPatchIn,
    account_id: uuid.UUID = Depends(get_current_account_id),
    session: AsyncSession = Depends(get_db),
):
    convo = await _get_owned_conversation(session, account_id, conversation_id)
    if body.state:
        convo.state = ConversationState(body.state)
        session.add(
            ConversationAction(
                conversation_id=convo.id, account_id=account_id, action_type=f"state_changed_to_{body.state}",
                payload={},
            )
        )
    await session.commit()
    await session.refresh(convo)
    return _list_item(convo)


@router.post("/{conversation_id}/analyze", response_model=ConversationListItemOut)
async def analyze_conversation(
    conversation_id: uuid.UUID,
    account_id: uuid.UUID = Depends(get_current_account_id),
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    convo = await _get_owned_conversation(session, account_id, conversation_id)
    convo.is_analyzed = False
    await jobs_service._analyze_one(session, convo, settings, max_age_hours=None)
    await session.commit()
    await session.refresh(convo)
    return _list_item(convo)


@router.post("/{conversation_id}/recalculate", response_model=ConversationListItemOut)
async def recalculate_conversation(
    conversation_id: uuid.UUID,
    account_id: uuid.UUID = Depends(get_current_account_id),
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    convo = await _get_owned_conversation(session, account_id, conversation_id)
    if not convo.is_analyzed:
        raise HTTPException(400, "Conversation has not been analyzed yet")
    convo.is_analyzed = False
    await jobs_service._analyze_one(session, convo, settings, max_age_hours=None)
    session.add(
        ConversationAction(conversation_id=convo.id, account_id=account_id, action_type="recalculated", payload={})
    )
    await session.commit()
    await session.refresh(convo)
    return _list_item(convo)


@router.post("/{conversation_id}/drafts", response_model=list[DraftOut])
async def regenerate_drafts(
    conversation_id: uuid.UUID,
    account_id: uuid.UUID = Depends(get_current_account_id),
    session: AsyncSession = Depends(get_db),
):
    from app.services import drafts as drafts_service

    convo = await _get_owned_conversation(session, account_id, conversation_id)
    analysis = (
        await session.execute(select(ConversationAnalysis).where(ConversationAnalysis.conversation_id == convo.id))
    ).scalars().first()
    if not analysis:
        raise HTTPException(400, "Conversation has not been analyzed yet")

    old_drafts = (
        await session.execute(select(ReplyDraft).where(ReplyDraft.conversation_id == convo.id))
    ).scalars().all()
    for d in old_drafts:
        await session.delete(d)
    await session.flush()

    variant_bodies = drafts_service.generate_drafts(
        language=convo.language, tool_request=analysis.tool_request,
        promotion_risk=analysis.promotion_risk.value, topic_name="",
    )
    recommended = drafts_service.recommended_variant(
        tool_request=analysis.tool_request, promotion_risk=analysis.promotion_risk.value
    )
    new_drafts = []
    for variant, body_text in variant_bodies.items():
        d = ReplyDraft(
            conversation_id=convo.id, variant=variant, language=convo.language, body=body_text,
            is_recommended=(variant == recommended),
        )
        session.add(d)
        new_drafts.append(d)
    await session.commit()
    for d in new_drafts:
        await session.refresh(d)
    return [DraftOut.model_validate(d) for d in new_drafts]


@router.patch("/{conversation_id}/drafts/{draft_id}", response_model=DraftOut)
async def edit_draft(
    conversation_id: uuid.UUID,
    draft_id: uuid.UUID,
    body: DraftPatchIn,
    account_id: uuid.UUID = Depends(get_current_account_id),
    session: AsyncSession = Depends(get_db),
):
    await _get_owned_conversation(session, account_id, conversation_id)
    draft = (
        await session.execute(select(ReplyDraft).where(ReplyDraft.id == draft_id, ReplyDraft.conversation_id == conversation_id))
    ).scalars().first()
    if not draft:
        raise HTTPException(404, "Draft not found")
    draft.body = body.body
    draft.is_edited = True
    await session.commit()
    await session.refresh(draft)
    return DraftOut.model_validate(draft)


@router.post("/{conversation_id}/actions")
async def record_action(
    conversation_id: uuid.UUID,
    action_type: str = Query(...),
    account_id: uuid.UUID = Depends(get_current_account_id),
    session: AsyncSession = Depends(get_db),
):
    convo = await _get_owned_conversation(session, account_id, conversation_id)
    session.add(
        ConversationAction(conversation_id=convo.id, account_id=account_id, action_type=action_type, payload={})
    )
    state_map = {
        "saved": ConversationState.saved,
        "marked_responded": ConversationState.responded,
        "discarded": ConversationState.discarded,
        "restored": ConversationState.recommended,
    }
    if action_type in state_map:
        convo.state = state_map[action_type]
    await session.commit()
    return {"ok": True}


@router.post("/{conversation_id}/outcome", response_model=OutcomeOut)
async def set_outcome(
    conversation_id: uuid.UUID,
    body: OutcomeIn,
    account_id: uuid.UUID = Depends(get_current_account_id),
    session: AsyncSession = Depends(get_db),
):
    convo = await _get_owned_conversation(session, account_id, conversation_id)
    outcome = (
        await session.execute(select(ConversationOutcome).where(ConversationOutcome.conversation_id == convo.id))
    ).scalars().first()
    if not outcome:
        outcome = ConversationOutcome(conversation_id=convo.id)
        session.add(outcome)

    outcome.final_text_used = body.final_text_used
    outcome.notes = body.notes
    outcome.upvotes = body.upvotes
    outcome.reply_count = body.reply_count
    outcome.attributed_visits = body.attributed_visits
    outcome.attributed_signups = body.attributed_signups
    outcome.result = body.result
    outcome.responded_at = datetime.now(timezone.utc)
    convo.state = ConversationState.responded

    if convo.community_id:
        community = (await session.execute(select(Community).where(Community.id == convo.community_id))).scalars().first()
        if community:
            community.responses_made = (community.responses_made or 0) + 1

    session.add(
        ConversationAction(conversation_id=convo.id, account_id=account_id, action_type="outcome_recorded", payload={"result": body.result})
    )
    await session.commit()
    await session.refresh(outcome)
    return OutcomeOut(
        responded_at=outcome.responded_at, final_text_used=outcome.final_text_used, notes=outcome.notes,
        upvotes=outcome.upvotes, reply_count=outcome.reply_count, attributed_visits=outcome.attributed_visits,
        attributed_signups=outcome.attributed_signups, result=outcome.result.value,
    )


@router.delete("/{conversation_id}/raw-content", status_code=204)
async def purge_raw_content_now(
    conversation_id: uuid.UUID,
    account_id: uuid.UUID = Depends(get_current_account_id),
    session: AsyncSession = Depends(get_db),
):
    """Manual 'delete immediately' control required by spec section 9."""
    convo = await _get_owned_conversation(session, account_id, conversation_id)
    convo.raw_title = None
    convo.raw_body = None
    convo.raw_author = None
    convo.raw_purged_at = datetime.now(timezone.utc)
    session.add(
        ConversationAction(conversation_id=convo.id, account_id=account_id, action_type="purged", payload={"manual": True})
    )
    await session.commit()
