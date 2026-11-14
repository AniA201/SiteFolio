"""Tiger Cloud event history and surcharge registry."""
from psycopg import connect
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from .settings import settings


SCHEMA = ("""
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
);""", "SELECT create_hypertable('history_events', 'at', if_not_exists => TRUE)", """
CREATE TABLE IF NOT EXISTS surcharge_registry (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  property_id TEXT NOT NULL,
  building TEXT NOT NULL,
  work TEXT NOT NULL,
  approved DATE NOT NULL,
  ends DATE NOT NULL,
  per_unit NUMERIC NOT NULL,
  source_claim_id TEXT UNIQUE
);""", """CREATE INDEX IF NOT EXISTS surcharge_active_lookup
  ON surcharge_registry (property_id, lower(work), ends)""", """
CREATE MATERIALIZED VIEW IF NOT EXISTS history_weekly
WITH (timescaledb.continuous, timescaledb.materialized_only = false) AS
SELECT time_bucket('1 week', at) AS week, persona,
       count(*) AS events, sum(paid) AS paid, sum(held) AS held
FROM history_events GROUP BY 1, 2
WITH NO DATA""", """SELECT add_continuous_aggregate_policy('history_weekly',
  start_offset => INTERVAL '8 weeks', end_offset => INTERVAL '1 hour',
  schedule_interval => INTERVAL '1 hour', if_not_exists => TRUE)""")


class TigerHistory:
    def __init__(self, url=None):
        self.url = url or settings.tiger_database_url

    @property
    def enabled(self):
        return bool(self.url)

    def initialize(self):
        if not self.enabled:
            return
        with connect(self.url) as db:
            for statement in SCHEMA:
                db.execute(statement)

    def record(self, claim_id, persona, kind, detail=None, paid=0, held=0):
        if not self.enabled:
            return
        with connect(self.url) as db:
            db.execute("INSERT INTO history_events (claim_id, persona, kind, detail, paid, held) VALUES (%s,%s,%s,%s,%s,%s)",
                       (claim_id, persona, kind, Jsonb(detail or {}), paid, held))

    def active_surcharges(self, property_id, work):
        if not self.enabled:
            return []
        with connect(self.url, row_factory=dict_row) as db:
            return db.execute("SELECT property_id, building, work, approved, ends, per_unit FROM surcharge_registry WHERE property_id=%s AND lower(work)=lower(%s) AND ends >= CURRENT_DATE ORDER BY approved DESC", (property_id, work)).fetchall()

    def register_surcharge(self, property_id, building, work, approved, ends, per_unit, source_claim_id):
        if not self.enabled:
            return
        with connect(self.url) as db:
            db.execute("""INSERT INTO surcharge_registry
                (property_id, building, work, approved, ends, per_unit, source_claim_id)
                VALUES (%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (source_claim_id) DO NOTHING""",
                (property_id, building, work, approved, ends, per_unit, source_claim_id))

    def dashboard(self, persona):
        if not self.enabled:
            return {"connected": False, "events": 0, "weekly": [], "surcharges": []}
        with connect(self.url, row_factory=dict_row) as db:
            events = db.execute("SELECT count(*) AS n FROM history_events").fetchone()["n"]
            weekly = db.execute("SELECT week, events, paid, held FROM history_weekly WHERE persona=%s ORDER BY week DESC LIMIT 7", (persona,)).fetchall()
            surcharges = db.execute("SELECT property_id, building, work, approved, ends, per_unit FROM surcharge_registry ORDER BY approved DESC").fetchall()
        return {"connected": True, "events": events,
                "weekly": [{**row, "week": row["week"].isoformat(), "paid": float(row["paid"]), "held": float(row["held"])} for row in weekly],
                "surcharges": [{**row, "approved": row["approved"].isoformat(), "ends": row["ends"].isoformat(), "per_unit": float(row["per_unit"])} for row in surcharges]}
