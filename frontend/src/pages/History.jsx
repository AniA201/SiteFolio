import { useEffect, useState } from "react";
import { api } from "../api";
import { Flag, Head } from "../lib";

const LABELS = { reviewer: "Events", lender: "Events", owner: "Events" };

const DOUBLE_CHARGE_SQL = `SELECT * FROM surcharge_registry
WHERE property_id = $1 AND lower(work) = lower($2)
  AND ends >= CURRENT_DATE;`;
const WEEKLY_SQL = `CREATE MATERIALIZED VIEW history_weekly
WITH (timescaledb.continuous) AS
SELECT time_bucket('1 week', at) AS week,
       persona, count(*) AS events, sum(paid), sum(held)
FROM history_events GROUP BY week, persona;`;

export default function History({ S, A }) {
  const [history, setHistory] = useState(null);
  useEffect(() => { let active = true; api.history(S.persona).then(v => { if (active) setHistory(v); }).catch(() => { if (active) setHistory(null); }); return () => { active = false; }; }, [S.persona, S.log.length]);
  const weekly = [...(history?.weekly || [])].reverse();
  const data = weekly.map(w => Number(w.events));
  const max = Math.max(...data, 1);
  const lab = LABELS[S.persona];
  const stats = [["Events stored", history?.connected ? history.events.toLocaleString() : "—", "documents, checks, decisions"], ["Active surcharges", history?.connected ? history.surcharges.filter(s => new Date(s.ends) >= new Date()).length : "—", "registry records"], ["Weekly buckets", history?.connected ? weekly.length : "—", "continuous aggregate"]];
  return (
    <div className="wrapx">
      <Head over="Tiger Data · time-series history" title="History" lede="Every document, check, payment and rent surcharge is stored as a time-stamped event. That's how Plumbline knows when the same work is charged twice." />
      <div className="grid g4">
        {stats.map(([l, v, d]) => <div className="tile" key={l}><div className="over">{l}</div><div className="stat num" style={{ fontSize: 34 }}>{v}</div><div className="muted small" style={{ marginTop: 8 }}>{d}</div></div>)}
      </div>
      <section className="grid g32">
        <div className="tile">
          <div className="row between"><h4>{lab} stored per week</h4></div>
          <div style={{ display: "flex", alignItems: "flex-end", gap: 14, height: 220, marginTop: 24, paddingBottom: 26 }}>
            {data.map((d, i) => (
              <div key={i} style={{ flex: 1, display: "flex", flexDirection: "column", justifyContent: "flex-end", height: "100%", position: "relative" }}>
                <div style={{ height: (d / max) * 100 + "%", background: "#000", borderRadius: "6px 6px 0 0" }} />
                <span className="small muted" style={{ position: "absolute", bottom: -24, left: 0, right: 0, textAlign: "center" }}>{new Date(weekly[i].week).toLocaleDateString(undefined, { month: "short", day: "numeric" })}</span>
              </div>
            ))}
          </div>
          <p className="muted small">{history?.connected ? "Measured from stored events." : "Connect Tiger Cloud to show live history."}</p>
        </div>
        <div className="tile">
          <h4>The double-charge check</h4>
          <pre className="json" style={{ marginTop: 12 }}>{DOUBLE_CHARGE_SQL}</pre>
          <p className="muted small" style={{ lineHeight: 1.5 }}>Checks active surcharges for the same property and type of work. Claims still require a reviewer to decide.</p>
          <button className="btn black sm" onClick={() => { A.setPersona("reviewer"); A.go("claims"); }}>Try it on Vermont Gardens</button>
        </div>
      </section>
      <div className="tbl"><table>
        <thead><tr><th>Building</th><th>Work</th><th>Approved</th><th>Ends</th><th>Per unit / month</th></tr></thead>
        <tbody>
          {(history?.surcharges || []).map(s => (
            <tr key={s.property_id + s.work} className={s.work === "Roof" ? "bad" : ""}>
              <td><b>{s.building}</b> <span className="mono muted small">{s.property_id}</span></td>
              <td>{s.work}</td><td>{s.approved}</td><td>{s.ends}</td><td className="num">${Number(s.per_unit).toFixed(2)}</td>
            </tr>
          ))}
        </tbody>
      </table></div>
      <section className="grid g2">
        <div className="tile"><h4>How the weekly chart is stored</h4><pre className="json" style={{ marginTop: 12 }}>{WEEKLY_SQL}</pre></div>
        <div className="tile">
          <h4>Live events</h4>
          <div className="term" style={{ marginTop: 12, maxHeight: 220 }}>
            {!history?.recent?.length ? <span className="g">No stored events yet.</span> : history.recent.map((event, k) => <div key={k}><span className="g">{event.kind}</span> {event.claim_id} · {event.detail?.text || event.detail?.status || event.detail?.action || "recorded"}</div>)}
          </div>
        </div>
      </section>
      <Flag t={history?.connected ? "Tiger Cloud history" : "Tiger Cloud connection required"} />
    </div>
  );
}
