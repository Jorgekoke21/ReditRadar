from datetime import datetime, timedelta, timezone

from app.models.enums import Priority, PromotionRisk
from app.services.scoring import ScoreInput, classify, compute_score


def _base_input(**overrides) -> ScoreInput:
    defaults = dict(
        audience_fit=True,
        problem_fit=True,
        requests_advice_or_tool=True,
        can_offer_concrete_value=True,
        published_at=datetime.now(timezone.utc),
        num_comments=1,
        community_priority=Priority.high,
        promotion_risk=PromotionRisk.low,
    )
    defaults.update(overrides)
    return ScoreInput(**defaults)


def test_perfect_input_scores_100_and_clamps():
    breakdown = compute_score(_base_input())
    assert breakdown.total == 100
    assert breakdown.classification == "respond_now"


def test_breakdown_components_sum_to_total():
    breakdown = compute_score(
        _base_input(promotion_risk=PromotionRisk.medium, num_comments=8, community_priority=Priority.low)
    )
    computed = (
        breakdown.audience_fit
        + breakdown.problem_fit
        + breakdown.request_intent
        + breakdown.value_potential
        + breakdown.recency
        + breakdown.low_competition
        + breakdown.community_priority
        - breakdown.promotion_risk_penalty
    )
    assert computed == breakdown.total


def test_score_never_negative_even_with_worst_inputs():
    breakdown = compute_score(
        _base_input(
            audience_fit=False,
            problem_fit=False,
            requests_advice_or_tool=False,
            can_offer_concrete_value=False,
            published_at=datetime.now(timezone.utc) - timedelta(days=30),
            num_comments=100,
            community_priority=Priority.low,
            promotion_risk=PromotionRisk.high,
        )
    )
    assert 0 <= breakdown.total <= 100
    assert breakdown.total == 0
    assert breakdown.classification == "discard"


def test_score_never_exceeds_100_with_extra_credit_inputs():
    # every sub-score maxed plus a zero penalty should still clamp at 100
    breakdown = compute_score(_base_input(num_comments=0, community_priority=Priority.high))
    assert breakdown.total <= 100


def test_classification_thresholds():
    assert classify(85) == "respond_now"
    assert classify(84) == "review_today"
    assert classify(70) == "review_today"
    assert classify(69) == "help_without_mentioning"
    assert classify(55) == "help_without_mentioning"
    assert classify(54) == "observe"
    assert classify(40) == "observe"
    assert classify(39) == "discard"
    assert classify(0) == "discard"


def test_high_promotion_risk_applies_full_penalty():
    low_risk = compute_score(_base_input(promotion_risk=PromotionRisk.low))
    high_risk = compute_score(_base_input(promotion_risk=PromotionRisk.high))
    assert high_risk.promotion_risk_penalty == 20
    assert high_risk.total == low_risk.total - 20
