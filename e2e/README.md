# SiteFolio click-through tests (Playwright, Chromium)

Every scenario in [docs/TESTING.md](../docs/TESTING.md), clicked through in a visible Chromium window.

```bash
cd e2e
npm install                     # first time only
npx playwright install chromium # first time only
npm test                        # visible window, slowed down so you can follow each click
```

Playwright starts its **own copy of the app on port 8799** (it builds the frontend first), so your app on 8787 and the
live site are never touched.

| Option | What it does |
|---|---|
| `E2E_SLOWMO=0` | Full speed (default 900 ms between actions, with a caption naming each scenario) |
| `E2E_HEADLESS=1` | Hide the browser window |
| `E2E_LIVE=1` | Use the live deep agent on the free models instead of the recorded plans (30–100 s per check) |
| `E2E_TIGER=1` | Write to Tiger Cloud (off by default so tests don't add to the shared history) |
| `npx playwright test tests/07-review-solana.spec.js` | Run one file |
| `npm run test:ui` | Playwright's UI: pick tests, watch them, time-travel through each step |
| `npm run report` | Open the HTML report of the last run (screenshots, video and trace of any failure) |

Bedrock stays off. Solana runs on devnet with free test SOL; the Solana tests skip themselves if the app wallet is empty.

| File | Covers |
|---|---|
| `01-navigation` | Health, every page for owner / reviewer / lender, the phone page, no page errors |
| `02-owner-bills` | O1–O5: inflated roof, inflated AC count, bank swap, honest repaint, incoming lobby floor |
| `03-reviewer-rent` | R1 reduced rent and the tenant proof, R2 duplicate surcharge denied |
| `04-lender-draws` | L1 partial draw release, L2 roof draw, draws never blocked |
| `05-fool-it` | F1–F4 judge's bills (honest, inflated, swapped bank, hidden note to the AI), the phone page |
| `06-upload` | Uploaded bills: bank swap + injection blocked, good bill partly verified, wrong file type refused |
| `07-review-solana` | Approve with a Solana receipt, Verify / edit / undo, reject, rent receipt, Phantom signing and release |
| `08-pages-and-reports` | How it thinks, claim tabs, History, Buildings explorer, 3D tour, HTML/JSON reports |
| `09-safety` | Retry never pays twice, reset and rerun, whole-app reset keeps pages live |

The Phantom wallet in `07` is a stand-in that signs real devnet transactions from the test process, so the app's real
signing path runs without the browser extension.
