import { useCallback } from "react";
import { useAuth } from "../contexts/AuthContext.jsx";
import { localPaperSecret } from "../utils/localDevAuth.js";

const API_SECRET = localPaperSecret();

/** Returns headers for backend API calls. Uses Bearer token when user is logged in; falls back to x-bot-secret in dev. */
export function useAuthHeaders() {
  const { session } = useAuth();
  const accessToken = session?.access_token;
  return useCallback(() => {
    const h = {};
    if (accessToken) h["Authorization"] = `Bearer ${accessToken}`;
    else if (API_SECRET) h["x-bot-secret"] = API_SECRET;
    return h;
  }, [accessToken]);
}

/** Appends ?token= or ?secret= to API URLs (matches WebSocket auth; helps cross-origin fetch). */
export function useAuthUrl() {
  const { session } = useAuth();
  const accessToken = session?.access_token;
  return useCallback((url) => {
    if (!accessToken && !API_SECRET) return url;
    try {
      const u = new URL(url, window.location.origin);
      if (accessToken) u.searchParams.set("token", accessToken);
      else if (API_SECRET) u.searchParams.set("secret", API_SECRET);
      return u.toString();
    } catch {
      const sep = url.includes("?") ? "&" : "?";
      if (accessToken) return `${url}${sep}token=${encodeURIComponent(accessToken)}`;
      if (API_SECRET) return `${url}${sep}secret=${encodeURIComponent(API_SECRET)}`;
      return url;
    }
  }, [accessToken]);
}

/** Returns auth query string for URLs (e.g. img src) where headers can't be sent. */
export function useAuthQueryParam() {
  const { session } = useAuth();
  const accessToken = session?.access_token;
  return useCallback(() => {
    if (accessToken) return `?token=${encodeURIComponent(accessToken)}`;
    if (API_SECRET) return `?secret=${encodeURIComponent(API_SECRET)}`;
    return "";
  }, [accessToken]);
}
