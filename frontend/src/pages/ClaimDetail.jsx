import { useState } from "react";
import { BUILDINGS, PARTIES, PERSONAS } from "../data";
import { COL, Check, Flag, J, LAYER, SvcChip, Tag, WHO, aerialKind, fmt, isLayer, money, sqft } from "../lib";
import { Aerial, FloorPlan } from "../components/Illustrations";
import MatterportTour, { toursFromCall } from "../components/MatterportTour";

const TABS = [["run", "Agent run"], ["apis", "Building data calls"], ["cross", "Cross-checks"], ["evidence", "Evidence"]];
const MEASURED_KINDS = ["roof", "rent", "rentdup", "parking"];
const DECISION_BG = s => ["blocked", "denied"].includes(s) ? "#FDF0F1" : s === "approved" ? "#EEF7F1" : "#FFF7E0";
const fileName = svc => svc.toLowerCase().replace(" ", "_") + ".json";
const snake = s => s.toLowerCase().replace(/ /g, "_");

// The real Vexcel orthophoto around the building, served by the backend (key stays server-side).
function RealAerial({ B, show }) {
  const [failed, setFailed] = useState(false);
  const half = Math.max(35, Math.round(Math.sqrt(B.roof * 0.0929) * 0.8));
  const src = `/api/data/vexcel/ortho.jpg?lat=${B.lat}&lon=${B.lon}&half_side_m=${half}&pixels=900`;
  if (failed) return <Aerial b={B.id} kind="roof" show={show} />;
  return (
    <div style={{ position: "relative", aspectRatio: "1 / 1", background: "#4E5A47" }}>
      <img src={src} alt={`Aerial view of ${B.name}`} onError={() => setFailed(true)} style={{ width: "100%", height: "100%", objectFit: "cover", display: "block", filter: show ? "none" : "grayscale(1) brightness(.8)" }} />
      {show && <span className="tag" style={{ position: "absolute", left: 10, bottom: 10, background: "#0A0A0A", color: "#FFAA00", fontFamily: "var(--mono)" }}>{B.roof.toLocaleString()} sq ft footprint · {B.ac} AC units</span>}
    </div>
  );
}

function RulesBox({ c, done }) {
  const o = c.outcome;
  if (c.persona === "reviewer") return (
    <div className="tile">
      <div className="row between"><h4>Rent math</h4><span className="over">Plain code, no AI</span></div>
      <p className="muted small" style={{ marginTop: 6 }}>LA formula: 50% of the cost, spread over 60 months, split across units.</p>
      <div className="receipt" style={{ background: "#fff" }}>
        {done ? <>claimed  {fmt(c.amount)} × 50% ÷ 60 ÷ {c.rent.units} = ${c.rent.claimed.toFixed(2)}<br />verified → ${c.rent.verified.toFixed(2)} per unit per month</> : "Waiting for the checks…"}
      </div>
    </div>
  );
  if (c.persona === "lender") return (
    <div className="tile">
      <div className="row between"><h4>Release math</h4><span className="over">Plain code, no AI</span></div>
      <div className="receipt" style={{ background: "#fff" }}>
        {done ? <>requested {fmt(c.amount)} · verified share {c.measured ? Math.round(c.measured / c.claim * 100) : 100}%<br />release {money(o.a[1])} · hold {money(o.b[1])}</> : "Waiting for the checks…"}
      </div>
    </div>
  );
  const p = PARTIES[c.party], badBank = c.bank && c.bank !== p.acct;
  const checks = [["Approved contractor", true], ["Account matches " + p.acct, !badBank], ["Amount at or below verified", true], ["Not paid before", true]];
  return (
    <div className="tile">
      <div className="row between"><h4>Payment rules</h4><span className="over">Plain code, no AI</span></div>
      <div style={{ marginTop: 8 }}>
        {checks.map(([t, ok]) => (
          <div className="chk" key={t}>
            <span className={"dot " + (done ? (ok ? "done" : "fail") : "")}>{done && <Check res={ok ? "done" : "fail"} />}</span>{t}
          </div>
        ))}
      </div>
    </div>
  );
}

