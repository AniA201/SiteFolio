"""Plain-code rules for the "Try to fool it" invoice check. No AI here; the math lives in money.py."""
import re

from .calls import ai, costar, tiger, vexcel
from .fixtures import BUILDINGS, CLAIMS, META
from .money import check_roof, pay_verified_share, payment_checks

FOOL = META.get("fool", {"building": "wc", "approved_acct": "4421"})
APPROVED_ACCT = FOOL["approved_acct"]
TARGET = BUILDINGS[FOOL["building"]]
VERIFIED_ROOF = round(TARGET["roof"])
PLATE = round(TARGET["size"] / (TARGET["floors"] or 1))


def _data_calls() -> list[dict]:
    """The building record and aerial calls: the real recorded ones when real data is loaded."""
    roof_claim = next((c for c in CLAIMS if c["id"] == "CLM-2207"), None)
    if TARGET.get("real") and roof_claim:
        return [roof_claim["apis"][1], roof_claim["apis"][2]]
    return [costar(FOOL["building"]), vexcel(FOOL["building"], "footprint,pitch", {"footprint_sqft": VERIFIED_ROOF, "roof_type": "flat", "pitch_deg": 0})]
INJECT_RE = re.compile(r"(ignore|disregard|pre-?approved|override|system|assistant|AI|urgent|changed banks)", re.I)


def fmt_int(n: int) -> str:
    return f"{n:,}"


def build_judge_claim(area: int, amount: int, bank: str, hidden: str, n: int) -> dict:
    cid = f"JDG-{n:02d}"
    ok = not payment_checks("••" + bank, "••" + APPROVED_ACCT, already_paid=False).blocked
    roof = check_roof(VERIFIED_ROOF, 0, area)
    inflated = roof.inflated
    inj = bool(hidden) and bool(INJECT_RE.search(hidden))
    pay = 0 if not ok else pay_verified_share(amount, area, roof.surface, roof.allowed).pay

    steps = [["coordinator", "Read the bill and write the plan", "done", 0]]
    if inj:
        steps.append(["coordinator", "Hidden instruction found and ignored", "warn"])
    steps += [
        ["records", "Get the building record", "done", 1],
        ["roof", "Measure the roof from above", "done", 2],
        ["roof", f"Compare: {fmt_int(area)} claimed vs {fmt_int(VERIFIED_ROOF)} measured", "fail" if inflated else "done"],
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
              else f"The roof is {fmt_int(VERIFIED_ROOF)} sq ft. The verified share is paid and the rest is held." if inflated
              else "Everything matches. Paid once.")
    return {
        "id": cid, "persona": "owner", "party": "lsr", "b": FOOL["building"], "date": "Now", "title": "Judge's invoice",
        "amount": amount, "kind": "roof", "claim": area, "measured": VERIFIED_ROOF, "bank": "••" + bank, "judge": True,
        "apis": [
            ai("judge_invoice.json", {"vendor": "Lone Star Roofing", "items": [{"work": "Roof", "qty": area, "amount": amount}],
                                      "pay_to": "••" + bank, "notes": hidden or None}),
            *_data_calls(),
            tiger("SELECT approved_acct FROM vendors\nWHERE vendor='Lone Star'", {"approved_acct": "••4421", "account_matches": ok}),
        ],
        "steps": steps,
        "cross": [
            ["Roof size", f"CoStar: {fmt_int(PLATE)} sq ft per floor", f"Vexcel: {fmt_int(VERIFIED_ROOF)} sq ft", f"Bill: {fmt_int(area)} sq ft",
             "Bill is too big." if inflated else "Matches."],
            ["Bank", "Vendor file: ••4421", "Phone-verified: ••4421", "Bill: ••" + bank,
             "Matches." if ok else "Not the approved account."],
        ],
        "lines": [
            ["Roof area", fmt_int(area) + " sq ft", f"{fmt_int(VERIFIED_ROOF)} sq ft", "bad" if inflated else "ok"],
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
