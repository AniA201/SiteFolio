// What the CoStar kit knows about a building beyond its record: rents, tenants, last sale, active listings.
const usd = n => "$" + Math.round(n).toLocaleString();
const words = s => s.replace(/([a-z])([A-Z])/g, "$1 $2").toLowerCase();

export default function Dossier({ d }) {
  if (!d || !Object.keys(d).length) return null;
  const rows = [];
  if (d.home) {
    const h = d.home;
    rows.push(["Home listing", `${h.price ? usd(h.price) : "Price not given"} · ${words(h.status)}${h.listed ? ` · listed ${h.listed}` : ""}`,
      [h.mls_type, h.subdivision, h.lot_acres ? `${h.lot_acres} acres` : null].filter(Boolean).join(" · ") || null]);
  }
  if (d.apartments) {
    const a = d.apartments;
    const rent = a.min_rent && a.max_rent ? `${usd(a.min_rent)}–${usd(a.max_rent)} / mo · ${a.plans} floor plans` : `${a.plans} floor plans listed`;
    rows.push(["Asking rents", rent + (a.available != null ? ` · ${a.available} available` : ""), a.manager ? `Apartments.com · managed by ${a.manager}` : "Apartments.com"]);
  }
  if (d.tenants) {
    const t = d.tenants;
    const named = t.top.filter(x => x.name !== "Unknown tenant").slice(0, 3)
      .map(x => x.name + (x.suites?.length ? ` (Suite ${x.suites.join(", ").replace(/\.$/, "")})` : ""));
    rows.push(["Tenants", `${t.count} current${t.occupied_sqft ? ` · ${t.occupied_sqft.toLocaleString()} sq ft occupied` : ""}`, named.length ? named.join(" · ") : null]);
  }
  if (d.last_sale) {
    const s = d.last_sale;
    rows.push(["Last sale", s.date + (s.price ? ` · ${usd(s.price)}` : ""),
      s.price ? `Price ${words(s.price_status)}${s.portfolio ? ", portfolio allocation" : ""}` : "Price not disclosed"]);
  }
  for (const l of d.listings || []) {
    if (l.available_sqft) {
      const rate = l.asking_rate_low ? ` · $${l.asking_rate_low}${l.asking_rate_high && l.asking_rate_high !== l.asking_rate_low ? "–" + l.asking_rate_high : ""}/sq ft ${l.rate_basis || ""}` : "";
      rows.push(["For lease", `${Math.round(l.available_sqft).toLocaleString()} sq ft available${rate}`, l.brokerage]);
    } else if (l.asking_price_low) {
      rows.push(["For sale", `Asking ${usd(l.asking_price_low)}`, l.brokerage]);
    }
  }
  return (
    <div style={{ marginTop: 14, borderTop: "1px solid var(--g3)", paddingTop: 10 }}>
      <div className="over" style={{ fontSize: 10.5 }}>Also in the CoStar kit</div>
      {rows.map(([k, v, sub]) => (
        <div key={k + v} className="small" style={{ display: "grid", gridTemplateColumns: "92px 1fr", gap: 10, padding: "6px 0" }}>
          <span className="muted">{k}</span>
          <span>{v}{sub && <span className="muted" style={{ display: "block", fontSize: 12 }}>{sub}</span>}</span>
        </div>
      ))}
    </div>
  );
}
