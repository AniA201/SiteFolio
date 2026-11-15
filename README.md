# SiteFolio

Check the paper against the building. SiteFolio reads a bill, rent increase application or loan draw request and checks every claim against three views of the same building (CoStar record, Vexcel aerial imagery, Matterport 3D scan), plus history in Tiger Data. Plain code does the money math, and a person approves.

## Layout

```
backend/    FastAPI API server: claim store, agent runner, rules, SSE stream
  app/main.py       routes
  app/engine.py     in-memory state + runner (replays scripted plans today; swap in the deep agent)
  app/rules.py      plain-code rules (Try to fool it invoice check, money math)
  app/calls.py      request/response record builders for the data calls
  app/money.py      roof slope/waste adjustment, bill splits, payment checks, LA rent and draw math
  app/settings.py   keys from backend/.env (see backend/.env.example)
  app/integrations/ Matterport (GraphQL + models_index.csv), Vexcel (ortho), CoStar (kit zip)
  app/routes_data.py /api/data routes onto the data layers
  tests/            pytest suite
  app/data/*.json   sample buildings, parties, personas, claims, surcharges
frontend/   React + Vite app
  src/pages/        Overview, Claims, ClaimDetail, Review, Tenant, History, Thinks, Fool
  src/components/   illustrations (aerial, floor plan, QR)
  src/useBackend.js live state over SSE
```

## Run locally

Backend (port 8787):

```bash
cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
```

```bash
cd backend && .venv/bin/uvicorn app.main:app --reload --port 8787
```

Keys: from `backend/`, run `.venv/bin/python setup_keys.py`. It asks for each key and file, saves them to `backend/.env` (gitignored), copies `models_index.csv` into place and tests every connection. You can also copy `backend/.env.example` to `backend/.env` by hand. `GET /api/health` shows which integrations are configured. Check them from `backend/`:

```bash
.venv/bin/python -m app.integrations.matterport
```

```bash
.venv/bin/python -m app.integrations.costar
```

Real buildings: after the keys are set, fetch and build the real data set (kept local in `backend/app/data/real/`, gitignored). The app loads it instead of the samples; set `PLUMBLINE_DATA=sample` to switch back.

```bash
.venv/bin/python -m scripts.scan_candidates
```

```bash
.venv/bin/python -m app.real.kit_index && .venv/bin/python -m app.real.fetch && .venv/bin/python -m app.real.build
```

`kit_index` indexes all 3,339 kit buildings for the Buildings page and joins each to its Apartments.com listing, current tenants, last sale and active listings.

Deep agent: each check runs the LangChain deep agent in `backend/app/agent/`. A coordinator plans with `write_todos`, sends three helper agents (roof inspector on Vexcel, interior inspector on Matterport, records clerk on the CoStar kit and vendor file), revises its plan when a check fails, writes an evidence folder, keeps long-term memory of vendors and buildings in `/memories/` (a LangGraph store saved to `backend/app/data/agent_memory.json`), and pauses at `record_decision` until a person approves or rejects in Review, which resumes the same run. Amounts always come from the plain-code math tools; if the agent's verdict contradicts the rules (blocking a bill whose bank account matches, or deciding without the math), the rules' result stands and the overrule is shown.

Models, tried in order for every call: **AWS Bedrock** when `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` and `AWS_REGION` are set (Claude Sonnet coordinates, Claude Haiku runs the helpers, Amazon Nova Pro/Lite as the Bedrock backup; Claude on Bedrock needs AWS's one-time Anthropic use-case form, Nova doesn't). A model the account can't use yet is skipped for 15 minutes instead of failing every step. Then the free models: Groq's free tier (`openai/gpt-oss-120b` for the coordinator, smaller Groq models for the helpers, each with its own per-minute budget), and on any rate limit, timeout or malformed tool call that single step falls over to Ollama on this machine (`gpt-oss:20b`). If both fail, the recorded plan replays. Set `GROQ_API_KEY`, run `ollama pull gpt-oss:20b`, and optionally `LANGSMITH_API_KEY` (free plan) for a trace link on every run. `PLUMBLINE_AGENT=replay` forces the recorded plans. Check the agent against the rules on every demo claim:

```bash
.venv/bin/python -m scripts.eval_agent
```

Tests:

```bash
cd backend && .venv/bin/pip install -r requirements-dev.txt && .venv/bin/python -m pytest -q
```

Frontend (port 5180, proxies `/api` to 8787; set `PLUMBLINE_API` to point elsewhere):

```bash
cd frontend && npm install && npm run dev
```

Production: `npm run build` in `frontend/`, then the backend serves `frontend/dist` at `/`.

## Click-through tests
Every scenario in [docs/TESTING.md](docs/TESTING.md) runs in a visible Chromium window with Playwright: `cd e2e && npm install && npx playwright install chromium && npm test`. See [e2e/README.md](e2e/README.md).

## API