function RunTab({ S, A, c, step, done, mine, reached, setTab }) {
  const o = c.outcome, B = BUILDINGS[c.b];
  const idx = svc => c.apis.findIndex(a => a.svc === svc);
  const vi = idx("Vexcel"), mi = idx("Matterport"), ci = idx("CoStar");
  const tours = B.real && mi >= 0 ? toursFromCall(c.apis[mi]) : [];
  return (
    <section className="grid g32" style={{ alignItems: "start" }}>
      <div>
        <div className="tile">
          <div className="row between"><h4>{step < 0 ? "Ready to check" : "The agent's plan"}</h4><span className="muted small">{Math.max(0, Math.min(step, c.steps.length))} of {c.steps.length}</span></div>
          <div style={{ marginTop: 10 }}>
            {c.steps.map(([who, text, res, api], k) => {
              const isDone = k < step, live = k === step && mine;
              const cls = isDone ? (res === "done" ? "done" : res === "fail" ? "fail" : "warn") : live ? "live" : "";
              return (
                <div className="todo" key={k} style={{ opacity: isDone || live ? 1 : .35, gridTemplateColumns: "22px 1fr auto auto" }}>
                  <span className={"dot " + cls}>{isDone && <Check res={res} />}</span>
                  <span>{text}</span>
                  {api !== undefined ? <SvcChip s={c.apis[api].svc} /> : <span />}
                  <span className="who">{WHO[who]}</span>
                </div>
              );
            })}
          </div>
        </div>
        {done && (
          <div className="tile" style={{ marginTop: 16, background: DECISION_BG(o.status) }}>
            <div className="row between"><div className="over">Decision</div><Tag s={o.status} /></div>
            <div className="row" style={{ gap: 48, marginTop: 18, alignItems: "flex-end" }}>
              {[o.a, o.b].map(([l, v, col]) => <div key={l}><div className="muted small" style={{ marginBottom: 8 }}>{l}</div><div className="bigmoney num" style={{ color: COL[col] }}>{money(v)}</div></div>)}
            </div>
            <p style={{ fontSize: 16, lineHeight: 1.55, margin: "18px 0 0" }}>{o.reason}</p>
            {o.injected && <div className="quote">Hidden instruction found and ignored: <span className="mono" style={{ color: "var(--red)" }}>"{o.injected}"</span></div>}
            <div className="row wrap" style={{ marginTop: 18 }}>
              {o.status !== "approved" && <button className="btn black sm" onClick={() => A.go("review")}>Decide in review</button>}
              {c.persona === "reviewer" && <button className="btn white sm" onClick={() => A.go("tenant", c.id)}>Open tenant page</button>}
              {c.persona === "owner" && o.a[1] > 0 && <button className="btn white sm" onClick={() => A.retry(c.id)}>Retry payment</button>}
              <button className="btn white sm" onClick={() => setTab("apis")}>See the data calls</button>
            </div>
            {S.retry[c.id] && <div className="receipt">Returned the existing receipt TX-{c.id}-01. No second payment was made.</div>}
          </div>
        )}
      </div>
      <div className="grid" style={{ gap: 16 }}>
        {ci >= 0 && (
          <div className="tile" style={{ opacity: reached(ci) ? 1 : .45 }}>
            <div className="row between"><h4>Building record</h4><SvcChip s="CoStar" /></div>
            <div style={{ fontSize: 24, fontWeight: 600, letterSpacing: "-.5px", marginTop: 12 }}>{B.name}</div>
            <div className="muted small">{B.city} · {B.type} · {B.cs}</div>
            <div className="row wrap" style={{ gap: 26, marginTop: 14 }}>
              {[["Size", sqft(B.size)], ["Floors", B.floors], ...(B.units ? [["Units", B.units]] : []), ["Built", B.status ? "Building now" : B.built]].map(([l, x]) => (
                <div key={l}><div className="muted small">{l}</div><div style={{ fontWeight: 600 }}>{x}</div></div>
              ))}
            </div>
          </div>
        )}
        {vi >= 0 && (
          <div className="tile" style={{ opacity: reached(vi) ? 1 : .45 }}>
            <div className="row between"><h4>From above</h4><SvcChip s="Vexcel" /></div>
            <div className="ph" style={{ marginTop: 14 }}>{B.real && B.lat ? <RealAerial B={B} show={reached(vi)} /> : <Aerial b={c.b} kind={aerialKind(c)} show={reached(vi)} />}</div>
            {c.claim && reached(vi) && MEASURED_KINDS.includes(c.kind) && <>
              <div className="cmp"><span className="muted">Claimed</span><div className="meter"><i style={{ width: "100%", background: "var(--g3)" }} /></div><span className="num r">{c.claim.toLocaleString()}</span></div>
              <div className="cmp"><span className="muted">Measured</span><div className="meter"><i style={{ width: Math.min(100, c.measured / c.claim * 100) + "%", background: c.measured / c.claim < .95 ? "var(--amber)" : "var(--green)" }} /></div><span className="num r" style={{ fontWeight: 700 }}>{c.measured.toLocaleString()}</span></div>
            </>}
            {c.roof_formula && reached(vi) && <div className="receipt" style={{ background: "#fff" }}>{c.roof_formula}</div>}
            <div className="muted small" style={{ marginTop: 10 }}>{B.real ? `Vexcel ortho, ${B.vexcel_collection} · roof ${B.pitch.toLowerCase()}${B.roof_material ? ", " + B.roof_material : ""} · ${B.ac} rooftop units counted` : "Illustration · roof outline measured on a Vultr GPU"}</div>
          </div>
        )}
        {mi >= 0 && (
          <div className="tile" style={{ opacity: reached(mi) ? 1 : .45 }}>
            <div className="row between"><h4>Inside · 3D tour</h4><SvcChip s="Matterport" /></div>
            {tours.length > 0 ? <>
              <MatterportTour tours={tours} show={reached(mi)} />
              <div className="muted small" style={{ marginTop: 10 }}>Live Matterport tour of the scanned space. Room areas come from the Model API.</div>
            </> : <>
              <div className="ph" style={{ marginTop: 14, position: "relative" }}>
                <FloorPlan show={reached(mi)} mode={c.persona === "reviewer" ? "apt" : c.persona === "lender" ? "units" : null} />
                <span className="tag" style={{ position: "absolute", top: 10, right: 10, background: "#0A0A0A", color: "#fff" }}>▶ Live 3D tour in the real app</span>
              </div>
              <div className="muted small" style={{ marginTop: 10 }}>In the real app this panel is the live Matterport tour (Embed SDK), with pins on each measured room. Room areas come from the Model API.</div>
            </>}
          </div>
        )}
        <RulesBox c={c} done={done} />
      </div>
    </section>
  );
}

