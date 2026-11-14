import { useState } from "react";
import { BUILDINGS, PARTIES, partyOf } from "../data";
import { Flag, Head, J, NEEDS, WHO } from "../lib";

const STACK = [["Agent", "deepagents"], ["Data", "CoStar · Vexcel · Matterport"], ["History", "Tiger Data"], ["Hosting + GPU", "Vultr"], ["Money and rent math", "plain code, no AI"]];
const LANES = ["coordinator", "records", "roof", "interior", "rules"];
const LANE_COLOR = { coordinator: "var(--ink)", records: "var(--ink3)", roof: "var(--accent)", interior: "var(--g3)", rules: "var(--ink2)" };

export default function Thinks({ S, A }) {
  const [sel, setSel] = useState(null);
  const ran = S.list.filter(c => (S.steps[c.id] ?? -1) >= c.steps.length);
  const c = ran.find(x => x.id === sel) || ran[0] || S.list[0];
  if (!c) return null;
  const done = (S.steps[c.id] ?? -1) >= c.steps.length;
  const n = c.steps.length;
  const changed = c.steps.findIndex(s => s[1].startsWith("Plan updated"));
  const paused = NEEDS.includes(c.outcome.status);
  return (
    <div className="wrapx">
      <Head over="For the LangChain judges" title="How it thinks" lede="A LangChain deep agent: it plans, sends helper agents to each data source, changes its plan when a check fails, keeps an evidence folder, remembers past claims and waits for a person." right={<button className="btn gray">Open LangSmith trace ↗</button>} />
      <div className="row wrap" style={{ marginBottom: 18, gap: 8 }}>
        {STACK.map(([k, v]) => <span key={k} className="tag t-ready" style={{ fontSize: 13, padding: "8px 14px" }}><b style={{ color: "var(--ink)" }}>{k}</b>&nbsp;{v}</span>)}
      </div>
      <div className="row wrap" style={{ marginBottom: 18 }}>
        {S.list.map(x => <button key={x.id} className={"btn sm " + (x.id === c.id ? "black" : "gray")} onClick={() => setSel(x.id)}>{x.id}</button>)}
      </div>
      {!done && (
        <div className="tile">
          <h4>{c.id} hasn't run yet</h4>
          <button className="btn black sm" style={{ marginTop: 12 }} disabled={S.running} onClick={() => A.run(c.id)}>Run it now</button>
        </div>
      )}
      {done && <>
        <div className="grid g2">
          <div className="tile">
            <div className="over">1 · Planning</div>
            <h4 style={{ marginTop: 8 }}>The plan, and how it changed</h4>
            <ol style={{ paddingLeft: 18, lineHeight: 1.8, fontSize: 14 }}>
              {c.steps.map((s, k) => <li key={k} style={{ fontWeight: k === changed ? 700 : 400, color: k === changed ? "var(--amberDeep)" : undefined }}>{s[1]}</li>)}
            </ol>
            <p className="muted small">{changed >= 0 ? "The bold step was added mid-run, after a check failed." : "No check failed, so the plan didn't change."}</p>
          </div>
          <div className="tile">
            <div className="over">2 · Helper agents</div>
            <h4 style={{ marginTop: 8 }}>Who did what, in order</h4>
            {LANES.map(l => (
              <div className="lane" key={l}>
                <span className="small" style={{ fontWeight: 600 }}>{WHO[l]}</span>
                <div className="track">{c.steps.map((s, k) => s[0] === l && <div key={k} className="seg" style={{ left: (k / n) * 100 + "%", width: (1 / n) * 100 - 1 + "%", background: LANE_COLOR[l] }} />)}</div>
              </div>
            ))}
          </div>
        </div>
        <div className="grid g3" style={{ marginTop: 16 }}>
          <div className="tile">
            <div className="over">3 · Evidence folder</div>
            <div className="term" style={{ marginTop: 12 }}>
              <div><b>/evidence/{c.id.toLowerCase()}/</b></div>
              {["plan.md", ...c.apis.map(a => a.svc.toLowerCase().replace(" ", "_") + ".json"), "decision.md"].map(f => <div key={f}>  {f}</div>)}
              <div><b>/memories/</b></div>
              <div>  buildings/{BUILDINGS[c.b].cs}.md</div>
              <div>  parties/{c.party}.md</div>
            </div>
          </div>
          <div className="tile">
            <div className="over">4 · Long-term memory</div>
            <pre className="json" style={{ marginTop: 12 }}>{J({ party: partyOf(c).name, note: partyOf(c).memory, building: BUILDINGS[c.b].name, last_check: c.id })}</pre>
          </div>
          <div className="tile">
            <div className="over">5 · Human in the loop</div>
            <h4 style={{ marginTop: 8 }}>{paused ? "Paused for a person" : "No pause needed"}</h4>
            <p className="muted" style={{ lineHeight: 1.55 }}>{paused ? "The agent stopped before any money moved or any rent changed. Approving in Review resumes the same run." : "Everything matched, so it finished without interrupting anyone."}</p>
            {paused && <button className="btn black sm" onClick={() => A.go("review")}>Go to review</button>}
          </div>
        </div>
      </>}
      <div style={{ marginTop: 14 }}><Flag t="Trace link is illustrative" /></div>
    </div>
  );
}
