import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext.jsx";
import { supabase } from "../supabaseClient.js";
import { localPaperSecret } from "../utils/localDevAuth.js";

function oauthErrorMessage(error) {
  const status = error?.status || error?.code;
  const msg = error?.message || String(error);
  if (status === 402 || msg.includes("402")) {
    return (
      "Sign-in blocked by Supabase (402 — billing or quota). " +
      "Check your Supabase project dashboard, or use “Local paper login” on the login page."
    );
  }
  return msg || "OAuth sign-in failed";
}

export default function AuthCallback() {
  const { user, profile, loading, enterLocalPaper } = useAuth();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [exchanging, setExchanging] = useState(true);
  const [exchangeError, setExchangeError] = useState("");

  useEffect(() => {
    const errorParam = searchParams.get("error");
    const errorDescription = searchParams.get("error_description");
    const code = searchParams.get("code");

    if (errorParam) {
      navigate("/login?error=" + encodeURIComponent(errorDescription || errorParam), { replace: true });
      return;
    }

    if (!code) {
      setExchanging(false);
      return;
    }

    let cancelled = false;
    (async () => {
      const { error } = await supabase.auth.exchangeCodeForSession(code);
      if (cancelled) return;
      if (error) {
        setExchangeError(oauthErrorMessage(error));
        setExchanging(false);
        return;
      }
      setExchanging(false);
    })();

    return () => { cancelled = true; };
  }, [searchParams, navigate]);

  useEffect(() => {
    if (exchanging || loading) return;

    if (exchangeError) {
      if (localPaperSecret()) {
        enterLocalPaper();
        navigate("/dashboard", { replace: true });
        return;
      }
      navigate("/login?error=" + encodeURIComponent(exchangeError), { replace: true });
      return;
    }

    if (user && profile?.onboarding_complete) {
      navigate("/dashboard", { replace: true });
    } else if (user) {
      navigate("/onboarding", { replace: true });
    } else {
      navigate("/login", { replace: true });
    }
  }, [user, profile, loading, exchanging, exchangeError, navigate, enterLocalPaper]);

  return (
    <div className="page-loading">
      <span className="page-loading__spinner" />
      {exchangeError ? "OAuth failed — switching to local paper…" : "Completing sign-in…"}
    </div>
  );
}
