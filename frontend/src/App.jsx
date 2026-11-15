import { useEffect, useState } from "react";
import { META, PERSONAS } from "./data";
import { Flag, NEEDS } from "./lib";
import { api } from "./api";
import { useBackend } from "./useBackend";
import Overview from "./pages/Overview";
import Claims from "./pages/Claims";
import ClaimDetail from "./pages/ClaimDetail";
import Review from "./pages/Review";
import Tenant from "./pages/Tenant";
import History from "./pages/History";
import Thinks from "./pages/Thinks";
import Fool from "./pages/Fool";
import Buildings from "./pages/Buildings";
import FoolPhone from "./pages/FoolPhone";

const NAV = [["overview", "Overview"], ["claims", "Claims"], ["buildings", "Buildings"], ["review", "Review"], ["history", "History"]];
const TOOLS = [["tenant", "Tenant view"], ["thinks", "How it thinks"], ["fool", "Try to fool it"]];
const PARENT = { claim: "claims", building: "buildings" };

const readHash = () => {
  const [page, id] = (location.hash || "#/overview").slice(2).split("/");
  return { page: page || "overview", id };
};
const go = (page, id) => { location.hash = "#/" + page + (id ? "/" + id : ""); };

export default function App() {
  const [route, setRoute] = useState(readHash);
  const [persona, setPersona] = useState("owner");
  const [confirmReset, setConfirmReset] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [state, apply] = useBackend();

  useEffect(() => {
    const onHash = () => { setRoute(readHash()); setMenuOpen(false); window.scrollTo(0, 0); };
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  const all = state.claims;
  const list = all.filter(c => c.persona === persona);
  const running = !!state.current || state.queue.length > 0;

  const A = {
    go, setPersona,
    run: id => { if (!running) api.run(id).then(apply); },
    runAll: () => api.runAll(persona).then(apply),
    reset: id => api.reset(id).then(apply),
    resetAll: () => api.resetAll().then(apply),
    retry: id => api.retry(id).then(apply),
    decide: (id, action) => api.decide(id, action).then(apply),
    ingest: sampleId => api.ingest(sampleId).then(r => { apply(r.state); go("claim", r.id); }),
    judge: bill => api.judge(bill).then(r => { apply(r.state); setPersona("owner"); go("claim", r.id); }),
    upload: (file, buildingId) => api.upload(file, buildingId).then(r => { apply(r.state); setPersona("owner"); go("claim", r.id); return r; }),
    judgeHere: bill => api.judge(bill).then(r => { apply(r.state); return r.id; }),
  };
  const S = { persona, list, all, samples: state.samples, memory: state.agent_memory, steps: state.steps, status: state.status, running, current: state.current, review: state.review, retry: state.retry, log: state.log };

  const { page, id } = route, active = PARENT[page] || page;
  const reviewCount = list.filter(c => NEEDS.includes(state.status[c.id]) && !state.review[c.id]).length;
  const P = { S, A };
  const body = {
    overview: <Overview key={persona} {...P} />,
    claims: <Claims {...P} />,
    claim: <ClaimDetail key={id} {...P} id={id} />,
    review: <Review key={persona} {...P} />,
    tenant: <Tenant {...P} id={id} />,
    history: <History {...P} />,
    thinks: <Thinks key={persona} {...P} />,
    fool: <Fool {...P} />,
    buildings: <Buildings {...P} />,
    building: <Buildings key={id} {...P} id={id} />,
  }[page] || <Overview {...P} />;

  if (page === "fool-it") return state.rev >= 0 ? <FoolPhone {...P} /> : null;

  return (
    <div>
      <a className="skip-link" href="#main" onClick={event => { event.preventDefault(); document.querySelector("#main").focus(); }}>Skip to content</a>
      <div className="navwrap"><nav className="nav" aria-label="Workspace">
        <a className="word" href="#/overview"><svg viewBox="0 0 20 23" width="18" height="21" aria-hidden="true"><path d="M10 1v10m0 0-5 5 5 6 5-6-5-5Z" fill="none" stroke="currentColor" strokeWidth="1.5" /></svg>SiteFolio</a>
        <div className="navlinks">
          {NAV.map(([k, l]) => <a key={k} href={`#/${k}`} aria-current={active === k ? "page" : undefined} className={active === k ? "on" : ""}>{l}{k === "review" && reviewCount > 0 && <span className="nav-count" aria-label={reviewCount + " pending"}>{reviewCount}</span>}</a>)}
        </div>
        <div className="nav-tools" onKeyDown={event => {
          if (event.key === "Escape" && menuOpen) {
            setMenuOpen(false);
            event.currentTarget.querySelector("button").focus();
          }
        }} onBlur={event => {
          if (!event.currentTarget.contains(event.relatedTarget)) setMenuOpen(false);
        }}>
          <button type="button" className="nav-menu-button" aria-expanded={menuOpen} aria-controls="workspace-tools"
            onClick={() => setMenuOpen(!menuOpen)}>
            {PERSONAS[persona].short} <span aria-hidden="true">⌄</span>
          </button>
          <div className="nav-menu" id="workspace-tools" hidden={!menuOpen}>
            <label>Workspace<select aria-label="Workspace persona" value={persona} onChange={event => {
              setPersona(event.target.value);
              if (page === "claim") go("claims");
            }}>
              {Object.entries(PERSONAS).map(([k, v]) => <option key={k} value={k}>{v.short}</option>)}
            </select></label>
            {TOOLS.map(([key, label]) => <a key={key} href={`#/${key}`} onClick={() => setMenuOpen(false)} aria-current={active === key ? "page" : undefined}>{label}</a>)}
            {confirmReset
              ? <div className="nav-reset"><span>Clear every check and decision?</span>
                  <button type="button" className="btn black sm" onClick={() => { A.resetAll(); setConfirmReset(false); setMenuOpen(false); go("overview"); }}>Reset</button>
                  <button type="button" className="btn white sm" onClick={() => setConfirmReset(false)}>Cancel</button></div>
              : <button type="button" className="nav-reset-open" onClick={() => setConfirmReset(true)}>Reset demo</button>}
          </div>
        </div>
      </nav></div>
      <main id="main" tabIndex={-1}>{state.rev >= 0 ? body : <p className="wrapx" role="status">Loading workspace…</p>}</main>
      <footer><div className="wrapx row between wrap">
        <span className="small muted">SiteFolio · Building evidence for payment review</span>
        <Flag t={META.data_note || "All buildings, parties and numbers are sample data"} />
      </div></footer>
    </div>
  );
}
