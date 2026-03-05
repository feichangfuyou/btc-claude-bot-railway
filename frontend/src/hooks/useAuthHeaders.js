import { useCallback } from "react";
import { useAuth } from "../contexts/AuthContext.jsx";

const API_SECRET = import.meta.env.VITE_BOT_API_SECRET || "";

/** Returns headers for backend API calls. Uses x-bot-secret when set, else Bearer token when user is logged in. */
export function useAuthHeaders() {
  const { session } = useAuth();
  const accessToken = session?.access_token;
  return useCallback(() => {
    const h = {};
    if (API_SECRET) h["x-bot-secret"] = API_SECRET;
    else if (accessToken) h["Authorization"] = `Bearer ${accessToken}`;
    return h;
  }, [accessToken]);
}

/** Returns auth query string for URLs (e.g. img src) where headers can't be sent. */
export function useAuthQueryParam() {
  const { session } = useAuth();
  const accessToken = session?.access_token;
  return useCallback(() => {
    if (API_SECRET) return `?secret=${encodeURIComponent(API_SECRET)}`;
    if (accessToken) return `?token=${encodeURIComponent(accessToken)}`;
    return "";
  }, [accessToken]);
}
