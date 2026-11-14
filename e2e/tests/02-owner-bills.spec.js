// Owner persona: contractor bills on 1113 Vine St (docs/TESTING.md O1–O5).
const { test, expect } = require("@playwright/test");
const { resetApp, watchErrors, persona, open, runClaim, expectDecision, waitForStatus } = require("./helpers");

test.describe.configure({ mode: "serial" });
test.beforeAll(async ({ request }) => resetApp(request));

test("O1 CLM-2207 roof: 52,000 claimed vs 35,909 measured → pay $215,453, hold $96,547", async ({ page }) => {
  const errors = watchErrors(page);
  await runClaim(page, "CLM-2207");
  await expectDecision(page, "partial", /\$215,45[34]/, /\$96,54[67]/);
  await expect(page.getByText(/35,909/).first()).toBeVisible();
  expect(errors).toEqual([]);
});

test("O2 CLM-2214 rooftop AC: 40 claimed vs 30 counted → pay $240,000, hold $80,000", async ({ page }) => {
  await runClaim(page, "CLM-2214");
  await expectDecision(page, "partial", "$240,000", "$80,000");
});

test("O3 CLM-2223 bank swap ••9914 vs approved ••4421 → blocked", async ({ page }) => {
  await runClaim(page, "CLM-2223");
  await expectDecision(page, "blocked", "$0", "$14,800");
  await expect(page.getByText(/isn't the approved one|approved one|bank/i).first()).toBeVisible();
});

test("O4 CLM-2219 repaint: 3,100 vs 3,115 sq ft → paid in full", async ({ page }) => {
  await runClaim(page, "CLM-2219");
  await expectDecision(page, "approved", "$24,800", "$0");
});

test("O5 CLM-2231 arrives as an incoming document and is verified", async ({ page, request }) => {
  await open(page, "claims");
  await persona(page, "owner");
  await page.getByRole("button", { name: /Use sample: Refinish lobby floor/ }).click();
  expect(await waitForStatus(request, "CLM-2231")).toBe("approved");
  await open(page, "claim/CLM-2231");
  await expectDecision(page, "approved", "$12,200", "$0");
});

test("the claims list shows every owner bill with its status", async ({ page }) => {
  await open(page, "claims");
  await persona(page, "owner");
  for (const id of ["CLM-2207", "CLM-2214", "CLM-2223", "CLM-2219", "CLM-2231"]) await expect(page.getByRole("cell", { name: id })).toBeVisible();
});
