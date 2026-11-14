# Plumbline architecture

Read left to right: **who uses it → where it runs → the app → the deep agent → models and data → records of what
happened**. Every external service the app talks to is in the right-hand columns.

## 1. The whole system

```
 PEOPLE / DEVICES            HOSTING                    APP (FastAPI, one process)                         DEEP AGENT (LangChain)                 MODELS & DATA SOURCES                     RECORDS & PROOF
 ────────────────            ───────                    ──────────────────────────                         ──────────────────────                 ─────────────────────                     ───────────────

 ┌──────────────────┐        ┌──────────────────────┐   ┌──────────────────────────────────────────┐     ┌──────────────────────────────┐      ┌──────────────────────────────┐        ┌───────────────────────────┐
 │ Owner / property │        │ Laptop (demo)        │   │ React + Vite frontend (frontend/dist)    │     │ Coordinator                  │      │ AWS Bedrock (us-east-1)      │        │ Tiger Cloud (TimescaleDB) │
 │ manager          │──┐     │  uvicorn :8787       │   │  Overview · Claims · Claim · Review      │     │  create_deep_agent()         │─────▶│  Nova Pro / Nova Lite        │        │  history_events           │
 ├──────────────────┤  │     │  Ollama gpt-oss:20b  │   │  How it thinks · History · Buildings     │     │  write_todos (plan, revised) │      │  (Claude Sonnet/Haiku once   │        │   (hypertable, compressed)│
 │ Rent reviewer    │──┤     └──────────┬───────────┘   │  Fool it (+ phone page, QR) · Tenant     │     │  task → 3 sub-agents         │      │   AWS approves; off for now) │        │  history_weekly           │
 ├──────────────────┤  │                │               │  Three.js PropertyScene                  │     │  /memories/  (vendors,       │      ├──────────────────────────────┤        │   (continuous aggregate)  │
 │ Lender           │──┼── HTTPS ──────▶│  or           │  Matterport Showcase SDK (3D tours)      │     │    buildings)                │─────▶│ Groq free tier               │        │  surcharge_registry       │
 ├──────────────────┤  │  (password)    ▼               │  @solana/web3.js (Phantom signing)       │     │  /evidence/<id>/ (files)     │      │  gpt-oss-120b / -20b, Qwen   │        │  claim_state (per host)   │
 │ Judge's phone    │──┤     ┌──────────────────────┐   └───────────────┬──────────────────────────┘     │  record_decision ── PAUSE ──┐│      ├──────────────────────────────┤        └─────────────▲─────────────┘
 │ (QR, mobile data)│  │     │ Vultr Cloud Compute  │                   │ /api/* JSON + /api/stream (SSE)│                             ││─────▶│ Ollama on the laptop         │                      │
 ├──────────────────┤  │     │ Ubuntu 24.04, NJ     │                   ▼                                │  records-clerk   roof-       ││      │  gpt-oss:20b (local, free)   │                      │ events, decisions,
 │ Phantom wallet   │──┘     │ ufw: 22, 80, 443     │   ┌──────────────────────────────────────────┐     │  (CoStar, bank,  inspector   ││      └──────────────────────────────┘                      │ paid/held, registry
 │ (Devnet, signs)  │        │ Caddy: HTTPS (Let's  │──▶│ main.py routes                           │     │   surcharges)    (Vexcel)    ││                                                            │ lookups
 └──────────────────┘        │  Encrypt), basic     │   │  claims · decision · judge · reset       │     │  interior-inspector          ││      ┌──────────────────────────────┐                      │
                             │  auth, SSE no-buffer │   │  routes_intake (upload)                  │     │  (Matterport, floor plans)   ││      │ CoStar hackathon kit         │         ┌────────────┴──────────────┐
 ┌──────────────────┐        │ systemd: plumbline   │   │  routes_kit  (5,245 properties)          │     └──────────────┬───────────────┘│      │  property + listing records  │         │ engine.py (in memory)     │
 │ Developer laptop │        │  (1 worker)          │   │  routes_data (Vexcel, Matterport)        │                    │ tool calls     │      │  kit_index, kit_dossiers     │         │  claims, status, steps,   │
 │  deploy/deploy.sh│─ SSH ─▶│ sslip.io hostname    │   │  routes_report (HTML, JSON, tenant)      │                    ▼                │      │  (Apartments.com floor plans)│         │  review, log, paused runs │
 │  (build, rsync,  │ rsync  │ /etc/plumbline.env   │   │  routes_solana (prepare/submit/verify)   │     ┌──────────────────────────────┐│      ├──────────────────────────────┤         │  rev never goes backwards │
 │   restart, check)│        └──────────────────────┘   └───────┬───────────────┬──────────────────┘     │ agent/tools.py               ││      │ Vexcel API                   │         └────────────┬──────────────┘
 └────────┬─────────┘                                           │               │                        │  get_building_record ────────┼┼─────▶│  ortho imagery, footprint,   │                      │
          │ git push                                            │               │                        │  check_vendor_account        ││      │  roof shape, AC units,       │                      │ approve / reject
          ▼                                                     ▼               ▼                        │  check_surcharge_history     ││      │  angled (oblique) counts     │                      ▼
 ┌──────────────────┐                             ┌──────────────────┐ ┌──────────────────────┐          │  measure_roof ───────────────┼┼─────▶├──────────────────────────────┤        ┌───────────────────────────┐
 │ GitHub           │                             │ intake.py        │ │ engine.py            │          │  count_rooftop_units_angled  ││      │ Matterport Model API         │        │ Solana devnet             │
 │ AniA201/Plumbline│                             │  pypdf / text /  │ │  queue, replay       │─────────▶│  list_scans · measure_rooms ─┼┼─────▶│  (GraphQL): scans, rooms,    │        │  SPL Token "Plumbline USD"│
 │ (private)        │                             │  .eml reader     │ │  runner ↔ agent      │ run_claim│  check_floor_plans           ││      │  room areas, scan dates      │        │  SPL multisig 2-of-2 hold │
 └──────────────────┘                             │  injection scan  │ │  rules overrule      │◀─────────│  average_unit_area           ││      └──────────────────────────────┘        │   (lender + Plumbline)    │
                                                  │  (Anthropic      │ │  Tiger hooks         │ steps,   │  compute_bill_split ─┐       ││                                              │  Memo: claim, amounts,    │
                                                  │   reader: off)   │ └─────────┬────────────┘ outcome  │  compute_verified_cost│ money.py      ┌──────────────────────────────┐        │   evidence SHA-256        │
                                                  └──────────────────┘           │                       │  compute_rent_surcharge│ (plain│      │ LangSmith (free)             │        │  Explorer links, Verify   │
                                                                                 │                       │  compute_draw_release ┘ code) ││      │  trace of every live run,    │        └─────────────▲─────────────┘
                                                                                 │                       │  record_decision (interrupt) ◀┘│      │  trace link on the page      │                      │
                                                                                 │                       └──────────────────────────────┘ │      └──────────────────────────────┘          solana_ledger.py
                                                                                 └────────────────────────────── traces ──────────────────┴─────────────────────────────────────────────── (after approval)
```

