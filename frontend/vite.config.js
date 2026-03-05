import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const backendTarget = "http://localhost:8000";

function silentErrorHandler(err) {
  if (["EPIPE", "ECONNRESET", "ECONNREFUSED", "ECONNABORTED", "ETIMEDOUT"].includes(err.code)) return;
  console.error("[proxy]", err.code || err.message);
}

function httpProxy() {
  return {
    target: backendTarget,
    changeOrigin: true,
    configure: (proxy) => { proxy.on("error", silentErrorHandler); },
  };
}

export default defineConfig({
  plugins: [react()],
  envDir: "..",  // load .env from project root (where BOT_API_SECRET / VITE_BOT_API_SECRET live)
  server: {
    port: 5173,
    proxy: {
      // Demo-mode price feed — Coinbase via backend proxy
      "/api/coinbase": httpProxy(),
      "/api/exchange": httpProxy(),
      "/api/prices": httpProxy(),
      "/api/alternative": {
        target: "https://api.alternative.me",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api\/alternative/, ""),
        configure: (proxy) => { proxy.on("error", silentErrorHandler); },
      },
      "/ws": {
        target: backendTarget,
        ws: true,
        changeOrigin: true,
        timeout: 0,
        configure: (proxy) => {
          proxy.on("error", silentErrorHandler);
          proxy.on("proxyReqWs", (_proxyReq, _req, socket) => {
            socket.on("error", () => {});
            socket.setTimeout(0);
          });
          proxy.on("open", (proxySocket) => {
            proxySocket.on("error", () => {});
            proxySocket.setTimeout(0);
          });
        },
      },
      "/health":     httpProxy(),
      "/readiness":  httpProxy(),
      "/metrics":    httpProxy(),
      "/trades":     httpProxy(),
      "/account":    httpProxy(),
      "/stats":      httpProxy(),
      "/wallet":     httpProxy(),
      "/ask_claude": httpProxy(),
      "/memory":     httpProxy(),
      "/costs":      httpProxy(),
      "/emergency":  httpProxy(),
      "/equity":     httpProxy(),
      "/snapshots":  httpProxy(),
      "/backtest":   httpProxy(),
      "/api/preset": httpProxy(),
      "/api/presets": httpProxy(),
      "/auth":       httpProxy(),
    },
  },
});
