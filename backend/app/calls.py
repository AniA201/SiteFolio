"""Builders for the request/response records shown on the "Building data calls" tab.

Each record is {svc, who, title, req, resp}. Today they describe mocked calls;
the same shape should be produced by the real CoStar / Vexcel / Matterport /
Tiger Data clients.
"""
import json

from .fixtures import BUILDINGS


def dump(o) -> str:
    return json.dumps(o, indent=2, ensure_ascii=False)


def num(x) -> str:
    """Render a number the way JavaScript's String(x) does (no trailing .0)."""
    if isinstance(x, float) and x.is_integer():
        return str(int(x))
    return str(x)


def ai(file: str, out: dict) -> dict:
    return {
        "svc": "AI model", "who": "coordinator", "title": "Read the document",
        "req": f"file: {file}\ntask: extract parties, building,\n      claimed work, amounts, pay_to",
        "resp": dump(out),
    }


def costar(b: str, extra: dict | None = None) -> dict:
    B = BUILDINGS[b]
    resp = {"property_id": B["cs"], "name": B["name"], "property_type": B["type"],
            "building_sf": B["size"], "stories": B["floors"]}
    if B.get("units"):
        resp["units"] = B["units"]
    resp["year_built"] = B["built"]
    if B.get("status"):
        resp["status"] = B["status"]
    resp.update(lat=B["lat"], lon=B["lon"], **(extra or {}))
    return {
        "svc": "CoStar", "who": "records", "title": "Get the building record",
        "req": f"GET /properties/search\n  ?address={B['name']},\n   {B['city']}",
        "resp": dump(resp),
    }


def vexcel(b: str, include: str, out: dict) -> dict:
    B = BUILDINGS[b]
    return {
        "svc": "Vexcel", "who": "roof", "title": "Look from above",
        "req": f"GET /imagery/roof\n  ?lat={num(B['lat'])}&lon={num(B['lon'])}\n  &include={include}",
        "resp": dump(out),
    }


def tiger(sql: str, out: dict) -> dict:
    return {"svc": "Tiger Data", "who": "records", "title": "Check history", "req": sql, "resp": dump(out)}
