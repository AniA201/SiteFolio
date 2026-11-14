"""In-memory claim store and agent runner.

The runner currently replays each claim's scripted plan one step at a time
(STEP_DELAY apart) and broadcasts every change to subscribed clients over SSE.
Swap `_run_claim` for the real deep agent later; the state shape stays the same.
"""
import asyncio
import copy
from datetime import datetime

from .fixtures import BUILDINGS, CLAIMS
from .intake import EXTRA_BUILDINGS
from .rules import build_judge_claim
from .settings import settings

STEP_DELAY = 0.55
LOG_LIMIT = 60
WHO = {"coordinator": "Coordinator", "roof": "Roof inspector", "interior": "Interior inspector",
       "records": "Records clerk", "rules": "Rules + math"}


class Engine:
    def __init__(self, history=None) -> None:
        self.history = history
        self.reset_all()
        if history and history.enabled:
            for row in history.load_claims():
                claim = row["claim"]
                if not self.find(claim["id"]):
                    self.claims.append(claim)
                    self.samples.pop(claim["id"], None)
                self.status[claim["id"]] = "ready" if row["status"] == "running" else row["status"]
                self.steps[claim["id"]] = row["steps"]
                if row["review"]:
                    self.review[claim["id"]] = row["review"]
                if row["retry"]:
                    self.retry[claim["id"]] = True
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
        self.paused: dict = {}          # claim id -> agent Run waiting at the human pause
        self.agent_memory: dict = {}    # the agent's /memories/ files, for the page
        self.upload_n = 0
        # Never go backwards: open pages ignore snapshots older than the last one they saw, so a reset keeps counting.
        self.rev = getattr(self, "rev", 0) + 1

    def find(self, cid: str) -> dict | None:
        return next((c for c in self.claims if c["id"] == cid), None)

    @property
    def running(self) -> bool:
        return self.current is not None or bool(self.queue)

    def snapshot(self) -> dict:
        return {
            "rev": self.rev, "claims": self.claims, "samples": list(self.samples.values()),
            "steps": self.steps, "status": self.status, "review": self.review, "retry": self.retry,
            "log": self.log, "queue": self.queue, "current": self.current, "buildings_extra": EXTRA_BUILDINGS,
            "agent_memory": self.agent_memory,
        }

    def _changed(self) -> None:
        self.rev += 1
        if self.history:
            for claim in self.claims:
                cid = claim["id"]
                if cid in self.status or cid in self.queue or claim.get("judge"):
                    self.history.save_claim(claim, self.status.get(cid, "ready"),
                                            self.steps.get(cid, 0), self.review.get(cid), self.retry.get(cid, False))
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
        self.paused.pop(cid, None)
        claim = self.find(cid)
        if claim and claim.get("recorded_steps") is not None:  # back to the recorded plan until the agent runs again
            claim["steps"] = claim["recorded_steps"]
            claim["outcome"] = claim.get("recorded_outcome", claim["outcome"])
            claim.pop("agent", None)
            claim.pop("evidence_files", None)
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
        run = self.paused.pop(cid, None) if decision else None
        if run is not None:  # the person decided: resume the same agent run from its pause
            asyncio.run_coroutine_threadsafe(self._resume(cid, run, decision), self._event_loop)

    async def _resume(self, cid: str, run, decision: str) -> None:
        from .agent.runner import resume
        claim = self.find(cid)
        if claim is None:
            return
        loop = asyncio.get_running_loop()
        verb = {"ok": "approved", "sent": "approved and sent the message", "rejected": "rejected"}.get(decision, decision)
        self._push_step(cid, claim, ["coordinator", f"Person {verb}: agent resumed the same run", "done"])
        try:
            await asyncio.to_thread(resume, run, decision, lambda s: loop.call_soon_threadsafe(self._push_step, cid, claim, s))
            claim["evidence_files"] = run.files
            self.agent_memory = run.memory
            self._push_step(cid, claim, ["coordinator", "Run finished and logged", "done"])
        except Exception as e:
            self._push_step(cid, claim, ["coordinator", f"Could not resume the agent ({type(e).__name__}); decision recorded", "warn"])

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
        self._event_loop = asyncio.get_running_loop()  # API routes run in worker threads; they hand work back to this loop
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
        if settings.agent_enabled and await self._run_with_agent(cid, claim):
            return
        await self._replay(cid, claim)

    def _push_step(self, cid: str, claim: dict, step: list) -> None:
        if len(step) > 3:  # map the data source to the claim's call record, so the step shows its source chip
            idx = next((i for i, a in enumerate(claim["apis"]) if a["svc"] == step[3]), None)
            step = step[:3] + ([idx] if idx is not None else [])
        claim["steps"].append(step)
        self.log.insert(0, {"t": datetime.now().strftime("%H:%M:%S"), "who": WHO[step[0]], "text": f"{cid} · {step[1]}", "ok": step[2]})
        del self.log[LOG_LIMIT:]
        self.steps[cid] = len(claim["steps"])
        self._changed()

    async def _run_with_agent(self, cid: str, claim: dict) -> bool:
        """Run the real deep agent; on any failure restore the recorded plan and let the replay run instead."""
        from .agent.runner import outcome_from, run_claim
        loop = asyncio.get_running_loop()
        recorded = claim["steps"]
        claim.setdefault("recorded_steps", recorded)
        claim.setdefault("recorded_outcome", claim["outcome"])
        claim["steps"] = []
        try:
            run = await asyncio.to_thread(run_claim, claim, lambda s: loop.call_soon_threadsafe(self._push_step, cid, claim, s))
        except Exception as e:  # network, rate limit, model refusal: the demo keeps working
            run, error = None, e
        else:
            error = None
        await asyncio.sleep(0)  # let queued step callbacks land
        if run is None or not run.proposed:
            claim["steps"] = claim["recorded_steps"]
            self.steps[cid] = 0
            self.log.insert(0, {"t": datetime.now().strftime("%H:%M:%S"), "who": "Coordinator",
                                "text": f"{cid} · Live agent unavailable ({type(error).__name__ if error else 'no decision'}); replaying the recorded plan", "ok": "warn"})
            return False
        outcome = outcome_from(run, claim)
        if outcome.get("overruled"):
            self._push_step(cid, claim, ["rules", "Rules overruled the agent: " + outcome["overruled"], "warn"])
        claim["outcome"] = outcome
        claim["evidence_files"] = run.files
        claim["agent"] = {"live": True, "plans": run.plans, "models": {n: run.served.count(n) for n in set(run.served)},
                          "overruled": outcome.get("overruled"), "run_id": run.run_id, "trace_url": None}
        self.agent_memory = run.memory
        self.paused[cid] = run
        loop.create_task(self._trace_url(cid, claim, run.run_id))
        self._check_surcharge(cid, claim)
        self.steps[cid] = len(claim["steps"])
        self.status[cid] = claim["outcome"]["status"]
        self.current = None
        self._changed()
        return True

    async def _trace_url(self, cid: str, claim: dict, run_id: str) -> None:
        """LangSmith link for the run, once the trace has been sent (best effort)."""
        from .agent.tracing import trace_url
        url = await asyncio.to_thread(trace_url, run_id)
        if url and claim.get("agent", {}).get("run_id") == run_id:
            claim["agent"]["trace_url"] = url
            self._changed()

    async def _replay(self, cid: str, claim: dict) -> None:
        while self.current == cid:
            cur = self.steps.get(cid, 0)
            if cur >= len(claim["steps"]):
                self._check_surcharge(cid, claim)
                self.status[cid] = claim["outcome"]["status"]
                if self.history:
                    self.history.record(cid, claim["persona"], "check_completed", {"status": self.status[cid]})
                self.current = None
                self._changed()
                return
            await asyncio.sleep(STEP_DELAY)
            who, text, res = claim["steps"][cur][:3]
            self.log.insert(0, {"t": datetime.now().strftime("%H:%M:%S"), "who": WHO[who],
                                "text": f"{cid} · {text}", "ok": res})
            del self.log[LOG_LIMIT:]
            self.steps[cid] = cur + 1
            if self.history:
                self.history.record(cid, claim["persona"], "check_step",
                                    {"worker": who, "text": text, "result": res})
            self._changed()

    def _check_surcharge(self, cid: str, claim: dict) -> None:
        if not (self.history and self.history.enabled and claim["persona"] == "reviewer" and claim["kind"] == "rentdup"):
            return
        building = BUILDINGS.get(claim["b"]) or EXTRA_BUILDINGS.get(claim["b"])
        property_id = building.get("cs") if building else None
        matches = self.history.active_surcharges(property_id, "roof") if property_id else []
        claim["history_check"] = {"property_id": property_id, "work": "roof", "active_count": len(matches), "source": "Tiger Cloud"}
        if matches:
            claim["outcome"]["status"] = "denied"
            claim["outcome"]["reason"] = "An active roof surcharge exists for this property. Review its registry record before approving another charge."
        else:
            claim["outcome"]["status"] = "blocked"
            claim["outcome"]["reason"] = "No active roof surcharge was found in Tiger Cloud. The duplicate-charge result is unverified; review the application manually."
        self.history.record(cid, "reviewer", "surcharge_checked", claim["history_check"])
