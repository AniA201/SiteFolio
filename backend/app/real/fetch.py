"""Fetch and cache the real responses for the chosen buildings, so the demo runs from files.

Run from backend/:  .venv/bin/python -m app.real.fetch [--refresh]
Writes app/data/real/cache/ (gitignored). Every later step reads only the cache.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from ..integrations.costar import CostarKit
from ..integrations.matterport import BASICS, ROOMS, MatterportClient
from ..integrations.vexcel import DEFAULT_LAYER, PROPERTY_URL, VexcelClient, count_by_view, detect, geometry_wkt, oblique_directions
from ..settings import settings
from .records import iter_buildings
from .selection import SELECTION

CACHE = Path(__file__).resolve().parents[1] / "data" / "real" / "cache"


def _write(name: str, data) -> None:
    CACHE.mkdir(parents=True, exist_ok=True)
    (CACHE / name).write_text(json.dumps(data, indent=1, ensure_ascii=False))


def fetch(refresh: bool = False) -> None:
    ids = {s["costar_id"] for s in SELECTION.values()}
    kit = CostarKit.open(path=settings.costar_kit_zip, url=settings.costar_kit_url, password=settings.costar_zip_password)
    records = {b.id: b for b in iter_buildings(kit, lambda b: b.id in ids)}
    missing = ids - set(records)
    if missing:
        raise SystemExit(f"Not in the kit: {sorted(missing)}")

    mp = MatterportClient(settings.matterport_api_key, settings.matterport_api_token)
    vx = VexcelClient(settings.vexcel_api_key)
    for key, sel in SELECTION.items():
        b = records[sel["costar_id"]]
        path = CACHE / f"{key}.json"
        if path.exists() and not refresh:
            print(f"{key}: cached")
            continue
        res = vx._send("GET", PROPERTY_URL, params={"wkt": f"POINT({b.lon!r} {b.lat!r})", "srid": 4326, "layer": DEFAULT_LAYER,
                                                    "latest": "true", "include": "precomputed", "unit-system": "imperial"})
        vx._check(res)
        vexcel = res.json()
        models = {}
        for mid in b.model_ids:
            models[mid] = {"basics": mp.graph(BASICS, {"id": mid})["model"], "rooms": mp.graph(ROOMS, {"id": mid})["model"]}
        _write(f"{key}.json", {"record": b.to_dict(), "vexcel_property": vexcel, "matterport": models})
        print(f"{key}: {b.name}, {len(models)} Matterport models")


AC_LABEL = "rooftop air conditioning unit"


def fetch_ac_views(key: str = "vine") -> None:
    """Count rooftop AC units again from Vexcel's angled (oblique) photos: an independent second view."""
    path = CACHE / f"{key}.json"
    d = json.loads(path.read_text())
    if "ac_views" in d:
        print(f"{key}: angled AC count cached")
        return
    vx = VexcelClient(settings.vexcel_api_key)
    wkt = geometry_wkt(d["vexcel_property"]["features"][0]["geometry"])
    views = [v for v in oblique_directions(vx, wkt) if v in ("oblique-north", "oblique-south")]
    counts = count_by_view(detect(vx, wkt, [AC_LABEL], views), views) if views else {}
    d["ac_views"] = {"label": AC_LABEL, "model": "sam3", "threshold": 0.5, "counts": counts}
    path.write_text(json.dumps(d, indent=1, ensure_ascii=False))
    print(f"{key}: angled AC counts {counts}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true")
    fetch(ap.parse_args().refresh)
    fetch_ac_views()
