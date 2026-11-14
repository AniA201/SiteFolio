import { useState } from "react";

export default function EvidenceFolio({ lines }) {
  const [side, setSide] = useState("claim");
  if (!lines.length) return null;
  return (
    <div className="evidence-folio">
      <div className="folio-switch" role="group" aria-label="Evidence sheet side">
        <button type="button" aria-pressed={side === "claim"} onClick={() => setSide("claim")}>The paper says</button>
        <button type="button" aria-pressed={side === "evidence"} onClick={() => setSide("evidence")}>The building says</button>
      </div>
      <div className="folio-perspective" data-side={side}>
        <div className="folio-sheet">
          {[["claim", "As submitted", 1], ["evidence", "Evidence findings", 2]].map(([face, label, column]) => (
            <div key={face} className={`folio-face folio-face--${face}`} aria-hidden={side !== face}>
              <div className="over">{label}</div>
              <dl>
                {lines.map((line, index) => (
                  <div key={index}><dt>{line[0]}</dt><dd className="num">{line[column]}</dd></div>
                ))}
              </dl>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
