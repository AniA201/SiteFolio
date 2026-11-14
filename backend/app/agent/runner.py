"""Run the deep agent on one claim and turn what it does into the app's live step list.

Every tool call (the coordinator's and each helper's) becomes a step; each write_todos becomes a plan version, so a
plan that changes mid-run is visible; money-tool results are kept so the payout comes from plain code; the run stops at
record_decision for a person and resume() continues the same run after Review.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from typing import Callable

from .agent import build_agent, claim_prompt, save_memory
from .tools import MONEY_TOOLS

SUBAGENT_WHO = {"records-clerk": "records", "roof-inspector": "roof", "interior-inspector": "interior"}
TOOL_STEP = {
    "get_building_record": ("records", "Get the building record", "CoStar"),
    "check_vendor_account": ("records", "Check the bank account on file", None),
    "check_surcharge_history": ("records", "Check for an existing surcharge", "Tiger Data"),
    "measure_roof": ("roof", "Measure the roof from above", "Vexcel"),
    "count_rooftop_units_angled": ("roof", "Count rooftop units again from angled views", "Vexcel"),
    "list_scans": ("interior", "List the building's 3D scans", "Matterport"),
    "measure_rooms": ("interior", "Measure rooms in a 3D scan", "Matterport"),
    "check_floor_plans": ("interior", "Check which floor plans are finished", "Matterport"),
    "average_unit_area": ("interior", "Average the apartments' measured area", "Matterport"),
    "compute_bill_split": ("rules", "Math: pay the verified share", None),
    "compute_verified_cost": ("rules", "Math: re-price at verified quantities", None),
    "compute_rent_surcharge": ("rules", "Rent math: 50% over 60 months", None),
    "compute_draw_release": ("rules", "Release math: verified share", None),
    "record_decision": ("coordinator", "Propose the decision and pause for a person", None),
}


@dataclass
class Run:
    claim_id: str
    graph: object
    config: dict
    run_id: str
    proposed: dict | None = None
    plans: list[list[dict]] = field(default_factory=list)
    money: list[dict] = field(default_factory=list)
    calls: list[dict] = field(default_factory=list)  # every data and math tool result, for the evidence folder
    files: dict[str, str] = field(default_factory=dict)
    memory: dict[str, str] = field(default_factory=dict)
    served: list[str] = field(default_factory=list)
    models: list = field(default_factory=list)
    finished: bool = False


def _short(v, n=60) -> str:
    s = str(v)
    return s if len(s) <= n else s[:n - 1] + "…"


def _steps_for(tool: str, args: dict, plans: list) -> list:
    if tool == "write_todos":
        todos = args.get("todos") or []
        changed = len(plans) > 1
        text = ("Plan updated: " if changed else "Plan: ") + "; ".join(t.get("content", "") for t in todos)
        return [["coordinator", _short(text, 200), "warn" if changed else "done"]]
    if tool == "task":
        who = SUBAGENT_WHO.get(args.get("subagent_type"), "coordinator")
        return [[who, "Assigned: " + _short(args.get("description") or "helper task", 150), "done"]]
    if tool in ("read_file", "write_file", "edit_file", "ls", "glob", "grep"):
        path = args.get("file_path") or args.get("path") or args.get("pattern") or ""
        if "/memories/" in str(path):
            verb = "Recall from memory" if tool in ("read_file", "ls", "glob", "grep") else "Update memory"
            return [["coordinator", f"{verb}: {_short(str(path).replace('/memories/', ''), 70)}", "done"]]
        if "/evidence/" in str(path) and tool in ("write_file", "edit_file"):
            return [["coordinator", f"Write evidence: {_short(str(path).split('/evidence/')[-1], 70)}", "done"]]
        return []
    who, text, svc = TOOL_STEP.get(tool, ("coordinator", tool.replace("_", " "), None))
    detail = args.get("building") or args.get("model_id") or args.get("claim_id") or ""
    text = f"{text} ({_short(detail, 40)})" if detail and tool not in MONEY_TOOLS else text
    return [[who, text, "done", svc] if svc else [who, text, "done"]]


def _drain(run: Run, stream, on_step: Callable[[list], None]) -> None:
    calls: dict[str, tuple[str, dict]] = {}
    for item in stream:
        update = item[1] if isinstance(item, tuple) else item
        for node, data in (update or {}).items():
            if node == "__interrupt__":
                for intr in data:
                    for req in (getattr(intr, "value", None) or {}).get("action_requests", []):
                        if req.get("name") == "record_decision":
                            a = req.get("args") or req.get("arguments") or {}
                            run.proposed = json.loads(a) if isinstance(a, str) else a
                continue
            for msg in (data or {}).get("messages", []) if isinstance(data, dict) else []:
                for call in getattr(msg, "tool_calls", None) or []:
                    args = call.get("args") or {}
                    calls[call.get("id")] = (call["name"], args)
                    if call["name"] == "write_todos":
                        run.plans.append([{"content": t.get("content", ""), "status": t.get("status", "pending")} for t in args.get("todos") or []])
                    for step in _steps_for(call["name"], args, run.plans):
                        on_step(step)
                if getattr(msg, "type", "") == "tool" and getattr(msg, "name", "") in TOOL_STEP and msg.name != "record_decision":
                    try:
                        result = json.loads(msg.content)
                    except (TypeError, ValueError):
                        continue
                    name, args = calls.get(getattr(msg, "tool_call_id", None), (msg.name, {}))
                    run.calls.append({"tool": name, "args": args, "result": result})
                    if name not in MONEY_TOOLS or "error" in result:
                        continue
                    run.money.append({"tool": name, "args": args, "result": result})
                    held = result.get("hold", 0) or 0
                    if held:
                        on_step(["rules", f"Math result: pay or release {result.get('pay', result.get('release'))}, hold {held}", "warn"])


NUDGE = ("Continue with your plan now: send the helpers you still need, use the math tool, write the evidence file, "
         "and finish by calling record_decision for claim {claim_id}. Do not stop before record_decision.")


def _paused(run: Run) -> bool:
    try:
        return bool(run.graph.get_state(run.config).interrupts)
    except Exception:
        return False


def _system_evidence(run: Run) -> dict[str, str]:
    """The evidence folder Plumbline always keeps: the plan as it changed, each data call's result, the decision."""
    base = f"/evidence/{run.claim_id}/"
    files = {}
    if run.plans:
        files[base + "plan.md"] = "\n\n".join(
            f"## Plan v{i + 1}{' (changed mid-run)' if i else ''}\n" + "\n".join(f"- [{t['status']}] {t['content']}" for t in p)
            for i, p in enumerate(run.plans))
    for n, c in enumerate(run.calls, 1):
        files[f"{base}{n:02d}_{c['tool']}.json"] = json.dumps({"args": c["args"], "result": c["result"]}, indent=2)
    if run.proposed:
        files[base + "decision.md"] = (f"# Proposed decision\n- status: {run.proposed.get('status')}\n- reason: {run.proposed.get('reason')}\n"
                                        f"- amounts: from the math tools only\n- waiting for: a person to approve, edit or reject\n")
    return files


