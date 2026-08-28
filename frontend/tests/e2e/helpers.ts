import crypto from "node:crypto";
import { Page, expect } from "@playwright/test";

export const API_URL = process.env.PLAYWRIGHT_API_URL || "http://localhost:8010";

/** Must match backend/tests/jwt_helpers.py exactly (same fixture secret,
 * same claim shape) — these mint tokens that verify_supabase_jwt() accepts
 * for real, exercising real signature/issuer/audience/expiry checks without
 * a real Supabase project's servers involved. See docs/authentication.md. */
const TEST_JWT_SECRET = "local-only-test-jwt-secret-do-not-use-in-production-1234567890";
const TEST_SUPABASE_URL = "https://local-test-project.supabase.co";
const TEST_ISSUER = `${TEST_SUPABASE_URL}/auth/v1`;
/** supabase-js derives its localStorage key as `sb-${hostname.split('.')[0]}-auth-token`. */
export const SUPABASE_STORAGE_KEY = "sb-local-test-project-auth-token";

function base64url(input: Buffer | string): string {
  return Buffer.from(input).toString("base64").replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

export function mintTestSupabaseJwt(
  opts: { sub?: string; email?: string; expiresInSeconds?: number; issuer?: string | null } = {}
): string {
  const sub = opts.sub ?? crypto.randomUUID();
  const email = opts.email ?? "e2e-jwt@example.com";
  const expiresIn = opts.expiresInSeconds ?? 3600;
  const now = Math.floor(Date.now() / 1000);
  const header = { alg: "HS256", typ: "JWT" };
  const payload: Record<string, unknown> = {
    aud: "authenticated",
    exp: now + expiresIn,
    iat: now,
    email,
    role: "authenticated",
    sub,
  };
  if (opts.issuer !== null) payload.iss = opts.issuer ?? TEST_ISSUER;
  const headerB64 = base64url(JSON.stringify(header));
  const payloadB64 = base64url(JSON.stringify(payload));
  const signingInput = `${headerB64}.${payloadB64}`;
  const signature = crypto.createHmac("sha256", TEST_JWT_SECRET).update(signingInput).digest();
  return `${signingInput}.${base64url(signature)}`;
}

/** Seeds a genuine-shaped Supabase session (matching what supabase-js itself
 * would have written after a real magic-link login) directly into the
 * page's localStorage, signed with the same fixture secret the backend
 * trusts — a "sesión Supabase simulada controlada" per the audit spec. Must
 * be called BEFORE the first page.goto() so AuthProvider's bootstrap effect
 * finds it on first load. */
export async function seedSimulatedSupabaseSession(
  page: Page,
  email: string,
  opts: { sub?: string; expiresInSeconds?: number } = {}
) {
  const sub = opts.sub ?? crypto.randomUUID();
  const token = mintTestSupabaseJwt({ sub, email, expiresInSeconds: opts.expiresInSeconds ?? 3600 });
  const now = Math.floor(Date.now() / 1000);
  const session = {
    access_token: token,
    token_type: "bearer",
    expires_in: opts.expiresInSeconds ?? 3600,
    expires_at: now + (opts.expiresInSeconds ?? 3600),
    refresh_token: "e2e-simulated-refresh-token",
    user: {
      id: sub,
      aud: "authenticated",
      role: "authenticated",
      email,
      email_confirmed_at: new Date().toISOString(),
      app_metadata: {},
      user_metadata: {},
      created_at: new Date().toISOString(),
    },
  };
  await page.addInitScript(
    ({ key, value }) => window.localStorage.setItem(key, value),
    { key: SUPABASE_STORAGE_KEY, value: JSON.stringify(session) }
  );
  return { sub, token };
}

/**
 * Logs a page into a fresh, isolated account (unique email) via the real
 * /api/auth/dev-login endpoint used by the actual Login page, then lands on
 * /today. Each call creates a brand new account, so tests never see another
 * test's data.
 */
export async function loginAsNewAccount(page: Page, label: string): Promise<{ email: string; accountId: string }> {
  const email = `e2e-${label}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}@example.com`;
  const res = await fetch(`${API_URL}/api/auth/dev-login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email }),
  });
  const data = await res.json();
  await page.goto("/login");
  await page.evaluate((token) => localStorage.setItem("radarin_radar_token", token), data.access_token);
  await page.goto("/today", { waitUntil: "networkidle" });
  await expect(page.getByRole("heading", { name: "Hoy" })).toBeVisible();
  return { email, accountId: data.profile.account_id };
}

/** Logs in through the REAL dev-login form (expands the "modo desarrollo"
 * disclosure, fills email, clicks submit) instead of injecting a token —
 * used by the tests that must prove the login UI itself is wired up, not
 * just the API it calls. Local test env always has a (fake) Supabase project
 * configured, so: the dev form starts collapsed behind a <details> toggle,
 * and shares its email field with the magic-link form above it (single
 * email input, pick which submit button to press). */
export async function loginViaForm(page: Page, email: string) {
  await page.goto("/login");
  await page.getByPlaceholder("tu@email.com").fill(email);
  const toggle = page.getByText("Usar acceso de desarrollo en su lugar");
  if (await toggle.isVisible().catch(() => false)) {
    await toggle.click();
  }
  await page.getByRole("button", { name: "Continuar en modo desarrollo" }).click();
  await expect(page).toHaveURL(/\/today$/, { timeout: 10000 });
}

export async function apiToken(email: string): Promise<string> {
  const res = await fetch(`${API_URL}/api/auth/dev-login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email }),
  });
  return (await res.json()).access_token;
}

export function collectConsoleErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on("console", (msg) => {
    if (msg.type() === "error") errors.push(msg.text());
  });
  page.on("pageerror", (err) => errors.push(`pageerror: ${err.message}`));
  return errors;
}

export async function createManualConversation(
  page: Page,
  token: string,
  overrides: Partial<{
    url: string;
    subreddit: string;
    title: string;
    body: string;
    num_comments: number;
    language: string;
    published_at: string;
  }> = {}
) {
  const res = await fetch(`${API_URL}/api/conversations/manual`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: JSON.stringify({
      subreddit: "agency",
      title: "Necesito ayuda para priorizar leads de mi agencia",
      body: "Tengo muchos leads y no se por cual empezar, alguna herramienta que recomendeis para priorizar leads?",
      num_comments: 1,
      language: "es",
      published_at: new Date().toISOString(),
      ...overrides,
    }),
  });
  if (!res.ok) throw new Error(`createManualConversation failed: ${res.status} ${await res.text()}`);
  return res.json();
}

export async function createTopic(page: Page, token: string, keywords: string[]) {
  const res = await fetch(`${API_URL}/api/topics`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: JSON.stringify({
      name: "Tema E2E",
      description: "tema de prueba",
      keywords,
      exclusions: [],
      priority: "high",
    }),
  });
  if (!res.ok) throw new Error(`createTopic failed: ${res.status} ${await res.text()}`);
  return res.json();
}
