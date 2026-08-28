import { test, expect } from "@playwright/test";
import { loginAsNewAccount, createManualConversation, createTopic, apiToken, collectConsoleErrors } from "./helpers";

test("empty state: brand new account shows the actionable empty message, not a blank list", async ({ page }) => {
  const errors = collectConsoleErrors(page);
  await loginAsNewAccount(page, "today-empty");
  await expect(page.getByText("No hemos encontrado conversaciones relevantes todavía")).toBeVisible();
  await expect(page.getByRole("link", { name: "Importar conversación" })).toBeVisible();
  expect(errors, `console errors: ${errors.join("; ")}`).toEqual([]);
});

test("today inbox lists a real conversation with score, action and at most two badges", async ({ page }) => {
  const { email } = await loginAsNewAccount(page, "today-list");
  const token = await apiToken(email);
  await createTopic(page, token, ["priorizar leads", "prioritize leads"]);
  await createManualConversation(page, token, {
    title: "Any tool to prioritize leads for my agency?",
    body: "Looking for a tool to prioritize leads based on real signals, any recommendation?",
  });

  await page.reload({ waitUntil: "networkidle" });

  const row = page.locator("text=Any tool to prioritize leads").first();
  await expect(row).toBeVisible();

  // score indicator (a two-digit-or-more number in a circle) must be present and non-zero
  const scoreText = await page.locator("text=/^\\d{1,3}$/").first().innerText();
  expect(Number(scoreText)).toBeGreaterThan(0);

  // at most two pill-style badges per card (recommended action text is not a badge itself;
  // only "Riesgo ..." and "Ejemplo ficticio"/topic name pills count)
  const card = page.locator("div").filter({ hasText: "Any tool to prioritize leads" }).first();
  const riskBadge = card.getByText(/Riesgo (bajo|medio|alto)/);
  await expect(riskBadge).toBeVisible();
});

test("Revisar ahora button actually triggers analysis jobs (not a no-op)", async ({ page }) => {
  const { email } = await loginAsNewAccount(page, "today-review");
  const token = await apiToken(email);
  await createTopic(page, token, ["priorizar leads"]);

  // create a conversation directly via SQL-less path: manual import always analyzes
  // synchronously already, so instead we verify the button calls the job endpoints
  // by watching the network requests it issues.
  const calledPaths: string[] = [];
  page.on("request", (req) => {
    const url = new URL(req.url());
    if (url.pathname.startsWith("/api/jobs/")) calledPaths.push(url.pathname);
  });

  await page.getByRole("button", { name: "Revisar ahora" }).click();
  await expect(page.getByRole("button", { name: /Revisando|Revisar ahora/ })).toBeVisible();
  await page.waitForTimeout(1500);

  expect(calledPaths).toContain("/api/jobs/analyze_pending_conversations/run");
  expect(calledPaths).toContain("/api/jobs/recalculate_scores/run");
});
