import { useState, useEffect, useRef } from "react";
import { useNavigate, Link } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext.jsx";
import { colors } from "../theme.js";
import { PublicNav } from "../components/PublicNav.jsx";
import { PublicFooter } from "../components/PublicFooter.jsx";

// Minimal Ticker for Landing — rAF-driven for butter-smooth scroll
function LandingTicker() {
  const symbols = ["BTC", "ETH", "SOL", "DOGE", "LINK", "AVAX", "PEPE", "WIF", "BONK", "AAPL", "TSLA", "NVDA"];
  // Initialize prices once
  const [items] = useState(() => {
    const all = [...symbols, ...symbols];
    return all.map((s, i) => ({
      key: i,
      sym: s,
      price: (Math.random() * 1000 + 10).toFixed(2),
      chg: (Math.random() * 5).toFixed(2),
    }));
  });

  const trackRef = useRef(null);
  const rafRef = useRef(null);
  const offsetRef = useRef(0);
  const lastTsRef = useRef(null);
  const halfWidthRef = useRef(0);

  useEffect(() => {
    function tick(ts) {
      rafRef.current = requestAnimationFrame(tick);
      const track = trackRef.current;
      if (!track) { lastTsRef.current = ts; return; }
      if (!halfWidthRef.current) {
        const tw = track.scrollWidth;
        if (tw > 0) halfWidthRef.current = tw / 2;
      }
      const dt = lastTsRef.current != null ? Math.min(ts - lastTsRef.current, 100) : 0;
      lastTsRef.current = ts;
      if (halfWidthRef.current > 0 && dt > 0) {
        offsetRef.current += (50 / 1000) * dt;
        if (offsetRef.current >= halfWidthRef.current) offsetRef.current -= halfWidthRef.current;
      }
      track.style.transform = `translate3d(${-offsetRef.current}px, 0, 0)`;
    }
    rafRef.current = requestAnimationFrame(tick);
    return () => { if (rafRef.current) cancelAnimationFrame(rafRef.current); };
  }, []);

  return (
    <div style={{ background: "rgba(212,175,55,0.03)", borderTop: "1px solid rgba(212,175,55,0.1)", borderBottom: "1px solid rgba(212,175,55,0.1)", padding: "10px 0", marginBottom: "0", overflow: "hidden" }}>
      <div
        ref={trackRef}
        style={{ display: "flex", gap: "40px", width: "max-content", willChange: "transform", backfaceVisibility: "hidden", WebkitFontSmoothing: "antialiased" }}
      >
        {items.map((item) => (
          <div key={item.key} style={{ display: "flex", alignItems: "center", gap: "8px", fontSize: "11px", fontWeight: "700", color: "#666", whiteSpace: "nowrap" }}>
            <span style={{ color: colors.gold }}>{item.sym}</span>
            <span>${item.price}</span>
            <span style={{ color: "#00E676" }}>+{item.chg}%</span>
          </div>
        ))}
      </div>
    </div>
  );
}


