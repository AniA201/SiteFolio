// Reference data served by the backend (/api/meta). Filled once before the app renders.
export const BUILDINGS = {};
export const PARTIES = {};
export const PERSONAS = {};
export const SURCHARGES = [];

export async function loadMeta() {
  const res = await fetch("/api/meta");
  if (!res.ok) throw new Error("Could not reach the Plumbline API");
  const m = await res.json();
  Object.assign(BUILDINGS, m.buildings);
  Object.assign(PARTIES, m.parties);
  Object.assign(PERSONAS, m.personas);
  SURCHARGES.push(...m.surcharges);
}
