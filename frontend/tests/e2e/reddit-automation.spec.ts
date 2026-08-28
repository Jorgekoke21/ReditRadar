import { test, expect } from "@playwright/test";
import { apiToken, createManualConversation, createTopic, loginAsNewAccount } from "./helpers";

test("simulated Reddit ingestion appears in Hoy with score, action and a response draft", async ({ page }) => {
  const { email } = await loginAsNewAccount(page, "reddit-automation-inbox");
  const token = await apiToken(email);
  await createTopic(page, token, ["prioritize leads", "herramienta"]);

  const title = "Simulated Reddit post: what tool helps prioritize leads?";
  const conversation = await createManualConversation(page, token, {
    url: "https://reddit.com/r/SaaS/comments/e2eautomation/",
    subreddit: "SaaS",
    title,
    body: "I need a tool to prioritize leads from real signals. What do other agencies recommend?",
    language: "en",
  });

  await page.goto("/today", { waitUntil: "networkidle" });
  await expect(page.getByText(title)).toBeVisible();
  await expect(page.locator("[title*='100']").first()).toBeVisible();
  await expect(page.getByText(/Responder ahora|Revisar hoy/).first()).toBeVisible();

  await page.goto("/conversations/" + conversation.id, { waitUntil: "networkidle" });
  await expect(page.locator("textarea").first()).toBeVisible();
  await expect(page.getByRole("link", { name: "Abrir en Reddit" })).toHaveAttribute("href", conversation.url);
});

test("disabled Reddit job records a safe simulated run and exposes diagnostics", async ({ page }) => {
  await loginAsNewAccount(page, "reddit-automation-diagnostics");
  await page.goto("/diagnostics", { waitUntil: "networkidle" });

  await expect(page.getByRole("heading", { name: /Diagn/ })).toBeVisible();
  await expect(page.getByText("desactivada", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "fetch_reddit_conversations" }).click();
  await expect(page.getByRole("status")).toContainText("fetch_reddit_conversations");

  await expect(page.getByText("fetch_reddit_conversations", { exact: true }).last()).toBeVisible();
  await expect(page.getByText(/posts: 0/)).toBeVisible();
  await expect(page.getByText(/Comunidades: 0/)).toBeVisible();
});
