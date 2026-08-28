import { test, expect } from "@playwright/test";
import { loginAsNewAccount } from "./helpers";

/**
 * Drives the Connect/Disconnect UI and the /reddit/callback page.
 *
 * The real stack runs with REDDIT_API_ENABLED=false and this phase must not
 * change that, so the two Reddit endpoints are served here by a controlled
 * route interceptor standing in for an enabled backend. Reddit itself is
 * never contacted: the "authorize" redirect is intercepted and answered with
 * a redirect straight back to the app's own callback route, exactly as
 * Reddit would do after the user approves.
 */

const AUTHORIZE_HOST = "https://www.reddit.com/api/v1/authorize**";
const STATE = "e2e-oauth-state-value";

type Options = { connected?: boolean; callbackStatus?: number; callbackBody?: unknown };

async function stubRedditBackend(page: import("@playwright/test").Page, opts: Options = {}) {
  let connected = opts.connected ?? false;

  // Present the integration as enabled so the button renders, while the real
  // backend flag stays false.
  await page.route("**/api/settings/integrations", async (route) => {
    const response = await route.fetch();
    const body = await response.json();
    await route.fulfill({
      json: { ...body, reddit_api_enabled: true, reddit_connected: connected },
    });
  });

  await page.route("**/api/reddit/connect", async (route) => {
    await route.fulfill({
      json: {
        authorize_url: `https://www.reddit.com/api/v1/authorize?client_id=fake&state=${STATE}`,
        state: STATE,
      },
    });
  });

  // Stand in for Reddit's consent screen: bounce straight back to the app's
  // callback with the code/state Reddit would have appended.
  await page.route(AUTHORIZE_HOST, async (route) => {
    const url = new URL(route.request().url());
    const state = url.searchParams.get("state") ?? "";
    await route.fulfill({
      status: 302,
      headers: { location: `http://localhost:5180/reddit/callback?code=e2e-code&state=${state}` },
      body: "",
    });
  });

  await page.route("**/api/reddit/callback", async (route) => {
    const status = opts.callbackStatus ?? 200;
    if (status === 200) connected = true;
    await route.fulfill({
      status,
      json: opts.callbackBody ?? (status === 200 ? { connected: true, scopes: "identity read" } : { detail: "Invalid OAuth state" }),
    });
  });

  return { getConnected: () => connected };
}

test("connect Reddit: Settings -> authorize -> callback -> back to Settings as connected", async ({ page }) => {
  await loginAsNewAccount(page, "reddit-oauth-connect");
  await stubRedditBackend(page);

  await page.goto("/settings", { waitUntil: "networkidle" });
  await expect(page.getByText("Reddit no conectado")).toBeVisible();

  await page.getByTestId("reddit-connect").click();

  // Lands on the callback page, exchanges, then returns to Settings itself.
  await expect(page).toHaveURL(/\/settings$/, { timeout: 15000 });
  await expect(page.getByText("Reddit conectado")).toBeVisible();
  await expect(page.getByTestId("reddit-disconnect")).toBeVisible();
});

test("disconnect Reddit returns the UI to the not-connected state", async ({ page }) => {
  await loginAsNewAccount(page, "reddit-oauth-disconnect");
  await stubRedditBackend(page, { connected: true });

  let deleteCalled = false;
  await page.route("**/api/reddit/connection", async (route) => {
    deleteCalled = route.request().method() === "DELETE";
    await route.fulfill({ status: 204, body: "" });
  });

  await page.goto("/settings", { waitUntil: "networkidle" });
  await expect(page.getByText("Reddit conectado")).toBeVisible();

  await page.getByTestId("reddit-disconnect").click();
  await expect(page.getByRole("status")).toContainText("Reddit desconectado");
  expect(deleteCalled).toBe(true);
});

test("callback page reports a cancelled authorization instead of a silent failure", async ({ page }) => {
  await loginAsNewAccount(page, "reddit-oauth-cancelled");
  await stubRedditBackend(page);

  await page.goto("/reddit/callback?error=access_denied", { waitUntil: "networkidle" });

  await expect(page.getByText(/Conexión cancelada/)).toBeVisible();
  await expect(page.getByRole("link", { name: "Volver a Configuración" })).toBeVisible();
});

test("callback page reports a rejected state instead of claiming success", async ({ page }) => {
  await loginAsNewAccount(page, "reddit-oauth-badstate");
  await stubRedditBackend(page, { callbackStatus: 400, callbackBody: { detail: "Invalid OAuth state" } });

  await page.goto("/reddit/callback?code=e2e-code&state=tampered", { waitUntil: "networkidle" });

  await expect(page.getByText(/State inválido/)).toBeVisible();
  await expect(page).not.toHaveURL(/\/settings$/);
});

test("connect button is not offered while the Reddit integration is disabled", async ({ page }) => {
  // No stub here: this asserts the real backend's REDDIT_API_ENABLED=false.
  await loginAsNewAccount(page, "reddit-oauth-disabled");
  await page.goto("/settings", { waitUntil: "networkidle" });

  await expect(page.getByText("Desactivada")).toBeVisible();
  await expect(page.getByTestId("reddit-connect")).toHaveCount(0);
  await expect(page.getByTestId("reddit-disconnect")).toHaveCount(0);
});
