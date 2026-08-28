import enum


class Priority(str, enum.Enum):
    high = "high"
    medium = "medium"
    low = "low"


class TriState(str, enum.Enum):
    yes = "yes"
    no = "no"
    unknown = "unknown"


class SelfPromoPolicy(str, enum.Enum):
    yes = "yes"
    no = "no"
    limited = "limited"
    unknown = "unknown"


class SourceMode(str, enum.Enum):
    demo = "demo"
    manual = "manual"
    reddit_api = "reddit_api"


class ConversationState(str, enum.Enum):
    new = "new"
    recommended = "recommended"
    review = "review"
    saved = "saved"
    responded = "responded"
    discarded = "discarded"
    expired = "expired"


class OutcomeResult(str, enum.Enum):
    no_result = "no_result"
    received_upvotes = "received_upvotes"
    author_replied = "author_replied"
    conversation_started = "conversation_started"
    private_message_received = "private_message_received"
    radarin_visit = "radarin_visit"
    radarin_signup = "radarin_signup"
    demo_requested = "demo_requested"
    customer = "customer"
    removed = "removed"


class PromotionRisk(str, enum.Enum):
    low = "low"
    medium = "medium"
    high = "high"


class RecommendedAction(str, enum.Enum):
    respond_now = "respond_now"
    review_today = "review_today"
    help_without_mentioning = "help_without_mentioning"
    ask_question = "ask_question"
    observe = "observe"
    discard = "discard"


class MentionRadarin(str, enum.Enum):
    no = "no"
    soft = "soft"
    transparent_direct = "transparent_direct"


class DraftVariant(str, enum.Enum):
    educational = "educational"
    soft_mention = "soft_mention"
    direct_transparent = "direct_transparent"


class ActionType(str, enum.Enum):
    prepared_reply = "prepared_reply"
    copied_draft = "copied_draft"
    opened_reddit = "opened_reddit"
    saved = "saved"
    marked_responded = "marked_responded"
    discarded = "discarded"
    restored = "restored"
    recalculated = "recalculated"
    analyzed = "analyzed"
    imported = "imported"
