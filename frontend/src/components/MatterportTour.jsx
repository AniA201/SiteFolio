// Live Matterport 3D tour of the scanned space, with a pin on every room the Model API measured.
// The tour connects through the Showcase SDK (browser-safe key from /api/meta); if it cannot connect, the plain
// public embed is shown instead so the tour itself still works.
import { useEffect, useRef, useState } from "react";
import { setupSdk } from "@matterport/sdk";
import { META } from "../data";

const SQFT_PER_SQM = 10.7639;
const AMBER = { r: 1, g: 0.667, b: 0 };
const QUERY = { play: 1, qs: 1, brand: 0, help: 0, title: 0 };
const CONNECT_TIMEOUT_MS = 30000;

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

export function tourUrl(modelId) {
  return `https://my.matterport.com/show/?${new URLSearchParams({ m: modelId, ...QUERY })}`;
}

const measuredRooms = t => (t.rooms || []).filter(r => r.areaFloor_m2)
  .map(r => ({ id: r.id, label: r.label || "Room", sqft: r.areaFloor_m2 * SQFT_PER_SQM }))
  .sort((a, b) => b.sqft - a.sqft);

const withTimeout = (p, ms) => Promise.race([p, new Promise((_, no) => setTimeout(() => no(new Error("timeout")), ms))]);

// Wait for Showcase to finish loading, then read its rooms (keyed by the viewer's own room ids).
async function sdkRooms(sdk) {
  await sdk.App.state.waitUntil(s => s.phase === sdk.App.Phase.PLAYING);
  return new Promise(resolve => {
    let done = false;
    const sub = sdk.Room.data.subscribe({
      onCollectionUpdated(coll) {
        if (done || !Object.keys(coll).length) return;
        done = true;
        resolve({ ...coll });
        sub?.cancel?.();
      },
    });
    setTimeout(() => { if (!done) { done = true; resolve({}); } }, 8000);
  });
}

async function placePins(sdk, rooms) {
  const viewerRooms = await sdkRooms(sdk);
  let idMap = {};
  try { idMap = await sdk.Room.Conversion.createIdMap(); } catch { /* older viewers use the same ids */ }
  const pins = [];
  for (const r of rooms) {
    const v = viewerRooms[r.id] || viewerRooms[idMap[r.id]];
    if (!v) continue;
    pins.push({
      room: r,
      descriptor: {
        label: `${r.label} · ${Math.round(r.sqft).toLocaleString()} sq ft`,
        description: "Floor area measured by Matterport's Model API. This is the number SiteFolio's check used.",
        anchorPosition: { x: v.center.x, y: v.bounds.min.y + 0.05, z: v.center.z },
        stemVector: { x: 0, y: 1.1, z: 0 },
        color: AMBER,
      },
    });
  }
  const ids = pins.length ? await sdk.Tag.add(...pins.map(p => p.descriptor)) : [];
  return Object.fromEntries(pins.map((p, i) => [p.room.id, ids[i]]));
}

function Viewer({ tour, rooms, onStatus, sdkRef, onPins }) {
  const box = useRef(null);
  const [fallback, setFallback] = useState(!META.matterport_sdk_key);

  useEffect(() => {
    if (fallback) return;
    let alive = true, sdk = null;
    const container = box.current;
    onStatus("Connecting to the 3D tour…");
    withTimeout(setupSdk(META.matterport_sdk_key, {
      container, space: tour.model, iframeQueryParams: QUERY,
      iframeAttributes: { title: `3D tour: ${tour.name}`, allow: "xr-spatial-tracking; fullscreen", allowfullscreen: true,
        style: "position:absolute;inset:0;width:100%;height:100%;border:0" },
    }), CONNECT_TIMEOUT_MS)
      .then(async s => {
        sdk = s;
        if (!alive) return s.disconnect?.();
        sdkRef.current = s;
        onStatus("Placing room pins…");
        const pins = await withTimeout(placePins(s, rooms), CONNECT_TIMEOUT_MS);
        if (!alive) return;
        onPins(pins);
        const n = Object.keys(pins).length;
        onStatus(n ? `${n} measured room${n > 1 ? "s" : ""} pinned in the tour` : "Tour loaded; the viewer did not report room bounds to pin");
      })
      .catch(() => {
        if (!alive) return;
        sdk?.disconnect?.();
        container.replaceChildren();
        setFallback(true);
        onStatus("Showing the plain tour (the SDK could not connect)");
      });
    return () => {
      alive = false;
      sdkRef.current = null;
      sdk?.disconnect?.();
      container?.replaceChildren();
    };
  }, [tour.model, fallback]);

  if (fallback) {
    return <iframe title={`3D tour: ${tour.name}`} src={tourUrl(tour.model)} allow="xr-spatial-tracking; fullscreen" allowFullScreen
      style={{ position: "absolute", inset: 0, width: "100%", height: "100%", border: 0 }} />;
  }
  return <div ref={box} style={{ position: "absolute", inset: 0 }} />;
}

export default function MatterportTour({ tours, show }) {
  const [sel, setSel] = useState(0);
  const [open, setOpen] = useState(false);
  const [status, setStatus] = useState("");
  const [pins, setPins] = useState({});
  const sdkRef = useRef(null);
  const t = tours[Math.min(sel, tours.length - 1)];
  const rooms = measuredRooms(t);
  const pick = i => { setSel(i); setOpen(false); setPins({}); setStatus(""); };
  const goTo = id => { const tag = pins[id]; if (tag && sdkRef.current) sdkRef.current.Tag.open(tag).catch(() => {}); };

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
          <Viewer key={t.model} tour={t} rooms={rooms} onStatus={setStatus} sdkRef={sdkRef} onPins={setPins} />
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
      {open && status && <div className="small" style={{ marginTop: 8, color: "var(--amberDeep)", fontWeight: 600 }}>{status}</div>}
      <div style={{ marginTop: 10, opacity: show ? 1 : .45 }}>
        {rooms.slice(0, 8).map((r, i) => {
          const pinned = !!pins[r.id];
          return (
            <div key={r.id || i} className="row between small" onClick={() => pinned && goTo(r.id)}
              style={{ padding: "5px 0", borderTop: i ? "1px solid var(--g2)" : 0, cursor: pinned ? "pointer" : "default" }}>
              <span>{pinned && <span style={{ color: "#FFAA00", marginRight: 6 }}>●</span>}{r.label}</span>
              <span className="num">{Math.round(r.sqft).toLocaleString()} sq ft</span>
            </div>
          );
        })}
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
