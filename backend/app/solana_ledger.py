"""Solana devnet ledger: every decision a person approves becomes a public receipt, and money moves with its proof.

One transaction, signed by the person approving (their Phantom wallet, or a demo lender key when no wallet is
connected), does three things at once or not at all:
  1. pays the verified amount to the contractor or builder,
  2. moves the unproven amount into a holding account that needs TWO signatures to release
     (the lender AND Plumbline's verifier, an SPL Token multisig), so neither can take it alone,
  3. records a memo: claim id, decision, amounts and a SHA-256 fingerprint of the evidence.
The agent never holds a key. Money is "Plumbline USD", a test token we mint on devnet; nothing here has real value.

Devnet only, on purpose: the cluster URL is fixed and the module refuses any other.
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
import threading
import time
from pathlib import Path

from solana.rpc.api import Client
from solana.rpc.commitment import Confirmed
from solana.rpc.types import TxOpts
from solders.hash import Hash
from solders.keypair import Keypair
from solders.message import Message
from solders.pubkey import Pubkey
from solders.signature import Signature
from solders.system_program import CreateAccountParams, create_account
from solders.transaction import Transaction
from spl.memo.constants import MEMO_PROGRAM_ID
from spl.memo.instructions import MemoParams, create_memo
from spl.token import instructions as T
from spl.token.constants import TOKEN_PROGRAM_ID

RPC = "https://api.devnet.solana.com"
CLUSTER = "devnet"
DECIMALS = 2                      # Plumbline USD has cents
MINT_SIZE, MULTISIG_SIZE = 82, 355
FUND_LENDER = 5_000_000           # test dollars minted to a lender wallet when it runs low
DIR = Path(__file__).resolve().parent / "data" / "solana"
WALLET = DIR / "app_wallet.json"  # secret key; gitignored
STATE = DIR / "ledger.json"       # mint, demo lender, payees, vaults; gitignored

_lock = threading.RLock()


class LedgerError(RuntimeError):
    def __init__(self, message: str, signature: str | None = None):
        super().__init__(message)
        self.signature = signature  # a transaction that was sent but not confirmed in time; it may still land


def landed(signature: str) -> bool:
    """Did an earlier, unconfirmed transaction land after all? Checked before any retry, so money never moves twice."""
    st = _retry(lambda: _client().get_signature_statuses([Signature.from_string(signature)], search_transaction_history=True).value[0])
    return st is not None and st.err is None


def explorer(kind: str, value: str) -> str:
    return f"https://explorer.solana.com/{kind}/{value}?cluster={CLUSTER}"


# ---------- keys and saved state ----------
def _kp(secret: list[int]) -> Keypair:
    return Keypair.from_bytes(bytes(secret))


def _secret(kp: Keypair) -> list[int]:
    return list(bytes(kp))


def app_wallet() -> Keypair:
    """Fee payer, mint authority and Plumbline's verifier signature. Created once and kept on this laptop."""
    DIR.mkdir(parents=True, exist_ok=True)
    if not WALLET.exists():
        WALLET.write_text(json.dumps(_secret(Keypair())))
    return _kp(json.loads(WALLET.read_text()))


def _state() -> dict:
    return json.loads(STATE.read_text()) if STATE.exists() else {}


def _save(s: dict) -> None:
    DIR.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(s, indent=1))


def _client() -> Client:
    return Client(RPC, timeout=30)


# ---------- evidence fingerprint ----------
def evidence_payload(claim: dict, files: list[str] | None = None) -> dict:
    """What the decision rests on: the checked lines, the data sources, the outcome and the agent's evidence files."""
    # Files are sealed at approval (the agent keeps writing notes after it resumes); the sealed copy is what was signed.
    ev = claim.get("sealed_files") or claim.get("evidence_files") or {}
    names = sorted(ev) if files is None else files
    o = claim["outcome"]
    return {"claim": claim["id"], "lines": claim.get("lines"), "apis": claim.get("apis"),
            "outcome": {"status": o["status"], "a": o["a"], "b": o["b"], "reason": o.get("reason")},
            "files": {n: ev.get(n) for n in names}}


def fingerprint(claim: dict, files: list[str] | None = None) -> str:
    raw = json.dumps(evidence_payload(claim, files), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode()).hexdigest()


# ---------- what an approval moves ----------
MONEY_PERSONAS = {"owner", "lender"}


def plan(claim: dict, decision: str) -> dict:
    """Pay and hold amounts (in dollars) for an approval. Rejections, blocks and rent decisions move no money."""
    o = claim["outcome"]
    moves = (decision in ("ok", "sent") and claim.get("persona") in MONEY_PERSONAS
             and o["status"] in ("approved", "partial") and isinstance(o["a"][1], (int, float)))
    pay = float(o["a"][1]) if moves else 0.0
    hold = float(o["b"][1]) if moves and isinstance(o["b"][1], (int, float)) else 0.0
    verdict = {"ok": "approved", "sent": "approved", "rejected": "rejected"}.get(decision, decision)
    return {"pay": pay, "hold": hold, "verdict": verdict, "status": o["status"], "moves": moves}


