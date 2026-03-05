import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext.jsx";
import { supabase } from "../supabaseClient.js";

export default function AuthCallback() {
  const { user, profile, loading } = useAuth();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [exchanging, setExchanging] = useState(true);

  useEffect(() => {
    const errorParam = searchParams.get("error");
    const errorDescription = searchParams.get("error_description");

    if (errorParam) {
      console.error("OAuth error:", errorParam, errorDescription);
      navigate("/login?error=" + encodeURIComponent(errorDescription || errorParam), { replace: true });
      return;
    }

    // Set exchanging to false after a slight delay to allow Supabase to populate AuthContext
    // The detectSessionInUrl=true setup in supabaseClient will automatically consume the ?code=
    const timeout = setTimeout(() => {
      setExchanging(false);
      // Clean up URL parameters implicitly by React Router shortly
    }, 1500);

    return () => clearTimeout(timeout);
  }, [searchParams, navigate]);

  useEffect(() => {
    if (exchanging || loading) return;

    if (user && profile?.onboarding_complete) {
      navigate("/dashboard", { replace: true });
    } else if (user) {
      navigate("/onboarding", { replace: true });
    } else {
      navigate("/login", { replace: true });
    }
  }, [user, profile, loading, exchanging, navigate]);

  return (
    <div className="page-loading">
      <span className="page-loading__spinner" />
      Completing sign-in...
    </div>
  );
}
