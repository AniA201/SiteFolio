import React from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import { loadMeta } from "./data";
import "./styles.css";

const root = createRoot(document.getElementById("root"));

loadMeta()
  .then(() => root.render(<App />))
  .catch(err => root.render(
    <div style={{ padding: 40, fontFamily: "system-ui" }}>
      <h2>Plumbline API is not reachable</h2>
      <p>{String(err.message)}. Start the backend on port 8000 and reload.</p>
    </div>
  ));