def memo_text(claim: dict, p: dict, digest: str, kind: str = "decision") -> str:
    return (f"plumbline:v1 {kind} {claim['id']} {p['verdict']}/{p['status']} "
            f"pay={p['pay']:.2f} hold={p['hold']:.2f} PUSD evidence=sha256:{digest}")


def parse_memo(text: str) -> dict:
    m = re.search(r"plumbline:v1 (\w+) (\S+) (\S+) pay=([\d.]+) hold=([\d.]+) PUSD evidence=sha256:([0-9a-f]{64})", text or "")
    if not m:
        return {}
    return {"kind": m.group(1), "claim": m.group(2), "verdict": m.group(3), "pay": float(m.group(4)),
            "hold": float(m.group(5)), "sha256": m.group(6)}


# ---------- devnet plumbing ----------
def _cents(dollars: float) -> int:
    return int(round(dollars * 10 ** DECIMALS))


def _blockhash(c: Client) -> Hash:
    return _retry(lambda: c.get_latest_blockhash(commitment=Confirmed).value.blockhash)


def _send(c: Client, ixs: list, signers: list[Keypair]) -> str:
    bh = _blockhash(c)
    tx = Transaction(signers, Message.new_with_blockhash(ixs, signers[0].pubkey(), bh), bh)
    return _send_raw(c, bytes(tx))


def _retry(fn, tries: int = 6):
    """The free public devnet server rate-limits (HTTP 429); back off and try again."""
    for i in range(tries):
        try:
            return fn()
        except Exception as e:
            if i == tries - 1 or "429" not in repr(getattr(e, "__cause__", None) or e) + str(e):
                raise
            time.sleep(1.5 * (i + 1))


def _send_raw(c: Client, raw: bytes) -> str:
    sig = _retry(lambda: c.send_raw_transaction(raw, opts=TxOpts(skip_preflight=False, preflight_commitment=Confirmed)).value)
    deadline = time.time() + 60
    while time.time() < deadline:
        time.sleep(1.5)
        try:
            st = c.get_signature_statuses([sig]).value[0]
        except Exception:
            time.sleep(2)  # rate-limited; keep waiting
            continue
        if st is not None:
            if st.err is not None:
                raise LedgerError(f"The transaction failed on chain: {st.err}")
            if st.confirmation_status is not None and str(st.confirmation_status) != "TransactionConfirmationStatus.Processed":
                return str(sig)
    raise LedgerError(f"Devnet didn't confirm in time; check {explorer('tx', str(sig))}", signature=str(sig))


def _ata(owner: Pubkey, mint: Pubkey) -> Pubkey:
    return T.get_associated_token_address(owner, mint)


def _balance_cents(c: Client, account: Pubkey) -> int:
    try:
        return int(c.get_token_account_balance(account, commitment=Confirmed).value.amount)
    except Exception:
        return 0


def sol_balance() -> float:
    return _client().get_balance(app_wallet().pubkey(), commitment=Confirmed).value / 1e9


def ensure_setup() -> dict:
    """Create the Plumbline USD mint and the demo lender once. Needs devnet SOL in the app wallet."""
    with _lock:
        s, app, c = _state(), app_wallet(), _client()
        if c.get_balance(app.pubkey(), commitment=Confirmed).value < 20_000_000:
            raise LedgerError(f"The app wallet needs free devnet SOL. Request it at https://faucet.solana.com for {app.pubkey()}.")
        if not s.get("mint"):
            mint = Keypair()
            rent = c.get_minimum_balance_for_rent_exemption(MINT_SIZE).value
            _send(c, [create_account(CreateAccountParams(from_pubkey=app.pubkey(), to_pubkey=mint.pubkey(), lamports=rent,
                                                         space=MINT_SIZE, owner=TOKEN_PROGRAM_ID)),
                      T.initialize_mint(T.InitializeMintParams(decimals=DECIMALS, program_id=TOKEN_PROGRAM_ID, mint=mint.pubkey(),
                                                               mint_authority=app.pubkey(), freeze_authority=None))],
                  [app, mint])
            s["mint"] = str(mint.pubkey())
        if not s.get("demo_lender"):
            s["demo_lender"] = _secret(Keypair())
        s.setdefault("payees", {})
        s.setdefault("vaults", {})
        _save(s)
        return s


def _payee(s: dict, claim: dict) -> Pubkey:
    """Each contractor or builder gets a devnet wallet address of its own (it only receives)."""
    key = claim.get("party") or claim["id"]
    if key not in s["payees"]:
        s["payees"][key] = _secret(Keypair())
        _save(s)
    return _kp(s["payees"][key]).pubkey()


