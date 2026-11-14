import { useState } from "react";
import { BUILDINGS, partyOf } from "../data";
import { Flag, Head, J, NEEDS, WHO } from "../lib";

const LANES = ["coordinator", "records", "roof", "interior", "rules"];
const LANE_COLOR = { coordinator: "var(--ink)", records: "var(--ink3)", roof: "var(--accent)", interior: "var(--g3)", rules: "var(--ink2)" };

function PlanVersions({ plans }) {
  return plans.map((plan, i) => {
    const before = new Set((plans[i - 1] || []).map(t => t.content));
    return (
      <div key={i} style={{ marginTop: i ? 14 : 8 }}>
        <div className="small" style={{ fontWeight: 600, color: i ? "var(--amberDeep, var(--accent))" : "var(--ink3)" }}>
          {i ? `Plan v${i + 1}: changed mid-run` : "Plan v1"}
        </div>
        <ol style={{ paddingLeft: 18, lineHeight: 1.7, fontSize: 14, margin: "4px 0 0" }}>
          {plan.map((t, k) => {
            const added = i > 0 && !before.has(t.content);
            return <li key={k} style={{ fontWeight: added ? 700 : 400, color: added ? "var(--amberDeep, var(--accent))" : undefined }}>
              {t.content}{added ? " (new)" : ""} <span className="muted small">· {t.status.replace("_", " ")}</span></li>;
          })}
        </ol>
      </div>
    );
  });
}

function Files({ files }) {
  const [open, setOpen] = useState(null);
  const names = Object.keys(files).sort();
  return (
    <div className="term" style={{ marginTop: 12, maxHeight: 320 }}>
      {names.map(f => (
        <div key={f}>
          <a style={{ cursor: "pointer", textDecoration: open === f ? "underline" : "none" }} onClick={() => setOpen(open === f ? null : f)}>{f}</a>
          {open === f && <pre style={{ margin: "6px 0 10px", whiteSpace: "pre-wrap", color: "rgba(255,255,255,.75)" }}>{files[f]}</pre>}
        </div>
      ))}
    </div>
  );
}

