import { useState, useEffect, useRef, useMemo } from "react";
import { useNavigate, Link, useSearchParams } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext.jsx";
import { colors } from "../theme.js";
import { Cpu, Shield, Zap, ArrowUp, ArrowRight } from "lucide-react";

// Minimal Ticker for Landing if the main one is too heavy
function LandingTicker() {
  const symbols = ["BTC", "ETH", "SOL", "DOGE", "LINK", "AVAX", "PEPE", "WIF", "BONK", "AAPL", "TSLA", "NVDA"];
  // Initialize prices once using lazy state to avoid react-hooks/purity warnings
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
        className="landing-ticker-track"
        style={{ display: "flex", width: "max-content", willChange: "transform", backfaceVisibility: "hidden", WebkitFontSmoothing: "antialiased" }}
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

export default function Login() {
  const { user, signIn, signInWithGoogle, signInWithApple } = useAuth();
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
    document.title = "DoYou.trade — Professional Crypto Trading Terminal | Institutional Intelligence";
    const meta = document.querySelector('meta[name="description"]');
    if (meta) meta.setAttribute("content", "DoYou.trade — The world's most advanced non-custodial trading terminal. Automate your crypto strategy with professional-grade algorithmic systems. Connect your exchange and trade like a pro.");
    
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
    <div className="landing-container" style={{ paddingBottom: "100px" }}>
      <nav className="landing-nav">
        <Link to="/" className="landing-nav__logo">
          <img src="/Bravo.svg" alt="DoYou.trade Professional Trading System" style={{ width: "32px" }} />
          <span className="auth-brand" style={{ fontSize: "20px", letterSpacing: "3px" }}>DOYOU.TRADE</span>
        </Link>
        <div style={{ display: "flex", gap: "20px", alignItems: "center" }}>
           <a href="#features" className="auth-link" style={{ fontSize: "11px", letterSpacing: "1px" }}>FEATURES</a>
           <Link to="/signup" className="btn btn-r" style={{ padding: "8px 16px", fontSize: "10px", borderRadius: "100px" }}>GET STARTED</Link>
        </div>
      </nav>

      <div style={{ paddingTop: "80px" }}>
        <LandingTicker />
      </div>

      <header className="landing-hero">
        <div className="hero-text">
          <div className="hero-badges">
            <span className="hero-badge">PREMIUM EXECUTION</span>
            <span className="hero-badge">PROPRIETARY STRATEGY ENGINE</span>
            <span className="hero-badge">24/7 AUTOMATED</span>
          </div>
          <h1>ADVANCED CRYPTO TRADING TERMINAL.</h1>
          <p>
            DoYou.trade is a premier non-custodial trading terminal that monitors global markets 24/7. 
            Integrated with a sophisticated execution model to analyze sentiment, technical indicators, 
            and global macro trends to execute high-precision trades automatically.
          </p>
          <div style={{ display: "flex", gap: "16px", marginBottom: "40px", justifyContent: "center", flexWrap: "wrap" }}>
            <button className="btn btn-r" onClick={() => document.getElementById('login-card').scrollIntoView({ behavior: 'smooth' })} aria-label="Start Trading Now" style={{ display: "flex", alignItems: "center", gap: "10px", padding: "16px 32px", fontSize: "14px" }}>START TRADING NOW <ArrowRight size={18} /></button>
          </div>
          <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: "10px", opacity: 0.45 }}>
            <div style={{ display: "flex", gap: "32px", justifyContent: "center", alignItems: "center", flexWrap: "wrap" }}>
              {/* Coinbase */}
              <svg aria-label="Trade Bitcoin on Coinbase" width="100" height="24" viewBox="0 0 100 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                <circle cx="12" cy="12" r="12" fill="#0052FF"/>
                <path d="M12 6C8.69 6 6 8.69 6 12C6 15.31 8.69 18 12 18C14.97 18 17.44 15.97 17.9 13.2H15.33C14.93 14.56 13.58 15.56 12 15.56C10.03 15.56 8.44 13.97 8.44 12C8.44 10.03 10.03 8.44 12 8.44C13.58 8.44 14.93 9.44 15.33 10.8H17.9C17.44 8.03 14.97 6 12 6Z" fill="white"/>
                <text x="28" y="17" fontFamily="'Space Mono', monospace" fontSize="12" fontWeight="700" fill="#aaa" letterSpacing="1">COINBASE</text>
              </svg>
              {/* Binance */}
              <svg aria-label="Automate Binance Trading" width="90" height="24" viewBox="0 0 90 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                <path d="M12 2L14.5 4.5L9.5 9.5L7 7L12 2Z" fill="#F3BA2F"/>
                <path d="M16.5 6.5L19 9L12 16L5 9L7.5 6.5L12 11L16.5 6.5Z" fill="#F3BA2F"/>
                <path d="M9.5 14.5L12 17L14.5 14.5L17 17L12 22L7 17L9.5 14.5Z" fill="#F3BA2F"/>
                <path d="M19.5 9.5L22 12L19.5 14.5L17 12L19.5 9.5Z" fill="#F3BA2F"/>
                <path d="M2 12L4.5 9.5L7 12L4.5 14.5L2 12Z" fill="#F3BA2F"/>
                <text x="28" y="17" fontFamily="'Space Mono', monospace" fontSize="12" fontWeight="700" fill="#aaa" letterSpacing="1">BINANCE</text>
              </svg>
              {/* Kraken */}
              <svg aria-label="Kraken Trading Systems" width="80" height="24" viewBox="0 0 80 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                <circle cx="12" cy="12" r="12" fill="#5741D9"/>
                <text x="6" y="16" fontFamily="Arial" fontSize="10" fontWeight="900" fill="white">K</text>
                <text x="26" y="17" fontFamily="'Space Mono', monospace" fontSize="12" fontWeight="700" fill="#aaa" letterSpacing="1">KRAKEN</text>
              </svg>
            </div>
            <span style={{ fontSize: "10px", letterSpacing: "2px", color: "#555", fontWeight: "600" }}>
              + MANY MORE EXCHANGES COMING SOON
            </span>
          </div>
        </div>

        <div className="hero-auth" id="login-card">
          <div className="auth-card" style={{ margin: 0, animation: "none", boxShadow: "0 0 100px rgba(212,175,55,0.15)" }}>
            <div className="auth-header">
              <div>
                <div className="auth-brand" style={{ fontSize: "24px" }}>{user ? "WELCOME BACK" : "SIGN IN"}</div>
                <div className="auth-tagline">{user ? user.email : "Access your trading terminal"}</div>
              </div>
            </div>

            {user ? (
              <div style={{ textAlign: "center", padding: "20px 0" }}>
                <p style={{ fontSize: "14px", color: "#888", marginBottom: "24px" }}>
                  You are already signed in. Ready to monitor the markets?
                </p>
                  <button 
                    className="btn btn-r" 
                    onClick={() => navigate("/dashboard")}
                    style={{ width: "100%", padding: "16px", display: "flex", alignItems: "center", justifyContent: "center", gap: "10px" }}
                    aria-label="Go to Dashboard"
                  >
                    GO TO DASHBOARD <ArrowRight size={18} />
                  </button>
              </div>
            ) : (
              <>
                {error && <div className="auth-alert auth-alert--error">{error}</div>}
                {resetSent && (
                  <div className="auth-alert auth-alert--success">
                    Password reset link sent — check your inbox.
                  </div>
                )}

                <button
                  className="auth-oauth"
                  onClick={() => handleOAuth("google")}
                  disabled={!!oauthLoading}
                  aria-label="Continue with Google"
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
                      aria-label="Email address"
                    />
                  </div>

                  <div className="auth-field">
                    <div className="auth-input-wrap">
                      <input
                        type={showPw ? "text" : "password"}
                        placeholder="Password"
                        value={password}
                        onChange={(e) => setPassword(e.target.value)}
                        required
                        className="auth-input auth-input--pw"
                        aria-label="Password"
                      />
                      <button
                        type="button"
                        className="auth-eye"
                        onClick={() => setShowPw(!showPw)}
                        aria-label={showPw ? "Hide password" : "Show password"}
                      >
                        {showPw ? "HIDE" : "SHOW"}
                      </button>
                    </div>
                  </div>

                  <button type="submit" disabled={loading} className="auth-submit" aria-label="Sign In">
                    {loading ? "AUTHENTICATING..." : "SIGN IN"}
                  </button>
                </form>

                <div className="auth-footer" style={{ borderTop: "1px solid rgba(255,255,255,0.05)", paddingTop: "16px", marginTop: "16px" }}>
                  New here? <Link to="/signup" className="auth-link">Create account</Link>
                </div>
              </>
            )}
          </div>
        </div>
      </header>

      <section className="landing-stats" style={{ contentVisibility: "auto", containIntrinsicSize: "0 200px" }}>
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

      <section className="landing-security" style={{ padding: "80px 20px", borderTop: "1px solid rgba(212,175,55,0.1)", contentVisibility: "auto", containIntrinsicSize: "0 400px" }}>
        <div style={{ maxWidth: "1200px", margin: "0 auto", display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(300px, 1fr))", gap: "60px", alignItems: "center" }}>
          <div>
            <h2 style={{ fontSize: "32px", marginBottom: "24px" }}>UNCOMPROMISING SECURITY</h2>
            <p style={{ fontSize: "16px", lineHeight: "1.8", color: "#888", marginBottom: "20px" }}>
              At DoYou.trade, your security is our highest priority. Our architecture is designed to provide 
              institutional-grade protection without ever touching your actual funds. 
            </p>
            <ul style={{ listStyle: "none", padding: 0, display: "flex", flexDirection: "column", gap: "15px" }}>
              {[
                "End-to-End Encryption for all API keys",
                "Non-custodial architecture (We never hold your funds)",
                "Strict withdrawal-disabled API policy",
                "24/7 internal auditing of execution engine decisions",
                "Global DDOS protection and encrypted traffic"
              ].map((text, i) => (
                <li key={i} style={{ display: "flex", alignItems: "center", gap: "10px", fontSize: "14px", color: "#aaa" }}>
                  <Shield size={14} style={{ color: colors.gold }} /> {text}
                </li>
              ))}
            </ul>
          </div>
          <div style={{ background: "linear-gradient(135deg, rgba(212,175,55,0.05), rgba(0,0,0,0.4))", padding: "40px", borderRadius: "24px", border: "1px solid rgba(212,175,55,0.1)", position: "relative", overflow: "hidden" }}>
             <div style={{ position: "absolute", top: "10px", right: "10px", opacity: 0.05, pointerEvents: "none" }}><Shield size={160} /></div>
             <h3 style={{ color: colors.gold, marginBottom: "15px", fontSize: "20px" }}>COMPLIANCE READY</h3>
             <p style={{ fontSize: "14px", color: "#666", lineHeight: "1.7" }}>
               Our systems are architected to meet rigorous data privacy standards. We process all 
               market data in real-time without storing sensitive user credentials beyond encrypted 
               connection parameters required for trade execution.
             </p>
          </div>
        </div>
      </section>

      <section className="landing-how-it-works" style={{ padding: "80px 20px", background: "rgba(255,255,255,0.02)", borderTop: "1px solid rgba(212,175,55,0.1)", contentVisibility: "auto", containIntrinsicSize: "0 400px" }}>
        <div className="section-header" style={{ textAlign: "center", marginBottom: "60px" }}>
          <h2 style={{ fontSize: "32px", marginBottom: "16px" }}>HOW IT WORKS</h2>
          <p style={{ color: "#888", maxWidth: "600px", margin: "0 auto" }}>THREE STEPS TO AUTOMATED TRADING EXCELLENCE</p>
        </div>
        <div className="features-grid" style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: "32px", maxWidth: "1200px", margin: "0 auto" }}>
          <div className="feature-card" style={{ background: "rgba(255,255,255,0.03)", padding: "40px", borderRadius: "16px", border: "1px solid rgba(255,255,255,0.05)" }}>
            <div style={{ color: colors.gold, fontSize: "24px", fontWeight: "800", marginBottom: "20px" }}>01. CONNECT</div>
            <h3 style={{ fontSize: "18px", marginBottom: "12px" }}>LINK YOUR EXCHANGE</h3>
            <p style={{ fontSize: "14px", lineHeight: "1.6", color: "#888" }}>Connect your Coinbase, Binance, or Kraken account via encrypted API keys. Withdrawals are always disabled for maximum security.</p>
          </div>
          <div className="feature-card" style={{ background: "rgba(255,255,255,0.03)", padding: "40px", borderRadius: "16px", border: "1px solid rgba(255,255,255,0.05)" }}>
            <div style={{ color: colors.gold, fontSize: "24px", fontWeight: "800", marginBottom: "20px" }}>02. CONFIGURE</div>
            <h3 style={{ fontSize: "18px", marginBottom: "12px" }}>SET YOUR STRATEGY</h3>
            <p style={{ fontSize: "14px", lineHeight: "1.6", color: "#888" }}>Choose from 100+ professional trading presets or customize your risk parameters. Our systems adapt to your preferences.</p>
          </div>
          <div className="feature-card" style={{ background: "rgba(255,255,255,0.03)", padding: "40px", borderRadius: "16px", border: "1px solid rgba(255,255,255,0.05)" }}>
            <div style={{ color: colors.gold, fontSize: "24px", fontWeight: "800", marginBottom: "20px" }}>03. AUTOMATE</div>
            <h3 style={{ fontSize: "18px", marginBottom: "12px" }}>EXECUTE 24/7</h3>
            <p style={{ fontSize: "14px", lineHeight: "1.6", color: "#888" }}>Sit back while our systems monitor global markets, analyze data streams, and execute trades with millisecond precision.</p>
          </div>
        </div>
      </section>

      <section className="landing-faq" style={{ padding: "80px 20px", maxWidth: "800px", margin: "0 auto", contentVisibility: "auto", containIntrinsicSize: "0 500px" }}>
        <div className="section-header" style={{ textAlign: "center", marginBottom: "40px" }}>
          <h2 style={{ fontSize: "32px", marginBottom: "16px" }}>FREQUENTLY ASKED QUESTIONS</h2>
          <p style={{ color: "#888" }}>EVERYTHING YOU NEED TO KNOW ABOUT DOYOU.TRADE</p>
        </div>
        <div className="faq-list" style={{ display: "flex", flexDirection: "column", gap: "20px" }}>
          {[
            { q: "Is DoYou.trade a custodial platform?", a: "No. DoYou.trade is 100% non-custodial. Your funds always remain in your own exchange account (Coinbase, Binance, or Kraken). We only execute trades on your behalf using API keys with withdrawal permissions strictly disabled." },
            { q: "How does the System make trading decisions?", a: "The platform utilizes advanced execution models to process millions of data points every second, including price action, technical indicators, global market sentiment, and on-chain liquidity flows. It identifies high-probability setups and executes with millisecond precision." },
            { q: "Do I need prior trading experience?", a: "Not at all. While professional traders use our advanced tools, beginners can leverage our 100+ expert trading presets. Simply connect your exchange, pick a strategy that matches your risk profile, and let the systems handle the technical execution." },
            { q: "Which exchanges are supported?", a: "Currently, we offer full support for Coinbase, Binance, and Kraken. You can connect multiple exchanges simultaneously and manage your entire portfolio from a single, unified dashboard." },
            { q: "What are the fees for using the platform?", a: "We offer transparent, tier-based subscription models with no hidden performance fees. Visit our billing section after signing up to choose a plan that fits your trading volume and needs." }
          ].map((item, idx) => (
            <details key={idx} style={{ background: "rgba(255,255,255,0.03)", borderRadius: "12px", border: "1px solid rgba(255,255,255,0.05)", padding: "20px", cursor: "pointer" }}>
              <summary style={{ fontWeight: "700", fontSize: "16px", color: colors.gold, listStyle: "none", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                {item.q}
                <span style={{ fontSize: "20px" }}><Zap size={18} /></span>
              </summary>
              <p style={{ marginTop: "15px", fontSize: "14px", lineHeight: "1.6", color: "#aaa" }}>{item.a}</p>
            </details>
          ))}
        </div>
      </section>

      <section className="landing-features" id="features" style={{ contentVisibility: "auto", containIntrinsicSize: "0 400px" }}>
        <div className="section-header">
          <h2>SYSTEM CAPABILITIES</h2>
          <p style={{ color: "#555", letterSpacing: "1px", fontSize: "14px" }}>ADVANCED INFRASTRUCTURE FOR THE MODERN TRADER</p>
        </div>
        <div className="features-grid">
          <div className="feature-card">
            <div style={{ marginBottom: "20px" }}><Cpu size={32} color={colors.gold} /></div>
            <h3>Advanced Systematic Intelligence</h3>
            <p>Leverage state-of-the-art systems for deep market analysis. Real-time inference on price action, global news sentiment, and on-chain liquidity.</p>
          </div>
          <div className="feature-card">
            <div style={{ marginBottom: "20px" }}><Shield size={32} color={colors.gold} /></div>
            <h3>Non-Custodial Security</h3>
            <p>Your funds stay safely in your exchange account. We never have withdrawal access. Our system only sends trade execution signals.</p>
          </div>
          <div className="feature-card">
            <div style={{ marginBottom: "20px" }}><Zap size={32} color={colors.gold} /></div>
            <h3>Institutional Execution</h3>
            <p>Multi-exchange connectivity with millisecond latency. Execute complex strategies across Bitcoin, Ethereum, and major altcoins seamlessly.</p>
          </div>
        </div>
      </section>

      <footer className="landing-footer" style={{ padding: "60px 20px", borderTop: "1px solid rgba(255,255,255,0.05)" }}>
        <div style={{ maxWidth: "1200px", margin: "0 auto", display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: "40px", marginBottom: "40px" }}>
          <div>
            <div className="auth-brand" style={{ fontSize: "20px", marginBottom: "15px" }}>DOYOU.TRADE</div>
            <p style={{ fontSize: "14px", color: "#666", lineHeight: "1.6" }}>
              The world's most advanced non-custodial trading terminal. 
              Built for precision, speed, and security.
            </p>
          </div>
          <div>
            <h4 style={{ fontSize: "12px", color: "#888", letterSpacing: "2px", marginBottom: "15px" }}>MARKET INDEX</h4>
            <div style={{ display: "flex", flexDirection: "column", gap: "8px", fontSize: "13px" }}>
              <Link to="/market/btc" title="Trade Bitcoin" aria-label="Trade Bitcoin">BTC/USD Intelligence</Link>
              <Link to="/market/eth" title="Automate Ethereum Trading" aria-label="Automate Ethereum Trading">ETH/USD Strategy</Link>
              <Link to="/market/sol" title="Solana Precision Execution" aria-label="Solana Precision Execution">SOL/USD Execution</Link>
              <Link to="/market/altcoins" title="Algorithmic Altcoin Trading" aria-label="Algorithmic Altcoin Trading">Altcoin Execution Engine</Link>
            </div>
          </div>
          <div>
            <h4 style={{ fontSize: "12px", color: "#888", letterSpacing: "2px", marginBottom: "15px" }}>PLATFORM</h4>
            <div style={{ display: "flex", flexDirection: "column", gap: "8px", fontSize: "13px" }}>
              <a href="#features" title="System Capabilities" aria-label="Features">Features</a>
              <Link to="/signup" title="Create your trading account" aria-label="Get Started">Get Started</Link>
              <Link to="/login" title="Sign in to your terminal" aria-label="Terminal Login">Terminal Login</Link>
              <a href="mailto:support@doyou.trade" title="Contact Support" aria-label="Support">Support</a>
            </div>
          </div>
          <div>
            <h4 style={{ fontSize: "12px", color: "#888", letterSpacing: "2px", marginBottom: "15px" }}>LEGAL</h4>
            <div style={{ display: "flex", flexDirection: "column", gap: "8px", fontSize: "13px" }}>
              <Link to="/terms" title="Terms of Service" aria-label="Terms of Service">Terms</Link>
              <Link to="/privacy" title="Privacy Policy" aria-label="Privacy Policy">Privacy</Link>
              <Link to="/terms" title="Risk Disclosure" aria-label="Risk Disclosure">Risk Disclosure</Link>
            </div>
          </div>
        </div>
        <div style={{ textAlign: "center", borderTop: "1px solid rgba(255,255,255,0.05)", paddingTop: "40px" }}>
          <div style={{ marginBottom: "20px", display: "flex", alignItems: "center", justifyContent: "center", gap: "10px" }}>
            <img src="/Bravo.svg" alt="DoYou.trade Logo" style={{ width: "20px", opacity: 0.5 }} />
            <span style={{ opacity: 0.3 }}>&copy; 2025 DOYOU.TRADE. ALL RIGHTS RESERVED.</span>
          </div>
        </div>
      </footer>

      {/* Floating Scroll to Top */}
      <button 
        onClick={() => window.scrollTo({ top: 0, behavior: 'smooth' })}
        aria-label="Scroll to top"
        style={{
          position: "fixed", bottom: "100px", right: "30px", width: "40px", height: "40px",
          borderRadius: "50%", background: "rgba(212,175,55,0.1)", border: "1px solid rgba(212,175,55,0.3)",
          color: colors.gold, cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center",
          zIndex: 1000, backdropFilter: "blur(10px)", transition: "all 0.3s"
        }}
        onMouseEnter={(e) => { e.currentTarget.style.background = "rgba(212,175,55,0.2)"; e.currentTarget.style.transform = "translateY(-5px)"; }}
        onMouseLeave={(e) => { e.currentTarget.style.background = "rgba(212,175,55,0.1)"; e.currentTarget.style.transform = "translateY(0)"; }}
      >
        <ArrowUp size={20} />
      </button>

      {/* Sticky Conversion Footer */}
      <div 
        style={{
          position: "fixed", bottom: "0", left: "0", right: "0",
          background: "rgba(10, 10, 10, 0.8)", backdropFilter: "blur(20px)",
          borderTop: "1px solid rgba(212, 175, 55, 0.2)", padding: "12px 20px",
          display: "flex", alignItems: "center", justifyContent: "center",
          gap: "20px", zIndex: 1100, boxShadow: "0 -10px 40px rgba(0,0,0,0.5)"
        }}
      >
        <div style={{ display: "none", alignItems: "center", gap: "10px" }} className="desktop-only-flex">
          <span className="dot" style={{ background: "#00E676", animation: "pulse 1.5s infinite" }} />
          <span style={{ fontSize: "11px", fontWeight: "700", letterSpacing: "1px", color: colors.gold }}>SYSTEMS MONITORING GLOBAL MARKETS</span>
        </div>
        <div style={{ flex: 1, maxWidth: "1200px", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <div style={{ display: "flex", flexDirection: "column" }}>
            <span style={{ fontSize: "12px", fontWeight: "800", letterSpacing: "1px" }}>READY TO AUTOMATE?</span>
            <span style={{ fontSize: "10px", color: "#666" }}>Join 12k+ traders using the execution engine.</span>
          </div>
          <div style={{ display: "flex", gap: "12px" }}>
            <Link to="/signup" className="btn btn-r" style={{ display: "flex", alignItems: "center", gap: "8px", padding: "10px 24px", fontSize: "11px", whiteSpace: "nowrap" }}>GET STARTED <ArrowRight size={14} /></Link>
            <Link to="/login" className="btn btn-d desktop-only-flex" style={{ padding: "10px 24px", fontSize: "11px" }}>SIGN IN</Link>
          </div>
        </div>
      </div>

      <style>{`
        .desktop-only-flex { display: none !important; }
        @media (min-width: 768px) {
          .desktop-only-flex { display: flex !important; }
        }
        .dot {
          width: 8px;
          height: 8px;
          border-radius: 50%;
          display: inline-block;
        }
        @keyframes pulse {
          0% { box-shadow: 0 0 0 0 rgba(0, 230, 118, 0.4); }
          70% { box-shadow: 0 0 0 10px rgba(0, 230, 118, 0); }
          100% { box-shadow: 0 0 0 0 rgba(0, 230, 118, 0); }
        }
      `}</style>
    </div>
  );
}
