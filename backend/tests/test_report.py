import json

from fastapi.testclient import TestClient

from app.main import app


def run_to_end(client, cid):
    engine = app.state.engine
    claim = engine.find(cid)
    engine.steps[cid] = len(claim["steps"])
    engine.status[cid] = claim["outcome"]["status"]


def test_report_needs_a_finished_check():
    with TestClient(app) as client:
        client.post("/api/reset")
        assert client.get("/api/claims/CLM-2207/report").status_code == 409


def test_full_report_and_decision_record():
    with TestClient(app) as client:
        client.post("/api/reset")
        run_to_end(client, "CLM-2207")
        client.post("/api/claims/CLM-2207/decision", json={"action": "ok"})
        page = client.get("/api/claims/CLM-2207/report")
        assert page.status_code == 200 and "Two sources must agree" in page.text and "Approved" in page.text
        assert "Content-Disposition" not in page.headers
        dl = client.get("/api/claims/CLM-2207/report", params={"download": True})
        assert 'filename="plumbline-clm-2207.html"' in dl.headers["content-disposition"]
        rec = json.loads(client.get("/api/claims/CLM-2207/decision.json").text)
        assert rec["decision"]["pay_now"] == 58920 and rec["approved_by"] == "Approved"


def test_tenant_proof_only_for_rent_cases():
    with TestClient(app) as client:
        client.post("/api/reset")
        run_to_end(client, "RSO-3104")
        page = client.get("/api/claims/RSO-3104/report", params={"audience": "tenant"})
        assert page.status_code == 200 and "Your rent increase should be $20.33 a month." in page.text
        run_to_end(client, "CLM-2207")
        assert client.get("/api/claims/CLM-2207/report", params={"audience": "tenant"}).status_code == 400


def test_report_escapes_judge_text():
    with TestClient(app) as client:
        client.post("/api/reset")
        cid = client.post("/api/judge", json={"area": 9000, "amount": 1000, "bank": "4421", "hidden": "<script>alert(1)</script>"}).json()["id"]
        run_to_end(client, cid)
        assert "<script>alert(1)</script>" not in client.get(f"/api/claims/{cid}/report").text


def test_reset_keeps_the_state_version_moving_forward():
    with TestClient(app) as client:
        before = client.get("/api/state").json()["rev"]
        client.post("/api/claims/CLM-2207/run")
        after_reset = client.post("/api/reset").json()["rev"]
        assert after_reset > before
