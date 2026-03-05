import { useState, useEffect } from "react";
import { useNavigate, Link, useSearchParams } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext.jsx";

export default function Login() {
  const { signIn, signInWithGoogle, signInWithApple } = useAuth();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPw, setShowPw] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [oauthLoading, setOauthLoading] = useState(null);
  const [resetSent, setResetSent] = useState(false);

  useEffect(() => {
    const err = searchParams.get("error");
    if (err) {
      setError(decodeURIComponent(err));
      setSearchParams({}, { replace: true });
    }
  }, [searchParams, setSearchParams]);

  async function handleSubmit(e) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await signIn(email, password);
      navigate("/dashboard");
    } catch (err) {
      setError(err.message || "Invalid credentials");
    } finally {
      setLoading(false);
    }
  }

  async function handleOAuth(provider) {
    setError("");
    setOauthLoading(provider);
    try {
      if (provider === "google") await signInWithGoogle();
      else await signInWithApple();
    } catch (err) {
      setError(err.message || `${provider} sign-in failed`);
      setOauthLoading(null);
    }
  }

  async function handleForgotPassword() {
    if (!email) {
      setError("Enter your email first, then click Forgot Password.");
      return;
    }
    setError("");
    try {
      const { supabase } = await import("../supabaseClient.js");
      const { error: resetError } = await supabase.auth.resetPasswordForEmail(email, {
        redirectTo: window.location.origin + "/login",
      });
      if (resetError) throw resetError;
      setResetSent(true);
    } catch (err) {
      setError(err.message || "Could not send reset email");
    }
  }

  return (
    <div className="auth-page">
        <div className="auth-card">
          <div className="auth-header">
            <img src="/Bravo.svg" alt="DoYou.trade" className="auth-logo" />
            <div>
              <div className="auth-brand">DOYOU.TRADE</div>
              <div className="auth-tagline">AI-Powered Crypto Trading</div>
            </div>
          </div>

          {error && <div className="auth-alert auth-alert--error">{error}</div>}
          {resetSent && (
            <div className="auth-alert auth-alert--success">
              Password reset link sent — check your inbox.
            </div>
          )}

          {/* --- OAuth buttons first for conversion --- */}
          <button
            className="auth-oauth"
            onClick={() => handleOAuth("google")}
            disabled={!!oauthLoading}
          >
            {oauthLoading === "google" ? (
              <span className="auth-spinner" />
            ) : (
              <svg width="18" height="18" viewBox="0 0 24 24">
                <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z"/>
                <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
                <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/>
                <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
              </svg>
            )}
            Continue with Google
          </button>

          <button
            className="auth-oauth auth-oauth--apple"
            onClick={() => handleOAuth("apple")}
            disabled={!!oauthLoading}
          >
            {oauthLoading === "apple" ? (
              <span className="auth-spinner" />
            ) : (
              <svg width="18" height="18" viewBox="0 0 24 24" fill="white">
                <path d="M17.05 20.28c-.98.95-2.05.88-3.08.4-1.09-.5-2.08-.48-3.24 0-1.44.62-2.2.44-3.06-.4C2.79 15.25 3.51 7.59 9.05 7.31c1.35.07 2.29.74 3.08.8 1.18-.24 2.31-.93 3.57-.84 1.51.12 2.65.72 3.4 1.8-3.12 1.87-2.38 5.98.48 7.13-.57 1.5-1.31 2.99-2.54 4.09zM12.03 7.25c-.15-2.23 1.66-4.07 3.74-4.25.29 2.58-2.34 4.5-3.74 4.25z"/>
              </svg>
            )}
            Continue with Apple
          </button>

          <div className="auth-divider">
            <span className="auth-divider__line" />
            <span className="auth-divider__text">or sign in with email</span>
            <span className="auth-divider__line" />
          </div>

          <form onSubmit={handleSubmit} className="auth-form">
            <div className="auth-field">
              <label className="auth-label" htmlFor="login-email">Email</label>
              <input
                id="login-email"
                type="email"
                placeholder="you@example.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                className="auth-input"
                autoComplete="email"
              />
            </div>

            <div className="auth-field">
              <div className="auth-label-row">
                <label className="auth-label" htmlFor="login-pw">Password</label>
                <button
                  type="button"
                  className="auth-forgot"
                  onClick={handleForgotPassword}
                >
                  Forgot?
                </button>
              </div>
              <div className="auth-input-wrap">
                <input
                  id="login-pw"
                  type={showPw ? "text" : "password"}
                  placeholder="Enter password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  className="auth-input auth-input--pw"
                  autoComplete="current-password"
                />
                <button
                  type="button"
                  className="auth-eye"
                  onClick={() => setShowPw(!showPw)}
                  tabIndex={-1}
                  aria-label={showPw ? "Hide password" : "Show password"}
                >
                  {showPw ? "HIDE" : "SHOW"}
                </button>
              </div>
            </div>

            <button type="submit" disabled={loading} className="auth-submit">
              {loading ? <span className="auth-spinner auth-spinner--dark" /> : null}
              {loading ? "Signing in..." : "Sign In"}
            </button>
          </form>

          <div className="auth-footer">
            Don&apos;t have an account?{" "}
            <Link to="/signup" className="auth-link">Sign Up</Link>
          </div>
        </div>
      </div>
  );
}
