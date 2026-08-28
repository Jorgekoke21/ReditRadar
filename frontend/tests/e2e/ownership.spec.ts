import { test, expect } from "@playwright/test";
import { loginAsNewAccount, apiToken, createManualConversation, API_URL } from "./helpers";

/**
 * Reproducible two-account ownership test, run in a real browser session
 * (not just an API client). Account B must not be able to read, list, or
 * edit anything created by Account A — enforced entirely by
 * get_current_account_id + explicit account_id filtering in every backend
 * router (see docs/acceptance-audit.md — RLS does NOT provide this
 * protection for the app's own DB role, only application code does).
 */
test("account B cannot read, list, or edit account A's conversation via the API", async ({ page }) => {
  const { email: emailA } = await loginAsNewAccount(page, "owner-a");
  const tokenA = await apiToken(emailA);
  const convo = await createManualConversation(page, tokenA, {
    title: "Private conversation belonging only to account A",
  });

  const { email: emailB } = await loginAsNewAccount(page, "owner-b");
  const tokenB = await apiToken(emailB);

  const getAsB = await fetch(`${API_URL}/api/conversations/${convo.id}`, {
    headers: { Authorization: `Bearer ${tokenB}` },
  });
  expect(getAsB.status).toBe(404);

  const listAsB = await (
    await fetch(`${API_URL}/api/conversations`, { headers: { Authorization: `Bearer ${tokenB}` } })
  ).json();
  expect(listAsB.find((c: { id: string }) => c.id === convo.id)).toBeUndefined();

  const patchAsB = await fetch(`${API_URL}/api/conversations/${convo.id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${tokenB}` },
    body: JSON.stringify({ state: "discarded" }),
  });
  expect(patchAsB.status).toBe(404);

  const outcomeAsB = await fetch(`${API_URL}/api/conversations/${convo.id}/outcome`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${tokenB}` },
    body: JSON.stringify({ result: "customer" }),
  });
  expect(outcomeAsB.status).toBe(404);

  // sanity: account A can still read its own conversation
  const getAsA = await fetch(`${API_URL}/api/conversations/${convo.id}`, {
    headers: { Authorization: `Bearer ${tokenA}` },
  });
  expect(getAsA.status).toBe(200);
});

test("account B navigating directly to account A's conversation URL in the browser sees no data (404 handled, not a leak)", async ({
  page,
}) => {
  const { email: emailA } = await loginAsNewAccount(page, "owner-ui-a");
  const tokenA = await apiToken(emailA);
  const convo = await createManualConversation(page, tokenA, {
    title: "UI-level private conversation for account A only",
  });

  await loginAsNewAccount(page, "owner-ui-b");
  await page.goto(`/conversations/${convo.id}`, { waitUntil: "networkidle" });

  await expect(page.getByText("UI-level private conversation for account A only")).not.toBeVisible();
  await expect(page.getByText("No se pudo cargar la conversación.")).toBeVisible();
});
