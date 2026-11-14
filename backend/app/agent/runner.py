"""Run the deep agent on one claim and turn what it does into the app's step list, live.

Each tool call becomes a step (who did it, what, which data source); the to-do list becomes the plan. The run
stops at record_decision, which is gated for a person; the proposed decision becomes the claim's outcome.
"""
from __future__ import annotations

import json
import uuid
from typing import Callable

from .agent import build_agent, claim_prompt

SUBAGENT_WHO = {"records-clerk": "records", "roof-inspector": "roof", "interior-inspector": "interior"}
TOOL_STEP = {
    "get_building_record": ("records", "Get the building record", "CoStar"),
    "check_vendor_account": ("records", "Check bank account and past payments", "Tiger Data"),
    "measure_roof": ("roof", "Measure the roof from above", "Vexcel"),
    "count_rooftop_units_angled": ("roof", "Count again from angled views", "Vexcel"),
    "list_scans": ("interior", "List the 3D scans", "Matterport"),
    "measure_rooms": ("interior", "Measure rooms in the 3D scan", "Matterport"),
    "compute_bill_split": ("rules", "Math: pay the verified share", None),
    "compute_rent_surcharge": ("rules", "Rent math: 50% over 60 months", None),
    "compute_draw_release": ("rules", "Release math: verified share", None),
    "record_decision": ("coordinator", "Propose the decision and pause for a person", None),
}


def _steps_for(tool: str, args: dict) -> list:
    if tool == "write_todos":
        todos = args.get("todos") or []
        return [["coordinator", "Plan: " + "; ".join(t.get("content", "") for t in todos)[:180], "done"]]
    if tool == "task":
        who = SUBAGENT_WHO.get(args.get("subagent_type"), "coordinator")
        return [[who, (args.get("description") or "Helper task")[:160], "done"]]
    who, text, svc = TOOL_STEP.get(tool, ("coordinator", tool.replace("_", " "), None))
    return [[who, text, "done", svc] if svc else [who, text, "done"]]


def run_claim(claim: dict, on_step: Callable[[list], None], model=None) -> dict | None:
    """Run until the agent pauses at record_decision. Returns the proposed decision args, or None if it never got there."""
    graph = build_agent(model=model)
    config = {"configurable": {"thread_id": f"{claim['id']}-{uuid.uuid4().hex[:8]}"}, "recursion_limit": 80}
    proposed = None
    stream = graph.stream({"messages": [{"role": "user", "content": claim_prompt(claim)}]}, config,
                          stream_mode="updates", subgraphs=True)  # subgraphs: also see what each helper does
    for item in stream:
        update = item[1] if isinstance(item, tuple) else item
        for node, data in (update or {}).items():
            if node == "__interrupt__":
                for intr in data:
                    for req in (getattr(intr, "value", None) or {}).get("action_requests", []):
                        if req.get("name") == "record_decision":
                            proposed = req.get("args") or req.get("arguments")
                continue
            for msg in (data or {}).get("messages", []) if isinstance(data, dict) else []:
                for call in getattr(msg, "tool_calls", None) or []:
                    for step in _steps_for(call["name"], call.get("args") or {}):
                        on_step(step)
    if isinstance(proposed, str):
        proposed = json.loads(proposed)
    return proposed


def outcome_from(proposed: dict, claim: dict) -> dict:
    status = proposed.get("status", "partial")
    pay, hold = proposed.get("pay", 0), proposed.get("hold", 0)
    labels = {"blocked": (["Paid", "gray"], ["Stopped", "red"]), "approved": (["Paid", "green"], ["Held", "gray"])}
    (al, ac), (bl, bc) = labels.get(status, (["Pay now", "green"], ["Hold", "amber"]))
    return {**claim["outcome"], "status": status, "a": [al, pay, ac], "b": [bl, hold, bc], "reason": proposed.get("reason", "")}
