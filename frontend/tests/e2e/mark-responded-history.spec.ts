import { test, expect } from "@playwright/test";
import { loginAsNewAccount, createManualConversation, apiToken, API_URL } from "./helpers";

test("marking as responded + registering an outcome persists and shows up in Historial", async ({ page }) => {
  const { email } = await loginAsNewAccount(page, "responded-history");
  const token = await apiToken(email);
  const convo = await createManualConversation(page, token, {
    title: "Conversación para marcar como respondida en el test",
  });

  await page.goto(`/conversations/${convo.id}`, { waitUntil: "networkidle" });

  await page.getByRole("button", { name: "Marcar como respondida" }).click();
  await expect(page.getByRole("status")).toContainText("Marcada como respondida");

  // reload to prove it's persisted server-side, not just optimistic local state
  await page.reload({ waitUntil: "networkidle" });

  await page.getByRole("button", { name: "Resultado" }).click();
  await page.getByLabel("Resultado").selectOption("conversation_started");
  await page.locator("input[type=number]").first().fill("7"); // votos
  await page.getByRole("button", { name: "Guardar resultado" }).click();
  await expect(page.getByRole("status")).toContainText("Resultado guardado");

  await page.goto("/history", { waitUntil: "networkidle" });
  await expect(page.getByText("Conversación para marcar como respondida en el test")).toBeVisible();
  await expect(page.getByText("Conversaciones iniciadas")).toBeVisible();

  // verify server-side persistence directly via the API too, independent of the UI
  const detail = await (
    await fetch(`${API_URL}/api/conversations/${convo.id}`, {
      headers: { Authorization: `Bearer ${token}` },
    })
  ).json();
  expect(detail.state).toBe("responded");
  expect(detail.outcome.result).toBe("conversation_started");
  expect(detail.outcome.upvotes).toBe(7);
});
