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

const NAV = [["overview", "Overview"], ["claims", "Claims"], ["buildings", "Buildings"], ["review", "Review"], ["tenant", "Tenant view"], ["history", "History"], ["thinks", "How it thinks"]];
const PARENT = { claim: "claims", building: "buildings" };

const readHash = () => {
  const [page, id] = (location.hash || "#/overview").slice(2).split("/");
  return { page: page || "overview", id };
};
const go = (page, id) => { location.hash = "#/" + page + (id ? "/" + id : ""); };

export default function App() {
  const [route, setRoute] = useState(readHash);
  const [persona, setPersona] = useState("owner");
  const [state, apply] = useBackend();

  useEffect(() => {
    const onHash = () => { setRoute(readHash()); window.scrollTo(0, 0); };
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
    retry: id => api.retry(id).then(apply),
    decide: (id, action) => api.decide(id, action).then(apply),
    ingest: sampleId => api.ingest(sampleId).then(r => { apply(r.state); go("claim", r.id); }),
    judge: bill => api.judge(bill).then(r => { apply(r.state); setPersona("owner"); go("claim", r.id); }),
    upload: (file, buildingId) => api.upload(file, buildingId).then(r => { apply(r.state); setPersona("owner"); go("claim", r.id); return r; }),
    judgeHere: bill => api.judge(bill).then(r => { apply(r.state); return r.id; }),
  };
  const S = { persona, list, all, samples: state.samples, steps: state.steps, status: state.status, running, current: state.current, review: state.review, retry: state.retry, log: state.log };

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
      <div className="navwrap"><nav className="nav">
        <span className="word" onClick={() => go("overview")}>PLUMBLINE</span>
        <div className="navlinks">
          {NAV.map(([k, l]) => <a key={k} className={active === k ? "on" : ""} onClick={() => go(k)}>{l}{k === "review" && reviewCount > 0 && <span className="badge">{reviewCount}</span>}</a>)}
        </div>
        {running && <span className="tag t-running" style={{ marginRight: 6 }}><i />Checking</span>}
        <div className="orgsw">
          {Object.entries(PERSONAS).map(([k, v]) => <button key={k} className={persona === k ? "on" : ""} onClick={() => { setPersona(k); if (page === "claim") go("claims"); }}>{v.short}</button>)}
        </div>
        <button className="cta" onClick={() => go("fool")}>Try to fool it</button>
      </nav></div>
      {state.rev >= 0 && body}
      <footer><div className="wrapx row between wrap">
        <span className="small muted">PLUMBLINE · Check the paper against the building · CoStar · Vexcel · Matterport · deepagents · Tiger Data · Vultr</span>
        <Flag t={META.data_note || "All buildings, parties and numbers are sample data"} />
      </div></footer>
    </div>
  );
}
