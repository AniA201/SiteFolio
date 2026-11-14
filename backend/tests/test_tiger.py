"""Tiger Data history against a real TimescaleDB. Skipped unless TIGER_TEST_URL is set, e.g. a local container:
  docker run -d --name plumbline-tsdb -e POSTGRES_PASSWORD=localtest -p 55432:5432 timescale/timescaledb:latest-pg17
  TIGER_TEST_URL=postgresql://postgres:localtest@localhost:55432/postgres pytest tests/test_tiger.py
"""
import asyncio
import os
import time

import pytest

URL = os.environ.get("TIGER_TEST_URL")
pytestmark = pytest.mark.skipif(not URL, reason="set TIGER_TEST_URL to a TimescaleDB to run these")


@pytest.fixture
def tiger():
    from psycopg import connect

    from app.tiger import TigerHistory
    with connect(URL, autocommit=True) as db:
        db.execute("DROP MATERIALIZED VIEW IF EXISTS history_weekly CASCADE")
        db.execute("DROP TABLE IF EXISTS history_events, surcharge_registry, claim_state CASCADE")
    t = TigerHistory(URL)
    t.initialize()
    return t


def test_schema_uses_hypertable_continuous_aggregate_and_compression(tiger):
    from psycopg import connect
    with connect(URL) as db:
        assert db.execute("SELECT count(*) FROM timescaledb_information.hypertables WHERE hypertable_name='history_events'").fetchone()[0] == 1
        assert db.execute("SELECT count(*) FROM timescaledb_information.continuous_aggregates WHERE view_name='history_weekly'").fetchone()[0] == 1
        jobs = {r[0] for r in db.execute("SELECT proc_name FROM timescaledb_information.jobs").fetchall()}
        assert "policy_compression" in jobs and "policy_refresh_continuous_aggregate" in jobs


def _dup_claim():
    from app.fixtures import BUILDINGS, CLAIMS
    c = next(c for c in CLAIMS if c["kind"] == "rentdup")
    return c, str(BUILDINGS[c["b"]]["cs"])


def test_registry_is_seeded_so_the_double_charge_check_finds_the_roof_surcharge(tiger):
    _, pid = _dup_claim()
    hits = tiger.active_surcharges(pid, "roof")
    assert len(hits) == 1
    tiger.initialize()  # seeding twice doesn't duplicate
    assert len(tiger.active_surcharges(pid, "roof")) == 1


def test_writes_are_queued_and_the_dashboard_shows_money(tiger):
    started = time.perf_counter()
    for i in range(50):
        tiger.record("CLM-T", "owner", "check_step", {"n": i})
    tiger.record("CLM-T", "owner", "decision", {"action": "ok"}, paid=100, held=40)
    tiger.save_claim({"id": "CLM-T"}, "partial", 3)
    assert time.perf_counter() - started < 0.05  # nothing waited on the database
    tiger.flush()
    d = tiger.dashboard("owner")
    assert d["connected"] and d["events"] == 51 and d["query_ms"] >= 0
    assert d["weekly"][0]["paid"] == 100 and d["weekly"][0]["held"] == 40
    assert [r["claim"]["id"] for r in tiger.load_claims()] == ["CLM-T"]


def test_engine_denies_a_duplicate_rent_charge_from_the_registry(tiger, monkeypatch):
    from app import engine as eng
    monkeypatch.setattr(eng, "STEP_DELAY", 0)
    cid = _dup_claim()[0]["id"]

    async def go():
        e = eng.Engine(history=tiger)
        e.start()
        e.ingest(cid) or e.run(cid)  # the rent application arrives as an incoming document
        for _ in range(300):
            await asyncio.sleep(0.01)
            if e.status.get(cid) not in ("running", "ready", None):
                break
        await e.stop()
        return e
    e = asyncio.run(go())
    c = e.find(cid)
    assert e.status[cid] == "denied" and c["history_check"]["active_count"] == 1