export default function Thinks({ S, A }) {
  const [sel, setSel] = useState(null);
  const ran = S.list.filter(c => (S.steps[c.id] ?? -1) >= c.steps.length);
  const c = S.list.find(x => x.id === sel) || ran.find(x => x.agent) || ran[0] || S.list[0];
  if (!c) return null;
  const done = (S.steps[c.id] ?? -1) >= c.steps.length;
  const n = Math.max(1, c.steps.length);
  const ag = c.agent;
  const paused = NEEDS.includes(c.outcome.status) && !S.review[c.id];
  const party = partyOf(c), B = BUILDINGS[c.b];
  const mem = S.memory || {};
  const myMemory = Object.fromEntries(Object.entries(mem).filter(([k]) => k.includes(party.name) || k.endsWith(`/${c.b}.md`)));
  const changed = c.steps.findIndex(s => s[1].startsWith("Plan updated"));
  const trace = ag?.trace_url;
  return (
    <div className="wrapx">
      <Head over="For the LangChain judges" title="How it thinks"
        lede="A LangChain deep agent on free models: it plans with a to-do list, sends three helper agents to the data layers, changes its plan when a check fails, writes an evidence folder, remembers vendors and buildings, and pauses for a person before money moves."
        right={trace ? <a className="btn gray" href={trace} target="_blank" rel="noopener">Open LangSmith trace ↗</a>
          : <button className="btn gray" disabled>{ag ? "Trace is uploading…" : "Run live to get a trace"}</button>} />
      <div className="row wrap" style={{ marginBottom: 18, gap: 8 }}>
        {[["Agent", "deepagents + LangGraph"], ["Models", "free: Groq gpt-oss-120b, then Ollama gpt-oss:20b on this Mac"], ["Data", "CoStar · Vexcel · Matterport"], ["Money and rent math", "plain code, no AI"]].map(([k, v]) =>
          <span key={k} className="tag t-ready" style={{ fontSize: 13, padding: "8px 14px" }}><b style={{ color: "var(--ink)" }}>{k}</b>&nbsp;{v}</span>)}
      </div>
      <div className="row wrap" style={{ marginBottom: 18 }}>
        {S.list.map(x => <button key={x.id} className={"btn sm " + (x.id === c.id ? "black" : "gray")} onClick={() => setSel(x.id)}>{x.id}{x.agent ? " · live" : ""}</button>)}
      </div>
      {!done && (
        <div className="tile">
          <h4>{c.id} hasn't run yet</h4>
          <p className="muted small">A live run takes about 30–70 seconds on the free models. Steps stream in as the agent works.</p>
          <button className="btn black sm" style={{ marginTop: 12 }} disabled={S.running} onClick={() => A.run(c.id)}>Run the agent now</button>
        </div>
      )}
      {done && <>
        {ag?.overruled && <div className="tile" style={{ marginBottom: 16 }}><div className="over">Rules overruled the agent</div><p style={{ margin: "6px 0 0" }}>{ag.overruled}</p></div>}
        <div className="grid g2">
          <div className="tile">
            <div className="over">1 · Planning</div>
            <h4 style={{ marginTop: 8 }}>{ag ? "The agent's to-do list, as it changed" : "The plan, and how it changed"}</h4>
            {ag?.plans?.length ? <PlanVersions plans={ag.plans} /> : <>
              <ol style={{ paddingLeft: 18, lineHeight: 1.8, fontSize: 14 }}>
                {c.steps.map((s, k) => <li key={k} style={{ fontWeight: k === changed ? 700 : 400, color: k === changed ? "var(--amberDeep)" : undefined }}>{s[1]}</li>)}
              </ol>
              <p className="muted small">Recorded plan. Run the agent live to see its own to-do list.</p>
            </>}
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
            {ag?.models && <p className="muted small" style={{ marginTop: 14 }}>Model calls: {Object.entries(ag.models).map(([m, k]) => `${m} × ${k}`).join(" · ")}. All free.</p>}
          </div>
        </div>
        <div className="grid g3" style={{ marginTop: 16 }}>
          <div className="tile">
            <div className="over">3 · Evidence folder</div>
            {c.evidence_files ? <Files files={c.evidence_files} /> : (
              <div className="term" style={{ marginTop: 12 }}>
                <div><b>/evidence/{c.id.toLowerCase()}/</b></div>
                {["plan.md", ...c.apis.map(a => a.svc.toLowerCase().replace(" ", "_") + ".json"), "decision.md"].map(f => <div key={f}>  {f}</div>)}
              </div>
            )}
          </div>
          <div className="tile">
            <div className="over">4 · Long-term memory</div>
            {Object.keys(myMemory).length ? <Files files={myMemory} />
              : <pre className="json" style={{ marginTop: 12 }}>{J({ party: party.name, note: party.memory, building: B.name, last_check: c.id })}</pre>}
            <p className="muted small">Stored in the agent's /memories/ folder (a LangGraph store) and read at the start of every check.</p>
          </div>
          <div className="tile">
            <div className="over">5 · Human in the loop</div>
            <h4 style={{ marginTop: 8 }}>{paused ? "Paused for a person" : S.review[c.id] ? "A person decided" : "No pause needed"}</h4>
            <p className="muted" style={{ lineHeight: 1.55 }}>{paused
              ? `The agent stopped at record_decision before any money moved or any rent changed.${ag ? " Approving or rejecting in Review resumes this same run." : ""}`
              : S.review[c.id] ? "The decision was recorded and the agent's run was resumed to log it." : "Everything matched."}</p>
            {paused && <button className="btn black sm" onClick={() => A.go("review")}>Go to review</button>}
          </div>
        </div>
      </>}
      <div style={{ marginTop: 14 }}><Flag t={ag ? "Live run on free models · trace in LangSmith" : "Recorded plan · run live for the agent's own trace"} /></div>
    </div>
  );
}
