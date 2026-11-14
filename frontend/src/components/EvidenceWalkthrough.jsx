import { lazy, Suspense, useEffect, useRef, useState } from "react";
import SurveyDrawing, { EVIDENCE_VIEWS } from "./SurveyDrawing";

const PropertyScene = lazy(() => import("./PropertyScene"));

const INTRO = ["Property verification", "The claim"];
const STAGES = [INTRO, ...EVIDENCE_VIEWS.map(({ source, title }) => [source, title])];
const clamp = (value, min, max) => Math.max(min, Math.min(max, value));

export default function EvidenceWalkthrough({ headline, lede, property, featured, waiting, running, onRun }) {
  const root = useRef(null);
  const pin = useRef(null);
  const [stage, setStage] = useState(0);
  const [sceneReady, setSceneReady] = useState(false);
  const sceneProgress = useRef({ value: 0, instant: false, draw: null });
  const lastStage = useRef(0);
  const direction = useRef(1);

  useEffect(() => {
    let frame = 0;
    const motion = matchMedia("(prefers-reduced-motion: reduce)");
    const measure = () => {
      frame = 0;
      const story = root.current;
      const sticky = pin.current;
      if (!story || !sticky) return;
      const top = parseFloat(getComputedStyle(sticky).top) || 0;
      const distance = Math.max(1, story.offsetHeight - sticky.offsetHeight);
      const progress = clamp((top - story.getBoundingClientRect().top) / distance, 0, 1);
      const active = Math.round(progress * (STAGES.length - 1));
      if (active !== lastStage.current) {
        direction.current = active > lastStage.current ? 1 : -1;
        lastStage.current = active;
        setStage(active);
      }
      const channel = sceneProgress.current;
      channel.value = motion.matches ? active : progress * (STAGES.length - 1);
      channel.draw?.();
      story.style.setProperty("--progress", progress);
      const compare = motion.matches ? Number(active >= 2) : clamp(progress * 3 - 1, 0, 1);
      story.style.setProperty("--comparison", compare);
    };
    const schedule = () => {
      if (!frame) frame = requestAnimationFrame(measure);
    };
    const resumeMotion = () => { sceneProgress.current.instant = false; };
    window.addEventListener("wheel", resumeMotion, { passive: true });
    window.addEventListener("touchstart", resumeMotion, { passive: true });
    window.addEventListener("scroll", schedule, { passive: true });
    window.addEventListener("resize", schedule);
    motion.addEventListener("change", schedule);
    schedule();
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener("wheel", resumeMotion);
      window.removeEventListener("touchstart", resumeMotion);
      window.removeEventListener("scroll", schedule);
      window.removeEventListener("resize", schedule);
      motion.removeEventListener("change", schedule);
    };
  }, []);

  function jump(index, keyboard) {
    const chapter = clamp(index, 0, STAGES.length - 1);
    const story = root.current;
    const sticky = pin.current;
    const inset = parseFloat(getComputedStyle(sticky).top) || 0;
    const distance = story.offsetHeight - sticky.offsetHeight;
    const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
    sceneProgress.current.instant = keyboard;
    window.scrollTo({
      top: window.scrollY + story.getBoundingClientRect().top - inset + distance * chapter / (STAGES.length - 1),
      behavior: reduced || keyboard ? "instant" : "smooth",
    });
  }

  function skipWalkthrough() {
    const ledger = document.querySelector("#workspace-summary");
    ledger.focus({ preventScroll: true });
    ledger.scrollIntoView({ block: "start" });
  }

  const view = EVIDENCE_VIEWS[stage - 1];
  const line = featured?.lines?.[0];
  return (
    <section ref={root} className="evidence-story" aria-label="Interactive evidence walkthrough">
      <div ref={pin} className="evidence-pin" data-stage={stage} style={{ "--entry-x": `${sceneProgress.current.instant ? 0 : direction.current * -32}px` }}>
        <div className="story-copy">
          <div className="story-words" key={stage}>
            <p className="over">{stage === 0 ? "Building evidence for payment review" : view.source}</p>
            {stage === 0 ? (
              <>
                <h1>{headline[0]}<br /><em>{headline[1]}</em></h1>
                <p className="story-lede">{lede}</p>
              </>
            ) : (
              <>
                <h2>{view.title}.</h2>
                <p className="story-lede">{view.description}</p>
              </>
            )}
          </div>
          {stage === 0 ? (
            <div className="story-actions">
              <button type="button" className="btn story-primary" onClick={event => jump(1, event.detail === 0)}>Explore the evidence <span aria-hidden="true">↓</span></button>
              <button type="button" className="story-text-action" disabled={!waiting || running} onClick={onRun}>
                {running ? "Checking…" : waiting ? `Check ${waiting} waiting` : "All checked"}
              </button>
            </div>
          ) : (
            <div className="story-actions">
              {featured && <a className="text-link" href={`#/claim/${featured.id}`}>Open sample case <span aria-hidden="true">↗</span></a>}
            </div>
          )}
        </div>
        <div className="story-visual">
          <div className="story-art" data-scene-ready={sceneReady}>
            <SurveyDrawing view={stage - 1} />
            <Suspense fallback={null}><PropertyScene progress={sceneProgress} onReady={setSceneReady} /></Suspense>
          </div>
          <div className="story-location"><strong>{property?.name ?? "Property survey"}</strong><span>{property?.city}</span><span>Illustrative property model</span></div>
          {line && <div className="story-comparison" aria-label="Featured case comparison">
            <div><small>Submitted</small><strong>{line[1]}</strong></div>
            <div><small>Case finding</small><strong>{line[2]}</strong></div>
          </div>}
        </div>
        <div className="story-navigation">
          <div className="story-controls">
            <button type="button" className="story-skip" onClick={skipWalkthrough}>Skip to workspace <span aria-hidden="true">↓</span></button>
            <div className="story-arrows">
              <button type="button" aria-label="Previous chapter" aria-disabled={stage === 0} onClick={event => stage > 0 && jump(stage - 1, event.detail === 0)}>←</button>
              <button type="button" aria-label="Next chapter" aria-disabled={stage === STAGES.length - 1} onClick={event => stage < STAGES.length - 1 && jump(stage + 1, event.detail === 0)}>→</button>
            </div>
          </div>
          <div className="story-progress" aria-hidden="true"><i /></div>
          <div className="story-rail" role="group" aria-label="Evidence chapters" onKeyDown={event => {
            if (!["ArrowLeft", "ArrowRight"].includes(event.key)) return;
            event.preventDefault();
            const buttons = [...event.currentTarget.querySelectorAll("button")];
            const next = clamp(buttons.indexOf(event.target) + (event.key === "ArrowRight" ? 1 : -1), 0, buttons.length - 1);
            buttons[next].focus({ preventScroll: true });
            jump(next, true);
          }}>
            {STAGES.map(([source, title], index) => (
              <button type="button" key={title} aria-label={`${source}: ${title}`} aria-pressed={stage === index} onClick={event => jump(index, event.detail === 0)}>
                <strong>{title}</strong>
              </button>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
