// Solana devnet: the approver's Phantom wallet signs; Plumbline's server builds the transaction and pays the fee.
// Without Phantom, the backend signs with a demo lender key, so the demo never depends on a browser extension.
import { Transaction } from "@solana/web3.js";

const phantom = () => window.phantom?.solana || (window.solana?.isPhantom ? window.solana : null);
export const hasPhantom = () => !!phantom();

export async function connectPhantom() {
  const p = phantom();
  if (!p) throw new Error("Phantom isn't installed in this browser.");
  const res = await p.connect();
  return res.publicKey.toString();
}

export async function disconnectPhantom() {
  try { await phantom()?.disconnect(); } catch { /* already disconnected */ }
}

async function post(path, body) {
  const res = await fetch("/api/solana" + path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  const out = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(out.detail || `Solana request failed (${res.status})`);
  return out;
}

const b64 = bytes => btoa(String.fromCharCode(...bytes));
const unb64 = s => Uint8Array.from(atob(s), ch => ch.charCodeAt(0));

// action: "decision" (with decision ok|sent|rejected) or "release". wallet: Phantom address or null for the demo key.
export async function signOnSolana(cid, { action = "decision", decision = "ok", wallet = null } = {}) {
  const prep = await post(`/claims/${cid}/prepare`, { action, decision, wallet });
  if (!prep.tx) return prep; // signed by the demo lender key on the server
  const tx = Transaction.from(unb64(prep.tx));
  const signed = await phantom().signTransaction(tx);
  return post(`/claims/${cid}/submit`, { action, tx: b64(signed.serialize()) });
}

export const verifyOnSolana = cid => fetch(`/api/solana/claims/${cid}/verify`).then(async r => {
  const out = await r.json();
  if (!r.ok) throw new Error(out.detail || "Verify failed");
  return out;
});

export const tamperEvidence = cid => post(`/claims/${cid}/tamper`, {});
export const solanaStatus = () => fetch("/api/solana/status").then(r => r.json());
