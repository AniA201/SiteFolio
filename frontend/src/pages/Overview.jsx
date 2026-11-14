import { useState } from "react";
import { META, PARTIES, PERSONAS } from "../data";
import { COL, FINAL, NEEDS, SvcChip, Tag, fmt, money, sumNum } from "../lib";
import { Aerial, FloorPlan } from "../components/Illustrations";

// Hero stories per persona: [title, text, claim to open, building drawn behind it]
const STORIES = {
  owner: [
    ["The roof that shrank", "A roofer billed 14,500 sq ft. The building record and the aerial image both say 9,820.", "CLM-2207", "wc"],
    ["Twelve units, eight on the roof", "The image from above and the 3D scan inside both count 8 AC units. The bill says 12.", "CLM-2214", "wc"],
    ["\"We changed banks.\"", "A bill asked to pay a new account. Plumbline paid $0 and opened a review.", "CLM-2223", "wc"],
  ],
  reviewer: [
    ["Rent up for a roof a third smaller", "A landlord claimed 10,800 sq ft of roof. The building has 7,200. Tenants would overpay for 5 years.", "RSO-3104", "wca"],
    ["The same roof, charged twice", "Tenants already pay for this roof until 2029. The history check catches it.", "RSO-3104", "vg"],
  ],
  lender: [
    ["Floor 3 isn't finished yet", "The builder asked for $400,000. The latest scan shows 9 of 12 units done.", "DRW-0412", "ml"],
    ["Release money for real progress", "Check the building from your desk before every loan payment.", "DRW-0412", "ml"],
  ],
};

const VIEWS = [
  ["CoStar", "The record", "What is this building? Size, floors, units, age.", <Aerial b="wc" kind="footprint" show={false} />],
  ["Vexcel", "From above", "How big is the roof? How many AC units? How big is the lot?", <Aerial b="wc" kind="roof" show />],
  ["Matterport", "Inside", "How big are the rooms? Which rooms exist? Walk the live 3D tour.", <FloorPlan show />],
];

function statTiles(persona, done, waiting, status) {
  if (persona === "owner") return [
    ["Held with proof", fmt(sumNum(done.filter(c => c.outcome.status === "partial"), "b")), "overbilling held back", "amber"],
    ["Fraud stopped", fmt(sumNum(done.filter(c => c.outcome.status === "blocked"), "b")), "fake bank changes", "red"],
    ["Paid correctly", fmt(sumNum(done, "a")), done.length + " bills verified", "ink"],
    ["Waiting", waiting.length, "bills to check", "ink"],
  ];
  if (persona === "reviewer") return [
    ["Tenant savings", "$" + done.reduce((t, c) => t + (c.rent ? (c.rent.claimed - c.rent.verified) * c.rent.units : 0), 0).toFixed(0) + "/mo", "across all units", "amber"],
    ["Reduced or denied", done.filter(c => ["reduced", "denied"].includes(status[c.id])).length, "applications", "red"],
    ["Checked", done.length, "applications", "ink"],
    ["Waiting", waiting.length, "to check", "ink"],
  ];
  return [
    ["Released", fmt(sumNum(done, "a")), "for verified work", "ink"],
    ["Held until done", fmt(sumNum(done, "b")), "unfinished work", "amber"],
    ["Checked", done.length, "loan requests", "ink"],
    ["Waiting", waiting.length, "to check", "ink"],
  ];
}

export default function Overview({ S, A }) {
  const { list, status, persona } = S;
  const [slide, setSlide] = useState(0);
  const stories = (META.stories || STORIES)[persona];
  const at = slide % stories.length;
  const [title, text, claimId, building] = stories[at];
  const done = list.filter(c => FINAL.includes(status[c.id]));
  const waiting = list.filter(c => !status[c.id] || status[c.id] === "ready");
  const attention = done.filter(c => NEEDS.includes(status[c.id]) && !S.review[c.id]);
  const tiles = statTiles(persona, done, waiting, status);
  const tone = c => c === "red" && done.length ? "var(--red)" : c === "amber" && done.length ? "var(--amberDeep)" : "#000";

  return (
    <div className="wrapx" style={{ paddingTop: 20 }}>
      <div className="hero">
        <Aerial b={building} kind="roof" show big />
        <div className="shade" />
        <div className="in">
          <div className="over" style={{ color: "rgba(255,255,255,.75)" }}>{PERSONAS[persona].label} · {PERSONAS[persona].org}</div>
          <h1 className="h1" style={{ fontSize: 64, color: "#fff" }}>{title}</h1>
          <p className="lede" style={{ color: "rgba(255,255,255,.85)" }}>{text}</p>
          <div className="row wrap" style={{ marginTop: 28 }}>
            <button className="btn white" disabled={!waiting.length || S.running} onClick={A.runAll}>{S.running ? "Checking…" : waiting.length ? `Check ${waiting.length} waiting` : "All checked"}</button>
            <button className="btn glass" onClick={() => A.go("claim", claimId)}>See this check</button>
          </div>
        </div>
        <div className="row" style={{ position: "absolute", bottom: 24, left: 64, right: 24, justifyContent: "space-between" }}>
          <div className="dots">{stories.map((_, i) => <i key={i} className={i === at ? "on" : ""} onClick={() => setSlide(i)} />)}</div>
          <div className="row">
            <button className="arrow" onClick={() => setSlide((slide + stories.length - 1) % stories.length)}>←</button>
            <button className="arrow" onClick={() => setSlide((slide + 1) % stories.length)}>→</button>
          </div>
        </div>
      </div>

      <section className="grid g4" style={{ marginTop: 16 }}>
        {tiles.map(([label, value, desc, c]) => (
          <div className="tile" key={label}>
            <div className="over">{label}</div>
            <div className="stat num" style={{ color: tone(c) }}>{value}</div>
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
                <div style={{ fontWeight: 600 }}>{PARTIES[c.party].name} · {c.title}</div>
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

      <section className="giant">
        <div className="w">3 VIEWS</div>
        <p className="lede" style={{ margin: "6px auto 28px", textAlign: "center" }}>Every claim is checked against three views of the same building. When two views agree with each other but not with the paper, the paper is wrong.</p>
      </section>
      <section className="grid g3" style={{ paddingTop: 0 }}>
        {VIEWS.map(([svc, heading, desc, img]) => (
          <div key={svc} className="tile" style={{ padding: 0, overflow: "hidden" }}>
            <div style={{ background: "#fff" }}>{img}</div>
            <div style={{ padding: 22 }}>
              <SvcChip s={svc} />
              <h4 style={{ fontSize: 22, marginTop: 10 }}>{heading}</h4>
              <p className="muted" style={{ lineHeight: 1.5 }}>{desc}</p>
            </div>
          </div>
        ))}
      </section>
    </div>
  );
}