def _collect(run: Run) -> None:
    try:
        values = run.graph.get_state(run.config).values
    except Exception:
        values = {}
    for path, f in (values.get("files") or {}).items():
        content = f.get("content") if isinstance(f, dict) else f
        run.files[path] = "\n".join(content) if isinstance(content, list) else str(content)
    run.files = {**_system_evidence(run), **{k: v for k, v in run.files.items() if k.startswith("/evidence/")}}
    run.memory = save_memory()


def run_claim(claim: dict, on_step: Callable[[list], None], model=None, sub_models=None) -> Run:
    """Run until the agent pauses at record_decision (or finishes)."""
    if model is None:  # free models, kept here so we can tell which provider answered each step
        from .models import free_model
        model = free_model("coordinator")
        sub_models = {r: free_model(r) for r in ("records", "roof", "interior")}
    run_models = [model, *(sub_models or {}).values()]
    graph = build_agent(model=model, sub_models=sub_models)
    run_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": f"{claim['id']}-{run_id[:8]}"}, "recursion_limit": 120, "run_id": run_id,
              "run_name": f"Plumbline check {claim['id']}", "tags": ["plumbline", claim.get("persona", "")],
              "metadata": {"claim_id": claim["id"], "building": claim["b"]}}
    run = Run(claim_id=claim["id"], graph=graph, config=config, run_id=run_id)
    from .tools import ACTIVE_CLAIMS
    ACTIVE_CLAIMS[claim["id"]] = claim
    stream = graph.stream({"messages": [{"role": "user", "content": claim_prompt(claim)}]}, config,
                          stream_mode="updates", subgraphs=True)
    _drain(run, stream, on_step)
    for _ in range(2):  # small models sometimes end their turn early: ask them to finish, same thread
        if run.proposed or _paused(run):
            break
        on_step(["coordinator", "Not finished yet: continue the plan", "warn"])
        _drain(run, graph.stream({"messages": [{"role": "user", "content": NUDGE.format(claim_id=claim["id"])}]}, config,
                                 stream_mode="updates", subgraphs=True), on_step)
    _collect(run)
    run.served = _served(run_models)
    run.models = run_models
    return run


