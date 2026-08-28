from app.config import get_settings
from app.services.analyzer import RulesConversationAnalyzer, get_analyzer
from app.services.crypto import decrypt_token, encrypt_token


def test_get_analyzer_falls_back_to_rules_when_ai_disabled():
    settings = get_settings()
    assert settings.ai_analysis_enabled is False
    analyzer = get_analyzer(settings)
    assert isinstance(analyzer, RulesConversationAnalyzer)


def test_get_analyzer_falls_back_to_rules_when_enabled_but_no_api_key():
    settings = get_settings()
    settings_copy = settings.model_copy(update={"ai_analysis_enabled": True, "ai_provider": "openai", "ai_api_key": ""})
    analyzer = get_analyzer(settings_copy)
    assert isinstance(analyzer, RulesConversationAnalyzer)


def test_token_encryption_roundtrip_never_stores_plaintext():
    settings = get_settings()
    plaintext = "super-secret-reddit-refresh-token"
    ciphertext = encrypt_token(settings, plaintext)
    assert plaintext not in ciphertext
    assert decrypt_token(settings, ciphertext) == plaintext


async def test_dev_login_response_never_includes_a_reddit_or_ai_secret(client):
    resp = await client.post("/api/auth/dev-login", json={"email": "secrets-check@example.com"})
    body = resp.json()
    serialized = str(body).lower()
    assert "client_secret" not in serialized
    assert "api_key" not in serialized
    assert "refresh_token" not in serialized


async def test_integrations_status_never_includes_raw_tokens(client, auth_headers):
    resp = await client.get("/api/settings/integrations", headers=auth_headers)
    serialized = str(resp.json()).lower()
    assert "token" not in serialized
    assert "secret" not in serialized
    assert "api_key" not in serialized
