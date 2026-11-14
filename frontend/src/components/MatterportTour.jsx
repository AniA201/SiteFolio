// Live Matterport 3D tour of the scanned space, with the room areas the Model API measured.
import { useState } from "react";
import { META } from "../data";

const SQFT_PER_SQM = 10.7639;

// Read the model(s) from a claim's Matterport call record. Returns [] for sample data.
export function toursFromCall(call) {
  if (!call) return [];
  try {
    const resp = JSON.parse(call.resp);
    return (Array.isArray(resp) ? resp : [resp]).filter(m => m && m.model);
  } catch {
    return [];
  }
}

// Plain Showcase embed. Adding applicationKey makes Showcase wait for an SDK connection from this page, so it is
// only added once the SDK is wired in (withSdk).
export function tourUrl(modelId, withSdk = false) {
  const p = new URLSearchParams({ m: modelId, play: "1", qs: "1", brand: "0", help: "0", title: "0" });
  if (withSdk && META.matterport_sdk_key) p.set("applicationKey", META.matterport_sdk_key);
  return `https://my.matterport.com/show/?${p}`;
}

export default function MatterportTour({ tours, show }) {
  const [sel, setSel] = useState(0);
  const [open, setOpen] = useState(false);
  const t = tours[Math.min(sel, tours.length - 1)];
  const rooms = (t.rooms || []).filter(r => r.areaFloor_m2).map(r => ({ label: r.label || "Unlabelled", sqft: r.areaFloor_m2 * SQFT_PER_SQM }))
    .sort((a, b) => b.sqft - a.sqft);
  const pick = i => { setSel(i); setOpen(false); };

  return (
    <div>
      {tours.length > 1 && (
        <div className="row wrap" style={{ gap: 6, marginTop: 12 }}>
          {tours.map((x, i) => (
            <button key={x.model} title={x.name} className={"btn sm " + (i === sel ? "black" : "gray")} style={{ height: 32, padding: "0 12px", fontSize: 12.5 }} onClick={() => pick(i)}>
              {label(tours, i)}
            </button>
          ))}
        </div>
      )}
      <div className="ph" style={{ marginTop: 12, position: "relative", aspectRatio: "4 / 3", background: "#0E0E0E" }}>
        {open ? (
          <iframe key={t.model} title={`3D tour: ${t.name}`} src={tourUrl(t.model)} allow="xr-spatial-tracking; fullscreen" allowFullScreen
            style={{ position: "absolute", inset: 0, width: "100%", height: "100%", border: 0 }} />
        ) : (
          <div style={{ position: "absolute", inset: 0, display: "grid", placeItems: "center", textAlign: "center", color: "#fff", padding: 20 }}>
            <div>
              <div className="over" style={{ color: "rgba(255,255,255,.6)" }}>Matterport 3D scan</div>
              <div style={{ fontSize: 20, fontWeight: 600, margin: "8px 0 16px", letterSpacing: "-.3px" }}>{t.name}</div>
              <button className="btn white sm" disabled={!show} onClick={() => setOpen(true)}>▶ Walk the live 3D tour</button>
              {!show && <div className="small" style={{ color: "rgba(255,255,255,.6)", marginTop: 10 }}>Opens once the interior inspector reaches this step</div>}
            </div>
          </div>
        )}
      </div>
      <div style={{ marginTop: 12, opacity: show ? 1 : .45 }}>
        {rooms.slice(0, 8).map((r, i) => (
          <div key={i} className="row between small" style={{ padding: "5px 0", borderTop: i ? "1px solid var(--g2)" : 0 }}>
            <span>{r.label}</span><span className="num">{Math.round(r.sqft).toLocaleString()} sq ft</span>
          </div>
        ))}
        {rooms.length > 8 && <div className="muted small" style={{ paddingTop: 4 }}>+ {rooms.length - 8} more rooms</div>}
        <div className="row between" style={{ padding: "8px 0 0", borderTop: "1px solid var(--g3)", marginTop: 4, fontWeight: 600 }}>
          <span>Measured floor area</span><span className="num">{Math.round(t.total_sq_ft).toLocaleString()} sq ft</span>
        </div>
      </div>
    </div>
  );
}

function label(tours, i) {
  const name = shortName(tours[i].name);
  const same = tours.filter(t => shortName(t.name) === name);
  return same.length > 1 ? `${name} (${same.indexOf(tours[i]) + 1})` : name;
}

function shortName(name) {
  const plan = name.match(/Plan\s+([0-9A-Z]{2})\b/) || name.match(/^([A-Z]\d+)\b/);
  return plan ? plan[1] : name.length > 18 ? name.slice(0, 17) + "…" : name;
}
