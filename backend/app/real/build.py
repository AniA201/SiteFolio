"""Turn cached real responses into the app's data files: buildings, claims, stories and the surcharge registry.

Run from backend/ after app.real.fetch:  .venv/bin/python -m app.real.build
Writes app/data/real/*.json (gitignored). The app loads these instead of the samples when they exist.

What is real: every building record (CoStar kit), roof footprint, roof type and rooftop AC count (Vexcel
/property/extract) and room areas (Matterport Model API). What is invented: the contractors, landlords and
builder, the bills and their prices, bank accounts, and the surcharge history. Every amount is computed by
money.py from the real measurements.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from .. import money
from ..freshness import AERIAL_STALE_DAYS, SCAN_STALE_DAYS, parse_date, scan_date, stamp
from ..integrations.matterport import parse_rooms, total_sqft
from ..integrations.vexcel import parse_property
from .selection import SELECTION

REAL = Path(__file__).resolve().parents[1] / "data" / "real"
CACHE = REAL / "cache"
SAMPLE = Path(__file__).resolve().parents[1] / "data"
_DOSSIER_FILE = REAL / "kit_dossiers.json"
DOSSIERS = json.loads(_DOSSIER_FILE.read_text()) if _DOSSIER_FILE.exists() else {}


def dossier_summary(d: dict) -> dict:
    """The CoStar kit facts shown on the building panel: rents, tenants, last sale, listings."""
    out = {}
    if a := d.get("apartments"):
        out["apartments"] = {k: a.get(k) for k in ("min_rent", "max_rent", "median_plan_rent", "available", "manager")} | {"plans": len(a.get("plans") or [])}
    if t := d.get("tenants"):
        out["tenants"] = {"count": t["count"], "occupied_sqft": t["occupied_sqft"], "top": t["list"][:5]}
    if s := d.get("last_sale"):
        out["last_sale"] = s
    if l := d.get("listings"):
        out["listings"] = l[:3]
    return out

J = lambda o: json.dumps(o, indent=2, ensure_ascii=False)
n0 = lambda x: f"{round(x):,}"
usd = lambda x: f"${round(x):,}"
pct = lambda a, b: round((a / b - 1) * 100)


def load(key: str) -> dict:
    return json.loads((CACHE / f"{key}.json").read_text())


# ---------- per-building facts ----------
class Facts:
    def __init__(self, key: str):
        d = load(key)
        self.key, self.rec, self.raw = key, d["record"], d
        feats = d["vexcel_property"].get("features") or []
        self.vx_attrs = feats[0]["properties"] if feats else {}
        self.vx = parse_property(self.vx_attrs)
        self.ac_views = d.get("ac_views")
        self.dossier = DOSSIERS.get(self.rec["id"], {})
        self.models = {mid: {"name": m["basics"]["name"], "basics": m["basics"], "rooms": parse_rooms(m["rooms"]), "raw_rooms": m["rooms"]}
                       for mid, m in d["matterport"].items()}

    @property
    def footprint(self) -> float:
        return self.vx.primary.footprint_sqft if self.vx.primary else 0.0

    @property
    def floor_plate(self) -> float:
        return (self.rec["gba_sqft"] or 0) / (self.rec["stories"] or 1)

    def building(self) -> dict:
        r, p = self.rec, self.vx.primary
        return {"id": self.key, "cs": r["id"], "name": r["name"], "city": f"{r['city']}, {r['state']}", "address": r["address"],
                "type": r["type"], "size": round(r["gba_sqft"] or 0), "floors": r["stories"], "roof": round(self.footprint),
                "ac": self.vx.total_ac_units, "pitch": (p.roof_shape or "unknown").title() if p else "Unknown",
                "roof_material": p.roof_material if p else None, "roof_condition": p.roof_condition if p else None,
                "built": r["year_built"], "renovated": r["year_renovated"], "lat": r["lat"], "lon": r["lon"],
                "units": r["units"], "parking_spaces": r["parking_spaces"], "vexcel_collection": self.vx.collection,
                "matterport_models": [{"id": mid, "name": m["name"]} for mid, m in self.models.items()], "real": True,
                "dossier": dossier_summary(self.dossier), "aerial_photo": self.aerial_stamp}

    @property
    def aerial_stamp(self) -> dict:
        return stamp("Vexcel aerial", parse_date(self.vx.photo_date), AERIAL_STALE_DAYS)

    def scan_stamp(self, mids: list[str]) -> dict:
        dates = [d for d in (scan_date((self.models[m]["basics"].get("image") or {}).get("url")) for m in mids if m in self.models) if d]
        return stamp("Matterport scan", max(dates) if dates else None, SCAN_STALE_DAYS)

    # ----- API call records, built from the real cached responses (trimmed) -----
    def call_costar(self) -> dict:
        r = self.rec
        resp = {"property_id": r["id"], "name": r["name"], "address": f"{r['address']}, {r['city']}, {r['state']}",
                "property_type": r["type"], "gross_building_area_sf": r["gba_sqft"], "stories": r["stories"],
                **({"units": r["units"]} if r["units"] else {}), "year_built": r["year_built"],
                **({"year_renovated": r["year_renovated"]} if r["year_renovated"] else {}),
                **({"parking_spaces": r["parking_spaces"]} if r["parking_spaces"] else {}), "lat": r["lat"], "lon": r["lon"],
                "matterport_models": len(self.models)}
        return {"svc": "CoStar", "who": "records", "title": "Get the building record",
                "req": f"CoStar data kit\n  data/commercial-property.jsonl\n  where id = {r['id']}", "resp": J(resp)}

    def call_vexcel(self, title="Look from above") -> dict:
        a, p = self.vx_attrs, self.vx.primary
        resp = {"metadata.collection": a.get("metadata.collection"), "structure.count": a.get("structure.count"),
                "primary_structure": {"footprint.area": round(p.footprint_sqft, 1), "roof-characteristics.shape.value": p.roof_shape,
                                      "roof-characteristics.material.class": p.roof_material,
                                      "roof-characteristics.condition": p.roof_condition, "roof-objects.ac-unit.count": p.ac_units}}
        return {"svc": "Vexcel", "who": "roof", "title": title,
                "req": f"GET /v2/property/extract\n  ?wkt=POINT({self.rec['lon']} {self.rec['lat']})\n  &srid=4326&latest=true\n  &include=precomputed\n  &unit-system=imperial",
                "resp": J(resp)}

    def call_vexcel_detect(self) -> dict:
        v = self.ac_views
        views = list(v["counts"])
        req = ("POST /v2/elements/detect\n{\n  wkt: <parcel polygon>, srid: 4326,\n  images: [" + ", ".join(views) + "],\n"
               f"  model-input: {{ elements: [{{ label: \"{v['label']}\",\n    model: \"{v['model']}\", detection-threshold: {v['threshold']} }}] }}\n}}")
        return {"svc": "Vexcel", "who": "roof", "title": "Count again from angled views", "req": req,
                "resp": J({"detections_per_view": v["counts"], "label": v["label"]})}

    def call_matterport(self, mids: list[str], note: str = "") -> dict:
        out = []
        for mid in mids:
            m = self.models[mid]
            out.append({"model": mid, "name": m["name"], "rooms": [
                {"id": r.id, "label": r.label, **({"areaFloor_m2": round(r.area_sqm, 2)} if r.area_sqm else {})} for r in m["rooms"]],
                "total_sq_ft": round(total_sqft(m["rooms"]))})
        req = ("POST /api/models/graph   (GraphQL, server-side)\nquery Rooms($id: ID!) {\n  model(id: $id) {\n    rooms {\n"
               "      id\n      classifications { label }\n      dimensions(units: metric) { areaFloor }\n    }\n  }\n}"
               + (f"\n# {note}" if note else ""))
        return {"svc": "Matterport", "who": "interior", "title": "Look inside", "req": req, "resp": J(out if len(out) > 1 else out[0])}


def ai(file: str, out: dict) -> dict:
    return {"svc": "AI model", "who": "coordinator", "title": "Read the document",
            "req": f"file: {file}\ntask: extract parties, building,\n      claimed work, amounts, pay_to", "resp": J(out)}


def tiger(sql: str, out: dict) -> dict:
    return {"svc": "Tiger Data", "who": "records", "title": "Check history", "req": sql, "resp": J(out)}


def plan_code(name: str) -> str | None:
    m = re.match(r"\s*([A-Z]\d+)\b", name) or re.search(r"Plan\s+([0-9A-Z]{2})\b", name)
    return m.group(1) if m else None


# ---------- claims ----------
def owner_claims(v: Facts) -> list[dict]:
    B = v.building()
    fp, plate, ac = v.footprint, v.floor_plate, v.vx.total_ac_units
    out = []

    # Roof replacement, area inflated.
    claim_area, rate = 52_000, 6.0
    amount = claim_area * rate
    roof = money.check_roof(fp, 0, claim_area, shape=(v.vx.primary.roof_shape if v.vx.primary else None))
    split = money.pay_verified_share(amount, claim_area, roof.surface, roof.allowed)
    out.append({"id": "CLM-2207", "persona": "owner", "party": "lsr", "b": "vine", "date": "Nov 11", "title": "Roof replacement",
        "amount": amount, "kind": "roof", "claim": claim_area, "measured": round(fp),
        "apis": [ai("lone_star_roof.pdf", {"vendor": "Lone Star Roofing", "items": [{"work": "Roof replacement", "qty": claim_area, "unit": "sq ft", "amount": amount}], "pay_to": "••4421"}),
                 v.call_costar(), v.call_vexcel(),
                 tiger(f"SELECT approved_acct, paid_before\nFROM vendors, payments\nWHERE vendor='Lone Star'\n  AND building='{B['cs']}'", {"approved_acct": "••4421", "account_matches": True, "duplicate": False})],
        "steps": [["coordinator", "Read the bill and write the plan", "done", 0], ["records", "Get the building record", "done", 1],
                  ["roof", "Measure the roof from above", "done", 2],
                  ["records", f"Cross-check: {n0(B['size'])} sq ft ÷ {B['floors']} floors = {n0(plate)}", "done"],
                  ["roof", f"Compare with bill: {n0(claim_area)} sq ft claimed", "fail"],
                  ["records", "Check bank account and past payments", "done", 3],
                  ["coordinator", "Plan updated: draft note to contractor, pause for manager", "warn"],
                  ["rules", f"Math: pay {usd(split.pay)} for the verified area, hold {usd(split.hold)}", "warn"]],
        "cross": [["Roof size", f"CoStar: {n0(B['size'])} sq ft ÷ {B['floors']} floors = {n0(plate)} sq ft",
                   f"Vexcel: {n0(fp)} sq ft, {B['pitch'].lower()} {B['roof_material'] or ''} roof".replace("  ", " "),
                   f"Bill: {n0(claim_area)} sq ft",
                   f"Both sources put the roof near {n0(plate)}–{n0(fp)} sq ft. The bill is {pct(claim_area, fp)}% too big."]],
        "lines": [["Roof area", f"{n0(claim_area)} sq ft", f"{n0(fp)} sq ft", "bad"], ["Amount", usd(amount), usd(split.pay), "bad"], ["Pay to", "••4421", "••4421 approved", "ok"]],
        "roof_formula": roof.formula,
        "outcome": {"status": "partial", "a": ["Pay now", split.pay, "green"], "b": ["Hold", split.hold, "amber"],
                    "reason": f"The building record and the aerial measurement both put the roof near {n0(fp)} sq ft, not {n0(claim_area)}. The verified area is paid and the difference is held.",
                    "note": f"Hi Dana, our building record and aerial measurement both show about {n0(fp)} sq ft of roof at {B['name']}, not {n0(claim_area)}. We've paid {usd(split.pay)} for the verified area. Could you send a corrected invoice or photos of the full scope?"}})

    # Rooftop AC units, count inflated.
    claim_units, unit_price = ac + 10, 8_000
    amount = claim_units * unit_price
    split = money.pay_verified_share(amount, claim_units, ac)
    out.append({"id": "CLM-2214", "persona": "owner", "party": "pam", "b": "vine", "date": "Nov 12", "title": "Rooftop AC replacement",
        "amount": amount, "kind": "hvac", "claim": claim_units, "measured": ac,
        "apis": [ai("polar_air_hvac.pdf", {"vendor": "Polar Air Mechanical", "items": [{"work": "Replace rooftop AC units", "qty": claim_units, "unit": "units", "amount": amount}], "pay_to": "••7730"}),
                 v.call_vexcel("Count units from above"), *([v.call_vexcel_detect()] if v.ac_views else [v.call_costar()]),
                 tiger("SELECT approved_acct FROM vendors\nWHERE vendor='Polar Air'", {"approved_acct": "••7730", "account_matches": True, "duplicate": False})],
        "steps": [["coordinator", "Read the bill and write the plan", "done", 0], ["roof", "Count rooftop units from above", "done", 1],
                  (["roof", "Count again from two angled (oblique) views", "done", 2] if v.ac_views else
                   ["records", "Check the building size for a sanity range", "done", 2]),
                  ["roof", f"Compare with bill: {claim_units} units claimed", "fail"],
                  ["records", "Check bank account and past payments", "done", 3], ["coordinator", "Plan updated: pause for manager", "warn"],
                  ["rules", f"Math: pay {usd(split.pay)} for {ac} units, hold {usd(split.hold)}", "warn"]],
        "cross": [["AC units", f"Vexcel top-down: {ac} units on the roof",
                   (" · ".join(f"{k.split('-')[1]}: {n}" for k, n in v.ac_views["counts"].items()).join(("Vexcel angled views: ", " units")) if v.ac_views
                    else f"CoStar: {n0(B['size'])} sq ft office, about 1 unit per {n0(B['size'] / ac)} sq ft"),
                   f"Bill: {claim_units} units",
                   (f"Two separate views agree on about {ac}. The bill claims {claim_units - ac} more." if v.ac_views
                    else f"The aerial count is {ac}. The bill claims {claim_units - ac} more.")]],
        "lines": [["Units", str(claim_units), str(ac), "bad"], ["Amount", usd(amount), usd(split.pay), "bad"], ["Pay to", "••7730", "••7730 approved", "ok"]],
        "outcome": {"status": "partial", "a": ["Pay now", split.pay, "green"], "b": ["Hold", split.hold, "amber"],
                    "reason": f"The straight-down and angled aerial views both show about {ac} rooftop units at {B['name']}, not {claim_units}. Paying for {ac} and holding the rest.",
                    "note": f"Hi Polar Air, the aerial survey counts {ac} rooftop units at {B['name']}. We've paid for {ac}. Can you share serial numbers for the other {claim_units - ac}?"}})

    # Fake bank change.
    out.append({"id": "CLM-2223", "persona": "owner", "party": "lsr", "b": "vine", "date": "Nov 13", "title": "Roof leak repair", "amount": 14800, "kind": "fraud", "bank": "••9914",
        "apis": [ai("lone_star_urgent.pdf", {"vendor": "Lone Star Roofing", "items": [{"work": "Roof leak repair", "amount": 14800}], "pay_to": "••9914", "note": "We changed banks, please pay urgently"}),
                 tiger("SELECT approved_acct FROM vendors\nWHERE vendor='Lone Star'", {"approved_acct": "••4421", "account_matches": False})],
        "steps": [["coordinator", "Read the bill and write the plan", "done", 0], ["coordinator", "Text says \"we changed banks, pay urgently\"", "warn"],
                  ["records", "Check bank account: ••9914 vs approved ••4421", "fail", 1], ["rules", "Refuse payment, open a review case", "fail"]],
        "cross": [["Bank account", "Vendor file: ••4421", "Phone-verified 2024: ••4421", "Bill: ••9914", "New account on a bill is never accepted."]],
        "lines": [["Pay to", "••9914", "••4421 only", "bad"], ["Amount", "$14,800", "$0 until verified", "bad"]],
        "outcome": {"status": "blocked", "a": ["Paid", 0, "gray"], "b": ["Stopped", 14800, "red"],
                    "reason": "This bill asks to pay a new account. Accounts only change after a phone call to the number already on file.",
                    "note": "Call Lone Star Roofing at the number in the vendor file, not the one on this bill."}})

    # Suite repaint, honest.
    suite = v.models[SELECTION["vine"]["suite_model"]]
    measured = total_sqft(suite["rooms"]); claim_area = round(measured / 100) * 100 if abs(round(measured / 100) * 100 - measured) < 50 else round(measured)
    amount = claim_area * 8
    out.append({"id": "CLM-2219", "persona": "owner", "party": "gcp", "b": "vine", "date": "Nov 10", "title": f"Repaint {suite['name']}", "amount": amount, "kind": "interior", "claim": claim_area, "measured": round(measured),
        "apis": [ai("gulf_paint.pdf", {"vendor": "Gulf Coast Painting", "items": [{"work": f"Repaint {suite['name']}", "qty": claim_area, "unit": "sq ft", "amount": amount}], "pay_to": "••5562"}),
                 v.call_costar(), v.call_matterport([SELECTION["vine"]["suite_model"]]),
                 tiger("SELECT approved_acct FROM vendors\nWHERE vendor='Gulf Coast Painting'", {"approved_acct": "••5562", "account_matches": True, "duplicate": False})],
        "steps": [["coordinator", "Read the bill and write the plan", "done", 0], ["records", "Get the building record", "done", 1],
                  ["interior", f"Measure {suite['name']} in the 3D scan", "done", 2],
                  ["interior", f"Compare: {n0(measured)} sq ft measured vs {n0(claim_area)} claimed", "done"],
                  ["records", "Check bank account and past payments", "done", 3], ["rules", f"Pay {usd(amount)} once", "done"]],
        "cross": [["Suite area", f"CoStar: floor plate {n0(v.floor_plate)} sq ft", f"Matterport: {suite['name']} rooms = {n0(measured)} sq ft",
                   f"Bill: {n0(claim_area)} sq ft", f"Matches within {abs(pct(claim_area, measured))}%."]],
        "lines": [["Area", f"{n0(claim_area)} sq ft", f"{n0(measured)} sq ft", "ok"], ["Pay to", "••5562", "••5562 approved", "ok"]],
        "outcome": {"status": "approved", "a": ["Paid", amount, "green"], "b": ["Held", 0, "gray"], "reason": "Everything matches. Paid once to the approved account."}})

    # Intake sample: lobby floor refinish, honest.
    lobby = v.models[SELECTION["vine"]["lobby_model"]]
    measured = total_sqft(lobby["rooms"]); claim_area = int(measured // 50 * 50)
    amount = claim_area * 4
    out.append({"id": "CLM-2231", "persona": "owner", "party": "gpv", "b": "vine", "date": "Nov 13", "title": "Refinish lobby floor", "amount": amount, "kind": "interior", "claim": claim_area, "measured": round(measured), "intake": True,
        "apis": [ai("gulf_floors.pdf", {"vendor": "Gulf Coast Floors", "items": [{"work": "Refinish lobby floor", "qty": claim_area, "unit": "sq ft", "amount": amount}], "pay_to": "••7710"}),
                 v.call_matterport([SELECTION["vine"]["lobby_model"]]),
                 tiger("SELECT approved_acct FROM vendors\nWHERE vendor='Gulf Coast Floors'", {"approved_acct": "••7710", "account_matches": True, "duplicate": False})],
        "steps": [["coordinator", "Read the bill and write the plan", "done", 0], ["interior", "Measure the lobby in the 3D scan", "done", 1],
                  ["interior", f"{n0(measured)} sq ft measured, {n0(claim_area)} billed", "done"],
                  ["records", "Check bank account and past payments", "done", 2], ["rules", f"Pay {usd(amount)} once", "done"]],
        "cross": [["Lobby floor", f"Matterport: lobby = {n0(measured)} sq ft", f"CoStar: floor plate {n0(v.floor_plate)} sq ft", f"Bill: {n0(claim_area)} sq ft", "Matches."]],
        "lines": [["Area", f"{n0(claim_area)} sq ft", f"{n0(measured)} sq ft", "ok"]],
        "outcome": {"status": "approved", "a": ["Paid", amount, "green"], "b": ["Held", 0, "gray"], "reason": "The billed area is within the measured lobby. Paid once."}})
    return out


def advertised_sqft(name: str) -> int | None:
    m = re.search(r"([\d,]{3,5})\s*SF", name.replace("\xa0", " "), re.I)
    return int(m.group(1).replace(",", "")) if m else None


def reviewer_claims(c: Facts, w: Facts) -> list[dict]:
    out = []
    B = c.building(); units = B["units"]
    plans = {mid: m for mid, m in c.models.items() if advertised_sqft(m["name"]) or re.search(r"\d\s*BR|studio|plan", m["name"], re.I)}
    plans = {mid: m for mid, m in plans.items() if total_sqft(m["rooms"]) > 150}
    unit_areas = [total_sqft(m["rooms"]) for m in plans.values()]
    avg_unit = sum(unit_areas) / len(unit_areas)
    listing = (c.dossier.get("apartments") or {})
    lp = [p for p in listing.get("plans") or [] if p.get("min_sqft")]
    listed_avg = sum(p["min_sqft"] * (p.get("units") or 1) for p in lp) / max(1, sum(p.get("units") or 1 for p in lp)) if lp else None
    median_rent = listing.get("median_plan_rent")
    fp = c.footprint
    roof_claim, roof_rate = int(round(fp * 1.5 / 500) * 500), 3.0
    floor_per_unit, floor_rate = 900, 3.0
    floor_claim = floor_per_unit * units
    roof_amt, floor_amt = roof_claim * roof_rate, floor_claim * floor_rate
    total = roof_amt + floor_amt
    verified_total = money.verified_cost([(roof_claim, roof_amt, fp), (floor_claim, floor_amt, avg_unit * units)])
    claimed_rent, verified_rent = money.rent_surcharge(total, units), money.rent_surcharge(verified_total, units)
    second_floor = (f"Apartments.com listing (CoStar): {len(lp)} plans average {n0(listed_avg)} sq ft" if listed_avg
                    else f"CoStar: {units} units")
    rent_ctx = {"median_rent": median_rent, "claimed_pct": round(claimed_rent / median_rent * 100, 1), "verified_pct": round(verified_rent / median_rent * 100, 1)} if median_rent else None
    out.append({"id": "RSO-3104", "persona": "reviewer", "party": "wcl", "b": c.key, "date": "Nov 9", "title": "Roof and unit flooring", "amount": total, "kind": "rent", "claim": roof_claim, "measured": round(fp),
        "apis": [ai(f"{c.key}_application.pdf", {"units": units, "items": [{"work": "Roof", "qty": roof_claim, "amount": roof_amt}, {"work": "Unit flooring", "qty": floor_claim, "per_unit": floor_per_unit, "amount": floor_amt}], "total_claimed": total}),
                 c.call_costar(), c.call_vexcel(), c.call_matterport(list(plans), note=f"{len(plans)} floor plans scanned"),
                 tiger(f"SELECT * FROM surcharges\nWHERE property='{B['cs']}'\n  AND work='roof' AND ends_at > now()", {"active_roof_surcharge": False})],
        "steps": [["coordinator", "Read the application and write the plan", "done", 0], ["records", "Get the building record and rent listing", "done", 1],
                  ["roof", "Measure the roof from above", "done", 2], ["interior", f"Measure the {len(plans)} scanned floor plans", "done", 3],
                  ["roof", f"Roof: {n0(fp)} sq ft vs {n0(roof_claim)} claimed", "fail"],
                  ["interior", f"Flooring: about {n0(avg_unit)} sq ft per unit vs {n0(floor_per_unit)} claimed", "fail"],
                  ["coordinator", "Plan updated: request contractor photos", "warn"], ["records", "Check for an active roof surcharge", "done", 4],
                  ["rules", f"Rent math: ${verified_rent:.2f} per unit, not ${claimed_rent:.2f}", "warn"]],
        "cross": [["Roof size", f"CoStar: {n0(B['size'])} ÷ {B['floors']} floors = {n0(c.floor_plate)}", f"Vexcel: {n0(fp)} sq ft, {B['pitch'].lower()}", f"Claim: {n0(roof_claim)} sq ft", f"Roof is {abs(pct(fp, roof_claim))}% smaller than claimed."],
                  ["Unit flooring", second_floor, f"Matterport: {len(plans)} floor plans average {n0(avg_unit)} sq ft", f"Claim: {n0(floor_per_unit)} sq ft per unit", f"Flooring is {abs(pct(avg_unit, floor_per_unit))}% smaller than claimed."]],
        "lines": [["Roof", f"{n0(roof_claim)} sq ft · {usd(roof_amt)}", f"{n0(fp)} sq ft · {usd(fp * roof_rate)}", "bad"],
                  ["Unit flooring", f"{n0(floor_claim)} sq ft · {usd(floor_amt)}", f"{n0(avg_unit * units)} sq ft · {usd(avg_unit * units * floor_rate)}", "bad"],
                  ["Per unit, per month", f"${claimed_rent:.2f}", f"${verified_rent:.2f}", "bad"]],
        "rent": {"units": units, "claimed": claimed_rent, "verified": verified_rent, "months": 60, **({"context": rent_ctx} if rent_ctx else {})},
        "tenant": {"inside_label": f"Average apartment, measured inside ({len(plans)} floor plans)", "inside_value": f"{n0(avg_unit)} sq ft"},
        "outcome": {"status": "reduced", "a": ["Claimed", f"${claimed_rent:.2f}/mo", "gray"], "b": ["Verified", f"${verified_rent:.2f}/mo", "amber"],
                    "reason": f"The roof and the apartments are both smaller than the application says. Under the 50% / 60-month formula, the fair surcharge is ${verified_rent:.2f} per unit per month.",
                    "note": f"The application overstates the roof by {n0(roof_claim - fp)} sq ft and the flooring by about {n0(floor_per_unit - avg_unit)} sq ft per unit. Please submit contractor photos or measurements to support the claimed areas."}})

    W = w.building(); fpw = w.footprint; claim = round(fpw * 1.02 / 100) * 100; amt = claim * 3.0
    rent = money.rent_surcharge(amt, W["units"])
    out.append({"id": "RSO-3110", "persona": "reviewer", "party": "vgl", "b": "westmoreland", "date": "Nov 13", "title": "Roof coating", "amount": amt, "kind": "rentdup", "claim": claim, "measured": round(fpw), "intake": True,
        "apis": [ai("westmoreland_application.pdf", {"units": W["units"], "items": [{"work": "Roof coating", "qty": claim, "amount": amt}]}),
                 w.call_costar(), w.call_vexcel(),
                 tiger(f"SELECT * FROM surcharges\nWHERE property='{W['cs']}'\n  AND work='roof' AND ends_at > now()", {"active_roof_surcharge": True, "approved": "2023-07", "ends_at": "2029-06", "monthly": 19.80})],
        "steps": [["coordinator", "Read the application and write the plan", "done", 0], ["records", "Get the building record", "done", 1],
                  ["roof", "Measure the roof from above", "done", 2], ["roof", f"Roof size matches within {abs(pct(claim, fpw))}%", "done"],
                  ["records", "Check for an active roof surcharge", "fail", 3], ["rules", "Same roof already charged to tenants until 2029: deny", "fail"]],
        "cross": [["Roof size", f"CoStar: {n0(W['size'])} ÷ {W['floors']} floors = {n0(w.floor_plate)}", f"Vexcel: {n0(fpw)} sq ft", f"Claim: {n0(claim)} sq ft", f"Size is fine (within {max(abs(pct(claim, fpw)), 1)}%)."],
                  ["Already charged?", "Tiger Data: roof surcharge approved 2023", "Ends June 2029", "Claim: new roof charge", "Tenants already pay for this roof."]],
        "lines": [["Roof size", f"{n0(claim)} sq ft", f"{n0(fpw)} sq ft", "ok"], ["Existing roof surcharge", "Not mentioned", "$19.80/mo until 2029", "bad"], ["Per unit, per month", f"${rent:.2f}", "$0", "bad"]],
        "rent": {"units": W["units"], "claimed": rent, "verified": 0, "months": 60},
        "outcome": {"status": "denied", "a": ["Claimed", f"${rent:.2f}/mo", "gray"], "b": ["Verified", "$0", "red"],
                    "reason": "The size checks out, but tenants are already paying a roof surcharge approved in 2023 that runs until June 2029. The same roof can't be charged twice.",
                    "note": "This roof already carries an active surcharge (approved July 2023, ends June 2029). A new roof surcharge can't be added until it ends."}})
    return out


def lender_claims(l: Facts) -> list[dict]:
    B = l.building(); out = []
    scanned = {plan_code(m["name"]): (mid, m) for mid, m in l.models.items() if plan_code(m["name"])}
    finished = {code for code, (_, m) in scanned.items() if {"Kitchen", "Bathroom"} <= {r.label for r in m["rooms"]}}
    listed = [p["name"] for p in (l.dossier.get("apartments") or {}).get("plans") or [] if p.get("name")]
    if listed:  # the Apartments.com listing in the CoStar kit says which floor plans the building has
        claimed = sorted(listed, key=lambda c: (c[0], int(c[1:]) if c[1:].isdigit() else 0))
    else:
        letters = sorted({c[0] for c in scanned})
        claimed = [f"{a}{i}" for a in letters for i in range(1, max(int(c[1:]) for c in scanned if c[0] == a) + 1)]
    missing = [c for c in claimed if c not in scanned]
    requested = 600_000
    split = money.release_draw(requested, len(finished & set(claimed)), len(claimed))
    out.append({"id": "DRW-0412", "persona": "lender", "party": "bbc", "b": "lenox", "date": "Nov 12", "title": "Draw 4: unit interiors", "amount": requested, "kind": "draw", "claim": len(claimed), "measured": len(finished),
        "apis": [ai("lenox_draw_4.pdf", {"claimed_complete": f"Unit interiors, all {len(claimed)} floor plans ({claimed[0]}–{claimed[-1]})", "amount_requested": requested}),
                 l.call_costar(), l.call_matterport([scanned[c][0] for c in sorted(scanned)], note=f"{len(scanned)} floor plans scanned"),
                 l.call_vexcel("Check the outside from above"),
                 tiger("SELECT sum(released) FROM draws\nWHERE loan='LNX-25' AND item='Interiors'", {"already_released": 0})],
        "steps": [["coordinator", "Read the request and write the plan", "done", 0], ["records", "Get the building record", "done", 1],
                  ["interior", "Check each floor plan for a finished kitchen and bath", "done", 2], ["roof", "Check the outside from above", "done", 3],
                  ["interior", f"{len(finished)} of {len(claimed)} floor plans verified; no scan for {', '.join(missing)}", "fail"],
                  ["coordinator", f"Plan updated: ask for site photos of {', '.join(missing)}", "warn"], ["records", "Check earlier releases", "done", 4],
                  ["rules", f"Release {usd(split.pay)}, hold {usd(split.hold)}", "warn"]],
        "cross": [["Unit interiors", (f"CoStar (Apartments.com listing): {len(claimed)} floor plans, {', '.join(claimed[:3])}…" if listed else f"CoStar: {B['units']} units, built {B['built']}"), f"Matterport: kitchen and bath found in {len(finished)} of {len(claimed)} floor plans", f"Request: all {len(claimed)} listed floor plans finished", f"{len(finished)} verified; {', '.join(missing)} not scanned yet."],
                  ["Building shell", f"CoStar: {B['floors']} floors, {n0(B['size'])} sq ft", f"Vexcel: {B['pitch'].lower()} roof, {n0(l.footprint)} sq ft footprint", "Request: n/a", "Shell is closed in."]],
        "lines": [["Floor plans finished", f"{len(claimed)} of {len(claimed)}", f"{len(finished)} of {len(claimed)}", "bad"], ["Amount", usd(requested), usd(split.pay), "bad"]],
        "outcome": {"status": "partial", "a": ["Release", split.pay, "green"], "b": ["Hold", split.hold, "amber"],
                    "reason": f"The 3D scans show finished kitchens and baths in {len(finished)} of {len(claimed)} floor plans. Plans {', '.join(missing)} have no scan yet, so their share is held until a scan or site photos arrive.",
                    "note": f"We've released {usd(split.pay)} for the {len(finished)} floor plans verified in the 3D scans. The remaining {usd(split.hold)} will be released once plans {', '.join(missing)} are scanned or photographed."}})
    out.append({"id": "DRW-0415", "persona": "lender", "party": "bbc", "b": "lenox", "date": "Nov 13", "title": "Draw 5: roof complete", "amount": 250_000, "kind": "drawroof", "intake": True,
        "apis": [ai("lenox_draw_5.pdf", {"claimed_complete": "Roof", "amount_requested": 250000}), l.call_costar(), l.call_vexcel(),
                 tiger("SELECT sum(released) FROM draws\nWHERE loan='LNX-25' AND item='Roof'", {"already_released": 0})],
        "steps": [["coordinator", "Read the request and write the plan", "done", 0], ["records", "Get the building record", "done", 1],
                  ["roof", f"Check roof from above: {B['pitch'].lower()} roof over {n0(l.footprint)} sq ft", "done", 2],
                  ["records", "Check earlier releases", "done", 3], ["rules", "Release $250,000", "done"]],
        "cross": [["Roof", f"CoStar: {n0(l.floor_plate)} sq ft per floor", f"Vexcel: roof complete, {n0(l.footprint)} sq ft ({l.vx.collection})", "Request: roof complete", "Matches."]],
        "lines": [["Roof", "Complete", "Complete", "ok"], ["Amount", "$250,000", "$250,000", "ok"]],
        "outcome": {"status": "approved", "a": ["Release", 250000, "green"], "b": ["Hold", 0, "gray"], "reason": "The aerial survey shows the roof complete over the whole footprint. Released in full."}})
    return out


def stories(claims: dict, b: dict) -> dict:
    c = claims
    r, ac, rso, drw = c["CLM-2207"], c["CLM-2214"], c["RSO-3104"], c["DRW-0412"]
    return {
        "owner": [["The roof that shrank", f"A roofer billed {n0(r['claim'])} sq ft at {b['vine']['name']}. The building record and the aerial survey both say about {n0(r['measured'])}.", "CLM-2207", "vine"],
                  [f"{ac['claim']} units billed, {ac['measured']} on the roof", f"The straight-down and angled aerial views both count about {ac['measured']} rooftop AC units. The bill says {ac['claim']}.", "CLM-2214", "vine"],
                  ["\"We changed banks.\"", "A bill asked to pay a new account. Plumbline paid $0 and opened a review.", "CLM-2223", "vine"]],
        "reviewer": [["Rent up for a roof a third smaller", f"A landlord claimed {n0(rso['claim'])} sq ft of roof at {b['tamarind']['name']}. The building has {n0(rso['measured'])}. Tenants would overpay for 5 years.", "RSO-3104", "tamarind"],
                     ["The same roof, charged twice", f"Tenants at {b['westmoreland']['name']} already pay for this roof until 2029. The history check catches it.", "RSO-3104", "westmoreland"]],
        "lender": [[f"{drw['measured']} of {drw['claim']} floor plans verified", f"The builder asked for {usd(drw['amount'])} for finished interiors at {b['lenox']['name']}. The 3D scans verify {drw['measured']} of {drw['claim']} floor plans.", "DRW-0412", "lenox"],
                   ["Release money for real progress", "Check the building from your desk before every loan payment.", "DRW-0412", "lenox"]],
    }


AERIAL_KINDS = {"roof", "hvac", "rent", "rentdup"}  # a completed-roof draw is proven by any photo showing it done


def add_freshness(c: dict, f: Facts) -> None:
    """Attach the evidence dates and, where old data matters, add the agent's step for it (before the final math)."""
    dates, notes = [], []
    if any(a["svc"] == "Vexcel" for a in c["apis"]):
        dates.append(f.aerial_stamp)
        if c["kind"] in AERIAL_KINDS and f.aerial_stamp["stale"]:
            notes.append(["coordinator", f"Aerial photo is from {f.aerial_stamp['label']}: it proves the size, not recent work. Ask for completion photos", "warn"])
    mp = next((a for a in c["apis"] if a["svc"] == "Matterport"), None)
    if mp:
        resp = json.loads(mp["resp"])
        mids = [m["model"] for m in (resp if isinstance(resp, list) else [resp])]
        scan = f.scan_stamp(mids)
        dates.append(scan)
        if c["kind"] == "draw" and scan["stale"]:
            notes.append(["coordinator", f"Plan updated: newest scan is from {scan['label']}; ask for a dated site photo of the finished units", "warn"])
    c["data_dates"] = dates
    if notes:
        c["steps"][-1:-1] = notes


