from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.core.security import get_current_profile, issue_dev_login
from app.db import get_db
from app.models.account import Profile
from app.schemas import AuthConfigOut, DevLoginRequest, ProfileOut, SessionOut

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.get("/config", response_model=AuthConfigOut)
async def auth_config(settings: Settings = Depends(get_settings)):
    """Public — no auth required. The login page calls this first to decide
    whether to render the real Supabase magic-link form, the dev-login form,
    or a 'Supabase auth is not configured' error state."""
    return AuthConfigOut(
        auth_mode=settings.auth_mode,
        dev_login_available=settings.is_development_auth_allowed,
        supabase_url=settings.supabase_url,
        supabase_anon_key=settings.supabase_anon_key,
    )


@router.post("/dev-login", response_model=SessionOut)
async def dev_login(
    body: DevLoginRequest,
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    """Only available when AUTH_MODE=development. Lets the app be used
    end-to-end (Demo + Manual mode) with zero external services. Issues an
    opaque `dev:<user_id>` token — never a real JWT, never accepted when
    AUTH_MODE=supabase (see core/security.py::get_current_principal)."""
    profile = await issue_dev_login(session, settings, body.email)
    return SessionOut(access_token=f"dev:{profile.id}", profile=ProfileOut.model_validate(profile))


@router.get("/me", response_model=ProfileOut)
async def me(profile: Profile = Depends(get_current_profile)):
    return ProfileOut.model_validate(profile)