export default function Signup() {
  const { signUp, signInWithGoogle, signInWithApple } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [showPw, setShowPw] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [loading, setLoading] = useState(false);
  const [oauthLoading, setOauthLoading] = useState(null);
  
  useEffect(() => {
    document.title = "Join DoYou.trade — Create Your Advanced Trading Account";
    const meta = document.querySelector('meta[name="description"]');
    if (meta) meta.setAttribute("content", "Start your non-custodial trading journey today. Create a secure, professional-grade account on DoYou.trade and automate your crypto portfolio with institutional speed.");
  }, []);

  async function handleSubmit(e) {
    e.preventDefault();
    setError("");
    setSuccess("");

    if (password !== confirm) {
      setError("Passwords don't match");
      return;
    }
    if (password.length < 6) {
      setError("Password must be at least 6 characters");
      return;
    }

    setLoading(true);
    try {
      const data = await signUp(email, password);
      if (data.user && !data.session) {
        setSuccess("Check your email for a confirmation link.");
      } else {
        navigate("/onboarding");
      }
    } catch (err) {
      setError(err.message || "Signup failed");
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

  const pwStrength = password.length === 0 ? 0 : password.length < 6 ? 1 : password.length < 10 ? 2 : 3;
  const strengthColor = ["transparent", "#FF1744", "#D4AF37", "#00E676"][pwStrength];

  return (
    <div className="landing-container">
      <PublicNav />

      <div style={{ paddingTop: "24px" }}>
        <LandingTicker />
      </div>

      <header className="landing-hero">
        <div className="hero-text">
          <div className="hero-badges">
            <span className="hero-badge">NON-CUSTODIAL</span>
            <span className="hero-badge">SECURE</span>
            <span className="hero-badge">SCALABLE</span>
          </div>
          <h1>START YOUR TRADING JOURNEY.</h1>
          <p>
            Create your account in seconds and unlock the power of automated trading. 
            Connect your favorite exchanges and let our systems do the heavy lifting.
          </p>
          <div style={{ display: "flex", gap: "16px", marginBottom: "40px", justifyContent: "center", flexWrap: "wrap" }}>
            <button className="btn btn-r" onClick={() => document.getElementById('signup-card').scrollIntoView({ behavior: 'smooth' })}>CREATE ACCOUNT &rarr;</button>
          </div>
        </div>

        <div className="hero-auth" id="signup-card">
          <div className="auth-card" style={{ margin: 0, animation: "none", boxShadow: "0 0 100px rgba(212,175,55,0.15)" }}>
            <div className="auth-header">
              <div>
                <div className="auth-brand" style={{ fontSize: "24px" }}>SIGN UP</div>
                <div className="auth-tagline">Create your automated trading terminal</div>
              </div>
            </div>

            {error && <div className="auth-alert auth-alert--error">{error}</div>}
            {success && <div className="auth-alert auth-alert--success">{success}</div>}

            <button
              className="auth-oauth"
              onClick={() => handleOAuth("google")}
              disabled={!!oauthLoading}
            >
              {oauthLoading === "google" ? <span className="auth-spinner" /> : (
                <svg width="18" height="18" viewBox="0 0 24 24">
                  <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z"/>
                  <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
                  <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/>
                  <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
                </svg>
              )}
              Continue with Google
            </button>

            <div className="auth-divider">
              <span className="auth-divider__line" />
              <span className="auth-divider__text">or email</span>
              <span className="auth-divider__line" />
            </div>

            <form onSubmit={handleSubmit} className="auth-form">
              <div className="auth-field">
                <input
                  type="email"
                  placeholder="Email address"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                  className="auth-input"
                />
              </div>

              <div className="auth-field">
                <div className="auth-input-wrap">
                  <input
                    type={showPw ? "text" : "password"}
                    placeholder="Password (min 6 chars)"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    required
                    className="auth-input auth-input--pw"
                  />
                  <button
                    type="button"
                    className="auth-eye"
                    onClick={() => setShowPw(!showPw)}
                  >
                    {showPw ? "HIDE" : "SHOW"}
                  </button>
                </div>
                {password.length > 0 && (
                  <div className="auth-strength" style={{ marginTop: "4px" }}>
                    <div className="auth-strength__track"><div className="auth-strength__bar" style={{ width: `${(pwStrength / 3) * 100}%`, background: strengthColor }} /></div>
                  </div>
                )}
              </div>

              <div className="auth-field">
                <input
                  type={showPw ? "text" : "password"}
                  placeholder="Confirm Password"
                  value={confirm}
                  onChange={(e) => setConfirm(e.target.value)}
                  required
                  className="auth-input"
                />
              </div>

              <button type="submit" disabled={loading} className="auth-submit">
                {loading ? "CREATING..." : "CREATE ACCOUNT"}
              </button>
            </form>

            <div className="auth-footer" style={{ borderTop: "1px solid rgba(255,255,255,0.05)", paddingTop: "16px", marginTop: "16px" }}>
              Already have an account? <Link to="/login" className="auth-link">Sign In</Link>
            </div>
          </div>
        </div>
      </header>

      <section id="features" className="landing-stats">
        <div className="stats-grid">
          <div className="stat-item">
            <h4>$2.4B</h4>
            <p>VOLUME TRADED</p>
          </div>
          <div className="stat-item">
            <h4>2.4ms</h4>
            <p>EXECUTION SPEED</p>
          </div>
          <div className="stat-item">
            <h4>12k+</h4>
            <p>ACTIVE USERS</p>
          </div>
          <div className="stat-item">
            <h4>99.9%</h4>
            <p>UPTIME</p>
          </div>
        </div>
      </section>

      <PublicFooter />
    </div>
  );
}