## 2. One check, end to end

```
 Document            Engine                   Deep agent                         Tools → data                          Decision                    Person              Afterwards
 ────────            ──────                   ──────────                         ────────────                          ────────                    ──────              ──────────
 fixture / upload ─▶ queue ─▶ run_claim() ─▶ prompt: kind, party,          ─▶  CoStar record, bank check,     ─▶  record_decision      ─▶  Review page   ─▶  resume same run
 / phone bill /      ACTIVE_CLAIMS[id]       building key, playbook,            surcharge registry,                 (PAUSE, interrupt_on)      approve / reject    (Command resume)
 incoming sample                             document lines (no answer)         Vexcel roof + AC units,           ─▶  outcome_from():          ──────────────▶    ├▶ memory saved
                                             │                                  Matterport rooms + plans               status from agent,                          ├▶ Solana receipt
                                             ├─ write_todos (plan v1, v2…)      ─▶ money.py math (only source          amounts from math only,                     │   (pay, hold, memo)
                                             ├─ read /memories/                    of dollar amounts)                  rules overrule if the                      └▶ Tiger: decision
                                             ├─ task → sub-agents                                                       agent contradicts them                         paid / held
                                             └─ write /evidence/<id>/                                                 ─▶ claim.outcome, agent,
                                                                                                                         evidence_files
 Every step on the way ─▶ engine._push_step ─▶ snapshot ─▶ /api/stream (SSE) ─▶ page updates live      (and ─▶ Tiger history_events, ─▶ LangSmith trace)
```

