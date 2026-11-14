from app import routes_kit


def test_search_ranks_and_filters(monkeypatch):
    index = [
        {"id": "1", "name": "Tamarind Apartments", "address": "1811 Tamarind Ave", "city": "Los Angeles", "type": "Multifamily",
         "stories": 3, "units": 49, "gba_sqft": 55484.0, "year_built": 1962, "models": 7, "model_ids": []},
        {"id": "2", "name": "Tamarind Sunset", "address": "1339 Tamarind Ave", "city": "Los Angeles", "type": "Multifamily",
         "stories": 5, "units": 41, "gba_sqft": 1.0, "year_built": 2026, "models": 0, "model_ids": []},
        {"id": "3", "name": "1113 Vine St", "address": "1113 Vine St", "city": "Houston", "type": "Office",
         "stories": 3, "units": None, "gba_sqft": 99000.0, "year_built": 1917, "models": 4, "model_ids": []},
    ]
    monkeypatch.setattr(routes_kit, "kit", lambda: (index, {"1": {"apartments": {"plans": []}, "tenants": {"count": 4}}}))
    hits = routes_kit.search("tamarind")
    assert [h["id"] for h in hits] == ["1", "2"] and hits[0]["has_rents"] and hits[0]["tenants"] == 4
    assert [h["id"] for h in routes_kit.search("tamarind", scanned=True)] == ["1"]
    assert [h["id"] for h in routes_kit.search("", city="Houston")] == ["3"]
    assert routes_kit.search("nothing matches this") == []
