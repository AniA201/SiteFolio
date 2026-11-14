from fastapi.testclient import TestClient

from app.main import app


def test_matterport_routes_explain_missing_keys():
    from app import routes_data
    with TestClient(app) as client:
        if routes_data.settings.matterport_api_key:
            return  # a real key is configured locally; nothing to assert offline
        res = client.get("/api/data/matterport/models/abc/rooms")
        assert res.status_code == 503 and "MATTERPORT_API_KEY" in res.json()["detail"]


def test_health_lists_integrations():
    with TestClient(app) as client:
        body = client.get("/api/health").json()
        assert body["ok"] and "matterport" in body["integrations"]
