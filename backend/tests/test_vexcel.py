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
