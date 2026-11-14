import { useState } from "react";
import { META, SURCHARGES } from "../data";
import { Head } from "../lib";

const VIEWS = [["all", "Activity"], ["flagged", "Flags"], ["registry", "Surcharge registry"]];
const OUTCOMES = { done: "Passed", fail: "Flagged", warn: "Needs attention" };

export default function History({ S, A }) {
  const [view, setView] = useState("all");
  const [query, setQuery] = useState("");
  const ids = new Set(S.all.map(claim => claim.id));
  const events = S.log.map(event => {
    const id = event.text.split(" · ", 1)[0];
    return { ...event, id: ids.has(id) ? id : null };
  });
  const flags = events.filter(event => event.ok === "fail" || event.ok === "warn");
  const registry = view === "registry";
  const search = query.trim().toLowerCase();
  const rows = (registry ? SURCHARGES : view === "flagged" ? flags : events).filter(row => (
    (registry ? [row.building, row.property_id, row.work] : [row.text, row.who, OUTCOMES[row.ok]])
      .some(value => value?.toLowerCase().includes(search))
  ));
  const counts = { all: events.length, flagged: flags.length, registry: SURCHARGES.length };

  return (
    <div className="wrapx history">
      <Head title="History" lede="Find a past check, follow a flag, or look up a registered surcharge." />
      <div className="history-toolbar">
        <div className="history-filters" role="group" aria-label="History view">
          {VIEWS.map(([key, label]) => <button type="button" key={key} aria-pressed={view === key} onClick={() => { setView(key); setQuery(""); }}>{label} <span>{counts[key]}</span></button>)}
        </div>
        <input type="search" aria-label={registry ? "Search registry" : "Search activity"} placeholder={registry ? "Search buildings or work" : "Search claims or checks"} value={query} onChange={event => setQuery(event.target.value)} />
      </div>
      {rows.length > 0 ? <div className="history-results" key={view}>
        {registry ? <div className="tbl"><table>
          <thead><tr><th scope="col">Building</th><th scope="col">Work</th><th scope="col">Approved</th><th scope="col">Ends</th><th scope="col">Per unit / month</th></tr></thead>
          <tbody>{rows.map(s => <tr key={s.property_id + s.work}>
            <td><b>{s.building}</b><br /><span className="mono muted small">{s.property_id}</span></td>
            <td>{s.work}</td><td>{s.approved}</td><td>{s.ends}</td><td className="num">{s.per_unit}</td>
          </tr>)}</tbody>
        </table></div> : <ul className="history-events">{rows.map((event, index) => (
          <li key={event.t + event.text + index}>
            <time className="mono">{event.t}</time>
            <div>{event.id ? <a href={`#/claim/${event.id}`}>{event.text.slice(event.id.length + 3)} <span aria-hidden="true">↗</span></a> : event.text}
              <small>{event.who}{event.id && " · " + event.id}</small></div>
            <span className={event.ok === "done" ? "muted" : "history-flag"}>{OUTCOMES[event.ok] ?? "Event"}</span>
          </li>
        ))}</ul>}
      </div> : <div className="history-empty">
        <p>{search ? "No matching records." : registry ? "No surcharges in the registry." : view === "flagged" ? "No flags in recent activity." : "Run a claim check to see its activity here."}</p>
        {search ? <button className="btn white sm" onClick={() => setQuery("")}>Clear search</button> : !registry && <a className="btn white sm" href="#/claims">Open claims</a>}
      </div>}
      {registry && <div className="history-note">
        <p className="muted small">{META.real ? "Surcharge registry" : "Sample surcharge registry"}</p>
        <button className="btn white sm" onClick={() => { A.setPersona("reviewer"); A.go("claims"); }}>Open rent applications</button>
      </div>}
    </div>
  );
}
