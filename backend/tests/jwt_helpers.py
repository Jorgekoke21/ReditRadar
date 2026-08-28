"""Local JWT test provider — mints tokens with EXACTLY the contract
verify_supabase_jwt() checks (HS256, aud=authenticated, iss={SUPABASE_URL}/auth/v1,
exp, sub), signed with the same SUPABASE_JWT_SECRET the test settings use.
This is "Probado con proveedor JWT local" per docs/acceptance-audit.md — it
exercises the real signature/issuer/audience/expiry verification code, just
without a real Supabase project's servers involved. See docs/authentication.md.
"""

import time
import uuid

from jose import jwt

TEST_JWT_SECRET = "local-only-test-jwt-secret-do-not-use-in-production-1234567890"
TEST_SUPABASE_URL = "https://local-test-project.supabase.co"
TEST_ISSUER = f"{TEST_SUPABASE_URL}/auth/v1"


def make_supabase_jwt(
    *,
    sub: str | None = None,
    email: str = "jwt-test@example.com",
    issuer: str | None = TEST_ISSUER,
    audience: str = "authenticated",
    expires_in: int = 3600,
    secret: str = TEST_JWT_SECRET,
    algorithm: str = "HS256",
    include_sub: bool = True,
) -> str:
    now = int(time.time())
    payload = {
        "aud": audience,
        "exp": now + expires_in,
        "iat": now,
        "email": email,
        "role": "authenticated",
    }
    if issuer is not None:
        payload["iss"] = issuer
    if include_sub:
        payload["sub"] = sub or str(uuid.uuid4())
    return jwt.encode(payload, secret, algorithm=algorithm)
