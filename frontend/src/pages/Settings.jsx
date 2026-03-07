import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext.jsx";
import { useAuthHeaders } from "../hooks/useAuthHeaders.js";
import { supabase } from "../supabaseClient.js";
import { colors, typography } from "../theme.js";
import { ArrowLeft, Check, ArrowRight, Lightbulb, Zap, X, Info } from "lucide-react";

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

const COIN_CATEGORIES = {
  "Major": ["BTC", "ETH", "XRP", "BNB", "SOL", "ADA", "DOGE", "TRX", "TON", "LTC"],
  "Large Cap Alts": ["AVAX", "DOT", "LINK", "NEAR", "APT", "SUI", "OP", "ARB", "ATOM", "ICP", "STX", "VET", "FIL", "HBAR", "ETC", "MNT", "XLM", "BCH"],
  "Meme": ["DOGE", "SHIB", "PEPE", "FLOKI", "BONK", "WIF", "MEME", "BOME", "COQ", "BRETT", "MOG", "NEIRO", "PNUT", "TURBO", "POPCAT", "MEW", "CAT", "FWOG"],
  "DeFi": ["UNI", "AAVE", "MKR", "CRV", "LDO", "COMP", "SNX", "BAL", "YFI", "1INCH", "SUSHI", "DYDX", "GMX", "PENDLE", "ENA", "ETHFI", "EIGEN", "MORPHO"],
  "L2 / Ecosystem": ["OP", "ARB", "MATIC", "STRK", "IMX", "ZK", "MANTA", "SCROLL", "METIS", "BOBA", "BLAST", "BASE", "CYBER", "TAIKO"],
  "Gaming / Meta": ["AXS", "SAND", "MANA", "ENJ", "GALA", "ILV", "GODS", "YGG", "PYR", "RON", "SLP", "PRIME", "BEAM", "MAGIC"],
  "AI / Data": ["FET", "AGIX", "OCEAN", "RNDR", "WLD", "TAO", "GRT", "NMR", "ARKM", "AIXBT", "VIRTUAL", "KAITO", "ATH"],
  "RWA / Infra": ["ONDO", "POLYX", "CFG", "MPL", "TRU", "PRCL", "ALTA", "QRDO", "POL", "CELESTIA", "TIA", "PYTH", "JTO", "JUP", "WEN"],
};
const ALL_COINS = [...new Set(Object.values(COIN_CATEGORIES).flat())];
const COIN_CATEGORY_KEYS = ["All", ...Object.keys(COIN_CATEGORIES)];

const TIER_MAX_EXCHANGES = { none: 0, starter: 1, pro: 3, elite: 10 };

