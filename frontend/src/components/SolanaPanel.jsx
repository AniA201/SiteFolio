import { useState } from "react";
import { fmt } from "../lib";
import { signOnSolana, tamperEvidence, verifyOnSolana } from "../solana";

const short = s => s ? `${s.slice(0, 6)}…${s.slice(-6)}` : "";

// The claim's Solana receipt: what moved, who signed, the evidence fingerprint, Verify and releasing held money.
export default function SolanaPanel({ c, wallet, compact = false }) {
  const sol = c.solana;
  const [check, setCheck] = useState(null);
  const [busy, setBusy] = useState("");
  const [err, setErr] = useState("");
  const run = async (label, fn) => {
    setBusy(label); setErr("");
    try { await fn(); } catch (e) { setErr(e.message || String(e)); } finally { setBusy(""); }
  };
  const verify = () => run("verify", async () => setCheck(await verifyOnSolana(c.id)));
  const tamper = () => run("tamper", async () => { await tamperEvidence(c.id); setCheck(await verifyOnSolana(c.id)); });
  const release = () => run("release", () => signOnSolana(c.id, { action: "release", wallet: sol.lender === wallet ? wallet : null }));
  const retry = () => run("retry", () => signOnSolana(c.id, { decision: "ok", wallet: null }));

  if (!sol) return compact ? null : (
    <div className="sol-panel"><div className="over">Solana receipt</div>
      <p className="muted small" style={{ margin: "6px 0 0" }}>Approving this claim in Review records it on Solana devnet: the verified amount is paid, the rest is held, and the evidence fingerprint is public.</p></div>
  );
  return (
    <div className="sol-panel">
      <div className="row between wrap" style={{ gap: 8 }}>
        <div className="over">Solana receipt · devnet</div>
        {sol.state === "recorded" && <a className="tag t-paid" href={sol.explorer} target="_blank" rel="noopener">Recorded on Solana ↗</a>}
        {sol.state === "pending" && <span className="tag t-running"><i />Recording on Solana…</span>}
        {sol.state === "failed" && <span className="tag t-blocked">Not recorded</span>}
      </div>
      {sol.state === "failed" && <>
        <p className="small" style={{ margin: "8px 0" }}>{sol.error}</p>
        <button className="btn white sm" disabled={!!busy} onClick={retry}>{busy === "retry" ? "Trying…" : "Try again"}</button>
      </>}
      {sol.state === "recorded" && <>
        <div className="sol-grid">
          {sol.moves ? <>
            <div><span className="muted small">Paid to {c.persona === "lender" ? "builder" : "contractor"}</span><b className="num">{fmt(sol.pay)}</b></div>
            <div><span className="muted small">Held (needs lender + SiteFolio)</span><b className="num">{sol.released ? "Released" : fmt(sol.hold)}</b></div>
          </> : <div><span className="muted small">Decision</span><b>{sol.verdict} · no money moved</b></div>}
          <div><span className="muted small">Signed by</span><b>{sol.signer}</b></div>
          <div><span className="muted small">Evidence fingerprint</span><b className="mono" title={sol.sha256}>{short(sol.sha256)}</b></div>
        </div>
        {!compact && <div className="row wrap" style={{ marginTop: 12, gap: 8 }}>
          <button className="btn black sm" disabled={!!busy} onClick={verify}>{busy === "verify" ? "Checking the chain…" : "Verify evidence"}</button>
          <button className="btn white sm" disabled={!!busy} onClick={tamper}>{c.untampered_lines ? "Undo the edit" : "Edit the evidence (demo)"}</button>
          {sol.moves && sol.hold > 0 && !sol.released &&
            <button className="btn amber sm" disabled={!!busy} onClick={release}>{busy === "release" ? "Waiting for signatures…" : `New scan verified: release ${fmt(sol.hold)}`}</button>}
          {sol.released && <a className="text-link small" href={sol.release_explorer} target="_blank" rel="noopener">Release transaction ↗</a>}
        </div>}
        {check && <div className={"sol-check " + (check.ok ? "ok" : "bad")}>
          <b>{check.ok ? "✓ Matches Solana" : "✕ Doesn't match Solana"}</b> {check.reason}
          {!check.ok && check.current_sha256 && <div className="mono small">on chain {short(check.onchain_sha256)} · now {short(check.current_sha256)}</div>}
        </div>}
        {sol.release_error && <p className="small" style={{ color: "var(--red)" }}>{sol.release_error}</p>}
      </>}
      {err && <p className="small" style={{ color: "var(--red)", marginTop: 8 }}>{err}</p>}
    </div>
  );
}
