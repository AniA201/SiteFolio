import { useState } from "react";
import { BUILDINGS, PARTIES, PERSONAS } from "../data";
import { Flag, Head, NEEDS, Tag, fmt } from "../lib";

const FILTERS = [["all", "All"], ["ready", "Waiting"], ["approved", "Verified"], ["attn", "Held, reduced or blocked"]];
const TITLES = { owner: "Bills", reviewer: "Applications", lender: "Loan requests" };

export default function Claims({ S, A }) {
  const [filter, setFilter] = useState("all");
  const P = PERSONAS[S.persona];
  const st = c => S.status[c.id] || "ready";
  const rows = S.list.filter(c => filter === "all" || (filter === "attn" ? NEEDS.includes(st(c)) : st(c) === filter));
  const sample = S.samples.find(c => c.persona === S.persona);

  return (
    <div className="wrapx">
      <Head over={P.label} title={TITLES[S.persona]} lede={`Upload a ${P.verb}. The agent reads every line and checks each claim against the building.`}
        right={<button className="btn black" disabled={S.running || !S.list.some(c => st(c) === "ready")} onClick={A.runAll}>Check all waiting</button>} />
      <div className="grid g21" style={{ alignItems: "stretch" }}>
        <div>
          <div className="tabs" style={{ marginBottom: 14 }}>
            {FILTERS.map(([k, l]) => <button key={k} className={filter === k ? "on" : ""} onClick={() => setFilter(k)}>{l}</button>)}
          </div>
          <div className="tbl"><table>
            <thead><tr><th>ID</th><th>From</th><th>Claim</th><th>Building</th><th className="r">Amount</th><th>Status</th></tr></thead>
            <tbody>
              {rows.map(c => (
                <tr key={c.id} className="click" onClick={() => A.go("claim", c.id)}>
                  <td className="mono">{c.id}</td>
                  <td style={{ fontWeight: 600 }}>{PARTIES[c.party].name}</td>
                  <td>{c.title}</td>
                  <td className="muted">{BUILDINGS[c.b].name}</td>
                  <td className="r num">{fmt(c.amount)}</td>
                  <td><Tag s={st(c)} /></td>
                </tr>
              ))}
            </tbody>
          </table></div>
        </div>
        <div className="tile" style={{ textAlign: "center", display: "grid", placeItems: "center", border: "2px dashed var(--g3)", background: "#fff" }}>
          <div>
            <div style={{ fontSize: 34 }}>↓</div>
            <h4 style={{ marginTop: 6 }}>Drop a {P.verb}</h4>
            <p className="muted small">PDF, photo or email. The building is matched automatically.</p>
            <button className="btn black sm" disabled={!sample} onClick={() => sample && A.ingest(sample.id)}>{sample ? `Use sample: ${sample.title}` : "No more samples"}</button>
            <div style={{ marginTop: 12 }}><Flag t="Upload is mocked" /></div>
          </div>
        </div>
      </div>
    </div>
  );
}