def _vault(c: Client, s: dict, lender: Pubkey) -> tuple[Pubkey, Pubkey]:
    """Holding account for a lender: a token account owned by a 2-of-2 multisig (lender + Plumbline verifier)."""
    app, mint = app_wallet(), Pubkey.from_string(s["mint"])
    v = s["vaults"].get(str(lender))
    if not v:
        ms = Keypair()
        rent = c.get_minimum_balance_for_rent_exemption(MULTISIG_SIZE).value
        _send(c, [create_account(CreateAccountParams(from_pubkey=app.pubkey(), to_pubkey=ms.pubkey(), lamports=rent,
                                                     space=MULTISIG_SIZE, owner=TOKEN_PROGRAM_ID)),
                  T.initialize_multisig(T.InitializeMultisigParams(program_id=TOKEN_PROGRAM_ID, multisig=ms.pubkey(), m=2,
                                                                   signers=[lender, app.pubkey()])),
                  T.create_idempotent_associated_token_account(app.pubkey(), ms.pubkey(), mint)],
              [app, ms])
        v = s["vaults"][str(lender)] = str(ms.pubkey())
        _save(s)
    ms = Pubkey.from_string(v)
    return ms, _ata(ms, mint)


def _fund(c: Client, s: dict, lender: Pubkey, need_cents: int) -> None:
    """Mint test dollars to the lender's account when it can't cover a payment."""
    app, mint = app_wallet(), Pubkey.from_string(s["mint"])
    acct = _ata(lender, mint)
    have = _balance_cents(c, acct)
    if have >= need_cents:
        return
    amount = max(_cents(FUND_LENDER), need_cents - have)
    _send(c, [T.create_idempotent_associated_token_account(app.pubkey(), lender, mint),
              T.mint_to_checked(T.MintToCheckedParams(program_id=TOKEN_PROGRAM_ID, mint=mint, dest=acct,
                                                      mint_authority=app.pubkey(), amount=amount, decimals=DECIMALS, signers=[]))],
          [app])


def _transfer(src: Pubkey, dest: Pubkey, owner: Pubkey, mint: Pubkey, cents: int, multisig: list[Pubkey] | None = None):
    return T.transfer_checked(T.TransferCheckedParams(program_id=TOKEN_PROGRAM_ID, source=src, mint=mint, dest=dest, owner=owner,
                                                      amount=cents, decimals=DECIMALS, signers=multisig or []))


def _memo(text: str, signer: Pubkey):
    return create_memo(MemoParams(program_id=MEMO_PROGRAM_ID, signer=signer, message=text.encode()))


# ---------- the two transactions ----------
def _decision_ixs(c: Client, s: dict, claim: dict, decision: str, lender: Pubkey) -> tuple[list, dict]:
    app, mint = app_wallet(), Pubkey.from_string(s["mint"])
    p = plan(claim, decision)
    sealed = dict(claim.get("sealed_files") or claim.get("evidence_files") or {})
    files = sorted(sealed)
    digest = fingerprint({**claim, "sealed_files": sealed}, files)
    ixs = []
    info = {**p, "sha256": digest, "files": files, "lender": str(lender), "sealed": sealed}
    if p["moves"]:
        payee = _payee(s, claim)
        _, vault = _vault(c, s, lender)
        _fund(c, s, lender, _cents(p["pay"] + p["hold"]))
        src = _ata(lender, mint)
        ixs.append(T.create_idempotent_associated_token_account(app.pubkey(), payee, mint))
        if p["pay"]:
            ixs.append(_transfer(src, _ata(payee, mint), lender, mint, _cents(p["pay"])))
        if p["hold"]:
            ixs.append(_transfer(src, vault, lender, mint, _cents(p["hold"])))
        info.update(payee=str(payee), vault=str(vault))
    # Plumbline's verifier signs the memo: the evidence was checked; the lender's signature moves the money.
    ixs.append(_memo(memo_text(claim, p, digest), app.pubkey()))
    if not p["moves"]:
        ixs.append(_memo(f"plumbline:v1 signed-by {lender}", lender))  # the person still signs the record
    return ixs, info


def _release_ixs(c: Client, s: dict, claim: dict, receipt: dict, lender: Pubkey) -> tuple[list, dict]:
    app, mint = app_wallet(), Pubkey.from_string(s["mint"])
    ms, vault = _vault(c, s, lender)
    payee = Pubkey.from_string(receipt["payee"])
    p = {"pay": receipt["hold"], "hold": 0.0, "verdict": "released", "status": claim["outcome"]["status"]}
    proof = {"follow_up": "New scan verified the remaining work", "decision_tx": receipt["signature"], "at": time.strftime("%Y-%m-%d")}
    digest = hashlib.sha256(json.dumps({"claim": claim["id"], "decision": receipt["sha256"], **proof}, sort_keys=True).encode()).hexdigest()
    ixs = [_transfer(vault, _ata(payee, mint), ms, mint, _cents(receipt["hold"]), multisig=[lender, app.pubkey()]),
           _memo(memo_text(claim, p, digest, kind="release"), app.pubkey())]
    return ixs, {"amount": receipt["hold"], "sha256": digest, "proof": proof}


