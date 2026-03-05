import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext.jsx";
import { supabase } from "../supabaseClient.js";

const GOLD = "#D4AF37";
const DARK = "#0A0A0A";
const CARD = "#111111";
const BORDER = "#1A1A1A";
const MUTED = "#5C5C5C";
const GREEN = "#27AE60";
const RED = "#C0392B";

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

const ALL_COINS = ["BTC", "ETH", "SOL", "LINK", "DOGE", "AVAX", "UNI", "AAVE", "XRP", "ADA", "BNB", "DOT"];

export default function Settings() {
  const { user, profile, signOut } = useAuth();
  const navigate = useNavigate();
  const [prefs, setPrefs] = useState(null);
  const [exchanges, setExchanges] = useState([]);
  const [presets, setPresets] = useState(PRESETS_FALLBACK);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  const [keyModal, setKeyModal] = useState(null);
  const [apiKey, setApiKey] = useState("");
  const [apiSecret, setApiSecret] = useState("");
  const [keyError, setKeyError] = useState("");

  useEffect(() => {
    if (!user) return;
    supabase.from("user_preferences").select("*").eq("user_id", user.id).single()
      .then(({ data }) => { if (data) setPrefs(data); });
    supabase.from("user_exchanges").select("*").eq("user_id", user.id)
      .then(({ data }) => { if (data) setExchanges(data); });
  }, [user]);

  useEffect(() => {
    const base = (import.meta.env.VITE_BACKEND_URL || "").replace(/\/$/, "") || "";
    const url = base ? `${base}/api/presets` : "/api/presets";
    fetch(url).then(r => r.ok && r.json()).then(d => {
      if (d?.presets?.length) setPresets(d.presets);
    }).catch(() => {});
  }, []);

  function updatePref(key, value) {
    setPrefs(prev => ({ ...prev, [key]: value }));
    setSaved(false);
  }

  function toggleCoin(c) {
    const current = prefs?.coins || [];
    const next = current.includes(c) ? current.filter(x => x !== c) : [...current, c];
    updatePref("coins", next);
  }

  async function handleSave() {
    if (!prefs) return;
    const validPreset = presets.some(p => p.id === prefs.trading_preset) ? prefs.trading_preset : "turtle";
    const toSave = { ...prefs, trading_preset: validPreset };
    setSaving(true);
    try {
      const { user_id, id, created_at, updated_at, ...rest } = toSave;
      await supabase.from("user_preferences").update(rest).eq("user_id", user.id);
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch {
      // ignore
    } finally {
      setSaving(false);
    }
  }

  async function handleAddKey() {
    if (!apiKey?.trim() || !apiSecret?.trim()) {
      setKeyError("Both API key and secret are required");
      return;
    }
    try {
      const base = (import.meta.env.VITE_BACKEND_URL || "").replace(/\/$/, "") || "";
      const url = base ? `${base}/api/exchange/validate` : "/api/exchange/validate";
      const res = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          exchange: keyModal,
          api_key: apiKey.trim(),
          api_secret: apiSecret.trim(),
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!data.valid) {
        setKeyError(data.error || "Invalid API credentials — please check your key and secret");
        return;
      }
      await supabase.from("user_exchanges").upsert({
        user_id: user.id,
        exchange: keyModal,
        connection_type: "api_key",
        api_key_enc: apiKey.trim(),
        api_secret_enc: apiSecret.trim(),
        is_active: true,
      }, { onConflict: "user_id,exchange" });
      const { data: exData } = await supabase.from("user_exchanges").select("*").eq("user_id", user.id);
      setExchanges(exData || []);
      setKeyModal(null);
      setApiKey("");
      setApiSecret("");
      setKeyError("");
    } catch (err) {
      setKeyError(err.message || "Failed to save. Is the backend running?");
    }
  }

  async function handleDisconnect(exchange) {
    await supabase.from("user_exchanges").update({ is_active: false }).eq("user_id", user.id).eq("exchange", exchange);
    setExchanges(prev => prev.map(e => e.exchange === exchange ? { ...e, is_active: false } : e));
  }

  if (!prefs) {
    return (
      <>
        <style>{responsiveCss}</style>
        <div style={styles.container}>
          <div style={{ color: MUTED, fontSize: 12 }}>Loading settings...</div>
        </div>
      </>
    );
  }

  return (
    <>
    <style>{responsiveCss}</style>
    <div style={styles.container}>
      <div style={styles.page} className="settings-page">
        <div style={styles.header}>
          <button style={styles.backBtn} onClick={() => navigate("/dashboard")}>&larr; Dashboard</button>
          <h1 style={styles.title}>SETTINGS</h1>
        </div>

        {/* Account */}
        <section style={styles.section}>
          <h2 style={styles.sectionTitle}>Account</h2>
          <div style={styles.row}>
            <span style={styles.rowLabel}>Email</span>
            <span>{profile?.email || user?.email}</span>
          </div>
          <div style={styles.row}>
            <span style={styles.rowLabel}>Plan</span>
            <span style={{ color: GOLD, textTransform: "capitalize" }}>{profile?.subscription_tier || "Starter"}</span>
          </div>
          <button style={styles.dangerBtn} onClick={signOut}>Sign Out</button>
        </section>

        {/* Connected Exchanges */}
        <section style={styles.section}>
          <h2 style={styles.sectionTitle}>Connected Exchanges</h2>
          {["coinbase", "kraken", "binance", "onchain"].map(ex => {
            const conn = exchanges.find(e => e.exchange === ex && e.is_active);
            return (
              <div key={ex} style={styles.exchangeRow}>
                <div>
                  <div style={styles.exchangeName}>{ex.charAt(0).toUpperCase() + ex.slice(1)}</div>
                  <div style={{ fontSize: 10, color: conn ? GREEN : MUTED }}>
                    {conn ? `Connected (${conn.connection_type})` : "Not connected"}
                  </div>
                </div>
                {conn ? (
                  <button style={styles.disconnectBtn} onClick={() => handleDisconnect(ex)}>Disconnect</button>
                ) : (
                  <button style={styles.connectBtn} onClick={() => setKeyModal(ex)}>
                    {ex === "coinbase" ? "Connect" : "Add Key"}
                  </button>
                )}
              </div>
            );
          })}
        </section>

        {/* Trading Preferences */}
        <section style={styles.section}>
          <h2 style={styles.sectionTitle}>Trading</h2>

          <label style={styles.label}>Strategy Preset</label>
          <select value={prefs.trading_preset} onChange={e => updatePref("trading_preset", e.target.value)} style={styles.select}>
            {presets.map(p => (
              <option key={p.id} value={p.id}>
                {p.name} {p.category ? `(${p.category})` : ""}
              </option>
            ))}
          </select>

          <label style={styles.label}>Risk Level</label>
          <div style={styles.riskRow}>
            {["conservative", "moderate", "aggressive"].map(r => (
              <button
                key={r}
                style={{ ...styles.riskBtn, ...(prefs.risk_level === r ? styles.riskActive : {}) }}
                onClick={() => updatePref("risk_level", r)}
              >
                {r.charAt(0).toUpperCase() + r.slice(1)}
              </button>
            ))}
          </div>

          <label style={styles.label}>Direction Bias</label>
          <div style={styles.riskRow}>
            {["long", "short", "both"].map(d => (
              <button
                key={d}
                style={{ ...styles.riskBtn, ...(prefs.direction_bias === d ? styles.riskActive : {}) }}
                onClick={() => updatePref("direction_bias", d)}
              >
                {d.charAt(0).toUpperCase() + d.slice(1)}
              </button>
            ))}
          </div>

          <label style={styles.label}>Coins</label>
          <div style={styles.coinGrid}>
            {ALL_COINS.map(c => (
              <button
                key={c}
                style={{ ...styles.coinBtn, ...((prefs.coins || []).includes(c) ? styles.coinActive : {}) }}
                onClick={() => toggleCoin(c)}
              >
                {c}
              </button>
            ))}
          </div>

          <label style={styles.label}>Paper Trading</label>
          <div style={styles.riskRow}>
            <button
              style={{ ...styles.riskBtn, ...(prefs.paper_trading ? { borderColor: GREEN, color: GREEN } : {}) }}
              onClick={() => updatePref("paper_trading", true)}
            >
              ON
            </button>
            <button
              style={{ ...styles.riskBtn, ...(!prefs.paper_trading ? { borderColor: RED, color: RED } : {}) }}
              onClick={() => updatePref("paper_trading", false)}
            >
              OFF (Live)
            </button>
          </div>

          <label style={styles.label}>Trade Approval Required</label>
          <div style={styles.riskRow}>
            <button
              style={{ ...styles.riskBtn, ...(prefs.require_trade_approval ? styles.riskActive : {}) }}
              onClick={() => updatePref("require_trade_approval", true)}
            >
              Yes
            </button>
            <button
              style={{ ...styles.riskBtn, ...(!prefs.require_trade_approval ? styles.riskActive : {}) }}
              onClick={() => updatePref("require_trade_approval", false)}
            >
              No
            </button>
          </div>

          <div style={styles.saveRow}>
            <button style={styles.saveBtn} onClick={handleSave} disabled={saving}>
              {saving ? "Saving..." : saved ? "\u2713 Saved" : "Save Changes"}
            </button>
          </div>
        </section>

        {/* API Key Modal */}
        {keyModal && (
          <div style={styles.modalOverlay} onClick={() => setKeyModal(null)}>
            <div style={styles.modal} className="settings-modal" onClick={e => e.stopPropagation()}>
              <h3 style={styles.modalTitle}>Add {keyModal.charAt(0).toUpperCase() + keyModal.slice(1)} API Key</h3>
              {keyError && <div style={styles.error}>{keyError}</div>}
              <input type="text" placeholder="API Key" value={apiKey} onChange={e => setApiKey(e.target.value)} style={styles.input} />
              <input type="password" placeholder="API Secret" value={apiSecret} onChange={e => setApiSecret(e.target.value)} style={{ ...styles.input, marginTop: 8 }} />
              <div style={{ display: "flex", gap: 8, marginTop: 16 }}>
                <button style={styles.backBtn} onClick={() => { setKeyModal(null); setKeyError(""); }}>Cancel</button>
                <button style={styles.saveBtn} onClick={handleAddKey}>Save Key</button>
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
    fontFamily: "'Space Mono', monospace",
    background: DARK,
    color: "#D4D4D4",
    minHeight: "100dvh",
    padding: "20px 16px",
    paddingBottom: "calc(20px + env(safe-area-inset-bottom, 0px))",
  },
  page: { maxWidth: 600, margin: "0 auto" },
  header: { display: "flex", alignItems: "center", gap: 16, marginBottom: 24 },
  title: {
    fontFamily: "'Bebas Neue', sans-serif",
    fontSize: 28,
    fontWeight: 400,
    letterSpacing: 4,
    color: GOLD,
    margin: 0,
  },
  backBtn: {
    fontFamily: "'Space Mono', monospace",
    fontSize: 12,
    padding: "6px 12px",
    background: "rgba(255,255,255,0.03)",
    backdropFilter: "blur(8px)",
    WebkitBackdropFilter: "blur(8px)",
    border: "1px solid rgba(255,255,255,0.06)",
    borderRadius: 8,
    color: MUTED,
    cursor: "pointer",
    transition: "all 0.2s ease",
  },
  section: {
    background: "rgba(17,17,17,0.55)",
    backdropFilter: "blur(20px) saturate(1.4)",
    WebkitBackdropFilter: "blur(20px) saturate(1.4)",
    border: "1px solid rgba(212,175,55,0.1)",
    borderRadius: 16,
    padding: "20px",
    marginBottom: 16,
    boxShadow: "0 8px 32px rgba(0,0,0,0.4), inset 0 1px 0 rgba(255,255,255,0.04)",
    transition: "border-color 0.3s ease, box-shadow 0.3s ease",
  },
  sectionTitle: {
    fontFamily: "'Oswald', sans-serif",
    fontSize: 14,
    fontWeight: 600,
    letterSpacing: 2,
    color: "#888",
    margin: "0 0 16px",
    textTransform: "uppercase",
  },
  row: {
    display: "flex",
    justifyContent: "space-between",
    fontSize: 12,
    padding: "8px 0",
    borderBottom: "1px solid rgba(255,255,255,0.04)",
  },
  rowLabel: { color: MUTED },
  label: { fontSize: 11, color: "#888", letterSpacing: 1, display: "block", marginTop: 14, marginBottom: 6 },
  select: {
    fontFamily: "'Space Mono', monospace",
    fontSize: 12,
    padding: "8px 10px",
    background: "rgba(10,10,10,0.6)",
    backdropFilter: "blur(8px)",
    WebkitBackdropFilter: "blur(8px)",
    border: "1px solid rgba(255,255,255,0.06)",
    borderRadius: 8,
    color: "#D4D4D4",
    width: "100%",
    transition: "border-color 0.2s ease",
  },
  input: {
    fontFamily: "'Space Mono', monospace",
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
  riskRow: { display: "flex", gap: 8 },
  riskBtn: {
    flex: 1,
    fontFamily: "'Space Mono', monospace",
    fontSize: 11,
    padding: "8px 0",
    background: "rgba(10,10,10,0.5)",
    backdropFilter: "blur(8px)",
    WebkitBackdropFilter: "blur(8px)",
    border: "1px solid rgba(255,255,255,0.06)",
    borderRadius: 8,
    color: "#D4D4D4",
    cursor: "pointer",
    textAlign: "center",
    transition: "all 0.2s ease",
  },
  riskActive: { borderColor: "rgba(212,175,55,0.4)", color: GOLD, background: "rgba(212,175,55,0.05)" },
  coinGrid: { display: "flex", flexWrap: "wrap", gap: 6 },
  coinBtn: {
    fontFamily: "'Space Mono', monospace",
    fontSize: 11,
    padding: "5px 10px",
    background: "rgba(10,10,10,0.5)",
    backdropFilter: "blur(8px)",
    WebkitBackdropFilter: "blur(8px)",
    border: "1px solid rgba(255,255,255,0.06)",
    borderRadius: 8,
    color: "#D4D4D4",
    cursor: "pointer",
    transition: "all 0.2s ease",
  },
  coinActive: { borderColor: "rgba(212,175,55,0.4)", color: GOLD, background: "rgba(212,175,55,0.05)" },
  exchangeRow: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    padding: "10px 0",
    borderBottom: "1px solid rgba(255,255,255,0.04)",
  },
  exchangeName: { fontSize: 13, fontWeight: 600 },
  connectBtn: {
    fontFamily: "'Oswald', sans-serif",
    fontSize: 11,
    letterSpacing: 1,
    padding: "5px 12px",
    border: "1px solid rgba(212,175,55,0.3)",
    borderRadius: 6,
    background: "rgba(212,175,55,0.05)",
    color: GOLD,
    cursor: "pointer",
    transition: "all 0.2s ease",
  },
  disconnectBtn: {
    fontFamily: "'Space Mono', monospace",
    fontSize: 10,
    padding: "5px 10px",
    border: "1px solid rgba(192,57,43,0.3)",
    borderRadius: 6,
    background: "rgba(192,57,43,0.05)",
    color: RED,
    cursor: "pointer",
    transition: "all 0.2s ease",
  },
  dangerBtn: {
    fontFamily: "'Space Mono', monospace",
    fontSize: 11,
    padding: "8px 16px",
    border: "1px solid rgba(192,57,43,0.3)",
    borderRadius: 8,
    background: "rgba(192,57,43,0.05)",
    color: RED,
    cursor: "pointer",
    marginTop: 12,
    transition: "all 0.2s ease",
  },
  saveRow: { marginTop: 20, textAlign: "right" },
  saveBtn: {
    fontFamily: "'Oswald', sans-serif",
    fontSize: 13,
    fontWeight: 600,
    letterSpacing: 2,
    padding: "10px 24px",
    border: "none",
    borderRadius: 10,
    cursor: "pointer",
    background: `linear-gradient(180deg, ${GOLD}, #B8860B)`,
    color: DARK,
    boxShadow: "0 4px 20px rgba(212,175,55,0.2)",
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
    boxShadow: "0 24px 64px rgba(0,0,0,0.5), inset 0 1px 0 rgba(255,255,255,0.06)",
  },
  modalTitle: {
    fontFamily: "'Bebas Neue', sans-serif",
    fontSize: 20,
    letterSpacing: 2,
    color: GOLD,
    margin: "0 0 16px",
  },
  error: {
    fontSize: 12,
    color: RED,
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
  .settings-page {
    max-width: 100% !important;
    padding: 0 !important;
  }
  .settings-modal {
    margin: 16px !important;
    max-width: calc(100vw - 32px) !important;
    box-sizing: border-box !important;
  }
}
@media (max-width: 375px) {
  .settings-page {
    padding: 0 !important;
  }
  .settings-modal {
    margin: 10px !important;
    max-width: calc(100vw - 20px) !important;
    padding: 20px 16px !important;
  }
}
@media (max-width: 320px) {
  .settings-modal {
    margin: 8px !important;
    max-width: calc(100vw - 16px) !important;
    padding: 16px 12px !important;
  }
}
`;
