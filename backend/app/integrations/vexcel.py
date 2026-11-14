"""Vexcel aerial imagery client.

One call clips Vexcel's latest orthophoto (about 7.5 cm per pixel) to a square around a lat/lon. The key goes in
the X-API-KEY header. Hackathon keys cover Houston and Los Angeles only; anywhere else answers 403.
property/extract adds the parcel and, per structure, footprint area, roof shape, material, condition and counted
roof objects such as AC units. Rate limits (429) are retried with backoff, as the Vexcel tutorial asks.
"""
from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass

import httpx

API = "https://api.vexcelgroup.com/v2"
ORTHO_URL = f"{API}/ortho/extract"
PROPERTY_URL = f"{API}/property/extract"
MAX_RETRIES = 5
DEFAULT_LAYER = "urban,urban-r,wide-area,urban-g"
M_PER_DEG_LAT = 111320.0


class VexcelError(RuntimeError):
    pass


def square_wkt(lat: float, lon: float, half_side_m: float = 70) -> str:
    """A WKT polygon (EPSG:4326, lon lat order) for a square centred on lat/lon."""
    dlat = half_side_m / M_PER_DEG_LAT
    dlon = half_side_m / (M_PER_DEG_LAT * math.cos(math.radians(lat)))
    w, e, s, n = lon - dlon, lon + dlon, lat - dlat, lat + dlat
    ring = [(w, s), (e, s), (e, n), (w, n), (w, s)]
    return "POLYGON((" + ",".join(f"{x!r} {y!r}" for x, y in ring) + "))"


def metres_per_pixel(half_side_m: float, pixels: int) -> float:
    return 2 * half_side_m / pixels


class VexcelClient:
    def __init__(self, api_key: str, http: httpx.Client | None = None, timeout: float = 120, sleep=time.sleep):
        if not api_key:
            raise VexcelError("Vexcel API key is not set (VEXCEL_API_KEY).")
        self._key = api_key
        self._http = http or httpx.Client(timeout=timeout)
        self._sleep = sleep

    def ortho(self, lat: float, lon: float, half_side_m: float = 70, pixels: int = 1400, layer: str = DEFAULT_LAYER) -> bytes:
        body = {
            "wkt": square_wkt(lat, lon, half_side_m),
            "srid": 4326,
            "layer": layer,
            "crop": "bounding_box",
            "image-format": "jpeg",
            "destination-dimensions": f"{pixels},{pixels}",
            "attribution": "false",
        }
        res = self._send("POST", ORTHO_URL, json=body)
        self._check(res)
        if not res.headers.get("content-type", "").startswith("image/"):
            raise VexcelError(f"Vexcel answered {res.headers.get('content-type')} instead of an image: {res.text[:200]}")
        return res.content

    def property(self, lat: float, lon: float) -> "PropertyFacts | None":
        """The parcel at a point with its structures: footprint, roof shape and material, counted roof objects.
        None when Vexcel has no parcel there (HTTP 404)."""
        res = self._send("GET", PROPERTY_URL, params={
            "wkt": f"POINT({lon!r} {lat!r})", "srid": 4326, "layer": DEFAULT_LAYER,
            "latest": "true", "include": "precomputed", "unit-system": "imperial"})
        if res.status_code == 404:
            return None
        self._check(res)
        features = res.json().get("features") or []
        return parse_property(features[0]["properties"]) if features else None

    def _send(self, method: str, url: str, **kwargs) -> httpx.Response:
        """Retry 429 Too Many Requests with exponential backoff (about 1, 2, 4, 8, 16 s), as Vexcel asks."""
        for attempt in range(MAX_RETRIES + 1):
            res = self._http.request(method, url, headers={"X-API-KEY": self._key}, **kwargs)
            if res.status_code != 429 or attempt == MAX_RETRIES:
                return res
            self._sleep(min(2 ** attempt, 30) + random.random())
        return res

    @staticmethod
    def _check(res: httpx.Response) -> None:
        if res.status_code == 403:
            raise VexcelError("Vexcel refused this location (HTTP 403). Hackathon keys cover Houston and Los Angeles only.")
        if res.status_code == 401:
            raise VexcelError("Vexcel rejected the key (HTTP 401).")
        if res.status_code == 429:
            raise VexcelError("Vexcel is rate limiting us (HTTP 429); try again in a minute.")
        res.raise_for_status()


@dataclass(frozen=True)
class Structure:
    primary: bool
    footprint_sqft: float | None
    roof_shape: str | None        # flat, gable, hip, ...
    roof_material: str | None
    roof_condition: float | None  # Vexcel's condition score (precise value when given)
    ac_units: int | None
    building_type: str | None


