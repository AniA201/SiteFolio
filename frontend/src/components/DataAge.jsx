// When a piece of evidence was captured, and whether it is too old to prove recent work.
export default function DataAge({ stamp, verb = "Photographed", staleNote = "older than the work claimed, so it proves size, not the new work" }) {
  if (!stamp || !stamp.date) return null;
  return (
    <div className="small" style={{ marginTop: 8, color: stamp.stale ? "var(--amberDeep, var(--accent))" : "var(--ink3)", fontWeight: stamp.stale ? 600 : 400 }}>
      {verb} {stamp.label}{stamp.stale ? ` · ${staleNote}` : ""}
    </div>
  );
}
