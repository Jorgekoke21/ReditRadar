"""ConversationAnalyzer abstraction (spec section 11).

RulesConversationAnalyzer is always available and requires no external
service — it is what powers Demo and Manual mode out of the box.
LLMConversationAnalyzer is only ever instantiated when AI_ANALYSIS_ENABLED
is true and an API key is configured; get_analyzer() falls back to rules
otherwise so the app always keeps working without an AI provider.

Only the fields in AnalysisResult ever leave this module — no raw model
chain-of-thought is stored or displayed, matching the "no mostrar cadenas
de razonamiento privadas" requirement.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import httpx

from app.config import Settings
from app.models.enums import MentionRadarin, PromotionRisk, RecommendedAction, SelfPromoPolicy
from app.services.text_utils import normalize

TOOL_REQUEST_PATTERNS = [
    "recommend a tool", "any tool", "any software", "que herramienta", "qué herramienta",
    "recomendáis", "recomiendan", "any app for", "is there a tool", "software recomendado",
    "crm recomendado", "какой инструмент",
]

QUESTION_MARKERS = ["?", "¿"]

AUDIENCE_HINTS = {
    "agency": "agencia de marketing o servicios digitales",
    "localseo": "profesional de SEO local",
    "web_design": "diseñador o desarrollador web freelance",
    "freelance": "freelancer de servicios digitales",
    "sales": "responsable comercial / ventas",
    "marketing": "profesional de marketing",
    "smallbusiness": "dueño de pequeño negocio",
    "saas": "fundador de SaaS en fase temprana",
    "saasdevelopers": "desarrollador construyendo un SaaS",
    "sideproject": "creador de un side project",
    "startups": "fundador de startup",
    "entrepreneur": "emprendedor",
    "entrepreneurridealong": "emprendedor documentando su progreso",
    "thesidehustle": "persona buscando ingresos extra",
}


@dataclass
class AnalysisResult:
    audience_type: str
    problem_detected: str
    intent: str
    topic_ids: list[str]
    can_add_value: bool
    value_angle: str
    tool_request: bool
    radarin_fit: str  # high | medium | low
    promotion_risk: PromotionRisk
    recommended_action: RecommendedAction
    mention_radarin: MentionRadarin
    reasoning_summary: str
    confidence: int
    analyzer_name: str = "rules"


@dataclass
class TopicForMatching:
    id: str
    name: str
    description: str
    keywords: list[str]
    exclusions: list[str]


@dataclass
class ConversationForAnalysis:
    subreddit: str
    title: str
    body: str
    language: str
    num_comments: int
    self_promo_policy: SelfPromoPolicy = SelfPromoPolicy.unknown


class ConversationAnalyzer(ABC):
    @abstractmethod
    async def analyze(
        self, conversation: ConversationForAnalysis, topics: list[TopicForMatching]
    ) -> AnalysisResult: ...


def _match_topics(text: str, topics: list[TopicForMatching]) -> list[TopicForMatching]:
    normalized = normalize(text)
    matches = []
    for topic in topics:
        if not topic.keywords:
            continue
        if any(normalize(kw) in normalized for kw in topic.exclusions):
            continue
        if any(normalize(kw) in normalized for kw in topic.keywords):
            matches.append(topic)
    return matches


def _looks_like_question(text: str) -> bool:
    return any(marker in text for marker in QUESTION_MARKERS)


def _looks_like_tool_request(text: str) -> bool:
    normalized = normalize(text)
    return any(normalize(p) in normalized for p in TOOL_REQUEST_PATTERNS)


class RulesConversationAnalyzer(ConversationAnalyzer):
    """Deterministic, explainable, zero-dependency analyzer. Always available."""

    async def analyze(
        self, conversation: ConversationForAnalysis, topics: list[TopicForMatching]
    ) -> AnalysisResult:
        text = f"{conversation.title}\n{conversation.body}"
        matched_topics = _match_topics(text, topics)
        is_question = _looks_like_question(text)
        tool_request = _looks_like_tool_request(text)

        audience_type = AUDIENCE_HINTS.get(
            conversation.subreddit.lower(), "profesional relacionado con negocio local o agencia"
        )

        if matched_topics:
            problem_detected = matched_topics[0].description or (
                f"Menciona: {matched_topics[0].name}"
            )
        else:
            problem_detected = "No se detectó un problema claro relacionado con Radarin."

        can_add_value = bool(matched_topics) and (is_question or tool_request)

        if tool_request:
            value_angle = "Puede beneficiarse de conocer cómo priorizar y preparar oportunidades comerciales."
        elif matched_topics:
            value_angle = f"Aportar un método práctico relacionado con {matched_topics[0].name.lower()}."
        else:
            value_angle = ""

        # promotion risk: explicit self-promo in the post already, or a community
        # that disallows/limits self-promotion, raises the risk of our reply
        # looking promotional.
        contains_self_promo_language = bool(
            re.search(r"\b(check out my|i built|i made|he creado|he lanzado|prueba mi)\b", text, re.I)
        )
        if contains_self_promo_language:
            promotion_risk = PromotionRisk.high
        elif conversation.self_promo_policy == SelfPromoPolicy.no:
            promotion_risk = PromotionRisk.medium
        elif tool_request:
            promotion_risk = PromotionRisk.low
        else:
            promotion_risk = PromotionRisk.medium

        if not matched_topics:
            recommended_action = RecommendedAction.discard
        elif not is_question and not tool_request:
            recommended_action = RecommendedAction.observe
        elif tool_request and promotion_risk in (PromotionRisk.low, PromotionRisk.medium):
            recommended_action = RecommendedAction.respond_now
        elif is_question:
            recommended_action = RecommendedAction.review_today
        else:
            recommended_action = RecommendedAction.help_without_mentioning

        if tool_request and promotion_risk == PromotionRisk.low:
            mention_radarin = MentionRadarin.transparent_direct
        elif can_add_value and promotion_risk != PromotionRisk.high:
            mention_radarin = MentionRadarin.soft
        else:
            mention_radarin = MentionRadarin.no

        radarin_fit = "high" if (matched_topics and tool_request) else ("medium" if matched_topics else "low")

        topic_names = ", ".join(t.name for t in matched_topics) or "ninguno"
        reasoning_summary = (
            f"Temas detectados: {topic_names}. "
            f"{'Pide herramienta/consejo. ' if tool_request else ''}"
            f"{'Es una pregunta abierta. ' if is_question else ''}"
            f"Riesgo promocional estimado: {promotion_risk.value}."
        )

        return AnalysisResult(
            audience_type=audience_type,
            problem_detected=problem_detected,
            intent="seeking_advice" if (is_question or tool_request) else "sharing_experience",
            topic_ids=[t.id for t in matched_topics],
            can_add_value=can_add_value,
            value_angle=value_angle,
            tool_request=tool_request,
            radarin_fit=radarin_fit,
            promotion_risk=promotion_risk,
            recommended_action=recommended_action,
            mention_radarin=mention_radarin,
            reasoning_summary=reasoning_summary,
            confidence=60,
            analyzer_name="rules",
        )


class LLMConversationAnalyzer(ConversationAnalyzer):
    """Optional classification via a configurable AI provider.

    Only ever constructed by get_analyzer() when AI_ANALYSIS_ENABLED=true and
    an API key is present. Sends only title/body/subreddit/language — never
    the raw author name or any other field not needed for classification.
    The response is used strictly for classification/drafting; it is never
    used to fine-tune or train anything.
    """

    def __init__(self, settings: Settings):
        self._settings = settings

    async def analyze(
        self, conversation: ConversationForAnalysis, topics: list[TopicForMatching]
    ) -> AnalysisResult:
        if self._settings.ai_provider == "openai":
            return await self._analyze_openai_compatible(conversation, topics)
        if self._settings.ai_provider == "anthropic":
            return await self._analyze_anthropic(conversation, topics)
        raise ValueError(f"Unsupported AI_PROVIDER: {self._settings.ai_provider!r}")

    async def _analyze_openai_compatible(self, conversation, topics) -> AnalysisResult:  # pragma: no cover - network
        prompt = _build_prompt(conversation, topics)
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {self._settings.ai_api_key}"},
                json={
                    "model": self._settings.ai_model or "gpt-4o-mini",
                    "messages": [{"role": "user", "content": prompt}],
                    "response_format": {"type": "json_object"},
                },
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
        return _parse_llm_json(content)

    async def _analyze_anthropic(self, conversation, topics) -> AnalysisResult:  # pragma: no cover - network
        prompt = _build_prompt(conversation, topics)
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": self._settings.ai_api_key,
                    "anthropic-version": "2023-06-01",
                },
                json={
                    "model": self._settings.ai_model or "claude-haiku-4-5",
                    "max_tokens": 800,
                    "messages": [{"role": "user", "content": prompt}],
                },
            )
            resp.raise_for_status()
            content = resp.json()["content"][0]["text"]
        return _parse_llm_json(content)


def _build_prompt(conversation: ConversationForAnalysis, topics: list[TopicForMatching]) -> str:
    topic_lines = "\n".join(f"- {t.id}: {t.name} — {t.description}" for t in topics)
    return (
        "Classify this Reddit post for a business-development radar. "
        "Return ONLY a JSON object with keys: audience_type, problem_detected, intent, "
        "topic_ids (array), can_add_value (bool), value_angle, tool_request (bool), "
        "radarin_fit (high|medium|low), promotion_risk (low|medium|high), "
        "recommended_action (respond_now|review_today|help_without_mentioning|ask_question|observe|discard), "
        "mention_radarin (no|soft|transparent_direct), reasoning_summary, confidence (0-100).\n\n"
        f"Known topics:\n{topic_lines}\n\n"
        f"Subreddit: {conversation.subreddit}\nLanguage: {conversation.language}\n"
        f"Title: {conversation.title}\nBody: {conversation.body[:2000]}\n"
    )


def _parse_llm_json(content: str) -> AnalysisResult:  # pragma: no cover - network
    import json

    data = json.loads(content)
    return AnalysisResult(
        audience_type=data.get("audience_type", ""),
        problem_detected=data.get("problem_detected", ""),
        intent=data.get("intent", ""),
        topic_ids=data.get("topic_ids", []),
        can_add_value=bool(data.get("can_add_value", False)),
        value_angle=data.get("value_angle", ""),
        tool_request=bool(data.get("tool_request", False)),
        radarin_fit=data.get("radarin_fit", "low"),
        promotion_risk=PromotionRisk(data.get("promotion_risk", "medium")),
        recommended_action=RecommendedAction(data.get("recommended_action", "observe")),
        mention_radarin=MentionRadarin(data.get("mention_radarin", "no")),
        reasoning_summary=data.get("reasoning_summary", ""),
        confidence=int(data.get("confidence", 50)),
        analyzer_name=f"llm",
    )


def get_analyzer(settings: Settings) -> ConversationAnalyzer:
    if settings.ai_analysis_enabled and settings.ai_api_key and settings.ai_provider:
        return LLMConversationAnalyzer(settings)
    return RulesConversationAnalyzer()
