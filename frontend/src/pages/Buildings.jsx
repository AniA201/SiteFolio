// Every building in the CoStar kit: search, then open one to see its record, what the kit knows about it, the roof
// from above (Vexcel, live) and its Matterport scans with the 3D tour.
import { useEffect, useRef, useState } from "react";
import { Flag, Head, SvcChip, sqft } from "../lib";
import Dossier from "../components/Dossier";
import MatterportTour from "../components/MatterportTour";
import { RealAerial } from "./ClaimDetail";

const CITIES = [["", "All"], ["Houston", "Houston"], ["Los Angeles", "Los Angeles"]];
const TYPES = ["", "Multifamily", "Office", "Industrial", "GeneralRetail", "Flex", "Hospitality"];
const label = t => t ? t.replace(/([a-z])([A-Z])/g, "$1 $2") : "Any type";
const getJSON = url => fetch(url).then(async r => { const b = await r.json().catch(() => ({})); if (!r.ok) throw new Error(b.detail || `HTTP ${r.status}`); return b; });

function Search({ A }) {
  const [q, setQ] = useState("");
  const [city, setCity] = useState("");
  const [type, setType] = useState("");
  const [scanned, setScanned] = useState(true);
  const [res, setRes] = useState({ results: [], total: 0, error: "" });
  useEffect(() => {
    const t = setTimeout(() => {
      const p = new URLSearchParams({ q, limit: "40", ...(city && { city }), ...(type && { type }), ...(scanned && { scanned: "true" }) });
      getJSON(`/api/kit/search?${p}`).then(r => setRes({ ...r, error: "" })).catch(e => setRes({ results: [], total: 0, error: e.message }));
    }, 180);
    return () => clearTimeout(t);
  }, [q, city, type, scanned]);
  return (
    <div className="wrapx">
      <Head over="CoStar data kit" title="Buildings" lede={`Every building in the kit for Houston and Los Angeles${res.total ? ` (${res.total.toLocaleString()})` : ""}. Open one to see its record, what CoStar knows about it, the roof from above and its 3D scans.`} />
      <div className="row wrap" style={{ gap: 10, marginBottom: 14 }}>
        <input id="kit-q" className="in" style={{ maxWidth: 380 }} placeholder="Search by name, address or CoStar id" value={q} onChange={e => setQ(e.target.value)} />
        <div className="tabs">{CITIES.map(([k, l]) => <button key={l} className={city === k ? "on" : ""} onClick={() => setCity(k)}>{l}</button>)}</div>
        <select id="kit-type" className="in" style={{ width: 170 }} value={type} onChange={e => setType(e.target.value)}>{TYPES.map(t => <option key={t} value={t}>{label(t)}</option>)}</select>
        <label className="row small" style={{ gap: 8, cursor: "pointer" }}><button type="button" className={"switch" + (scanned ? " on" : "")} onClick={() => setScanned(!scanned)} aria-pressed={scanned} />Has 3D scans</label>
      </div>
      {res.error && <div className="tile"><h4>Search isn't available</h4><p className="muted">{res.error}</p></div>}
      {!res.error && (
        <div className="tbl"><table>
          <thead><tr><th>Building</th><th>City</th><th>Type</th><th className="r">Size</th><th className="r">Floors</th><th className="r">Units</th><th>CoStar kit</th></tr></thead>
          <tbody>
            {res.results.map(b => (
              <tr key={b.id} className="click" onClick={() => A.go("building", b.id)}>
                <td><b>{b.name}</b><div className="muted small">{b.address} · <span className="mono">{b.id}</span></div></td>
                <td>{b.city}</td><td>{label(b.type)}</td>
                <td className="r num">{b.gba_sqft ? sqft(Math.round(b.gba_sqft)) : "—"}</td>
                <td className="r num">{b.stories || "—"}</td><td className="r num">{b.units || "—"}</td>
                <td><div className="row wrap" style={{ gap: 4 }}>
                  {b.models > 0 && <span className="tag t-ready">{b.models} scan{b.models > 1 ? "s" : ""}</span>}
                  {b.has_rents && <span className="tag t-ready">rents</span>}
                  {b.tenants > 0 && <span className="tag t-ready">{b.tenants} tenants</span>}
                </div></td>
              </tr>
            ))}
            {!res.results.length && <tr><td colSpan={7} className="muted">No buildings match.</td></tr>}
          </tbody>
        </table></div>
      )}
    </div>
  );
}

function Scans({ ids }) {
  const [models, setModels] = useState(ids.slice(0, 12).map(id => ({ id, name: id })));
  const [tour, setTour] = useState(null);
  const [error, setError] = useState("");
  useEffect(() => {
    ids.slice(0, 12).forEach((id, i) => getJSON(`/api/data/matterport/models/${id}`)
      .then(m => setModels(ms => ms.map((x, k) => k === i ? { id, name: m.name || id } : x))).catch(() => {}));
  }, [ids.join(",")]);
  const open = m => {
    setError("");
    getJSON(`/api/data/matterport/models/${m.id}/rooms`).then(r => setTour({
      model: m.id, name: m.name, total_sq_ft: r.total_sqft,
      rooms: r.rooms.map(x => ({ id: x.id, label: x.label, ...(x.area_sqm ? { areaFloor_m2: x.area_sqm } : {}) })),
    })).catch(e => setError(e.message));
  };
  return (
    <div>
      <div className="row wrap" style={{ gap: 6, marginTop: 12 }}>
        {models.map(m => <button key={m.id} className={"btn sm " + (tour?.model === m.id ? "black" : "gray")} style={{ height: 32, padding: "0 12px", fontSize: 12.5 }} onClick={() => open(m)}>{m.name.length > 26 ? m.name.slice(0, 25) + "…" : m.name}</button>)}
      </div>
      {error && <p className="small" style={{ color: "var(--red)" }}>{error}</p>}
      {tour ? <MatterportTour key={tour.model} tours={[tour]} show /> : <p className="muted small" style={{ marginTop: 10 }}>Pick a scan to measure its rooms and walk the 3D tour.</p>}
    </div>
  );
}

function Detail({ A, id }) {
  const [b, setB] = useState(null);
  const [error, setError] = useState("");
  const [upload, setUpload] = useState({ busy: false, error: "" });
  const picker = useRef(null);
  useEffect(() => { getJSON(`/api/kit/buildings/${id}`).then(setB).catch(e => setError(e.message)); }, [id]);
  const send = file => {
    if (!file) return;
    setUpload({ busy: true, error: "" });
    A.upload(file, id).catch(e => setUpload({ busy: false, error: e.message }));
  };
  if (error) return <div className="wrapx"><Head over="CoStar data kit" title="Building not found" lede={error} right={<button className="btn gray" onClick={() => A.go("buildings")}>Back to search</button>} /></div>;
  if (!b) return <div className="wrapx"><Head over="CoStar data kit" title="Loading…" /></div>;
  const v = b.vexcel, d = b.dossier || {}, apt = d.apartments, ten = d.tenants;
  const aerial = v && b.lat ? { id: b.id, name: b.name, lat: b.lat, lon: b.lon, roof: v.footprint_sqft, ac: v.ac_units } : null;
  return (
    <div className="wrapx">
      <div className="pagehead">
        <div className="over"><a onClick={() => A.go("buildings")}>Buildings</a> / CoStar {b.id}</div>
        <div className="row between wrap" style={{ alignItems: "flex-end", marginTop: 10 }}>
          <div><h1 className="h1">{b.name}</h1><div className="muted" style={{ marginTop: 10 }}>{b.address}, {b.city}, {b.state} · {label(b.type)}{b.status !== "Existing" ? ` · ${b.status}` : ""}</div></div>
          <div style={{ textAlign: "right" }}>
            <input ref={picker} type="file" accept=".pdf,.txt,.eml,.md" hidden onChange={e => { send(e.target.files?.[0]); e.target.value = ""; }} />
            <button className="btn black" disabled={upload.busy} onClick={() => picker.current?.click()}>{upload.busy ? "Reading the bill…" : "Check a bill for this building"}</button>
            {upload.error && <div className="small" style={{ color: "var(--red)", marginTop: 8, maxWidth: 360 }}>{upload.error}</div>}
          </div>
        </div>
      </div>
      <section className="grid g3" style={{ alignItems: "start" }}>
        <div className="tile">
          <div className="row between"><h4>Building record</h4><SvcChip s="CoStar" /></div>
          <div className="row wrap" style={{ gap: 26, marginTop: 14 }}>
            {[["Size", b.gba_sqft ? sqft(Math.round(b.gba_sqft)) : "—"], ["Floors", b.stories || "—"], ...(b.units ? [["Units", b.units]] : []), ["Built", b.year_built || "—"]].map(([l, x]) =>
              <div key={l}><div className="muted small">{l}</div><div style={{ fontWeight: 600 }}>{x}</div></div>)}
          </div>
          <Dossier d={{ ...d, ...(apt && { apartments: { ...apt, plans: apt.plans.length } }), ...(ten && { tenants: { count: ten.count, occupied_sqft: ten.occupied_sqft, top: ten.list.slice(0, 5) } }) }} />
        </div>
        <div className="tile">
          <div className="row between"><h4>From above</h4><SvcChip s="Vexcel" /></div>
          {aerial ? <div className="ph" style={{ marginTop: 14 }}><RealAerial B={aerial} show /></div> : <p className="muted small">{b.vexcel_error || "No Vexcel parcel at this location."}</p>}
          {v && <div className="small" style={{ marginTop: 10, lineHeight: 1.7 }}>
            Roof {v.roof_shape || "unknown"}{v.roof_material ? `, ${v.roof_material}` : ""} · footprint {sqft(v.footprint_sqft)}{v.structures > 1 ? ` (${v.structures} structures, ${sqft(v.total_footprint_sqft)} total)` : ""}<br />
            {v.ac_units} rooftop AC units · condition {v.roof_condition ?? "—"} · {v.collection}
            {b.roof_cross_check && <div className="receipt" style={{ background: "#fff" }}>CoStar floor plate {sqft(b.roof_cross_check.floor_plate_sqft)} vs Vexcel roof {sqft(b.roof_cross_check.roof_sqft)} ({b.roof_cross_check.basis}): {b.roof_cross_check.agreement_pct <= 15 ? `agree within ${b.roof_cross_check.agreement_pct}%` : `differ by ${b.roof_cross_check.agreement_pct}%, so roof claims here go to a person`}</div>}
            {b.roof_surface && <div className="receipt" style={{ background: "#fff" }}>{b.roof_surface.formula}</div>}
          </div>}
        </div>
        <div className="tile">
          <div className="row between"><h4>Inside · 3D scans</h4><SvcChip s="Matterport" /></div>
          {b.model_ids.length ? <Scans ids={b.model_ids} /> : <p className="muted small">No Matterport scans for this building.</p>}
        </div>
      </section>
      {apt && apt.plans.length > 0 && (
        <section>
          <h4 style={{ marginBottom: 10 }}>Floor plans on Apartments.com <span className="muted small">· from the CoStar kit</span></h4>
          <div className="tbl"><table>
            <thead><tr><th>Plan</th><th className="r">Beds</th><th className="r">Baths</th><th className="r">Size</th><th className="r">Units</th><th className="r">Available</th><th className="r">Rent</th></tr></thead>
            <tbody>{apt.plans.map((p, i) => <tr key={i}><td>{p.name || "—"}</td><td className="r">{p.beds ?? "—"}</td><td className="r">{p.baths ?? "—"}</td><td className="r num">{p.min_sqft ? sqft(p.min_sqft) : "—"}</td><td className="r num">{p.units ?? "—"}</td><td className="r num">{p.available ?? "—"}</td><td className="r num">{p.min_rent ? `$${p.min_rent.toLocaleString()}${p.per_bed ? " / bed" : ""}` : "—"}</td></tr>)}</tbody>
          </table></div>
        </section>
      )}
      {ten && ten.list.length > 0 && (
        <section>
          <h4 style={{ marginBottom: 10 }}>Current tenants <span className="muted small">· {ten.count} in the CoStar kit</span></h4>
          <div className="tbl"><table>
            <thead><tr><th>Tenant</th><th>Suite</th><th className="r">Occupied</th><th>Since</th></tr></thead>
            <tbody>{ten.list.slice(0, 15).map((t, i) => <tr key={i}><td>{t.name}</td><td>{t.suites.join(", ") || "—"}</td><td className="r num">{t.sqft ? sqft(Math.round(t.sqft)) : "—"}</td><td>{t.since || "—"}</td></tr>)}</tbody>
          </table></div>
        </section>
      )}
      <Flag t="CoStar kit records · Vexcel and Matterport fetched live" />
    </div>
  );
}

export default function Buildings({ A, id }) {
  return id ? <Detail key={id} A={A} id={id} /> : <Search A={A} />;
}
