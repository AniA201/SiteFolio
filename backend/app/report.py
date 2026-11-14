"""Evidence reports: a self-contained HTML page per checked claim (prints cleanly to PDF) and its decision record.

Two audiences: the full audit report for the person who decides, and a plain-language proof for tenants.
"""
from __future__ import annotations

import html
from datetime import datetime, timezone

from .fixtures import BUILDINGS, PARTIES, PERSONAS

WHO = {"coordinator": "Coordinator", "roof": "Roof inspector", "interior": "Interior inspector",
       "records": "Records clerk", "rules": "Rules + math"}
STATUS = {"approved": "Verified", "partial": "Partly verified", "reduced": "Reduced", "denied": "Denied", "blocked": "Blocked"}
REVIEW = {"ok": "Approved", "sent": "Message sent", "rejected": "Rejected"}
e = lambda x: html.escape(str(x))


def party(c: dict) -> dict:
    return PARTIES.get(c["party"]) or c.get("party_info") or {"name": "Unknown sender", "role": "Contractor"}


def money(v) -> str:
    return f"${round(v):,}" if isinstance(v, (int, float)) else str(v)


def decision_record(c: dict, review: str | None) -> dict:
    o, B, p = c["outcome"], BUILDINGS[c["b"]], party(c)
    key = lambda s: s.lower().replace(" ", "_")
    return {"id": c["id"], "persona": c["persona"], "from": p["name"], "title": c["title"], "amount": c["amount"],
            "building": {"name": B["name"], "costar_id": B["cs"], "city": B["city"]},
            "checks": [{"claim": x[0], "source_a": x[1], "source_b": x[2], "paper": x[3], "verdict": x[4]} for x in c["cross"]],
            "lines": [{"line": l[0], "paper": l[1], "building": l[2], "ok": l[3] == "ok"} for l in c["lines"]],
            "decision": {"status": o["status"], key(o["a"][0]): o["a"][1], key(o["b"][0]): o["b"][1], "reason": o["reason"]},
            "data_sources": sorted({a["svc"] for a in c["apis"]}),
            "approved_by": REVIEW.get(review, "waiting for a person"),
            **({"solana": {k: c["solana"].get(k) for k in ("signature", "explorer", "signer", "pay", "hold", "sha256", "lender",
                                                            "released", "release_signature")}}
               if (c.get("solana") or {}).get("state") == "recorded" else {}),
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}


STYLE = """
:root{--ink:#0A0A0A;--ink3:#6E6E6E;--g1:#F2F2F2;--g2:#E4E4E4;--amber:#FFAA00;--green:#1E8E4E;--red:#C62F3B}
*{box-sizing:border-box}body{margin:0;background:#fff;color:var(--ink);font:15px/1.5 "Helvetica Neue",Helvetica,Arial,sans-serif}
main{max-width:860px;margin:0 auto;padding:40px 24px 64px}
.over{font-size:11.5px;font-weight:600;letter-spacing:.14em;text-transform:uppercase;color:var(--ink3)}
h1{font-size:38px;letter-spacing:-1.5px;line-height:1.05;margin:8px 0 6px}h2{font-size:19px;margin:34px 0 10px;letter-spacing:-.3px}
.muted{color:var(--ink3)}.pill{display:inline-block;font-size:12px;font-weight:600;padding:4px 10px;border-radius:999px;background:var(--g1)}
.big{display:flex;gap:40px;flex-wrap:wrap;margin:16px 0}.big div{min-width:140px}.big b{display:block;font-size:34px;letter-spacing:-1.2px}
table{width:100%;border-collapse:collapse;font-size:14px}th,td{text-align:left;padding:9px 10px;border-top:1px solid var(--g2);vertical-align:top}
th{font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:var(--ink3);background:var(--g1);border:0}
tr.bad td{background:#FFF6DD}pre{background:#0E0E0E;color:#eee;border-radius:10px;padding:12px;font:12px/1.55 ui-monospace,Menlo,monospace;
white-space:pre-wrap;word-break:break-word;margin:6px 0 0}.call{border:1px solid var(--g2);border-radius:12px;padding:14px;margin-top:10px;break-inside:avoid}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:10px}@media(max-width:640px){.grid{grid-template-columns:1fr}}
img.aerial{width:100%;max-width:420px;border-radius:12px;display:block;margin-top:8px}
.box{background:var(--g1);border-radius:12px;padding:16px;margin-top:12px}.note{font-size:12.5px;color:var(--ink3);margin-top:28px}
.toolbar{display:flex;gap:8px;margin-bottom:22px}.toolbar button{border:0;border-radius:999px;padding:9px 16px;font:inherit;font-size:14px;cursor:pointer;background:#000;color:#fff}
@media print{.toolbar{display:none}main{padding:0}}
"""


