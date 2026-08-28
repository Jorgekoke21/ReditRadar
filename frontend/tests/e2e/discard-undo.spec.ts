import { test, expect } from "@playwright/test";
import { loginAsNewAccount, createManualConversation, createTopic, apiToken, API_URL } from "./helpers";

test("discard removes a card from Hoy, and Deshacer restores it (server-persisted, not just UI)", async ({ page }) => {
  const { email } = await loginAsNewAccount(page, "discard-undo");
  const token = await apiToken(email);
  await createTopic(page, token, ["prioritize leads"]);
  const convo = await createManualConversation(page, token, {
    subreddit: "SaaS",
    title: "Conversación para probar descartar y deshacer",
    body: "Any tool to prioritize leads for my team?",
    language: "en",
  });

  await page.reload({ waitUntil: "networkidle" });
  await expect(page.getByText("Conversación para probar descartar y deshacer")).toBeVisible();

  await page.getByRole("button", { name: "Descartar", exact: true }).click();
  await expect(page.getByText("Conversación para probar descartar y deshacer")).not.toBeVisible();
  await expect(page.getByRole("status")).toContainText("Descartada");

  // verify the discard was actually persisted server-side before undoing
  const afterDiscard = await (
    await fetch(`${API_URL}/api/conversations/${convo.id}`, {
      headers: { Authorization: `Bearer ${token}` },
    })
  ).json();
  expect(afterDiscard.state).toBe("discarded");

  await page.getByRole("button", { name: "Deshacer" }).click();
  await page.waitForTimeout(500);

  const afterUndo = await (
    await fetch(`${API_URL}/api/conversations/${convo.id}`, {
      headers: { Authorization: `Bearer ${token}` },
    })
  ).json();
  expect(afterUndo.state).toBe("recommended");

  await page.reload({ waitUntil: "networkidle" });
  await expect(page.getByText("Conversación para probar descartar y deshacer")).toBeVisible();
});

test("guardar moves a conversation's state to saved and it stays saved after reload", async ({ page }) => {
  const { email } = await loginAsNewAccount(page, "save-state");
  const token = await apiToken(email);
  await createTopic(page, token, ["prioritize leads"]);
  const convo = await createManualConversation(page, token, {
    subreddit: "SaaS",
    title: "Conversación para probar guardar",
    body: "Any tool to prioritize leads?",
    language: "en",
  });

  await page.reload({ waitUntil: "networkidle" });
  await page.getByRole("button", { name: "Guardar", exact: true }).click();
  await expect(page.getByRole("status")).toContainText("Guardada para más tarde");

  const detail = await (
    await fetch(`${API_URL}/api/conversations/${convo.id}`, {
      headers: { Authorization: `Bearer ${token}` },
    })
  ).json();
  expect(detail.state).toBe("saved");
});
