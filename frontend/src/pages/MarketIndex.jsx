import { useState, useEffect, useRef } from "react";
import { Link, useParams, useNavigate } from "react-router-dom";
import { PublicNav } from "../components/PublicNav.jsx";
import { PublicFooter } from "../components/PublicFooter.jsx";
import {
  ArrowRight, TrendingUp, TrendingDown, Shield, Zap, Cpu,
  BarChart2, Target, Settings as Bot, Diamond,
  Flame, Activity, Shuffle, Globe,
  Rocket, Cloud, Layers, Waves,
  RefreshCcw, MessageCircle, Crosshair, LineChart,
} from "lucide-react";
import { colors } from "../theme.js";

// ── Coin configuration ─────────────────────────────────────────────────────────
const COIN_DATA = {
  btc: {
    symbol: "BTC",
    name: "Bitcoin",
    slug: "bitcoin",
    label: "BTC/USD Intelligence",
    tagline: "The Original. The Benchmark. Primary Market Asset.",
    description:
      "Bitcoin is the world's first and most liquid cryptocurrency, representing over 50% of total crypto market cap. Our systems monitor BTC 24/7, analyzing global macro signals, on-chain flows, institutional order books, and hundreds of technical indicators to execute high-precision entries and exits.",
    strategies: [
      { name: "Turtle Traders", desc: "Momentum breakout — ride the trend until it ends.", Icon: BarChart2 },
      { name: "Paul Tudor Jones", desc: "Macro-driven risk management with tight stops.", Icon: Target },
      { name: "Renaissance Quant", desc: "Statistical arbitrage & mean reversion at scale.", Icon: Bot },
      { name: "Saylor HODL", desc: "Long-term conviction accumulation strategy.", Icon: Diamond },
    ],
    metrics: [
      { label: "MARKET DOMINANCE", value: "~52%" },
      { label: "AVG DAILY VOLUME", value: "$30B+" },
      { label: "LIQUIDITY TIER", value: "TIER 1" },
      { label: "DAILY SCANS", value: "480+" },
    ],
    color: "#F7931A",
    gradient: "linear-gradient(135deg, rgba(247,147,26,0.15), rgba(247,147,26,0.02))",
    borderGlow: "rgba(247,147,26,0.3)",
    cgId: "bitcoin",
  },
  eth: {
    symbol: "ETH",
    name: "Ethereum",
    slug: "ethereum",
    label: "ETH/USD Strategy",
    tagline: "Smart Contract Powerhouse — Systematic DeFi Edge.",
    description:
      "Ethereum is the backbone of decentralized finance and Web3. Its deep liquidity and rich on-chain data give our systems unique alpha through gas fee analysis, DeFi protocol flows, NFT volume signals, and staking yield dynamics — layers of data unavailable to traditional traders.",
    strategies: [
      { name: "Arthur Hayes Degen", desc: "High-conviction crypto-native momentum plays.", Icon: Flame },
      { name: "Donchian Channel", desc: "Systematic breakout entries on confirmed trends.", Icon: Activity },
      { name: "Bollinger Mean-Rev", desc: "Volatility squeeze entries with defined risk.", Icon: Shuffle },
      { name: "Druckenmiller Macro", desc: "Follow the big macro money into ETH.", Icon: Globe },
    ],
    metrics: [
      { label: "DEFI TVL TRACKED", value: "$50B+" },
      { label: "AVG DAILY VOLUME", value: "$15B+" },
      { label: "LIQUIDITY TIER", value: "TIER 1" },
      { label: "DAILY SCANS", value: "480+" },
    ],
    color: "#627EEA",
    gradient: "linear-gradient(135deg, rgba(98,126,234,0.15), rgba(98,126,234,0.02))",
    borderGlow: "rgba(98,126,234,0.3)",
    cgId: "ethereum",
  },
  sol: {
    symbol: "SOL",
    name: "Solana",
    slug: "solana",
    label: "SOL/USD Execution",
    tagline: "Speed-Native. High-Velocity Asset.",
    description:
      "Solana's sub-second finality and low fees make it the premier chain for high-frequency patterns. Our platform capitalizes on SOL's explosive momentum cycles, NFT ecosystem surges, and memecoin season correlations — capturing moves often too fast for human reaction.",
    strategies: [
      { name: "Momentum Scalp", desc: "Rapid-fire entries on confirmed volume spikes.", Icon: Rocket },
      { name: "Ichimoku Cloud", desc: "Multi-timeframe trend confirmation for SOL.", Icon: Cloud },
      { name: "Volatility Breakout", desc: "NR7 patterns on high-vol SOL sessions.", Icon: Layers },
      { name: "Crypto Swing Pro", desc: "Best-practice swing entries for high-beta assets.", Icon: Waves },
    ],
    metrics: [
      { label: "TPS (THROUGHPUT)", value: "65,000+" },
      { label: "AVG DAILY VOLUME", value: "$4B+" },
      { label: "LIQUIDITY TIER", value: "TIER 2+" },
      { label: "DAILY SCANS", value: "480+" },
    ],
    color: "#9945FF",
    gradient: "linear-gradient(135deg, rgba(153,69,255,0.15), rgba(153,69,255,0.02))",
    borderGlow: "rgba(153,69,255,0.3)",
    cgId: "solana",
  },
  altcoins: {
    symbol: "ALT",
    name: "Altcoin Universe",
    slug: "altcoins",
    label: "Altcoin Execution Engine",
    tagline: "Maximum Alpha. 500+ Coins. One Unified System.",
    description:
      "The Altcoin Execution Engine covers LINK, AVAX, UNI, AAVE, DOGE, PEPE, and 490+ more tokens simultaneously. The system rotates capital into the highest-probability setups across the entire market, detecting sector rotations (DeFi, L2, Gaming, memecoins) before they go mainstream.",
    strategies: [
      { name: "Sector Rotation", desc: "Rotate into DeFi, L2, gaming on signal.", Icon: RefreshCcw },
      { name: "Cobie CT Alpha", desc: "Crypto-Twitter sentiment-driven momentum.", Icon: MessageCircle },
      { name: "Ansem Degen Momentum", desc: "High-beta plays with defined risk gates.", Icon: Crosshair },
      { name: "Elliott Wave", desc: "Wave structure analysis on altcoin cycles.", Icon: LineChart },
    ],
    metrics: [
      { label: "COINS MONITORED", value: "500+" },
      { label: "SECTOR SIGNALS", value: "REAL-TIME" },
      { label: "AVG DAILY VOLUME", value: "$20B+" },
      { label: "DAILY SCANS", value: "2,400+" },
    ],
    color: "#D4AF37",
    gradient: "linear-gradient(135deg, rgba(212,175,55,0.15), rgba(212,175,55,0.02))",
    borderGlow: "rgba(212,175,55,0.3)",
    cgId: "bitcoin", // fallback for price display
  },
};

