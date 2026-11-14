"""Run the live deep agent on every demo claim and compare its decisions with the plain-code rules' answers.

Run from backend/:  .venv/bin/python -m scripts.eval_agent [--rounds 1] [CLAIM_ID ...]
Free models only (Groq free tier, then local Ollama). Prints one line per run and a summary.
"""
import argparse
import json
import logging
import time

from app.agent.runner import outcome_from, run_claim
from app.fixtures import CLAIMS

logging.basicConfig(level=logging.ERROR)


def money(o):
    return [o["a"][1], o["b"][1]]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ids", nargs="*")
    ap.add_argument("--rounds", type=int, default=1)
    args = ap.parse_args()
    claims = [c for c in CLAIMS if not args.ids or c["id"] in args.ids]
    rows = []
    for r in range(args.rounds):
        for base in claims:
            c = json.loads(json.dumps(base))
            t = time.time()
            steps = []
            try:
                run = run_claim(c, steps.append)
                out = outcome_from(run, c)
                err = None
            except Exception as e:
                run, out, err = None, None, f"{type(e).__name__}: {str(e)[:120]}"
            exp = base["outcome"]
            ok = out is not None and out["status"] == exp["status"] and _close(money(out), money(exp))
            row = {"round": r + 1, "id": c["id"], "ok": ok, "secs": round(time.time() - t),
                   "status": out and out["status"], "expected": exp["status"], "amounts": out and money(out), "expected_amounts": money(exp),
                   "live": bool(run and run.proposed), "overruled": out and out.get("overruled"),
                   "plan_versions": run and len(run.plans), "evidence_files": run and len(run.files),
                   "models": run and {n: run.served.count(n) for n in set(run.served)}, "error": err}
            rows.append(row)
            print(json.dumps(row), flush=True)
    live = [r for r in rows if r["live"] and not r["overruled"]]
    print(f"SUMMARY runs={len(rows)} correct={sum(r['ok'] for r in rows)} agent_decided_live={len(live)} "
          f"overruled={sum(1 for r in rows if r['overruled'])} errors={sum(1 for r in rows if r['error'])} "
          f"plan_changed={sum(1 for r in rows if (r['plan_versions'] or 0) > 1)} avg_secs={sum(r['secs'] for r in rows) / max(1, len(rows)):.0f}")


def _close(a, b):
    def num(x):
        if isinstance(x, (int, float)):
            return float(x)
        try:
            return float(str(x).replace("$", "").replace("/mo", "").replace(",", ""))
        except ValueError:
            return None
    return all((num(x) is None and num(y) is None) or (num(x) is not None and num(y) is not None and abs(num(x) - num(y)) <= max(2, 0.01 * abs(num(y))))
               for x, y in zip(a, b))


if __name__ == "__main__":
    main()
