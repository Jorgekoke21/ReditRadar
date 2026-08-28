"""Pydantic request/response schemas. Kept in one module — the API surface
is small enough that per-domain files would add navigation cost without
real benefit. Response models are explicit allow-lists: nothing here ever
includes token fields (see ReplyDraft/RedditConnection below), matching the
'no devolver tokens ni secretos al frontend' requirement.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --- auth -------------------------------------------------------------
class DevLoginRequest(BaseModel):
    email: str


class ProfileOut(ORMModel):
    id: uuid.UUID
    account_id: uuid.UUID
    email: str
    display_name: str


class SessionOut(BaseModel):
    access_token: str
    profile: ProfileOut


class AuthConfigOut(BaseModel):
    """Public, unauthenticated — the login page needs this before any
    session exists. supabase_anon_key is meant to be public (it's what
    Supabase's own JS client ships to the browser); nothing secret goes here."""

    auth_mode: str
    dev_login_available: bool
    supabase_url: str
    supabase_anon_key: str


# --- communities --------------------------------------------------------
class CommunityIn(BaseModel):
    name: str
    is_active: bool = True
    group: str = "leads"
    priority: str = "medium"
    primary_language: str = "en"
    allows_links: str = "unknown"
    allows_self_promo: str = "unknown"
    notes: str = ""
    rules_url: str = ""
    rules_last_reviewed_at: date | None = None


class CommunityOut(ORMModel):
    id: uuid.UUID
    name: str
    is_active: bool
    group: str
    priority: str
    primary_language: str
    allows_links: str
    allows_self_promo: str
    notes: str
    rules_url: str
    rules_last_reviewed_at: date | None
    opportunities_found: int
    responses_made: int
    historical_outcome: str
    reddit_watermark_id: str | None = None
    reddit_watermark_at: datetime | None = None
    reddit_last_fetch_at: datetime | None = None
    reddit_last_success_at: datetime | None = None
    reddit_last_error: str = ""
    reddit_rate_remaining: float | None = None
    reddit_rate_used: float | None = None
    reddit_rate_reset_seconds: float | None = None


# --- topics --------------------------------------------------------------
class TopicIn(BaseModel):
    name: str
    description: str = ""
    languages: str = "es,en"
    priority: str = "medium"
    is_active: bool = True
    keywords: list[str] = Field(default_factory=list)
    exclusions: list[str] = Field(default_factory=list)
    positive_examples: list[str] = Field(default_factory=list)
    negative_examples: list[str] = Field(default_factory=list)


class TopicOut(ORMModel):
    id: uuid.UUID
    name: str
    description: str
    languages: str
    priority: str
    is_active: bool
    keywords: list[str]
    exclusions: list[str]
    positive_examples: list[str]
    negative_examples: list[str]


# --- conversations --------------------------------------------------------
class ManualConversationIn(BaseModel):
    url: str = ""
    subreddit: str
    title: str
    body: str = ""
    published_at: datetime | None = None
    num_comments: int = 0
    language: str = "en"


class ScoreBreakdownOut(BaseModel):
    audience_fit: int
    problem_fit: int
    request_intent: int
    value_potential: int
    recency: int
    low_competition: int
    community_priority: int
    promotion_risk_penalty: int
    total: int
    classification: str


class AnalysisOut(ORMModel):
    audience_type: str
    problem_detected: str
    intent: str
    can_add_value: bool
    value_angle: str
    tool_request: bool
    radarin_fit: str
    promotion_risk: str
    recommended_action: str
    mention_radarin: str
    reasoning_summary: str
    confidence: int


class DraftOut(ORMModel):
    id: uuid.UUID
    variant: str
    language: str
    body: str
    is_edited: bool
    is_recommended: bool


class OutcomeIn(BaseModel):
    final_text_used: str = ""
    notes: str = ""
    upvotes: int | None = None
    reply_count: int | None = None
    attributed_visits: int | None = None
    attributed_signups: int | None = None
    result: str = "no_result"


class OutcomeOut(ORMModel):
    responded_at: datetime | None
    final_text_used: str
    notes: str
    upvotes: int | None
    reply_count: int | None
    attributed_visits: int | None
    attributed_signups: int | None
    result: str


class ConversationListItemOut(BaseModel):
    id: uuid.UUID
    subreddit: str
    title: str
    summary: str
    problem_detected: str
    language: str
    state: str
    score_total: int | None
    recommended_action: str | None
    promotion_risk: str | None
    topic_id: uuid.UUID | None
    topic_name: str | None = None
    published_at: datetime | None
    detected_at: datetime
    num_comments: int
    url: str
    source_mode: str
    is_demo: bool
    raw_purged: bool


class ConversationDetailOut(ConversationListItemOut):
    raw_title: str | None
    raw_body: str | None
    community_notes: str | None = None
    community_rules_url: str | None = None
    analysis: AnalysisOut | None
    score_breakdown: ScoreBreakdownOut | None
    drafts: list[DraftOut]
    outcome: OutcomeOut | None
    expires_at: datetime | None


class ConversationPatchIn(BaseModel):
    state: str | None = None


class DraftPatchIn(BaseModel):
    body: str


class CSVImportResult(BaseModel):
    imported: int
    duplicates: int
    errors: list[str]


# --- alerts ----------------------------------------------------------------
class AlertSettingsIn(BaseModel):
    email_recipient: str = ""
    timezone: str = "Europe/Madrid"
    daily_digest_enabled: bool = True
    daily_digest_time: str = "09:00"
    min_score_threshold: int = 60
    urgent_alerts_enabled: bool = True
    urgent_score_threshold: int = 90
    max_urgent_per_day: int = 2
    weekly_digest_enabled: bool = True


class AlertSettingsOut(ORMModel, AlertSettingsIn):
    id: uuid.UUID


class AlertDeliveryOut(ORMModel):
    id: uuid.UUID
    kind: str
    subject: str
    body_html: str
    to_address: str
    provider: str
    sent: bool
    created_at: datetime


# --- jobs / settings ---------------------------------------------------
class JobRunOut(ORMModel):
    id: uuid.UUID
    job_name: str
    started_at: datetime
    finished_at: datetime | None
    status: str
    processed_count: int
    error_count: int
    error_message: str
    duration_ms: int | None
    metrics: dict = Field(default_factory=dict)


class JobTriggerResult(BaseModel):
    job_name: str
    result: dict


class IntegrationsStatusOut(BaseModel):
    reddit_api_enabled: bool
    reddit_connected: bool
    ai_analysis_enabled: bool
    ai_provider: str
    email_provider: str
    email_configured: bool
    auth_mode: str
    dev_auth_bypass: bool
    supabase_configured: bool
    raw_content_retention_hours: int
    reddit_credentials_configured: bool = False
    reddit_last_run_at: datetime | None = None
    reddit_last_success: bool = False
    reddit_posts_retrieved: int = 0
    reddit_new_conversations: int = 0
    reddit_duplicates: int = 0
    reddit_communities_reviewed: int = 0
    reddit_errors: int = 0
    reddit_rate_remaining: float | None = None
    reddit_rate_used: float | None = None
    reddit_rate_reset_seconds: float | None = None
    reddit_next_run_frequency: str = "every 15 minutes"


class DashboardOut(BaseModel):
    found_today: int
    respond_now: int
    review_today: int
    saved: int
    responded: int
    discarded: int
    last_run_at: datetime | None
