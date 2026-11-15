// The page a judge's phone opens from the QR code: write a bill, then watch the live agent check it.
import { useState } from "react";
import { COL, Check, FINAL, Tag, WHO, money } from "../lib";
import FoolForm from "../components/FoolForm";
import { trick } from "./Fool";

export default function FoolPhone({ S, A }) {
  const [mine, setMine] = useState(null);
  const [error, setError] = useState("");
  const c = mine && S.all.find(x => x.id === mine);
  const step = c ? S.steps[c.id] ?? -1 : -1;
  const done = c && FINAL.includes(S.status[c.id]);
  const submit = bill => {
    setError("");
    A.judgeHere(bill).then(setMine).catch(e => setError(/422/.test(String(e?.message || e))
      ? "That bill has a number that's too big or a note that's too long. Try smaller numbers."
      : "Couldn't send the bill. Check the connection and try again."));
  };

  return (
    <div style={{ maxWidth: 460, margin: "0 auto", padding: "max(20px, env(safe-area-inset-top)) 18px 40px" }}>
      <div className="row between">
        <span className="word" style={{ fontSize: 13, letterSpacing: ".3em" }}>SITEFOLIO</span>
        <span className="mono" style={{ fontSize: 11, color: "var(--ink3)" }}>fool-it</span>
      </div>
      {!c && <>
        <h1 className="h1" style={{ fontSize: 44, letterSpacing: "-2px", marginTop: 22 }}>Try to fool it.</h1>
        <p className="muted" style={{ lineHeight: 1.5 }}>Inflate the roof, swap the bank account, or hide a message to the AI in the notes. The bill goes straight to the live agent.</p>
        <FoolForm disabled={S.running && !mine} onSubmit={submit} submitLabel={S.running ? "Agent is busy, one moment…" : "Send the bill"} />
        {error && <p className="small" style={{ color: "var(--red)" }}>{error}</p>}
      </>}
      {c && (
        <div style={{ marginTop: 22 }}>
          <div className="row between"><span className="mono small muted">{c.id}</span><Tag s={S.status[c.id] || "ready"} /></div>
          <h2 className="h3" style={{ marginTop: 10 }}>{done ? "Here's what the agent decided" : "The agent is checking your bill…"}</h2>
          <div style={{ marginTop: 12 }}>
            {c.steps.map(([who, text, res], k) => {
              const isDone = k < step, live = k === step;
              return (
                <div className="todo" key={k} style={{ opacity: isDone || live ? 1 : .35, gridTemplateColumns: "22px 1fr", fontSize: 14 }}>
                  <span className={"dot " + (isDone ? (res === "done" ? "done" : res === "fail" ? "fail" : "warn") : live ? "live" : "")}>{isDone && <Check res={res} />}</span>
                  <span>{text} <span className="muted small">· {WHO[who]}</span></span>
                </div>
              );
            })}
          </div>
          {done && (
            <div className="tile" style={{ marginTop: 14 }}>
              <div className="over">Your trick: {trick(c)}</div>
              <div className="row" style={{ gap: 28, marginTop: 12 }}>
                {[c.outcome.a, c.outcome.b].map(([l, v, col]) => <div key={l}><div className="muted small">{l}</div><div className="num" style={{ fontSize: 30, fontWeight: 600, color: COL[col] }}>{money(v)}</div></div>)}
              </div>
              <p style={{ lineHeight: 1.5 }}>{c.outcome.reason}</p>
              {c.outcome.injected && <div className="quote">Hidden instruction found and ignored: <span className="mono" style={{ color: "var(--red)" }}>"{c.outcome.injected}"</span></div>}
              <button className="btn black sm" style={{ marginTop: 14, width: "100%" }} onClick={() => setMine(null)}>Try another trick</button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
