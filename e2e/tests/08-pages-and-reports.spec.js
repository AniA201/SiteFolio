// How it thinks, History, the Buildings explorer, the 3D tour and reports (docs/TESTING.md T, B, P, M).
const { test, expect, resetApp, persona, open, runClaim } = require("./helpers");

test.describe.configure({ mode: "serial" });
test.beforeAll(async ({ request }) => resetApp(request));

test("How it thinks shows planning, helper agents, evidence, memory and the human pause", async ({ page }) => {
  await runClaim(page, "CLM-2207");
  await open(page, "thinks");
  await page.getByRole("button", { name: /^CLM-2207/ }).click();
  for (const label of ["1 · Planning", "2 · Helper agents", "3 · Evidence folder", "4 · Long-term memory", "5 · Human in the loop"])
    await expect(page.getByText(label)).toBeVisible();
});

test("the claim's tabs: agent run, data calls, cross-checks and evidence", async ({ page }) => {
  await open(page, "claim/CLM-2207");
  for (const tab of ["Building data calls", "Cross-checks", "Evidence", "Agent run"]) {
    await page.locator(".tabs").getByRole("button", { name: tab }).click();
    await expect(page.locator(".tabs").getByRole("button", { name: tab })).toHaveClass(/on/);
  }
  await page.locator(".tabs").getByRole("button", { name: "Evidence" }).click();
  await expect(page.getByText("Evidence folder")).toBeVisible();
});

test("History: activity, flags and the surcharge registry", async ({ page }) => {
  await open(page, "history");
  await persona(page, "reviewer");
  await page.getByRole("button", { name: /Surcharge registry/ }).click();
  await expect(page.getByText(/Westmoreland Apartments/).first()).toBeVisible();
  await page.getByRole("button", { name: /Activity/ }).click();
});

test("Buildings: search the CoStar kit and open a building's dossier", async ({ page }) => {
  await open(page, "buildings");
  await page.locator("#kit-q").fill("apartments");
  const first = page.locator("tr.click").first();
  await expect(first).toBeVisible();
  await first.click();
  await expect(page).toHaveURL(/#\/building\//);
  await expect(page.locator("h1").first()).toBeVisible();
});

test("the 3D tour opens on a scanned claim", async ({ page }) => {
  await runClaim(page, "CLM-2219");
  const walk = page.getByRole("button", { name: /Walk the live 3D tour/ });
  await expect(walk).toBeEnabled();
  await walk.click();
  await expect(page.locator('iframe[title^="3D tour"], iframe[src*="matterport"]').first()).toBeAttached({ timeout: 30_000 });
});

test("reports: HTML and JSON after a run, refused before one", async ({ request }) => {
  const html = await request.get("/api/claims/CLM-2207/report");
  expect(html.ok()).toBeTruthy();
  expect(await html.text()).toContain("Line by line");
  const json = await (await request.get("/api/claims/CLM-2207/decision.json")).json();
  expect(json.decision.status).toBe("partial");
  const early = await request.get("/api/claims/CLM-2214/report");
  expect(early.status()).toBe(409);
});
