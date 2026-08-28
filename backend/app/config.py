from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "local"
    app_url: str = "http://localhost:5180"
    api_url: str = "http://localhost:8010"

    # Legacy single URL, kept as the fallback for all three roles below so the
    # SQLite-based test suite (which has no concept of Postgres roles) keeps
    # working unchanged. Real Postgres deployments should set the three
    # role-specific URLs explicitly — see docs/rls.md.
    database_url: str = "sqlite+aiosqlite:///./radarin_radar.db"
    database_migration_url: str = ""  # owner role (radarin) — Alembic only, never the running app
    database_app_url: str = ""  # radar_app — the FastAPI request/response cycle
    database_worker_url: str = ""  # radar_worker — the background worker (needs to enumerate accounts)
    radar_app_db_password: str = "radar_app_dev_only_change_me"
    radar_worker_db_password: str = "radar_worker_dev_only_change_me"

    def resolved_migration_url(self) -> str:
        return self.database_migration_url or self.database_url

    def resolved_app_url(self) -> str:
        return self.database_app_url or self.database_url

    def resolved_worker_url(self) -> str:
        return self.database_worker_url or self.database_url

    # --- Auth --------------------------------------------------------------
    # "supabase": real Supabase Auth JWTs only, dev tokens always rejected.
    # "development": also accepts opaque dev:<uuid> tokens from /api/auth/dev-login.
    # Enforced at startup: app_env=production + auth_mode=development refuses to boot.
    auth_mode: str = "development"

    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_role_key: str = ""
    supabase_jwt_secret: str = ""

    @property
    def supabase_issuer(self) -> str:
        return f"{self.supabase_url.rstrip('/')}/auth/v1" if self.supabase_url else ""

    @property
    def is_development_auth_allowed(self) -> bool:
        return self.auth_mode == "development"

    # Reddit API — hard gate. No client code may call Reddit unless this is True.
    reddit_api_enabled: bool = False
    reddit_client_id: str = ""
    reddit_client_secret: str = ""
    reddit_redirect_uri: str = "http://localhost:8010/api/reddit/callback"
    reddit_user_agent: str = "radarin-conversation-radar/0.1 (internal tool)"
    reddit_token_encryption_key: str = ""
    reddit_fetch_limit: int = 50
    reddit_max_pages_per_community: int = 3
    reddit_max_retries: int = 4
    reddit_default_max_age_hours: int = 72
    job_admin_emails: str = ""

    # AI
    ai_analysis_enabled: bool = False
    ai_provider: str = ""
    ai_model: str = ""
    ai_api_key: str = ""

    # Email
    email_provider: str = "console"
    email_from: str = "radar@radarin.local"
    email_to: str = "you@example.com"
    smtp_host: str = ""
    smtp_port: str = "587"
    smtp_user: str = ""
    smtp_password: str = ""
    resend_api_key: str = ""

    # Retention / misc
    app_timezone: str = "Europe/Madrid"
    raw_content_retention_hours: int = 48

    @property
    def reddit_encryption_key_is_safe(self) -> bool:
        return bool(self.reddit_token_encryption_key) and self.reddit_token_encryption_key != "dev-only-insecure-key-change-me"

    def validate_reddit_startup(self) -> None:
        if self.reddit_api_enabled and not self.reddit_encryption_key_is_safe:
            raise RuntimeError(
                "Refusing to start Reddit integration: REDDIT_API_ENABLED=true requires a non-empty REDDIT_TOKEN_ENCRYPTION_KEY that is not the development fallback."
            )


@lru_cache
def get_settings() -> Settings:
    return Settings()
