"""How old the evidence is. Old data still proves sizes, but not recent work, so the agent flags it instead of trusting it.

Vexcel gives an ortho date estimate per parcel. Matterport's `created` date is when a model was added to an account,
so the scan's own photo date (in its preview image's file name, e.g. 11.26.2024_12.36.17.jpg) is used instead.
"""
from __future__ import annotations

import re
from datetime import date, datetime

AERIAL_STALE_DAYS = 365   # an aerial older than this can't show whether recent roof work happened
SCAN_STALE_DAYS = 90      # a construction draw needs a recent scan of the finished work


def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value)[:10]).date()
    except ValueError:
        return None


def scan_date(image_url: str | None) -> date | None:
    """The photo date Matterport writes into a scan's preview image file name (MM.DD.YYYY_HH.MM.SS.jpg)."""
    m = re.search(r"/(\d\d)\.(\d\d)\.(\d{4})_\d\d\.\d\d\.\d\d\.jpe?g", image_url or "")
    if not m:
        return None
    try:
        return date(int(m.group(3)), int(m.group(1)), int(m.group(2)))
    except ValueError:
        return None


def age_days(d: date | None, today: date | None = None) -> int | None:
    return None if d is None else ((today or date.today()) - d).days


def describe(d: date | None, today: date | None = None) -> str:
    """'Jan 2025, 22 months ago'"""
    if d is None:
        return "date unknown"
    days = age_days(d, today)
    months = round(days / 30.44)
    ago = "this month" if months < 1 else f"{months} month{'s' if months != 1 else ''} ago" if months < 24 else f"{months // 12} years ago"
    return f"{d:%b %Y}, {ago}"


def stamp(source: str, d: date | None, stale_after: int, today: date | None = None) -> dict:
    days = age_days(d, today)
    return {"source": source, "date": d.isoformat() if d else None, "label": describe(d, today),
            "age_days": days, "stale": days is not None and days > stale_after}
