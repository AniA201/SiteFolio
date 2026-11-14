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
from ..integrations.vexcel import DEFAULT_LAYER, PROPERTY_URL, VexcelClient
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


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true")
    fetch(ap.parse_args().refresh)
