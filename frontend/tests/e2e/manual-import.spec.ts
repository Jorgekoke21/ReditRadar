import { test, expect } from "@playwright/test";
import { loginAsNewAccount, createTopic, apiToken } from "./helpers";

test("manual import form validates required fields inline", async ({ page }) => {
  await loginAsNewAccount(page, "manual-validate");
  await page.goto("/manual-import");
  await page.getByRole("button", { name: "Analizar e incorporar a la bandeja" }).click();
  await expect(page.getByText("Indica el subreddit.")).toBeVisible();
  await expect(page.getByText("Indica el título de la publicación.")).toBeVisible();
});

test("manual import creates a real, analyzed conversation and navigates to its ficha", async ({ page }) => {
  const { email } = await loginAsNewAccount(page, "manual-create");
  const token = await apiToken(email);
  await createTopic(page, token, ["priorizar leads"]);
  await page.goto("/manual-import");

  await page.locator("label", { hasText: "Subreddit" }).locator("input").fill("agency");
  await page.locator("label", { hasText: "Título" }).locator("input").fill("Necesito ayuda priorizando leads");
  await page
    .locator("label", { hasText: "Texto de la publicación" })
    .locator("textarea")
    .fill("Tengo demasiados leads, alguna herramienta para priorizar leads?");

  await page.getByRole("button", { name: "Analizar e incorporar a la bandeja" }).click();

  // must navigate away from the import form into the conversation's own ficha —
  // proves the button is wired to a real create+analyze call, not a fake "success" toast.
  await expect(page).toHaveURL(/\/conversations\/[0-9a-f-]{36}$/, { timeout: 10000 });
  await expect(page.getByText("Necesito ayuda priorizando leads")).toBeVisible();

  // score breakdown must be present (proves analysis actually ran server-side)
  await page.getByRole("button", { name: "Desglose de puntuación" }).click();
  await expect(page.getByText("Total")).toBeVisible();
});

test("CSV import reports parse errors without discarding valid rows", async ({ page }) => {
  await loginAsNewAccount(page, "manual-csv");
  await page.goto("/manual-import");

  const csv =
    "url,subreddit,title,body,num_comments,language\n" +
    ",agency,CSV import test conversation,cuerpo de prueba,1,es\n" +
    ",,Missing subreddit and title,should error,0,en\n";

  const fileChooserPromise = page.waitForEvent("filechooser");
  await page.getByText("Selecciona un archivo .csv").click();
  const chooser = await fileChooserPromise;
  await chooser.setFiles({ name: "import.csv", mimeType: "text/csv", buffer: Buffer.from(csv) });

  await expect(page.getByText(/1 importadas/)).toBeVisible({ timeout: 10000 });
  await expect(page.getByText(/Fila 3/)).toBeVisible();
});
