from datetime import date

from app.freshness import describe, scan_date, stamp

TODAY = date(2026, 11, 14)


def test_scan_date_from_matterport_image_name():
    assert scan_date("https://cdn-2.matterport.com/apifs/models/x/images/y/11.26.2024_12.36.17.jpg?t=1") == date(2024, 11, 26)
    assert scan_date("https://cdn/x/HePjN7kzEQB-Living_Room.jpg") is None


def test_describe_and_stale():
    assert describe(date(2025, 1, 7), TODAY) == "Jan 2025, 22 months ago"
    assert stamp("Vexcel aerial", date(2025, 1, 7), 365, TODAY)["stale"]
    assert not stamp("Matterport scan", date(2026, 10, 1), 90, TODAY)["stale"]
    assert stamp("x", None, 90, TODAY) == {"source": "x", "date": None, "label": "date unknown", "age_days": None, "stale": False}
