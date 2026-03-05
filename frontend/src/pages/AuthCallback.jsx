import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext.jsx";

export default function AuthCallback() {
  const { user, profile, loading } = useAuth();
  const navigate = useNavigate();

  useEffect(() => {
    if (loading) return;

    if (user && profile?.onboarding_complete) {
      navigate("/dashboard", { replace: true });
    } else if (user) {
      navigate("/onboarding", { replace: true });
    } else {
      navigate("/login", { replace: true });
    }
  }, [user, profile, loading, navigate]);

  return (
    <div style={{
      fontFamily: "'Space Mono', monospace",
      background: "#0A0A0A",
      color: "#5C5C5C",
      minHeight: "100vh",
      display: "flex",
      flexDirection: "column",
      alignItems: "center",
      justifyContent: "center",
      gap: 16,
      fontSize: 12,
      letterSpacing: 1,
    }}>
      <span style={{
        display: "inline-block",
        width: 24,
        height: 24,
        border: "2px solid #1E1E1E",
        borderTopColor: "#D4AF37",
        borderRadius: "50%",
        animation: "auth-cb-spin 0.6s linear infinite",
      }} />
      Completing sign-in...
      <style>{`@keyframes auth-cb-spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}