def _build(c: Client, ixs: list, lender: Pubkey) -> tuple[Transaction, Hash]:
    """App pays the fee and signs as verifier; the lender's signature is still needed."""
    app = app_wallet()
    bh = _blockhash(c)
    tx = Transaction.new_unsigned(Message.new_with_blockhash(ixs, app.pubkey(), bh))
    tx.partial_sign([app], bh)
    return tx, bh


def _sign_demo(tx: Transaction, bh: Hash, lender: Keypair) -> bytes:
    tx.partial_sign([lender], bh)
    return bytes(tx)


def demo_lender() -> Keypair:
    return _kp(ensure_setup()["demo_lender"])


def prepare(claim: dict, decision: str, lender: str | None, action: str = "decision") -> dict:
    """Build the transaction for a person to sign. With no wallet address, the demo lender key is used."""
    with _lock:
        s, c = ensure_setup(), _client()
        lk = None if lender else _kp(s["demo_lender"])
        lpub = Pubkey.from_string(lender) if lender else lk.pubkey()
        if action == "release":
            receipt = (claim.get("solana") or {})
            if not receipt.get("hold") or receipt.get("released"):
                raise LedgerError("Nothing is being held for this claim.")
            if receipt.get("lender") != str(lpub):
                raise LedgerError("Only the lender who approved this claim can co-sign its release.")
            ixs, info = _release_ixs(c, s, claim, receipt, lpub)
        else:
            ixs, info = _decision_ixs(c, s, claim, decision, lpub)
        tx, bh = _build(c, ixs, lpub)
        if lk:
            return {"raw": _sign_demo(tx, bh, lk), "info": info, "signer": "demo lender key"}
        return {"tx": base64.b64encode(bytes(tx)).decode(), "info": info, "signer": "Phantom"}


def submit(raw: bytes) -> str:
    return _send_raw(_client(), raw)


def check_signed(raw: bytes, expected_message: bytes | None = None) -> None:
    """Refuse a wallet-returned transaction that isn't the one we built or isn't fully signed."""
    tx = Transaction.from_bytes(raw)
    if expected_message is not None and bytes(tx.message) != expected_message:
        raise LedgerError("The signed transaction differs from the one Plumbline prepared.")
    if any(sig == Signature.default() for sig in tx.signatures):
        raise LedgerError("The transaction is missing a signature.")


def read_memo(signature: str) -> dict:
    """Fetch a transaction from devnet and pull out Plumbline's memo."""
    r = _client().get_transaction(Signature.from_string(signature), encoding="json", commitment=Confirmed,
                                  max_supported_transaction_version=0).value
    if r is None:
        raise LedgerError("Transaction not found on devnet yet.")
    meta = r.transaction.meta
    if meta.err is not None:
        raise LedgerError(f"The transaction failed on chain: {meta.err}")
    for line in meta.log_messages or []:
        found = parse_memo(line)
        if found:
            return {**found, "slot": r.slot, "block_time": r.block_time}
    raise LedgerError("No Plumbline memo in that transaction.")


def verify(claim: dict) -> dict:
    """Recompute the evidence fingerprint and compare it with the one recorded on Solana."""
    receipt = claim.get("solana") or {}
    if not receipt.get("signature"):
        return {"ok": False, "reason": "Not recorded on Solana yet."}
    onchain = read_memo(receipt["signature"])
    now = fingerprint(claim, receipt.get("files"))
    ok = onchain["sha256"] == now and onchain["claim"] == claim["id"]
    return {"ok": ok, "onchain_sha256": onchain["sha256"], "current_sha256": now, "slot": onchain["slot"],
            "reason": "Evidence matches the fingerprint recorded on Solana." if ok
            else "Evidence changed after approval: it no longer matches the fingerprint recorded on Solana."}


def status() -> dict:
    s, app = _state(), app_wallet()
    out = {"cluster": CLUSTER, "app_wallet": str(app.pubkey()), "mint": s.get("mint"),
           "demo_lender": str(_kp(s["demo_lender"]).pubkey()) if s.get("demo_lender") else None,
           "explorer_wallet": explorer("address", str(app.pubkey()))}
    try:
        out["sol"] = round(sol_balance(), 4)
        out["ready"] = out["sol"] >= 0.02
    except Exception as e:
        out.update(sol=None, ready=False, error=f"{type(e).__name__}")
    return out
