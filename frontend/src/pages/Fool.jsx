import { useEffect, useState } from "react";
import QRCode from "qrcode";
import { META } from "../data";
import { FINAL, Tag, fmt } from "../lib";
import FoolForm, { foolTarget } from "../components/FoolForm";

export const trick = c => c.outcome.injected ? "Hidden message" : c.bank !== "••4421" ? "Bank swap" : c.claim > c.measured * 1.05 ? "Inflated roof" : "Honest";

// Where phones should open the form. Set PUBLIC_URL on the server once deployed (e.g. https://plumbline.us).
export const phoneUrl = () => `${(META.public_url || location.origin).replace(/\/$/, "")}/#/fool-it`;

function RealQR({ text }) {
  const [src, setSrc] = useState(null);
  useEffect(() => {
    QRCode.toDataURL(text, { margin: 1, width: 280, errorCorrectionLevel: "M", color: { dark: "#000000", light: "#FFFFFF" } })
      .then(setSrc).catch(() => setSrc(null));
  }, [text]);
  return src ? <img src={src} alt={`QR code for ${text}`} width={140} height={140} style={{ display: "block", borderRadius: 8 }} />
    : <div style={{ width: 140, height: 140 }} />;
}

export default function Fool({ S, A }) {
  const attempts = S.all.filter(c => c.judge);
  const target = foolTarget()?.name || "Westheimer Commons";
  const url = phoneUrl();
  const local = /localhost|127\.0\.0\.1/.test(url);
  return (
    <div className="wrapx">
      <div className="grid g2" style={{ alignItems: "center", gap: 56, paddingTop: 40 }}>
        <div>
          <div className="over">For judges</div>
          <h1 className="h1" style={{ fontSize: 88, letterSpacing: "-4px" }}>Try to<br />fool it.</h1>
          <p className="lede">Scan the code and write a roofing bill for {target}. Inflate the roof, swap the bank account, or hide a message to the AI. It goes straight to the live agent.</p>
          <div className="row" style={{ gap: 20, marginTop: 28 }}>
            <div className="tile" style={{ padding: 10, background: "#fff", border: "1px solid var(--g2)" }}><RealQR text={url} /></div>
            <div className="muted">
              <a href={url} target="_blank" rel="noopener" className="mono small" style={{ color: "var(--ink)", wordBreak: "break-all" }}>{url.replace(/^https?:\/\//, "")}</a>
              <br />Any phone works
              {local && <div className="small" style={{ marginTop: 6, color: "var(--amberDeep)" }}>Phones can't reach localhost. Set PUBLIC_URL once deployed.</div>}
            </div>
          </div>
          {attempts.length > 0 && (
            <div className="tbl" style={{ marginTop: 28 }}><table>
              <thead><tr><th>Attempt</th><th>Trick</th><th className="r">Paid</th><th>Result</th></tr></thead>
              <tbody>
                {attempts.map(c => (
                  <tr key={c.id} className="click" onClick={() => A.go("claim", c.id)}>
                    <td className="mono">{c.id}</td>
                    <td>{trick(c)}</td>
                    <td className="r num">{FINAL.includes(S.status[c.id]) ? fmt(c.outcome.a[1]) : "—"}</td>
                    <td><Tag s={S.status[c.id] || "ready"} /></td>
                  </tr>
                ))}
              </tbody>
            </table></div>
          )}
        </div>
        <div style={{ display: "flex", justifyContent: "center" }}>
          <div className="phone"><div className="screen">
            <div className="mono" style={{ fontSize: 11, color: "var(--ink3)", textAlign: "center" }}>fool-it</div>
            <FoolForm disabled={S.running} onSubmit={A.judge} />
          </div></div>
        </div>
      </div>
    </div>
  );
}
