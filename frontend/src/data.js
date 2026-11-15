// Reference data served by the backend (/api/meta). Filled once before the app renders.
export const BUILDINGS = {};
export const PARTIES = {};
export const PERSONAS = {};
export const SURCHARGES = [];
export const META = { real: false, stories: null, fool: null, data_note: null };

export async function loadMeta() {
  const res = await fetch("/api/meta");
  if (!res.ok) throw new Error("Could not reach SiteFolio");
  const m = await res.json();
  Object.assign(BUILDINGS, m.buildings);
  Object.assign(PARTIES, m.parties);
  Object.assign(PERSONAS, m.personas);
  SURCHARGES.push(...m.surcharges);
  Object.assign(META, m.meta || {}, { real: !!m.real, matterport_sdk_key: m.matterport_sdk_key || null, public_url: m.public_url || null, has_ai_reader: !!m.has_ai_reader });
}

// A claim's party: from the reference list, or carried on the claim itself (bills uploaded from new vendors).
export const partyOf = c => PARTIES[c.party] || c.party_info || { name: "Unknown sender", role: "Contractor", acct: "—", memory: "No history in our records." };
