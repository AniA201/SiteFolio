import json

import httpx
import pytest

from app.integrations.vexcel import ORTHO_URL, VexcelClient, VexcelError, square_wkt

# The request the quick start sends for 5836 La Mirada Ave (34.0934917, -118.3171)
QUICKSTART_WKT = ("POLYGON((-118.31785932808691 34.092862882177506,-118.31634067191308 34.092862882177506,"
                  "-118.31634067191308 34.094120517822496,-118.31785932808691 34.094120517822496,"
                  "-118.31785932808691 34.092862882177506))")


def parse(wkt):
    return [tuple(map(float, p.split())) for p in wkt[len("POLYGON(("):-2].split(",")]


def test_square_matches_quickstart_request():
    for (x1, y1), (x2, y2) in zip(parse(square_wkt(34.0934917, -118.3171)), parse(QUICKSTART_WKT)):
        assert x1 == pytest.approx(x2, abs=2e-7) and y1 == pytest.approx(y2, abs=2e-7)


def client(status, content=b"\xff\xd8jpeg", ctype="image/jpeg", seen=None):
    def handler(req):
        if seen is not None:
            seen.append(req)
        return httpx.Response(status, content=content, headers={"content-type": ctype})
    return VexcelClient("vx-key", http=httpx.Client(transport=httpx.MockTransport(handler)))


def test_ortho_request_shape():
    seen = []
    img = client(200, seen=seen).ortho(34.0934917, -118.3171)
    req = seen[0]
    assert img.startswith(b"\xff\xd8") and str(req.url) == ORTHO_URL
    assert req.headers["x-api-key"] == "vx-key"
    body = json.loads(req.content)
    assert body["srid"] == 4326 and body["destination-dimensions"] == "1400,1400" and body["crop"] == "bounding_box"


def test_outside_coverage_is_explained():
    with pytest.raises(VexcelError, match="Houston and Los Angeles"):
        client(403).ortho(40.35, -74.65)


def test_non_image_reply_is_an_error():
    with pytest.raises(VexcelError, match="instead of an image"):
        client(200, content=b'{"error":"x"}', ctype="application/json").ortho(29.7, -95.4)


def test_missing_key():
    with pytest.raises(VexcelError, match="VEXCEL_API_KEY"):
        VexcelClient("")


PROPERTY = {"features": [{"properties": {
    "metadata.collection": "us-tx-cypress-2026", "request-information.inside-parcel": True, "structure.count": 2,
    "structures": [
        {"primary-structure": True, "footprint.area": 74416.2, "roof-characteristics.shape.value": "flat",
         "roof-characteristics.material.class": "gravel", "roof-characteristics.condition": 2.0,
         "roof-characteristics.condition.precise-value": 2.31, "roof-objects.ac-unit.count": 26, "building-type.class": "commercial"},
        {"primary-structure": False, "footprint.area": 1200.0, "roof-objects.ac-unit.count": None},
    ]}}]}


def test_property_facts():
    seen = []

    def handler(req):
        seen.append(req)
        return httpx.Response(200, json=PROPERTY)
    facts = VexcelClient("k", http=httpx.Client(transport=httpx.MockTransport(handler))).property(29.8502572, -95.5340642)
    assert seen[0].url.params["wkt"] == "POINT(-95.5340642 29.8502572)"  # longitude first
    assert seen[0].url.params["unit-system"] == "imperial"
    p = facts.primary
    assert (p.footprint_sqft, p.roof_shape, p.roof_material, p.roof_condition, p.ac_units) == (74416.2, "flat", "gravel", 2.31, 26)
    assert facts.total_footprint_sqft == 75616.2 and facts.total_ac_units == 26


def test_property_404_means_no_parcel():
    c = VexcelClient("k", http=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(404, json={}))))
    assert c.property(29.7, -95.4) is None


def test_rate_limit_retried_with_backoff():
    calls, slept = [], []

    def handler(req):
        calls.append(1)
        return httpx.Response(429) if len(calls) < 3 else httpx.Response(200, json=PROPERTY)
    c = VexcelClient("k", http=httpx.Client(transport=httpx.MockTransport(handler)), sleep=slept.append)
    assert c.property(29.85, -95.53).primary.ac_units == 26
    assert len(calls) == 3 and len(slept) == 2 and 1 <= slept[0] < 2 and 2 <= slept[1] < 3
