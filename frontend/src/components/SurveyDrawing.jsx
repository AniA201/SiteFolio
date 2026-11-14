import { useId } from "react";

export const EVIDENCE_VIEWS = [
  { source: "CoStar", title: "Property record", description: "Check the recorded size, floor count, and property details." },
  { source: "Vexcel", title: "Aerial survey", description: "Measure the roof outline and inspect visible rooftop equipment." },
  { source: "Matterport", title: "Interior scan", description: "Inspect room measurements and evidence of interior work." },
];

const ROOF = "M161 139H492V205H547V382H161Z";
const ROOM_LINES = "M161 253H547M161 287H547M249 139V253M336 139V253M427 139V253M249 287V382M365 287V382M457 287V382";
const DIMENSIONS = "M161 124V101M492 124V101M161 113H492M145 139H119M145 382H119M131 139V382";
const PARCEL = "M104 74H596V424H104Z";
const HATCH_LINES = "M0 8L8 0M-2 2L2-2M6 10L10 6";

export default function SurveyDrawing({ view }) {
  const id = useId();
  return (
    <svg className="survey-drawing" data-view={view} viewBox="0 0 700 485" aria-hidden="true" fill="none">
      <defs>
        <pattern id={id + "-grid"} width="24" height="24" patternUnits="userSpaceOnUse">
          <path d="M24 0H0V24" stroke="var(--line)" strokeWidth=".65" />
        </pattern>
        <pattern id={id + "-hatch"} width="8" height="8" patternUnits="userSpaceOnUse">
          <path d={HATCH_LINES} stroke="var(--accent)" strokeOpacity=".38" strokeWidth=".6" />
        </pattern>
      </defs>
      <path d="M1 1H699V484H1Z" fill={"url(#" + id + "-grid)"} />
      <g className="survey-context">
        <path d={PARCEL} strokeDasharray="4 5" />
        <path d="M52 74H78M65 61V87M622 424H648M635 411V437M622 74H648M635 61V87M52 424H78M65 411V437" />
        <path d="M104 397H596M570 74V397M104 91H596" opacity=".6" />
      </g>
      <g className="survey-massing">
        <path d="M130 301 390 378 627 293 368 218Z" className="massing-shadow" />
        <path d="M160 185 398 255 398 357 160 287Z" className="massing-front" />
        <path d="M398 255 593 185 593 286 398 357Z" className="massing-side" />
        <path d="M160 185 356 115 593 185 398 255Z" className="massing-top" />
        <path d="M178 185 356 121 576 186 398 249Z" className="massing-roof-inset" />
        <path d="M160 218 398 289 593 218M160 252 398 323 593 252" className="massing-lines" />
        {[0, 1, 2].map(floor => (
          <g key={floor}>
            {Array.from({ length: 8 }, (_, index) => {
              const x = 171 + index * 28;
              const y = 195 + (x - 160) * .294 + floor * 33.5;
              return <path key={index} d={`M${x} ${y}l17 5v14l-17-5Z`} className="massing-window" />;
            })}
            {Array.from({ length: 6 }, (_, index) => {
              const x = 411 + index * 28;
              const y = 264 - (x - 398) * .359 + floor * 33.5;
              return <path key={index} d={`M${x} ${y}l17-6v14l-17 6Z`} className="massing-window" />;
            })}
          </g>
        ))}
        <path d="M160 185 356 115 593 185 398 255Z" className="massing-outline" pathLength="1" />
        <path d="M356 115 379 84H482M593 286 624 315H650" className="survey-accent" />
        <text x="482" y="75" textAnchor="end">PROPERTY MODEL</text>
        <circle cx="356" cy="115" r="3.5" fill="var(--accent)" />
      </g>
      <g className="survey-camera">
        <path className="survey-footprint" d={ROOF} />
        <g className="survey-layer survey-aerial">
          <path className="roof-trace" d={ROOF} pathLength="1" />
          <path d="M172 150H481V216H536V371H172Z" fill={"url(#" + id + "-hatch)"} opacity=".55" />
          <g className="survey-ink">
            <path d="M182 165H471V225H523V355H182ZM182 312H523M411 165V355" opacity=".5" />
            {[211, 274, 337, 453].map(x => (
              <g key={x}>
                <path d={`M${x} 192h30v21h-30z M${x + 4} 197h22m-22 5h22m-22 5h22`} />
                <path d={`M${x} 329h30v19h-30z M${x + 4} 334h22m-22 5h22m-22 5h22`} />
              </g>
            ))}
          </g>
          <path className="survey-accent" d="M492 139L527 103H592M547 345H581" />
          <text x="592" y="95" textAnchor="end">ROOF OUTLINE</text>
          <circle cx="492" cy="139" r="4" fill="var(--accent)" />
        </g>
        <g className="survey-layer survey-record">
          <path d={DIMENSIONS} className="survey-accent" />
          <path d="M157 117L165 109M488 117L496 109M127 143L135 135M127 386L135 378" className="survey-accent" />
          <path d="M161 205H492M161 270H547M161 334H547M223 139V382M304 139V382M385 139V382M466 139V382" className="survey-ink" opacity=".45" />
          <text x="327" y="103" textAnchor="middle">BUILDING FOOTPRINT</text>
        </g>
        <g className="survey-layer survey-interior">
          <path d="M161 253H547V287H161Z" fill={"url(#" + id + "-hatch)"} />
          <path d={ROOM_LINES} className="survey-ink" />
          <path d="M185 270H508L552 314H590" className="survey-accent" strokeDasharray="3 3" />
          <circle cx="185" cy="270" r="4" fill="var(--accent)" />
          <text x="590" y="331" textAnchor="end">INTERIOR COVERAGE</text>
        </g>
      </g>
      <g className="survey-ink">
        <path d="M624 117V165M612 132L624 117L636 132M624 117L620 135" />
        <text x="624" y="104" textAnchor="middle">N</text>
        <path d="M104 450H166M104 445V455M135 445V455M166 445V455" />
      </g>
      <text x="104" y="474">SCHEMATIC · NOT TO SCALE</text>
    </svg>
  );
}
