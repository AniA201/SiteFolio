"""Plumbline API server.

Run: uvicorn app.main:app --reload --port 8787   (from backend/)
"""
import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .engine import Engine
from .fixtures import BUILDINGS, META, PARTIES, PERSONAS, SURCHARGES, USING_REAL
from .routes_data import router as data_router
from .routes_report import router as report_router
from .routes_intake import router as intake_router
from .routes_kit import router as kit_router
from .settings import settings
from .tiger import TigerHistory

engine: Engine
tiger = TigerHistory()


@asynccontextmanager
async def lifespan(_: FastAPI):
    global engine
    tiger.initialize()
    engine = Engine(history=tiger)
    _.state.engine = engine
    engine.start()
    yield
    await engine.stop()


app = FastAPI(title="Plumbline API", lifespan=lifespan)


class RunAll(BaseModel):
    persona: Literal["owner", "reviewer", "lender"]


class Decision(BaseModel):
    action: Literal["ok", "sent", "rejected"] | None = None


class Ingest(BaseModel):
    sample_id: str


class JudgeBill(BaseModel):
    area: int = Field(ge=0, le=10_000_000)
    amount: int = Field(ge=0, le=1_000_000_000)
    bank: str = Field(pattern=r"^\d{4}$")
    hidden: str = Field(default="", max_length=2000)


def _claim_or_404(cid: str) -> dict:
    claim = engine.find(cid)
    if not claim:
        raise HTTPException(404, f"Unknown claim {cid}")
    return claim


# ---------- read ----------
@app.get("/api/health")
def health():
    return {"ok": True, "integrations": settings.integrations()}


@app.get("/api/meta")
def meta():
    return {"buildings": BUILDINGS, "parties": PARTIES, "personas": PERSONAS, "surcharges": SURCHARGES,
            "meta": META, "real": USING_REAL,
            # Browser-safe by design (Matterport SDK keys are domain-locked); every other key stays server-side.
            "matterport_sdk_key": settings.matterport_sdk_key, "public_url": settings.public_url,
            "has_ai_reader": bool(settings.anthropic_api_key)}


@app.get("/api/state")
def state():
    return engine.snapshot()


@app.get("/api/history/{persona}")
def history(persona: Literal["owner", "reviewer", "lender"]):
    return tiger.dashboard(persona)


@app.get("/api/stream")
async def stream(request: Request):
    """Server-sent events: one full state snapshot per change."""
    q = engine.subscribe()

    async def gen():
        try:
            yield f"data: {json.dumps(engine.snapshot(), ensure_ascii=False)}\n\n"
            while not await request.is_disconnected():
                try:
                    snap = await asyncio.wait_for(q.get(), timeout=15)
                    yield f"data: {json.dumps(snap, ensure_ascii=False)}\n\n"
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
        finally:
            engine.unsubscribe(q)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ---------- actions (each returns the new snapshot) ----------
@app.post("/api/claims/run-all")
def run_all(body: RunAll):
    engine.run_all(body.persona)
    return engine.snapshot()


@app.post("/api/claims/ingest")
def ingest(body: Ingest):
    cid = engine.ingest(body.sample_id)
    if not cid:
        raise HTTPException(404, "Sample already used or unknown")
    tiger.record(cid, _claim_or_404(cid)["persona"], "document_ingested")
    return {"id": cid, "state": engine.snapshot()}


@app.post("/api/claims/{cid}/run")
def run(cid: str):
    claim = _claim_or_404(cid)
    engine.run(cid)
    tiger.record(cid, claim["persona"], "check_started")
    return engine.snapshot()


@app.post("/api/claims/{cid}/reset")
def reset(cid: str):
    _claim_or_404(cid)
    engine.reset(cid)
    return engine.snapshot()


@app.post("/api/claims/{cid}/retry")
def retry(cid: str):
    _claim_or_404(cid)
    engine.mark_retry(cid)
    return engine.snapshot()


@app.post("/api/claims/{cid}/decision")
def decision(cid: str, body: Decision):
    claim = _claim_or_404(cid)
    engine.decide(cid, body.action)
    tiger.record(cid, claim["persona"], "decision", {"action": body.action})
    return engine.snapshot()


@app.post("/api/judge")
def judge(body: JudgeBill):
    cid = engine.judge(body.area, body.amount, body.bank, body.hidden)
    tiger.record(cid, "owner", "document_ingested")
    return {"id": cid, "state": engine.snapshot()}


@app.post("/api/reset")
def reset_everything():
    """Restore the demo to its starting state."""
    tiger.clear_claims()
    engine.reset_all()
    engine._changed()
    return engine.snapshot()


app.include_router(data_router)
app.include_router(report_router)
app.include_router(intake_router)
app.include_router(kit_router)


# ---------- built frontend (production) ----------
DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}")
    def spa(path: str):
        return FileResponse(DIST / "index.html")
