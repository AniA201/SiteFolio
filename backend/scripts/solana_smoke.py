"""Live devnet check of the full Solana flow, with a separate key standing in for the approver's Phantom wallet.

Run from backend/:  .venv/bin/python -m scripts.solana_smoke
Free: devnet only, test SOL and a test token. Prints each transaction's Explorer link.
"""
import base64
import copy

from solders.keypair import Keypair
from solders.pubkey import Pubkey
from solders.transaction import Transaction

from app import solana_ledger as L
from app.fixtures import CLAIMS


def wallet_signs(prepared: dict, wallet: Keypair) -> bytes:
    """What Phantom does: take the server-built transaction (fee payer already signed) and add the approver's signature."""
    tx = Transaction.from_bytes(base64.b64decode(prepared["tx"]))
    expected = bytes(tx.message)
    tx.partial_sign([wallet], tx.message.recent_blockhash)
    raw = bytes(tx)
    L.check_signed(raw, expected)
    return raw


def main():
    s = L.ensure_setup()
    print("app wallet", L.app_wallet().pubkey(), f"{L.sol_balance():.4f} SOL", "· mint", s["mint"])
    wallet = Keypair()  # stands in for Phantom; it never needs SOL
    c = copy.deepcopy(next(x for x in CLAIMS if x["id"] == "DRW-0412"))
    c["evidence_files"] = {"/evidence/DRW-0412/05_check_floor_plans.json": '{"verified_finished_count": 10, "listed_count": 13}'}

    prep = L.prepare(c, "ok", str(wallet.pubkey()))
    assert "tx" in prep, "a wallet address must get a transaction to sign, not a server-signed one"
    sig = L.submit(wallet_signs(prep, wallet))
    info = dict(prep["info"])
    c["sealed_files"] = info.pop("sealed")
    c["solana"] = {"state": "recorded", "signature": sig, **info}
    print("approve (wallet signed):", L.explorer("tx", sig))

    c["evidence_files"]["/evidence/DRW-0412/findings.md"] = "written by the agent after it resumed"
    assert L.verify(c)["ok"], "notes written after approval must not break Verify"
    c["sealed_files"]["/evidence/DRW-0412/05_check_floor_plans.json"] = '{"verified_finished_count": 13, "listed_count": 13}'
    assert not L.verify(c)["ok"], "an edited evidence file must fail Verify"
    c["sealed_files"]["/evidence/DRW-0412/05_check_floor_plans.json"] = '{"verified_finished_count": 10, "listed_count": 13}'
    assert L.verify(c)["ok"]
    print("verify: green, red after an edit, green after undo")

    try:
        L.prepare(c, "ok", None, "release")
        raise AssertionError("a different signer must not be able to release")
    except L.LedgerError as e:
        print("release by another key refused:", e)
    rel = L.prepare(c, "ok", str(wallet.pubkey()), "release")
    rsig = L.submit(wallet_signs(rel, wallet))
    print("release (wallet + Plumbline signed):", L.explorer("tx", rsig))

    cl, mint = L._client(), Pubkey.from_string(s["mint"])
    payee = L._ata(Pubkey.from_string(c["solana"]["payee"]), mint)
    print("payee holds", L._balance_cents(cl, payee) / 100, "PUSD (includes earlier demo runs for this party)")
    print("SOL left", f"{L.sol_balance():.4f}")
    print("OK")


if __name__ == "__main__":
    main()
