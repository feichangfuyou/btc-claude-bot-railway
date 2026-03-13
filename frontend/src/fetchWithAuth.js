/**
 * Global fetch wrapper: on 401 from backend API, redirect to /login (session expired).
 * Skips redirect when already on login/signup or when request was to auth endpoints.
 */
const _fetch = window.fetch;
window.fetch = async function fetchWithAuthInterceptor(input, init = {}) {
  const url = typeof input === "string" ? input : input?.url ?? "";
  const res = await _fetch.call(this, input, init);
  if (res.status === 401) {
    const path = window.location.pathname || "";
    const isAuthPage = path.startsWith("/login") || path.startsWith("/signup") || path.startsWith("/oauth/");
    const isAuthEndpoint = url.includes("/auth/") || url.includes("/login") || url.includes("/signup");
    if (!isAuthPage && !isAuthEndpoint) {
      window.location.href = "/login";
    }
  }
  return res;
};
