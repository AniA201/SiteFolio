"""Matterport Model API client (GraphQL, server-side only).

Auth is HTTP basic: the API key is the user name and the API token the password. The hackathon keys
only work on production, api.matterport.com. Room areas come back in square metres.

Check a key from backend/:  .venv/bin/python -m app.integrations.matterport
"""
from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from pathlib import Path

import httpx

GRAPH_URL = "https://api.matterport.com/api/models/graph"
SQFT_PER_SQM = 10.7639

KEY_CHECK = """{ rootFolder { name modelCountSummary(includeModelsInSubfolders: true)
  subfolders { results { id name modelCountSummary(includeModelsInSubfolders: true) } } } }"""

BASICS = """query Basics($id: ID!) { model(id: $id) {
  id name description created visibility
  address { address locality administrativeArea postalCode }
  geolocation { lat long }
  generatedDescription { summary }
  propertyClassifications { classification type }
  floors { id label } rooms { id } panoLocations { id }
  image { url }
} }"""

ROOMS = """query Rooms($id: ID!) { model(id: $id) {
  floors { id label }
  rooms { id floor { id } classifications { label confidence }
          dimensions(units: metric) { areaFloor width depth height } }
} }"""


class MatterportError(RuntimeError):
    pass


@dataclass(frozen=True)
class Room:
    id: str
    floor_id: str | None
    floor_label: str | None
    label: str | None
    confidence: float | None
    area_sqm: float | None

    @property
    def area_sqft(self) -> float | None:
        return None if self.area_sqm is None else self.area_sqm * SQFT_PER_SQM


class MatterportClient:
    def __init__(self, api_key: str, api_token: str, http: httpx.Client | None = None, timeout: float = 30):
        if not (api_key and api_token):
            raise MatterportError("Matterport API key and token are not set (MATTERPORT_API_KEY, MATTERPORT_API_TOKEN).")
        self._http = http or httpx.Client(timeout=timeout)
        self._auth = (api_key, api_token)

    def graph(self, query: str, variables: dict | None = None) -> dict:
        res = self._http.post(GRAPH_URL, json={"query": query, "variables": variables or {}}, auth=self._auth)
        if res.status_code in (401, 403):
            raise MatterportError(f"Matterport rejected the key (HTTP {res.status_code}). Check the key and token.")
        res.raise_for_status()
        body = res.json()
        if body.get("errors"):
            raise MatterportError("; ".join(e.get("message", "unknown error") for e in body["errors"]))
        return body["data"]

    def key_check(self) -> dict:
        return self.graph(KEY_CHECK)["rootFolder"]

    def basics(self, model_id: str) -> dict:
        return self.graph(BASICS, {"id": model_id})["model"]

    def rooms(self, model_id: str) -> list[Room]:
        return parse_rooms(self.graph(ROOMS, {"id": model_id})["model"])


def parse_rooms(model: dict) -> list[Room]:
    floors = {f["id"]: f.get("label") for f in model.get("floors") or []}
    out = []
    for r in model.get("rooms") or []:
        cls = sorted(r.get("classifications") or [], key=lambda c: -(c.get("confidence") or 0))
        top = cls[0] if cls else {}
        floor_id = (r.get("floor") or {}).get("id")
        dims = r.get("dimensions") or {}
        out.append(Room(r["id"], floor_id, floors.get(floor_id), top.get("label"), top.get("confidence"), dims.get("areaFloor")))
    return out


def rooms_labelled(rooms: list[Room], *labels: str, floor_label: str | None = None) -> list[Room]:
    """Rooms whose top classification matches any label (case-insensitive), optionally on one floor."""
    want = {l.lower() for l in labels}
    return [r for r in rooms if (r.label or "").lower() in want and (floor_label is None or r.floor_label == floor_label)]


def total_sqft(rooms: list[Room]) -> float:
    return sum(r.area_sqft or 0 for r in rooms)


# ---------- models_index.csv: the API has no geographic search ----------
LAT_COLS = ("lat", "latitude")
LON_COLS = ("lon", "lng", "long", "longitude")
COSTAR_COLS = ("costar_property_id", "costar_id", "property_id")
HOMES_COLS = ("homes_listing_id", "listing_id")


def _pick(row: dict, names: tuple[str, ...]) -> str | None:
    for n in names:
        if row.get(n) not in (None, ""):
            return row[n]
    return None


@dataclass(frozen=True)
class IndexedModel:
    sid: str
    name: str
    lat: float
    lon: float
    segment: str | None
    costar_id: str | None
    homes_listing_id: str | None
    row: dict


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


class ModelIndex:
    """Plain lookups over models_index.csv (one row per model the hackathon keys can see)."""

    def __init__(self, models: list[IndexedModel]):
        self.models = models

    @classmethod
    def load(cls, path: str | Path) -> "ModelIndex":
        models = []
        with open(path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                row = {k.strip().lower(): (v or "").strip() for k, v in row.items() if k}
                lat, lon = _pick(row, LAT_COLS), _pick(row, LON_COLS)
                if not (row.get("sid") and lat and lon):
                    continue
                models.append(IndexedModel(row["sid"], row.get("name", ""), float(lat), float(lon), row.get("segment") or None,
                                           _pick(row, COSTAR_COLS), _pick(row, HOMES_COLS), row))
        return cls(models)

    def near(self, lat: float, lon: float, radius_m: float = 150, limit: int = 10) -> list[tuple[float, IndexedModel]]:
        hits = sorted((haversine_m(lat, lon, m.lat, m.lon), m) for m in self.models)
        return [(d, m) for d, m in hits if d <= radius_m][:limit]

    def by_costar_id(self, costar_id: str) -> list[IndexedModel]:
        return [m for m in self.models if m.costar_id == str(costar_id)]


if __name__ == "__main__":
    from ..settings import settings

    folder = MatterportClient(settings.matterport_api_key or "", settings.matterport_api_token or "").key_check()
    print(f"Key OK. '{folder['name']}' holds {folder['modelCountSummary']:,} models:")
    for sub in (folder.get("subfolders") or {}).get("results", []):
        print(f"  {sub['name']:<22}{sub['modelCountSummary']:>7,}   (folder {sub['id']})")
