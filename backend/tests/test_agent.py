import json

import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage

from app.agent import agent as agent_mod
from app.agent import tools as T
from app.agent.agent import SUBAGENTS, build_agent, claim_prompt
from app.fixtures import CLAIMS


class FakeToolModel(GenericFakeChatModel):
    def bind_tools(self, tools, **kw):
        return self


SCRIPT: list = []  # replies for ScriptedModel; module-level so copies of the model share one script


class ScriptedModel(GenericFakeChatModel):
    """Replies from SCRIPT in order. deepagents copies models internally, which drains a one-pass iterator."""

    def bind_tools(self, tools, **kw):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        from langchain_core.outputs import ChatGeneration, ChatResult
        msg = SCRIPT.pop(0) if SCRIPT else AIMessage(content="done")
        return ChatResult(generations=[ChatGeneration(message=msg)])


@pytest.fixture(autouse=True)
def isolated_memory(tmp_path, monkeypatch):
    """Never touch the real agent memory file."""
    monkeypatch.setattr(agent_mod, "MEMORY_FILE", tmp_path / "agent_memory.json")
    monkeypatch.setattr(agent_mod, "_store", None)


def claim(cid):
    return json.loads(json.dumps(next(c for c in CLAIMS if c["id"] == cid)))


def call(name, args, i):
    return AIMessage(content="", tool_calls=[{"name": name, "id": f"t{i}", "args": args}])


def test_tools_use_plain_code_math():
    assert json.loads(T.compute_bill_split(87000, 14500, 9820, roof_shape="flat"))["pay"] == 58920
    assert json.loads(T.compute_rent_surcharge(90400, 24))["per_unit_per_month"] == 31.39
    assert json.loads(T.compute_draw_release(400000, 9, 12)) == {"release": 300000, "hold": 100000}
    lines = [{"claimed_qty": 10800, "amount": 64800, "verified_qty": 7200}]
    assert json.loads(T.compute_verified_cost(lines))["verified_cost"] == 43200


def test_tools_read_facts_from_the_claim_and_forgive_loose_input():
    T.ACTIVE_CLAIMS["CLM-2223"] = claim("CLM-2223")
    swap = json.loads(T.check_vendor_account("clm-2223"))
    assert swap["blocked"] and swap["approved_account"] == "••4421" and swap["pay_to"] == "••9914"
    assert json.loads(T.measure_roof("key wc"))["footprint_sqft"] == 9820
    assert json.loads(T.get_building_record("Westheimer Commons"))["floor_plate_sqft"] == 9820


def test_tool_errors_come_back_as_text():
    out = json.loads(T.get_building_record("nowhere"))
    assert "wc (Westheimer Commons)" in out["error"]


def test_angled_count_says_not_to_add_counts():
    assert "angled" in T.count_rooftop_units_angled("wc") or "note" in json.loads(T.count_rooftop_units_angled("wc"))


def test_agent_graph_builds_with_planning_helpers_memory_and_pause():
    graph = build_agent(model=FakeToolModel(messages=iter([AIMessage(content="ok")])), sub_models={})
    assert graph is not None
    assert {s["name"] for s in SUBAGENTS} == {"records-clerk", "roof-inspector", "interior-inspector"}
    mem = agent_mod.save_memory()
    assert any("Lone Star Roofing" in k for k in mem)  # seeded from the vendor file


def test_prompt_shows_the_document_and_playbook_not_the_answer():
    p = claim_prompt(claim("CLM-2207"))
    assert "14500" in p and "compute_bill_split" in p and "58920" not in p and "partial" in p


def run_scripted(cid, script):
    from app.agent.runner import outcome_from, run_claim
    c = claim(cid)
    steps = []
    SCRIPT[:] = list(script)
    run = run_claim(c, steps.append, model=ScriptedModel(messages=iter([])), sub_models={})
    return c, run, steps, outcome_from(run, c)


