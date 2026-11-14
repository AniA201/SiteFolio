"""Data the app serves: real buildings when app/data/real/ has been built, otherwise the bundled samples.

Build the real set with `python -m app.real.fetch` then `python -m app.real.build`. Set PLUMBLINE_DATA=sample to force
the samples (the tests do). Real data stays local: app/data/real/ is gitignored.
"""
import json
import os
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
REAL_DIR = DATA_DIR / "real"

USING_REAL = os.getenv("PLUMBLINE_DATA", "real") != "sample" and (REAL_DIR / "claims.json").exists()
_SRC = REAL_DIR if USING_REAL else DATA_DIR


def _load(name: str, default=None):
    p = _SRC / name
    if not p.exists():
        return default
    with open(p, encoding="utf-8") as f:
        return json.load(f)


BUILDINGS: dict = _load("buildings.json")
PARTIES: dict = _load("parties.json")
PERSONAS: dict = _load("personas.json")
SURCHARGES: list = _load("surcharges.json")
CLAIMS: list = _load("claims.json")
META: dict = _load("meta.json", default={}) or {}
