import { test, expect } from "@playwright/test";
import { loginAsNewAccount, createManualConversation, createTopic, apiToken } from "./helpers";

test("alert settings persist across reload (not just a success toast)", async ({ page }) => {
  await loginAsNewAccount(page, "alerts-settings");
  await page.goto("/alerts", { waitUntil: "networkidle" });

  const email = "alertas-test@example.com";
  await page.getByPlaceholder("tu@email.com").fill(email);
  await page.locator("input[type=time]").fill("07:30");
  await page.getByRole("button", { name: "Guardar configuración" }).click();
  await expect(page.getByRole("status")).toContainText("Configuración de alertas guardada");

  await page.reload({ waitUntil: "networkidle" });
  await expect(page.getByPlaceholder("tu@email.com")).toHaveValue(email);
  await expect(page.locator("input[type=time]")).toHaveValue("07:30");
});

test("empty preview tray shows an actionable empty state before any email is generated", async ({ page }) => {
  await loginAsNewAccount(page, "alerts-empty");
  await page.goto("/alerts", { waitUntil: "networkidle" });
  await expect(page.getByText("Todavía no se ha generado ningún correo")).toBeVisible();
});

test("send-test email appears in the preview tray marked as NOT externally sent (console provider)", async ({ page }) => {
  await loginAsNewAccount(page, "alerts-test-email");
  await page.goto("/alerts", { waitUntil: "networkidle" });

  await page.getByPlaceholder("tu@email.com").fill("preview-only@example.com");
  await page.getByRole("button", { name: "Enviar correo de prueba" }).click();
  await expect(page.getByRole("status")).toContainText("sin proveedor externo");

  const details = page.locator("details", { hasText: "Correo de prueba" });
  await expect(details).toBeVisible();
  await expect(details).toContainText("solo previsualización");
});

test("daily digest preview reflects a real qualifying conversation, generated via the job trigger", async ({ page }) => {
  const { email } = await loginAsNewAccount(page, "alerts-digest");
  const token = await apiToken(email);
  await createTopic(page, token, ["prioritize leads"]);
  await createManualConversation(page, token, {
    subreddit: "SaaS",
    title: "Digest preview conversation",
    body: "Any tool to prioritize leads for my agency, really need one?",
    language: "en",
  });

  await page.goto("/alerts", { waitUntil: "networkidle" });
  await page.getByPlaceholder("tu@email.com").fill("digest@example.com");
  await page.getByRole("button", { name: "Guardar configuración" }).click();
  await expect(page.getByRole("status")).toContainText("guardada");

  await page.goto("/diagnostics", { waitUntil: "networkidle" });
  await page.getByRole("button", { name: "send_daily_digest" }).click();
  await expect(page.getByRole("status")).toContainText("send_daily_digest");

  await page.goto("/alerts", { waitUntil: "networkidle" });
  const digestRow = page.locator("details", { hasText: "conversaciones nuevas donde puedes aportar valor" });
  await expect(digestRow).toBeVisible();
  await digestRow.locator("summary").click();
  const frame = digestRow.locator("iframe");
  await expect(frame).toBeVisible();
});
