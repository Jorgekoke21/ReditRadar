"""Deterministic pre-filter (spec section 10) that runs before the analyzer.

Cheap, explainable checks that never call an LLM. Anything that fails here
is never scored or sent for analysis, which keeps the pipeline fast and
keeps AI usage (when enabled) limited to conversations worth spending on.
"""

from dataclasses import dataclass
from datetime import datetime, timezone

from app.services.text_utils import normalize

JOB_OFFER_PATTERNS = [
    "hiring", "we are hiring", "job opening", "job opportunity", "apply now",
    "send your resume", "send your cv", "looking to hire", "full-time position",
    "part-time position", "buscamos programador", "se busca desarrollador",
    "oferta de empleo", "puesto vacante", "contratando", "envía tu cv",
]

FREE_WORK_PATTERNS = [
    "work for free", "unpaid", "equity only", "no pay", "trabajar gratis",
    "sin remuneracion", "sin remuneración", "a cambio de experiencia",
]

SPAM_PATTERNS = [
    "click here", "limited time offer", "act now", "guaranteed income",
    "make money fast", "dinero facil", "dinero fácil", "gana dinero rapido",
]

CRYPTO_GAMBLING_PATTERNS = [
    "crypto", "bitcoin", "nft", "token presale", "airdrop", "casino",
    "sports betting", "apuestas deportivas", "criptomoneda", "cripto",
]

GENERIC_DROPSHIPPING_PATTERNS = ["dropshipping", "aliexpress store", "shopify dropship"]

UNRELATED_COURSE_PATTERNS = ["my course", "mi curso", "buy my ebook", "compra mi curso"]

MEME_MARKERS = ["meme", "shitpost", "circlejerk", "[removed]", "[deleted]"]

REMOVED_MARKERS = ["[removed]", "[deleted]"]

MIN_CONTENT_LENGTH = 40

VALID_MAX_AGE_HOURS = {24, 48, 72, 168}
DEFAULT_MAX_AGE_HOURS = 72


@dataclass
class FilterResult:
    passed: bool
    reasons: list[str]

    @property
    def rejection_reason(self) -> str | None:
        return None if self.passed else self.reasons[0]


def _contains_any(haystack: str, patterns: list[str]) -> bool:
    normalized = normalize(haystack)
    return any(normalize(p) in normalized for p in patterns)


def is_job_offer(text: str) -> bool:
    return _contains_any(text, JOB_OFFER_PATTERNS) or _contains_any(text, FREE_WORK_PATTERNS)


def is_spam(text: str) -> bool:
    return (
        _contains_any(text, SPAM_PATTERNS)
        or _contains_any(text, CRYPTO_GAMBLING_PATTERNS)
        or _contains_any(text, GENERIC_DROPSHIPPING_PATTERNS)
    )


def is_unrelated_course_promo(text: str) -> bool:
    return _contains_any(text, UNRELATED_COURSE_PATTERNS)


def is_meme(text: str) -> bool:
    return _contains_any(text, MEME_MARKERS)


def is_removed(text: str) -> bool:
    return _contains_any(text, REMOVED_MARKERS)


def is_promotional_without_question(title: str, body: str) -> bool:
    combined = f"{title} {body}"
    has_question = "?" in combined or "¿" in combined
    promo_markers = ["check out my", "i built", "i made", "prueba mi", "he creado", "he lanzado"]
    return _contains_any(combined, promo_markers) and not has_question


def run_initial_filter(
    *,
    title: str,
    body: str,
    subreddit: str,
    published_at: datetime | None,
    is_watched_community: bool,
    has_topic_match: bool,
    already_analyzed: bool,
    is_removed_upstream: bool,
    max_age_hours: int | None = DEFAULT_MAX_AGE_HOURS,
) -> FilterResult:
    reasons: list[str] = []
    text = f"{title}\n{body}"

    if already_analyzed:
        reasons.append("already_analyzed")
    if is_removed_upstream or is_removed(text):
        reasons.append("removed_content")
    if not is_watched_community:
        reasons.append("community_not_watched")
    if published_at is not None:
        age_hours = (datetime.now(timezone.utc) - _as_aware(published_at)).total_seconds() / 3600
        if max_age_hours is not None and age_hours > max_age_hours:
            reasons.append("too_old")
    if len(f"{title} {body}".strip()) < MIN_CONTENT_LENGTH:
        reasons.append("insufficient_content")
    if not has_topic_match:
        reasons.append("no_topic_match")
    if is_job_offer(text):
        reasons.append("job_offer")
    if is_spam(text):
        reasons.append("spam")
    if is_meme(text):
        reasons.append("meme")
    if is_unrelated_course_promo(text):
        reasons.append("unrelated_promotion")
    if is_promotional_without_question(title, body):
        reasons.append("promotional_without_question")

    return FilterResult(passed=len(reasons) == 0, reasons=reasons)


def _as_aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