| Method | Path | What it does |
| --- | --- | --- |
| GET | `/api/meta` | Buildings, parties, personas, surcharge registry |
| GET | `/api/state` | Full claim state snapshot |
| GET | `/api/stream` | Server-sent events, one snapshot per change |
| POST | `/api/claims/run-all` | `{persona}` queue every waiting claim |
| POST | `/api/claims/ingest` | `{sample_id}` add a new claim and queue it |
| POST | `/api/claims/{id}/run` | Run one claim |
| POST | `/api/claims/{id}/reset` | Reset one claim |
| POST | `/api/claims/{id}/retry` | Idempotent payment retry |
| POST | `/api/claims/{id}/decision` | `{action: "ok" \| "sent" \| "rejected" \| null}` |
| POST | `/api/judge` | `{area, amount, bank, hidden}` Try to fool it bill |
| POST | `/api/reset` | Restore the starting state |
| GET | `/api/health` | Which integrations have keys (booleans only) |
| GET | `/api/data/matterport/models/near` | `lat, lon, radius_m` models from models_index.csv |
| GET | `/api/data/matterport/models/{id}` | Model basics |
| GET | `/api/data/matterport/models/{id}/rooms` | Rooms with labels and areas in sq ft |
| GET | `/api/data/vexcel/ortho.jpg` | `lat, lon, half_side_m, pixels` aerial image |
| GET | `/api/kit/search` | `q, city, type, scanned` search every building in the CoStar kit |
| GET | `/api/kit/buildings/{id}` | One kit building: record, dossier, live Vexcel roof facts and the CoStar cross-check |
| GET | `/api/data/vexcel/property` | `lat, lon` footprint, roof shape/material/condition, rooftop AC count |

With the real data built, buildings and measurements are real (CoStar kit, Vexcel, Matterport); parties, bills, bank accounts and surcharge history are sample data. Without it, everything is sample data.

## Solana: receipts and payments (devnet, free)
Every decision a person approves in Review becomes one Solana devnet transaction that does three things at once:
1. pays the verified amount to the contractor or builder (in "SiteFolio USD", a test token we mint on devnet),
2. moves the unproven amount into a holding account owned by a **2-of-2 SPL Token multisig** (the lender and
   SiteFolio's verifier), so neither can release it alone,
3. records a memo with the claim id, the decision, the amounts and a **SHA-256 fingerprint of the evidence**.

The agent never holds a key. The approver signs with **Phantom** (Review → Connect Phantom); without Phantom, a demo
lender key on this laptop signs instead. **Verify** recomputes the fingerprint and compares it with the one on chain;
**Edit the evidence (demo)** shows it turn red. When a later scan proves the remaining work, **release** moves the held
money with both signatures and a new receipt. Blocks, rejections and rent decisions are receipts only (no money).

Setup (free, devnet only): the app wallet is created at `backend/app/data/solana/app_wallet.json` (gitignored) on first
use; fund its address with devnet SOL at https://faucet.solana.com (`GET /api/solana/status` shows the address and
balance). Phantom needs no SOL: the app pays the fees. Set `PLUMBLINE_SOLANA=off` to turn it off.
Live check of the whole flow on devnet, with a test key standing in for Phantom: `cd backend && .venv/bin/python -m scripts.solana_smoke`.
Evidence is sealed at approval, so notes the agent writes after it resumes never break Verify; an edited evidence file does.
Approved decisions can't be undone in Review once they're on Solana, and the exported report and `decision.json` carry the receipt.

## Tiger Data history
Set `TIGER_DATABASE_URL` (a Tiger Cloud connection string) in `backend/.env`. On start the app creates:
- `history_events`, a **hypertable** of every check step, decision and amount paid or held, with **columnar
  compression** for events older than a week;
- `history_weekly`, a **continuous aggregate** of events, paid and held per week and user type (History page chart,
  with the dashboard's query time shown);
- `surcharge_registry`, seeded with the city's active surcharges; a rent increase for work that is already being
  charged is **denied** (the double-charge check);
- `claim_state`, so claims and decisions survive a restart.
Writes go through one background thread and one connection, so checks never wait on the database. Tests against a real
TimescaleDB: `TIGER_TEST_URL=postgresql://... pytest tests/test_tiger.py` (see the file for a local Docker command).

## Deploy on Vultr
The app runs on a Vultr Cloud Compute server (Ubuntu 24.04, 2 vCPU / 4 GB, New Jersey) behind Caddy, which serves
HTTPS automatically and asks for a site password. Live demo: https://66-135-21-65.sslip.io (user `plumbline`, password
`SITE_PASSWORD` in `backend/.env`).

- `deploy/deploy.sh <ip>` builds the frontend, copies the app, keys (`backend/.env`), CoStar data and Solana wallet over
  SSH (never through git), installs packages, restarts the service and checks `/api/health`.
- First time only: `deploy/deploy.sh <ip> --setup <hostname> <site-password>` installs Python and Caddy, turns on the
  firewall (SSH and HTTPS only), and sets up the `plumbline` service ([deploy/plumbline.service](deploy/plumbline.service)).
- One worker on purpose: live state is in memory. Server settings (`PUBLIC_URL`) live in `/etc/plumbline.env`.
- No Ollama on the server: when Groq's free per-minute limit is hit, the agent falls back across the other free Groq
  models and waits out the minute; if that still fails, it replays the recorded plan. Run one live check at a time.
- Logs: `ssh root@<ip> journalctl -u plumbline -f`. Delete the server after the hackathon to stop the credits.

## Open-source credits
- Agent: [deepagents](https://github.com/langchain-ai/deepagents), LangChain, LangGraph; tracing in LangSmith (free tier).
- Models: AWS Bedrock (Anthropic Claude, Amazon Nova) via langchain-aws; OpenAI gpt-oss (open weights) and Qwen on Groq's free tier; Ollama on the laptop.
- Backend: FastAPI, Uvicorn, httpx, pydantic, pypdf, pyzipper, qrcode.
- Frontend: React, Vite, Three.js; Matterport Showcase SDK for the 3D tours.
- Hosting: Vultr Cloud Compute, Caddy, sslip.io.
- Solana: solana-py, solders, @solana/web3.js, SPL Token and Memo programs, Phantom wallet (devnet).
- Data: CoStar hackathon kit, Vexcel aerial imagery, Matterport scans (used under the hackathon's terms; not in this repo).
