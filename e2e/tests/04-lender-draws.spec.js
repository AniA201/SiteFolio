// Lender persona: construction loan draws on Lenox Timbergrove (docs/TESTING.md L1–L2).
const { test, expect, resetApp, persona, open, runClaim, expectDecision, waitForStatus } = require("./helpers");

test.describe.configure({ mode: "serial" });
test.beforeAll(async ({ request }) => resetApp(request));

test("L1 DRW-0412: 13 of 13 claimed, 10 of 13 scanned → release $461,538, hold $138,462", async ({ page }) => {
  await runClaim(page, "DRW-0412");
  await expectDecision(page, "partial", "$461,538", "$138,462");
});

test("L2 DRW-0415 arrives as an incoming document: roof complete → release $250,000", async ({ page, request }) => {
  await open(page, "claims");
  await persona(page, "lender");
  await page.getByRole("button", { name: /Use sample: Draw 5/ }).click();
  expect(await waitForStatus(request, "DRW-0415")).toBe("approved");
  await open(page, "claim/DRW-0415");
  await expectDecision(page, "approved", "$250,000", "$0");
});

test("draws are never blocked", async ({ request }) => {
  const s = await (await request.get("/api/state")).json();
  for (const id of ["DRW-0412", "DRW-0415"]) expect(s.status[id]).not.toBe("blocked");
});
