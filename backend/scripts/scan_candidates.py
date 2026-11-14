"""Find real buildings that have all three layers (CoStar record, Matterport rooms with areas, Vexcel roof data).

Run from backend/:  .venv/bin/python -m scripts.scan_candidates [--per-group 10]
Writes app/data/real/candidates.json (gitignored: hackathon data stays local).
"""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from app.integrations.costar import CostarKit
from app.integrations.matterport import MatterportClient, MatterportError, total_sqft
from app.integrations.vexcel import VexcelClient, VexcelError
from app.real.records import iter_buildings
from app.settings import settings

OUT = Path(__file__).resolve().parents[1] / "app" / "data" / "real"

GROUPS = {
    # owner: a low-rise Houston office with a flat roof and rooftop units
    "owner": lambda b: b.city == "Houston" and b.type == "Office" and b.status == "Existing"
    and (b.stories or 0) in range(1, 6) and 15_000 <= (b.gba_sqft or 0) <= 150_000,
    # reviewer: a small LA apartment building (rent-stabilised stock is mostly older walk-ups)
    "reviewer": lambda b: b.city == "Los Angeles" and b.type == "Multifamily" and b.status == "Existing"
    and (b.stories or 0) in range(2, 5) and 8 <= (b.units or 0) <= 60 and (b.year_built or 2100) < 1990,
    # lender: a mid-size Houston apartment building, framed as a construction draw
    "lender": lambda b: b.city == "Houston" and b.type == "Multifamily" and (b.stories or 0) in range(3, 7)
    and 24 <= (b.units or 0) <= 200,
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-group", type=int, default=10)
    args = ap.parse_args()
    kit = CostarKit.open(path=settings.costar_kit_zip, url=settings.costar_kit_url, password=settings.costar_zip_password)
    mp = MatterportClient(settings.matterport_api_key, settings.matterport_api_token)
    vx = VexcelClient(settings.vexcel_api_key)

    pools = {g: [] for g in GROUPS}
    for b in iter_buildings(kit, lambda b: bool(b.model_ids and b.lat and b.lon)):
        for g, keep in GROUPS.items():
            if keep(b):
                pools[g].append(b)
    print({g: len(v) for g, v in pools.items()}, file=sys.stderr)

    results = {}
    for g, pool in pools.items():
        pool.sort(key=lambda b: (-(len(b.model_ids)), b.id))
        rows = []
        for b in pool[: args.per_group]:
            row = {"building": b.to_dict(), "models": []}
            for mid in b.model_ids[:3]:
                try:
                    rooms = mp.rooms(mid)
                    labels = Counter(r.label for r in rooms if r.label)
                    row["models"].append({"id": mid, "rooms": len(rooms), "with_area": sum(r.area_sqm is not None for r in rooms),
                                          "total_sqft": round(total_sqft(rooms)), "labels": dict(labels.most_common(8))})
                except MatterportError as e:
                    row["models"].append({"id": mid, "error": str(e)[:120]})
            try:
                f = vx.property(b.lat, b.lon)
                row["vexcel"] = None if f is None else {"footprint_sqft": round(f.total_footprint_sqft), "ac_units": f.total_ac_units,
                                                         "roof": f.primary.roof_shape if f.primary else None,
                                                         "structures": len(f.structures), "collection": f.collection}
            except VexcelError as e:
                row["vexcel"] = {"error": str(e)[:120]}
            rows.append(row)
            m = max((x for x in row["models"] if "rooms" in x), key=lambda x: x["with_area"], default={})
            v = row["vexcel"] or {}
            print(f"{g:8} {b.id:>8} {b.name[:34]:34} st={b.stories} gba={b.gba_sqft} units={b.units} | "
                  f"mp rooms={m.get('with_area')}/{m.get('rooms')} {m.get('total_sqft')}sf {list((m.get('labels') or {}))[:4]} | "
                  f"vx fp={v.get('footprint_sqft')} ac={v.get('ac_units')} roof={v.get('roof')}", file=sys.stderr)
        results[g] = rows
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "candidates.json").write_text(json.dumps(results, indent=1))
    print(f"wrote {OUT / 'candidates.json'}", file=sys.stderr)


if __name__ == "__main__":
    main()
