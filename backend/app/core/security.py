"""Auth (spec section 5, hardened in the auth/RLS phase — see docs/authentication.md and docs/rls.md).

Two auth modes, controlled by AUTH_MODE:

- "supabase" (required whenever APP_ENV=production — enforced in main.py at
  import time, the process refuses to start otherwise): the frontend
  authenticates against Supabase Auth (magic link) and sends the resulting
  Supabase JWT as a Bearer token. verify_supabase_jwt validates the
  signature (HS256 / SUPABASE_JWT_SECRET), issuer, audience and expiry, and
  requires a `sub` claim. Dev tokens are unconditionally rejected in this mode.

- "development": ALSO accepts an opaque `dev:<profile_id>` token issued by
  POST /api/auth/dev-login, with no signature at all — this exists purely so
  Demo/Manual mode can be exercised with zero external services. It must
  never be reachable in a deployed environment (see the startup guard in
  main.py and the "modo autenticación de desarrollo" banner the frontend
  shows whenever this mode is active).

Row-level security context: every account-owned table's RLS policy checks
`current_setting('app.account_id')`, EXCEPT `profiles`, which checks
`current_setting('app.user_id')` instead — because resolving *which* account
a freshly-authenticated user belongs to requires reading their profile row
first, before account_id is known. So the flow for every request is:

  1. Verify the token → get user_id (Supabase `sub`, or the profile id from
     a dev token).
  2. remember_rls_context(session, user_id=...) — lets the profiles-table
     policy allow this one self-lookup, and keeps re-applying it to every
     later transaction on this session (see app/db.py for why that matters).
  3. Look up (or provision) the profile by id. Provisioning also sets
     account_id to the newly generated account id *before* inserting, so
     the INSERT's WITH CHECK passes (see _provision_new_account_and_profile).
  4. remember_rls_context(session, account_id=...) — scopes every
     subsequent query in this request to that account.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.db import get_db, remember_rls_context
from app.models.account import Account, Profile

_bearer = HTTPBearer(auto_error=False)

# Deterministic namespace used ONLY by the development auth path to derive a
# stable user_id from an email address, so dev-login never needs to look
# profiles up "by email" (which the profiles table's self-lookup RLS policy
# can't support — it only ever allows `id = current_setting('app.user_id')`,
# and until we resolve the profile we don't have an id to compare against
# unless, like Supabase's real `sub` claim, we already know it upfront).
_DEV_NAMESPACE = uuid.UUID("6f6a9a4e-6b8b-4f0e-9a2a-4a2f9b7a5c11")


def dev_user_id_for_email(email: str) -> uuid.UUID:
    return uuid.uuid5(_DEV_NAMESPACE, email.strip().lower())


@dataclass(frozen=True)
class AuthenticatedPrincipal:
    """What every authenticated request resolves to. Deliberately does not
    carry the raw JWT or any secret — only what routers need."""

    user_id: uuid.UUID
    account_id: uuid.UUID
    email: str | None = None


async def verify_supabase_jwt(token: str, settings: Settings) -> dict:
    """Validates signature (HS256/SUPABASE_JWT_SECRET), audience, expiry, and
    issuer (only when SUPABASE_URL is configured — a token minted by a local
    JWT test provider that doesn't claim to be a specific Supabase project
    still has its signature/audience/expiry checked). Raises HTTPException(401)
    on any failure. Never logs or returns the raw token."""
    if not settings.supabase_jwt_secret:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Supabase auth is not configured (SUPABASE_JWT_SECRET unset)")
    try:
        options = {"require_sub": True, "require_exp": True}
        payload = jwt.decode(
            token,
            settings.supabase_jwt_secret,
            algorithms=["HS256"],
            audience="authenticated",
            options=options,
        )
    except JWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid, expired, or malformed token")

    if settings.supabase_issuer and payload.get("iss") != settings.supabase_issuer:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token issuer does not match this Supabase project")

    if not payload.get("sub"):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token missing required 'sub' claim")

    return payload


async def _provision_new_account_and_profile(session: AsyncSession, *, user_id: uuid.UUID, email: str) -> Profile:
    """Idempotent-by-construction: the caller only reaches here after a
    lookup by id found nothing, and profiles.id is the Supabase user's own
    UUID (never re-generated), so a retry/race that hits the unique
    constraint on profiles.id or accounts.id fails loudly instead of
    silently creating a duplicate — see test_provisioning_race_is_safe."""
    new_account_id = uuid.uuid4()
    # The accounts RLS policy is `id = current_setting('app.account_id')` —
    # set it to the id we're about to insert so the INSERT's WITH CHECK passes.
    await remember_rls_context(session, account_id=str(new_account_id))

    account = Account(id=new_account_id, name="My workspace")
    session.add(account)
    await session.flush()

    profile = Profile(id=user_id, account_id=new_account_id, email=email, display_name=email.split("@")[0] if email else "")
    session.add(profile)
    await session.commit()
    await session.refresh(profile)
    return profile


async def _resolve_profile(session: AsyncSession, *, user_id: uuid.UUID, email: str) -> Profile:
    """Look up a profile strictly by its Supabase user id (never by email —
    email is not a stable identifier and must not be used to merge accounts).
    Requires app.user_id to already be set on this session (remember_rls_context)."""
    profile = (await session.execute(select(Profile).where(Profile.id == user_id))).scalars().first()
    if profile is not None:
        return profile
    return await _provision_new_account_and_profile(session, user_id=user_id, email=email)


async def get_current_principal(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> AuthenticatedPrincipal:
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")
    token = credentials.credentials

    if token.startswith("dev:"):
        if not settings.is_development_auth_allowed:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Development auth tokens are disabled (AUTH_MODE=supabase)")
        try:
            user_id = uuid.UUID(token.removeprefix("dev:"))
        except ValueError:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid dev token")
        await remember_rls_context(session, user_id=str(user_id))
        profile = (await session.execute(select(Profile).where(Profile.id == user_id))).scalars().first()
        if profile is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Unknown dev session")
        await remember_rls_context(session, account_id=str(profile.account_id))
        return AuthenticatedPrincipal(user_id=profile.id, account_id=profile.account_id, email=profile.email)

    payload = await verify_supabase_jwt(token, settings)
    user_id = uuid.UUID(payload["sub"])
    email = payload.get("email") or ""

    await remember_rls_context(session, user_id=str(user_id))
    profile = await _resolve_profile(session, user_id=user_id, email=email)
    await remember_rls_context(session, account_id=str(profile.account_id))

    return AuthenticatedPrincipal(user_id=profile.id, account_id=profile.account_id, email=profile.email)


async def get_current_account_id(principal: AuthenticatedPrincipal = Depends(get_current_principal)) -> uuid.UUID:
    return principal.account_id


async def get_current_admin_principal(
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    settings: Settings = Depends(get_settings),
) -> AuthenticatedPrincipal:
    """Administrative gate for diagnostics and manual job execution.

    Production uses an explicit email allowlist. Local development keeps the
    existing single-user workflow available only while development auth is
    enabled; production cannot accidentally inherit that behavior.
    """
    allowlist = {email.strip().lower() for email in settings.job_admin_emails.split(",") if email.strip()}
    if allowlist and (principal.email or "").strip().lower() in allowlist:
        return principal
    if not allowlist and settings.app_env != "production" and settings.auth_mode == "development":
        return principal
    raise HTTPException(status.HTTP_403_FORBIDDEN, "Administrator access is required for diagnostics and jobs")


async def get_current_profile(
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db),
) -> Profile:
    """Back-compat helper for the couple of call sites that want the full
    Profile row rather than just the principal (e.g. /api/auth/me)."""
    profile = (await session.execute(select(Profile).where(Profile.id == principal.user_id))).scalars().first()
    if profile is None:  # pragma: no cover - can't happen, get_current_principal already provisioned it
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Profile not found")
    return profile


async def issue_dev_login(session: AsyncSession, settings: Settings, email: str) -> Profile:
    """The whole implementation of POST /api/auth/dev-login. Kept here
    rather than in the router so it can share _resolve_profile/remember_rls_context
    with the real Supabase path — same idempotent-provisioning code, same
    RLS-context bootstrapping, the only difference is where user_id comes
    from (deterministic hash of the email vs. a verified JWT `sub`)."""
    if not settings.is_development_auth_allowed:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Development auth is disabled (AUTH_MODE=supabase)")

    user_id = dev_user_id_for_email(email)
    await remember_rls_context(session, user_id=str(user_id))
    profile = await _resolve_profile(session, user_id=user_id, email=email)
    await remember_rls_context(session, account_id=str(profile.account_id))
    return profile
