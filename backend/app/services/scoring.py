"""Explainable 0-100 scoring engine (spec section 12).

score = audience_fit + problem_fit + request_intent + value_potential
        + recency + low_competition + community_priority - promotion_risk_penalty

Every sub-score is capped at its documented maximum so the breakdown always
adds up to the total, and the total itself is clamped to [0, 100].
"""

from dataclasses import dataclass, asdict
from datetime import datetime, timezone

from app.models.enums import Priority, PromotionRisk

MAX_AUDIENCE_FIT = 25
MAX_PROBLEM_FIT = 25
MAX_REQUEST_INTENT = 15
MAX_VALUE_POTENTIAL = 15
MAX_RECENCY = 10
MAX_LOW_COMPETITION = 5
MAX_COMMUNITY_PRIORITY = 5
MAX_PROMOTION_PENALTY = 20


@dataclass
class ScoreInput:
    audience_fit: bool  # matches Radarin's target audience (agencies, freelancers, local biz)
    problem_fit: bool  # conversation is about a problem Radarin solves
    requests_advice_or_tool: bool
    can_offer_concrete_value: bool
    published_at: datetime | None
    num_comments: int
    community_priority: Priority
    promotion_risk: PromotionRisk


@dataclass
class ScoreBreakdown:
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

    def as_dict(self) -> dict:
        return asdict(self)


_COMMUNITY_PRIORITY_POINTS = {Priority.high: MAX_COMMUNITY_PRIORITY, Priority.medium: 3, Priority.low: 1}
_PROMOTION_PENALTY_POINTS = {PromotionRisk.low: 0, PromotionRisk.medium: 10, PromotionRisk.high: MAX_PROMOTION_PENALTY}


def _recency_points(published_at: datetime | None) -> int:
    if published_at is None:
        return 0
    now = datetime.now(timezone.utc)
    pub = published_at if published_at.tzinfo else published_at.replace(tzinfo=timezone.utc)
    hours = max((now - pub).total_seconds() / 3600, 0)
    if hours <= 6:
        return MAX_RECENCY
    if hours <= 24:
        return 8
    if hours <= 48:
        return 5
    if hours <= 72:
        return 2
    return 0


def _low_competition_points(num_comments: int) -> int:
    if num_comments <= 2:
        return MAX_LOW_COMPETITION
    if num_comments <= 5:
        return 3
    if num_comments <= 10:
        return 1
    return 0


def classify(total: int) -> str:
    if total >= 85:
        return "respond_now"
    if total >= 70:
        return "review_today"
    if total >= 55:
        return "help_without_mentioning"
    if total >= 40:
        return "observe"
    return "discard"


def compute_score(inp: ScoreInput) -> ScoreBreakdown:
    audience_fit = MAX_AUDIENCE_FIT if inp.audience_fit else 0
    problem_fit = MAX_PROBLEM_FIT if inp.problem_fit else 0
    request_intent = MAX_REQUEST_INTENT if inp.requests_advice_or_tool else 0
    value_potential = MAX_VALUE_POTENTIAL if inp.can_offer_concrete_value else 0
    recency = _recency_points(inp.published_at)
    low_competition = _low_competition_points(inp.num_comments)
    community_priority = _COMMUNITY_PRIORITY_POINTS[inp.community_priority]
    promotion_risk_penalty = _PROMOTION_PENALTY_POINTS[inp.promotion_risk]

    raw_total = (
        audience_fit
        + problem_fit
        + request_intent
        + value_potential
        + recency
        + low_competition
        + community_priority
        - promotion_risk_penalty
    )
    total = max(0, min(100, raw_total))

    return ScoreBreakdown(
        audience_fit=audience_fit,
        problem_fit=problem_fit,
        request_intent=request_intent,
        value_potential=value_potential,
        recency=recency,
        low_competition=low_competition,
        community_priority=community_priority,
        promotion_risk_penalty=promotion_risk_penalty,
        total=total,
        classification=classify(total),
    )
