import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const API = process.env.PLUMBLINE_API || "http://localhost:8787";

export default defineConfig({
  plugins: [react()],
  server: {
    port: Number(process.env.PORT) || 5180,
    proxy: { "/api": API },
  },
});
