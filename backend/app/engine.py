"""In-memory claim store and agent runner.

The runner currently replays each claim's scripted plan one step at a time
(STEP_DELAY apart) and broadcasts every change to subscribed clients over SSE.
Swap `_run_claim` for the real deep agent later; the state shape stays the same.
"""
import asyncio
import copy
from datetime import datetime

from .fixtures import CLAIMS
from .rules import build_judge_claim

STEP_DELAY = 0.55
LOG_LIMIT = 60
WHO = {"coordinator": "Coordinator", "roof": "Roof inspector", "interior": "Interior inspector",
       "records": "Records clerk", "rules": "Rules + math"}


class Engine:
    def __init__(self) -> None:
        self.reset_all()
        self._subs: set[asyncio.Queue] = set()
        self._wake = asyncio.Event()
        self._task: asyncio.Task | None = None

    # ---------- state ----------
    def reset_all(self) -> None:
        fixtures = copy.deepcopy(CLAIMS)
        self.claims: list[dict] = [c for c in fixtures if not c.get("intake")]
        self.samples: dict[str, dict] = {c["id"]: c for c in fixtures if c.get("intake")}
        self.steps: dict[str, int] = {}
        self.status: dict[str, str] = {}
        self.review: dict[str, str] = {}
        self.retry: dict[str, bool] = {}
        self.log: list[dict] = []
        self.queue: list[str] = []
        self.current: str | None = None
        self.judge_n = 1
        self.upload_n = 0
        self.rev = 0

    def find(self, cid: str) -> dict | None:
        return next((c for c in self.claims if c["id"] == cid), None)

    @property
    def running(self) -> bool:
        return self.current is not None or bool(self.queue)

    def snapshot(self) -> dict:
        return {
            "rev": self.rev, "claims": self.claims, "samples": list(self.samples.values()),
            "steps": self.steps, "status": self.status, "review": self.review, "retry": self.retry,
            "log": self.log, "queue": self.queue, "current": self.current,
        }

    def _changed(self) -> None:
        self.rev += 1
        snap = self.snapshot()
        for q in list(self._subs):
            # Drop stale frames for slow clients; only the newest snapshot matters.
            while not q.empty():
                q.get_nowait()
            q.put_nowait(snap)
        self._wake.set()

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self._subs.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subs.discard(q)

    # ---------- actions ----------
    def _start(self, cid: str) -> None:
        self.status[cid] = "running"
        self.steps[cid] = 0
        self.current = cid

    def run(self, cid: str) -> None:
        if self.running or not self.find(cid):
            return
        self._start(cid)
        self._changed()

    def run_all(self, persona: str) -> None:
        waiting = [c["id"] for c in self.claims
                   if c["persona"] == persona and self.status.get(c["id"], "ready") == "ready"
                   and c["id"] not in self.queue and c["id"] != self.current]
        self.queue.extend(waiting)
        self._changed()

    def reset(self, cid: str) -> None:
        if self.current == cid:
            return
        self.steps[cid] = -1
        self.status[cid] = "ready"
        self.review.pop(cid, None)
        self.retry.pop(cid, None)
        self._changed()

    def mark_retry(self, cid: str) -> None:
        # Payments are idempotent: a retry returns the existing receipt.
        self.retry[cid] = True
        self._changed()

    def decide(self, cid: str, decision: str | None) -> None:
        if decision:
            self.review[cid] = decision
        else:
            self.review.pop(cid, None)
        self._changed()

    def ingest(self, sample_id: str) -> str | None:
        sample = self.samples.pop(sample_id, None)
        if not sample:
            return None
        self.claims.append(sample)
        self.queue.append(sample["id"])
        self._changed()
        return sample["id"]

    def next_upload_id(self) -> str:
        self.upload_n = getattr(self, "upload_n", 0) + 1
        return f"UPL-{self.upload_n:03d}"

    def add_claim(self, claim: dict) -> str:
        """Add a claim built from an uploaded document and queue the agent on it."""
        self.claims.insert(0, claim)
        self.queue.append(claim["id"])
        self._changed()
        return claim["id"]

    def judge(self, area: int, amount: int, bank: str, hidden: str) -> str:
        claim = build_judge_claim(area, amount, bank, hidden, self.judge_n)
        self.judge_n += 1
        self.claims.insert(0, claim)
        self.queue.append(claim["id"])
        self._changed()
        return claim["id"]

    # ---------- runner ----------
    def start(self) -> None:
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()

    async def _loop(self) -> None:
        while True:
            if self.current is None and self.queue:
                self._start(self.queue.pop(0))
                self._changed()
            if self.current is None:
                self._wake.clear()
                await self._wake.wait()
                continue
            await self._run_claim(self.current)

    async def _run_claim(self, cid: str) -> None:
        claim = self.find(cid)
        while self.current == cid:
            cur = self.steps.get(cid, 0)
            if cur >= len(claim["steps"]):
                self.status[cid] = claim["outcome"]["status"]
                self.current = None
                self._changed()
                return
            await asyncio.sleep(STEP_DELAY)
            who, text, res = claim["steps"][cur][:3]
            self.log.insert(0, {"t": datetime.now().strftime("%H:%M:%S"), "who": WHO[who],
                                "text": f"{cid} · {text}", "ok": res})
            del self.log[LOG_LIMIT:]
            self.steps[cid] = cur + 1
            self._changed()
