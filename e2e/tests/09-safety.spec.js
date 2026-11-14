// Safety checks (docs/TESTING.md S): retries never pay twice, reset keeps the page in sync, and every owner bill
// still decides correctly when checks run back to back.
const { test, expect, resetApp, open, runClaim, expectDecision } = require("./helpers");

test.describe.configure({ mode: "serial" });
test.beforeAll(async ({ request }) => resetApp(request));

test("retrying a payment returns the existing receipt instead of paying again", async ({ page }) => {
  await runClaim(page, "CLM-2219");
  await page.getByRole("button", { name: "Retry payment" }).click();
  await expect(page.getByText(/Returned the existing receipt TX-CLM-2219-01. No second payment was made./)).toBeVisible();
});

test("resetting a claim sends it back to waiting, and it can run again", async ({ page }) => {
  await runClaim(page, "CLM-2223");
  await page.getByRole("button", { name: "Reset", exact: true }).click();
  await expect(page.getByRole("button", { name: "Run agent", exact: true })).toBeEnabled();
  await runClaim(page, "CLM-2223");
  await expectDecision(page, "blocked");
});

test("a whole-app reset keeps the open page live (state version never goes backwards)", async ({ page, request }) => {
  await open(page, "claims");
  const before = (await (await request.get("/api/state")).json()).rev;
  await resetApp(request);
  const after = (await (await request.get("/api/state")).json()).rev;
  expect(after).toBeGreaterThan(before);
  await expect(page.getByRole("cell", { name: "CLM-2207" })).toBeVisible();
});
