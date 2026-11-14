"""Tools the deep agent calls. Each wraps a real data layer (cached real responses first, live API otherwise) or a
plain-code rule.

The agent gathers evidence and decides the verdict; every dollar figure comes from money.py through these tools, and
record_decision, the only tool that records anything, pauses for a person (interrupt_on in agent.py). Tools return
short JSON so small free models can read them.
"""
from __future__ import annotations

import functools
import json
import re
from functools import lru_cache
from pathlib import Path

from .. import money
from ..fixtures import BUILDINGS, PARTIES, SURCHARGES
from ..freshness import AERIAL_STALE_DAYS, SCAN_STALE_DAYS, parse_date, scan_date, stamp
from ..integrations.matterport import MatterportClient, MatterportError, parse_rooms, total_sqft
from ..settings import settings

DATA = Path(__file__).resolve().parents[1] / "data" / "real"
CACHE = DATA / "cache"


def _building(building: str) -> dict:
    key = (building or "").strip().strip("'\"")
    low = key.lower()
    b = (BUILDINGS.get(key) or BUILDINGS.get(low)
         or next((v for v in BUILDINGS.values() if v["name"].lower() == low or str(v.get("cs")) == key), None)
         # loose input from small models: "key vine", "building: vine", "1113 Vine St, Houston"
         or next((v for k, v in BUILDINGS.items() if re.search(rf"\b{re.escape(k.lower())}\b", low) or v["name"].lower() in low), None))
    if not b:
        raise ValueError(f"Unknown building '{building}'. Known: {', '.join(f'{k} ({v['name']})' for k, v in BUILDINGS.items())}")
    return b


@lru_cache(maxsize=16)
def _cache(key: str) -> dict:
    p = CACHE / f"{key}.json"
    return json.loads(p.read_text()) if p.exists() else {}


@lru_cache(maxsize=1)
def _dossiers() -> dict:
    p = DATA / "kit_dossiers.json"
    return json.loads(p.read_text()) if p.exists() else {}


def _plan_code(name: str) -> str | None:
    import re
    m = re.match(r"\s*([A-Z]\d+)\b", name or "") or re.search(r"Plan\s+([0-9A-Z]{2})\b", name or "")
    return m.group(1) if m else None


def _rooms(model_id: str) -> list:
    for key in BUILDINGS:
        m = (_cache(key).get("matterport") or {}).get(model_id)
        if m:
            return parse_rooms(m["rooms"])
    return MatterportClient(settings.matterport_api_key or "", settings.matterport_api_token or "").rooms(model_id)


# ---------- records clerk (CoStar kit, vendor file, history) ----------
def get_building_record(building: str) -> str:
    """CoStar building record: size (sq ft), floors, units, year built, type, floor plate. `building` is the building key."""
    b = _building(building)
    keys = ("cs", "name", "city", "type", "size", "floors", "units", "built", "renovated")
    rec = {k: b.get(k) for k in keys if b.get(k) is not None}
    rec["floor_plate_sqft"] = round(b["size"] / (b["floors"] or 1))
    return json.dumps(rec)


# Claims the agent is working on, so tools read facts from the claim itself instead of trusting the model to copy them.
ACTIVE_CLAIMS: dict[str, dict] = {}


def check_vendor_account(claim_id: str) -> str:
    """Compare the account the claim's document asks to be paid to with that vendor's phone-verified account on file."""
    c = ACTIVE_CLAIMS.get((claim_id or "").strip().upper())
    if not c:
        raise ValueError(f"Unknown claim '{claim_id}'. Use the claim id from the request, e.g. {next(iter(ACTIVE_CLAIMS), 'CLM-0000')}.")
    p = PARTIES.get(c["party"]) or c.get("party_info") or {}
    approved = p["acct"] if p.get("acct", "—") != "—" else None
    pay_to = c.get("bank") or approved
    if approved is None and c.get("persona") != "owner":
        return json.dumps({"vendor": p.get("name"), "note": "Not a payment to a vendor; no bank account to check."})
    checks = money.payment_checks(pay_to or "", approved, already_paid=False)
    return json.dumps({"vendor": p.get("name"), "pay_to": pay_to, "approved_account": approved,
                       "account_matches": checks.account_matches, "blocked": checks.blocked})


