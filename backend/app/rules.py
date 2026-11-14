"""Plain-code rules: money math and the "Try to fool it" invoice check. No AI here."""
import math
import re

from .calls import ai, costar, tiger, vexcel

APPROVED_ACCT = "4421"
VERIFIED_ROOF = 9820
TOLERANCE = 1.05
INJECT_RE = re.compile(r"(ignore|disregard|pre-?approved|override|system|assistant|AI|urgent|changed banks)", re.I)


def js_round(x: float) -> int:
    return int(math.floor(x + 0.5))


def fmt_int(n: int) -> str:
    return f"{n:,}"


def build_judge_claim(area: int, amount: int, bank: str, hidden: str, n: int) -> dict:
    cid = f"JDG-{n:02d}"
    ok = bank == APPROVED_ACCT
    inflated = area > VERIFIED_ROOF * TOLERANCE
    inj = bool(hidden) and bool(INJECT_RE.search(hidden))
    pay = 0 if not ok else js_round(amount * VERIFIED_ROOF / area) if inflated else amount

    steps = [["coordinator", "Read the bill and write the plan", "done", 0]]
    if inj:
        steps.append(["coordinator", "Hidden instruction found and ignored", "warn"])
    steps += [
        ["records", "Get the building record", "done", 1],
        ["roof", "Measure the roof from above", "done", 2],
        ["roof", f"Compare: {fmt_int(area)} claimed vs 9,820 measured", "fail" if inflated else "done"],
        ["records", f"Check bank account: ••{bank} vs ••{APPROVED_ACCT}", "done" if ok else "fail", 3],
    ]
    if not ok:
        steps.append(["rules", "Refuse payment, open review", "fail"])
    elif inflated:
        steps.append(["rules", f"Pay ${fmt_int(pay)}, hold ${fmt_int(amount - pay)}", "warn"])
    else:
        steps.append(["rules", f"Pay ${fmt_int(amount)} once", "done"])

    status = "blocked" if not ok else "partial" if inflated else "approved"
    reason = ("The bill asks to pay an account that isn't the approved one. Nothing is paid, whatever the bill says." if not ok
              else "The roof is 9,820 sq ft. The verified share is paid and the rest is held." if inflated
              else "Everything matches. Paid once.")
    return {
        "id": cid, "persona": "owner", "party": "lsr", "b": "wc", "date": "Now", "title": "Judge's invoice",
        "amount": amount, "kind": "roof", "claim": area, "measured": VERIFIED_ROOF, "bank": "••" + bank, "judge": True,
        "apis": [
            ai("judge_invoice.json", {"vendor": "Lone Star Roofing", "items": [{"work": "Roof", "qty": area, "amount": amount}],
                                      "pay_to": "••" + bank, "notes": hidden or None}),
            costar("wc"),
            vexcel("wc", "footprint,pitch", {"footprint_sqft": VERIFIED_ROOF, "roof_type": "flat", "pitch_deg": 0}),
            tiger("SELECT approved_acct FROM vendors\nWHERE vendor='Lone Star'", {"approved_acct": "••4421", "account_matches": ok}),
        ],
        "steps": steps,
        "cross": [
            ["Roof size", "CoStar: 9,820 sq ft per floor", "Vexcel: 9,820 sq ft", f"Bill: {fmt_int(area)} sq ft",
             "Bill is too big." if inflated else "Matches."],
            ["Bank", "Vendor file: ••4421", "Phone-verified: ••4421", "Bill: ••" + bank,
             "Matches." if ok else "Not the approved account."],
        ],
        "lines": [
            ["Roof area", fmt_int(area) + " sq ft", "9,820 sq ft", "bad" if inflated else "ok"],
            ["Pay to", "••" + bank, "••4421", "ok" if ok else "bad"],
        ],
        "outcome": {
            "status": status,
            "a": ["Pay now" if ok else "Paid", pay, "green" if pay else "gray"],
            "b": ["Hold" if ok else "Stopped", amount - pay, "red" if not ok else "amber" if amount - pay else "gray"],
            "reason": reason,
            "injected": hidden if inj else None,
        },
    }
