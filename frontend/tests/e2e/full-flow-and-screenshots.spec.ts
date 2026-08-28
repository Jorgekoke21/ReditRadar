import { test, expect } from "@playwright/test";
import path from "path";
import { collectConsoleErrors, createManualConversation, createTopic, loginAsNewAccount, API_URL } from "./helpers";

const SHOTS_DIR = path.resolve(process.cwd(), "../docs/screenshots");

async function assertNoHorizontalOverflow(page: import("@playwright/test").Page) {
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth + 1);
  expect(overflow, "page has horizontal overflow").toBe(false);
}

test("full principal flow end-to-end + required QA screenshots", async ({ page }) => {
  test.setTimeout(90_000);
  const errors = collectConsoleErrors(page);

  // 1. Acceso
  const { email } = await loginAsNewAccount(page, "full-flow");
  const token = await (
    await fetch(`${API_URL}/api/auth/dev-login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email }),
    })
  ).json();
  const bearerToken = token.access_token as string;

  await createTopic(page, bearerToken, ["prioritize leads", "any tool"]);

  // Seed a few varied conversations first so the required screenshots show real
  // populated cards (score, action, risk badges, truncation) instead of an
  // empty inbox — an empty screenshot can't verify "max two badges" etc.
  await createManualConversation(page, bearerToken, {
    subreddit: "SaaS",
    title: "Any tool you'd recommend to prioritize leads for a busy agency with way too many prospects to track manually?",
    body: "Looking for a tool to prioritize leads based on real signals, any recommendation?",
    language: "en",
  });
  await createManualConversation(page, bearerToken, {
    subreddit: "agency",
    title: "I built my own tool, everyone should use it to prioritize leads",
    body: "I built a tool to prioritize leads and I think it's amazing, way better than anything else, check it out",
    language: "en",
  });
  await createManualConversation(page, bearerToken, {
    subreddit: "startups",
    title: "How do you prioritize leads when you have any tool but no time?",
    body: "Curious how other founders prioritize leads day to day",
    language: "en",
  });

  // 2. Bandeja Hoy — desktop 1440x900
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/today", { waitUntil: "networkidle" });
  await assertNoHorizontalOverflow(page);
  await page.screenshot({ path: path.join(SHOTS_DIR, "today-desktop-1440x900.png") });

  // 1280x800
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.waitForTimeout(200);
  await assertNoHorizontalOverflow(page);
  await page.screenshot({ path: path.join(SHOTS_DIR, "today-desktop-1280x800.png") });

  // tablet 768x1024
  await page.setViewportSize({ width: 768, height: 1024 });
  await page.waitForTimeout(200);
  await assertNoHorizontalOverflow(page);
  await page.screenshot({ path: path.join(SHOTS_DIR, "today-tablet-768x1024.png") });

  // mobile 390x844
  await page.setViewportSize({ width: 390, height: 844 });
  await page.waitForTimeout(200);
  await assertNoHorizontalOverflow(page);
  await page.screenshot({ path: path.join(SHOTS_DIR, "today-mobile-390x844.png") });

  // 3. Importación manual (back to desktop for the form flow)
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/manual-import", { waitUntil: "networkidle" });
  await assertNoHorizontalOverflow(page);
  await page.screenshot({ path: path.join(SHOTS_DIR, "manual-import.png") });

  const conversationSourceUrl = "https://reddit.com/r/SaaS/comments/fullflow/any_tool_to_prioritize_leads/";
  await page
    .locator("label", { hasText: "URL de Reddit" })
    .locator("input")
    .fill(conversationSourceUrl);
  await page.locator("label", { hasText: "Subreddit" }).locator("input").fill("SaaS");
  await page.locator("label", { hasText: "Título" }).locator("input").fill("Any tool you'd recommend to prioritize leads?");
  await page
    .locator("label", { hasText: "Texto de la publicación" })
    .locator("textarea")
    .fill("Looking for a tool to prioritize leads based on real signals, any recommendation for my agency?");
  await page.locator("label", { hasText: "Idioma" }).locator("select").selectOption("en");
  await page.getByRole("button", { name: "Analizar e incorporar a la bandeja" }).click();

  // 4. Análisis + 5. Puntuación y desglose — lands on the ficha automatically
  await expect(page).toHaveURL(/\/conversations\/[0-9a-f-]{36}$/, { timeout: 10000 });
  const conversationUrl = page.url();
  const conversationId = conversationUrl.split("/").pop()!;
  await page.getByRole("button", { name: "Desglose de puntuación" }).click();
  await expect(page.getByText("Total")).toBeVisible();
  await assertNoHorizontalOverflow(page);
  await page.screenshot({ path: path.join(SHOTS_DIR, "conversation-desktop.png") });

  // 6. Generación de borradores (ya generados en el análisis) + edición
  const textarea = page.locator("textarea").first();
  await expect(textarea).toBeVisible();
  await textarea.fill("Borrador editado durante el flujo end-to-end.");
  await textarea.blur();
  await page.waitForTimeout(400);

  // 7. Copia
  await page.context().grantPermissions(["clipboard-read", "clipboard-write"]);
  await page.getByRole("button", { name: /Copiar respuesta/ }).click();
  await expect(page.getByRole("status").filter({ hasText: "copiada" })).toBeVisible();
  const clipboard = await page.evaluate(() => navigator.clipboard.readText());
  expect(clipboard).toBe("Borrador editado durante el flujo end-to-end.");

  // 8. Apertura de Reddit — verify the link is real, without leaving the app
  const redditLink = page.getByRole("link", { name: "Abrir en Reddit" });
  await expect(redditLink).toHaveAttribute("href", conversationSourceUrl);
  await expect(redditLink).toHaveAttribute("target", "_blank");

  // mobile screenshot of the ficha
  await page.setViewportSize({ width: 390, height: 844 });
  await page.waitForTimeout(200);
  await assertNoHorizontalOverflow(page);
  await page.screenshot({ path: path.join(SHOTS_DIR, "conversation-mobile.png") });
  await page.setViewportSize({ width: 1440, height: 900 });

  // 9. Marcar como respondida
  await page.getByRole("button", { name: "Marcar como respondida" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Marcada como respondida" })).toBeVisible();

  // 10. Registrar resultado
  await page.getByRole("button", { name: "Resultado" }).click();
  await page.getByLabel("Resultado").selectOption("radarin_signup");
  await page.getByRole("button", { name: "Guardar resultado" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Resultado guardado" })).toBeVisible();

  // 11. Ver resultado en Historial
  await page.goto("/history", { waitUntil: "networkidle" });
  await expect(page.getByText("Any tool you'd recommend to prioritize leads?")).toBeVisible();

  // 12. Configurar una alerta + 13. Previsualizar el resumen diario
  await page.goto("/alerts", { waitUntil: "networkidle" });
  await assertNoHorizontalOverflow(page);
  await page.screenshot({ path: path.join(SHOTS_DIR, "alerts.png") });

  await page.getByPlaceholder("tu@email.com").fill("fullflow@example.com");
  await page.getByRole("button", { name: "Guardar configuración" }).click();
  await expect(page.getByRole("status").filter({ hasText: "guardada" })).toBeVisible();

  // create a second, fresh, qualifying conversation so the digest has something to include
  await createManualConversation(page, bearerToken, {
    subreddit: "SaaS",
    title: "Second qualifying conversation for the digest",
    body: "Any tool to prioritize leads for my team, please recommend one?",
    language: "en",
  });

  await page.goto("/diagnostics", { waitUntil: "networkidle" });
  await page.getByRole("button", { name: "send_daily_digest" }).click();
  await expect(page.getByRole("status")).toContainText("send_daily_digest");

  await page.goto("/alerts", { waitUntil: "networkidle" });
  await expect(page.locator("details", { hasText: "conversaciones nuevas donde puedes aportar valor" })).toBeVisible();

  expect(errors, `console errors during full flow: ${errors.join("; ")}`).toEqual([]);
  void conversationId;
});
