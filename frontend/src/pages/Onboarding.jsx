import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext.jsx";
import { useAuthHeaders } from "../hooks/useAuthHeaders.js";
import { supabase } from "../supabaseClient.js";
import { colors, radii, typography } from "../theme.js";

const EXCHANGES = [
  { id: "coinbase", name: "Coinbase", type: "oauth", desc: "OAuth — secure, no API key needed" },
  { id: "kraken", name: "Kraken", type: "api_key", desc: "API Key — create a restricted key" },
  { id: "binance", name: "Binance", type: "api_key", desc: "API Key — create a restricted key" },
  { id: "onchain", name: "On-Chain (Base)", type: "wallet", desc: "Wallet Connect — trustless" },
];

const PRESETS_FALLBACK = [
  { id: "default", name: "Default (Balanced)", category: "General" },
  { id: "turtle", name: "Turtle Traders", category: "Trend Following" },
  { id: "seykota", name: "Ed Seykota", category: "Trend Following" },
  { id: "trend_dunn", name: "Dunn Capital Trend", category: "Trend Following" },
  { id: "trend_henry", name: "John W. Henry", category: "Trend Following" },
  { id: "trend_harding", name: "Winton Trend", category: "Trend Following" },
  { id: "trend_abraham", name: "Abraham Trading", category: "Trend Following" },
  { id: "trend_millburn", name: "Millburn Ridgefield", category: "Trend Following" },
  { id: "donchian", name: "Donchian Channel", category: "Trend Following" },
  { id: "soros", name: "Soros Reflexivity", category: "Macro" },
  { id: "ptj", name: "Paul Tudor Jones", category: "Macro" },
  { id: "druckenmiller", name: "Druckenmiller Macro", category: "Macro" },
  { id: "kovner", name: "Kovner Conservative", category: "Macro" },
  { id: "bacon", name: "Louis Bacon Macro", category: "Macro" },
  { id: "dalio", name: "Dalio All-Weather", category: "Macro" },
  { id: "robertson", name: "Julian Robertson", category: "Macro" },
  { id: "steinhardt", name: "Michael Steinhardt", category: "Macro" },
  { id: "tudor_bvi", name: "Tudor BVI Macro", category: "Macro" },
  { id: "gross", name: "Bill Gross Bond King", category: "Macro" },
  { id: "gundlach", name: "Gundlach DoubleLine", category: "Macro" },
  { id: "livermore", name: "Livermore Pivots", category: "Stock Legends" },
  { id: "minervini", name: "Minervini Momentum", category: "Stock Legends" },
  { id: "oneil", name: "William O'Neil CANSLIM", category: "Stock Legends" },
  { id: "darvas", name: "Nicolas Darvas Box", category: "Stock Legends" },
  { id: "zanger", name: "Dan Zanger Breakout", category: "Stock Legends" },
  { id: "weinstein", name: "Weinstein Stage", category: "Stock Legends" },
  { id: "lefevre", name: "Reminiscences Classic", category: "Stock Legends" },
  { id: "simons", name: "Renaissance Quant", category: "Quantitative" },
  { id: "shannon", name: "Shannon Rebalance", category: "Quantitative" },
  { id: "thorp", name: "Ed Thorp Kelly", category: "Quantitative" },
  { id: "aqr", name: "AQR Factor", category: "Quantitative" },
  { id: "two_sigma", name: "Two Sigma Systematic", category: "Quantitative" },
  { id: "de_shaw", name: "D.E. Shaw Quant", category: "Quantitative" },
  { id: "citadel", name: "Citadel Multi-Strat", category: "Quantitative" },
  { id: "man_ahl", name: "Man AHL Systematic", category: "Quantitative" },
  { id: "blackbox", name: "Black Box Quant", category: "Quantitative" },
  { id: "buffett", name: "Buffett Value", category: "Value / Contrarian" },
  { id: "icahn", name: "Carl Icahn Activist", category: "Value / Contrarian" },
  { id: "klarman", name: "Seth Klarman Value", category: "Value / Contrarian" },
  { id: "marks", name: "Howard Marks Cycles", category: "Value / Contrarian" },
  { id: "templeton", name: "Templeton Contrarian", category: "Value / Contrarian" },
  { id: "neff", name: "John Neff Low P/E", category: "Value / Contrarian" },
  { id: "burry", name: "Michael Burry Deep Value", category: "Value / Contrarian" },
  { id: "driehaus", name: "Driehaus Momentum", category: "Momentum / Growth" },
  { id: "lynch", name: "Peter Lynch Growth", category: "Momentum / Growth" },
  { id: "ryan", name: "David Ryan CANSLIM", category: "Momentum / Growth" },
  { id: "wood", name: "Cathie Wood Innovation", category: "Momentum / Growth" },
  { id: "raschke", name: "Raschke Short-Term", category: "Short-Term / Swing" },
  { id: "williams_balanced", name: "Williams Balanced", category: "Short-Term / Swing" },
  { id: "williams_swing", name: "Williams Swing", category: "Short-Term / Swing" },
  { id: "douglas", name: "Mark Douglas Zone", category: "Short-Term / Swing" },
  { id: "elder", name: "Alexander Elder", category: "Short-Term / Swing" },
  { id: "schwartz", name: "Marty Schwartz Pit Bull", category: "Short-Term / Swing" },
  { id: "jones_crt", name: "CRT Bond Arb", category: "Short-Term / Swing" },
  { id: "taleb", name: "Taleb Barbell", category: "Volatility / Tail Risk" },
  { id: "niederhoffer", name: "Niederhoffer Mean-Rev", category: "Volatility / Tail Risk" },
  { id: "tail_risk", name: "Tail Risk Hunter", category: "Volatility / Tail Risk" },
  { id: "vol_breakout", name: "Volatility Breakout", category: "Volatility / Tail Risk" },
  { id: "crypto_swing", name: "Crypto Swing Pro", category: "Crypto Native" },
  { id: "crypto_conservative", name: "Crypto Maximum Room", category: "Crypto Native" },
  { id: "saylor", name: "Saylor HODL Conviction", category: "Crypto Native" },
  { id: "hayes", name: "Arthur Hayes Degen", category: "Crypto Native" },
  { id: "su_zhu", name: "Su Zhu Supercycle", category: "Crypto Native" },
  { id: "cobie", name: "Cobie CT Alpha", category: "Crypto Native" },
  { id: "pentoshi", name: "Pentoshi Swing", category: "Crypto Native" },
  { id: "hsaka", name: "Hsaka Scalp-Swing", category: "Crypto Native" },
  { id: "ansem", name: "Ansem Degen Momentum", category: "Crypto Native" },
  { id: "gainzy", name: "GCR Contrarian", category: "Crypto Native" },
  { id: "light", name: "Light Crypto Macro", category: "Crypto Native" },
  { id: "mobius", name: "Mark Mobius EM", category: "Global / Emerging" },
  { id: "rogers", name: "Jim Rogers Commodities", category: "Global / Emerging" },
  { id: "rogers_jim", name: "Jim Rogers Adventure", category: "Global / Emerging" },
  { id: "paulson", name: "John Paulson Event", category: "Event-Driven" },
  { id: "tepper", name: "David Tepper Distressed", category: "Event-Driven" },
  { id: "einhorn", name: "David Einhorn Value", category: "Event-Driven" },
  { id: "loeb", name: "Dan Loeb Activist", category: "Event-Driven" },
  { id: "ackman", name: "Bill Ackman Conviction", category: "Event-Driven" },
  { id: "coleman", name: "Chase Coleman Tiger", category: "Tiger Cubs / Modern HF" },
  { id: "mandel", name: "Steve Mandel Lone Pine", category: "Tiger Cubs / Modern HF" },
  { id: "ainslie", name: "Lee Ainslie Maverick", category: "Tiger Cubs / Modern HF" },
  { id: "marcus", name: "Michael Marcus", category: "Market Wizards Classic" },
  { id: "mean_rev_bollinger", name: "Bollinger Mean-Rev", category: "Mean-Reversion" },
  { id: "mean_rev_connors", name: "Connors RSI Reversal", category: "Mean-Reversion" },
  { id: "scalp_tight", name: "Scalper Tight", category: "Scalping" },
  { id: "scalp_momentum", name: "Momentum Scalp", category: "Scalping" },
  { id: "market_maker", name: "Market Maker Spread", category: "Scalping" },
  { id: "risk_parity", name: "Risk Parity", category: "Portfolio / Systematic" },
  { id: "grid_dca", name: "Grid DCA", category: "Portfolio / Systematic" },
  { id: "seasonal", name: "Seasonal Patterns", category: "Portfolio / Systematic" },
  { id: "sentiment", name: "Sentiment Extremes", category: "Portfolio / Systematic" },
  { id: "fib_trader", name: "Fibonacci Precision", category: "Technical Systems" },
  { id: "ichimoku", name: "Ichimoku Cloud", category: "Technical Systems" },
  { id: "wyckoff", name: "Wyckoff Method", category: "Technical Systems" },
  { id: "volume_profile", name: "Volume Profile", category: "Technical Systems" },
  { id: "elliott", name: "Elliott Wave", category: "Technical Systems" },
  { id: "gann", name: "W.D. Gann Geometric", category: "Technical Systems" },
  { id: "pnf", name: "Point & Figure", category: "Technical Systems" },
  { id: "smc", name: "Smart Money Concepts", category: "Technical Systems" },
  { id: "gap_trader", name: "Gap & Go", category: "Technical Systems" },
  { id: "vwap", name: "VWAP Institutional", category: "Technical Systems" },
  { id: "pairs_trade", name: "Pairs Trading", category: "Technical Systems" },
];

