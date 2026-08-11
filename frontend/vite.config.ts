import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In docker-compose the API is reachable at http://api:8000; locally it's
// http://localhost:8000. The dev server proxies API paths so the browser only
// ever talks to a single origin (no CORS needed).
const target = process.env.VITE_PROXY_TARGET || "http://localhost:8000";
const port = Number(process.env.FRONTEND_PORT) || 5173;

export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port,
    watch: { usePolling: true, interval: 300 },
    proxy: {
      "/auth": target,
      "/admin": target,
      "/reports": target,
      "/health": target,
    },
  },
});
