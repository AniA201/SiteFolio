"""Normalised building records from the CoStar kit, joined to their Matterport model ids."""
from __future__ import annotations

import csv
import io
import json
from dataclasses import asdict, dataclass, field
from typing import Callable, Iterator

from ..integrations.costar import CostarKit

PROPERTY_TYPES_OF_INTEREST = {"Office", "Multifamily", "Industrial", "Flex", "GeneralRetail"}


@dataclass
class BuildingRecord:
    id: str
    name: str
    address: str
    city: str
    state: str
    lat: float | None
    lon: float | None
    type: str
    status: str
    gba_sqft: float | None
    stories: int | None
    typical_floor_sqft: float | None
    units: int | None
    year_built: int | None
    year_renovated: int | None
    parking_spaces: int | None
    model_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def _street(a: dict) -> str:
    parts = [a.get("streetNumber"), a.get("streetDirection"), a.get("streetName"), a.get("streetType")]
    return " ".join(str(p) for p in parts if p)


def _year(events: list[dict], *types: int) -> int | None:
    years = [e.get("year") for e in events or [] if e.get("eventType") in types and e.get("year")]
    return max(years) if years else None


def model_ids_by_property(kit: CostarKit) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for row in kit.rows("commercial-properties.csv"):
        if row.get("matterportmodelid"):
            out.setdefault(row["propertyid"], []).append(row["matterportmodelid"])
    return out


def iter_buildings(kit: CostarKit, keep: Callable[[BuildingRecord], bool] = lambda b: True) -> Iterator[BuildingRecord]:
    enums = json.load(kit.zip.open("schemas/enums.json"))
    ptype, cstatus = enums["PropertyType"], enums["ConstructionStatus"]
    models = model_ids_by_property(kit)
    with kit.zip.open("data/commercial-property.jsonl") as f:
        for line in io.TextIOWrapper(f, encoding="utf-8"):
            r = json.loads(line)
            a = r.get("primaryAddress") or {}
            apt = r.get("propertyApartment") or {}
            spaces = sum(p.get("totalSpaces") or 0 for p in r.get("parking") or []) or None
            b = BuildingRecord(
                id=str(r["id"]), name=(r.get("buildingName") or _street(a)).strip(), address=_street(a),
                city=(a.get("city") or "").title(), state=a.get("state") or "", lat=a.get("latitude"), lon=a.get("longitude"),
                type=ptype.get(str(r.get("propertyType")), "Unknown"), status=cstatus.get(str(r.get("constructionStatus")), "Unknown"),
                gba_sqft=r.get("grossBuildingAreaSquareFeet"), stories=r.get("numStoriesAboveGrade"),
                typical_floor_sqft=r.get("grossTypicalFloorSquareFeet"), units=apt.get("totalNumUnits"),
                year_built=_year(r.get("constructionEvents"), 2), year_renovated=_year(r.get("constructionEvents"), 4, 5),
                parking_spaces=spaces, model_ids=models.get(str(r["id"]), []))
            if keep(b):
                yield b
