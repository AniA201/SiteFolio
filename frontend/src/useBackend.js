import { useEffect, useRef, useState } from "react";
import { api } from "./api";

const EMPTY = { rev: -1, claims: [], samples: [], steps: {}, status: {}, review: {}, retry: {}, log: [], queue: [], current: null };

// Live mirror of the backend's claim state: one snapshot on load, then one per change over SSE.
export function useBackend() {
  const [state, setState] = useState(EMPTY);
  const rev = useRef(-1);
  const apply = s => { if (s && s.rev >= rev.current) { rev.current = s.rev; setState(s); } return s; };

  useEffect(() => {
    api.state().then(apply);
    return api.stream(apply);
  }, []);

  return [state, apply];
}
