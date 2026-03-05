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
    <div className="page-loading">
      <span className="page-loading__spinner" />
      Completing sign-in...
    </div>
  );
}
