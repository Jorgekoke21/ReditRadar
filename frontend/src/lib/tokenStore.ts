/**
 * Bridges the currently-active bearer token (dev token OR live Supabase
 * session access_token, kept fresh by supabase-js's autoRefreshToken) to
 * lib/api.ts without a circular import between it and lib/auth.tsx. Auth.tsx
 * is the only writer; api.ts is the only reader (aside from a couple of
 * direct-fetch test helpers).
 */

let activeToken: string | null = null;

export function setActiveToken(token: string | null) {
  activeToken = token;
}

export function getActiveToken(): string | null {
  return activeToken;
}
