import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider, useAuth } from "./contexts/AuthContext.jsx";
import App from "./App.jsx";
import Login from "./pages/Login.jsx";
import Signup from "./pages/Signup.jsx";
import Onboarding from "./pages/Onboarding.jsx";
import Settings from "./pages/Settings.jsx";
import History from "./pages/History.jsx";
import Billing from "./pages/Billing.jsx";
import AuthCallback from "./pages/AuthCallback.jsx";
import Terms from "./pages/Terms.jsx";
import Privacy from "./pages/Privacy.jsx";
import "./suppress-warnings.js";
import "./capacitor-init.js";
import "./global.css";
import "./styles/auth.css";

function ProtectedRoute({ children }) {
  const { user, profile, loading } = useAuth();

  if (loading) {
    return (
      <div className="page-loading">
        <span className="page-loading__spinner" />
        Loading...
      </div>
    );
  }

  if (!user) return <Navigate to="/login" replace />;
  if (profile && !profile.onboarding_complete) return <Navigate to="/onboarding" replace />;
  return children;
}

function PublicRoute({ children }) {
  const { user, profile, loading } = useAuth();
  if (loading) return null;
  if (user && profile?.onboarding_complete) return <Navigate to="/dashboard" replace />;
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

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<PublicRoute><Login /></PublicRoute>} />
          <Route path="/signup" element={<PublicRoute><Signup /></PublicRoute>} />
          <Route path="/oauth/callback" element={<AuthCallback />} />
          <Route path="/onboarding" element={<OnboardingRoute />} />
          <Route path="/dashboard" element={<ProtectedRoute><App /></ProtectedRoute>} />
          <Route path="/settings" element={<ProtectedRoute><Settings /></ProtectedRoute>} />
          <Route path="/history" element={<ProtectedRoute><History /></ProtectedRoute>} />
          <Route path="/billing" element={<ProtectedRoute><Billing /></ProtectedRoute>} />
          <Route path="/terms" element={<Terms />} />
          <Route path="/privacy" element={<Privacy />} />
          <Route path="/" element={<Navigate to="/dashboard" replace />} />
          <Route path="*" element={<Navigate to="/dashboard" replace />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  </React.StrictMode>
);
