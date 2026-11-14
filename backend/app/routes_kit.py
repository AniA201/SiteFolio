"""Building explorer over the whole CoStar kit: search every building, open one with its dossier and live Vexcel facts.

Reads app/data/real/kit_index.json and kit_dossiers.json (built by `python -m app.real.kit_index`).
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query

from .integrations.vexcel import VexcelClient, VexcelError
from .settings import settings

router = APIRouter(prefix="/api/kit")
REAL = Path(__file__).resolve().parent / "data" / "real"


@lru_cache(maxsize=1)
def kit() -> tuple[list[dict], dict[str, dict]]:
    idx, dos = REAL / "kit_index.json", REAL / "kit_dossiers.json"
    if not idx.exists():
        return [], {}
    return json.loads(idx.read_text()), (json.loads(dos.read_text()) if dos.exists() else {})


def _words(s: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", (s or "").lower())


def search(q: str = "", city: str | None = None, ptype: str | None = None, scanned: bool = False, limit: int = 25) -> list[dict]:
    index, dossiers = kit()
    terms = _words(q)
    hits = []
    for b in index:
        if city and b["city"] != city or ptype and b["type"] != ptype or scanned and not b["models"]:
            continue
        hay = " ".join(_words(f"{b['name']} {b['address']} {b['id']}"))
        if terms and not all(t in hay for t in terms):
            continue
        score = sum(3 if f" {t} " in f" {hay} " else 1 for t in terms) + (1 if b["models"] else 0)
        hits.append((score, b))
    hits.sort(key=lambda x: (-x[0], -(x[1]["models"]), x[1]["name"]))
    return [{k: b[k] for k in ("id", "name", "address", "city", "type", "stories", "units", "gba_sqft", "year_built", "models")}
            | {"has_rents": bool((dossiers.get(b["id"]) or {}).get("apartments")),
               "tenants": ((dossiers.get(b["id"]) or {}).get("tenants") or {}).get("count", 0)} for _, b in hits[:limit]]


def find(pid: str) -> dict | None:
    return next((b for b in kit()[0] if b["id"] == str(pid)), None)


@lru_cache(maxsize=256)
def vexcel_facts(lat: float, lon: float) -> dict | None:
    f = VexcelClient(settings.vexcel_api_key or "").property(lat, lon)
    if f is None or f.primary is None:
        return None
    p = f.primary
    return {"footprint_sqft": round(p.footprint_sqft or 0), "total_footprint_sqft": round(f.total_footprint_sqft),
            "roof_shape": p.roof_shape, "roof_material": p.roof_material, "roof_condition": p.roof_condition,
            "ac_units": f.total_ac_units, "structures": len(f.structures), "collection": f.collection}


def roof_basis(v: dict, plate: float | None) -> tuple[int, str, int | None]:
    """Which Vexcel figure is the property's roof: the primary structure or every structure together, whichever agrees
    with CoStar's floor plate (gross area / floors). Returns (sq ft, basis, % difference from the floor plate)."""
    options = [(v["footprint_sqft"], "main building")]
    if v.get("structures", 1) > 1 and v.get("total_footprint_sqft"):
        options.append((v["total_footprint_sqft"], f"all {v['structures']} structures"))
    if not plate:
        return options[0][0], options[0][1], None
    sqft, basis = min(options, key=lambda o: abs(o[0] / plate - 1))
    return sqft, basis, round(abs(sqft / plate - 1) * 100)


@router.get("/search")
def search_route(q: str = "", city: str | None = None, type: str | None = None, scanned: bool = False, limit: int = Query(25, ge=1, le=100)):
    if not kit()[0]:
        raise HTTPException(503, "The CoStar kit index isn't built yet. Run: python -m app.real.kit_index")
    return {"results": search(q, city, type, scanned, limit), "total": len(kit()[0])}


@router.get("/buildings/{pid}")
def building(pid: str):
    b = find(pid)
    if not b:
        raise HTTPException(404, f"No building {pid} in the CoStar kit.")
    out = {**b, "dossier": kit()[1].get(b["id"], {}), "vexcel": None, "vexcel_error": None}
    if b.get("lat") and settings.vexcel_api_key:
        try:
            out["vexcel"] = vexcel_facts(round(b["lat"], 6), round(b["lon"], 6))
        except VexcelError as e:
            out["vexcel_error"] = str(e)
    if out["vexcel"]:
        from .money import check_roof
        plate = b["gba_sqft"] / b["stories"] if b.get("gba_sqft") and b.get("stories") else None
        sqft, basis, diff = roof_basis(out["vexcel"], plate)
        if plate:
            out["roof_cross_check"] = {"floor_plate_sqft": round(plate), "roof_sqft": sqft, "basis": basis, "agreement_pct": diff}
        r = check_roof(sqft, 0, 0, shape=out["vexcel"]["roof_shape"] or "flat")
        out["roof_surface"] = {"surface_sqft": round(r.surface), "allowed_sqft": round(r.allowed), "formula": r.formula}
    return out
