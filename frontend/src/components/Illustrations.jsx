// Drawn stand-ins for aerial imagery, floor plans and the QR code (not real imagery).
import { BUILDINGS } from "../data";

const ROOF_OUTLINE = "70,50 300,50 300,120 250,120 250,190 70,190";
const TREES = [[30, 28], [24, 196], [372, 226], [14, 116], [44, 120]];

export function Aerial({ b, kind, show, big }) {
  const B = BUILDINGS[b] || BUILDINGS.wc;
  const units = kind === "hvac" ? 8 : B.ac;
  const hiUnits = kind === "hvac" && show;
  const outline = kind === "roof" || kind === "footprint";
  return (
    <svg viewBox="0 0 400 240" width="100%" preserveAspectRatio={big ? "xMaxYMid slice" : "xMidYMid meet"} className={big ? "bgimg" : ""} style={{ display: "block" }}>
      <rect width="400" height="240" fill="#4E5A47" />
      <rect x="0" y="206" width="400" height="34" fill="#5E6163" />
      {Array.from({ length: 12 }, (_, i) => <line key={i} x1={20 + i * 32} y1="221" x2={34 + i * 32} y2="221" stroke="#E9E3C5" strokeWidth="1.5" />)}
      <rect x="318" y="18" width="72" height="180" fill="#585C60" />
      {Array.from({ length: 9 }, (_, i) => <line key={i} x1="320" y1={28 + i * 19} x2="352" y2={28 + i * 19} stroke="#E2DECD" strokeWidth="1" />)}
      {TREES.map(([x, y], i) => <circle key={i} cx={x} cy={y} r="12" fill="#37512F" />)}
      <polygon points={ROOF_OUTLINE} fill="#B6B9BB" stroke="#8C9093" strokeWidth="3" />
      {Array.from({ length: units }, (_, i) => <rect key={i} x={92 + (i % 4) * 40} y={i < 4 ? 68 : 138} width="18" height="14" fill="#E6E8EA" stroke={hiUnits ? "#FFAA00" : "#777"} strokeWidth={hiUnits ? 2.5 : 1} />)}
      {show && outline && <polygon points={ROOF_OUTLINE} fill="rgba(255,170,0,.25)" stroke="#FFAA00" strokeWidth="3" strokeDasharray="900" style={{ animation: "draw 1.4s ease forwards" }} />}
      {show && kind === "parking" && <rect x="318" y="18" width="72" height="180" fill="rgba(255,170,0,.25)" stroke="#FFAA00" strokeWidth="3" />}
      {show && !big && (outline || kind === "hvac") && (
        <g>
          <rect x="80" y="102" width="160" height="24" rx="12" fill="#0A0A0A" />
          <text x="160" y="118" textAnchor="middle" fill="#FFAA00" fontSize="11.5" fontFamily="ui-monospace,monospace">{kind === "hvac" ? "8 units detected" : B.roof.toLocaleString() + " sq ft footprint"}</text>
        </g>
      )}
    </svg>
  );
}

const PLAN_LABELS = {
  apt: [["Apt 101", 0], ["Apt 102", 0], ["Apt 103", 0], ["Hallway", 1], ["Apt 104", 0], ["Stairs", 0], ["Apt 105", 0]],
  units: [["Unit 301", 1], ["Unit 302", 1], ["Unit 303", 1], ["Corridor", 0], ["Unit 304", 1], ["Unit 305", 0], ["Unit 306", 0]],
  office: [["Office 301", 1], ["Office 302", 1], ["Office 303", 1], ["Corridor", 1], ["Office 304", 1], ["Mechanical", 0], ["Office 305", 1]],
};
const PLAN_RECTS = [[10, 10, 120, 90], [130, 10, 120, 90], [250, 10, 140, 90], [10, 100, 380, 40], [10, 140, 160, 90], [170, 140, 100, 90], [270, 140, 120, 90]];

export function FloorPlan({ show, mode }) {
  const labels = PLAN_LABELS[mode] || PLAN_LABELS.office;
  return (
    <svg viewBox="0 0 400 240" width="100%" style={{ display: "block", background: "#fff" }}>
      {PLAN_RECTS.map(([x, y, w, h], i) => {
        const [name, on] = labels[i], lit = show && on;
        return (
          <g key={i}>
            <rect x={x} y={y} width={w} height={h} fill={lit ? "rgba(255,170,0,.35)" : "#fff"} stroke="#0A0A0A" strokeWidth="1.5" />
            <text x={x + w / 2} y={y + h / 2 + 4} textAnchor="middle" fill={lit ? "#0A0A0A" : "#888"} fontSize="11" fontFamily="Helvetica,Arial">{name}</text>
          </g>
        );
      })}
    </svg>
  );
}

// Decorative QR-style grid with three finder squares.
const N = 21;
const inFinder = (r, c, r0, c0) => r >= r0 && r < r0 + 7 && c >= c0 && c < c0 + 7 &&
  (r === r0 || r === r0 + 6 || c === c0 || c === c0 + 6 || (r >= r0 + 2 && r <= r0 + 4 && c >= c0 + 2 && c <= c0 + 4));
const inZone = (r, c, r0, c0) => r >= r0 - 1 && r < r0 + 8 && c >= c0 - 1 && c < c0 + 8;
const FINDERS = [[0, 0], [0, 14], [14, 0]];
const QR_CELLS = Array.from({ length: N * N }, (_, i) => {
  const r = Math.floor(i / N), c = i % N;
  if (FINDERS.some(([r0, c0]) => inZone(r, c, r0, c0))) return FINDERS.some(([r0, c0]) => inFinder(r, c, r0, c0));
  return ((r * 31 + c * 17 + r * c * 7) % 11) < 5;
});

export function QR() {
  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(21,1fr)", width: 140, height: 140, padding: 8, background: "#fff", borderRadius: 12 }}>
      {QR_CELLS.map((on, i) => <i key={i} style={{ background: on ? "#000" : "transparent" }} />)}
    </div>
  );
}