function ApisTab({ c, reached }) {
  return (
    <section>
      <p className="muted" style={{ marginTop: 0 }}>Every call the agent made, with the request sent and the response returned. <Flag t="Matterport calls follow its real GraphQL Model API · CoStar and Vexcel shapes are assumed" /></p>
      <div className="grid" style={{ gap: 14 }}>
        {c.apis.map((a, i) => {
          const r = reached(i), layer = isLayer(a.svc);
          return (
            <div key={i} className="tile" style={{ background: layer ? "#fff" : "var(--g1)", border: layer ? "2px solid #FFAA00" : "0", opacity: r ? 1 : .45 }}>
              <div className="row between">
                <div className="row">
                  <span className="num" style={{ width: 26, height: 26, borderRadius: "50%", background: "#000", color: "#fff", display: "grid", placeItems: "center", fontSize: 12, fontWeight: 600 }}>{i + 1}</span>
                  <h4>{a.title}</h4><SvcChip s={a.svc} /><span className="muted small">{LAYER[a.svc]}</span>
                </div>
                <span className="who">{WHO[a.who]}</span>
              </div>
              <div className="grid g2" style={{ marginTop: 12 }}>
                <div><div className="over" style={{ fontSize: 10.5, marginBottom: 6 }}>Request</div><pre className="json" style={{ background: "#1B1B1B" }}>{a.req}</pre></div>
                <div><div className="over" style={{ fontSize: 10.5, marginBottom: 6 }}>Response</div><pre className="json">{r ? a.resp : "// waiting for the agent to reach this step"}</pre></div>
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}

function CrossTab({ c, done }) {
  return (
    <section>
      <div className="tile">
        <h4>Two sources must agree</h4>
        <p className="muted small" style={{ marginTop: 6 }}>If two independent views agree with each other but not with the paper, the paper is wrong.</p>
        {c.cross.map(([claim, a, b, doc, verdict]) => (
          <div key={claim} style={{ display: "grid", gridTemplateColumns: "140px 1fr 1fr 1fr", gap: 10, marginTop: 12, opacity: done ? 1 : .45 }}>
            <div style={{ fontWeight: 600, paddingTop: 12 }}>{claim}</div>
            {[a, b].map(x => <div key={x} style={{ background: "#fff", borderRadius: 12, padding: "12px 14px", fontSize: 13.5 }}>{x}</div>)}
            <div style={{ background: "#FFF4D6", borderRadius: 12, padding: "12px 14px", fontSize: 13.5 }}>{doc}</div>
            <div />
            <div style={{ gridColumn: "2 / 5", background: "#111", color: "#fff", borderRadius: 12, padding: "12px 14px", fontSize: 13.5 }}>{done ? verdict : "Run the agent to compare"}</div>
          </div>
        ))}
      </div>
      <div className="tbl" style={{ marginTop: 16 }}><table>
        <thead><tr><th>Line</th><th>The paper says</th><th>The building says</th></tr></thead>
        <tbody>
          {c.lines.map(l => <tr key={l[0]} className={done && l[3] === "bad" ? "bad" : ""}><td>{l[0]}</td><td className="num">{l[1]}</td><td className="num" style={{ fontWeight: 600 }}>{done ? l[2] : "—"}</td></tr>)}
        </tbody>
      </table></div>
    </section>
  );
}

function EvidenceTab({ S, c, step, done }) {
  const o = c.outcome, B = BUILDINGS[c.b], p = PARTIES[c.party];
  const files = ["document.json", "plan.md", ...c.apis.filter(a => a.svc !== "AI model").map(a => fileName(a.svc)), "cross_checks.json", "decision.md"];
  const record = {
    id: c.id, persona: c.persona, from: p.name, building: { name: B.name, costar_id: B.cs },
    checks: c.cross.map(x => ({ claim: x[0], verdict: x[4] })),
    decision: { status: o.status, [snake(o.a[0])]: o.a[1], [snake(o.b[0])]: o.b[1] },
    approved_by: S.review[c.id] || "waiting",
  };
  return (
    <section className="grid g12">
      <div className="tile">
        <h4>Evidence folder</h4>
        <div className="term" style={{ marginTop: 14 }}>
          <div><b>/evidence/{c.id.toLowerCase()}/</b></div>
          {files.map(f => <div key={f}>  {done ? "" : <span className="g">(pending) </span>}{f}</div>)}
        </div>
        <h4 style={{ marginTop: 18 }}>Audit log</h4>
        <div className="term" style={{ marginTop: 10 }}>
          {c.steps.slice(0, Math.max(0, step)).map((s, k) => <div key={k}><span className="g">{String(k + 1).padStart(2, "0")}</span> {WHO[s[0]]} · {s[1]}</div>)}
          {S.review[c.id] && <div><span className="g">--</span> Person · decision: {S.review[c.id]}</div>}
          {step < 1 && <span className="g">No events yet.</span>}
        </div>
      </div>
      <div className="tile">
        <div className="row between"><h4>decision.json</h4><div className="row">
          {done && <a className="small" style={{ textDecoration: "underline" }} href={`/api/claims/${c.id}/decision.json`}>Download JSON</a>}
          <button className="btn white sm" disabled={!done} onClick={() => window.open(`/api/claims/${c.id}/report`, "_blank", "noopener")}>Export report</button></div></div>
        <pre className="json" style={{ marginTop: 14, minHeight: 260 }}>{done ? J(record) : "// Run the agent to write the evidence file"}</pre>
      </div>
    </section>
  );
}

export default function ClaimDetail({ S, A, id }) {
  const c = S.all.find(x => x.id === id) || S.list[0];
  const [tab, setTab] = useState("run");
  if (!c) return null;
  const step = S.steps[c.id] ?? -1, st = S.status[c.id] || "ready", done = step >= c.steps.length, mine = S.current === c.id;
  const B = BUILDINGS[c.b], p = PARTIES[c.party];
  const reached = i => done || c.steps.some((s, k) => s[3] === i && k < step);
  const ctx = { S, A, c, step, done, mine, reached, setTab };
  return (
    <div className="wrapx">
      <div className="pagehead">
        <div className="over"><a onClick={() => A.go("claims")}>{PERSONAS[c.persona].short}</a> / {c.id}</div>
        <div className="row between" style={{ alignItems: "flex-end", marginTop: 10 }}>
          <div>
            <h1 className="h1">{c.title}</h1>
            <div className="row wrap" style={{ marginTop: 14 }}><Tag s={st} /><span className="muted">{p.name} ({p.role.toLowerCase()}) · {B.name}, {B.city} · <b style={{ color: "#000" }}>{fmt(c.amount)}</b></span></div>
          </div>
          <div className="row">
            <button className="btn gray" disabled={mine} onClick={() => A.reset(c.id)}>Reset</button>
            <button className="btn black" disabled={S.running || done} onClick={() => A.run(c.id)}>{mine ? "Checking…" : done ? "Checked" : "Run agent"}</button>
          </div>
        </div>
      </div>
      <div className="tabs">{TABS.map(([k, l]) => <button key={k} className={tab === k ? "on" : ""} onClick={() => setTab(k)}>{l}</button>)}</div>
      {tab === "run" && <RunTab {...ctx} />}
      {tab === "apis" && <ApisTab {...ctx} />}
      {tab === "cross" && <CrossTab {...ctx} />}
      {tab === "evidence" && <EvidenceTab {...ctx} />}
    </div>
  );
}
