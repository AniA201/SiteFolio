# Plumbline

Check the paper against the building. Plumbline reads a bill, rent increase application or loan draw request and checks every claim against three views of the same building (CoStar record, Vexcel aerial imagery, Matterport 3D scan), plus history in Tiger Data. Plain code does the money math, and a person approves.

## Layout

```
backend/    FastAPI API server: claim store, agent runner, rules, SSE stream
  app/main.py       routes
  app/engine.py     in-memory state + runner (replays scripted plans today; swap in the deep agent)
  app/rules.py      plain-code rules (Try to fool it invoice check, money math)
  app/calls.py      request/response record builders for the data calls
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

All buildings, parties and numbers are sample data.
