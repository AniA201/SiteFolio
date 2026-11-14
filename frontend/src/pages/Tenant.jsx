import { BUILDINGS } from "../data";
import { Check, FINAL, Flag, Head } from "../lib";
import { Aerial, FloorPlan } from "../components/Illustrations";

export default function Tenant({ S, A, id }) {
  const ready = S.all.filter(c => c.persona === "reviewer" && FINAL.includes(S.status[c.id]));
  const c = ready.find(x => x.id === id) || ready[0];
  if (!c) return (
    <div className="wrapx">
      <Head over="For tenants" title="Tenant view" lede="A plain-language page tenants get after a reviewer checks a rent increase. Switch to Reviewer and check an application first."
        right={<button className="btn black" onClick={() => { A.setPersona("reviewer"); A.go("claims"); }}>Go to applications</button>} />
    </div>
  );
  const B = BUILDINGS[c.b], r = c.rent;
  const hasScan = c.apis.some(a => a.svc === "Matterport");
  return (
    <div className="wrapx">
      <div className="row wrap" style={{ paddingTop: 32, gap: 8 }}>
        {ready.map(x => <button key={x.id} className={"btn sm " + (x.id === c.id ? "black" : "gray")} onClick={() => A.go("tenant", x.id)}>{BUILDINGS[x.b].name}</button>)}
      </div>
      <div className="grid g2" style={{ alignItems: "center", gap: 56, paddingTop: 24 }}>
        <div>
          <div className="over">For tenants of {B.name}</div>
          <h1 className="h1" style={{ fontSize: 64, letterSpacing: "-3px" }}>Your rent increase should be {r.verified ? "$" + r.verified.toFixed(2) : "$0"} a month.</h1>
          <p className="lede">Your landlord asked for <b>${r.claimed.toFixed(2)}</b> a month per apartment for {c.title.toLowerCase()}. We checked the building itself.</p>
          <div className="tile" style={{ marginTop: 24 }}>
            <h4>What we found</h4>
            {c.cross.map(x => (
              <div key={x[0]} className="chk" style={{ alignItems: "flex-start" }}>
                <span className="dot fail" style={{ marginTop: 2 }}><Check res="fail" /></span>
                <div><b>{x[0]}:</b> {x[4]}</div>
              </div>
            ))}
            <p className="muted small" style={{ marginTop: 10 }}>Sources: building record (CoStar), aerial image (Vexcel){hasScan ? ", 3D scan (Matterport)" : ""}, past rent records.</p>
          </div>
          <div className="tile dark" style={{ marginTop: 16 }}>
            <div className="over" style={{ color: "rgba(255,255,255,.6)" }}>What this means for you</div>
            <div className="stat num" style={{ color: "var(--amber)" }}>${((r.claimed - r.verified) * r.months).toFixed(0)}</div>
            <p style={{ color: "rgba(255,255,255,.75)" }}>less over {r.months / 12} years, per apartment. Status: {S.review[c.id] ? "reviewer decision recorded" : "waiting for the reviewer's final decision"}.</p>
          </div>
          <div className="row wrap" style={{ marginTop: 18 }}>
            <button className="btn black sm">Share with my tenant association</button>
            <button className="btn gray sm">Download the proof</button>
          </div>
        </div>
        <div className="grid" style={{ gap: 16 }}>
          <div className="tile" style={{ padding: 0, overflow: "hidden" }}>
            <Aerial b={c.b} kind="roof" show />
            <div style={{ padding: 18 }}><b>Roof from above:</b> {B.roof.toLocaleString()} sq ft</div>
          </div>
          {hasScan && (
            <div className="tile" style={{ padding: 0, overflow: "hidden" }}>
              <FloorPlan show mode="apt" />
              <div style={{ padding: 18 }}><b>Hallways, measured inside:</b> 1,920 sq ft</div>
            </div>
          )}
        </div>
      </div>
      <div style={{ marginTop: 16 }}><Flag t="Sample building · plain-language page, not legal advice" /></div>
    </div>
  );
}
