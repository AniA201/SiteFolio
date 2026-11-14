"""Index the whole CoStar kit: every building in a search index, plus a dossier per building.

The dossier joins the kit's other datasets to each property: the Apartments.com listing (asking rents, advertised
floor plans), current tenants (company, suite, square feet), the latest sale, and active for-lease/for-sale listings.

Run from backend/:  .venv/bin/python -m app.real.kit_index
Writes app/data/real/kit_index.json and kit_dossiers.json (gitignored: hackathon data stays local).
"""
from __future__ import annotations

import io
import json
import time
from collections import defaultdict
from datetime import date
from pathlib import Path

from ..integrations.costar import CostarKit
from ..settings import settings
from .records import iter_buildings

OUT = Path(__file__).resolve().parents[1] / "data" / "real"
TODAY = date.today().isoformat()
MAX_TENANTS = 40


def _jsonl(kit: CostarKit, name: str):
    with kit.zip.open(name) as f:
        for line in io.TextIOWrapper(f, encoding="utf-8"):
            if line.strip():
                yield json.loads(line)


def _num(v):
    return v if isinstance(v, (int, float)) and v else None


def build(kit: CostarKit) -> tuple[list[dict], dict[str, dict]]:
    t0 = time.time()
    enums = json.load(kit.zip.open("schemas/enums.json"))
    price_status = enums.get("SalePriceStatus", {})
    listing_type = enums.get("ListingType", {})

    index = []
    for b in iter_buildings(kit):
        index.append({k: getattr(b, k) for k in ("id", "name", "address", "city", "state", "type", "status", "gba_sqft", "stories",
                                                  "units", "year_built", "lat", "lon")} | {"models": len(b.model_ids), "model_ids": b.model_ids})
    print(f"index: {len(index)} buildings ({time.time() - t0:.0f}s)")

    dossier: dict[str, dict] = defaultdict(dict)

    for r in _jsonl(kit, "data/apartment-listing.jsonl"):
        pid = str(r.get("propertyId") or "")
        if not pid:
            continue
        plans = [{"name": m.get("name"), "beds": m.get("numBeds"), "baths": m.get("numBaths"), "units": m.get("numUnits"),
                  "available": m.get("numUnitsAvailable"), "min_sqft": _num(m.get("minSquareFeet")), "max_sqft": _num(m.get("maxSquareFeet")),
                  "min_rent": _num(m.get("minRent")), "max_rent": _num(m.get("maxRent")), "per_bed": m.get("rentPricingType") == 2}
                 for m in r.get("apartmentModels") or []]
        rents = [p["min_rent"] for p in plans if p["min_rent"] and not p["per_bed"]]
        dossier[pid]["apartments"] = {"min_rent": _num(r.get("minRent")), "max_rent": _num(r.get("maxRent")),
                                      "median_plan_rent": sorted(rents)[len(rents) // 2] if rents else None,
                                      "units": r.get("totalNumUnits"), "available": r.get("numUnitsAvailable"),
                                      "manager": r.get("propertyManagementCompanyName"), "plans": plans}
    print(f"apartment listings ({time.time() - t0:.0f}s)")

    tenants: dict[str, list] = defaultdict(list)
    need_companies: set[int] = set()
    for r in _jsonl(kit, "data/location-occupancy.jsonl"):
        to = r.get("toDate")
        if to and str(to)[:10] < TODAY:
            continue
        pid = str(r.get("propertyId") or "")
        spaces = r.get("spaces") or []
        sqft = sum(s.get("squareFeetOccupied") or 0 for s in spaces) or None
        suites = sorted({str(s["suite"]).strip() for s in spaces if s.get("suite")})
        tid = r.get("tenantLocationId")
        tenants[pid].append({"company_id": tid, "suites": suites, "sqft": sqft, "since": str(r.get("moveInDate") or r.get("fromDate") or "")[:10] or None})
        if tid:
            need_companies.add(tid)
    names = {}
    for r in _jsonl(kit, "data/company-detail.jsonl"):
        if r.get("id") in need_companies:
            names[r["id"]] = r.get("name") or r.get("companyName")
    for pid, rows in tenants.items():
        rows.sort(key=lambda t: -(t["sqft"] or 0))
        dossier[pid]["tenants"] = {"count": len(rows), "occupied_sqft": round(sum(t["sqft"] or 0 for t in rows)),
                                   "list": [{"name": names.get(t["company_id"]) or "Unknown tenant", **{k: v for k, v in t.items() if k != "company_id"}}
                                            for t in rows[:MAX_TENANTS]]}
    print(f"tenancies: {sum(len(v) for v in tenants.values())} current ({time.time() - t0:.0f}s)")

    for r in _jsonl(kit, "data/commercial-sale-comp.jsonl"):
        sold = str(r.get("soldDate") or "")[:10]
        for e in r.get("entities") or []:
            pid = str(e.get("propertyId") or "")
            if not pid or not sold:
                continue
            prev = dossier[pid].get("last_sale")
            if prev and prev["date"] >= sold:
                continue
            price = _num(e.get("allocatedPrice")) if (r.get("numberOfEntities") or 1) > 1 else _num(r.get("soldForPrice"))
            dossier[pid]["last_sale"] = {"date": sold, "price": price,
                                         "price_status": price_status.get(str(r.get("salePriceStatus")), "Unknown"),
                                         "portfolio": (r.get("numberOfEntities") or 1) > 1, "price_per_unit": _num(r.get("pricePerUnit"))}
    print(f"sale comps ({time.time() - t0:.0f}s)")

    for r in _jsonl(kit, "data/commercial-listing-summary.jsonl"):
        pid = str(r.get("propertyId") or "")
        if not pid:
            continue
        lease, sale = r.get("forLeaseSummary") or {}, r.get("forSaleSummary") or {}
        entry = {"type": listing_type.get(str(r.get("listingType")), "Listing"), "brokerage": r.get("brokerageCompanyName")}
        if lease:
            entry |= {"available_sqft": _num(lease.get("totalAvailableSquareFeet")), "asking_rate_low": _num(lease.get("askingRateLow")),
                      "asking_rate_high": _num(lease.get("askingRateHigh")), "rate_basis": {1: "per month", 2: "per year"}.get(lease.get("askingRateBasis"))}
        if sale:
            entry |= {"asking_price_low": _num(sale.get("askingPriceLow")), "asking_price_high": _num(sale.get("askingPriceHigh"))}
        dossier[pid].setdefault("listings", []).append(entry)
    print(f"listings ({time.time() - t0:.0f}s)")

    # Homes: MLS listings with Matterport scans (residential-listings), one entry per home.
    for_sale = enums.get("ForSaleStatus", {})
    txn = enums.get("TransactionType", {})
    home_models: dict[str, list[str]] = defaultdict(list)
    for row in kit.rows("residential-listings.csv"):
        if row.get("matterportmodelid"):
            home_models[row["listingid"]].append(row["matterportmodelid"])
    seen = set()
    for r in _jsonl(kit, "data/residential-listings.jsonl"):
        prop = r.get("property") or {}
        a = prop.get("address") or {}
        home_key = r.get("residentialListingId") or r["id"]
        if home_key in seen or not a.get("latitude"):
            continue
        seen.add(home_key)
        street = " ".join(str(x) for x in (a.get("streetNumber"), a.get("streetDirection"), a.get("streetName"), a.get("streetType") or a.get("streetSuffix")) if x)
        unit = a.get("unitNumber") or a.get("unit")
        hid = f"home-{r['id']}"
        structure = (r.get("resoValues") or {}).get("structure") or {}
        index.append({"id": hid, "name": street + (f" #{unit}" if unit else ""), "address": street, "city": (a.get("city") or "").title(),
                      "state": a.get("state") or "", "type": "Home", "status": "Existing", "gba_sqft": _num(prop.get("sqftMin")),
                      "stories": structure.get("stories"), "units": None, "year_built": prop.get("yearBuilt"),
                      "lat": a.get("latitude"), "lon": a.get("longitude"), "models": len(home_models.get(str(r["id"]), [])),
                      "model_ids": home_models.get(str(r["id"]), [])})
        dossier[hid]["home"] = {"price": _num(r.get("currentPrice")), "transaction": txn.get(str(r.get("transactionType")), "Unknown"),
                                "status": for_sale.get(str(r.get("forSaleStatus")), "Unknown"), "listed": str(r.get("listDate") or "")[:10] or None,
                                "beds": prop.get("bedsMax") or prop.get("bedsMin"), "baths": prop.get("bathsMax") or prop.get("bathsMin"),
                                "living_sqft": _num(prop.get("sqftMin")), "lot_acres": _num(prop.get("lotSizeAcresMin")),
                                "mls_type": prop.get("mlsPropertyType"), "subdivision": prop.get("subdivision"), "parking": prop.get("totalParkingSpaces")}
    print(f"homes: {len(seen)} ({time.time() - t0:.0f}s)")
    return index, dict(dossier)


if __name__ == "__main__":
    kit = CostarKit.open(path=settings.costar_kit_zip, url=settings.costar_kit_url, password=settings.costar_zip_password)
    index, dossier = build(kit)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "kit_index.json").write_text(json.dumps(index, ensure_ascii=False))
    (OUT / "kit_dossiers.json").write_text(json.dumps(dossier, ensure_ascii=False))
    print(f"wrote {len(index)} buildings, {len(dossier)} dossiers")
