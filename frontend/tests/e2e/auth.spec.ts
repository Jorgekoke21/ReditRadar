import { test, expect } from "@playwright/test";
import { loginViaForm, mintTestSupabaseJwt, seedSimulatedSupabaseSession } from "./helpers";

test("requesting a magic link shows the sent confirmation", async ({ page }) => {
  // supabase-js's signInWithOtp() posts here; no real Supabase project
  // exists in this environment, so the network call is intercepted the
  // same way it would be answered by a real one (audit spec: "mostrar
  // confirmación de enlace enviado").
  await page.route("**/auth/v1/otp*", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: "{}" })
  );
  await page.goto("/login");
  await page.getByPlaceholder("tu@email.com").fill(`e2e-magic-${Date.now()}@example.com`);
  await page.getByRole("button", { name: "Enviar enlace mágico" }).click();
  await expect(page.getByText("Enlace enviado. Revisa tu correo y haz clic para entrar.")).toBeVisible();
});

test("a genuine (locally-signed) Supabase session recovered from storage logs the user in", async ({ page }) => {
  // Seeds a session shaped exactly like what supabase-js itself persists
  // after a real magic-link login, signed with the same secret the backend
  // trusts. AuthProvider's bootstrap calls supabase.auth.getSession(),
  // which recovers this from localStorage with no network call needed
  // (audit spec: "entrar con sesión Supabase simulada controlada").
  const email = `e2e-supabase-session-${Date.now()}@example.com`;
  await seedSimulatedSupabaseSession(page, email);
  await page.goto("/today");
  await expect(page.getByRole("heading", { name: "Hoy" })).toBeVisible();
  await expect(page.getByText(email)).toBeVisible();
});

test("an expired (but validly signed) session no longer grants access", async ({ page }) => {
  const email = `e2e-expiry-${Date.now()}@example.com`;
  await loginViaForm(page, email);

  const expiredToken = mintTestSupabaseJwt({ expiresInSeconds: -3600 });
  await page.evaluate((token) => localStorage.setItem("radarin_radar_token", token), expiredToken);
  await page.goto("/today");

  await expect(page).toHaveURL(/\/login/);
});

test("logout clears the session and further protected access requires login again", async ({ page }) => {
  const email = `e2e-logout-${Date.now()}@example.com`;
  await loginViaForm(page, email);

  await page.getByRole("button", { name: "Cerrar sesión" }).click();
  await expect(page).toHaveURL(/\/login/);

  await page.goto("/conversations");
  await expect(page).toHaveURL(/\/login/);
});

test("dev login is not offered when the backend reports AUTH_MODE=supabase", async ({ page }) => {
  await page.route("**/api/auth/config", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        auth_mode: "supabase",
        dev_login_available: false,
        supabase_url: "https://local-test-project.supabase.co",
        supabase_anon_key: "local-test-anon-key",
      }),
    })
  );
  await page.goto("/login");

  await expect(page.getByPlaceholder("tu@email.com")).toBeVisible();
  await expect(page.getByRole("button", { name: "Continuar en modo desarrollo" })).toHaveCount(0);
  await expect(page.getByText("Usar acceso de desarrollo en su lugar")).toHaveCount(0);
  await expect(page.getByText("Modo autenticación de desarrollo")).toHaveCount(0);
});

test("auth callback surfaces an invalid/expired-link error reported by Supabase's own redirect", async ({ page }) => {
  await page.goto(
    "/auth/callback?error=access_denied&error_description=Email%20link%20is%20invalid%20or%20has%20expired"
  );
  await expect(page.getByText(/Enlace inválido o expirado/)).toBeVisible();
});
