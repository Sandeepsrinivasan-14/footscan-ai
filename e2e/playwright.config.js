// Playwright smoke tests run against the real FastAPI app with a deterministic fake model
// (scripts/e2e_server.py), so no weights, GPU or Git LFS objects are needed.
import { defineConfig, devices } from "@playwright/test";

const PORT = Number(process.env.E2E_PORT || 8791);
const PYTHON = process.env.PYTHON || "python";

export default defineConfig({
  testDir: "./tests",
  fullyParallel: false, // tests share one server/database and create patients
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  timeout: 45_000,
  expect: { timeout: 10_000 },
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL: `http://127.0.0.1:${PORT}`,
    launchOptions: { executablePath: process.env.E2E_CHROMIUM || undefined }, // optional: use a pre-installed Chromium
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"], viewport: { width: 1360, height: 900 } }, grepInvert: /@mobile/ },
    { name: "mobile", use: { ...devices["Pixel 7"] }, grep: /@mobile/ },
  ],
  webServer: {
    command: `${PYTHON} ../scripts/e2e_server.py --port ${PORT}`,
    url: `http://127.0.0.1:${PORT}/health`,
    reuseExistingServer: !process.env.CI,
    timeout: 180_000,
    env: { NO_ALBUMENTATIONS_UPDATE: "1" },
  },
});
