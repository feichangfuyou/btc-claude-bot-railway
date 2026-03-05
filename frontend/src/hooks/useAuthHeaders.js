import { useCallback } from "react";
import { useAuth } from "../contexts/AuthContext.jsx";

// VITE_BOT_API_SECRET is a dev-only shortcut for local single-user testing.
// In production multi-user deployments, leave it unset — Supabase JWT handles auth.
const API_SECRET = import.meta.env.DEV ? (import.meta.env.VITE_BOT_API_SECRET || "") : "";

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
