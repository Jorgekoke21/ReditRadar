from app.services.analyzer import RulesConversationAnalyzer, TopicForMatching
from app.services.text_utils import normalize


def test_normalize_strips_accents_and_lowercases():
    assert normalize("Página de Prioridad Máxima") == normalize("pagina de prioridad maxima")


async def test_rules_analyzer_matches_keyword_despite_accent_mismatch():
    from app.services.analyzer import ConversationForAnalysis

    topics = [
        TopicForMatching(
            id="t1", name="Negocios sin web", description="", keywords=["sin pagina web"], exclusions=[]
        )
    ]
    convo = ConversationForAnalysis(
        subreddit="web_design", title="Negocios sin página web en mi ciudad", body="", language="es", num_comments=0
    )
    result = await RulesConversationAnalyzer().analyze(convo, topics)
    assert "t1" in result.topic_ids
