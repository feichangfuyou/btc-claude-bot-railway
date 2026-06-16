import React, { lazy, Suspense } from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Routes, Route, Navigate, useLocation, useSearchParams } from "react-router-dom";
import { AuthProvider, useAuth } from "./contexts/AuthContext.jsx";
import { isAdminEmail } from "./utils/adminEmails.js";

// Eagerly loaded — these are public pages visited on first load
import Login from "./pages/Login.jsx";
import Signup from "./pages/Signup.jsx";
import AuthCallback from "./pages/AuthCallback.jsx";
import Terms from "./pages/Terms.jsx";
import Privacy from "./pages/Privacy.jsx";
import MarketIndex from "./pages/MarketIndex.jsx";

// Lazily loaded — only downloaded when user is authenticated and navigates there
const App = lazy(() => import("./App.jsx"));
const Onboarding = lazy(() => import("./pages/Onboarding.jsx"));
const Settings = lazy(() => import("./pages/Settings.jsx"));
const History = lazy(() => import("./pages/History.jsx"));
const Billing = lazy(() => import("./pages/Billing.jsx"));
const Admin = lazy(() => import("./pages/Admin.jsx"));

import "./suppress-warnings.js";
import "./fetchWithAuth.js";
import "./capacitor-init.js";
import "./global.css";
import "./styles/mobile-app.css";
import "./styles/spacing.css";
import "./styles/auth.css";
import "./styles/pages.css";

// Minimal Suspense fallback — dark background, no flash
function PageFallback() {
  return (
    <div style={{ background: "#050505", minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center", gap: "12px", fontFamily: "'Space Mono',monospace", fontSize: "11px", letterSpacing: "1px", color: "#5C5C5C" }}>
      <span style={{ display: "inline-block", width: "20px", height: "20px", border: "2px solid rgba(255,255,255,0.1)", borderTopColor: "#D4AF37", borderRadius: "50%", animation: "spin 0.6s linear infinite" }} />
      <style>{`@keyframes spin{to{transform:rotate(360deg)}}`}</style>
    </div>
  );
}

function ProtectedRoute({ children }) {
  const { user, profile, loading, localPaper } = useAuth();
  const location = useLocation();

  if (loading) {
    return (
      <div className="page-loading">
        <span className="page-loading__spinner" />
        Loading...
      </div>
    );
  }

  if (!user && !localPaper) return <Navigate to="/login" replace />;
  if (profile && !profile.onboarding_complete && !localPaper) return <Navigate to="/onboarding" replace />;

  const isActive = profile?.subscription_status === "active" || localPaper;
  const isBilling = location.pathname === "/billing";
  const isAdmin = isAdminEmail(user?.email) || localPaper;

  if (!isActive && !isBilling && !isAdmin) {
    return <Navigate to="/billing" replace />;
  }

  return children;
}

function RootRoute() {
  const [searchParams] = useSearchParams();
  const code = searchParams.get("code");
  const oauthErr = searchParams.get("error");
  if (code || oauthErr) {
    return <Navigate to={`/oauth/callback?${searchParams.toString()}`} replace />;
  }
  return (
    <PublicRoute>
      <Login />
    </PublicRoute>
  );
}

function PublicRoute({ children }) {
  const { user, profile, loading, localPaper } = useAuth();
  if (loading) return null;
  if (localPaper || (user && profile?.onboarding_complete)) return <Navigate to="/dashboard" replace />;
  if (user && !profile?.onboarding_complete) return <Navigate to="/onboarding" replace />;
  return children;
}
function OnboardingRoute() {
  const { user, profile, loading } = useAuth();
  if (loading) return null;
  if (!user) return <Navigate to="/login" replace />;
  if (profile?.onboarding_complete) return <Navigate to="/dashboard" replace />;
  return <Onboarding />;
}

function AdminRoute({ children }) {
  const { user, profile, loading } = useAuth();
  if (loading) return null;
  if (!user) return <Navigate to="/login" replace />;
  if (!isAdminEmail(user.email)) {
    return <Navigate to="/dashboard" replace />;
  }
  return children;
}

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <Suspense fallback={<PageFallback />}>
          <Routes>
            <Route path="/login" element={<PublicRoute><Login /></PublicRoute>} />
            <Route path="/signup" element={<PublicRoute><Signup /></PublicRoute>} />
            <Route path="/oauth/callback" element={<AuthCallback />} />
            <Route path="/onboarding" element={<OnboardingRoute />} />
            <Route path="/dashboard" element={<ProtectedRoute><App /></ProtectedRoute>} />
            <Route path="/settings" element={<ProtectedRoute><Settings /></ProtectedRoute>} />
            <Route path="/history" element={<ProtectedRoute><History /></ProtectedRoute>} />
            <Route path="/billing" element={<ProtectedRoute><Billing /></ProtectedRoute>} />
            <Route path="/admin" element={<AdminRoute><Admin /></AdminRoute>} />
            <Route path="/terms" element={<Terms />} />
            <Route path="/privacy" element={<Privacy />} />
            <Route path="/market/:coin" element={<MarketIndex />} />
            <Route path="/" element={<RootRoute />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </Suspense>
      </AuthProvider>
    </BrowserRouter>
  </React.StrictMode>
);