def resume(run: Run, decision: str, on_step: Callable[[list], None], note: str | None = None) -> Run:
    """Continue the paused run with the person's decision (approve or reject) from Review."""
    from langgraph.types import Command
    d = {"type": "approve"} if decision in ("ok", "sent") else {"type": "reject", "message": note or "The reviewer rejected this decision."}
    config = {**run.config, "run_id": str(uuid.uuid4()), "run_name": f"Plumbline resume {run.claim_id}"}
    skip_repeat = lambda step: None if step[1].startswith("Propose the decision") else on_step(step)  # already shown before the pause
    _drain(run, run.graph.stream(Command(resume={"decisions": [d]}), config, stream_mode="updates", subgraphs=True), skip_repeat)
    _collect(run)
    run.served += _served(getattr(run, "models", []))
    run.finished = True
    return run


def _served(models: list) -> list[str]:
    names = []
    for m in models:
        names.extend(getattr(m, "served", None) or [])
        if getattr(m, "served", None):
            m.served.clear()
    return names


VALID = {"approved", "partial", "reduced", "denied", "blocked"}
# The verdicts each kind of claim can have; anything else the model says is mapped onto them.
DRAW_STATUS = {"approved": "approved", "partial": "partial", "reduced": "partial", "blocked": "partial", "denied": "partial"}
KIND_STATUS = {"draw": DRAW_STATUS, "drawroof": DRAW_STATUS, "rent": {"reduced": "reduced", "partial": "reduced", "denied": "denied", "blocked": "denied", "approved": "approved"},
               "rentdup": {"reduced": "reduced", "partial": "reduced", "denied": "denied", "blocked": "denied", "approved": "approved"}}
BILL_STATUS = {"reduced": "partial", "denied": "blocked", "partial": "partial", "blocked": "blocked", "approved": "approved"}


def _dollars(v) -> float | None:
    try:
        return float(str(v).replace("$", "").replace("/mo", "").replace(",", ""))
    except ValueError:
        return None


def _active_surcharge(run: Run, claim: dict) -> bool:
    """Plain-code registry lookup: the agent's own call if it made one, otherwise the rules check it themselves."""
    seen = [c["result"] for c in run.calls if c["tool"] == "check_surcharge_history" and "error" not in c["result"]]
    if any(r.get("active_surcharge") for r in seen):
        return True
    from . import tools as T
    try:
        return bool(json.loads(T.check_surcharge_history(claim["b"], claim.get("work") or "roof")).get("active_surcharge"))
    except Exception:
        return False


