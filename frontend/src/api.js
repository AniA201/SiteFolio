async function post(path, body) {
  const res = await fetch("/api" + path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`${path} failed: ${res.status}`);
  return res.json();
}

export const api = {
  state: () => fetch("/api/state").then(r => r.json()),
  stream: onState => {
    const es = new EventSource("/api/stream");
    es.onmessage = e => onState(JSON.parse(e.data));
    return () => es.close();
  },
  run: id => post(`/claims/${id}/run`),
  runAll: persona => post("/claims/run-all", { persona }),
  reset: id => post(`/claims/${id}/reset`),
  retry: id => post(`/claims/${id}/retry`),
  decide: (id, action) => post(`/claims/${id}/decision`, { action }),
  ingest: sampleId => post("/claims/ingest", { sample_id: sampleId }),
  judge: bill => post("/judge", bill),
  upload: async file => {
    const form = new FormData();
    form.append("file", file);
    const res = await fetch("/api/claims/upload", { method: "POST", body: form });
    const body = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(body.detail || `Upload failed (${res.status})`);
    return body;
  },
};
