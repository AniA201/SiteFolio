"""Vexcel aerial imagery client.

One call clips Vexcel's latest orthophoto (about 7.5 cm per pixel) to a square around a lat/lon. The key goes in
the X-API-KEY header. Hackathon keys cover Houston and Los Angeles only; anywhere else answers 403.
Roof attributes, obliques and object detection come from Vexcel's own tutorial (linked from the keys card).
"""
from __future__ import annotations

import math

import httpx

ORTHO_URL = "https://api.vexcelgroup.com/v2/ortho/extract"
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
    def __init__(self, api_key: str, http: httpx.Client | None = None, timeout: float = 60):
        if not api_key:
            raise VexcelError("Vexcel API key is not set (VEXCEL_API_KEY).")
        self._key = api_key
        self._http = http or httpx.Client(timeout=timeout)

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
        res = self._http.post(ORTHO_URL, json=body, headers={"X-API-KEY": self._key})
        if res.status_code == 403:
            raise VexcelError("Vexcel refused this location (HTTP 403). Hackathon keys cover Houston and Los Angeles only.")
        if res.status_code == 401:
            raise VexcelError("Vexcel rejected the key (HTTP 401).")
        res.raise_for_status()
        if not res.headers.get("content-type", "").startswith("image/"):
            raise VexcelError(f"Vexcel answered {res.headers.get('content-type')} instead of an image: {res.text[:200]}")
        return res.content
