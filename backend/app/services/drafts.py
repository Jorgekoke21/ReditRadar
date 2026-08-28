"""Generates the three reply-draft variants described in spec section 13.

Templates are intentionally varied (several phrasings per slot) so repeated
generations don't read as robotic/copy-pasted, per the "evitar estructuras
repetitivas" requirement. Nothing here ever produces a "publish" action —
drafts are text the user copies and posts manually from Reddit.
"""

import random

from app.models.enums import DraftVariant

_EDUCATIONAL_ES = [
    "Por lo que cuentas, el cuello de botella suele estar en priorizar a quién contactar primero, no en encontrar leads. "
    "Una forma que funciona bien: apunta cada negocio potencial con 2-3 señales de necesidad (web anticuada, sin reseñas "
    "recientes, sin presencia en Maps) y ordénalos por esas señales antes de escribir el primer mensaje. Te ahorra mucho "
    "tiempo frente a contactar en el orden en que los vas encontrando.",
    "Algo que me ha servido en casos parecidos: separar la búsqueda de la cualificación. Primero saca una lista amplia "
    "(Maps, directorios locales, lo que uses), y en un segundo paso descarta rápido los que no tienen ninguna señal de "
    "necesidad real. Así no pierdes horas investigando negocios que probablemente no te van a responder.",
]

_EDUCATIONAL_EN = [
    "From what you're describing, the bottleneck is usually prioritization, not lead volume. What's worked for me: tag "
    "each prospect with 2-3 concrete need signals (outdated website, no recent reviews, weak Maps presence) and sort by "
    "that before writing a single message. Saves a lot of time versus contacting people in the order you found them.",
    "One thing that helped in a similar situation: split sourcing from qualifying. Pull a broad list first, then do a "
    "fast second pass to drop anyone without a real need signal. You end up spending your outreach time on the "
    "businesses actually likely to respond.",
]

_SOFT_ES = [
    "Coincido con lo anterior. De hecho llevo un tiempo construyendo una herramienta justo para esta parte — priorizar "
    "qué negocios contactar según señales reales en vez de ir a ciegas. Si te sirve, luego puedo contarte cómo lo "
    "estructuro, sin rollo comercial.",
    "Esto lo he vivido bastante. Estoy desarrollando algo (Radarin) que ayuda precisamente a ordenar estas oportunidades "
    "por prioridad, así que llevo un tiempo pensando en el problema. Si te interesa el enfoque te cuento cómo lo armo.",
]

_SOFT_EN = [
    "Agree with the above. I've actually been building a tool for exactly this part — prioritizing which businesses to "
    "contact based on real signals instead of going in blind. Happy to share how I approach it if useful, no pitch.",
    "I've run into this a lot. I'm building something (Radarin) focused on ranking these opportunities by priority, so "
    "I've spent a while thinking about this exact problem — happy to share the approach if it's helpful.",
]

_DIRECT_ES = [
    "Soy el creador de Radarin, una herramienta pensada exactamente para esto: encontrar negocios locales con potencial, "
    "detectar señales de necesidad y priorizar a quién contactar. Lo digo de forma transparente porque preguntabas por "
    "herramientas — no es una recomendación independiente, es la mía. Si quieres la miro contigo sin compromiso.",
]

_DIRECT_EN = [
    "I'm the creator of Radarin, a tool built for exactly this — finding local businesses with potential, spotting need "
    "signals, and prioritizing who to contact. Saying this openly since you asked for tool recommendations — it's not "
    "an independent suggestion, it's mine. Happy to walk you through it, no pressure.",
]


def _pick(options_es: list[str], options_en: list[str], language: str) -> str:
    pool = options_es if language.startswith("es") else options_en
    return random.choice(pool)


def generate_drafts(
    *, language: str, tool_request: bool, promotion_risk: str, topic_name: str
) -> dict[DraftVariant, str]:
    drafts: dict[DraftVariant, str] = {
        DraftVariant.educational: _pick(_EDUCATIONAL_ES, _EDUCATIONAL_EN, language),
        DraftVariant.soft_mention: _pick(_SOFT_ES, _SOFT_EN, language),
    }
    if tool_request:
        drafts[DraftVariant.direct_transparent] = _pick(_DIRECT_ES, _DIRECT_EN, language)
    return drafts


def recommended_variant(*, tool_request: bool, promotion_risk: str) -> DraftVariant:
    if tool_request and promotion_risk == "low":
        return DraftVariant.direct_transparent
    if promotion_risk == "high":
        return DraftVariant.educational
    return DraftVariant.soft_mention