def check_surcharge_history(building: str, work: str = "roof") -> str:
    """Is this work already charged to tenants? Looks for an active surcharge for the same work on the building."""
    b = _building(building)
    hits = [s for s in SURCHARGES if str(s.get("property_id")) == str(b.get("cs")) and work.lower() in s.get("work", "").lower()]
    active = [s for s in hits if s.get("ends", "") >= "2026-11" and s.get("per_unit") != "ended"]
    return json.dumps({"active_surcharge": bool(active), "records": active or hits})


# ---------- roof inspector (Vexcel) ----------
def measure_roof(building: str) -> str:
    """Vexcel aerial survey: roof footprint (sq ft), roof shape, counted rooftop AC units, and how old the photo is."""
    b = _building(building)
    pitch, assumed = money.pitch_for_shape((b.get("pitch") or "flat").lower())
    photo = b.get("aerial_photo") or stamp("Vexcel aerial", None, AERIAL_STALE_DAYS)
    return json.dumps({"footprint_sqft": b["roof"], "roof_shape": (b.get("pitch") or "flat").lower(), "pitch_deg": round(pitch, 1),
                       "pitch_assumed": assumed, "rooftop_ac_units_counted": b.get("ac"), "photo": photo.get("label"),
                       "photo_too_old_to_show_new_work": photo.get("stale", False)})


def count_rooftop_units_angled(building: str) -> str:
    """Second, independent count of rooftop AC units from Vexcel's angled (oblique) photos."""
    b = _building(building)
    views = _cache(b["id"]).get("ac_views")
    if not views:
        return json.dumps({"note": "No angled count recorded for this building."})
    return json.dumps({"angled_counts": views["counts"], "note": "Each angled photo is a second look at the SAME rooftop units. "
                       "Do not add them together: they should roughly agree with measure_roof's rooftop_ac_units_counted."})


# ---------- interior inspector (Matterport) ----------
def list_scans(building: str) -> str:
    """The Matterport scans (suites, lobbies, floor plans) of a building: model id, name and photo date."""
    b = _building(building)
    cached = (_cache(b["id"]).get("matterport") or {})
    out = []
    for m in b.get("matterport_models") or []:
        d = scan_date(((cached.get(m["id"]) or {}).get("basics", {}).get("image") or {}).get("url"))
        out.append({"model_id": m["id"], "name": m["name"], "photographed": d.isoformat() if d else None})
    return json.dumps(out)


def measure_rooms(model_id: str) -> str:
    """Room labels and floor areas (sq ft) in one Matterport scan, and the total measured area."""
    try:
        rooms = _rooms(model_id)
    except MatterportError as e:
        return json.dumps({"error": str(e)})
    return json.dumps({"rooms": [{"label": r.label, "sqft": round(r.area_sqft)} for r in rooms if r.area_sqft],
                       "total_sqft": round(total_sqft(rooms))})


def check_floor_plans(building: str) -> str:
    """For a construction draw: the floor plans the building's Apartments.com listing names, which have a scan with a
    finished kitchen and bath, which have no scan, and how old the newest scan is."""
    b = _building(building)
    listed = [p["name"] for p in ((_dossiers().get(str(b.get("cs"))) or {}).get("apartments") or {}).get("plans") or [] if p.get("name")]
    cached = (_cache(b["id"]).get("matterport") or {})
    verified, dates = [], []
    for mid, m in cached.items():
        code = _plan_code(m["basics"]["name"])
        labels = {r.label for r in parse_rooms(m["rooms"])}
        if code and {"Kitchen", "Bathroom"} <= labels:
            verified.append(code)
        d = scan_date((m["basics"].get("image") or {}).get("url"))
        if d:
            dates.append(d)
    listed = listed or sorted(set(verified))
    newest = stamp("Matterport scan", max(dates) if dates else None, SCAN_STALE_DAYS)
    done = sorted(set(verified) & set(listed))
    return json.dumps({"listed_count": len(listed), "verified_finished_count": len(done),
                       "listed_plans": listed, "verified_finished": done,
                       "no_scan": [p for p in listed if p not in verified], "newest_scan": newest["label"],
                       "newest_scan_older_than_90_days": newest["stale"]})


