import { test, expect } from "@playwright/test";
import { loginAsNewAccount } from "./helpers";

test("keyboard focus is visible on the primary action button", async ({ page }) => {
  await loginAsNewAccount(page, "a11y-focus");
  await page.goto("/today", { waitUntil: "networkidle" });

  // Tab from the top of the document until we land on the "Revisar ahora" button
  let found = false;
  for (let i = 0; i < 15; i++) {
    await page.keyboard.press("Tab");
    const active = await page.evaluate(() => document.activeElement?.textContent?.trim());
    if (active?.includes("Revisar ahora")) {
      found = true;
      break;
    }
  }
  expect(found, "could not reach 'Revisar ahora' via keyboard Tab").toBe(true);

  const outline = await page.evaluate(() => {
    const el = document.activeElement as HTMLElement;
    const style = getComputedStyle(el);
    return { outlineStyle: style.outlineStyle, outlineWidth: style.outlineWidth };
  });
  expect(outline.outlineStyle).not.toBe("none");
  expect(outline.outlineWidth).not.toBe("0px");
});

test("email input has an associated accessible label", async ({ page }) => {
  await page.goto("/login");
  const input = page.getByPlaceholder("tu@email.com");
  await expect(input).toHaveAccessibleName(/correo/i);
});
