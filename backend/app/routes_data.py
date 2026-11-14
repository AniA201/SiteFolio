"""Read-only routes onto the building data layers. Each answers 503 with a plain message until its key is set."""
from functools import lru_cache

from fastapi import APIRouter, HTTPException, Query, Response

from .integrations.matterport import MatterportClient, MatterportError, ModelIndex, total_sqft
from .integrations.vexcel import VexcelClient, VexcelError
from .settings import settings

router = APIRouter(prefix="/api/data")


def _matterport() -> MatterportClient:
    try:
        return MatterportClient(settings.matterport_api_key or "", settings.matterport_api_token or "")
    except MatterportError as e:
        raise HTTPException(503, str(e))


@lru_cache(maxsize=1)
def _index() -> ModelIndex:
    return ModelIndex.load(settings.models_index_csv)


def _call(fn, *args):
    try:
        return fn(*args)
    except MatterportError as e:
        raise HTTPException(502, str(e))


@router.get("/matterport/models/near")
def models_near(lat: float, lon: float, radius_m: float = Query(150, gt=0, le=5000)):
    if not settings.models_index_csv.exists():
        raise HTTPException(503, f"models_index.csv not found at {settings.models_index_csv.name}; set MODELS_INDEX_CSV.")
    return [{"sid": m.sid, "name": m.name, "distance_m": round(d, 1), "lat": m.lat, "lon": m.lon, "segment": m.segment,
             "costar_id": m.costar_id, "homes_listing_id": m.homes_listing_id} for d, m in _index().near(lat, lon, radius_m)]


@router.get("/matterport/models/{model_id}")
def model_basics(model_id: str):
    return _call(_matterport().basics, model_id)


@router.get("/matterport/models/{model_id}/rooms")
def model_rooms(model_id: str):
    rooms = _call(_matterport().rooms, model_id)
    return {"rooms": [{"id": r.id, "floor": r.floor_label, "label": r.label, "confidence": r.confidence,
                       "area_sqm": r.area_sqm, "area_sqft": None if r.area_sqft is None else round(r.area_sqft, 1)} for r in rooms],
            "total_sqft": round(total_sqft(rooms), 1)}


@lru_cache(maxsize=64)
def _ortho(lat: float, lon: float, half_side_m: float, pixels: int) -> bytes:
    return VexcelClient(settings.vexcel_api_key or "").ortho(lat, lon, half_side_m, pixels)


@router.get("/vexcel/ortho.jpg")
def vexcel_ortho(lat: float, lon: float, half_side_m: float = Query(70, gt=5, le=500), pixels: int = Query(1400, ge=200, le=4000)):
    if not settings.vexcel_api_key:
        raise HTTPException(503, "Vexcel API key is not set (VEXCEL_API_KEY).")
    try:
        img = _ortho(round(lat, 6), round(lon, 6), half_side_m, pixels)
    except VexcelError as e:
        raise HTTPException(502, str(e))
    return Response(img, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=3600"})


@router.get("/vexcel/property")
def vexcel_property(lat: float, lon: float):
    """Footprint, roof shape/material/condition and counted roof objects (AC units) for the parcel at a point."""
    if not settings.vexcel_api_key:
        raise HTTPException(503, "Vexcel API key is not set (VEXCEL_API_KEY).")
    try:
        facts = VexcelClient(settings.vexcel_api_key).property(lat, lon)
    except VexcelError as e:
        raise HTTPException(502, str(e))
    if facts is None:
        raise HTTPException(404, "Vexcel has no parcel at this point. Nudge it onto the roof.")
    p = facts.primary
    return {"collection": facts.collection, "inside_parcel": facts.inside_parcel,
            "total_footprint_sqft": round(facts.total_footprint_sqft), "total_ac_units": facts.total_ac_units,
            "primary": None if p is None else {k: getattr(p, k) for k in p.__dataclass_fields__},
            "structures": len(facts.structures)}
