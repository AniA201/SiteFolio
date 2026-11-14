import { SURCHARGES } from "../data";
import { FINAL, Flag, Head, sumNum } from "../lib";

const WEEKS = ["Sep 28", "Oct 5", "Oct 12", "Oct 19", "Oct 26", "Nov 2", "This week"];
// Past weeks per persona: [main, held]. Sample history.
const PAST = {
  owner: [[41, 0], [38, 4], [52, 0], [47, 1], [35, 0], [58, 10]],
  reviewer: [[3, 1], [2, 0], [4, 2], [3, 1], [5, 2], [2, 1]],
  lender: [[300, 0], [0, 0], [450, 50], [0, 0], [250, 0], [0, 0]],
};
const LABELS = { reviewer: ["Checked", "Reduced or denied", "applications"], lender: ["Released", "Held", "$ thousands"], owner: ["Paid", "Held", "$ thousands"] };

const DOUBLE_CHARGE_SQL = `SELECT * FROM surcharges
WHERE property = $1
  AND work = 'roof'
  AND ends_at > now();`;
const WEEKLY_SQL = `SELECT create_hypertable('events', 'at');

CREATE MATERIALIZED VIEW weekly
WITH (timescaledb.continuous) AS
SELECT time_bucket('1 week', at) AS week,
       persona, sum(paid), sum(held)
FROM events GROUP BY week, persona;`;

export default function History({ S, A }) {
  const events = 1284310 + S.log.length;
  const caught = S.status["RSO-3110"] === "denied" ? 1 : 0;
  const done = S.list.filter(c => FINAL.includes(S.status[c.id]));
  const now = S.persona === "reviewer"
    ? [done.length, done.filter(c => c.outcome.status !== "approved").length]
    : [Math.round(sumNum(done, "a") / 1000), Math.round(sumNum(done, "b") / 1000)];
  const data = [...PAST[S.persona], now], max = Math.max(...data.map(d => d[0] + d[1]), 1);
  const lab = LABELS[S.persona];
  const stats = [["Events stored", events.toLocaleString(), "documents, checks, decisions"], ["Double charges caught", caught, "same work billed twice"], ["Dashboard query", "38 ms", "continuous aggregate"], ["Storage after compression", "91% smaller", "hypertable compression"]];
  return (
    <div className="wrapx">
      <Head over="Tiger Data · time-series history" title="History" lede="Every document, check, payment and rent surcharge is stored as a time-stamped event. That's how Plumbline knows when the same work is charged twice." />
      <div className="grid g4">
        {stats.map(([l, v, d]) => <div className="tile" key={l}><div className="over">{l}</div><div className="stat num" style={{ fontSize: 34 }}>{v}</div><div className="muted small" style={{ marginTop: 8 }}>{d}</div></div>)}
      </div>
      <section className="grid g32">
        <div className="tile">
          <div className="row between"><h4>{lab[0]} vs {lab[1]}, per week ({lab[2]})</h4></div>
          <div style={{ display: "flex", alignItems: "flex-end", gap: 14, height: 220, marginTop: 24, paddingBottom: 26 }}>
            {data.map((d, i) => (
              <div key={i} style={{ flex: 1, display: "flex", flexDirection: "column", justifyContent: "flex-end", height: "100%", position: "relative" }}>
                <div style={{ height: (d[1] / max) * 100 + "%", background: "var(--amber)", borderRadius: "6px 6px 0 0" }} />
                <div style={{ height: (d[0] / max) * 100 + "%", background: "#000", borderRadius: d[1] ? 0 : "6px 6px 0 0" }} />
                <span className="small muted" style={{ position: "absolute", bottom: -24, left: 0, right: 0, textAlign: "center", fontWeight: i === 6 ? 700 : 400 }}>{WEEKS[i]}</span>
              </div>
            ))}
          </div>
          <p className="muted small">This week's bar fills in as you run checks.</p>
        </div>
        <div className="tile">
          <h4>The double-charge check</h4>
          <pre className="json" style={{ marginTop: 12 }}>{DOUBLE_CHARGE_SQL}</pre>
          <p className="muted small" style={{ lineHeight: 1.5 }}>Runs on every rent application and every bill. It caught the Vermont Gardens roof being charged to tenants twice.</p>
          <button className="btn black sm" onClick={() => { A.setPersona("reviewer"); A.go("claims"); }}>Try it on Vermont Gardens</button>
        </div>
      </section>
      <div className="tbl"><table>
        <thead><tr><th>Building</th><th>Work</th><th>Approved</th><th>Ends</th><th>Per unit / month</th></tr></thead>
        <tbody>
          {SURCHARGES.map(s => (
            <tr key={s.property_id + s.work} className={s.work === "Roof" ? "bad" : ""}>
              <td><b>{s.building}</b> <span className="mono muted small">{s.property_id}</span></td>
              <td>{s.work}</td><td>{s.approved}</td><td>{s.ends}</td><td className="num">{s.per_unit}</td>
            </tr>
          ))}
        </tbody>
      </table></div>
      <section className="grid g2">
        <div className="tile"><h4>How the weekly chart is stored</h4><pre className="json" style={{ marginTop: 12 }}>{WEEKLY_SQL}</pre></div>
        <div className="tile">
          <h4>Live events</h4>
          <div className="term" style={{ marginTop: 12, maxHeight: 220 }}>
            {S.log.length === 0 ? <span className="g">Run a check to stream events here.</span> : S.log.slice(0, 9).map((l, k) => <div key={k}><span className="g">INSERT</span> {l.t} · {l.who} · {l.text.slice(0, 46)}</div>)}
          </div>
        </div>
      </section>
      <Flag t="Sample history · storage and timing figures are placeholders" />
    </div>
  );
}
