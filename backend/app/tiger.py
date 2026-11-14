"""Tiger Cloud event history and surcharge registry.

Writes go through one background thread and one reused connection, so a check never waits on the database: events
are appended in order, and each claim's latest state is coalesced and saved about once a second.
"""
import logging
import queue
import re
import threading
from datetime import date
from time import perf_counter

from psycopg import connect
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from .fixtures import SURCHARGES
from .settings import settings

log = logging.getLogger("plumbline.tiger")


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
CREATE TABLE IF NOT EXISTS claim_state (
  claim_id TEXT PRIMARY KEY,
  claim JSONB NOT NULL,
  status TEXT NOT NULL,
  steps INTEGER NOT NULL DEFAULT 0,
  review TEXT,
  retry BOOLEAN NOT NULL DEFAULT false,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
)""", """
CREATE MATERIALIZED VIEW IF NOT EXISTS history_weekly
WITH (timescaledb.continuous, timescaledb.materialized_only = false) AS
SELECT time_bucket('1 week', at) AS week, persona,
       count(*) AS events, sum(paid) AS paid, sum(held) AS held
FROM history_events GROUP BY 1, 2
WITH NO DATA""", """SELECT add_continuous_aggregate_policy('history_weekly',
  start_offset => INTERVAL '8 weeks', end_offset => INTERVAL '1 hour',
  schedule_interval => INTERVAL '1 hour', if_not_exists => TRUE)""",
# Columnar compression for events older than a week; recent events stay row-based for fast inserts.
"""ALTER TABLE history_events SET (timescaledb.compress, timescaledb.compress_segmentby = 'persona',
  timescaledb.compress_orderby = 'at DESC')""",
"SELECT add_compression_policy('history_events', INTERVAL '7 days', if_not_exists => TRUE)")


class TigerHistory:
    def __init__(self, url=None):
        self.url = url or settings.tiger_database_url
        self._events: queue.Queue = queue.Queue()
        self._claims: dict = {}
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._writer = None
        self._db = None

    @property
    def enabled(self):
        return bool(self.url)

    def initialize(self):
        if not self.enabled:
            return
        with connect(self.url, autocommit=True) as db:
            for statement in SCHEMA:
                try:
                    db.execute(statement)
                except Exception as e:  # e.g. compression already set up with other options: keep going
                    log.warning("Tiger schema step skipped: %s", str(e)[:160])
            self._seed_registry(db)
        self._writer = threading.Thread(target=self._write_loop, name="tiger-writer", daemon=True)
        self._writer.start()

    def _seed_registry(self, db):
        """The surcharge registry starts with the city's known active surcharges, so the double-charge check has data."""
        month = lambda v: date.fromisoformat(f"{v}-01")
        for s in SURCHARGES:
            per_unit = re.sub(r"[^0-9.]", "", str(s.get("per_unit") or "")) or "0"
            db.execute("""INSERT INTO surcharge_registry (property_id, building, work, approved, ends, per_unit, source_claim_id)
                VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (source_claim_id) DO NOTHING""",
                       (str(s["property_id"]), s["building"], s["work"], month(s["approved"]), month(s["ends"]), per_unit,
                        f"registry-{s['property_id']}-{s['work'].lower().replace(' ', '-')}"))

    # ---------- writes: queued, written by one background thread ----------
    def record(self, claim_id, persona, kind, detail=None, paid=0, held=0):
        if not self.enabled:
            return
        self._events.put((claim_id, persona, kind, detail or {}, paid or 0, held or 0))
        self._wake.set()

    def save_claim(self, claim, status, steps=0, review=None, retry=False):
        if not self.enabled:
            return
        with self._lock:  # only the newest state per claim is written
            self._claims[claim["id"]] = (claim, status, steps, review, retry)
        self._wake.set()

    def _conn(self):
        if self._db is None or self._db.closed:
            self._db = connect(self.url, autocommit=True)
        return self._db

    def _write_loop(self):
        while True:
            self._wake.wait(timeout=1.0)
            self._wake.clear()
            try:
                self.flush()
            except Exception as e:  # network blip: drop the connection, retry on the next tick
                log.warning("Tiger write failed, will retry: %s", str(e)[:160])
                try:
                    self._db and self._db.close()
                finally:
                    self._db = None

    def flush(self):
        """Write everything queued so far (also used by tests)."""
        events = []
        while not self._events.empty():
            events.append(self._events.get_nowait())
        with self._lock:
            claims, self._claims = self._claims, {}
        if not events and not claims:
            return
        db = self._conn()
        try:
            with db.cursor() as cur:
                if events:
                    cur.executemany("INSERT INTO history_events (claim_id, persona, kind, detail, paid, held) VALUES (%s,%s,%s,%s,%s,%s)",
                                    [(c, p, k, Jsonb(d), pa, h) for c, p, k, d, pa, h in events])
                for claim, status, steps, review, retry in claims.values():
                    cur.execute("""INSERT INTO claim_state (claim_id, claim, status, steps, review, retry)
                        VALUES (%s,%s,%s,%s,%s,%s)
                        ON CONFLICT (claim_id) DO UPDATE SET claim=EXCLUDED.claim, status=EXCLUDED.status,
                        steps=EXCLUDED.steps, review=EXCLUDED.review, retry=EXCLUDED.retry, updated_at=now()""",
                                (claim["id"], Jsonb(claim), status, steps, review, retry))
        except Exception:
            for e in events:  # keep them for the next try
                self._events.put(e)
            with self._lock:
                for cid, v in claims.items():
                    self._claims.setdefault(cid, v)
            raise

    def load_claims(self):
        if not self.enabled:
            return []
        with connect(self.url, row_factory=dict_row) as db:
            return db.execute("SELECT claim, status, steps, review, retry FROM claim_state ORDER BY updated_at").fetchall()

    def clear_claims(self):
        if not self.enabled:
            return
        with self._lock:
            self._claims.clear()
        with connect(self.url) as db:
            db.execute("DELETE FROM claim_state")

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
            return {"connected": False, "events": 0, "weekly": [], "surcharges": [], "recent": []}
        started = perf_counter()
        with connect(self.url, row_factory=dict_row) as db:
            events = db.execute("SELECT count(*) AS n FROM history_events").fetchone()["n"]
            weekly = db.execute("SELECT week, events, paid, held FROM history_weekly WHERE persona=%s ORDER BY week DESC LIMIT 7", (persona,)).fetchall()
            surcharges = db.execute("SELECT property_id, building, work, approved, ends, per_unit FROM surcharge_registry ORDER BY approved DESC").fetchall()
            recent = db.execute("SELECT at, claim_id, kind, detail FROM history_events WHERE persona=%s ORDER BY at DESC, id DESC LIMIT 60", (persona,)).fetchall()
        return {"connected": True, "events": events,
                "query_ms": round((perf_counter() - started) * 1000, 1),
                "weekly": [{**row, "week": row["week"].isoformat(), "paid": float(row["paid"]), "held": float(row["held"])} for row in weekly],
                "surcharges": [{**row, "approved": row["approved"].isoformat(), "ends": row["ends"].isoformat(), "per_unit": float(row["per_unit"])} for row in surcharges],
                "recent": [{**row, "at": row["at"].isoformat()} for row in recent]}
