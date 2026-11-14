import { useState } from "react";
import { BUILDINGS, PARTIES } from "../data";
import { COL, Head, NEEDS, Tag, money } from "../lib";

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
        <div className="grid g12" style={{ alignItems: "start" }}>
          <div className="tbl">
            {cases.map(c => (
              <div key={c.id} onClick={() => setSel(c.id)} style={{ padding: "16px 18px", borderTop: "1px solid var(--g2)", cursor: "pointer", background: c.id === cur.id ? "var(--g1)" : "#fff" }}>
                <div className="row between"><span className="mono small muted">{c.id}</span><Tag s={S.review[c.id] || S.status[c.id]} /></div>
                <div style={{ fontWeight: 600, marginTop: 6 }}>{PARTIES[c.party].name}</div>
                <div className="row between"><span className="small muted">{c.title}</span><span className="num" style={{ fontWeight: 700, color: COL[c.outcome.b[2]] }}>{money(c.outcome.b[1])}</span></div>
              </div>
            ))}
          </div>
          <div className="tile">
            <div className="row between">
              <div><div className="over">{cur.id} · {BUILDINGS[cur.b].name}</div><h2 className="h3" style={{ marginTop: 8 }}>{cur.title}</h2></div>
              <a className="small" style={{ textDecoration: "underline" }} onClick={() => A.go("claim", cur.id)}>Full check →</a>
            </div>
            <div className="grid g2" style={{ marginTop: 18 }}>
              <div className="tile w">
                <div className="over">The paper says</div>
                {cur.lines.map(l => <div key={l[0]} style={{ marginTop: 12 }}><div className="muted small">{l[0]}</div><div style={{ fontSize: 22, fontWeight: 600 }} className="num">{l[1]}</div></div>)}
              </div>
              <div className="tile dark">
                <div className="over" style={{ color: "rgba(255,255,255,.6)" }}>The building says</div>
                {cur.lines.map(l => <div key={l[0]} style={{ marginTop: 12 }}><div style={{ color: "rgba(255,255,255,.6)", fontSize: 13.5 }}>{l[0]}</div><div style={{ fontSize: 22, fontWeight: 600, color: l[3] === "bad" ? "var(--amber)" : "#fff" }} className="num">{l[2]}</div></div>)}
              </div>
            </div>
            <p style={{ fontSize: 16, lineHeight: 1.55, marginTop: 18 }}>{cur.outcome.reason}</p>
            {cur.outcome.note && <>
              <div className="over" style={{ marginTop: 16 }}>Drafted message</div>
              <textarea className="ta" rows={3} style={{ marginTop: 8, background: "#fff" }} value={msg[cur.id] ?? cur.outcome.note} onChange={e => setMsg({ ...msg, [cur.id]: e.target.value })} />
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
