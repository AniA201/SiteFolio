"""Solana routes: prepare a transaction for the approver's wallet, submit it, release held money, verify evidence.

When no wallet is connected, approving in Review records the decision with the demo lender key in the background
(after_decision below), so the demo never waits on devnet.
"""
from __future__ import annotations

import asyncio
import base64
import copy
import os
import threading
import time

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from . import solana_ledger as L

router = APIRouter(prefix="/api/solana")
_pending: dict[str, dict] = {}   # claim id -> the message we built, so a wallet can't swap in another transaction


class Prepare(BaseModel):
    action: str = Field(default="decision", pattern="^(decision|release)$")
    decision: str = Field(default="ok", pattern="^(ok|sent|rejected)$")
    wallet: str | None = Field(default=None, max_length=64)


class Submit(BaseModel):
    action: str = Field(default="decision", pattern="^(decision|release)$")
    tx: str = Field(max_length=4000)


def _engine(request: Request):
    return request.app.state.engine


def _claim(request: Request, cid: str) -> dict:
    claim = _engine(request).find(cid)
    if not claim:
        raise HTTPException(404, "Unknown claim")
    return claim


def _changed(engine) -> None:
    loop = getattr(engine, "_event_loop", None)
    if loop and loop.is_running():
        loop.call_soon_threadsafe(engine._changed)
    else:
        engine._changed()


def _record(engine, claim: dict, action: str, signature: str, info: dict, signer: str) -> None:
    if action == "release":
        claim["solana"].update(released=True, release_signature=signature, release_explorer=L.explorer("tx", signature),
                               release_sha256=info["sha256"], release_amount=info["amount"])
    else:
        info = dict(info)
        claim["sealed_files"] = info.pop("sealed", None) or {}
        claim["solana"] = {"state": "recorded", "signature": signature, "explorer": L.explorer("tx", signature),
                           "signer": signer, "at": time.strftime("%Y-%m-%d %H:%M"), **info}
    _changed(engine)


def _fail(engine, claim: dict, action: str, error: Exception) -> None:
    msg = f"{type(error).__name__}: {error}"[:300]
    if action == "release":
        claim["solana"].update(release_error=msg, release_sent=getattr(error, "signature", None), release_info=getattr(error, "info", None))
    else:
        claim["solana"] = {"state": "failed", "error": msg, "sent": getattr(error, "signature", None),
                           "info": getattr(error, "info", None), "signer": getattr(error, "signer", None)}
    _changed(engine)


def after_decision(engine, cid: str, decision: str | None) -> None:
    """Called after Review records a decision. Records it on Solana in the background unless a wallet already did."""
    if os.environ.get("PLUMBLINE_SOLANA", "on") == "off":
        return
    claim = engine.find(cid)
    if not claim or not decision or (claim.get("solana") or {}).get("state") in ("recorded", "pending"):
        return
    claim["solana"] = {"state": "pending", "signer": "demo lender key"}

    def work():
        out = None
        try:
            out = L.prepare(claim, decision, None)
            _record(engine, claim, "decision", L.submit(out["raw"]), out["info"], out["signer"])
        except Exception as e:
            if out:
                e.info, e.signer = out["info"], out["signer"]
            _fail(engine, claim, "decision", e)
    threading.Thread(target=work, daemon=True).start()


@router.get("/status")
def status():
    return L.status()


@router.post("/claims/{cid}/prepare")
def prepare(cid: str, body: Prepare, request: Request):
    claim = _claim(request, cid)
    sol = claim.get("solana") or {}
    if body.action == "decision" and sol.get("state") in ("recorded", "pending"):
        raise HTTPException(409, "Already recorded on Solana.")
    if body.action == "decision" and sol.get("sent") and sol.get("info") and L.landed(sol["sent"]):
        _record(_engine(request), claim, "decision", sol["sent"], sol["info"], sol.get("signer") or "demo lender key")
        return {"signature": sol["sent"], "explorer": L.explorer("tx", sol["sent"])}
    if body.action == "release" and sol.get("release_sent") and sol.get("release_info") and L.landed(sol["release_sent"]):
        _record(_engine(request), claim, "release", sol["release_sent"], sol["release_info"], "")
        return {"signature": sol["release_sent"], "explorer": L.explorer("tx", sol["release_sent"])}
    try:
        out = L.prepare(claim, body.decision, body.wallet, body.action)
    except L.LedgerError as e:
        raise HTTPException(400, str(e))
    if "raw" in out:  # demo lender key: sign and send right here
        try:
            sig = L.submit(out["raw"])
        except Exception as e:
            e.info, e.signer = out["info"], out["signer"]
            _fail(_engine(request), claim, body.action, e)
            raise HTTPException(502, f"Devnet refused the transaction: {e}")
        _record(_engine(request), claim, body.action, sig, out["info"], out["signer"])
        return {"signature": sig, "explorer": L.explorer("tx", sig)}
    from solders.transaction import Transaction
    _pending[f"{cid}:{body.action}"] = {"message": bytes(Transaction.from_bytes(base64.b64decode(out["tx"])).message),
                                        "info": out["info"]}
    return {"tx": out["tx"], "info": out["info"]}


@router.post("/claims/{cid}/submit")
def submit(cid: str, body: Submit, request: Request):
    claim = _claim(request, cid)
    want = _pending.pop(f"{cid}:{body.action}", None)
    if not want:
        raise HTTPException(409, "Prepare the transaction first.")
    raw = base64.b64decode(body.tx)
    try:
        L.check_signed(raw, want["message"])
        sig = L.submit(raw)
    except L.LedgerError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(502, f"Devnet refused the transaction: {e}")
    _record(_engine(request), claim, body.action, sig, want["info"], "Phantom")
    return {"signature": sig, "explorer": L.explorer("tx", sig)}


@router.get("/claims/{cid}/verify")
def verify(cid: str, request: Request):
    claim = _claim(request, cid)
    try:
        return L.verify(claim)
    except L.LedgerError as e:
        raise HTTPException(400, str(e))


@router.post("/claims/{cid}/tamper")
def tamper(cid: str, request: Request):
    """Demo only: change one checked number in memory (toggle) so Verify can show a mismatch."""
    claim = _claim(request, cid)
    if "untampered_lines" in claim:
        claim["lines"] = claim.pop("untampered_lines")
        tampered = False
    else:
        claim["untampered_lines"] = copy.deepcopy(claim["lines"])
        line = claim["lines"][0]
        line[2] = line[1]  # make the verified value agree with the claimed one
        tampered = True
    _changed(_engine(request))
    return {"tampered": tampered}