// ── Live price widget ──────────────────────────────────────────────────────────
const BACKEND_BASE = import.meta.env.VITE_BACKEND_URL
  || (import.meta.env.DEV ? "http://localhost:8000" : "");

// Map coin symbol → CoinGecko id for fallback
const SYM_TO_CG = {
  BTC: "bitcoin", ETH: "ethereum", SOL: "solana",
  ALT: "bitcoin", // altcoins page uses BTC as a market proxy
};

function PriceWidget({ symbol, cgId, accentColor }) {
  const [price, setPrice] = useState(null);
  const [change, setChange] = useState(null);
  const [loading, setLoading] = useState(true);
  const [source, setSource] = useState("—");
  const [lastUpdate, setLastUpdate] = useState(null);
  const priceRef = useRef(null); // keep last good price so we never show "unavailable" after loading once

  useEffect(() => {
    let cancelled = false;

    async function fetchPrice() {
      const sym = symbol === "ALT" ? "BTC" : symbol; // ALT page uses BTC as reference

      // ── Source 1: backend /api/prices/multi (fast, real-time, same as terminal) ──
      try {
        const url = `/api/prices/multi?symbols=${sym}`;
        const r = await fetch(url, { signal: AbortSignal.timeout(4000) });
        if (r.ok) {
          const d = await r.json();
          const entry = d?.[sym];
          if (entry?.price && !cancelled) {
            const p = entry.price;
            const chg = entry.price_change_24h ?? entry.change24h ?? null;
            setPrice(p);
            if (chg !== null) setChange(chg);
            setSource("LIVE");
            setLastUpdate(new Date());
            priceRef.current = { price: p, change: chg };
            setLoading(false);
            return;
          }
        }
      } catch {
        // fall through to CoinGecko
      }

      // ── Source 2: CoinGecko fallback ──────────────────────────────────────────
      try {
        const id = SYM_TO_CG[symbol] || cgId;
        const r = await fetch(
          `https://api.coingecko.com/api/v3/simple/price?ids=${id}&vs_currencies=usd&include_24hr_change=true`,
          { signal: AbortSignal.timeout(6000) }
        );
        if (r.ok) {
          const d = await r.json();
          const v = d?.[id];
          if (v?.usd && !cancelled) {
            const p = v.usd;
            const chg = v.usd_24h_change ?? null;
            setPrice(p);
            if (chg !== null) setChange(chg);
            setSource("COINGECKO");
            setLastUpdate(new Date());
            priceRef.current = { price: p, change: chg };
          }
        }
      } catch {
        // both sources failed — keep whatever we had before
        if (priceRef.current && !cancelled) {
          setPrice(priceRef.current.price);
          setChange(priceRef.current.change);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    fetchPrice();
    const id = setInterval(fetchPrice, 10000); // refresh every 10s
    return () => { cancelled = true; clearInterval(id); };
  }, [symbol, cgId]);

  const isUp = (change ?? 0) >= 0;
  const fmt = (n) => {
    if (!n) return "—";
    if (n >= 1000) return n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    if (n >= 1) return n.toFixed(2);
    return n.toFixed(6);
  };

  const displaySym = symbol === "ALT" ? "BTC" : symbol;

  if (loading) {
    return (
      <div style={{ textAlign: "center", padding: "24px 0" }}>
        <div style={{ width: "140px", height: "42px", background: "rgba(255,255,255,0.04)", borderRadius: "8px", margin: "0 auto 10px", animation: "shimmer 1.5s infinite" }} />
        <div style={{ width: "90px", height: "16px", background: "rgba(255,255,255,0.04)", borderRadius: "4px", margin: "0 auto", animation: "shimmer 1.5s infinite" }} />
      </div>
    );
  }

  if (!price) {
    return (
      <div style={{ textAlign: "center", padding: "24px 0" }}>
        <div style={{ fontSize: "12px", color: "#555", marginBottom: "6px" }}>{displaySym} price loading...</div>
        <div style={{ fontSize: "10px", color: "#333", letterSpacing: "1px" }}>Check backend connection</div>
      </div>
    );
  }

  return (
    <div style={{ textAlign: "center", padding: "20px 0" }}>
      {/* Header badge */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: "7px", marginBottom: "10px" }}>
        <span style={{
          display: "inline-block", width: "7px", height: "7px", borderRadius: "50%",
          background: "#00E676", boxShadow: "0 0 8px #00E676",
          animation: "pulse-dot 2s ease-in-out infinite",
        }} />
        <span style={{ fontSize: "10px", color: accentColor, letterSpacing: "3px", fontWeight: "700" }}>
          {displaySym}/USD · LIVE
        </span>
      </div>

      {/* Price */}
      <div style={{
        fontFamily: "'Bebas Neue', 'Montserrat', sans-serif",
        fontSize: "clamp(32px, 5vw, 52px)", letterSpacing: "2px",
        color: isUp ? "#00E676" : "#FF1744", lineHeight: 1,
        textShadow: isUp ? "0 0 20px #00E67640" : "0 0 20px #FF174440",
      }}>
        ${fmt(price)}
      </div>

      {/* 24h change */}
      <div style={{ marginTop: "10px", fontSize: "13px", fontWeight: "700", color: isUp ? "#00E676" : "#FF1744", display: "flex", alignItems: "center", justifyContent: "center", gap: "5px" }}>
        {isUp ? <TrendingUp size={14} /> : <TrendingDown size={14} />}
        {isUp ? "+" : ""}{(change ?? 0).toFixed(2)}% (24h)
      </div>

      {/* Source + last updated */}
      <div style={{ fontSize: "9px", color: "#2a2a2a", marginTop: "8px", letterSpacing: "1px" }}>
        SOURCE: {source}
        {lastUpdate && <span> · {lastUpdate.toLocaleTimeString()}</span>}
      </div>

      {symbol === "ALT" && (
        <div style={{ fontSize: "9px", color: "#444", marginTop: "4px" }}>
          Showing BTC as market reference
        </div>
      )}
    </div>
  );
}


// ── Strategy card ─────────────────────────────────────────────────────────────
function StrategyCard({ strategy, accentColor }) {
  const [hovered, setHovered] = useState(false);
  const Icon = strategy.Icon;
  return (
    <div
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        background: hovered ? "rgba(14,14,14,0.70)" : "rgba(14,14,14,0.62)",
        border: `1px solid ${hovered ? accentColor + "44" : "rgba(255,255,255,0.04)"}`,
        borderRadius: "12px", padding: "20px",
        transition: "all 0.25s ease",
        transform: hovered ? "translateY(-2px)" : "none",
        cursor: "default",
      }}
    >
      <div style={{
        width: "40px", height: "40px", borderRadius: "10px",
        background: `${accentColor}18`,
        border: `1px solid ${accentColor}33`,
        display: "flex", alignItems: "center", justifyContent: "center",
        marginBottom: "14px", color: accentColor,
      }}>
        {Icon && <Icon size={20} strokeWidth={1.75} />}
      </div>
      <div style={{ fontFamily: "'Montserrat', sans-serif", fontWeight: "700", fontSize: "13px", color: accentColor, letterSpacing: "1px", marginBottom: "6px" }}>{strategy.name}</div>
      <div style={{ fontSize: "12px", color: "#888", lineHeight: "1.6" }}>{strategy.desc}</div>
    </div>
  );
}