def average_unit_area(building: str) -> str:
    """Average apartment floor area measured across the building's scanned floor plans, and the listing's average plan size."""
    b = _building(building)
    cached = (_cache(b["id"]).get("matterport") or {})
    areas = [total_sqft(parse_rooms(m["rooms"])) for m in cached.values()]
    areas = [a for a in areas if a > 150]
    plans = [p for p in ((_dossiers().get(str(b.get("cs"))) or {}).get("apartments") or {}).get("plans") or [] if p.get("min_sqft")]
    listed = sum(p["min_sqft"] * (p.get("units") or 1) for p in plans) / max(1, sum(p.get("units") or 1 for p in plans)) if plans else None
    return json.dumps({"measured_avg_sqft": round(sum(areas) / len(areas)) if areas else None, "scans_measured": len(areas),
                       "listing_avg_sqft": round(listed) if listed else None, "units": b.get("units")})


# ---------- rules + math (plain code, no AI) ----------
def compute_bill_split(amount: float, claimed: float, verified: float, roof_shape: str | None = None) -> str:
    """Pay/hold split for a contractor bill. For roof area pass roof_shape (flat, gable, hip...) to apply slope and waste."""
    if roof_shape:
        roof = money.check_roof(verified, 0, claimed, shape=roof_shape.lower())
        split = money.pay_verified_share(amount, claimed, roof.surface, roof.allowed)
        return json.dumps({"pay": split.pay, "hold": split.hold, "inflated": roof.inflated, "formula": roof.formula})
    split = money.pay_verified_share(amount, claimed, verified)
    return json.dumps({"pay": split.pay, "hold": split.hold, "inflated": split.hold > 0})


def compute_verified_cost(lines: list[dict]) -> str:
    """Re-price an application's lines at their own unit prices using verified quantities.
    lines: [{"claimed_qty": 10800, "amount": 64800, "verified_qty": 7200}, ...]"""
    total = money.verified_cost([(float(l["claimed_qty"]), float(l["amount"]), float(l["verified_qty"])) for l in lines])
    return json.dumps({"verified_cost": round(total), "claimed_cost": round(sum(float(l["amount"]) for l in lines))})


def compute_rent_surcharge(cost: float, units: int) -> str:
    """Los Angeles capital improvement surcharge per unit per month: 50% of cost over 60 months, $55 cap."""
    return json.dumps({"per_unit_per_month": money.rent_surcharge(cost, int(units))})


def compute_draw_release(requested: float, verified_done: int, claimed_done: int) -> str:
    """Construction draw: release the verified share of the requested amount, hold the rest.
    requested: dollars asked for. verified_done: how many plans are verified finished. claimed_done: how many are listed."""
    if claimed_done <= 0 or claimed_done > 500 or verified_done > claimed_done or requested < claimed_done:
        raise ValueError("Pass requested = the dollar amount, verified_done = verified_finished_count, "
                         "claimed_done = listed_count (counts of floor plans, not dollars).")
    split = money.release_draw(requested, int(verified_done), int(claimed_done))
    return json.dumps({"release": split.pay, "hold": split.hold})


def record_decision(claim_id: str, status: str, reason: str) -> str:
    """Record the verdict for a person to approve. status: approved, partial, reduced, denied or blocked.
    Amounts are taken from the math tools, never typed here. A person approves, edits or rejects before anything is paid."""
    return json.dumps({"recorded": claim_id, "status": status, "reason": reason})


def _safe(fn):
    """Tool errors go back to the model as text it can correct, instead of ending the run."""
    @functools.wraps(fn)
    def run(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            return json.dumps({"error": f"{type(e).__name__}: {e}"})
    return run


for _name in ("get_building_record", "check_vendor_account", "check_surcharge_history", "measure_roof",
              "count_rooftop_units_angled", "list_scans", "measure_rooms", "check_floor_plans", "average_unit_area",
              "compute_bill_split", "compute_verified_cost", "compute_rent_surcharge", "compute_draw_release"):
    globals()[_name] = _safe(globals()[_name])

RECORDS = [get_building_record, check_vendor_account, check_surcharge_history]
ROOF = [measure_roof, count_rooftop_units_angled]
INTERIOR = [list_scans, measure_rooms, check_floor_plans, average_unit_area]
RULES = [compute_bill_split, compute_verified_cost, compute_rent_surcharge, compute_draw_release, record_decision]
MONEY_TOOLS = {"compute_bill_split", "compute_verified_cost", "compute_rent_surcharge", "compute_draw_release"}
