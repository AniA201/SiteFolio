"""Tiger Cloud event history and surcharge registry."""
import os

from psycopg import connect
from psycopg.rows import dict_row


SCHEMA = """
CREATE EXTENSION IF NOT EXISTS timescaledb;
CREATE TABLE IF NOT EXISTS history_events (
  id BIGINT GENERATED ALWAYS AS IDENTITY,
  at TIMESTAMPTZ NOT NULL DEFAULT now(),
  claim_id TEXT NOT NULL,
  persona TEXT NOT NULL,
  kind TEXT NOT NULL,
  detail JSONB NOT NULL DEFAULT '{}'::jsonb,
  paid NUMERIC NOT NULL DEFAULT 0,
  held NUMERIC NOT NULL DEFAULT 0,
  PRIMARY KEY (id, at)
);
SELECT create_hypertable('history_events', 'at', if_not_exists => TRUE);
CREATE TABLE IF NOT EXISTS surcharge_registry (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  property_id TEXT NOT NULL,
  building TEXT NOT NULL,
  work TEXT NOT NULL,
  approved DATE NOT NULL,
  ends DATE NOT NULL,
  per_unit NUMERIC NOT NULL,
  source_claim_id TEXT UNIQUE
);
CREATE INDEX IF NOT EXISTS surcharge_active_lookup
  ON surcharge_registry (property_id, lower(work), ends);
CREATE MATERIALIZED VIEW IF NOT EXISTS history_weekly
WITH (timescaledb.continuous) AS
SELECT time_bucket('1 week', at) AS week, persona,
       count(*) AS events, sum(paid) AS paid, sum(held) AS held
FROM history_events GROUP BY 1, 2
WITH NO DATA;
"""


class TigerHistory:
    def __init__(self, url=None):
        self.url = url or os.getenv("TIGER_DATABASE_URL")

    @property
    def enabled(self):
        return bool(self.url)

    def initialize(self):
        if not self.enabled:
            return
        with connect(self.url) as db:
            db.execute(SCHEMA)

    def record(self, claim_id, persona, kind, detail=None, paid=0, held=0):
        if not self.enabled:
            return
        from psycopg.types.json import Jsonb
        with connect(self.url) as db:
            db.execute("INSERT INTO history_events (claim_id, persona, kind, detail, paid, held) VALUES (%s,%s,%s,%s,%s,%s)",
                       (claim_id, persona, kind, Jsonb(detail or {}), paid, held))

    def active_surcharges(self, property_id, work):
        if not self.enabled:
            return []
        with connect(self.url, row_factory=dict_row) as db:
            return db.execute("SELECT property_id, building, work, approved, ends, per_unit FROM surcharge_registry WHERE property_id=%s AND lower(work)=lower(%s) AND ends >= CURRENT_DATE ORDER BY approved DESC", (property_id, work)).fetchall()

    def dashboard(self, persona):
        if not self.enabled:
            return {"connected": False, "events": 0, "weekly": [], "surcharges": []}
        with connect(self.url, row_factory=dict_row) as db:
            events = db.execute("SELECT count(*) AS n FROM history_events").fetchone()["n"]
            weekly = db.execute("SELECT week, events, paid, held FROM history_weekly WHERE persona=%s ORDER BY week DESC LIMIT 7", (persona,)).fetchall()
            surcharges = db.execute("SELECT property_id, building, work, approved, ends, per_unit FROM surcharge_registry ORDER BY approved DESC").fetchall()
        return {"connected": True, "events": events, "weekly": weekly, "surcharges": surcharges}
