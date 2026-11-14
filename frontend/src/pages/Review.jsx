import { useState } from "react";
import { BUILDINGS, PARTIES, partyOf } from "../data";
import { COL, Head, NEEDS, Tag, money } from "../lib";
import EvidenceFolio from "../components/EvidenceFolio";

const APPROVE_LABEL = {
  owner: c => c.outcome.status === "blocked" ? "Confirm block" : `Approve: pay ${money(c.outcome.a[1])}, hold ${money(c.outcome.b[1])}`,
  reviewer: c => c.outcome.status === "denied" ? "Confirm denial" : `Approve at ${c.outcome.b[1]}`,
  lender: c => `Release ${money(c.outcome.a[1])}, hold ${money(c.outcome.b[1])}`,
};

export default function Review({ S, A }) {
  const cases = S.list.filter(c => NEEDS.includes(S.status[c.id]));
  const [sel, setSel] = useState(null);
  const [msg, setMsg] = useState({});
  const cur = cases.find(c => c.id === sel) || cases[0];
  return (
    <div className="wrapx">
      <Head over="Human in the loop" title="Review" lede="The agent never moves money or decides rent on its own. It pauses here with the proof, and a person decides." />
      {!cur && (
        <div className="tile">
          <h4>Nothing to review yet</h4>
          <p className="muted">Check the waiting items first.</p>
          <button className="btn black sm" disabled={S.running} onClick={A.runAll}>Check waiting</button>
        </div>
      )}
      {cur && (
        <div className="grid g12 review-layout">
          <div className="review-queue">
            {cases.map(c => (
              <button type="button" className="review-item" key={c.id} aria-pressed={c.id === cur.id} onClick={() => setSel(c.id)}>
                <div className="row between"><span className="mono small muted">{c.id}</span><Tag s={S.review[c.id] || S.status[c.id]} /></div>
                <div style={{ fontWeight: 600, marginTop: 6 }}>{partyOf(c).name}</div>
                <div className="row between"><span className="small muted">{c.title}</span><span className="num" style={{ fontWeight: 700, color: COL[c.outcome.b[2]] }}>{money(c.outcome.b[1])}</span></div>
              </button>
            ))}
          </div>
          <div className="tile">
            <div className="row between">
              <div><div className="over">{cur.id} · {BUILDINGS[cur.b].name}</div><h2 className="h3" style={{ marginTop: 8 }}>{cur.title}</h2></div>
              <a className="text-link" href={`#/claim/${cur.id}`}>Full check ↗</a>
            </div>
            <EvidenceFolio key={cur.id} lines={cur.lines} />
            <p style={{ fontSize: 16, lineHeight: 1.55, marginTop: 18 }}>{cur.outcome.reason}</p>
            {cur.outcome.note && <>
              <div className="over" style={{ marginTop: 16 }}>Drafted message</div>
              <textarea className="ta" rows={3} style={{ marginTop: 8, background: "var(--surface)" }} value={msg[cur.id] ?? cur.outcome.note} onChange={e => setMsg({ ...msg, [cur.id]: e.target.value })} />
            </>}
            <div className="row wrap" style={{ marginTop: 18 }}>
              {S.review[cur.id] ? <>
                <Tag s={S.review[cur.id]} />
                <span className="muted small">Recorded. The agent resumed and logged it.</span>
                <button className="btn white sm" onClick={() => A.decide(cur.id, null)}>Undo</button>
              </> : <>
                <button className="btn black sm" onClick={() => A.decide(cur.id, "ok")}>{APPROVE_LABEL[cur.persona](cur)}</button>
                {cur.outcome.note && <button className="btn amber sm" onClick={() => A.decide(cur.id, "sent")}>Send message</button>}
                <button className="btn white sm" onClick={() => A.decide(cur.id, "rejected")}>Reject</button>
              </>}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