def _aerial(B: dict) -> str:
    if not (B.get("real") and B.get("lat")):
        return ""
    half = max(35, round((B["roof"] * 0.0929) ** 0.5 * 0.8))
    src = f"/api/data/vexcel/ortho.jpg?lat={B['lat']}&lon={B['lon']}&half_side_m={half}&pixels=900"
    return f'<img class="aerial" src="{e(src)}" alt="Aerial view of {e(B["name"])}"><div class="muted" style="font-size:12.5px">Vexcel orthophoto · {e(B.get("vexcel_collection") or "")}</div>'


def _solana(c: dict) -> str:
    sol = c.get("solana") or {}
    if sol.get("state") != "recorded":
        return ""
    moved = (f"Paid {money(sol['pay'])}; held {money(sol['hold'])} in a holding account that needs both the lender's and "
             f"Plumbline's signatures." if sol.get("moves") else "No money moved; the decision is recorded.")
    release = (f" The held amount was released later: <a href='{e(sol['release_explorer'])}'>release transaction</a>."
               if sol.get("released") else "")
    return (f"<h2>Recorded on Solana (devnet)</h2><p>{e(moved)} Signed by {e(sol.get('signer'))}. "
            f"<a href='{e(sol['explorer'])}'>View the transaction</a>.{release}</p>"
            f"<p class=muted>Evidence fingerprint (SHA-256): <code>{e(sol.get('sha256'))}</code>. Anyone can recompute it from this "
            f"evidence and compare it with the memo on chain.</p>")


