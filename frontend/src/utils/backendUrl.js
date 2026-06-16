/** Production API when VITE_BACKEND_URL is unset (Vercel static hosting has no /api proxy). */
export const PROD_BACKEND = "https://api.doyou.trade";
export const PROD_WS = "wss://api.doyou.trade/ws";

export function getBackendBase() {
  const fromEnv = (import.meta.env.VITE_BACKEND_URL || "").replace(/\/$/, "");
  if (fromEnv) return fromEnv;
  if (import.meta.env.DEV) return "";
  return PROD_BACKEND;
}

export function getWsBase() {
  if (import.meta.env.VITE_WS_URL) return import.meta.env.VITE_WS_URL.replace(/\/$/, "");
  const base = getBackendBase();
  if (base) {
    try {
      const u = new URL(base);
      const proto = u.protocol === "https:" ? "wss:" : "ws:";
      return `${proto}//${u.host}/ws`;
    } catch { /* fall through */ }
  }
  if (import.meta.env.DEV) return "ws://127.0.0.1:8000/ws";
  return PROD_WS;
}