def build() -> None:
    facts = {k: Facts(k) for k in SELECTION}
    buildings = {k: f.building() for k, f in facts.items()}
    claims = owner_claims(facts["vine"]) + reviewer_claims(facts["tamarind"], facts["westmoreland"]) + lender_claims(facts["lenox"])
    for c in claims:
        if c["b"] in facts:
            add_freshness(c, facts[c["b"]])
    by_id = {c["id"]: c for c in claims}
    parties = json.loads((SAMPLE / "parties.json").read_text())
    parties["wcl"] = {"name": "Tamarind Apartments Owner LLC", "role": "Landlord", "acct": "—", "memory": "First application in our records."}
    parties["vgl"] = {"name": "Westmoreland Owner LLC", "role": "Landlord", "acct": "—", "memory": "Roof surcharge approved in 2023, still active."}
    parties["gpv"] = {"name": "Gulf Coast Floors", "role": "Contractor", "acct": "••7710", "memory": "Charges by finished area. History is clean."}
    W, C = buildings["westmoreland"], buildings["tamarind"]
    surcharges = [{"property_id": W["cs"], "building": W["name"], "work": "Roof", "approved": "2023-07", "ends": "2029-06", "per_unit": "$19.80"},
                  {"property_id": C["cs"], "building": C["name"], "work": "Seismic retrofit", "approved": "2021-03", "ends": "2027-02", "per_unit": "$38.00"}]
    personas = json.loads((SAMPLE / "personas.json").read_text())
    meta = {"stories": stories(by_id, buildings), "fool": {"building": "vine", "party": "lsr", "approved_acct": "4421", "rate": 6.0},
            "data_note": "Buildings and measurements are real (CoStar, Vexcel, Matterport) · parties, bills and history are sample data"}
    REAL.mkdir(parents=True, exist_ok=True)
    for name, data in (("buildings", buildings), ("claims", claims), ("parties", parties), ("surcharges", surcharges), ("personas", personas), ("meta", meta)):
        (REAL / f"{name}.json").write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    for c in claims:
        print(f"{c['id']}  {c['title'][:34]:34} {c['outcome']['status']:9} {c['outcome']['a']} {c['outcome']['b']}")


if __name__ == "__main__":
    build()
