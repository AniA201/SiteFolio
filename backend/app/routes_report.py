"""Report routes: the evidence report (HTML, prints to PDF) and the decision record (JSON) for a checked claim."""
import json
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, Response

from .report import decision_record, render

router = APIRouter(prefix="/api/claims")
FINAL = {"approved", "partial", "reduced", "denied", "blocked"}


def _checked_claim(request: Request, cid: str) -> tuple[dict, str | None, int]:
    engine = request.app.state.engine
    claim = engine.find(cid)
    if not claim:
        raise HTTPException(404, f"Unknown claim {cid}")
    if engine.status.get(cid) not in FINAL:
        raise HTTPException(409, "Run the agent on this claim first; the report is written once the checks finish.")
    return claim, engine.review.get(cid), engine.steps.get(cid, 0)


@router.get("/{cid}/report", response_class=HTMLResponse)
def report(request: Request, cid: str, audience: Literal["full", "tenant"] = "full", download: bool = False):
    claim, review, steps = _checked_claim(request, cid)
    if audience == "tenant" and not claim.get("rent"):
        raise HTTPException(400, "The tenant proof is only for rent increase applications.")
    headers = {"Content-Disposition": f'attachment; filename="plumbline-{cid.lower()}{"-tenant" if audience == "tenant" else ""}.html"'} if download else {}
    return HTMLResponse(render(claim, review, steps, audience), headers=headers)


@router.get("/{cid}/decision.json")
def decision(request: Request, cid: str):
    claim, review, _ = _checked_claim(request, cid)
    body = json.dumps(decision_record(claim, review), indent=2, ensure_ascii=False)
    return Response(body, media_type="application/json",
                    headers={"Content-Disposition": f'attachment; filename="plumbline-{cid.lower()}-decision.json"'})
