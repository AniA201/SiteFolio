"""Tools the deep agent can call. Each wraps a real data layer or a plain-code rule.

The agent gathers evidence and proposes; every dollar figure comes from money.py through these tools, and the only
tool that records a decision is paused for a person (interrupt_on in agent.py).
"""
from __future__ import annotations

import json
from pathlib import Path

from .. import money
from ..fixtures import BUILDINGS, PARTIES
from ..integrations.matterport import MatterportClient, MatterportError, total_sqft
from ..settings import settings

CACHE = Path(__file__).resolve().parents[1] / "data" / "real" / "cache"


def _building(building: str) -> dict:
    b = BUILDINGS.get(building) or next((v for v in BUILDINGS.values() if v["name"].lower() == building.lower()), None)
    if not b:
        raise ValueError(f"Unknown building '{building}'. Known: {', '.join(f'{k} ({v['name']})' for k, v in BUILDINGS.items())}")
    return b


# ---------- records clerk ----------
def get_building_record(building: str) -> str:
    """CoStar building record: size (sq ft), floors, units, year built, type, coordinates. `building` is a building key or name."""
    b = _building(building)
    keys = ("id", "cs", "name", "city", "address", "type", "size", "floors", "units", "built", "renovated", "parking_spaces", "lat", "lon")
    rec = {k: b.get(k) for k in keys if b.get(k) is not None}
    rec["floor_plate_sqft"] = round(b["size"] / (b["floors"] or 1))
    return json.dumps(rec)


def check_vendor_account(vendor: str, pay_to_last4: str) -> str:
    """Compare the account a bill asks to be paid to with the vendor's phone-verified account on file."""
    p = next((p for p in PARTIES.values() if p["name"].lower() == vendor.lower()), None)
    approved = p["acct"] if p and p.get("acct", "—") != "—" else None
    checks = money.payment_checks(f"••{pay_to_last4}", approved, already_paid=False)
    return json.dumps({"vendor_known": p is not None, "approved_account": approved, "account_matches": checks.account_matches,
                       "blocked": checks.blocked, "history_note": p.get("memory") if p else None})


# ---------- roof inspector ----------
def measure_roof(building: str) -> str:
    """Vexcel aerial survey of the building: roof footprint (sq ft), roof shape and material, and counted rooftop AC units."""
    b = _building(building)
    pitch, assumed = money.pitch_for_shape((b.get("pitch") or "flat").lower())
    return json.dumps({"footprint_sqft": b["roof"], "roof_shape": b.get("pitch"), "pitch_deg": pitch, "pitch_assumed": assumed, "roof_material": b.get("roof_material"),
                       "rooftop_ac_units_top_down": b.get("ac"), "capture": b.get("vexcel_collection")})


def count_rooftop_units_angled(building: str) -> str:
    """Second, independent count of rooftop AC units from Vexcel's angled (oblique) photos, when available."""
    b = _building(building)
    path = CACHE / f"{b['id']}.json"
    views = json.loads(path.read_text()).get("ac_views") if path.exists() else None
    return json.dumps(views["counts"] if views else {"note": "No angled count recorded for this building."})


# ---------- interior inspector ----------
def measure_rooms(model_id: str) -> str:
    """Matterport 3D scan of one space: each room's label and floor area (sq ft), and the total."""
    try:
        rooms = MatterportClient(settings.matterport_api_key or "", settings.matterport_api_token or "").rooms(model_id)
    except MatterportError as e:
        return json.dumps({"error": str(e)})
    return json.dumps({"rooms": [{"label": r.label, "sqft": round(r.area_sqft, 1) if r.area_sqft else None} for r in rooms],
                       "total_sqft": round(total_sqft(rooms), 1)})


def list_scans(building: str) -> str:
    """The Matterport scans (suites, lobbies, floor plans) recorded for a building, with their model ids."""
    return json.dumps(_building(building).get("matterport_models") or [])


# ---------- rules + math (plain code) ----------
def compute_bill_split(amount: float, claimed: float, verified: float, roof_pitch_deg: float | None = None) -> str:
    """Pay/hold split for a bill. For roofs pass roof_pitch_deg to apply the slope factor and waste allowance."""
    if roof_pitch_deg is not None:
        roof = money.check_roof(verified, roof_pitch_deg, claimed)
        split = money.pay_verified_share(amount, claimed, roof.surface, roof.allowed)
        return json.dumps({"pay": split.pay, "hold": split.hold, "formula": roof.formula, "inflated": roof.inflated})
    split = money.pay_verified_share(amount, claimed, verified)
    return json.dumps({"pay": split.pay, "hold": split.hold})


def compute_rent_surcharge(cost: float, units: int) -> str:
    """Los Angeles capital improvement surcharge per unit per month (50% over 60 months, $55 cap)."""
    return json.dumps({"per_unit_per_month": money.rent_surcharge(cost, units)})


def compute_draw_release(requested: float, verified_done: int, claimed_done: int) -> str:
    """Construction draw: release the verified share of the requested amount, hold the rest."""
    split = money.release_draw(requested, verified_done, claimed_done)
    return json.dumps({"release": split.pay, "hold": split.hold})


def record_decision(claim_id: str, status: str, pay: float, hold: float, reason: str) -> str:
    """Record the proposed decision. A person approves, edits or rejects this before anything is paid."""
    return json.dumps({"recorded": claim_id, "status": status, "pay": pay, "hold": hold, "reason": reason})


RECORDS = [get_building_record, check_vendor_account]
ROOF = [measure_roof, count_rooftop_units_angled]
INTERIOR = [list_scans, measure_rooms]
RULES = [compute_bill_split, compute_rent_surcharge, compute_draw_release, record_decision]
