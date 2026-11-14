// Shared formatting, labels and small UI pieces.

export const J = o => JSON.stringify(o, null, 2);
export const fmt = n => "$" + Math.round(n).toLocaleString();
export const money = v => typeof v === "number" ? fmt(v) : v;
export const sqft = n => n.toLocaleString() + " sq ft";

export const TAG = {
  approved: ["t-paid", "Verified"], partial: ["t-partial", "Partly verified"], reduced: ["t-partial", "Reduced"],
  denied: ["t-blocked", "Denied"], blocked: ["t-blocked", "Blocked"], ready: ["t-ready", "Waiting"],
  running: ["t-running", "Checking"], ok: ["t-paid", "Approved"], rejected: ["t-blocked", "Rejected"], sent: ["t-running", "Message sent"],
};
export const WHO = { coordinator: "Coordinator", roof: "Roof inspector", interior: "Interior inspector", records: "Records clerk", rules: "Rules + math" };
export const COL = { green: "var(--green)", amber: "var(--amberDeep)", red: "var(--red)", gray: "var(--ink3)" };
export const LAYER = { CoStar: "Building record", Vexcel: "From above", Matterport: "Inside (3D scan)", "Tiger Data": "History", "AI model": "Reads documents" };
export const FINAL = ["approved", "partial", "reduced", "denied", "blocked"];
export const NEEDS = ["partial", "reduced", "denied", "blocked"];

export const isLayer = s => s === "CoStar" || s === "Vexcel" || s === "Matterport";
export const aerialKind = c => c.kind === "hvac" ? "hvac" : c.kind === "parking" ? "parking" : "roof";
export const sumNum = (arr, k) => arr.reduce((t, c) => t + (typeof c.outcome[k][1] === "number" ? c.outcome[k][1] : 0), 0);

export const Tag = ({ s }) => <span className={"tag " + TAG[s][0]}><i />{TAG[s][1]}</span>;
export const Flag = ({ t = "Sample data" }) => <span className="flag">{t}</span>;

const LAYER_STYLE = { background: "#FFF4D6", color: "#8A5A00", border: "1px solid #FFAA00" };
const TIGER_STYLE = { background: "#E1F5EE", color: "#085041" };
const OTHER_STYLE = { background: "var(--g1)", color: "var(--ink2)" };
export const SvcChip = ({ s }) => <span className="tag" style={isLayer(s) ? LAYER_STYLE : s === "Tiger Data" ? TIGER_STYLE : OTHER_STYLE}>{s}</span>;

const CHECK_PATH = { done: "M2 5.2 4.2 7.4 8 3", fail: "M3 3l4 4M7 3 3 7" };
export function Check({ res }) {
  return (
    <svg width="10" height="10" viewBox="0 0 10 10">
      <path d={CHECK_PATH[res] || "M5 2.5v3.2M5 7.4v.1"} stroke={res === "warn" ? "#000" : "#fff"} strokeWidth="1.8" fill="none" strokeLinecap="round" />
    </svg>
  );
}

export const Head = ({ over, title, lede, right }) => (
  <div className="pagehead row between" style={{ alignItems: "flex-end" }}>
    <div><div className="over">{over}</div><h1 className="h1">{title}</h1>{lede && <p className="lede">{lede}</p>}</div>
    {right}
  </div>
);
