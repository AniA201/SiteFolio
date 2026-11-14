"""Matterport client against the response shapes published in the hackathon quick start (trimmed)."""
import base64
import json

import httpx
import pytest

from app.integrations.matterport import (GRAPH_URL, MatterportClient, MatterportError, ModelIndex, parse_rooms,
                                         rooms_labelled, total_sqft)

ROOMS_RESPONSE = {"data": {"model": {
    "floors": [{"id": "f1", "label": "Floor 1"}],
    "rooms": [
        {"id": "r1", "floor": {"id": "f1"}, "classifications": [{"label": "Void", "confidence": 1.0}]},
        {"id": "r2", "floor": {"id": "f1"}, "classifications": [{"label": "Dining Room", "confidence": 1.0}],
         "dimensions": {"areaFloor": 22.709, "width": 4.4, "depth": 4.84, "height": 2.68}},
        {"id": "r3", "floor": {"id": "f1"}, "classifications": [{"label": "Hallway", "confidence": 0.9}],
         "dimensions": {"areaFloor": 3.03}},
        {"id": "r4", "floor": {"id": "f1"}, "classifications": [{"label": "Hallway", "confidence": 0.8}],
         "dimensions": {"areaFloor": 2.29}},
    ]}}}


def client_returning(status: int, body: dict, seen: list):
    def handler(request: httpx.Request):
        seen.append(request)
        return httpx.Response(status, json=body)
    return MatterportClient("key", "secret", http=httpx.Client(transport=httpx.MockTransport(handler)))


def test_rooms_query_uses_basic_auth_and_converts_to_sqft():
    seen = []
    rooms = client_returning(200, ROOMS_RESPONSE, seen).rooms("zvKHR9DHNjJ")
    req = seen[0]
    assert str(req.url) == GRAPH_URL
    assert req.headers["authorization"] == "Basic " + base64.b64encode(b"key:secret").decode()
    assert json.loads(req.content)["variables"] == {"id": "zvKHR9DHNjJ"}
    halls = rooms_labelled(rooms, "hallway")
    assert [r.id for r in halls] == ["r3", "r4"]
    assert round(total_sqft(halls), 1) == round((3.03 + 2.29) * 10.7639, 1)
    assert rooms[0].area_sqft is None and rooms[1].floor_label == "Floor 1"


def test_bad_key_gives_plain_message():
    with pytest.raises(MatterportError, match="rejected the key"):
        client_returning(401, {}, []).key_check()


def test_graphql_errors_surface():
    with pytest.raises(MatterportError, match="no model"):
        client_returning(200, {"errors": [{"message": "no model"}]}, []).basics("x")


def test_missing_keys_refused():
    with pytest.raises(MatterportError, match="not set"):
        MatterportClient("", "")


def test_parse_rooms_takes_most_confident_label():
    rooms = parse_rooms({"rooms": [{"id": "a", "classifications": [{"label": "Closet", "confidence": 0.2},
                                                                  {"label": "Bedroom", "confidence": 0.7}]}]})
    assert rooms[0].label == "Bedroom"


def test_model_index_near_and_costar_join(tmp_path):
    p = tmp_path / "models_index.csv"
    p.write_text("sid,name,segment,lat,lon,costar_property_id,homes_listing_id\n"
                 "zvKHR9DHNjJ,5836 La Mirada Ave,residential,34.0934917,-118.3171,,221139020\n"
                 "far,Somewhere,commercial,29.737,-95.42,48213,\n"
                 "nogeo,No location,commercial,,,1,\n")
    idx = ModelIndex.load(p)
    assert len(idx.models) == 2
    hits = idx.near(34.0935, -118.3171, radius_m=50)
    assert [m.sid for _, m in hits] == ["zvKHR9DHNjJ"]
    assert idx.by_costar_id("48213")[0].sid == "far"
    assert hits[0][1].homes_listing_id == "221139020"
