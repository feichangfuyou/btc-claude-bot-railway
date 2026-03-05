import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext.jsx";

export default function Login() {
  const { signIn, signInWithGoogle, signInWithApple } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPw, setShowPw] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [oauthLoading, setOauthLoading] = useState(null);
  const [resetSent, setResetSent] = useState(false);

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
    <>
      <style>{cssText}</style>
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
    </>
  );
}

const cssText = `
.auth-page {
  font-family: 'Space Mono', monospace;
  background: #0A0A0A;
  color: #D4D4D4;
  min-height: 100vh;
  min-height: 100dvh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px 16px;
  position: relative;
  overflow: hidden;
}
.auth-page::before {
  content: '';
  position: fixed;
  top: -40%;
  left: -20%;
  width: 80%;
  height: 80%;
  background: radial-gradient(ellipse, rgba(212,175,55,0.04) 0%, transparent 70%);
  pointer-events: none;
  animation: authAmbient 15s ease infinite;
}
.auth-page::after {
  content: '';
  position: fixed;
  bottom: -30%;
  right: -20%;
  width: 70%;
  height: 70%;
  background: radial-gradient(ellipse, rgba(192,57,43,0.025) 0%, transparent 70%);
  pointer-events: none;
  animation: authAmbient 20s ease infinite reverse;
}
@keyframes authAmbient {
  0% { transform: translate(0, 0) scale(1); }
  33% { transform: translate(5%, -3%) scale(1.05); }
  66% { transform: translate(-3%, 5%) scale(0.95); }
  100% { transform: translate(0, 0) scale(1); }
}
@keyframes authCardIn {
  from { opacity: 0; transform: translateY(12px) scale(0.97); }
  to { opacity: 1; transform: translateY(0) scale(1); }
}
@keyframes glassShimmer {
  0% { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}

.auth-card {
  background: rgba(17, 17, 17, 0.6);
  backdrop-filter: blur(40px) saturate(1.6);
  -webkit-backdrop-filter: blur(40px) saturate(1.6);
  border: 1px solid rgba(212, 175, 55, 0.1);
  border-radius: 24px;
  padding: 40px 32px 32px;
  width: 100%;
  max-width: 420px;
  box-shadow: 0 24px 80px rgba(0,0,0,0.5), 0 0 0 1px rgba(255,255,255,0.03), inset 0 1px 0 rgba(255,255,255,0.06);
  position: relative;
  z-index: 1;
  animation: authCardIn 0.5s cubic-bezier(0.4, 0, 0.2, 1);
}

.auth-header {
  display: flex;
  align-items: center;
  gap: 14px;
  margin-bottom: 32px;
}

.auth-logo {
  width: 52px;
  height: 52px;
  flex-shrink: 0;
  filter: drop-shadow(0 0 12px rgba(212,175,55,0.15));
}

.auth-brand {
  font-family: 'Bebas Neue', sans-serif;
  font-size: 30px;
  font-weight: 400;
  letter-spacing: 5px;
  color: #D4AF37;
  line-height: 1;
}

.auth-tagline {
  font-size: 11px;
  color: #5C5C5C;
  letter-spacing: 1.5px;
  margin-top: 2px;
}

.auth-alert {
  font-size: 12px;
  border-radius: 10px;
  padding: 10px 14px;
  margin-bottom: 16px;
  line-height: 1.5;
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
}
.auth-alert--error {
  color: #E74C3C;
  background: rgba(231,76,60,0.08);
  border: 1px solid rgba(231,76,60,0.2);
}
.auth-alert--success {
  color: #27AE60;
  background: rgba(39,174,96,0.08);
  border: 1px solid rgba(39,174,96,0.2);
}

.auth-oauth {
  font-family: 'Space Mono', monospace;
  font-size: 13px;
  padding: 12px 0;
  width: 100%;
  background: rgba(255,255,255,0.04);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  border: 1px solid rgba(255,255,255,0.08);
  border-radius: 12px;
  color: #D4D4D4;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
  margin-bottom: 8px;
}
.auth-oauth:hover:not(:disabled) {
  background: rgba(255,255,255,0.07);
  border-color: rgba(255,255,255,0.15);
  box-shadow: 0 4px 16px rgba(0,0,0,0.2);
  transform: translateY(-1px);
}
.auth-oauth:active:not(:disabled) {
  transform: scale(0.985);
}
.auth-oauth:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.auth-oauth--apple {
  background: rgba(0,0,0,0.5);
  border-color: rgba(255,255,255,0.1);
  color: #fff;
}
.auth-oauth--apple:hover:not(:disabled) {
  background: rgba(0,0,0,0.6);
  border-color: rgba(255,255,255,0.18);
}

.auth-divider {
  display: flex;
  align-items: center;
  gap: 12px;
  margin: 20px 0;
}
.auth-divider__line {
  flex: 1;
  height: 1px;
  background: linear-gradient(90deg, transparent, rgba(255,255,255,0.08), transparent);
}
.auth-divider__text {
  font-size: 10px;
  color: #444;
  letter-spacing: 1px;
  text-transform: uppercase;
  white-space: nowrap;
}

.auth-form {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.auth-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.auth-label {
  font-size: 10px;
  color: #666;
  letter-spacing: 1.5px;
  text-transform: uppercase;
}

.auth-label-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.auth-forgot {
  font-family: 'Space Mono', monospace;
  font-size: 10px;
  color: #D4AF37;
  background: none;
  border: none;
  cursor: pointer;
  letter-spacing: 0.5px;
  padding: 0;
  transition: opacity 0.2s;
}
.auth-forgot:hover {
  opacity: 0.7;
}

.auth-input {
  font-family: 'Space Mono', monospace;
  font-size: 13px;
  padding: 12px 14px;
  background: rgba(10,10,10,0.6);
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
  border: 1px solid rgba(255,255,255,0.06);
  border-radius: 10px;
  color: #D4D4D4;
  outline: none;
  transition: border-color 0.2s ease, box-shadow 0.2s ease, background 0.2s ease;
  width: 100%;
  box-sizing: border-box;
}
.auth-input:focus {
  border-color: rgba(212,175,55,0.4);
  box-shadow: 0 0 0 3px rgba(212,175,55,0.08);
  background: rgba(10,10,10,0.8);
}
.auth-input::placeholder {
  color: #333;
}

.auth-input-wrap {
  position: relative;
  display: flex;
}
.auth-input--pw {
  padding-right: 60px;
}
.auth-eye {
  position: absolute;
  right: 2px;
  top: 2px;
  bottom: 2px;
  width: 52px;
  background: transparent;
  border: none;
  color: #555;
  font-family: 'Space Mono', monospace;
  font-size: 9px;
  letter-spacing: 1px;
  cursor: pointer;
  border-radius: 8px;
  transition: color 0.2s;
}
.auth-eye:hover {
  color: #D4AF37;
}

.auth-submit {
  font-family: 'Oswald', sans-serif;
  font-size: 14px;
  font-weight: 600;
  letter-spacing: 2px;
  text-transform: uppercase;
  padding: 14px 0;
  border: none;
  border-radius: 12px;
  cursor: pointer;
  background: linear-gradient(180deg, #D4AF37, #B8860B);
  color: #0A0A0A;
  margin-top: 4px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
  box-shadow: 0 4px 20px rgba(212,175,55,0.2);
  position: relative;
  overflow: hidden;
}
.auth-submit::before {
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(135deg, transparent 40%, rgba(255,255,255,0.15) 50%, transparent 60%);
  background-size: 200% 100%;
  opacity: 0;
  transition: opacity 0.3s;
}
.auth-submit:hover:not(:disabled)::before {
  opacity: 1;
  animation: glassShimmer 1.5s ease infinite;
}
.auth-submit:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 8px 28px rgba(212,175,55,0.3);
}
.auth-submit:active:not(:disabled) {
  transform: scale(0.97);
}
.auth-submit:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

@keyframes auth-spin {
  to { transform: rotate(360deg); }
}
.auth-spinner {
  display: inline-block;
  width: 16px;
  height: 16px;
  border: 2px solid rgba(255,255,255,0.2);
  border-top-color: #fff;
  border-radius: 50%;
  animation: auth-spin 0.6s linear infinite;
  flex-shrink: 0;
}
.auth-spinner--dark {
  border-color: rgba(10,10,10,0.2);
  border-top-color: #0A0A0A;
}

.auth-footer {
  font-size: 12px;
  color: #5C5C5C;
  text-align: center;
  margin-top: 20px;
}

.auth-link {
  color: #D4AF37;
  text-decoration: none;
  transition: opacity 0.2s;
}
.auth-link:hover {
  opacity: 0.8;
}

@media (max-width: 600px) {
  .auth-page {
    padding: 16px 12px;
    align-items: flex-start;
    padding-top: calc(16px + env(safe-area-inset-top, 0px));
  }
  .auth-card {
    padding: 28px 20px 24px;
    border-radius: 20px;
    max-width: 100%;
    width: 100%;
  }
  .auth-brand { font-size: 26px; letter-spacing: 3px; }
  .auth-logo { width: 44px; height: 44px; }
  .auth-oauth { padding: 14px 0; font-size: 14px; min-height: 48px; }
  .auth-input { padding: 14px; font-size: 16px; }
  .auth-submit { padding: 16px 0; font-size: 15px; min-height: 50px; }
}
@media (max-width: 375px) {
  .auth-page {
    padding: 8px 6px;
    padding-top: calc(8px + env(safe-area-inset-top, 0px));
  }
  .auth-card {
    padding: 24px 16px 20px;
    border-radius: 16px;
    max-width: 100%;
  }
  .auth-brand { font-size: 24px; letter-spacing: 2px; }
  .auth-logo { width: 40px; height: 40px; }
  .auth-tagline { font-size: 10px; letter-spacing: 1px; }
  .auth-header { gap: 10px; margin-bottom: 24px; }
}
@media (max-width: 320px) {
  .auth-page { padding: 6px 4px; padding-top: calc(6px + env(safe-area-inset-top, 0px)); }
  .auth-card { padding: 20px 12px 16px; border-radius: 12px; }
  .auth-brand { font-size: 22px; letter-spacing: 1px; }
  .auth-tagline { font-size: 9px; letter-spacing: 0.5px; }
  .auth-divider__text { font-size: 9px; letter-spacing: 0.5px; }
  .auth-divider { margin: 14px 0; }
  .auth-oauth { font-size: 12px; gap: 6px; }
  .auth-footer { font-size: 11px; }
  .auth-header { gap: 8px; margin-bottom: 20px; }
  .auth-form { gap: 12px; }
}
`;
