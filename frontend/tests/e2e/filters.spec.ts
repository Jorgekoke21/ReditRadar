import { test, expect } from "@playwright/test";
import { loginAsNewAccount, createManualConversation, createTopic, apiToken } from "./helpers";

test("conversations list filters actually change the result set (not cosmetic)", async ({ page }) => {
  const { email } = await loginAsNewAccount(page, "filters");
  const token = await apiToken(email);
  await createTopic(page, token, ["priorizar leads", "seo local"]);
  await createManualConversation(page, token, {
    subreddit: "agency",
    title: "Necesito priorizar leads en mi agencia",
    body: "alguna herramienta para priorizar leads",
  });
  await createManualConversation(page, token, {
    subreddit: "localseo",
    title: "Busco clientes de SEO local",
    body: "quiero mas clientes de seo local",
  });

  await page.goto("/conversations", { waitUntil: "networkidle" });
  await expect(page.getByText("Necesito priorizar leads en mi agencia")).toBeVisible();
  await expect(page.getByText("Busco clientes de SEO local")).toBeVisible();

  // free-text search narrows the list
  await page.getByPlaceholder("Buscar por título o resumen…").fill("SEO local");
  await page.waitForTimeout(400);
  await expect(page.getByText("Busco clientes de SEO local")).toBeVisible();
  await expect(page.getByText("Necesito priorizar leads en mi agencia")).not.toBeVisible();

  await page.getByPlaceholder("Buscar por título o resumen…").fill("");

  // subreddit filter narrows the list via a real API call, not client-side only
  const requestsSeen: string[] = [];
  page.on("request", (req) => {
    if (req.url().includes("/api/conversations?")) requestsSeen.push(req.url());
  });
  await page.getByLabel("Subreddit").selectOption("agency");
  await page.waitForTimeout(400);
  await expect(page.getByText("Necesito priorizar leads en mi agencia")).toBeVisible();
  await expect(page.getByText("Busco clientes de SEO local")).not.toBeVisible();
  expect(requestsSeen.some((u) => u.includes("subreddit=agency"))).toBeTruthy();
});

test("empty result from filters shows an actionable empty state, not a silent blank page", async ({ page }) => {
  const { email } = await loginAsNewAccount(page, "filters-empty");
  const token = await apiToken(email);
  await createManualConversation(page, token, { title: "Conversación única para filtro vacío" });

  await page.goto("/conversations", { waitUntil: "networkidle" });
  await page.getByPlaceholder("Buscar por título o resumen…").fill("texto que no existe en ningun lado xyz");
  await page.waitForTimeout(400);

  await expect(page.getByText("Ningún resultado con estos filtros")).toBeVisible();
  await expect(page.getByRole("button", { name: "Quitar filtros" })).toBeVisible();
});