@dataclass(frozen=True)
class PropertyFacts:
    collection: str | None
    inside_parcel: bool | None
    structures: list[Structure]
    photo_date: str | None = None   # Vexcel's ortho date estimate (ISO date)

    @property
    def primary(self) -> Structure | None:
        return next((s for s in self.structures if s.primary), self.structures[0] if self.structures else None)

    @property
    def total_footprint_sqft(self) -> float:
        return sum(s.footprint_sqft or 0 for s in self.structures)

    @property
    def total_ac_units(self) -> int:
        return sum(s.ac_units or 0 for s in self.structures)


def parse_property(attrs: dict) -> PropertyFacts:
    structures = [Structure(
        primary=bool(s.get("primary-structure")),
        footprint_sqft=s.get("footprint.area"),
        roof_shape=s.get("roof-characteristics.shape.value"),
        roof_material=s.get("roof-characteristics.material.class"),
        roof_condition=s.get("roof-characteristics.condition.precise-value", s.get("roof-characteristics.condition")),
        ac_units=s.get("roof-objects.ac-unit.count"),
        building_type=s.get("building-type.class"),
    ) for s in attrs.get("structures") or []]
    return PropertyFacts(attrs.get("metadata.collection"), attrs.get("request-information.inside-parcel"), structures,
                         (attrs.get("metadata.ortho-date-estimate") or "")[:10] or None)


ORIENTED_COLLECTIONS_URL = f"{API}/oriented/collections"
DETECT_URL = f"{API}/elements/detect"
OBLIQUES = ("oblique-north", "oblique-south", "oblique-east", "oblique-west")


def geometry_wkt(geometry) -> str:
    """GeoJSON Polygon/MultiPolygon (or WKT) -> WKT, longitude first. Uses the first polygon's outer ring."""
    if isinstance(geometry, str):
        return geometry
    ring = geometry["coordinates"][0] if geometry["type"] == "Polygon" else geometry["coordinates"][0][0]
    return "POLYGON((" + ",".join(f"{x!r} {y!r}" for x, y in ring) + "))"


@dataclass(frozen=True)
class Detection:
    label: str
    view: str          # "ortho" or an oblique direction
    confidence: float


def oblique_directions(client: "VexcelClient", wkt: str) -> list[str]:
    """Oblique views available in the newest capture over this area (only the 'urban' layer has obliques)."""
    res = client._send("GET", ORIENTED_COLLECTIONS_URL, params={"wkt": wkt, "srid": 4326, "layer": "urban", "product-type": "oblique",
                                                                "include": "product-type,collection,last-capture-date"})
    if res.status_code == 404:
        return []
    client._check(res)
    feats = res.json().get("features") or []
    newest = max((f["properties"]["last-capture-date"] for f in feats), default=None)
    have = {f["properties"]["product-type"] for f in feats if f["properties"]["last-capture-date"] == newest}
    return [d for d in OBLIQUES if d in have]


def detect(client: "VexcelClient", wkt: str, labels: list[str], views: list[str], threshold: float = 0.5) -> list[Detection]:
    """Open-vocabulary detection (sam3) on the parcel in each requested view. Views: 'ortho' and/or oblique directions."""
    images = []
    for v in views:
        if v == "ortho":
            images.append({"endpoint": "ortho/extract", "request": {"layer": DEFAULT_LAYER, "srid": 4326, "wkt": wkt, "crop": "bounding_box"}})
        else:
            images.append({"endpoint": "oriented/extract", "request": {"layer": "urban", "srid": 4326, "wkt": wkt, "product-type": v,
                                                                       "rotation": "natural", "crop": "bbox"}})
    res = client._send("POST", DETECT_URL, json={
        "wkt": wkt, "srid": 4326, "buffer-meter": 0, "images": images,
        "model-input": {"elements": [{"label": l, "model": "sam3", "detection-threshold": threshold} for l in labels],
                        "include": ["bbox", "confidence"]}})
    client._check(res)
    body = res.json()
    view_of = {im.get("image-id"): views[i] for i, im in enumerate(body.get("images") or []) if i < len(views)}
    return [Detection(f["properties"]["label"], view_of.get(d["imageId"], "unknown"), d.get("confidence", 0))
            for f in body.get("features") or [] for d in f["properties"].get("detections") or []]


def count_by_view(detections: list[Detection], views: list[str]) -> dict[str, int]:
    return {v: sum(1 for d in detections if d.view == v) for v in views}
