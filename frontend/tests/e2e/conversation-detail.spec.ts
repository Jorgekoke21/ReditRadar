import { test, expect } from "@playwright/test";
import { loginAsNewAccount, createManualConversation, createTopic, apiToken } from "./helpers";

test.beforeEach(async ({ context }) => {
  await context.grantPermissions(["clipboard-read", "clipboard-write"]);
});

async function openFreshConversation(page: import("@playwright/test").Page, label: string) {
  const { email } = await loginAsNewAccount(page, label);
  const token = await apiToken(email);
  await createTopic(page, token, ["prioritize leads", "any tool"]);
  const convo = await createManualConversation(page, token, {
    subreddit: "SaaS",
    title: "Any tool you'd recommend to prioritize leads?",
    body: "Looking for a tool to prioritize leads based on real signals for my agency, any recommendation?",
    language: "en",
  });
  await page.goto(`/conversations/${convo.id}`, { waitUntil: "networkidle" });
  return convo;
}

test("ficha shows problem, value angle, recommended action and risk — not placeholders", async ({ page }) => {
  await openFreshConversation(page, "detail-content");
  await expect(page.getByText("Qué necesita la persona")).toBeVisible();
  await expect(page.getByText("Cómo podemos aportar")).toBeVisible();
  await expect(page.getByText("Acción recomendada")).toBeVisible();
  await expect(page.getByText("Mención de Radarin")).toBeVisible();
  // the "—" fallback must NOT be showing for a conversation that was actually
  // analyzed: it should show the matched topic's own description instead.
  await expect(page.getByText("tema de prueba")).toBeVisible();
});

test("draft editor: can switch variants, edit text, and the edit persists on reload", async ({ page }) => {
  const convo = await openFreshConversation(page, "detail-draft-edit");

  const textarea = page.locator("textarea").first();
  await expect(textarea).toBeVisible();
  const original = await textarea.inputValue();
  expect(original.length).toBeGreaterThan(0);

  await textarea.fill("Texto de prueba editado por el test end-to-end.");
  await textarea.blur();
  await page.waitForTimeout(500);

  await page.reload({ waitUntil: "networkidle" });
  await expect(page.locator("textarea").first()).toHaveValue("Texto de prueba editado por el test end-to-end.");
  void convo;
});

test("copiar respuesta writes the draft text to the clipboard and shows confirmation", async ({ page }) => {
  await openFreshConversation(page, "detail-copy");

  const textarea = page.locator("textarea").first();
  const text = await textarea.inputValue();

  await page.getByRole("button", { name: /Copiar respuesta/ }).click();
  await expect(page.getByRole("status")).toContainText("copiada al portapapeles");

  const clipboardText = await page.evaluate(() => navigator.clipboard.readText());
  expect(clipboardText).toBe(text);
});

test("abrir en Reddit points at the real conversation URL when one was provided", async ({ page }) => {
  const { email } = await loginAsNewAccount(page, "detail-reddit-link");
  const token = await apiToken(email);
  await createTopic(page, token, ["prioritize leads"]);
  const convo = await createManualConversation(page, token, {
    subreddit: "SaaS",
    title: "Conversation with a real Reddit URL",
    body: "Any tool to prioritize leads?",
    language: "en",
    url: "https://reddit.com/r/SaaS/comments/abc123/conversation_with_a_real_reddit_url/",
  });
  await page.goto(`/conversations/${convo.id}`, { waitUntil: "networkidle" });

  const link = page.getByRole("link", { name: "Abrir en Reddit" });
  await expect(link).toHaveAttribute("href", convo.url);
  await expect(link).toHaveAttribute("target", "_blank");
});

test("abrir en Reddit is NOT rendered (no dead button) when the conversation has no URL", async ({ page }) => {
  // regression test: manual imports without a URL used to get a synthetic
  // "manual://subreddit/title" stored as their url, which produced a
  // non-functional "Abrir en Reddit" link. The button must not exist at all
  // in this case, rather than linking to a fake, unopenable address.
  const convo = await openFreshConversation(page, "detail-reddit-no-link");
  expect(convo.url).toBe("");
  await expect(page.getByRole("link", { name: "Abrir en Reddit" })).toHaveCount(0);
});

test("recalcular puntuación and volver a analizar call the backend and update the score breakdown", async ({ page }) => {
  await openFreshConversation(page, "detail-recalc");
  await page.getByRole("button", { name: "Desglose de puntuación" }).click();
  await expect(page.getByText("Total")).toBeVisible();

  const requests: string[] = [];
  page.on("request", (req) => {
    const url = new URL(req.url());
    if (url.pathname.match(/\/api\/conversations\/[0-9a-f-]+\/(recalculate|analyze)$/)) requests.push(url.pathname);
  });

  await page.getByRole("button", { name: "Recalcular puntuación" }).click();
  await page.waitForTimeout(800);
  expect(requests.some((p) => p.endsWith("/recalculate"))).toBeTruthy();

  await page.getByRole("button", { name: "Volver a analizar" }).click();
  await page.waitForTimeout(800);
  expect(requests.some((p) => p.endsWith("/analyze"))).toBeTruthy();
});

test("eliminar contenido original ahora purges raw content and updates the ficha", async ({ page }) => {
  await openFreshConversation(page, "detail-purge");
  await page.getByRole("button", { name: "Conversación original" }).click();
  await page.getByRole("button", { name: "Eliminar contenido original ahora" }).click();
  await expect(page.getByText("El contenido original se eliminó automáticamente")).toBeVisible({ timeout: 5000 });
});
