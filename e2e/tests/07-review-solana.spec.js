// Human in the loop and Solana (docs/TESTING.md H1–H7): approve, reject, the devnet receipt, Verify, the evidence
// edit, Phantom signing and releasing held money. Solana steps are skipped if the app wallet has no devnet SOL.
const { test, expect } = require("@playwright/test");
const { LIVE, resetApp, persona, open, runClaim, installWallet, solanaReady } = require("./helpers");

test.describe.configure({ mode: "serial" });
test.beforeAll(async ({ request }) => resetApp(request));

const panel = page => page.locator(".sol-panel");

async function reviewItem(page, id) {
  await open(page, "review");
  await page.locator(".review-item", { hasText: id }).click();
}

test("H1/H2 approve CLM-2207 in Review: decision recorded and a Solana receipt with pay and hold", async ({ page, request }) => {
  await runClaim(page, "CLM-2207");
  await reviewItem(page, "CLM-2207");
  await page.getByRole("button", { name: /Approve: pay \$215,45\d, hold \$96,54\d/ }).click();
  await expect(page.getByText("Recorded. The agent resumed and logged it.")).toBeVisible();
  if (LIVE) await expect(page.getByText(/agent resumed the same run/).first()).toBeAttached();
  test.skip(!(await solanaReady(request)), "Solana app wallet has no devnet SOL");
  await expect(panel(page).getByRole("link", { name: /Recorded on Solana/ })).toBeVisible({ timeout: 90_000 });
  await expect(panel(page)).toContainText("Paid to contractor");
  await expect(panel(page)).toContainText(/\$215,45\d/);
  await expect(panel(page)).toContainText(/\$96,54\d/);
  await expect(panel(page)).toContainText("demo lender key");
  await expect(page.getByText("Permanent: it's on Solana.")).toBeVisible();
});

test("H4 Verify is green, an evidence edit turns it red, undo turns it green again", async ({ page, request }) => {
  test.skip(!(await solanaReady(request)), "Solana app wallet has no devnet SOL");
  await reviewItem(page, "CLM-2207");
  await page.getByRole("button", { name: "Verify evidence" }).click();
  await expect(panel(page).getByText("✓ Matches Solana")).toBeVisible();
  await page.getByRole("button", { name: "Edit the evidence (demo)" }).click();
  await expect(panel(page).getByText("✕ Doesn't match Solana")).toBeVisible();
  await page.getByRole("button", { name: "Undo the edit" }).click();
  await page.getByRole("button", { name: "Verify evidence" }).click();
  await expect(panel(page).getByText("✓ Matches Solana")).toBeVisible();
});

test("H6 reject CLM-2214: rejected, receipt only, no money moves", async ({ page, request }) => {
  await runClaim(page, "CLM-2214");
  await reviewItem(page, "CLM-2214");
  await page.getByRole("button", { name: "Reject", exact: true }).click();
  await expect(page.locator(".review-item", { hasText: "CLM-2214" }).getByText("Rejected")).toBeVisible();
  test.skip(!(await solanaReady(request)), "Solana app wallet has no devnet SOL");
  await expect(panel(page)).toContainText(/rejected · no money moved/, { timeout: 90_000 });
});

test("H7 approving a rent decision records a receipt only", async ({ page, request }) => {
  await runClaim(page, "RSO-3104");
  await open(page, "review");
  await persona(page, "reviewer");
  await page.locator(".review-item", { hasText: "RSO-3104" }).click();
  await page.getByRole("button", { name: /Approve at \$20\.92\/mo/ }).click();
  test.skip(!(await solanaReady(request)), "Solana app wallet has no devnet SOL");
  await expect(panel(page)).toContainText(/no money moved/, { timeout: 90_000 });
});

test("H3/H5 lender signs with a Phantom wallet, then co-signs the release of the held money", async ({ page, request }) => {
  test.skip(!(await solanaReady(request)), "Solana app wallet has no devnet SOL");
  const wallet = await installWallet(page);
  await runClaim(page, "DRW-0412");
  await open(page, "review");
  await persona(page, "lender");
  await page.getByRole("button", { name: "Connect Phantom to sign" }).click();
  await expect(page.getByText(new RegExp(`Phantom · ${wallet.slice(0, 4)}`))).toBeVisible();
  await page.locator(".review-item", { hasText: "DRW-0412" }).click();
  await page.getByRole("button", { name: "Release $461,538, hold $138,462" }).click();
  await expect(panel(page).getByRole("link", { name: /Recorded on Solana/ })).toBeVisible({ timeout: 90_000 });
  await expect(panel(page)).toContainText("Phantom");
  await expect(panel(page)).toContainText("$461,538");
  expect(await page.evaluate(() => window.__e2eSigned)).toBe(1);
  await page.getByRole("button", { name: "New scan verified: release $138,462" }).click();
  await expect(panel(page)).toContainText("Released", { timeout: 90_000 });
  await expect(panel(page).getByRole("link", { name: /Release transaction/ })).toBeVisible();
  expect(await page.evaluate(() => window.__e2eSigned)).toBe(2);
});
