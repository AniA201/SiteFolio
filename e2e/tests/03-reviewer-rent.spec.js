// Reviewer persona: LA rent increase applications (docs/TESTING.md R1–R2).
const { test, expect } = require("@playwright/test");
const { resetApp, persona, open, runClaim, expectDecision, waitForStatus } = require("./helpers");

test.describe.configure({ mode: "serial" });
test.beforeAll(async ({ request }) => resetApp(request));

test("R1 RSO-3104: asks $36.28/unit/month, verified quantities give $20.92", async ({ page }) => {
  await runClaim(page, "RSO-3104");
  await expectDecision(page, "reduced", "$36.28/mo", "$20.92/mo");
});

test("R1 tenant page and tenant proof say $20.92 a month", async ({ page, request }) => {
  await open(page, "claim/RSO-3104");
  await page.getByRole("button", { name: "Open tenant page" }).click();
  await expect(page.getByText(/20\.92/).first()).toBeVisible();
  const proof = await request.get("/api/claims/RSO-3104/report?audience=tenant");
  expect(proof.ok()).toBeTruthy();
  expect(await proof.text()).toContain("$20.92");
});

test("R2 RSO-3110 arrives as an incoming document and is denied (roof already surcharged until 2029)", async ({ page, request }) => {
  await open(page, "claims");
  await persona(page, "reviewer");
  await page.getByRole("button", { name: /Use sample: Roof coating/ }).click();
  expect(await waitForStatus(request, "RSO-3110")).toBe("denied");
  await open(page, "claim/RSO-3110");
  await expectDecision(page, "denied", "$8.16/mo", "$0");
});
