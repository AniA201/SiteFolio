import json

from app.agent import tools as T
from app.agent.agent import SUBAGENTS, build_agent, claim_prompt
from app.fixtures import CLAIMS


def test_tools_use_plain_code_math():
    assert json.loads(T.compute_bill_split(87000, 14500, 9820, roof_pitch_deg=0))["pay"] == 58920
    assert json.loads(T.compute_rent_surcharge(90400, 24))["per_unit_per_month"] == 31.39
    assert json.loads(T.compute_draw_release(400000, 9, 12)) == {"release": 300000, "hold": 100000}


def test_records_and_roof_tools():
    rec = json.loads(T.get_building_record("wc"))
    assert rec["floor_plate_sqft"] == 9820 and rec["name"] == "Westheimer Commons"
    assert json.loads(T.measure_roof("Westheimer Commons"))["footprint_sqft"] == 9820
    swap = json.loads(T.check_vendor_account("Lone Star Roofing", "9914"))
    assert swap["blocked"] and swap["approved_account"] == "••4421"


def test_unknown_building_lists_known_ones():
    try:
        T.get_building_record("nowhere")
    except ValueError as e:
        assert "wc (Westheimer Commons)" in str(e)


def test_agent_graph_builds_with_helpers_and_pause():
    from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
    from langchain_core.messages import AIMessage

    class FakeToolModel(GenericFakeChatModel):
        def bind_tools(self, tools, **kw):
            return self

    graph = build_agent(model=FakeToolModel(messages=iter([AIMessage(content="ok")])))
    assert graph is not None
    assert {s["name"] for s in SUBAGENTS} == {"records-clerk", "roof-inspector", "interior-inspector"}


def test_prompt_shows_the_document_not_the_answer():
    c = next(c for c in CLAIMS if c["id"] == "CLM-2207")
    p = claim_prompt(c)
    assert "14500" in p and "58920" not in p and "partial" not in p


def test_runner_maps_tool_calls_and_stops_at_the_decision():
    from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
    from langchain_core.messages import AIMessage

    from app.agent.runner import outcome_from, run_claim

    class FakeToolModel(GenericFakeChatModel):
        def bind_tools(self, tools, **kw):
            return self

    script = iter([
        AIMessage(content="", tool_calls=[{"name": "write_todos", "id": "t1", "args": {"todos": [
            {"content": "Get the building record", "status": "pending"}, {"content": "Measure the roof", "status": "pending"}]}}]),
        AIMessage(content="", tool_calls=[{"name": "compute_bill_split", "id": "t2",
                                           "args": {"amount": 87000, "claimed": 14500, "verified": 9820, "roof_pitch_deg": 0}}]),
        AIMessage(content="", tool_calls=[{"name": "record_decision", "id": "t3", "args": {
            "claim_id": "CLM-2207", "status": "partial", "pay": 58920, "hold": 28080, "reason": "Roof is 9,820 sq ft."}}]),
        AIMessage(content="done"),
    ])
    claim = next(c for c in CLAIMS if c["id"] == "CLM-2207")
    steps = []
    proposed = run_claim(claim, steps.append, model=FakeToolModel(messages=script))
    assert proposed["pay"] == 58920 and proposed["hold"] == 28080
    assert steps[0][1].startswith("Plan: Get the building record") and any("verified share" in s[1] for s in steps)
    out = outcome_from(proposed, claim)
    assert out["a"] == ["Pay now", 58920, "green"] and out["b"] == ["Hold", 28080, "amber"]


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