def test_runner_tracks_plan_changes_money_and_evidence():
    c, run, steps, out = run_scripted("CLM-2207", [
        call("write_todos", {"todos": [{"content": "Measure the roof", "status": "in_progress"}]}, 1),
        call("write_todos", {"todos": [{"content": "Measure the roof", "status": "completed"},
                                       {"content": "Draft a note to the contractor", "status": "pending"}]}, 2),
        call("compute_bill_split", {"amount": 87000, "claimed": 14500, "verified": 9820, "roof_shape": "flat"}, 3),
        call("record_decision", {"claim_id": "CLM-2207", "status": "partial", "reason": "Roof is 9,820 sq ft."}, 4),
        AIMessage(content="done"),
    ])
    assert run.proposed["status"] == "partial" and len(run.plans) == 2
    assert any(s[1].startswith("Plan updated") and s[2] == "warn" for s in steps)
    assert out["a"] == ["Pay now", 58920, "green"] and out["b"] == ["Hold", 28080, "amber"]
    assert "/evidence/CLM-2207/plan.md" in run.files and "/evidence/CLM-2207/decision.md" in run.files


def test_amounts_come_from_the_tools_not_the_model():
    c, run, steps, out = run_scripted("CLM-2207", [
        call("compute_bill_split", {"amount": 87000, "claimed": 14500, "verified": 9820, "roof_shape": "flat"}, 1),
        call("record_decision", {"claim_id": "CLM-2207", "status": "approved", "reason": "Pay it all."}, 2),
        AIMessage(content="done"),
    ])
    assert out["status"] == "partial" and out["a"][1] == 58920  # the model said approve-all; the math holds the difference


def test_rules_overrule_a_wrong_block():
    T.ACTIVE_CLAIMS.clear()
    c, run, steps, out = run_scripted("CLM-2214", [
        call("task", {"subagent_type": "records-clerk", "description": "Check the bank account for claim CLM-2214"}, 1),
        call("check_vendor_account", {"claim_id": "CLM-2214"}, 2),       # the records clerk's tool
        AIMessage(content='{"account_matches": true}'),                    # the clerk reports back
        call("record_decision", {"claim_id": "CLM-2214", "status": "blocked", "reason": "Too many units."}, 3),
    ])
    assert any(s[0] == "records" for s in steps)
    assert out.get("overruled") and out["status"] == c["outcome"]["status"]


def test_review_resumes_the_paused_run():
    from app.agent.runner import resume
    c, run, steps, out = run_scripted("CLM-2223", [
        call("task", {"subagent_type": "records-clerk", "description": "Check the bank account for claim CLM-2223"}, 1),
        call("check_vendor_account", {"claim_id": "CLM-2223"}, 2),
        AIMessage(content='{"blocked": true}'),
        call("record_decision", {"claim_id": "CLM-2223", "status": "blocked", "reason": "New account."}, 3),
        AIMessage(content="Logged the approval."),
    ])
    assert out["status"] == "blocked" and run.proposed
    resume(run, "ok", steps.append)
    assert run.finished


def test_free_model_falls_back_per_call(monkeypatch):
    from langchain_core.messages import HumanMessage

    from app.agent.models import FreeChatModel

    class Broken(GenericFakeChatModel):
        def _generate(self, *a, **k):
            raise RuntimeError("Error code: 429 - Rate limit reached. Please try again in 1.5s")

    ok = GenericFakeChatModel(messages=iter([AIMessage(content="from ollama")]))
    m = FreeChatModel(chain=[Broken(messages=iter([])), ok], names=["Groq x", "Ollama y"], served=[])
    assert m.invoke([HumanMessage(content="hi")]).content == "from ollama"
    assert m.served == ["Ollama y"]


def test_engine_falls_back_to_replay_when_the_agent_fails(monkeypatch):
    import asyncio

    from app import engine as eng
    from app.agent import runner
    from app.settings import Settings

    monkeypatch.setattr(Settings, "agent_enabled", property(lambda self: True))
    monkeypatch.setattr(runner, "run_claim", lambda *a, **k: (_ for _ in ()).throw(ConnectionError("offline")))
    monkeypatch.setattr(eng, "STEP_DELAY", 0)

    async def go():
        e = eng.Engine()
        e.start()
        e.run("CLM-2207")
        for _ in range(200):
            await asyncio.sleep(0.01)
            if e.status.get("CLM-2207") == "partial":
                break
        await e.stop()
        return e

    e = asyncio.run(go())
    assert e.status["CLM-2207"] == "partial" and e.steps["CLM-2207"] == len(e.find("CLM-2207")["steps"])
    assert any("replaying the recorded plan" in l["text"] for l in e.log)


