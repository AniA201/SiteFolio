import { BUILDINGS, META, partyOf } from "../data";
import { COL, FINAL, NEEDS, Tag, fmt, money, sumNum } from "../lib";
import EvidenceWalkthrough from "../components/EvidenceWalkthrough";

const FEATURED = {
  owner: ["CLM-2207", "wc"],
  reviewer: ["RSO-3104", "wca"],
  lender: ["DRW-0412", "ml"],
};

const HEADLINES = {
  owner: ["Verify the work.", "Then pay the bill."],
  reviewer: ["Check the work", "behind the rent."],
  lender: ["Verify progress.", "Then release funds."],
};

const LEDE = {
  owner: "Compare contractor invoices with property records, aerial surveys, and interior scans before approving payment.",
  reviewer: "Check the improvements behind a rent increase and show tenants how the amount was calculated.",
  lender: "Verify the progress behind a construction draw and see what work remains.",
};

function statTiles(persona, done, waiting, status) {
  if (persona === "owner") return [
    ["Held with proof", fmt(sumNum(done.filter(c => c.outcome.status === "partial"), "b")), "overbilling held back"],
    ["Fraud stopped", fmt(sumNum(done.filter(c => c.outcome.status === "blocked"), "b")), "fake bank changes"],
    ["Paid correctly", fmt(sumNum(done, "a")), done.length + " bills verified"],
    ["Waiting", waiting.length, "bills to check"],
  ];
  if (persona === "reviewer") return [
    ["Tenant savings", "$" + done.reduce((t, c) => t + (c.rent ? (c.rent.claimed - c.rent.verified) * c.rent.units : 0), 0).toFixed(0) + "/mo", "across all units"],
    ["Reduced or denied", done.filter(c => ["reduced", "denied"].includes(status[c.id])).length, "applications"],
    ["Checked", done.length, "applications"],
    ["Waiting", waiting.length, "to check"],
  ];
  return [
    ["Released", fmt(sumNum(done, "a")), "for verified work"],
    ["Held until done", fmt(sumNum(done, "b")), "unfinished work"],
    ["Checked", done.length, "loan requests"],
    ["Waiting", waiting.length, "to check"],
  ];
}

export default function Overview({ S, A }) {
  const { list, status, persona } = S;
  const story = META.stories?.[persona]?.[0];
  const [claimId, building] = story ? story.slice(2) : FEATURED[persona];
  const featured = list.find(claim => claim.id === claimId);
  const property = BUILDINGS[featured?.b || building];
  const lines = featured?.lines ?? [];
  const [comparison] = lines;
  const done = list.filter(c => FINAL.includes(status[c.id]));
  const waiting = list.filter(c => !status[c.id] || status[c.id] === "ready");
  const attention = done.filter(c => NEEDS.includes(status[c.id]) && !S.review[c.id]);
  const tiles = statTiles(persona, done, waiting, status);

  return (
    <div className="overview">
      <EvidenceWalkthrough headline={HEADLINES[persona]} lede={LEDE[persona]} property={property}
        featured={featured} waiting={waiting.length} running={S.running} onRun={A.runAll} />
      <div className="wrapx overview-ledger" id="workspace-summary" tabIndex={-1}>
      {comparison && (
        <section className="featured-check" aria-labelledby="featured-title">
          <div><p className="over">Featured case</p><h2 id="featured-title">{featured.title}</h2></div>
          <div><small>The paper says</small><strong>{comparison[1]}</strong></div>
          <div><small>The building says</small><strong>{comparison[2]}</strong></div>
          <a href={`#/claim/${claimId}`} className="text-link">Inspect the check <span aria-hidden="true">↗</span></a>
        </section>
      )}
      <section className="grid g4 ledger" aria-label="Workspace totals">
        {tiles.map(([label, value, desc]) => (
          <div className="tile" key={label}>
            <div className="over">{label}</div>
            <div className="stat num">{value}</div>
            <div className="muted small" style={{ marginTop: 8 }}>{desc}</div>
          </div>
        ))}
      </section>

      <section className="grid g32">
        <div className="tile w">
          <div className="row between"><h4>Needs your decision</h4><a className="small" style={{ textDecoration: "underline" }} onClick={() => A.go("review")}>Review all</a></div>
          {attention.length === 0 && <p className="muted">Nothing yet. Press "Check {waiting.length || ""} waiting" to watch the agent work.</p>}
          {attention.map(c => (
            <div key={c.id} className="row" style={{ padding: "16px 0", borderTop: "1px solid var(--g2)", marginTop: 12, cursor: "pointer" }} onClick={() => A.go("claim", c.id)}>
              <Tag s={status[c.id]} />
              <div style={{ flex: 1 }}>
                <div style={{ fontWeight: 600 }}>{partyOf(c).name} · {c.title}</div>
                <div className="muted small">{c.outcome.reason.split(". ")[0]}.</div>
              </div>
              <div className="num" style={{ fontWeight: 600, fontSize: 18, color: COL[c.outcome.b[2]] }}>{money(c.outcome.b[1])}</div>
            </div>
          ))}
        </div>
        <div className="tile">
          <h4>Agent activity</h4>
          <div className="term" style={{ marginTop: 14, maxHeight: 260 }}>
            {S.log.length === 0 && <div className="g">No runs yet.</div>}
            {S.log.slice(0, 12).map((l, k) => <div key={k}><span className="g">{l.t}</span> {l.ok === "done" ? "✓" : l.ok === "fail" ? "✗" : "!"} <span className="g">{l.who}</span> {l.text}</div>)}
          </div>
        </div>
      </section>

      </div>
    </div>
  );
}
