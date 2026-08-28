import { defineConfig, devices } from "@playwright/test";

/**
 * Runs against the app already started by `docker compose up` (or `npm run dev`)
 * at http://localhost:5180 talking to the API at http://localhost:8010 (see
 * tests/e2e/helpers.ts for the single source of truth on the API URL).
 * We do NOT start the servers here — this suite audits the real running stack,
 * not a throwaway in-process server.
 */
export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [["list"], ["html", { outputFolder: "playwright-report", open: "never" }]],
  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL || "http://localhost:5180",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
  ],
});