// ── Metric card ───────────────────────────────────────────────────────────────
function MetricCard({ label, value, accentColor }) {
  return (
    <div style={{
      background: "rgba(14,14,14,0.65)", border: "1px solid rgba(255,255,255,0.06)",
      borderRadius: "12px", padding: "20px", textAlign: "center",
      boxShadow: "inset 0 1px 3px rgba(0,0,0,0.3), 0 1px 0 rgba(255,255,255,0.03)",
    }}>
      <div style={{ fontSize: "22px", fontFamily: "'Bebas Neue', sans-serif", color: accentColor, letterSpacing: "1px", marginBottom: "6px" }}>{value}</div>
      <div style={{ fontSize: "9px", color: "#555", letterSpacing: "2px" }}>{label}</div>
    </div>
  );
}

// ── Main page ──────────────────────────────────────────────────────────────────
export default function MarketIndex() {
  const { coin } = useParams(); // "btc" | "eth" | "sol" | "altcoins"
  const navigate = useNavigate();
  const data = COIN_DATA[coin?.toLowerCase()];

  useEffect(() => {
    if (!data) { navigate("/", { replace: true }); return; }
    document.title = `${data.label} — Advanced Crypto Trading | DoYou.trade`;
    const meta = document.querySelector('meta[name="description"]');
    if (meta) meta.setAttribute("content", `${data.tagline} Automate your ${data.name} trading with professional-grade algorithmic strategies on DoYou.trade. High-precision execution for ${data.symbol}.`);
  }, [data, navigate]);

  if (!data) return null;

  return (
    <div style={{ minHeight: "100vh", background: "#050505", color: "#D4D4D4" }}>

      <PublicNav />

      {/* ── Coin tabs ── */}
      <div style={{ display: "flex", gap: "0", borderBottom: "1px solid rgba(255,255,255,0.04)", overflowX: "auto" }}>
        {Object.entries(COIN_DATA).map(([key, c]) => (
          <Link
            key={key}
            to={`/market/${key}`}
            style={{
              padding: "12px 20px", fontSize: "11px", fontWeight: "700", letterSpacing: "1.5px",
              color: coin?.toLowerCase() === key ? c.color : "#444",
              borderBottom: coin?.toLowerCase() === key ? `2px solid ${c.color}` : "2px solid transparent",
              background: coin?.toLowerCase() === key ? `${c.color}08` : "transparent",
              textDecoration: "none", whiteSpace: "nowrap", transition: "all 0.2s",
            }}
          >
            {c.symbol}
          </Link>
        ))}
      </div>

      <div style={{ maxWidth: "1100px", margin: "0 auto", padding: "0 24px 120px" }}>

        {/* ── Hero ── */}
        <div style={{
          padding: "60px 0 40px",
          display: "grid", gridTemplateColumns: "1fr auto", gap: "40px", alignItems: "start",
        }} className="market-hero-grid">
          <div>
            <div style={{
              display: "inline-flex", alignItems: "center", gap: "8px",
              fontSize: "10px", fontWeight: "700", letterSpacing: "2px",
              color: data.color, border: `1px solid ${data.color}44`,
              borderRadius: "100px", padding: "4px 14px", marginBottom: "20px",
              background: `${data.color}0D`,
            }}>
              <span style={{ width: "6px", height: "6px", borderRadius: "50%", background: data.color, display: "inline-block", boxShadow: `0 0 8px ${data.color}` }} />
              SYSTEMS ACTIVE · LIVE MONITORING
            </div>
            <h1 style={{
              fontFamily: "'Bebas Neue', sans-serif", fontSize: "clamp(36px, 6vw, 64px)",
              color: "#fff", letterSpacing: "4px", lineHeight: 1.1, marginBottom: "16px",
            }}>
              {data.label.toUpperCase()}
            </h1>
            <p style={{ fontSize: "14px", color: data.color, fontWeight: "700", letterSpacing: "1px", marginBottom: "16px" }}>
              {data.tagline}
            </p>
            <p style={{ fontSize: "14px", color: "#777", lineHeight: "1.8", maxWidth: "580px", marginBottom: "32px" }}>
              {data.description}
            </p>
            <div style={{ display: "flex", gap: "12px", flexWrap: "wrap" }}>
              <Link to="/signup" style={{
                fontFamily: "'Montserrat', sans-serif", fontWeight: "800", fontSize: "12px",
                letterSpacing: "2px", padding: "14px 28px",
                background: `linear-gradient(180deg, ${colors.gold}, ${colors.goldDark})`,
                color: "#0A0A0A", borderRadius: "8px", textDecoration: "none",
                display: "inline-flex", alignItems: "center", gap: "8px",
                transition: "transform 0.2s",
              }}>
                TRADE {data.symbol} WITH PRECISION <ArrowRight size={14} />
              </Link>
              <Link to="/login" style={{
                fontFamily: "'Montserrat', sans-serif", fontWeight: "700", fontSize: "12px",
                letterSpacing: "2px", padding: "14px 28px",
                background: "rgba(14,14,14,0.62)", color: "#888",
                border: "1px solid rgba(255,255,255,0.06)", borderRadius: "8px",
                textDecoration: "none",
              }}>
                SIGN IN
              </Link>
            </div>
          </div>

          {/* price widget */}
          <div style={{
            background: data.gradient,
            border: `1px solid ${data.borderGlow}`,
            borderRadius: "20px", padding: "24px 32px", minWidth: "240px",
            boxShadow: `0 0 60px ${data.borderGlow}40`,
          }}>
            <PriceWidget cgId={data.cgId} symbol={data.symbol} accentColor={data.color} />
          </div>
        </div>

        {/* ── Metrics ── */}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: "16px", marginBottom: "60px" }}>
          {data.metrics.map((m) => (
            <MetricCard key={m.label} label={m.label} value={m.value} accentColor={data.color} />
          ))}
        </div>

        {/* ── Systematic Strategies ── */}
        <div style={{ marginBottom: "60px" }}>
          <div style={{ marginBottom: "24px" }}>
            <h2 style={{ fontFamily: "'Montserrat', sans-serif", fontSize: "22px", fontWeight: "800", color: "#ccc", letterSpacing: "2px", marginBottom: "8px" }}>
              STRATEGIES FOR {data.symbol}
            </h2>
            <p style={{ fontSize: "12px", color: "#555" }}>
              The system selects from 100+ legendary trader presets — here are the top approaches for {data.name}.
            </p>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: "16px" }}>
            {data.strategies.map((s) => (
              <StrategyCard key={s.name} strategy={s} accentColor={data.color} />
            ))}
          </div>
        </div>

        {/* ── How it works ── */}
        <div style={{
          background: "rgba(14, 14, 14, 0.62)", border: "1px solid rgba(255,255,255,0.04)",
          borderRadius: "20px", padding: "40px", marginBottom: "60px",
          backdropFilter: "blur(24px) saturate(1.5)", WebkitBackdropFilter: "blur(24px) saturate(1.5)",
          boxShadow: "0 14px 44px rgba(0,0,0,0.50), 0 2px 6px rgba(0,0,0,0.35), inset 0 1px 0 rgba(255,255,255,0.11), inset 1px 0 0 rgba(255,255,255,0.05), inset 0 -1px 0 rgba(0,0,0,0.18), inset -1px 0 0 rgba(0,0,0,0.08)",
        }}>
          <h2 style={{ fontFamily: "'Montserrat', sans-serif", fontSize: "18px", fontWeight: "800", color: data.color, letterSpacing: "2px", marginBottom: "32px" }}>
            HOW THE SYSTEM TRADES {data.symbol}
          </h2>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: "32px" }}>
            {[
              { icon: <Zap size={20} />, title: "SCAN", desc: `480+ data points per scan — price action, indicators, volume, market sentiment.` },
              { icon: <Cpu size={20} />, title: "ANALYZE", desc: `The system evaluates confidence score, risk/reward, and regime fit before every trade.` },
              { icon: <Shield size={20} />, title: "EXECUTE", desc: `Trade signals fire in milliseconds with pre-defined stop-loss and take-profit levels.` },
            ].map((step) => (
              <div key={step.title} style={{ display: "flex", gap: "16px", alignItems: "flex-start" }}>
                <div style={{ color: data.color, flexShrink: 0, marginTop: "2px" }}>{step.icon}</div>
                <div>
                  <div style={{ fontFamily: "'Montserrat', sans-serif", fontWeight: "800", fontSize: "12px", color: "#ccc", letterSpacing: "2px", marginBottom: "6px" }}>{step.title}</div>
                  <div style={{ fontSize: "12px", color: "#666", lineHeight: "1.7" }}>{step.desc}</div>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* ── CTA ── */}
        <div style={{
          textAlign: "center", padding: "60px 20px",
          background: `linear-gradient(135deg, ${data.color}08, rgba(0,0,0,0.4))`,
          border: `1px solid ${data.color}22`, borderRadius: "24px",
          backdropFilter: "blur(24px) saturate(1.5)", WebkitBackdropFilter: "blur(24px) saturate(1.5)",
          boxShadow: "0 14px 44px rgba(0,0,0,0.50), 0 2px 6px rgba(0,0,0,0.35), inset 0 1px 0 rgba(255,255,255,0.11), inset 1px 0 0 rgba(255,255,255,0.05), inset 0 -1px 0 rgba(0,0,0,0.18), inset -1px 0 0 rgba(0,0,0,0.08)",
        }}>
          <div style={{ fontSize: "10px", color: data.color, letterSpacing: "3px", marginBottom: "16px" }}>JOIN THE COMMUNITY</div>
          <h2 style={{ fontFamily: "'Bebas Neue', sans-serif", fontSize: "clamp(28px, 4vw, 48px)", letterSpacing: "4px", color: "#fff", marginBottom: "16px" }}>
            START TRADING {data.symbol}
          </h2>
          <p style={{ fontSize: "13px", color: "#666", maxWidth: "480px", margin: "0 auto 32px", lineHeight: "1.8" }}>
            Non-custodial. Your capital stays on your exchange. Set up takes under 5 minutes.
          </p>
          <Link to="/signup" style={{
            fontFamily: "'Montserrat', sans-serif", fontWeight: "800", fontSize: "13px",
            letterSpacing: "2px", padding: "16px 40px",
            background: `linear-gradient(180deg, ${colors.gold}, ${colors.goldDark})`,
            color: "#0A0A0A", borderRadius: "10px", textDecoration: "none",
            display: "inline-flex", alignItems: "center", gap: "10px",
          }}>
            CREATE FREE ACCOUNT <ArrowRight size={16} />
          </Link>
        </div>
      </div>

      <PublicFooter />

      <style>{`
        @keyframes shimmer {
          0% { opacity: 0.4; }
          50% { opacity: 0.7; }
          100% { opacity: 0.4; }
        }
        @keyframes pulse-dot {
          0%, 100% { opacity: 1; box-shadow: 0 0 6px #00E676; }
          50% { opacity: 0.5; box-shadow: 0 0 12px #00E676; }
        }
        @media (max-width: 640px) {
          .market-hero-grid {
            grid-template-columns: 1fr !important;
          }
        }
      `}</style>
    </div>
  );
}
