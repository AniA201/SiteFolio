// Every page opens for every persona without errors, and the server's integrations are up.
const { test, expect } = require("@playwright/test");
const { LIVE, resetApp, watchErrors, persona, open } = require("./helpers");

test.beforeAll(async ({ request }) => resetApp(request));

test("health: data layers, agent and Solana are configured", async ({ request }) => {
  const h = await (await request.get("/api/health")).json();
  expect(h.ok).toBe(true);
  for (const k of ["costar", "vexcel", "matterport"]) expect(h.integrations[k], k).toBe(true);
  if (LIVE) expect(h.integrations.deep_agent, "deep_agent").toBe(true);  // off on purpose in replay mode
  const sol = await (await request.get("/api/solana/status")).json();
  expect(sol.cluster).toBe("devnet");
});

for (const who of ["owner", "reviewer", "lender"]) {
  test(`every page opens for the ${who} persona`, async ({ page }) => {
    const errors = watchErrors(page);
    await open(page, "overview");
    await persona(page, who);
    for (const [hash, heading] of [["overview", null], ["claims", null], ["review", "Review"], ["thinks", "How it thinks"],
                                   ["history", "History"], ["buildings", null], ["fool", null]]) {
      await open(page, hash);
      if (heading) await expect(page.getByRole("heading", { name: heading, exact: true })).toBeVisible();
      await expect(page.locator("main, .wrapx").first()).toBeVisible();
    }
    expect(errors, errors.join("\n")).toEqual([]);
  });
}

test("the phone page opens on its own", async ({ page }) => {
  const errors = watchErrors(page);
  await page.goto("/#/fool-it");
  await expect(page.getByText(/Inflate the roof, swap the bank account/)).toBeVisible();
  expect(errors).toEqual([]);
});
