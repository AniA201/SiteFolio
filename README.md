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
| GET | `/api/data/vexcel/property` | `lat, lon` footprint, roof shape/material/condition, rooftop AC count |

All buildings, parties and numbers are sample data.
