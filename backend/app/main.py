from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import alerts, auth, communities, conversations, dashboard, health, history, jobs, reddit, settings_api, topics
from app.config import get_settings

settings = get_settings()
settings.validate_reddit_startup()

# Hard startup guard (spec: "Si APP_ENV=production y AUTH_MODE=development, el
# backend debe negarse a arrancar"). The insecure dev-login path must never be
# reachable in a deployed environment — refusing to boot is the only way to
# guarantee that, since a silently-ignored misconfiguration is exactly the
# failure mode this exists to prevent. Checked at import time, not lazily on
# first request, so a misconfigured deploy fails in CI/at container start
# rather than serving traffic first.
if settings.app_env == "production" and settings.auth_mode == "development":
    raise RuntimeError(
        "Refusing to start: APP_ENV=production with AUTH_MODE=development. "
        "The development auth bypass (dev-login, unsigned tokens) must never run in "
        "production. Set AUTH_MODE=supabase and configure SUPABASE_JWT_SECRET, or set "
        "APP_ENV to something other than 'production' for a genuine local/staging deploy."
    )
if settings.auth_mode == "supabase" and not settings.supabase_jwt_secret:
    raise RuntimeError(
        "Refusing to start: AUTH_MODE=supabase but SUPABASE_JWT_SECRET is not set. "
        "This must be an explicit, actionable configuration error, not a silent fallback "
        "to the insecure development login."
    )

app = FastAPI(title="Radar de Conversaciones API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.app_url, "http://localhost:5180", "http://127.0.0.1:5180"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for router in (
    health.router,
    auth.router,
    dashboard.router,
    conversations.router,
    communities.router,
    topics.router,
    alerts.router,
    jobs.router,
    settings_api.router,
    reddit.router,
    history.router,
):
    app.include_router(router)