def test_draws_are_never_blocked_and_need_the_release_math():
    c, run, steps, out = run_scripted("DRW-0412", [
        call("compute_draw_release", {"requested": 400000, "verified_done": 9, "claimed_done": 12}, 1),
        call("record_decision", {"claim_id": "DRW-0412", "status": "blocked", "reason": "Not finished."}, 2),
    ])
    assert out["status"] == "partial" and out["a"][1] == 300000 and out["b"][1] == 100000
    c, run, steps, out = run_scripted("DRW-0415", [
        call("record_decision", {"claim_id": "DRW-0415", "status": "partial", "reason": "Roof done."}, 1),
    ])
    assert out.get("overruled") and out["status"] == c["outcome"]["status"]


def test_draw_release_rejects_swapped_arguments():
    assert "error" in json.loads(T.compute_draw_release(600000, 10, 600000))
    assert json.loads(T.compute_draw_release(600000, 10, 13)) == {"release": 461538, "hold": 138462}


def test_cloud_without_ollama_falls_back_across_free_groq_models(monkeypatch):
    from app.agent import models as M
    monkeypatch.setattr(M, "ollama_ready", lambda: False)
    import dataclasses
    monkeypatch.setattr(M, "settings", dataclasses.replace(M.settings, groq_api_key="test-key"))
    m = M.free_model("coordinator")
    assert m.patient and len(m.names) == len(set(M.ROLE_GROQ_MODEL.values())) and m.names[0].endswith(M.ROLE_GROQ_MODEL["coordinator"])


def test_bedrock_comes_first_with_free_models_behind_it(monkeypatch):
    import dataclasses

    from app.agent import models as M
    monkeypatch.setenv("PLUMBLINE_BEDROCK", "on")
    monkeypatch.setattr(M, "ollama_ready", lambda: False)
    monkeypatch.setattr(M, "settings", dataclasses.replace(M.settings, aws_access_key_id="AKIATEST", groq_api_key="test-key"))
    coord, helper = M.free_model("coordinator"), M.free_model("roof")
    assert coord.names[:2] == ["Bedrock Claude Sonnet 4.6", "Bedrock Nova Pro"] and any(n.startswith("Groq") for n in coord.names)
    assert helper.names[:2] == ["Bedrock Claude Haiku 4.5", "Bedrock Nova Lite"]


def test_a_model_the_account_cannot_use_is_skipped_for_a_while():
    from app.agent.models import _cooldown_seconds
    assert _cooldown_seconds(RuntimeError("Model use case details have not been submitted for this account")) >= 600
    assert _cooldown_seconds(RuntimeError("ThrottlingException: Too many requests")) == 20.0


def test_rules_deny_a_duplicate_rent_charge_the_agent_approved():
    cid = next(c["id"] for c in CLAIMS if c["kind"] == "rentdup")
    c, run, steps, out = run_scripted(cid, [
        call("compute_rent_surcharge", {"cost": 90400, "units": 24}, 1),
        call("record_decision", {"claim_id": cid, "status": "approved", "reason": "Looks fine."}, 2),
    ])
    assert out.get("overruled") and out["status"] == "denied"


def test_rules_keep_the_rent_amount_when_the_agent_used_the_wrong_cost():
    cid = next(c["id"] for c in CLAIMS if c["kind"] == "rent")
    c, run, steps, out = run_scripted(cid, [
        call("compute_rent_surcharge", {"cost": 1000, "units": 24}, 1),
        call("record_decision", {"claim_id": cid, "status": "reduced", "reason": "Reduced."}, 2),
    ])
    assert out.get("overruled") and out["b"] == c["outcome"]["b"]