## 3. Model fallback (per model call, not per run)

```
 agent step ─▶ Bedrock primary ─▶ Bedrock backup ─▶ Groq (role model) ─▶ Ollama (laptop) / other Groq models (cloud) ─▶ retry rounds ─▶ recorded plan replays
               (off for now:      Nova Pro / Lite   gpt-oss-120b,         gpt-oss:20b, then a warmer retry              (cooldowns on
                PLUMBLINE_                          gpt-oss-20b, Qwen                                                     429 / throttling;
                BEDROCK=off)                                                                                               15 min skip if a
                                                                                                                           model isn't enabled)
```

## 4. Integrations checklist

| Integration | Where | Used for | Settings / keys (in `backend/.env`, never in git) |
|---|---|---|---|
| CoStar hackathon kit | `app/integrations/costar.py`, `app/real/*`, `routes_kit.py` | Property and listing records (password-protected kit zip, read by HTTP range requests), 5,245-property explorer, floor plans from Apartments.com listings, Homes listings | `COSTAR_KIT_ZIP` or `COSTAR_KIT_URL`, `COSTAR_ZIP_PASSWORD`; cached in `backend/app/data/real/` (gitignored) |
| Vexcel | `app/integrations/vexcel.py`, `routes_data.py` | Ortho imagery, footprint, roof shape/slope, AC unit counts (top-down and angled) | `VEXCEL_API_KEY` |
| Matterport Model API | `app/integrations/matterport.py` | Scans, rooms, room areas, scan dates (GraphQL) | `MATTERPORT_API_KEY`, `MATTERPORT_API_TOKEN` |
| Matterport Showcase SDK | `frontend/src/components/MatterportTour.jsx` | 3D tours with room pins (plain tour fallback) | `MATTERPORT_SDK_KEY` (browser-safe) |
| LangChain deepagents + LangGraph | `app/agent/` | Coordinator, sub-agents, planning, file system, memory store, interrupt/resume | — |
| AWS Bedrock | `app/agent/models.py` (langchain-aws) | First models in the chain (Nova; Claude when approved) | `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION`, `PLUMBLINE_BEDROCK` (off) |
| Groq | `app/agent/models.py` (langchain-groq) | Free models: gpt-oss-120b/20b, Qwen | `GROQ_API_KEY` |
| Ollama | `app/agent/models.py` (langchain-ollama) | Local free model on the laptop: gpt-oss:20b | `OLLAMA_URL` (default localhost) |
| LangSmith | `app/agent/tracing.py`, settings | Trace of every live run, link on the page | `LANGSMITH_API_KEY` |
| Tiger Cloud (TimescaleDB) | `app/tiger.py`, `engine.py`, History page | Event history, weekly aggregate, compression, surcharge registry, saved claims | `TIGER_DATABASE_URL` |
| Solana devnet | `app/solana_ledger.py`, `routes_solana.py`, `frontend/src/solana.js` | Pay/hold/memo transaction, 2-of-2 multisig hold, Verify, release | Wallet in `backend/app/data/solana/` (gitignored); fund at faucet.solana.com |
| Phantom wallet | Browser extension, Review page | The approver signs; the app pays fees | Phantom set to Devnet |
| Solana Explorer | Links on receipts | Public view of each transaction | — |
| Vultr | `deploy/` | Cloud server, HTTPS (Caddy + Let's Encrypt), firewall, systemd service | SSH key `~/.ssh/plumbline_vultr`; `SITE_PASSWORD`; `/etc/plumbline.env` (`PUBLIC_URL`, `PLUMBLINE_HOST`) |
| sslip.io | Hostname | Free HTTPS-capable address for the server IP | — |
| GitHub | `AniA201/Plumbline` (private) | Code, branches, pull requests | — |
| Anthropic API (bill reader) | `app/intake.py` | Optional AI reader for uploaded bills; **off** (rule reader used) | `ANTHROPIC_API_KEY` (not set) |
| Libraries | backend / frontend | FastAPI, Uvicorn, httpx, pydantic, pypdf, pyzipper, qrcode, psycopg, solana-py, solders; React, Vite, Three.js, @solana/web3.js | — |