export default function Onboarding() {
  const { user, refreshProfile, accessToken } = useAuth();
  const getAuthHeaders = useAuthHeaders();
  const navigate = useNavigate();
  const [step, setStep] = useState(1);
  const [connected, setConnected] = useState({});
  const [keyModal, setKeyModal] = useState(null);
  const [apiKey, setApiKey] = useState("");
  const [apiSecret, setApiSecret] = useState("");
  const [keyError, setKeyError] = useState("");
  const [keySaving, setKeySaving] = useState(false);

  const [preset, setPreset] = useState("turtle");
  const [presets, setPresets] = useState(PRESETS_FALLBACK);
  const [risk, setRisk] = useState("moderate");
  const [startBalance, setStartBalance] = useState("1000");
  const [paperMode, setPaperMode] = useState(true);
  const [coins, setCoins] = useState(["BTC", "ETH", "SOL", "LINK"]);
  const [saving, setSaving] = useState(false);

  const allCoins = ["BTC", "ETH", "SOL", "LINK", "DOGE", "AVAX", "UNI", "AAVE", "XRP", "ADA"];

  useEffect(() => {
    const base = (import.meta.env.VITE_BACKEND_URL || "").replace(/\/$/, "") || "";
    const url = base ? `${base}/api/presets` : "/api/presets";
    fetch(url, { headers: getAuthHeaders() }).then(r => r.ok && r.json()).then(d => {
      if (d?.presets?.length) setPresets(d.presets);
    }).catch(() => {});
  }, [getAuthHeaders]);

  function toggleCoin(c) {
    setCoins(prev => prev.includes(c) ? prev.filter(x => x !== c) : [...prev, c]);
  }

  async function handleConnectOAuth(exchange) {
    // Coinbase OAuth would redirect — for now mark as connected (placeholder)
    setConnected(prev => ({ ...prev, [exchange]: true }));
  }

  async function handleSaveKey() {
    if (!apiKey?.trim() || !apiSecret?.trim()) {
      setKeyError("Both API key and secret are required");
      return;
    }
    setKeySaving(true);
    setKeyError("");
    try {
      const base = (import.meta.env.VITE_BACKEND_URL || "").replace(/\/$/, "") || "";
      const validateUrl = base ? `${base}/auth/exchange/validate` : "/auth/exchange/validate";
      const connectUrl = base ? `${base}/auth/exchanges/connect` : "/auth/exchanges/connect";
      const headers = {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${accessToken}`,
      };
      const res = await fetch(validateUrl, {
        method: "POST",
        headers,
        body: JSON.stringify({
          exchange: keyModal,
          api_key: apiKey.trim(),
          api_secret: apiSecret.trim(),
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!data.valid) {
        setKeyError(data.error || "Invalid API credentials — please check your key and secret");
        setKeySaving(false);
        return;
      }
      const connectRes = await fetch(connectUrl, {
        method: "POST",
        headers,
        body: JSON.stringify({
          exchange: keyModal,
          connection_type: "api_key",
          api_key: apiKey.trim(),
          api_secret: apiSecret.trim(),
        }),
      });
      if (!connectRes.ok) {
        const errData = await connectRes.json().catch(() => ({}));
        throw new Error(errData.error || "Failed to save exchange");
      }
      setConnected(prev => ({ ...prev, [keyModal]: true }));
      setKeyModal(null);
      setApiKey("");
      setApiSecret("");
    } catch (err) {
      setKeyError(err.message || "Failed to save. Is the backend running?");
    } finally {
      setKeySaving(false);
    }
  }

  async function handleFinish() {
    const validPreset = presets.some(p => p.id === preset) ? preset : "turtle";
    setSaving(true);
    try {
      await supabase.from("user_preferences").upsert({
        user_id: user.id,
        trading_preset: validPreset,
        risk_level: risk,
        paper_trading: paperMode,
        start_balance: parseFloat(startBalance) || 1000,
        target_balance: (parseFloat(startBalance) || 1000) * 5,
        coins: coins,
      }, { onConflict: "user_id" });

      await supabase.from("profiles").update({ onboarding_complete: true }).eq("id", user.id);
      await refreshProfile();
      navigate("/dashboard");
    } catch {
      // Silently continue to dashboard
      navigate("/dashboard");
    } finally {
      setSaving(false);
    }
  }

  const connectedCount = Object.values(connected).filter(Boolean).length;
  const progress = ((step - 1) / 3) * 100;

  return (
    <>
    <style>{responsiveCss}</style>
    <div style={styles.container}>
      <div style={styles.card} className="onboarding-card">
        {/* Progress bar */}
        <div style={styles.progressBar}>
          <div style={{ ...styles.progressFill, width: `${progress}%` }} />
        </div>
        <div style={styles.stepLabel}>Step {step} of 4</div>

        {/* Step 1: Connect Exchanges */}
        {step === 1 && (
          <div>
            <h2 style={styles.heading}>Connect Your Exchanges</h2>
            <p style={styles.desc}>Connect at least one exchange to start trading. Your API keys are encrypted and never stored in plaintext.</p>

            <div style={styles.exchangeList}>
              {EXCHANGES.map(ex => (
                <div key={ex.id} style={styles.exchangeRow}>
                  <div style={{ flex: 1 }}>
                    <div style={styles.exchangeName}>
                      {connected[ex.id] && <span style={{ color: colors.success, marginRight: 6 }}>&#10003;</span>}
                      {ex.name}
                    </div>
                    <div style={styles.exchangeDesc}>{ex.desc}</div>
                  </div>
                  {connected[ex.id] ? (
                    <span style={{ color: colors.success, fontSize: 11, fontFamily: typography.fontMono }}>Connected</span>
                  ) : (
                    <button
                      style={styles.connectBtn}
                      onClick={() => {
                        if (ex.type === "oauth") handleConnectOAuth(ex.id);
                        else if (ex.type === "api_key") setKeyModal(ex.id);
                        else handleConnectOAuth(ex.id);
                      }}
                    >
                      {ex.type === "oauth" ? "Connect" : ex.type === "api_key" ? "Add Key" : "Connect Wallet"}
                    </button>
                  )}
                </div>
              ))}
            </div>

            <div style={styles.btnRow}>
              <button style={styles.skipBtn} onClick={() => setStep(2)}>Skip for now</button>
              <button style={styles.nextBtn} onClick={() => setStep(2)} disabled={connectedCount === 0}>
                Next &rarr;
              </button>
            </div>
          </div>
        )}

        {/* Step 2: Trading Preferences */}
        {step === 2 && (
          <div>
            <h2 style={styles.heading}>Trading Preferences</h2>
            <p style={styles.desc}>Choose your strategy and risk level. You can change these anytime in Settings.</p>

            <label style={styles.label}>Strategy Preset</label>
            <div style={styles.presetCarousel}>
              {presets.map(p => (
                <button
                  key={p.id}
                  style={{ ...styles.presetCard, ...(preset === p.id ? styles.presetActive : {}) }}
                  onClick={() => setPreset(p.id)}
                >
                  <div style={styles.presetName}>{p.name}</div>
                  <div style={styles.presetDesc}>{p.description || p.desc}</div>
                </button>
              ))}
            </div>

            <label style={styles.label}>Risk Level</label>
            <div style={styles.riskRow}>
              {["conservative", "moderate", "aggressive"].map(r => (
                <button
                  key={r}
                  style={{ ...styles.riskBtn, ...(risk === r ? styles.riskActive : {}) }}
                  onClick={() => setRisk(r)}
                >
                  {r.charAt(0).toUpperCase() + r.slice(1)}
                </button>
              ))}
            </div>

            <label style={styles.label}>Starting Balance ($)</label>
            <input
              type="number"
              value={startBalance}
              onChange={e => setStartBalance(e.target.value)}
              style={styles.input}
              min="100"
            />

            <div style={styles.btnRow}>
              <button style={styles.skipBtn} onClick={() => setStep(1)}>&larr; Back</button>
              <button style={styles.nextBtn} onClick={() => setStep(3)}>Next &rarr;</button>
            </div>
          </div>
        )}

        {/* Step 3: Coins & Paper Mode */}
        {step === 3 && (
          <div>
            <h2 style={styles.heading}>Coins & Mode</h2>
            <p style={styles.desc}>Select which coins to trade and whether to start in paper trading mode.</p>

            <label style={styles.label}>Coins to Trade</label>
            <div style={styles.coinGrid}>
              {allCoins.map(c => (
                <button
                  key={c}
                  style={{ ...styles.coinBtn, ...(coins.includes(c) ? styles.coinActive : {}) }}
                  onClick={() => toggleCoin(c)}
                >
                  {c}
                </button>
              ))}
            </div>

            <label style={styles.label}>Paper Trading (Practice Mode)</label>
            <div style={styles.toggleRow}>
              <button
                style={{ ...styles.toggleBtn, ...(paperMode ? styles.toggleActive : {}) }}
                onClick={() => setPaperMode(true)}
              >
                ON — Practice with virtual money
              </button>
              <button
                style={{ ...styles.toggleBtn, ...(!paperMode ? styles.toggleDanger : {}) }}
                onClick={() => setPaperMode(false)}
              >
                OFF — Real money
              </button>
            </div>

            <div style={styles.btnRow}>
              <button style={styles.skipBtn} onClick={() => setStep(2)}>&larr; Back</button>
              <button style={styles.nextBtn} onClick={() => setStep(4)}>Next &rarr;</button>
            </div>
          </div>
        )}

        {/* Step 4: Confirmation */}
        {step === 4 && (
          <div>
            <h2 style={styles.heading}>You&apos;re Ready</h2>
            <p style={styles.desc}>Review your setup. You can change everything later in Settings.</p>

            <div style={styles.summaryBox}>
              <div style={styles.summaryRow}>
                <span style={styles.summaryLabel}>Exchanges</span>
                <span>{connectedCount > 0 ? Object.keys(connected).filter(k => connected[k]).join(", ") : "None (paper only)"}</span>
              </div>
              <div style={styles.summaryRow}>
                <span style={styles.summaryLabel}>Strategy</span>
                <span>{presets.find(p => p.id === preset)?.name || preset}</span>
              </div>
              <div style={styles.summaryRow}>
                <span style={styles.summaryLabel}>Risk</span>
                <span>{risk.charAt(0).toUpperCase() + risk.slice(1)}</span>
              </div>
              <div style={styles.summaryRow}>
                <span style={styles.summaryLabel}>Balance</span>
                <span>${parseFloat(startBalance).toLocaleString()}</span>
              </div>
              <div style={styles.summaryRow}>
                <span style={styles.summaryLabel}>Coins</span>
                <span>{coins.join(", ")}</span>
              </div>
              <div style={styles.summaryRow}>
                <span style={styles.summaryLabel}>Mode</span>
                <span style={{ color: paperMode ? colors.success : colors.error }}>
                  {paperMode ? "Paper Trading" : "LIVE Trading"}
                </span>
              </div>
            </div>

            <div style={styles.btnRow}>
              <button style={styles.skipBtn} onClick={() => setStep(3)}>&larr; Back</button>
              <button style={styles.launchBtn} onClick={handleFinish} disabled={saving}>
                {saving ? "Setting up..." : "Launch Bot \u2192"}
              </button>
            </div>
          </div>
        )}

        {/* API Key Modal */}
        {keyModal && (
          <div style={styles.modalOverlay} onClick={() => setKeyModal(null)}>
            <div style={styles.modal} onClick={e => e.stopPropagation()}>
              <h3 style={styles.modalTitle}>Add {keyModal.charAt(0).toUpperCase() + keyModal.slice(1)} API Key</h3>

              {keyError && <div style={styles.error}>{keyError}</div>}

              <input
                type="text"
                placeholder="API Key"
                value={apiKey}
                onChange={e => setApiKey(e.target.value)}
                style={styles.input}
              />
              <input
                type="password"
                placeholder="API Secret"
                value={apiSecret}
                onChange={e => setApiSecret(e.target.value)}
                style={{ ...styles.input, marginTop: 8 }}
              />

              <div style={styles.keyInfo}>
                <div style={styles.keyInfoTitle}>Make sure your key has:</div>
                <div style={styles.keyPerm}><span style={{ color: colors.success }}>&#10003;</span> Query Funds</div>
                <div style={styles.keyPerm}><span style={{ color: colors.success }}>&#10003;</span> Query Orders & Trades</div>
                <div style={styles.keyPerm}><span style={{ color: colors.success }}>&#10003;</span> Create & Modify Orders</div>
                <div style={styles.keyPerm}><span style={{ color: colors.error }}>&#10007;</span> Withdraw Funds (leave OFF)</div>
              </div>

              <div style={{ display: "flex", gap: 8, marginTop: 16 }}>
                <button style={styles.skipBtn} onClick={() => { setKeyModal(null); setApiKey(""); setApiSecret(""); setKeyError(""); }}>Cancel</button>
                <button style={styles.nextBtn} onClick={handleSaveKey} disabled={keySaving}>
                  {keySaving ? "Saving..." : "Save Key"}
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
    </>
  );
}

const styles = {
  container: {
    fontFamily: typography.fontMono,
    background: colors.dark,
    color: colors.text,
    minHeight: "100dvh",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    padding: "20px 16px",
    paddingBottom: "calc(20px + env(safe-area-inset-bottom, 0px))",
  },
  card: {
    background: "rgba(17,17,17,0.6)",
    backdropFilter: "blur(40px) saturate(1.6)",
    WebkitBackdropFilter: "blur(40px) saturate(1.6)",
    border: "1px solid rgba(212,175,55,0.1)",
    borderRadius: 24,
    padding: "32px 28px",
    width: "100%",
    maxWidth: 520,
    boxShadow: "0 24px 80px rgba(0,0,0,0.5), 0 0 0 1px rgba(255,255,255,0.03), inset 0 1px 0 rgba(255,255,255,0.06)",
  },
  progressBar: {
    height: 3,
    background: "rgba(255,255,255,0.06)",
    borderRadius: 2,
    marginBottom: 8,
    overflow: "hidden",
  },
  progressFill: {
    height: "100%",
    background: colors.gold,
    transition: "width 0.3s ease",
    borderRadius: 2,
  },
  stepLabel: { fontSize: 10, color: colors.muted, letterSpacing: 1, marginBottom: 20 },
  heading: {
    fontFamily: typography.fontDisplay,
    fontSize: 24,
    fontWeight: 400,
    letterSpacing: 3,
    color: colors.gold,
    margin: "0 0 8px",
  },
  desc: { fontSize: 12, color: colors.muted, lineHeight: 1.6, marginBottom: 20 },
  label: { fontSize: 11, color: "#888", letterSpacing: 1, display: "block", marginTop: 16, marginBottom: 8 },
  input: {
    fontFamily: typography.fontMono,
    fontSize: 13,
    padding: "10px 12px",
    background: "rgba(10,10,10,0.6)",
    backdropFilter: "blur(8px)",
    WebkitBackdropFilter: "blur(8px)",
    border: "1px solid rgba(255,255,255,0.06)",
    borderRadius: 8,
    color: "#D4D4D4",
    outline: "none",
    width: "100%",
    boxSizing: "border-box",
    transition: "border-color 0.2s ease, box-shadow 0.2s ease",
  },
  exchangeList: { display: "flex", flexDirection: "column", gap: 8 },
  exchangeRow: {
    display: "flex",
    alignItems: "center",
    gap: 12,
    padding: "12px 14px",
    background: "rgba(10,10,10,0.4)",
    backdropFilter: "blur(8px)",
    WebkitBackdropFilter: "blur(8px)",
    border: "1px solid rgba(255,255,255,0.06)",
    borderRadius: 12,
    transition: "border-color 0.2s ease",
  },
  exchangeName: { fontSize: 13, fontWeight: 600, color: "#D4D4D4" },
  exchangeDesc: { fontSize: 10, color: colors.muted, marginTop: 2 },
  connectBtn: {
    fontFamily: typography.fontButton,
    fontSize: 11,
    letterSpacing: 1,
    padding: "6px 14px",
    border: "1px solid rgba(212,175,55,0.3)",
    borderRadius: 6,
    background: "rgba(212,175,55,0.05)",
    color: colors.gold,
    cursor: "pointer",
    whiteSpace: "nowrap",
    transition: "all 0.2s ease",
  },
  presetCarousel: {
    display: "flex",
    gap: 8,
    overflowX: "auto",
    paddingBottom: 8,
    scrollSnapType: "x mandatory",
    WebkitOverflowScrolling: "touch",
  },
  presetCard: {
    flexShrink: 0,
    minWidth: 160,
    maxWidth: 200,
    padding: "10px 12px",
    background: "rgba(10,10,10,0.4)",
    backdropFilter: "blur(8px)",
    WebkitBackdropFilter: "blur(8px)",
    border: "1px solid rgba(255,255,255,0.06)",
    borderRadius: 10,
    cursor: "pointer",
    textAlign: "left",
    color: "#D4D4D4",
    scrollSnapAlign: "start",
    transition: "all 0.2s ease",
  },
  presetActive: { borderColor: `${colors.gold}66`, background: `${colors.gold}0F` },
  presetName: { fontSize: 12, fontWeight: 600 },
  presetDesc: { fontSize: 10, color: colors.muted, marginTop: 2 },
  riskRow: { display: "flex", gap: 8 },
  riskBtn: {
    flex: 1,
    fontFamily: typography.fontMono,
    fontSize: 11,
    padding: "8px 0",
    background: "#0D0D0D",
    border: `1px solid ${colors.border}`,
    borderRadius: 4,
    color: "#D4D4D4",
    cursor: "pointer",
  },
  riskActive: { borderColor: colors.gold, color: colors.gold },
  coinGrid: { display: "flex", flexWrap: "wrap", gap: 6 },
  coinBtn: {
    fontFamily: typography.fontMono,
    fontSize: 11,
    padding: "6px 12px",
    background: "#0D0D0D",
    border: `1px solid ${colors.border}`,
    borderRadius: 4,
    color: "#D4D4D4",
    cursor: "pointer",
  },
  coinActive: { borderColor: colors.gold, color: colors.gold, background: `${colors.gold}0D` },
  toggleRow: { display: "flex", gap: 8 },
  toggleBtn: {
    flex: 1,
    fontFamily: typography.fontMono,
    fontSize: 11,
    padding: "10px 8px",
    background: "rgba(10,10,10,0.5)",
    backdropFilter: "blur(8px)",
    WebkitBackdropFilter: "blur(8px)",
    border: "1px solid rgba(255,255,255,0.06)",
    borderRadius: 8,
    color: "#D4D4D4",
    cursor: "pointer",
    textAlign: "center",
    minWidth: 0,
    wordBreak: "break-word",
    transition: "all 0.2s ease",
  },
  toggleActive: { borderColor: `${colors.success}66`, color: colors.success, background: `${colors.success}0D` },
  toggleDanger: { borderColor: `${colors.error}66`, color: colors.error, background: `${colors.error}0D` },
  summaryBox: {
    background: "rgba(10,10,10,0.4)",
    backdropFilter: "blur(8px)",
    WebkitBackdropFilter: "blur(8px)",
    border: "1px solid rgba(255,255,255,0.06)",
    borderRadius: 12,
    padding: 16,
    marginBottom: 20,
  },
  summaryRow: {
    display: "flex",
    justifyContent: "space-between",
    fontSize: 12,
    padding: "6px 0",
    borderBottom: "1px solid rgba(255,255,255,0.04)",
  },
  summaryLabel: { color: colors.muted },
  btnRow: {
    display: "flex",
    justifyContent: "space-between",
    marginTop: 24,
    gap: 12,
  },
  skipBtn: {
    fontFamily: typography.fontMono,
    fontSize: 12,
    padding: "10px 16px",
    background: "rgba(255,255,255,0.03)",
    backdropFilter: "blur(8px)",
    WebkitBackdropFilter: "blur(8px)",
    border: "1px solid rgba(255,255,255,0.06)",
    borderRadius: 8,
    color: colors.muted,
    cursor: "pointer",
    transition: "all 0.2s ease",
  },
  nextBtn: {
    fontFamily: typography.fontButton,
    fontSize: 13,
    fontWeight: 600,
    letterSpacing: 2,
    padding: "10px 24px",
    border: "none",
    borderRadius: 10,
    cursor: "pointer",
    background: `linear-gradient(180deg, ${colors.gold}, ${colors.goldDark})`,
    color: DARK,
    boxShadow: "0 4px 20px rgba(212,175,55,0.2)",
    transition: "all 0.25s cubic-bezier(0.4, 0, 0.2, 1)",
  },
  launchBtn: {
    fontFamily: typography.fontButton,
    fontSize: 14,
    fontWeight: 600,
    letterSpacing: 2,
    padding: "12px 28px",
    border: "none",
    borderRadius: 10,
    cursor: "pointer",
    background: `linear-gradient(180deg, ${colors.success}, #00C853)`,
    color: "#fff",
    boxShadow: "0 4px 20px rgba(39,174,96,0.2)",
    transition: "all 0.25s cubic-bezier(0.4, 0, 0.2, 1)",
  },
  modalOverlay: {
    position: "fixed",
    top: 0, left: 0, right: 0, bottom: 0,
    background: "rgba(0,0,0,0.6)",
    backdropFilter: "blur(24px) saturate(1.5)",
    WebkitBackdropFilter: "blur(24px) saturate(1.5)",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    zIndex: 1000,
  },
  modal: {
    background: "rgba(17,17,17,0.72)",
    backdropFilter: "blur(40px) saturate(1.6)",
    WebkitBackdropFilter: "blur(40px) saturate(1.6)",
    border: "1px solid rgba(212,175,55,0.12)",
    borderRadius: 20,
    padding: "28px 24px",
    width: "100%",
    maxWidth: 380,
    margin: "16px",
    boxSizing: "border-box",
    boxShadow: "0 24px 64px rgba(0,0,0,0.5), inset 0 1px 0 rgba(255,255,255,0.06)",
  },
  modalTitle: {
    fontFamily: typography.fontDisplay,
    fontSize: 20,
    letterSpacing: 2,
    color: colors.gold,
    margin: "0 0 16px",
  },
  keyInfo: {
    background: "rgba(10,10,10,0.4)",
    backdropFilter: "blur(8px)",
    WebkitBackdropFilter: "blur(8px)",
    border: "1px solid rgba(255,255,255,0.06)",
    borderRadius: 8,
    padding: 12,
    marginTop: 12,
  },
  keyInfoTitle: { fontSize: 11, color: "#888", marginBottom: 6 },
  keyPerm: { fontSize: 11, padding: "2px 0", display: "flex", gap: 6 },
  error: {
    fontSize: 12,
    color: colors.error,
    background: "rgba(192,57,43,0.08)",
    backdropFilter: "blur(8px)",
    WebkitBackdropFilter: "blur(8px)",
    border: "1px solid rgba(192,57,43,0.2)",
    borderRadius: 8,
    padding: "8px 12px",
    marginBottom: 12,
  },
};

const responsiveCss = `
@media (max-width: 600px) {
  .onboarding-card {
    max-width: 100% !important;
    border-radius: 20px !important;
    padding: 24px 16px !important;
  }
}
@media (max-width: 375px) {
  .onboarding-card {
    padding: 20px 12px !important;
    border-radius: 16px !important;
  }
}
@media (max-width: 320px) {
  .onboarding-card {
    padding: 16px 10px !important;
    border-radius: 12px !important;
  }
}
`;
