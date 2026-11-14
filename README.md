# Plumbline

Check the paper against the building. Plumbline reads a bill, rent increase application or loan draw request and checks every claim against three views of the same building (CoStar record, Vexcel aerial imagery, Matterport 3D scan), plus history in Tiger Data. Plain code does the money math, and a person approves.

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

Deep agent (free models only): each check runs the LangChain deep agent in `backend/app/agent/`. A coordinator plans with `write_todos`, sends three helper agents (roof inspector on Vexcel, interior inspector on Matterport, records clerk on the CoStar kit and vendor file), revises its plan when a check fails, writes an evidence folder, keeps long-term memory of vendors and buildings in `/memories/` (a LangGraph store saved to `backend/app/data/agent_memory.json`), and pauses at `record_decision` until a person approves or rejects in Review, which resumes the same run. Amounts always come from the plain-code math tools; if the agent's verdict contradicts the rules (blocking a bill whose bank account matches, or deciding without the math), the rules' result stands and the overrule is shown.

Models cost nothing: Groq's free tier first (`openai/gpt-oss-120b` for the coordinator, smaller Groq models for the helpers, each with its own per-minute budget), and on any rate limit, timeout or malformed tool call that single step falls over to Ollama on this machine (`gpt-oss:20b`). If both fail, the recorded plan replays. Set `GROQ_API_KEY`, run `ollama pull gpt-oss:20b`, and optionally `LANGSMITH_API_KEY` (free plan) for a trace link on every run. `PLUMBLINE_AGENT=replay` forces the recorded plans. Check the agent against the rules on every demo claim:

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

## Open-source credits
- Agent: [deepagents](https://github.com/langchain-ai/deepagents), LangChain, LangGraph; tracing in LangSmith (free tier).
- Free models: OpenAI gpt-oss (open weights) and Qwen, served by Groq's free tier, with fallback to Ollama on the laptop.
- Backend: FastAPI, Uvicorn, httpx, pydantic, pypdf, pyzipper, qrcode.
- Frontend: React, Vite, Three.js; Matterport Showcase SDK for the 3D tours.
- Data: CoStar hackathon kit, Vexcel aerial imagery, Matterport scans (used under the hackathon's terms; not in this repo).