def render(c: dict, review: str | None, steps_done: int, audience: str = "full") -> str:
    o, B, p = c["outcome"], BUILDINGS[c["b"]], party(c)
    head = f"<!doctype html><html lang=en><head><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'><title>Plumbline · {e(c['id'])}</title><style>{STYLE}</style></head><body><main>"
    toolbar = '<div class="toolbar"><button onclick="print()">Save as PDF</button></div>'
    data_note = ("Buildings and measurements come from CoStar, Vexcel and Matterport. Parties, bills and history in this demo are sample data."
                 if B.get("real") else "All buildings, parties and numbers in this demo are sample data.")
    if audience == "tenant" and c.get("rent"):
        r = c["rent"]
        verified = f"${r['verified']:.2f}" if r["verified"] else "$0"
        found = "".join(f"<li><b>{e(x[0])}:</b> {e(x[4])}</li>" for x in c["cross"])
        return (head + toolbar + f"<div class=over>For tenants of {e(B['name'])} · {e(B['city'])}</div>"
                f"<h1>Your rent increase should be {verified} a month.</h1>"
                f"<p>Your landlord asked for <b>${r['claimed']:.2f}</b> a month per apartment for {e(c['title'].lower())}. "
                f"Plumbline checked the building itself.</p><h2>What we found</h2><ul>{found}</ul>"
                f"<div class=box><b>${(r['claimed'] - r['verified']) * r['months']:,.0f}</b> less over {r['months'] // 12} years, per apartment. "
                f"Status: {'the reviewer has recorded a decision' if review else 'waiting for the reviewer’s final decision'}.</div>"
                f"<h2>Proof</h2>{_aerial(B)}<p>Roof from above: {B['roof']:,} sq ft. Sources: building record (CoStar), aerial survey (Vexcel)"
                f"{', 3D scan (Matterport)' if any(a['svc'] == 'Matterport' for a in c['apis']) else ''}, past rent records.</p>"
                f"<p class=note>Case {e(c['id'])}. Plain-language summary, not legal advice. {e(data_note)}</p></main></body></html>")

    cross = "".join(f"<tr><td><b>{e(x[0])}</b></td><td>{e(x[1])}</td><td>{e(x[2])}</td><td>{e(x[3])}</td><td>{e(x[4])}</td></tr>" for x in c["cross"])
    lines = "".join(f"<tr class=\"{'bad' if l[3] == 'bad' else ''}\"><td>{e(l[0])}</td><td>{e(l[1])}</td><td><b>{e(l[2])}</b></td></tr>" for l in c["lines"])
    calls = "".join(f"<div class=call><b>{i + 1}. {e(a['title'])}</b> <span class=pill>{e(a['svc'])}</span> <span class=muted>{e(WHO.get(a['who'], a['who']))}</span>"
                    f"<div class=grid><div><div class=over>Request</div><pre>{e(a['req'])}</pre></div><div><div class=over>Response</div><pre>{e(a['resp'])}</pre></div></div></div>"
                    for i, a in enumerate(c["apis"]))
    log = "".join(f"<tr><td>{k + 1:02d}</td><td>{e(WHO[s[0]])}</td><td>{e(s[1])}</td><td>{e(s[2])}</td></tr>" for k, s in enumerate(c["steps"][:steps_done]))
    formula = f"<div class=box style='font-family:ui-monospace,Menlo,monospace;font-size:13px'>{e(c['roof_formula'])}</div>" if c.get("roof_formula") else ""
    return (head + toolbar +
            f"<div class=over>{e(PERSONAS[c['persona']]['label'])} · Evidence report · {e(c['id'])}</div><h1>{e(c['title'])}</h1>"
            f"<div class=muted>{e(p['name'])} ({e(p['role'].lower())}) · {e(B['name'])}, {e(B['city'])} · CoStar {e(B['cs'])} · {money(c['amount'])}</div>"
            f"<h2>Decision <span class=pill>{e(STATUS.get(o['status'], o['status']))}</span> <span class=pill>{e(REVIEW.get(review, 'Waiting for a person'))}</span></h2>"
            f"<div class=big><div><span class=muted>{e(o['a'][0])}</span><b>{e(money(o['a'][1]))}</b></div><div><span class=muted>{e(o['b'][0])}</span><b>{e(money(o['b'][1]))}</b></div></div>"
            f"<p>{e(o['reason'])}</p>{formula}"
            f"<h2>Two sources must agree</h2><table><tr><th>Claim</th><th>Source 1</th><th>Source 2</th><th>The paper</th><th>Verdict</th></tr>{cross}</table>"
            f"<h2>Line by line</h2><table><tr><th>Line</th><th>The paper says</th><th>The building says</th></tr>{lines}</table>"
            f"{'<h2>From above</h2>' + _aerial(B) if _aerial(B) else ''}"
            f"{_solana(c)}"
            f"<h2>Data calls</h2>{calls}"
            f"<h2>Audit log</h2><table><tr><th>#</th><th>Who</th><th>Step</th><th>Result</th></tr>{log}"
            f"{f'<tr><td>--</td><td>Person</td><td>Decision recorded</td><td>{e(REVIEW[review])}</td></tr>' if review else ''}</table>"
            f"<p class=note>Generated {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC by Plumbline. Money and rent math is plain code; a person approves every payment. {e(data_note)}</p>"
            "</main></body></html>")
