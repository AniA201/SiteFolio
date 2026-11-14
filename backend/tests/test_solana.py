"""Solana ledger logic that runs without devnet: amounts, memo, evidence fingerprint and signed-transaction checks."""
import copy

import pytest
from solders.hash import Hash
from solders.keypair import Keypair
from solders.message import Message
from solders.transaction import Transaction
from spl.memo.constants import MEMO_PROGRAM_ID
from spl.memo.instructions import MemoParams, create_memo

from app import solana_ledger as L
from app.fixtures import CLAIMS


def claim(cid):
    return copy.deepcopy(next(c for c in CLAIMS if c["id"] == cid))


def test_approval_pays_the_verified_share_and_holds_the_rest():
    c = claim("DRW-0412")
    p = L.plan(c, "ok")
    assert p["moves"] and p["pay"] == c["outcome"]["a"][1] and p["hold"] == c["outcome"]["b"][1] and p["hold"] > 0


def test_blocks_rejections_and_rent_move_no_money():
    assert not L.plan(claim("CLM-2223"), "ok")["moves"]          # bank account swap: confirm the block
    assert not L.plan(claim("CLM-2207"), "rejected")["moves"]
    assert not L.plan(claim("RSO-3104"), "ok")["moves"]          # rent decisions are receipts only


def test_memo_round_trips_and_fits_in_a_transaction():
    c = claim("CLM-2207")
    p, digest = L.plan(c, "ok"), L.fingerprint(c)
    text = L.memo_text(c, p, digest)
    assert len(text.encode()) < 300
    got = L.parse_memo(f'Program log: Memo (len {len(text)}): "{text}"')
    assert got["claim"] == "CLM-2207" and got["sha256"] == digest and got["pay"] == c["outcome"]["a"][1]


def test_fingerprint_changes_when_evidence_changes():
    c = claim("CLM-2207")
    before = L.fingerprint(c)
    assert L.fingerprint(copy.deepcopy(c)) == before
    c["lines"][0][2] = "52,000 sq ft"
    assert L.fingerprint(c) != before


def test_fingerprint_only_covers_the_files_signed_at_approval():
    c = claim("CLM-2207")
    c["evidence_files"] = {"/evidence/CLM-2207/plan.md": "plan"}
    files = sorted(c["evidence_files"])
    signed = L.fingerprint(c, files)
    c["evidence_files"]["/evidence/CLM-2207/decision.md"] = "written after the person approved"
    assert L.fingerprint(c, files) == signed
    c["evidence_files"]["/evidence/CLM-2207/plan.md"] = "edited"
    assert L.fingerprint(c, files) != signed


def _tx(signers, text="plumbline"):
    bh = Hash.default()
    ix = create_memo(MemoParams(program_id=MEMO_PROGRAM_ID, signer=signers[0].pubkey(), message=text.encode()))
    return Transaction.new_unsigned(Message.new_with_blockhash([ix], signers[0].pubkey(), bh)), bh


def test_signed_transaction_must_match_what_we_built():
    a = Keypair()
    tx, bh = _tx([a])
    expected = bytes(tx.message)
    with pytest.raises(L.LedgerError):
        L.check_signed(bytes(tx), expected)        # unsigned
    tx.partial_sign([a], bh)
    L.check_signed(bytes(tx), expected)
    other, bh2 = _tx([a], "something else")
    other.partial_sign([a], bh2)
    with pytest.raises(L.LedgerError):
        L.check_signed(bytes(other), expected)     # a wallet can't swap in another transaction


def test_approving_without_solana_still_records_the_decision():
    from fastapi.testclient import TestClient

    from app.main import app
    with TestClient(app) as client:
        client.post("/api/reset")
        r = client.post("/api/claims/CLM-2207/decision", json={"action": "ok"})
        assert r.status_code == 200 and r.json()["review"]["CLM-2207"] == "ok"
        t = client.post("/api/solana/claims/CLM-2207/tamper").json()
        assert t["tampered"] is True
        assert client.post("/api/solana/claims/CLM-2207/tamper").json()["tampered"] is False


def test_sealed_evidence_ignores_notes_written_after_approval():
    c = claim("CLM-2207")
    c["evidence_files"] = {"/evidence/CLM-2207/plan.md": "plan"}
    c["sealed_files"] = dict(c["evidence_files"])
    signed = L.fingerprint(c, sorted(c["sealed_files"]))
    c["evidence_files"]["/evidence/CLM-2207/plan.md"] = "the agent rewrote its notes after resuming"
    assert L.fingerprint(c, sorted(c["sealed_files"])) == signed
    c["sealed_files"]["/evidence/CLM-2207/plan.md"] = "someone edited the sealed evidence"
    assert L.fingerprint(c, sorted(c["sealed_files"])) != signed


def test_report_and_decision_record_include_the_solana_receipt():
    from app.report import decision_record, render
    c = claim("DRW-0412")
    c["solana"] = {"state": "recorded", "signature": "abc", "explorer": "https://explorer.solana.com/tx/abc?cluster=devnet",
                   "signer": "Phantom", "pay": 1.0, "hold": 2.0, "moves": True, "sha256": "f" * 64}
    assert "Recorded on Solana" in render(c, "ok", len(c["steps"]))
    assert decision_record(c, "ok")["solana"]["signer"] == "Phantom"
