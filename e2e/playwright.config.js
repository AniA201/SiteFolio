// Click-through tests of every Plumbline scenario (docs/TESTING.md) in Chromium.
//
// Playwright starts its own copy of the app on port 8799 so tests never disturb the app you use on 8787:
//   - recorded plans (PLUMBLINE_AGENT=replay) by default: fast and the same every time. E2E_LIVE=1 uses the live
//     deep agent on the free models instead (slower: 30-100 s per check).
//   - Tiger Cloud off (tests never write to the shared history); E2E_TIGER=1 turns it on.
//   - Bedrock stays off (backend/.env); Solana devnet is on (free test SOL).
// The window is visible and slowed down (900 ms per action, a caption shows the scenario) so you can follow each click.
// E2E_SLOWMO=250 is quicker, E2E_SLOWMO=0 full speed, E2E_HEADLESS=1 hides the window.
const { defineConfig, devices } = require("@playwright/test");

const PORT = Number(process.env.E2E_PORT || 8799);
const live = process.env.E2E_LIVE === "1";

module.exports = defineConfig({
  testDir: "./tests",
  fullyParallel: false,
  workers: 1, // one shared app, one browser: scenarios run in order like a person clicking through
  timeout: (live ? 8 : 4) * 60_000,
  expect: { timeout: live ? 150_000 : 30_000 },
  reporter: [["list"], ["html", { open: "never", outputFolder: "playwright-report" }]],
  use: {
    baseURL: `http://localhost:${PORT}`,
    headless: process.env.E2E_HEADLESS === "1",
    viewport: { width: 1440, height: 900 },
    launchOptions: { slowMo: Number(process.env.E2E_SLOWMO ?? 900) },  // ms between actions, slow enough to follow
    screenshot: "only-on-failure",
    video: "retain-on-failure",
    trace: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } } }],
  webServer: {
    command: `sh -c "cd ../frontend && npx vite build >/dev/null && cd .. && backend/.venv/bin/uvicorn app.main:app --app-dir backend --port ${PORT}"`,
    url: `http://localhost:${PORT}/api/health`,
    reuseExistingServer: false,
    timeout: 120_000,
    env: {
      ...process.env,
      PLUMBLINE_AGENT: live ? "" : "replay",
      TIGER_DATABASE_URL: process.env.E2E_TIGER === "1" ? (process.env.TIGER_DATABASE_URL || "") : "",
      PLUMBLINE_HOST: "e2e",
      PLUMBLINE_BEDROCK: "off",
      PUBLIC_URL: "",
    },
  },
});