const EXCHANGES_META = {
  kraken: {
    name: "Kraken",
    keyPlaceholder: "API Key (e.g. XXXX-XXXX-XXXX-XXXX)",
    secretPlaceholder: "Private Key / API Secret",
    keyHint: "Kraken API keys are alphanumeric strings (usually 56 characters). Enable Spot trading, Futures trading, and margin permissions. The only permission to leave OFF is Withdraw Funds.",
    keyPattern: /^[A-Za-z0-9+/=]{40,90}$/,
    keyPatternHint: "Must be 40–90 alphanumeric characters (no spaces).",
  },
  binance: {
    name: "Binance",
    keyPlaceholder: "API Key (64 characters)",
    secretPlaceholder: "Secret Key (64 characters)",
    keyHint: "Binance API keys are exactly 64 hexadecimal characters. Enable Spot trading AND Futures trading. The only permission to leave OFF is Enable Withdrawals.",
    keyPattern: /^[A-Za-z0-9]{60,70}$/,
    keyPatternHint: "Must be exactly 64 alphanumeric characters (no spaces or dashes).",
  },
};
export default function Settings() {
  const { user, profile, signOut, accessToken } = useAuth();
  const getAuthHeaders = useAuthHeaders();
  const navigate = useNavigate();
  const [prefs, setPrefs] = useState(null);
  const [coinCategory, setCoinCategory] = useState("All");
  const [coinSearch, setCoinSearch] = useState("");
  const [customCoin, setCustomCoin] = useState("");
  const [exchanges, setExchanges] = useState([]);
  const [presets, setPresets] = useState(PRESETS_FALLBACK);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [loadError, setLoadError] = useState(false);
  const [backendConfig, setBackendConfig] = useState({
    min_trade_usd: 75,
    min_profit_after_costs: 5,
    round_trip_fee: 0.012,
    max_position_size: 0.1,
  });

  const [keyModal, setKeyModal] = useState(null);
  const [apiKey, setApiKey] = useState("");
  const [apiSecret, setApiSecret] = useState("");
  const [walletAddress, setWalletAddress] = useState("");
  const [keyError, setKeyError] = useState("");

  useEffect(() => {
    if (!user) return;
    let cancelled = false;
    const timer = setTimeout(() => {
      if (!cancelled) setLoadError(true);
    }, 6000);
    supabase.from("user_preferences").select("*").eq("user_id", user.id).single()
      .then(({ data }) => {
        if (!cancelled) {
          clearTimeout(timer);
          if (data) setPrefs(data);
          else setLoadError(true);
        }
      })
      .catch(() => { if (!cancelled) setLoadError(true); });
    supabase.from("user_exchanges").select("exchange, connection_type, is_active").eq("user_id", user.id)
      .then(({ data }) => { if (!cancelled && data) setExchanges(data); });
    return () => { cancelled = true; clearTimeout(timer); };
  }, [user]);

  useEffect(() => {
    const base = (import.meta.env.VITE_BACKEND_URL || "").replace(/\/$/, "") || "";
    const url = base ? `${base}/api/presets` : "/api/presets";
    const configUrl = base ? `${base}/api/config` : "/api/config";
    
    fetch(url, { headers: getAuthHeaders() }).then(r => r.ok && r.json()).then(d => {
      if (d?.presets?.length) setPresets(d.presets);
    }).catch(() => { });

    fetch(configUrl, { headers: getAuthHeaders() }).then(r => r.ok && r.json()).then(d => {
      if (d) setBackendConfig(prev => ({ ...prev, ...d }));
    }).catch(() => { });
  }, [getAuthHeaders]);

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
      // Save to Supabase directly
      await supabase.from("user_preferences").update(rest).eq("user_id", user.id);
      // Also call backend to bust server-side user_config cache (takes effect instantly on bot)
      if (accessToken) {
        const base = (import.meta.env.VITE_BACKEND_URL || "").replace(/\/$/, "") || "";
        const prefsUrl = base ? `${base}/auth/preferences` : "/auth/preferences";
        fetch(prefsUrl, {
          method: "PUT",
          headers: { "Content-Type": "application/json", "Authorization": `Bearer ${accessToken}` },
          body: JSON.stringify(rest),
        }).catch(() => {}); // fire-and-forget; Supabase save already succeeded
      }
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch {
      // ignore
    } finally {
      setSaving(false);
    }
  }

  async function handleConnectCoinbase() {
    // Coinbase uses OAuth / AgentKit — no API key validation needed, just record the connection
    if (!accessToken) {
      setKeyError("Please sign in to connect Coinbase");
      return;
    }
    try {
      const base = (import.meta.env.VITE_BACKEND_URL || "").replace(/\/$/, "") || "";
      const connectUrl = base ? `${base}/auth/exchanges/connect` : "/auth/exchanges/connect";
      const headers = { "Content-Type": "application/json", "Authorization": `Bearer ${accessToken}` };
      const connectRes = await fetch(connectUrl, {
        method: "POST",
        headers,
        body: JSON.stringify({ exchange: "coinbase", connection_type: "coinbase_oauth" }),
      });
      if (!connectRes.ok) {
        const errData = await connectRes.json().catch(() => ({}));
        throw new Error(errData.error || "Failed to connect Coinbase");
      }
      const { data: exData } = await supabase.from("user_exchanges").select("exchange, connection_type, is_active").eq("user_id", user.id);
      setExchanges(exData || []);
      setKeyModal(null);
      setKeyError("");
    } catch (err) {
      setKeyError(err.message || "Failed to connect. Is the backend running?");
    }
  }

  async function handleConnectOnchain() {
    if (!walletAddress?.trim()) {
      setKeyError("Wallet address is required.");
      return;
    }
    if (!accessToken) {
      setKeyError("Please sign in to connect on-chain.");
      return;
    }
    try {
      const base = (import.meta.env.VITE_BACKEND_URL || "").replace(/\/$/, "") || "";
      const connectUrl = base ? `${base}/auth/exchanges/connect` : "/auth/exchanges/connect";
      const headers = { "Content-Type": "application/json", "Authorization": `Bearer ${accessToken}` };
      const connectRes = await fetch(connectUrl, {
        method: "POST",
        headers,
        body: JSON.stringify({
          exchange: "onchain",
          connection_type: "wallet",
          wallet_address: walletAddress.trim(),
        }),
      });
      if (!connectRes.ok) {
        const errData = await connectRes.json().catch(() => ({}));
        throw new Error(errData.error || "Failed to save wallet");
      }
      const { data: exData } = await supabase.from("user_exchanges").select("exchange, connection_type, is_active").eq("user_id", user.id);
      setExchanges(exData || []);
      setKeyModal(null);
      setWalletAddress("");
      setKeyError("");
    } catch (err) {
      setKeyError(err.message || "Failed to save. Is the backend running?");
    }
  }

  async function handleAddKey() {
    if (!apiKey?.trim() || !apiSecret?.trim()) {
      setKeyError("Both API key and secret are required.");
      return;
    }
    const exMeta = EXCHANGES_META[keyModal];
    if (exMeta?.keyPattern && !exMeta.keyPattern.test(apiKey.trim())) {
      setKeyError(`Invalid ${exMeta.name} API key format. ${exMeta.keyPatternHint}`);
      return;
    }
    if (!accessToken) {
      setKeyError("Please sign in to add exchange keys");
      return;
    }
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
      const { data: exData } = await supabase.from("user_exchanges").select("exchange, connection_type, is_active").eq("user_id", user.id);
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

  if (loadError) {
    return (
      <>
        <style>{responsiveCss}</style>
        <div style={styles.container}>
          <div style={{ color: "#C0392B", fontSize: 12, textAlign: "center", paddingTop: 60 }}>
            Could not load settings. Check your connection and try again.
            <br /><br />
            <button style={styles.saveBtn} onClick={() => window.location.reload()}>Retry</button>
          </div>
        </div>
      </>
    );
  }

  if (!prefs) {
    return (
      <>
        <style>{responsiveCss}</style>
        <div style={styles.container}>
          <div style={{ color: colors.muted, fontSize: 12 }}>Loading settings...</div>
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
            <button style={styles.backBtn} onClick={() => navigate("/dashboard")}><ArrowLeft size={14} style={{ marginRight: "4px", verticalAlign: "middle" }} /> Dashboard</button>
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
              <span style={{ color: colors.gold, textTransform: "capitalize" }}>{profile?.subscription_tier || "None"}</span>
            </div>
            {(user?.email === "feichangfuyou@gmail.com" || profile?.role === "admin") && (
              <div style={styles.row}>
                <span style={styles.rowLabel}>Administration</span>
                <button 
                  style={{ ...styles.legalBtn, borderColor: colors.gold, color: colors.gold }} 
                  onClick={() => navigate("/admin")}
                >
                  OPEN ADMIN CONSOLE <ArrowRight size={14} style={{ marginLeft: "4px", verticalAlign: "middle" }} />
                </button>
              </div>
            )}
            <button style={styles.dangerBtn} onClick={signOut}>Sign Out</button>
          </section>

          {/* Connected Exchanges */}
          <section style={styles.section}>
            <h2 style={styles.sectionTitle}>Connected Exchanges</h2>
            {["coinbase", "kraken", "binance", "onchain"].map(ex => {
              const conn = exchanges.find(e => e.exchange === ex && e.is_active);
              const connectedCount = exchanges.filter(e => e.is_active).length;
              const maxExchanges = TIER_MAX_EXCHANGES[profile?.subscription_tier || "none"] ?? 0;
              const atLimit = !conn && connectedCount >= maxExchanges;
              const exLabel = ex === "coinbase" ? "Coinbase" : ex === "onchain" ? "On-Chain" : ex.charAt(0).toUpperCase() + ex.slice(1);
              const btnLabel = ex === "coinbase" ? "Connect" : ex === "onchain" ? "Add Wallet" : "Add Key";
              return (
                <div key={ex} style={styles.exchangeRow}>
                  <div>
                    <div style={styles.exchangeName}>{exLabel}</div>
                    <div style={{ fontSize: 10, color: conn ? colors.success : colors.muted }}>
                      {conn ? `Connected (${conn.connection_type})` : "Not connected"}
                    </div>
                  </div>
                  {conn ? (
                    <button style={styles.disconnectBtn} onClick={() => handleDisconnect(ex)}>Disconnect</button>
                  ) : atLimit ? (
                    <button style={styles.connectBtn} onClick={() => navigate("/billing")}>
                      Upgrade to add more
                    </button>
                  ) : (
                    <button style={styles.connectBtn} onClick={() => { setKeyModal(ex); setKeyError(""); setApiKey(""); setApiSecret(""); setWalletAddress(""); }}>
                      {btnLabel}
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

            <label style={styles.label}>Coins to Trade</label>

            {/* Category Tab Bar */}
            <div style={styles.coinCatBar}>
              {COIN_CATEGORY_KEYS.map(cat => (
                <button
                  key={cat}
                  id={`coin-cat-${cat.toLowerCase().replace(/[^a-z0-9]/g, "-")}`}
                  style={{
                    ...styles.coinCatBtn,
                    ...(coinCategory === cat ? styles.coinCatActive : {}),
                  }}
                  onClick={() => setCoinCategory(cat)}
                >
                  {cat}
                  {cat !== "All" && (() => {
                    const catCoins = COIN_CATEGORIES[cat] || [];
                    const selected = (prefs.coins || []).filter(c => catCoins.includes(c)).length;
                    return selected > 0 ? (
                      <span style={styles.coinCatBadge}>{selected}</span>
                    ) : null;
                  })()}
                  {cat === "All" && (() => {
                    const total = (prefs.coins || []).length;
                    return total > 0 ? (
                      <span style={styles.coinCatBadge}>{total}</span>
                    ) : null;
                  })()}
                </button>
              ))}
            </div>

            {/* Per-category select/clear helpers */}
            {coinCategory !== "All" && (
              <div style={styles.coinCatActions}>
                <button style={styles.coinCatActionBtn} onClick={() => {
                  const cats = COIN_CATEGORIES[coinCategory] || [];
                  const current = prefs.coins || [];
                  const merged = [...new Set([...current, ...cats])];
                  updatePref("coins", merged);
                }}>
                  Select All
                </button>
                <button style={styles.coinCatActionBtn} onClick={() => {
                  const cats = COIN_CATEGORIES[coinCategory] || [];
                  const current = prefs.coins || [];
                  updatePref("coins", current.filter(c => !cats.includes(c)));
                }}>
                  Clear
                </button>
                <span style={styles.coinCatCount}>
                  {(prefs.coins || []).filter(c => (COIN_CATEGORIES[coinCategory] || []).includes(c)).length}
                  /{(COIN_CATEGORIES[coinCategory] || []).length} selected
                </span>
              </div>
            )}
            {coinCategory === "All" && (
              <div style={styles.coinCatActions}>
                <button style={styles.coinCatActionBtn} onClick={() => updatePref("coins", [...ALL_COINS])}>
                  Select All
                </button>
                <button style={styles.coinCatActionBtn} onClick={() => updatePref("coins", [])}>
                  Clear All
                </button>
                <span style={styles.coinCatCount}>
                  {(prefs.coins || []).length}/{ALL_COINS.length} selected
                </span>
              </div>
            )}

            {/* Search and Custom Symbol Input */}
            <div style={{ display: "flex", gap: 8, marginBottom: 12 }}>
              <input
                type="text"
                placeholder="Search symbols..."
                value={coinSearch}
                onChange={e => setCoinSearch(e.target.value)}
                style={{ ...styles.input, flex: 2, padding: "6px 10px" }}
              />
              <div style={{ display: "flex", flex: 1, gap: 4 }}>
                <input
                  type="text"
                  placeholder="+ Symbol"
                  value={customCoin}
                  onChange={e => setCustomCoin(e.target.value.toUpperCase())}
                  onKeyPress={e => {
                    if (e.key === "Enter" && customCoin.trim()) {
                      const c = customCoin.trim().toUpperCase();
                      if (!ALL_COINS.includes(c) && !(prefs.coins || []).includes(c)) {
                        toggleCoin(c);
                        setCustomCoin("");
                      }
                    }
                  }}
                  style={{ ...styles.input, padding: "6px 10px", width: "100%" }}
                />
                <button 
                  onClick={() => {
                    if (customCoin.trim()) {
                      const c = customCoin.trim().toUpperCase();
                      if (!ALL_COINS.includes(c) && !(prefs.coins || []).includes(c)) {
                        toggleCoin(c);
                        setCustomCoin("");
                      }
                    }
                  }}
                  style={{ ...styles.coinCatActionBtn, padding: "0 10px", height: "auto" }}
                >
                  Add
                </button>
              </div>
            </div>

            {/* Coin Chip Grid */}
            <div style={styles.coinGrid}>
              {(coinCategory === "Selected" ? (prefs.coins || []) : (coinCategory === "All" ? ALL_COINS : (COIN_CATEGORIES[coinCategory] || [])))
                .filter(c => !coinSearch || c.toLowerCase().includes(coinSearch.toLowerCase()))
                .map(c => (
                  <button
                    key={c}
                    id={`coin-toggle-${c.toLowerCase()}`}
                    style={{ ...styles.coinBtn, ...((prefs.coins || []).includes(c) ? styles.coinActive : {}) }}
                    onClick={() => toggleCoin(c)}
                  >
                    {c}{!ALL_COINS.includes(c) ? " (custom)" : ""}
                  </button>
                ))}
              {/* If in 'All' tab, we also want to show custom coins that aren't in the global list */}
              {coinCategory === "All" && (prefs.coins || [])
                .filter(c => !ALL_COINS.includes(c))
                .filter(c => !coinSearch || c.toLowerCase().includes(coinSearch.toLowerCase()))
                .map(c => (
                  <button
                    key={c}
                    id={`coin-toggle-${c.toLowerCase()}`}
                    style={{ ...styles.coinBtn, ...styles.coinActive }}
                    onClick={() => toggleCoin(c)}
                  >
                    {c} (custom)
                  </button>
                ))
              }
            </div>

            <label style={styles.label}>Paper Trading</label>
            <div style={styles.riskRow}>
              <button
                style={{ ...styles.riskBtn, ...(prefs.paper_trading ? { borderColor: colors.success, color: colors.success } : {}) }}
                onClick={() => updatePref("paper_trading", true)}
              >
                ON
              </button>
              <button
                style={{ ...styles.riskBtn, ...(!prefs.paper_trading ? { borderColor: colors.error, color: colors.error } : {}) }}
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

            {/* Minimum Capital Requirements Info Panel */}
            <div style={styles.capitalBox}>
              <div style={styles.capitalHeader}>
                <Lightbulb size={20} color={colors.gold} />
                <span style={styles.capitalTitle}>Real Money Requirements</span>
              </div>
              <p style={styles.capitalIntro}>
                Before switching to <strong style={{ color: "#e05f5f" }}>live trading</strong>, make sure your account meets these minimums — the bot enforces them automatically.
              </p>
              <div style={styles.capitalGrid} className="capital-grid">
                <div style={styles.capitalItem}>
                  <div style={styles.capitalValue}>${backendConfig.min_trade_usd}</div>
                  <div style={styles.capitalLabel}>Min trade size</div>
                  <div style={styles.capitalSub}>Per position. Smaller trades are rejected.</div>
                </div>
                <div style={styles.capitalItem}>
                  <div style={styles.capitalValue}>${Math.round(backendConfig.min_trade_usd / backendConfig.max_position_size)}</div>
                  <div style={styles.capitalLabel}>Recommended balance</div>
                  <div style={styles.capitalSub}>{(backendConfig.max_position_size * 100).toFixed(0)}% position = ${backendConfig.min_trade_usd} trade. Below ${Math.round(backendConfig.min_trade_usd / backendConfig.max_position_size)} blocks most trades.</div>
                </div>
                <div style={styles.capitalItem}>
                  <div style={styles.capitalValue}>{(backendConfig.round_trip_fee * 100).toFixed(1)}%</div>
                  <div style={styles.capitalLabel}>Round-trip fees</div>
                  <div style={styles.capitalSub}>{(backendConfig.round_trip_fee * 50).toFixed(1)}% in + {(backendConfig.round_trip_fee * 50).toFixed(1)}% out (taker fee).</div>
                </div>
                <div style={styles.capitalItem}>
                  <div style={styles.capitalValue}>${backendConfig.min_profit_after_costs}</div>
                  <div style={styles.capitalLabel}>Min net profit at TP</div>
                  <div style={styles.capitalSub}>Each trade&apos;s take-profit must clear ${backendConfig.min_profit_after_costs} after all fees or it&apos;s rejected.</div>
                </div>
              </div>
              <div style={styles.capitalNote}>
                <Zap size={14} /> <strong>Why these limits?</strong> A ${backendConfig.min_trade_usd} trade costs ~${(backendConfig.min_trade_usd * backendConfig.round_trip_fee).toFixed(2)} in exchange fees + AI costs. We require the take-profit to net at least ${backendConfig.min_profit_after_costs} above all costs.
              </div>
            </div>

            <div style={styles.saveRow}>
              <button style={styles.saveBtn} onClick={handleSave} disabled={saving}>
                {saving ? "Saving..." : saved ? <span style={{ display: "flex", alignItems: "center", gap: "4px" }}><Check size={14} /> Saved</span> : "Save Changes"}
              </button>
            </div>
          </section>

          {/* Support & Legal */}
          <section style={styles.section}>
            <h2 style={styles.sectionTitle}>Support & Legal</h2>
            <div style={styles.row}>
              <span style={styles.rowLabel}>Privacy Policy</span>
              <button style={styles.legalBtn} onClick={() => navigate("/privacy")}>Read Policy</button>
            </div>
            <div style={styles.row}>
              <span style={styles.rowLabel}>Terms of Service</span>
              <button style={styles.legalBtn} onClick={() => navigate("/terms")}>Read Terms</button>
            </div>
            <div style={styles.row}>
              <span style={styles.rowLabel}>Support</span>
              <button style={styles.legalBtn} onClick={() => window.location.href = "mailto:support@doyou.trade"}>Email Support</button>
            </div>
            <div style={{ marginTop: 16, textAlign: "center", color: "#3a3a3a", fontSize: 9, letterSpacing: 1, fontFamily: "'Montserrat', sans-serif" }}>
              © 2025 DOYOU.TRADE
            </div>
          </section>

          {/* Exchange Connection Modals */}
          {keyModal && (() => {
            const exMeta = EXCHANGES_META[keyModal];
            const closeModal = () => { setKeyModal(null); setApiKey(""); setApiSecret(""); setWalletAddress(""); setKeyError(""); };

            /* ── COINBASE: direct connect (no API key needed) ── */
            if (keyModal === "coinbase") {
              return (
                <div style={styles.modalOverlay} onClick={closeModal}>
                  <div style={styles.modal} className="settings-modal" onClick={e => e.stopPropagation()}>
                    <h3 style={styles.modalTitle}>Connect Coinbase</h3>
                     <div style={styles.keyHintBanner}>
                       <Info size={14} style={{ color: colors.gold, marginRight: 6 }} />
                       Coinbase is connected via your account credentials (the API keys you entered in the server .env). Click Connect to link your Coinbase account to your bot profile.
                     </div>
                    {keyError && <div style={styles.error}>{keyError}</div>}
                    <div style={{ display: "flex", gap: 8, marginTop: 16 }}>
                      <button style={styles.backBtn} onClick={closeModal}>Cancel</button>
                      <button style={styles.saveBtn} onClick={handleConnectCoinbase}>Connect</button>
                    </div>
                  </div>
                </div>
              );
            }

            /* ── ONCHAIN: wallet address ── */
            if (keyModal === "onchain") {
              return (
                <div style={styles.modalOverlay} onClick={closeModal}>
                  <div style={styles.modal} className="settings-modal" onClick={e => e.stopPropagation()}>
                    <h3 style={styles.modalTitle}>Add On-Chain Wallet</h3>
                     <div style={styles.keyHintBanner}>
                       <Info size={14} style={{ color: colors.gold, marginRight: 6 }} />
                       Enter your wallet address (e.g. Base/Ethereum). The bot uses Coinbase AgentKit to execute on-chain trades — no private key is stored.
                     </div>
                    {keyError && <div style={styles.error}>{keyError}</div>}
                    <input
                      id="settings-wallet-address"
                      type="text"
                      placeholder="0x... wallet address"
                      value={walletAddress}
                      onChange={e => { setWalletAddress(e.target.value); setKeyError(""); }}
                      style={styles.input}
                      autoComplete="off"
                      spellCheck={false}
                    />
                    <div style={styles.fieldHint}>Your Base / Ethereum wallet address (starts with 0x).</div>
                    <div style={{ display: "flex", gap: 8, marginTop: 16 }}>
                      <button style={styles.backBtn} onClick={closeModal}>Cancel</button>
                      <button style={styles.saveBtn} onClick={handleConnectOnchain} disabled={!walletAddress.trim()}>Save Wallet</button>
                    </div>
                  </div>
                </div>
              );
            }

            /* ── KRAKEN / BINANCE: full API key + validation ── */
            const exName = exMeta?.name || (keyModal.charAt(0).toUpperCase() + keyModal.slice(1));
            return (
              <div style={styles.modalOverlay} onClick={closeModal}>
                <div style={styles.modal} className="settings-modal" onClick={e => e.stopPropagation()}>
                  <h3 style={styles.modalTitle}>Add {exName} API Key</h3>

                   {exMeta?.keyHint && (
                     <div style={styles.keyHintBanner}>
                       <Info size={14} style={{ color: colors.gold, marginRight: 6 }} />
                       {exMeta.keyHint}
                     </div>
                   )}

                  {keyError && <div style={styles.error}>{keyError}</div>}

                  <input
                    id={`settings-api-key-${keyModal}`}
                    type="text"
                    placeholder={exMeta?.keyPlaceholder || "API Key"}
                    value={apiKey}
                    onChange={e => { setApiKey(e.target.value); setKeyError(""); }}
                    style={styles.input}
                    autoComplete="off"
                    spellCheck={false}
                  />
                  {exMeta?.keyPatternHint && (
                    <div style={styles.fieldHint}>{exMeta.keyPatternHint}</div>
                  )}
                  <input
                    id={`settings-api-secret-${keyModal}`}
                    type="password"
                    placeholder={exMeta?.secretPlaceholder || "API Secret"}
                    value={apiSecret}
                    onChange={e => { setApiSecret(e.target.value); setKeyError(""); }}
                    style={{ ...styles.input, marginTop: 10 }}
                    autoComplete="new-password"
                  />

                  <div style={styles.keyInfo}>
                    <div style={styles.keyInfoTitle}>Enable these permissions on your key:</div>
                    <div style={styles.keyPerm}><Check size={12} style={{ color: colors.success }} /> View / Query Funds &amp; Balances</div>
                    <div style={styles.keyPerm}><Check size={12} style={{ color: colors.success }} /> Query Orders &amp; Trade History</div>
                    <div style={styles.keyPerm}><Check size={12} style={{ color: colors.success }} /> Spot Trading (Create &amp; Modify Orders)</div>
                    <div style={styles.keyPerm}><Check size={12} style={{ color: colors.success }} /> Futures / Derivatives Trading</div>
                    <div style={styles.keyPerm}><X size={12} style={{ color: colors.error }} /> Withdraw Funds — leave <strong>OFF</strong></div>
                  </div>

                  <div style={{ display: "flex", gap: 8, marginTop: 16 }}>
                    <button style={styles.backBtn} onClick={closeModal}>Cancel</button>
                    <button style={styles.saveBtn} onClick={handleAddKey} disabled={!apiKey.trim() || !apiSecret.trim()}>Save Key</button>
                  </div>
                </div>
              </div>
            );
          })()}
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
    padding: "20px 16px",
    paddingBottom: "calc(20px + env(safe-area-inset-bottom, 0px))",
  },
  page: { maxWidth: 600, margin: "0 auto" },
  header: { display: "flex", alignItems: "center", gap: 16, marginBottom: 24 },
  title: {
    fontFamily: typography.fontDisplay,
    fontSize: 28,
    fontWeight: 400,
    letterSpacing: 4,
    color: colors.gold,
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
    color: colors.muted,
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
    fontFamily: "'Montserrat', sans-serif",
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
  rowLabel: { color: colors.muted },
  label: { fontSize: 11, color: "#888", letterSpacing: 1, display: "block", marginTop: 14, marginBottom: 6 },
  capitalBox: {
    marginTop: 20,
    background: "rgba(212,175,55,0.04)",
    border: "1px solid rgba(212,175,55,0.18)",
    borderRadius: 14,
    padding: "16px 18px",
    backdropFilter: "blur(12px)",
    WebkitBackdropFilter: "blur(12px)",
  },
  capitalHeader: {
    display: "flex",
    alignItems: "center",
    gap: 8,
    marginBottom: 8,
  },
  capitalIcon: { fontSize: 16 },
  capitalTitle: {
    fontFamily: "'Montserrat', sans-serif",
    fontSize: 12,
    fontWeight: 700,
    letterSpacing: 2,
    color: colors.gold,
    textTransform: "uppercase",
  },
  capitalIntro: {
    fontSize: 11,
    color: colors.muted,
    lineHeight: 1.6,
    margin: "0 0 14px",
  },
  capitalGrid: {
    display: "grid",
    gridTemplateColumns: "1fr 1fr",
    gap: 10,
    marginBottom: 12,
  },
  // We'll handle grid responsiveness in responsiveCss via a class
  capitalItem: {
    background: "rgba(0,0,0,0.25)",
    border: "1px solid rgba(255,255,255,0.05)",
    borderRadius: 10,
    padding: "10px 12px",
  },
  capitalValue: {
    fontFamily: "'Montserrat', sans-serif",
    fontSize: 22,
    fontWeight: 700,
    color: colors.gold,
    letterSpacing: 1,
    lineHeight: 1,
    marginBottom: 3,
  },
  capitalLabel: {
    fontSize: 10,
    fontWeight: 600,
    color: "#ccc",
    letterSpacing: 1,
    textTransform: "uppercase",
    marginBottom: 3,
  },
  capitalSub: {
    fontSize: 10,
    color: "#666",
    lineHeight: 1.4,
  },
  capitalNote: {
    fontSize: 10,
    color: "#888",
    lineHeight: 1.6,
    background: "rgba(0,0,0,0.2)",
    border: "1px solid rgba(255,255,255,0.04)",
    borderRadius: 8,
    padding: "8px 10px",
  },
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
  riskActive: { borderColor: `${colors.gold}66`, color: colors.gold, background: `${colors.gold}0D` },
  coinCatBar: {
    display: "flex",
    flexWrap: "wrap",
    gap: 5,
    marginBottom: 8,
    padding: "6px",
    background: "rgba(0,0,0,0.2)",
    borderRadius: 10,
    border: "1px solid rgba(255,255,255,0.04)",
  },
  coinCatBtn: {
    fontFamily: "'Space Mono', monospace",
    fontSize: 10,
    padding: "4px 9px",
    background: "transparent",
    border: "1px solid rgba(255,255,255,0.07)",
    borderRadius: 6,
    color: "#888",
    cursor: "pointer",
    transition: "all 0.18s ease",
    display: "flex",
    alignItems: "center",
    gap: 4,
    whiteSpace: "nowrap",
    letterSpacing: 0.5,
  },
  coinCatActive: {
    background: `${colors.gold}18`,
    borderColor: `${colors.gold}55`,
    color: colors.gold,
    boxShadow: `0 0 8px ${colors.gold}22`,
  },
  coinCatBadge: {
    background: `${colors.gold}33`,
    color: colors.gold,
    fontSize: 9,
    fontWeight: 700,
    borderRadius: 20,
    padding: "1px 5px",
    minWidth: 14,
    textAlign: "center",
  },
  coinCatActions: {
    display: "flex",
    alignItems: "center",
    gap: 6,
    marginBottom: 8,
  },
  coinCatActionBtn: {
    fontFamily: "'Space Mono', monospace",
    fontSize: 9,
    padding: "3px 8px",
    background: "rgba(255,255,255,0.04)",
    border: "1px solid rgba(255,255,255,0.07)",
    borderRadius: 5,
    color: "#888",
    cursor: "pointer",
    transition: "all 0.15s ease",
    letterSpacing: 0.3,
  },
  coinCatCount: {
    fontSize: 10,
    color: "#555",
    marginLeft: "auto",
    fontFamily: "'Space Mono', monospace",
  },
  coinGrid: { display: "flex", flexWrap: "wrap", gap: 5, maxHeight: 220, overflowY: "auto", paddingRight: 2 },
  coinBtn: {
    fontFamily: "'Space Mono', monospace",
    fontSize: 10,
    padding: "5px 10px",
    background: "rgba(10,10,10,0.5)",
    backdropFilter: "blur(8px)",
    WebkitBackdropFilter: "blur(8px)",
    border: "1px solid rgba(255,255,255,0.06)",
    borderRadius: 7,
    color: "#A0A0A0",
    cursor: "pointer",
    transition: "all 0.18s ease",
    letterSpacing: 0.5,
  },
  coinActive: { borderColor: `${colors.gold}66`, color: colors.gold, background: `${colors.gold}11`, boxShadow: `0 0 6px ${colors.gold}22` },
  exchangeRow: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    padding: "10px 0",
    borderBottom: "1px solid rgba(255,255,255,0.04)",
  },
  exchangeName: { fontSize: 13, fontWeight: 600 },
  connectBtn: {
    fontFamily: "'Montserrat', sans-serif",
    fontSize: 11,
    letterSpacing: 1,
    padding: "5px 12px",
    border: "1px solid rgba(212,175,55,0.3)",
    borderRadius: 6,
    background: "rgba(212,175,55,0.05)",
    color: colors.gold,
    cursor: "pointer",
    transition: "all 0.2s ease",
  },
  disconnectBtn: {
    fontFamily: "'Space Mono', monospace",
    fontSize: 10,
    padding: "5px 10px",
    border: `1px solid ${colors.error}4D`,
    borderRadius: 6,
    background: `${colors.error}0D`,
    color: colors.error,
    cursor: "pointer",
    transition: "all 0.2s ease",
  },
  dangerBtn: {
    fontFamily: typography.fontMono,
    fontSize: 11,
    padding: "8px 16px",
    border: `1px solid ${colors.error}4D`,
    borderRadius: 8,
    background: `${colors.error}0D`,
    color: colors.error,
    cursor: "pointer",
    marginTop: 12,
    transition: "all 0.2s ease",
  },
  legalBtn: {
    fontFamily: "'Space Mono', monospace",
    fontSize: 10,
    padding: "4px 10px",
    background: "rgba(255,255,255,0.03)",
    border: "1px solid rgba(255,255,255,0.06)",
    borderRadius: 6,
    color: colors.muted,
    cursor: "pointer",
    transition: "all 0.2s ease",
  },
  saveRow: { marginTop: 20, textAlign: "right" },
  saveBtn: {
    fontFamily: "'Montserrat', sans-serif",
    fontSize: 13,
    fontWeight: 600,
    letterSpacing: 2,
    padding: "10px 24px",
    border: "none",
    borderRadius: 10,
    cursor: "pointer",
    background: `linear-gradient(180deg, ${colors.gold}, ${colors.goldDark})`,
    color: colors.dark,
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
    fontFamily: typography.fontDisplay,
    fontSize: 20,
    letterSpacing: 2,
    color: colors.gold,
    margin: "0 0 16px",
  },
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
  keyHintBanner: {
    fontSize: 11,
    color: "#aaa",
    lineHeight: 1.6,
    background: "rgba(212,175,55,0.05)",
    border: "1px solid rgba(212,175,55,0.15)",
    borderRadius: 8,
    padding: "10px 12px",
    marginBottom: 12,
  },
  fieldHint: {
    fontSize: 10,
    color: "#666",
    marginTop: 4,
    marginBottom: 4,
    paddingLeft: 2,
  },
  keyInfo: {
    background: "rgba(10,10,10,0.4)",
    border: "1px solid rgba(255,255,255,0.06)",
    borderRadius: 8,
    padding: 12,
    marginTop: 12,
  },
  keyInfoTitle: { fontSize: 11, color: "#888", marginBottom: 6 },
  keyPerm: { fontSize: 11, padding: "2px 0", display: "flex", gap: 6, alignItems: "center" },
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
  .settings-page {
    padding: 0 !important;
  }
  /* Accessing sub-styles via CSS since they are inline-first */
  [class*="capitalGrid"] {
    grid-template-columns: 1fr !important;
  }
}
@media (max-width: 280px) {
  .settings-page section {
    padding: 12px 10px !important;
    border-radius: 12px !important;
  }
  .settings-page h1 {
    font-size: 20px !important;
    letter-spacing: 2px !important;
  }
  .settings-page h2 {
    font-size: 12px !important;
  }
  .settings-page button, .settings-page select, .settings-page input {
    font-size: 10px !important;
  }
}
`;
