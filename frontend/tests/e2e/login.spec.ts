import { test, expect } from "@playwright/test";
import { loginViaForm } from "./helpers";

test("real login form: entering an email and submitting reaches /today", async ({ page }) => {
  const email = `e2e-login-${Date.now()}@example.com`;
  await loginViaForm(page, email);
  await expect(page.getByRole("heading", { name: "Hoy" })).toBeVisible();
});

test("unauthenticated user hitting a protected route is redirected to /login", async ({ page }) => {
  await page.goto("/conversations");
  await expect(page).toHaveURL(/\/login$/);
});
