// Shared steps for the click-through tests: reset, switch persona, run a claim from its page, read the decision,
// and a stand-in Phantom wallet that signs real devnet transactions from the test process.
const { expect } = require("@playwright/test");
const { Keypair, Transaction } = require("@solana/web3.js");

const LIVE = process.env.E2E_LIVE === "1";

// Status words the app shows (frontend/src/lib.jsx TAG).
const LABEL = {
  approved: "Verified", partial: "Partly verified", reduced: "Reduced", denied: "Denied", blocked: "Blocked",
  ok: "Approved", rejected: "Rejected", sent: "Message sent",
};

async function resetApp(request) {
  const r = await request.post("/api/reset");
  expect(r.ok()).toBeTruthy();
}

/** Fail the test on any uncaught error in the page. */
function watchErrors(page) {
  const errors = [];
  page.on("pageerror", e => errors.push(e.message));
  return errors;
}

async function persona(page, who) {
  const select = page.getByLabel("Workspace persona");
  if (!(await select.isVisible())) await page.locator(".nav-menu-button").click();  // the persona switch is in the menu
  await select.selectOption(who);
  await page.keyboard.press("Escape");
}

async function open(page, hash) {
  await page.goto("/#/" + hash);
  await expect(page.locator(".nav")).toBeVisible();
}

const decisionTile = page => page.locator(".tile", { has: page.locator(".over", { hasText: /^Decision$/ }) });

/** Open a claim, press Run agent, and wait for the decision. */
async function runClaim(page, id) {
  await open(page, "claim/" + id);
  const run = page.getByRole("button", { name: "Run agent", exact: true });
  if (await run.isVisible() && await run.isEnabled()) await run.click();
  await expect(decisionTile(page)).toBeVisible();
}

/** The decision tile shows the expected status and both amounts. */
async function expectDecision(page, status, a, b) {
  const tile = decisionTile(page);
  await expect(tile.locator(".tag").first()).toHaveText(LABEL[status]);
  const money = tile.locator(".bigmoney");
  if (a !== undefined) await expect(money.nth(0)).toHaveText(a);
  if (b !== undefined) await expect(money.nth(1)).toHaveText(b);
}

/** Wait until the server reports a final status for a claim (for claims queued by uploads, samples or the phone page). */
async function waitForStatus(request, id, timeout = LIVE ? 180_000 : 60_000) {
  let status;
  await expect.poll(async () => {
    const s = await (await request.get("/api/state")).json();
    status = s.status[id];
    return status && !["ready", "running"].includes(status);
  }, { timeout, intervals: [1000] }).toBe(true);
  return status;
}

async function stateClaims(request) {
  return (await (await request.get("/api/state")).json()).claims;
}

/**
 * A stand-in for the Phantom extension: window.phantom.solana in the page, with the private key kept in the test
 * process. The app's real code path runs: it builds the transaction on the server, the "wallet" signs, the server
 * checks the signed bytes and submits to Solana devnet.
 */
async function installWallet(page) {
  const kp = Keypair.generate();
  await page.exposeFunction("__e2eSign", b64 => {
    const tx = Transaction.from(Buffer.from(b64, "base64"));
    tx.partialSign(kp);
    return tx.serialize({ requireAllSignatures: true }).toString("base64");
  });
  await page.addInitScript(addr => {
    const publicKey = { toString: () => addr, toBase58: () => addr };
    const toB64 = bytes => btoa(String.fromCharCode(...bytes));
    const fromB64 = s => Uint8Array.from(atob(s), ch => ch.charCodeAt(0));
    window.phantom = {
      solana: {
        isPhantom: true,
        publicKey: null,
        async connect() { this.publicKey = publicKey; return { publicKey }; },
        async disconnect() { this.publicKey = null; },
        async signTransaction(tx) {
          window.__e2eSigned = (window.__e2eSigned || 0) + 1;
          const signed = await window.__e2eSign(toB64(tx.serialize({ requireAllSignatures: false, verifySignatures: false })));
          return tx.constructor.from(fromB64(signed));
        },
      },
    };
  }, kp.publicKey.toBase58());
  return kp.publicKey.toBase58();
}

async function solanaReady(request) {
  const s = await (await request.get("/api/solana/status")).json();
  return !!s.ready;
}

module.exports = { LIVE, LABEL, resetApp, watchErrors, persona, open, runClaim, expectDecision, decisionTile, waitForStatus,
  stateClaims, installWallet, solanaReady };
