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
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          // Put all node_modules in a single vendor chunk to avoid circular dependencies between them
          if (id.includes('node_modules')) {
            return 'vendor';
          }
          // Heavy dashboard-only code in its own chunk (NOT loaded on landing page)
          if (
            id.includes('/src/App.jsx') ||
            id.includes('/src/pages/Admin') ||
            id.includes('/src/pages/Settings') ||
            id.includes('/src/pages/Onboarding') ||
            id.includes('/src/components/BottomPanels') ||
            id.includes('/src/components/AnalyticsSection') ||
            id.includes('/src/components/ChartSection') ||
            id.includes('/src/components/PositionsPanel') ||
            id.includes('/src/components/ControlPanel') ||
            id.includes('/src/TradingViewChart')
          ) {
            return 'dashboard';
          }
        }
      }
    },
    // Increase the warning limit since dashboard chunk is intentionally large
    chunkSizeWarningLimit: 1200,
  },
  envDir: "..",  // load .env from project root (where BOT_API_SECRET / VITE_BOT_API_SECRET live)
  server: {
    port: 5173,
    strictPort: true,
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
            socket.on("error", () => { });
            socket.setTimeout(0);
          });
          proxy.on("open", (proxySocket) => {
            proxySocket.on("error", () => { });
            proxySocket.setTimeout(0);
          });
        },
      },
      "/health": httpProxy(),
      "/readiness": httpProxy(),
      "/metrics": httpProxy(),
      "/trades": httpProxy(),
      "/account": httpProxy(),
      "/stats": httpProxy(),
      "/wallet": httpProxy(),
      "/ask_claude": httpProxy(),
      "/memory": httpProxy(),
      "/costs": httpProxy(),
      "/emergency": httpProxy(),
      "/equity": httpProxy(),
      "/snapshots": httpProxy(),
      "/backtest": httpProxy(),
      "/api/preset": httpProxy(),
      "/api/presets": httpProxy(),
      "/api/config": httpProxy(),
      "/api/admin": httpProxy(),
      "/api/trade": httpProxy(),
      "/auth": httpProxy(),
    },
  },
});
