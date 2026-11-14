"""Sample data loaded from JSON fixtures in app/data.

All buildings, parties, IDs and numbers are sample data. When the real
data layers are connected, these fixtures become recorded API responses
that the demo can fall back to.
"""
import json
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"


def _load(name: str):
    with open(DATA_DIR / name, encoding="utf-8") as f:
        return json.load(f)


BUILDINGS: dict = _load("buildings.json")
PARTIES: dict = _load("parties.json")
PERSONAS: dict = _load("personas.json")
SURCHARGES: list = _load("surcharges.json")
CLAIMS: list = _load("claims.json")