def outcome_from(run: Run, claim: dict) -> dict:
    """The decision shown to the person: the agent's verdict and reason, amounts from the money tools only."""
    rec = claim["outcome"]
    proposed = run.proposed or {}
    raw = str(proposed.get("status", "")).lower().strip()
    status = KIND_STATUS.get(claim.get("kind"), BILL_STATUS).get(raw) if raw in VALID else rec["status"]
    reason = proposed.get("reason") or rec["reason"]
    amount = claim["amount"]
    last = lambda tool: next((m["result"] for m in reversed(run.money) if m["tool"] == tool), None)
    out = {**rec, "status": status, "reason": reason}
    kind = claim.get("kind")
    # The rules overrule the agent when its verdict contradicts the plain-code checks.
    bank = [c["result"] for c in run.calls if c["tool"] == "check_vendor_account" and "error" not in c["result"]]
    bank_blocked = any(r.get("blocked") for r in bank)
    bills = kind not in ("rent", "rentdup", "draw", "drawroof")
    needs_math = {"rent": "compute_rent_surcharge", "draw": "compute_draw_release", "drawroof": "compute_draw_release"}.get(
        kind, "compute_bill_split" if bills else None)
    if bills and status == "blocked" and bank and not bank_blocked:
        return {**rec, "overruled": "The agent blocked the bill, but the bank account matches the approved one; "
                                    "only a changed account blocks a bill. The rules' result stands."}
    if bills and bank_blocked and status != "blocked":
        return {**rec, "overruled": "The bank account isn't the approved one, so the bill is blocked whatever the agent proposed."}
    if kind == "rentdup" and status != "denied" and _active_surcharge(run, claim):
        return {**rec, "overruled": "The surcharge registry shows this work is already being charged to tenants, so a second "
                                    "charge is denied whatever the agent proposed."}
    if kind == "rent" and status not in ("denied",):
        rents = [m["result"]["per_unit_per_month"] for m in run.money if m["tool"] == "compute_rent_surcharge"]
        expect = _dollars(rec["b"][1])
        if rents and expect and abs(min(rents) - expect) > max(0.5, 0.02 * expect):
            return {**rec, "overruled": f"The agent's rent math used inputs that don't match the verified quantities "
                                        f"(${min(rents):.2f} vs ${expect:.2f} a month), so the rules' amount stands."}
    if needs_math and status not in ("blocked", "denied") and not any(m["tool"] in (needs_math, "compute_verified_cost") for m in run.money):
        return {**rec, "overruled": "The agent decided without running the math tool, so the plain-code rules' amounts stand."}
    if kind in ("rent", "rentdup"):
        rents = [m["result"]["per_unit_per_month"] for m in run.money if m["tool"] == "compute_rent_surcharge"]
        claimed = max(rents) if rents else (claim.get("rent") or {}).get("claimed", 0)
        verified = 0 if status == "denied" else (min(rents) if rents else (claim.get("rent") or {}).get("verified", 0))
        out["a"] = ["Claimed", f"${claimed:.2f}/mo", "gray"]
        out["b"] = ["Verified", f"${verified:.2f}/mo" if verified else "$0", "red" if status == "denied" else "amber" if verified < claimed else "green"]
        if status == "approved" and verified >= claimed:
            out["b"][2] = "green"
        if claim.get("rent"):
            claim["rent"] = {**claim["rent"], "claimed": claimed, "verified": verified}
    elif kind in ("draw", "drawroof"):
        r = last("compute_draw_release")
        release, hold = (r["release"], r["hold"]) if r else ((amount, 0) if status == "approved" else (0, amount))
        out["a"], out["b"] = ["Release", release, "green"], ["Hold", hold, "amber" if hold else "gray"]
        if hold and status == "approved":
            out["status"] = "partial"
    else:
        if status == "blocked":
            out["a"], out["b"] = ["Paid", 0, "gray"], ["Stopped", amount, "red"]
        else:
            r = last("compute_bill_split")
            v = last("compute_verified_cost")
            if r:
                pay, hold = r["pay"], r["hold"]
            elif v:  # the model re-priced the bill instead of splitting it: same plain-code math
                pay = min(round(v["verified_cost"]), round(amount)); hold = round(amount) - pay
            else:
                pay, hold = (amount, 0) if status == "approved" else (0, amount)
            if not hold and status == "partial":
                out["status"] = "approved"
            if hold and status == "approved":
                out["status"] = "partial"
            out["a"] = ["Pay now" if hold else "Paid", pay, "green" if pay else "gray"]
            out["b"] = ["Hold" if hold else "Held", hold, "amber" if hold else "gray"]
    return out
