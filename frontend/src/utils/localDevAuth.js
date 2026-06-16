/** Local paper mode: x-bot-secret works on localhost even in production Vite builds (:8000 keep-alive). */
export function localPaperSecret() {
  const secret = import.meta.env.VITE_BOT_API_SECRET || "";
  if (!secret) return "";
  if (import.meta.env.DEV) return secret;
  if (typeof window === "undefined") return "";
  const host = window.location.hostname;
  if (host === "localhost" || host === "127.0.0.1") return secret;
  return "";
}

export function isLocalPaperHost() {
  if (typeof window === "undefined") return false;
  const host = window.location.hostname;
  return host === "localhost" || host === "127.0.0.1";
}
