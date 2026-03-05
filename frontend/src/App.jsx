import { useState, useEffect, useLayoutEffect, useRef, useCallback, useMemo, Component } from "react";
import confetti from "canvas-confetti";
import { useAuth } from "./contexts/AuthContext.jsx";
import AnimatedNumber from "./AnimatedNumber.jsx";
import FetchingPrice from "./FetchingPrice.jsx";
import { staggerIn } from "./animations.js";
import { useAuthHeaders, useAuthQueryParam } from "./hooks/useAuthHeaders.js";
import { colors } from "./theme.js";
import { TradeQuote } from "./components/TradeQuote.jsx";
import { TickerTape, FALLBACK_SYMBOL_TO_COINGECKO } from "./components/TickerTape.jsx";
import { AnalyticsSection } from "./components/AnalyticsSection.jsx";
import { TradeHistoryOverlay } from "./components/TradeHistoryOverlay.jsx";
import { TradeDetailModal } from "./components/TradeDetailModal.jsx";
import { PositionsPanel } from "./components/PositionsPanel.jsx";
import { ControlPanel } from "./components/ControlPanel.jsx";
import { ChartSection } from "./components/ChartSection.jsx";
import { ClaudeBrainPanel, MarketRegimePanel, AgentKitPanel, IndicatorsPanel, RiskMonitorPanel, RecentTradesPanel, ActivityLogPanel } from "./components/BottomPanels.jsx";

// ─── Error Boundary ────────────────────────────────────────────────────────────
class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }
  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }
  render() {
    if (this.state.hasError) {
      return (
        <div style={{ fontFamily:"'Space Mono',monospace", background:"#0A0A0A", color:"#D4D4D4", minHeight:"100vh", display:"flex", alignItems:"center", justifyContent:"center", flexDirection:"column", gap:"16px", padding:"20px", textAlign:"center" }}>
          <div style={{ fontSize:"48px" }}>🥊</div>
          <div style={{ fontFamily:"'Bebas Neue',sans-serif", fontSize:"28px", fontWeight:"400", color:colors.error, letterSpacing:"4px" }}>DOWN FOR THE COUNT</div>
          <div style={{ fontSize:"12px", color:colors.muted, maxWidth:"500px", lineHeight:"1.8" }}>
            {this.state.error?.message || "An unexpected error occurred."}
          </div>
          <button
            onClick={() => { this.setState({ hasError: false, error: null }); window.location.reload(); }}
            style={{ fontFamily:"'Oswald',sans-serif", fontSize:"12px", fontWeight:"600", letterSpacing:"2px", padding:"10px 24px", border:"none", borderRadius:"3px", cursor:"pointer", background:`linear-gradient(180deg,${colors.gold},${colors.goldDark})`, color:colors.dark }}
          >
            GET BACK UP
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

// ─── Unique ID generator for logs ─────────────────────────────────────────────
let _logSeq = 0;
function logId() { return `log_${Date.now()}_${++_logSeq}`; }

// Dev-only shortcut; production uses Supabase JWT (VITE_BOT_API_SECRET is never bundled in prod builds)
const API_SECRET = import.meta.env.DEV ? (import.meta.env.VITE_BOT_API_SECRET || "") : "";

// Direct backend connection by default (no proxy). More reliable for WebSocket + API.
const BACKEND_BASE = import.meta.env.VITE_BACKEND_URL
  || (import.meta.env.DEV ? "http://localhost:8000" : "");

function getBackendWsUrl(accessToken) {
  // Prefer JWT when logged in so backend can resolve per-user keys (dev vs user_exchanges)
  const auth = accessToken
    ? `?token=${encodeURIComponent(accessToken)}`
    : API_SECRET
      ? `?secret=${encodeURIComponent(API_SECRET)}`
      : "";
  if (import.meta.env.VITE_WS_URL) return import.meta.env.VITE_WS_URL + auth;
  if (BACKEND_BASE) {
    try {
      const u = new URL(BACKEND_BASE.replace(/\/$/, ""));
      const proto = u.protocol === "https:" ? "wss:" : "ws:";
      return `${proto}//${u.host}/ws` + auth;
    } catch {}
  }
  return (window.location.protocol === "https:" ? "wss:" : "ws:") + "//" + window.location.host + "/ws" + auth;
}
const DEFAULT_ROUND_TRIP_FEE = 0.012;  // fallback: 0.6% taker × 2 sides
const DEFAULT_COINS = ["BTC","ETH","SOL","DOGE","LINK","AVAX","UNI","AAVE"];

const PRESETS_FALLBACK = [
  { id: "default", name: "Default (Balanced)", trader: "Bot default", category: "General" },
  { id: "turtle", name: "Turtle Traders", trader: "Richard Dennis", category: "Trend Following" },
  { id: "seykota", name: "Ed Seykota", trader: "Ed Seykota", category: "Trend Following" },
  { id: "trend_dunn", name: "Dunn Capital Trend", trader: "Bill Dunn", category: "Trend Following" },
  { id: "trend_henry", name: "John W. Henry", trader: "John W. Henry", category: "Trend Following" },
  { id: "trend_harding", name: "Winton Trend", trader: "David Harding", category: "Trend Following" },
  { id: "trend_abraham", name: "Abraham Trading", trader: "Salem Abraham", category: "Trend Following" },
  { id: "trend_millburn", name: "Millburn Ridgefield", trader: "Millburn Ridgefield", category: "Trend Following" },
  { id: "donchian", name: "Donchian Channel", trader: "Richard Donchian", category: "Trend Following" },
  { id: "soros", name: "Soros Reflexivity", trader: "George Soros", category: "Macro" },
  { id: "ptj", name: "Paul Tudor Jones", trader: "Paul Tudor Jones", category: "Macro" },
  { id: "druckenmiller", name: "Druckenmiller Macro", trader: "Stanley Druckenmiller", category: "Macro" },
  { id: "kovner", name: "Kovner Conservative", trader: "Bruce Kovner", category: "Macro" },
  { id: "bacon", name: "Louis Bacon Macro", trader: "Louis Bacon", category: "Macro" },
  { id: "dalio", name: "Dalio All-Weather", trader: "Ray Dalio", category: "Macro" },
  { id: "robertson", name: "Julian Robertson", trader: "Julian Robertson", category: "Macro" },
  { id: "steinhardt", name: "Michael Steinhardt", trader: "Michael Steinhardt", category: "Macro" },
  { id: "tudor_bvi", name: "Tudor BVI Macro", trader: "Tudor Investment Corp", category: "Macro" },
  { id: "gross", name: "Bill Gross Bond King", trader: "Bill Gross", category: "Macro" },
  { id: "gundlach", name: "Gundlach DoubleLine", trader: "Jeffrey Gundlach", category: "Macro" },
  { id: "livermore", name: "Livermore Pivots", trader: "Jesse Livermore", category: "Stock Legends" },
  { id: "minervini", name: "Minervini Momentum", trader: "Mark Minervini", category: "Stock Legends" },
  { id: "oneil", name: "William O'Neil CANSLIM", trader: "William O'Neil", category: "Stock Legends" },
  { id: "darvas", name: "Nicolas Darvas Box", trader: "Nicolas Darvas", category: "Stock Legends" },
  { id: "zanger", name: "Dan Zanger Breakout", trader: "Dan Zanger", category: "Stock Legends" },
  { id: "weinstein", name: "Weinstein Stage", trader: "Stan Weinstein", category: "Stock Legends" },
  { id: "lefevre", name: "Reminiscences Classic", trader: "Edwin Lefèvre / Livermore", category: "Stock Legends" },
  { id: "simons", name: "Renaissance Quant", trader: "Jim Simons", category: "Quantitative" },
  { id: "shannon", name: "Shannon Rebalance", trader: "Claude Shannon", category: "Quantitative" },
  { id: "thorp", name: "Ed Thorp Kelly", trader: "Ed Thorp", category: "Quantitative" },
  { id: "aqr", name: "AQR Factor", trader: "Cliff Asness / AQR", category: "Quantitative" },
  { id: "two_sigma", name: "Two Sigma Systematic", trader: "David Siegel / John Overdeck", category: "Quantitative" },
  { id: "de_shaw", name: "D.E. Shaw Quant", trader: "David Shaw", category: "Quantitative" },
  { id: "citadel", name: "Citadel Multi-Strat", trader: "Ken Griffin", category: "Quantitative" },
  { id: "man_ahl", name: "Man AHL Systematic", trader: "Man Group / AHL", category: "Quantitative" },
  { id: "blackbox", name: "Black Box Quant", trader: "Quantitative firms", category: "Quantitative" },
  { id: "buffett", name: "Buffett Value", trader: "Warren Buffett", category: "Value / Contrarian" },
  { id: "icahn", name: "Carl Icahn Activist", trader: "Carl Icahn", category: "Value / Contrarian" },
  { id: "klarman", name: "Seth Klarman Value", trader: "Seth Klarman", category: "Value / Contrarian" },
  { id: "marks", name: "Howard Marks Cycles", trader: "Howard Marks", category: "Value / Contrarian" },
  { id: "templeton", name: "Templeton Contrarian", trader: "John Templeton", category: "Value / Contrarian" },
  { id: "neff", name: "John Neff Low P/E", trader: "John Neff", category: "Value / Contrarian" },
  { id: "burry", name: "Michael Burry Deep Value", trader: "Michael Burry", category: "Value / Contrarian" },
  { id: "driehaus", name: "Driehaus Momentum", trader: "Richard Driehaus", category: "Momentum / Growth" },
  { id: "lynch", name: "Peter Lynch Growth", trader: "Peter Lynch", category: "Momentum / Growth" },
  { id: "ryan", name: "David Ryan CANSLIM", trader: "David Ryan", category: "Momentum / Growth" },
  { id: "wood", name: "Cathie Wood Innovation", trader: "Cathie Wood", category: "Momentum / Growth" },
  { id: "raschke", name: "Raschke Short-Term", trader: "Linda Raschke", category: "Short-Term / Swing" },
  { id: "williams_balanced", name: "Williams Balanced", trader: "Larry Williams", category: "Short-Term / Swing" },
  { id: "williams_swing", name: "Williams Swing", trader: "Larry Williams", category: "Short-Term / Swing" },
  { id: "douglas", name: "Mark Douglas Zone", trader: "Mark Douglas", category: "Short-Term / Swing" },
  { id: "elder", name: "Alexander Elder", trader: "Alexander Elder", category: "Short-Term / Swing" },
  { id: "schwartz", name: "Marty Schwartz Pit Bull", trader: "Martin Schwartz", category: "Short-Term / Swing" },
  { id: "jones_crt", name: "CRT Bond Arb", trader: "Paul Tudor Jones (CRT era)", category: "Short-Term / Swing" },
  { id: "taleb", name: "Taleb Barbell", trader: "Nassim Taleb", category: "Volatility / Tail Risk" },
  { id: "niederhoffer", name: "Niederhoffer Mean-Rev", trader: "Victor Niederhoffer", category: "Volatility / Tail Risk" },
  { id: "tail_risk", name: "Tail Risk Hunter", trader: "Universa / Spitznagel", category: "Volatility / Tail Risk" },
  { id: "vol_breakout", name: "Volatility Breakout", trader: "Toby Crabel / NR7", category: "Volatility / Tail Risk" },
  { id: "crypto_swing", name: "Crypto Swing Pro", trader: "Crypto best practices", category: "Crypto Native" },
  { id: "crypto_conservative", name: "Crypto Maximum Room", trader: "High-volatility best practices", category: "Crypto Native" },
  { id: "saylor", name: "Saylor HODL Conviction", trader: "Michael Saylor", category: "Crypto Native" },
  { id: "hayes", name: "Arthur Hayes Degen", trader: "Arthur Hayes", category: "Crypto Native" },
  { id: "su_zhu", name: "Su Zhu Supercycle", trader: "Su Zhu (pre-3AC)", category: "Crypto Native" },
  { id: "cobie", name: "Cobie CT Alpha", trader: "Cobie (Jordan Fish)", category: "Crypto Native" },
  { id: "pentoshi", name: "Pentoshi Swing", trader: "Pentoshi", category: "Crypto Native" },
  { id: "hsaka", name: "Hsaka Scalp-Swing", trader: "Hsaka", category: "Crypto Native" },
  { id: "ansem", name: "Ansem Degen Momentum", trader: "Ansem", category: "Crypto Native" },
  { id: "gainzy", name: "GCR Contrarian", trader: "GCR (Gigantic Rebirth)", category: "Crypto Native" },
  { id: "light", name: "Light Crypto Macro", trader: "Light (Crypto)", category: "Crypto Native" },
  { id: "mobius", name: "Mark Mobius EM", trader: "Mark Mobius", category: "Global / Emerging" },
  { id: "rogers", name: "Jim Rogers Commodities", trader: "Jim Rogers", category: "Global / Emerging" },
  { id: "rogers_jim", name: "Jim Rogers Adventure", trader: "Jim Rogers", category: "Global / Emerging" },
  { id: "paulson", name: "John Paulson Event", trader: "John Paulson", category: "Event-Driven" },
  { id: "tepper", name: "David Tepper Distressed", trader: "David Tepper", category: "Event-Driven" },
  { id: "einhorn", name: "David Einhorn Value", trader: "David Einhorn", category: "Event-Driven" },
  { id: "loeb", name: "Dan Loeb Activist", trader: "Daniel Loeb", category: "Event-Driven" },
  { id: "ackman", name: "Bill Ackman Conviction", trader: "Bill Ackman", category: "Event-Driven" },
  { id: "coleman", name: "Chase Coleman Tiger", trader: "Chase Coleman", category: "Tiger Cubs / Modern HF" },
  { id: "mandel", name: "Steve Mandel Lone Pine", trader: "Steve Mandel", category: "Tiger Cubs / Modern HF" },
  { id: "ainslie", name: "Lee Ainslie Maverick", trader: "Lee Ainslie", category: "Tiger Cubs / Modern HF" },
  { id: "marcus", name: "Michael Marcus", trader: "Michael Marcus", category: "Market Wizards Classic" },
  { id: "mean_rev_bollinger", name: "Bollinger Mean-Rev", trader: "John Bollinger", category: "Mean-Reversion" },
  { id: "mean_rev_connors", name: "Connors RSI Reversal", trader: "Larry Connors", category: "Mean-Reversion" },
  { id: "scalp_tight", name: "Scalper Tight", trader: "Professional scalpers", category: "Scalping" },
  { id: "scalp_momentum", name: "Momentum Scalp", trader: "Crypto scalpers", category: "Scalping" },
  { id: "market_maker", name: "Market Maker Spread", trader: "Market makers", category: "Scalping" },
  { id: "risk_parity", name: "Risk Parity", trader: "Bridgewater / Risk Parity", category: "Portfolio / Systematic" },
  { id: "grid_dca", name: "Grid DCA", trader: "Systematic DCA", category: "Portfolio / Systematic" },
  { id: "seasonal", name: "Seasonal Patterns", trader: "Seasonal traders", category: "Portfolio / Systematic" },
  { id: "sentiment", name: "Sentiment Extremes", trader: "Sentiment traders", category: "Portfolio / Systematic" },
  { id: "fib_trader", name: "Fibonacci Precision", trader: "Harmonic traders", category: "Technical Systems" },
  { id: "ichimoku", name: "Ichimoku Cloud", trader: "Goichi Hosoda", category: "Technical Systems" },
  { id: "wyckoff", name: "Wyckoff Method", trader: "Richard Wyckoff", category: "Technical Systems" },
  { id: "volume_profile", name: "Volume Profile", trader: "Market Profile traders", category: "Technical Systems" },
  { id: "elliott", name: "Elliott Wave", trader: "R.N. Elliott / Prechter", category: "Technical Systems" },
  { id: "gann", name: "W.D. Gann Geometric", trader: "W.D. Gann", category: "Technical Systems" },
  { id: "pnf", name: "Point & Figure", trader: "P&F chartists", category: "Technical Systems" },
  { id: "smc", name: "Smart Money Concepts", trader: "ICT / SMC traders", category: "Technical Systems" },
  { id: "gap_trader", name: "Gap & Go", trader: "Opening range traders", category: "Technical Systems" },
  { id: "vwap", name: "VWAP Institutional", trader: "Institutional traders", category: "Technical Systems" },
  { id: "pairs_trade", name: "Pairs Trading", trader: "Stat arb / relative value", category: "Technical Systems" },
];
const PRESETS_CATEGORIES_FALLBACK = [
  "General", "Trend Following", "Macro", "Stock Legends", "Quantitative",
  "Value / Contrarian", "Momentum / Growth", "Short-Term / Swing",
  "Volatility / Tail Risk", "Crypto Native", "Global / Emerging",
  "Event-Driven", "Tiger Cubs / Modern HF", "Market Wizards Classic",
  "Mean-Reversion", "Scalping", "Portfolio / Systematic", "Technical Systems",
];

function Dashboard() {
  const { user, profile, signOut, accessToken } = useAuth();
  const getAuthHeaders = useAuthHeaders();
  const getAuthQueryParam = useAuthQueryParam();

  // ── Connection ──────────────────────────────────────────────────────────────
  const [connected,   setConnected]   = useState(false);
  const [cbLive,      setCbLive]      = useState(false);
  const [krakenEnabled, setKrakenEnabled] = useState(false);
  const [hasClaude,   setHasClaude]   = useState(false);
  const [paperMode,   setPaperMode]   = useState(true);
  const [agentKit,    setAgentKit]    = useState({ agentkit_ready:false, wallet_address:null, network:null, error:null });
  const [wsRetrying,  setWsRetrying]  = useState(false);

  // ── Multi-coin ──────────────────────────────────────────────────────────────
  const [coins,       setCoins]       = useState({});
  const [activeCoins, setActiveCoins] = useState(DEFAULT_COINS);
  const [selectedCoin, setSelectedCoin] = useState("BTC");
  const selectedCoinRef = useRef("BTC");
  const [chartSymbol, setChartSymbol] = useState("BTC");  // What's shown on the main chart (can be any ticker/exchange)
  const [marketTickers, setMarketTickers] = useState([]);  // Exchange top tickers for ticker tape
  const [multiExchangePrices, setMultiExchangePrices] = useState({});

  // ── Market (derived from selected coin) ───────────────────────────────────
  const [price,       setPrice]       = useState(0);
  const [prevPrice,   setPrevPrice]   = useState(0);
  const [change24h,   setChange24h]   = useState(0);
  const [priceSource, setPriceSource] = useState("coinbase");  // "coinbase" | "coingecko" — chart matches only when coinbase
  const [history,     setHistory]     = useState([]);
  const [indic,       setIndic]       = useState({ ema9:null, ema21:null, rsi:50, atr:0, bb_upper:0, bb_middle:0, bb_lower:0, bb_width:0, vwap:null });
  const [regime,      setRegime]      = useState("ranging");
  const [fearGreed,   setFearGreed]   = useState({ value: 50, label: "Neutral" });
  const [candles,     setCandles]     = useState([]);

  // ── Account ─────────────────────────────────────────────────────────────────
  const [startBal,    setStartBal]    = useState(1000);
  const [targetBal,   setTargetBal]   = useState(5000);
  const [account,     setAccount]     = useState({ balance: 1000, daily_pnl: 0, total_pnl: 0 });

  // ── Trading ─────────────────────────────────────────────────────────────────
  const [position,    setPosition]    = useState(null);
  const [positions,   setPositions]   = useState([]);
  const [maxPositions, setMaxPositions] = useState(3);
  const [maxFuturesPositions, setMaxFuturesPositions] = useState(0);
  const [enableFutures, setEnableFutures] = useState(false);
  const [trades,      setTrades]      = useState([]);
  const [decision,    setDecision]    = useState(null);
  const [lastAiBlockReason, setLastAiBlockReason] = useState(null);
  const [thinking,    setThinking]    = useState(false);
  const [botOn,       setBotOn]       = useState(false);
  const [lastCall,    setLastCall]    = useState("--");
  const [countdown,   setCountdown]   = useState(180);
  const [priceAge,    setPriceAge]    = useState(0);

  // ── Claude model ───────────────────────────────────────────────────────────
  const [claudeModel, setClaudeModel] = useState("claude-opus-4-20250514");

  // ── Confirm dialogs ────────────────────────────────────────────────────────
  const [confirmAction, setConfirmAction] = useState(null);

  // ── Approval mode & pending trade ───────────────────────────────────────────
  const [pendingDecision, setPendingDecision] = useState(null);
  const [pendingExpiresAt, setPendingExpiresAt] = useState(0);
  const [requireTradeApproval, setRequireTradeApproval] = useState(false);
  const [directionBias, setDirectionBias] = useState("both");
  const [pendingCountdown, setPendingCountdown] = useState(0);

  // ── Toast (loss notification) ──────────────────────────────────────────────
  const [lossToast, setLossToast] = useState(null);

  // ── Trading preset (top 100 trader strategies) ────────────────────────────
  const [tradingPreset, setTradingPreset] = useState("turtle");
  const [presets, setPresets] = useState(PRESETS_FALLBACK);
  const [presetCategories, setPresetCategories] = useState(PRESETS_CATEGORIES_FALLBACK);

  // ── Profit goal (configurable target, progress bar) ────────────────────────
  const [profitGoal, setProfitGoal] = useState(() => {
    try { const v = localStorage.getItem("claudebot_profit_goal"); return v ? Math.max(0, +v) : 4000; } catch { return 4000; }
  });
  useEffect(() => { if (profitGoal > 0) try { localStorage.setItem("claudebot_profit_goal", String(profitGoal)); } catch {} }, [profitGoal]);
  const profitGoalSyncRef = useRef(false);
  useEffect(() => {
    if (!profitGoalSyncRef.current) { profitGoalSyncRef.current = true; return; }
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ cmd: "set_profit_goal", profit_goal: profitGoal }));
    }
  }, [profitGoal]);

  // ── Backend config (fetched on mount, hardcoded fallbacks) ─────────────────
  const [roundTripFee, setRoundTripFee] = useState(DEFAULT_ROUND_TRIP_FEE);
  const roundTripFeeRef = useRef(DEFAULT_ROUND_TRIP_FEE);
  roundTripFeeRef.current = roundTripFee;
  useEffect(() => {
    const base = window.location.origin;
    const url = `${base}/api/config${API_SECRET ? `?secret=${encodeURIComponent(API_SECRET)}` : ""}`;
    fetch(url).then(r => r.ok ? r.json() : null).then(cfg => {
      if (!cfg) return;
      if (cfg.round_trip_fee) setRoundTripFee(cfg.round_trip_fee);
      if (cfg.symbol_to_coingecko) Object.assign(FALLBACK_SYMBOL_TO_COINGECKO, cfg.symbol_to_coingecko);
    }).catch(() => {});
  }, []);

  // ── Logs ────────────────────────────────────────────────────────────────────
  const [logs, setLogs] = useState([{ id: logId(), msg: "Connecting to backend...", type: "info", ts: "--:--:--" }]);
  const log = useCallback((msg, type = "info") =>
    setLogs(prev => [{ id: logId(), msg, type, ts: new Date().toLocaleTimeString() }, ...prev].slice(0, 60)), []);

  // ── Refs (always current, no stale closures) ─────────────────────────────────
  const wsRef        = useRef(null);
  const priceRef     = useRef(price);
  const accountRef   = useRef(account);
  const posRef       = useRef(position);
  const positionsRef = useRef(positions);
  const indicRef     = useRef(indic);
  const regimeRef    = useRef(regime);
  const tradesRef    = useRef(trades);
  const fearGreedRef = useRef(fearGreed);
  const botTimerRef  = useRef(null);
  const priceAgeRef  = useRef(null);
  const lastResetRef = useRef("");
  const thinkingRef  = useRef(false);
  const lastGoalReachedRef = useRef(false);
  const profitGoalRef = useRef(profitGoal);
  const change24hRef = useRef(change24h);
  const priceTimestampRef = useRef(0);
  const logsContainerRef = useRef(null);
  const tradesContainerRef = useRef(null);
  const lastStaggeredLogsRef = useRef(0);
  const lastStaggeredTradesRef = useRef(0);

  priceRef.current         = price;
  accountRef.current       = account;
  posRef.current           = position;
  positionsRef.current     = positions;
  indicRef.current         = indic;
  regimeRef.current        = regime;
  tradesRef.current        = trades;
  fearGreedRef.current     = fearGreed;
  thinkingRef.current      = thinking;
  change24hRef.current     = change24h;
  selectedCoinRef.current  = selectedCoin;
  profitGoalRef.current    = profitGoal;

  // ── Send to backend ──────────────────────────────────────────────────────────
  const send = useCallback((cmd, extra) => {
    if (wsRef.current?.readyState === WebSocket.OPEN)
      wsRef.current.send(JSON.stringify({ cmd, ...extra }));
  }, []);

  // ── Backend WebSocket ────────────────────────────────────────────────────────
  useEffect(() => {
    let ws, retryTimer, pingTimer, connectTimeout, disposed = false;
    let retryDelay = 2000;
    const MAX_RETRY = 30000;
    let hadConnection = false;

    function connect() {
      if (disposed) return;
      if (ws && ws.readyState !== WebSocket.CLOSED && ws.readyState !== WebSocket.CLOSING) {
        try { ws.close(); } catch {}
      }
      setWsRetrying(true);
      ws = new WebSocket(getBackendWsUrl(accessToken));
      wsRef.current = ws;

      ws.onopen = () => {
        if (disposed) { ws.close(); return; }
        retryDelay = 2000;
        hadConnection = true;
        setConnected(true);
        setWsRetrying(false);
        try { ws.send(JSON.stringify({ cmd: "set_profit_goal", profit_goal: profitGoalRef.current })); } catch {}
        if (botTimerRef.current){ clearInterval(botTimerRef.current); botTimerRef.current = null; }
        if (priceAgeRef.current){ clearInterval(priceAgeRef.current); priceAgeRef.current = null; }
        priceAgeRef.current = setInterval(() => setPriceAge(p => p + 1), 1000);
        log("Backend connected — real-time data active", "success");
        if (pingTimer) clearInterval(pingTimer);
        pingTimer = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) {
            try { ws.send(JSON.stringify({ cmd: "ping" })); } catch {}
          }
        }, 25000);
      };

      ws.onmessage = (e) => {
        try {
          const m = JSON.parse(e.data);
          if (m.type === "pong") return;
          if (m.coins) {
            setCoins(prev => {
              const updated = { ...prev };
              for (const [sym, data] of Object.entries(m.coins)) {
                updated[sym] = { ...(prev[sym] || {}), ...data };
              }
              return updated;
            });
            // Sync header to selected coin's price + age whenever coins update
            const sel = selectedCoinRef.current;
            const cd = m.coins[sel];
            if (cd?.price != null) {
              setPrevPrice(priceRef.current);
              setPrice(cd.price);
              setPriceAge(cd.price_age_sec ?? 0);
              priceTimestampRef.current = Date.now();
              setPriceSource("coinbase");  // Backend uses Coinbase — matches TradingView
            }
            if (cd?.price_change24h != null) setChange24h(cd.price_change24h);
          }
          if (m.active_coins) setActiveCoins(m.active_coins);
          if (m.type === "full_state" && Array.isArray(m.market_tickers) && m.market_tickers.length > 0) {
            setMarketTickers(m.market_tickers.map((c) => ({
              sym: (c.sym || c.symbol || "").toUpperCase(),
              price: c.price ?? 0,
              chg24h: c.chg24h ?? null,
              image: c.image || null,
            })).filter((x) => x.sym));
          }

          const isBtcSelected = selectedCoinRef.current === "BTC";
          if (isBtcSelected) {
            if (m.price != null)            { setPrevPrice(priceRef.current); setPrice(m.price); setPriceAge(m.coins?.BTC?.price_age_sec ?? 0); priceTimestampRef.current = Date.now(); setPriceSource("coinbase"); }
            if (m.price_change24h != null)  setChange24h(m.price_change24h);
            if (m.history)                  setHistory(m.history);
            if (m.indicators)               setIndic(m.indicators);
            if (m.market_condition)         setRegime(m.market_condition);
            if (m.candles) {
              setCandles(prev => {
                if (m.type === "full_state") return m.candles;
                const merged = [...prev];
                for (const c of m.candles) {
                  const idx = merged.findIndex(x => x.time === c.time);
                  if (idx >= 0) merged[idx] = c;
                  else merged.push(c);
                }
                merged.sort((a, b) => a.time - b.time);
                return merged.slice(-300);
              });
            }
          }
          if (m.account) {
            setAccount(m.account);
            // Celebrate when hitting your configured profit goal
            const pnl = m.account.total_pnl;
            const goal = profitGoalRef.current || 0;
            if (goal > 0 && pnl >= goal && !lastGoalReachedRef.current) {
              lastGoalReachedRef.current = true;
              confetti({ particleCount: 150, spread: 100, origin: { y: 0.6 }, colors: [colors.gold, colors.goldDark, "#FFD700", colors.error] });
              setTimeout(() => confetti({ particleCount: 100, spread: 80, origin: { y: 0.5, x: 0.3 }, colors: ["#D4AF37", "#B8860B", "#FFD700"] }), 150);
              setTimeout(() => confetti({ particleCount: 100, spread: 80, origin: { y: 0.5, x: 0.7 }, colors: ["#D4AF37", "#B8860B", "#FFD700"] }), 300);
            }
            if (pnl < goal) lastGoalReachedRef.current = false;
          }
          if (m.open_position !== undefined) setPosition(m.open_position);
          if (m.open_positions !== undefined) setPositions(m.open_positions);
          if (m.max_positions != null)    setMaxPositions(m.max_positions);
          if (m.max_futures_positions != null) setMaxFuturesPositions(m.max_futures_positions);
          if (m.enable_futures != null)  setEnableFutures(m.enable_futures);
          if (m.trades) {
            setTrades(m.trades);
            if (m.type === "trade_update" && m.trades?.length > 0) {
              const latest = m.trades[0];
              const prevLatest = tradesRef.current[0];
              const isNewTrade = !prevLatest || latest.id !== prevLatest.id;
              if (isNewTrade && latest.win) {
                confetti({ particleCount: 100, spread: 100, origin: { y: 0.6 }, colors: [colors.gold, colors.goldDark, "#FFD700", colors.success] });
                setTimeout(() => confetti({ particleCount: 60, spread: 80, origin: { y: 0.5, x: 0.3 }, colors: [colors.gold, "#FFD700"] }), 120);
                setTimeout(() => confetti({ particleCount: 60, spread: 80, origin: { y: 0.5, x: 0.7 }, colors: [colors.gold, "#FFD700"] }), 240);
              } else if (isNewTrade && !latest.win) {
                const sym = latest.symbol || "Position";
                setLossToast({ msg: `${sym} closed — $${Math.abs(latest.pnl).toFixed(2)} loss` });
                setTimeout(() => setLossToast(null), 4000);
              }
            }
          }
          if (m.claude_decision)          setDecision(m.claude_decision);
          if (m.last_ai_block_reason !== undefined) setLastAiBlockReason(m.last_ai_block_reason);
          if (m.pending_decision !== undefined) setPendingDecision(m.pending_decision);
          if (m.pending_expires_at != null)    setPendingExpiresAt(m.pending_expires_at);
          if (m.require_trade_approval != null) setRequireTradeApproval(m.require_trade_approval);
          if (m.direction_bias)                 setDirectionBias(m.direction_bias);
          if (m.trading_preset)                 setTradingPreset(m.trading_preset);
          if (m.type === "preset_changed")       setTradingPreset(m.trading_preset);
          if (m.type === "pending_trade") {
            setPendingDecision(m.pending_decision ?? null);
            if (m.pending_expires_at != null) setPendingExpiresAt(m.pending_expires_at);
          }
          if (m.bot_running  != null)     setBotOn(m.bot_running);
          if (m.claude_thinking != null)  setThinking(m.claude_thinking);
          if (m.last_claude_call)         setLastCall(m.last_claude_call);
          if (m.countdown != null)        setCountdown(m.countdown);
          if (m.has_claude_key != null)   setHasClaude(m.has_claude_key);
          if (m.paper_trading  != null)   setPaperMode(m.paper_trading);
          if (m.coinbase_connected != null) setCbLive(m.coinbase_connected);
          if (m.kraken_enabled != null) setKrakenEnabled(m.kraken_enabled);
          if (m.fear_greed)               setFearGreed(m.fear_greed);
          if (m.agentkit)                 setAgentKit(m.agentkit);
          if (m.start_balance != null)    setStartBal(m.start_balance);
          if (m.target_balance != null)   setTargetBal(m.target_balance);
          if (m.profit_goal != null && m.profit_goal > 0) setProfitGoal(m.profit_goal);
          else if (m.profit_to_target != null && profitGoalRef.current === 0) setProfitGoal(m.profit_to_target);
          if (m.claude_model)             setClaudeModel(m.claude_model);
          if (m.logs)                     setLogs(m.logs.map((l, i) => ({ ...l, id: l.id || `srv_${i}` })));
          if (m.type === "wallet_status") setAgentKit(prev => ({ ...prev, ...m }));
          if (m.type === "log" && m.entry) setLogs(prev => [{ ...m.entry, id: logId() }, ...prev].slice(0, 60));
        } catch { /* ignore parse errors */ }
      };

      ws.onerror = () => {};
      ws.onclose = (ev) => {
        if (disposed) return;
        if (pingTimer) { clearInterval(pingTimer); pingTimer = null; }
        if (priceAgeRef.current) { clearInterval(priceAgeRef.current); priceAgeRef.current = null; }
        setConnected(false);
        setCbLive(false);
        setKrakenEnabled(false);
        setWsRetrying(true);
        if (hadConnection) {
          log("Backend disconnected — reconnecting...", "warning");
        } else {
          log("Backend offline — start backend.py for live trading.", "warning");
        }
        retryTimer = setTimeout(connect, retryDelay);
        retryDelay = Math.min(retryDelay * 1.5, MAX_RETRY);
      };
    }

    // Defer connect to avoid React Strict Mode double-mount: cleanup runs before deferred connect
    connectTimeout = setTimeout(() => {
      connectTimeout = null;
      if (!disposed) connect();
    }, 0);

    return () => {
      disposed = true;
      if (connectTimeout) clearTimeout(connectTimeout);
      clearTimeout(retryTimer);
      if (pingTimer) clearInterval(pingTimer);
      if (ws && ws.readyState !== WebSocket.CLOSED && ws.readyState !== WebSocket.CLOSING) {
        try { ws.close(); } catch {}
      }
      wsRef.current = null;
    };
  }, [log, accessToken]);

  // ── Periodic account sync (failsafe so balance/P&L always reflect backend) ───
  useEffect(() => {
    if (!connected) return;
    const apiBase = BACKEND_BASE;
    const url = apiBase ? `${apiBase.replace(/\/$/, "")}/account` : "/account";
    const sync = async () => {
      try {
        const ctrl = new AbortController();
        const to = setTimeout(() => ctrl.abort(), 5000);
        const r = await fetch(url, { headers: getAuthHeaders(), signal: ctrl.signal });
        clearTimeout(to);
        if (!r.ok) return;
        const d = await r.json();
        setAccount(a => ({
          ...a,
          balance:   d.balance ?? a.balance,
          daily_pnl: d.daily_pnl ?? a.daily_pnl,
          total_pnl: d.total_pnl ?? a.total_pnl,
        }));
        if (d.start_balance != null) setStartBal(d.start_balance);
        if (d.target_balance != null) setTargetBal(d.target_balance);
      } catch {}
    };
    sync(); // immediate sync on connect
    // 10k scale: 15s when idle (no positions), 10s when active — reduces aggregate REST load
    const intervalMs = positions?.length > 0 ? 10000 : 15000;
    const id = setInterval(sync, intervalMs);
    return () => clearInterval(id);
  }, [connected, getAuthHeaders, positions?.length]);

  // ── Price fetch: backend first (Coinbase), then direct CoinGecko when backend fails ─
  const CG_IDS = { BTC:"bitcoin", ETH:"ethereum", SOL:"solana", DOGE:"dogecoin", LINK:"chainlink", AVAX:"avalanche-2", UNI:"uniswap", AAVE:"aave", XRP:"ripple", ADA:"cardano" };
  const fetchCoinGeckoDirect = async (sel) => {
    const cgId = CG_IDS[sel] || "bitcoin";
    const r = await fetch(`https://api.coingecko.com/api/v3/simple/price?ids=${cgId}&vs_currencies=usd&include_24hr_change=true`);
    if (!r.ok) return false;
    const d = await r.json();
    const v = d[cgId];
    if (v?.usd > 0) {
      setPrevPrice(priceRef.current);
      setPrice(v.usd);
      setPriceAge(0);
      priceTimestampRef.current = Date.now();
      setChange24h(v.usd_24h_change ?? 0);
      setCoins(prev => ({ ...prev, [sel]: { price: v.usd, price_change24h: v.usd_24h_change ?? 0 } }));
      setPriceSource("coingecko");  // Backend down — doesn't match TradingView
      return true;
    }
    return false;
  };

  useEffect(() => {
    const apiBase = BACKEND_BASE;
    const base = apiBase ? apiBase.replace(/\/$/, "") : "";
    const tickersUrl = base ? `${base}/api/coinbase/tickers` : "/api/coinbase/tickers";
    const headers = {};
    if (API_SECRET) headers["x-bot-secret"] = API_SECRET;
    // When cbLive (Coinbase WS): 8s polling — WS provides sub-second; REST is backup only
    const PRICE_FALLBACK_MS = cbLive ? 8000 : 2000;
    const STALE_THRESHOLD_MS = 10000;  // Force refresh if no update in 10s (WS likely stalled)

    const fetchPrice = async () => {
      const sel = selectedCoinRef.current;
      try {
        const ctrl = new AbortController();
        const to = setTimeout(() => ctrl.abort(), 5000);
        const r = await fetch(`${tickersUrl}?symbols=${encodeURIComponent(activeCoins.join(","))}`, { headers, signal: ctrl.signal });
        clearTimeout(to);
        if (r.ok) {
          const d = await r.json();
          let coinData = d?.coins;
          if (!coinData?.BTC && d?.bitcoin?.usd) {
            coinData = { BTC: { price: d.bitcoin.usd, price_change24h: d.bitcoin.usd_24h_change || 0 } };
          }
          if (coinData && Object.keys(coinData).length > 0) {
            setCoins(prev => ({ ...prev, ...coinData }));
          }
          const cd = coinData?.[sel];
          if (cd?.price != null && cd.price > 0) {
            setPrevPrice(priceRef.current);
            setPrice(cd.price);
            setPriceAge(0);
            priceTimestampRef.current = Date.now();
            if (cd.price_change24h != null) setChange24h(cd.price_change24h);
            setPriceSource("coinbase");  // Backend uses Coinbase — matches TradingView
            return;
          }
        }
      } catch { /* backend unreachable */ }
      if (priceRef.current <= 0) await fetchCoinGeckoDirect(sel);
    };

    fetchPrice(); // immediate
    const pollId = setInterval(fetchPrice, PRICE_FALLBACK_MS);
    // Staleness check (only when connected): if WS stops pushing, trigger immediate refresh
    const staleId = connected ? setInterval(() => {
      if (priceTimestampRef.current <= 0) return;
      const age = Date.now() - priceTimestampRef.current;
      if (age > STALE_THRESHOLD_MS && priceRef.current > 0) {
        fetchPrice(); // Force refresh — WS likely stalled
      }
    }, 5000) : null;
    return () => {
      clearInterval(pollId);
      if (staleId) clearInterval(staleId);
    };
  }, [connected, activeCoins, cbLive]);

  // ── Coinbase WebSocket — real-time price stream matching TradingView ─────────
  useEffect(() => {
    let ws, disposed = false, reconnectTimer;
    const CB_WS = "wss://ws-feed.exchange.coinbase.com";
    const productId = `${selectedCoinRef.current}-USD`;

    function connect() {
      if (disposed) return;
      try { ws = new WebSocket(CB_WS); } catch { scheduleReconnect(); return; }

      ws.onopen = () => {
        if (disposed) { ws.close(); return; }
        ws.send(JSON.stringify({
          type: "subscribe",
          product_ids: [productId],
          channels: ["ticker"],
        }));
      };

      ws.onmessage = (evt) => {
        try {
          const m = JSON.parse(evt.data);
          if (m.type !== "ticker" || m.product_id !== `${selectedCoinRef.current}-USD`) return;
          const p = parseFloat(m.price);
          if (!p || p <= 0) return;
          setPrevPrice(priceRef.current);
          setPrice(p);
          setPriceAge(0);
          priceTimestampRef.current = Date.now();
          setPriceSource("coinbase");
          const open24 = parseFloat(m.open_24h);
          if (open24 > 0) setChange24h(((p - open24) / open24) * 100);
        } catch {}
      };

      ws.onclose = () => { if (!disposed) scheduleReconnect(); };
      ws.onerror = () => { try { ws.close(); } catch {} };
    }

    function scheduleReconnect() {
      if (disposed) return;
      reconnectTimer = setTimeout(connect, 3000);
    }

    connect();

    return () => {
      disposed = true;
      clearTimeout(reconnectTimer);
      if (ws && ws.readyState !== WebSocket.CLOSED && ws.readyState !== WebSocket.CLOSING) {
        try { ws.close(); } catch {}
      }
    };
  }, [selectedCoin]);

  // ── Market tickers for ticker tape — exchange top 50 by volume ───
  useEffect(() => {
    const base = (BACKEND_BASE || "").replace(/\/$/, "");
    const url = base ? `${base}/api/exchange/tickers` : "/api/exchange/tickers";
    async function fetchMarkets() {
      try {
        const ctrl = new AbortController();
        const to = setTimeout(() => ctrl.abort(), 15000);
        const r = await fetch(`${url}?limit=500`, { headers: getAuthHeaders(), signal: ctrl.signal });
        clearTimeout(to);
        if (!r.ok) return;
        const arr = await r.json();
        if (Array.isArray(arr) && arr.length > 0) {
          const mapped = arr.map((c) => ({
            sym: (c.sym || c.symbol || "").toUpperCase(),
            price: c.price ?? 0,
            chg24h: c.chg24h ?? null,
            image: c.image || null,
          })).filter((x) => x.sym);
          if (mapped.length > 0) {
            setMarketTickers(mapped);
          }
        }
      } catch { /* non-critical, ticker works with coins/activeCoins fallback */ }
    }
    fetchMarkets();
    const t = setInterval(fetchMarkets, 180000); // 10k scale: 180s (was 120s) — reduces aggregate load
    return () => clearInterval(t);
  }, [getAuthHeaders]);

  // ── Fear & Greed index ─────────────────────────────────────────────────────
  useEffect(() => {
    async function fetchFG() {
      try {
        const ctrl = new AbortController();
        const to = setTimeout(() => ctrl.abort(), 5000);
        const r = await fetch("/api/alternative/fng/", { signal: ctrl.signal });
        clearTimeout(to);
        const d = await r.json();
        setFearGreed({ value: +d.data[0].value, label: d.data[0].value_classification });
      } catch { /* non-critical */ }
    }
    fetchFG();
    const t = setInterval(fetchFG, 3600000);
    return () => clearInterval(t);
  }, []);

  // ── Pending trade countdown ─────────────────────────────────────────────────
  useEffect(() => {
    if (!pendingDecision || pendingExpiresAt <= 0) return;
    const update = () => setPendingCountdown(Math.max(0, Math.ceil(pendingExpiresAt - Date.now() / 1000)));
    update();
    const id = setInterval(update, 1000);
    return () => clearInterval(id);
  }, [pendingDecision, pendingExpiresAt]);

  // ── Fetch trading presets when connected ───────────────────────────────────
  useEffect(() => {
    if (!connected) return;
    const url = BACKEND_BASE ? `${BACKEND_BASE}/api/presets` : "/api/presets";
    fetch(url, { headers: getAuthHeaders() }).then(r => r.ok && r.json()).then(d => {
      if (d?.presets?.length) {
        setPresets(d.presets);
        setPresetCategories(d.categories || []);
      }
    }).catch(() => {});
  }, [connected, getAuthHeaders]);

  // ── Midnight P&L reset (display) ────────────────────────────────────────────
  useEffect(() => {
    const t = setInterval(() => {
      const now   = new Date();
      const today = now.toDateString();
      if (now.getHours() === 0 && now.getMinutes() === 0 && lastResetRef.current !== today) {
        lastResetRef.current = today;
        setAccount(a => ({ ...a, daily_pnl: 0 }));
        log("Daily P&L reset (midnight)", "info");
      }
    }, 60000);
    return () => clearInterval(t);
  }, [log]);

  const callClaude = useCallback(async () => {
    if (thinkingRef.current) return;
    setThinking(true);
    setLastCall(new Date().toLocaleTimeString());
    log("Claude analyzing live market data...", "claude");

    try {
      const backendBase = BACKEND_BASE || `${window.location.protocol}//${window.location.hostname}:8000`;
      const res = await fetch(`${backendBase}/ask_claude`, { method: "POST", headers: getAuthHeaders() });

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.error || `Backend returned ${res.status}`);
      }

      const dec = await res.json();
      setDecision(dec);
      log(`Claude: ${dec.action?.toUpperCase()} — ${dec.reasoning?.slice(0, 80) || ""}`, dec.action === "wait" ? "dim" : "claude");
    } catch (e) {
      if (e.message?.toLowerCase().includes("failed to fetch") || e.message?.toLowerCase().includes("networkerror")) {
        log("Backend offline — cannot reach Claude. Start python backend.py", "warning");
        setDecision({ reasoning: "Backend offline. Start backend.py for AI trading.", action: "wait", confidence: 0, market_condition: regimeRef.current });
      } else {
        log(`Claude error: ${e.message}`, "error");
      }
    } finally {
      setThinking(false);
    }
  }, [log, getAuthHeaders]);

  // ── Handlers ─────────────────────────────────────────────────────────────────
  const handleStart = () => {
    if (connected) { send("start_bot"); }
    else { log("Start backend.py first", "warning"); }
  };
  const handleStop = () => {
    if (connected) { send("stop_bot"); }
    else { log("Backend offline", "warning"); }
  };
  const handleAsk = () => {
    if (connected) send("ask_claude", { direct: true });
    else callClaude();  // callClaude will show "Backend offline" if unreachable
  };
  const handleModelChange = (model) => {
    setClaudeModel(model);
    if (connected) send("set_model", { model });
    log(`Model switched to ${model}`, "info");
  };
  const handlePresetChange = (presetId) => {
    setTradingPreset(presetId);
    if (connected) send("set_preset", { preset: presetId });
    const preset = presets.find(p => p.id === presetId);
    log(`Strategy: ${preset?.name || presetId}`, "info");
  };

  const handleApprovePending = () => {
    if (connected && pendingDecision) send("approve_pending");
    else log("No pending trade or backend offline", "warning");
  };
  const handleRejectPending = () => {
    if (connected && pendingDecision) send("reject_pending");
    else if (!connected) setPendingDecision(null);
    log("Pending trade rejected", "dim");
  };

  const handleClose = (posToClose) => {
    if (!positions.length && !connected) return;
    const sym = posToClose?.symbol || "ALL";
    const label = posToClose
      ? `Close ${posToClose.side?.toUpperCase()} ${posToClose.symbol} position? Unrealized P&L will be realized at current price.`
      : "Close ALL open positions?";
    setConfirmAction({ type: "close", label, pos: posToClose });
  };
  const handleReset = () => {
    setConfirmAction({ type: "reset", label: `Reset account to $${startBal}? All positions and local trade history will be cleared.` });
  };
  const confirmYes = () => {
    const act = confirmAction;
    setConfirmAction(null);
    if (!act) return;
    if (act.type === "close") {
      if (connected) {
        const extra = {};
        if (act.pos?.id) extra.pos_id = act.pos.id;
        else if (act.pos?.symbol) extra.symbol = act.pos.symbol;
        send("close_position", extra);
        return;
      }
      const closeTargets = act.pos ? [act.pos] : positionsRef.current;
      if (!closeTargets.length) return;
      let totalNet = 0;
      const newTrades = [];
      for (const pos of closeTargets) {
        const coinPrice = coins[pos.symbol]?.price || priceRef.current;
        const closeSz = pos.coin_size || pos.btc_size || 0;
        const pnl = pos.side==="buy" ? (coinPrice-pos.entry)*closeSz : (pos.entry-coinPrice)*closeSz;
        const net = +(pnl - pos.usd_size * roundTripFeeRef.current).toFixed(2);
        totalNet += net;
        newTrades.push({ id:Date.now()+Math.random(), symbol:pos.symbol, side:pos.side, entry:pos.entry, exit:coinPrice, pnl:net, reason:"MANUAL CLOSE", ts:new Date().toLocaleTimeString(), win:net>0 });
        setAccount(a => ({ balance:+(a.balance+pos.usd_size+net).toFixed(2), daily_pnl:+(a.daily_pnl+net).toFixed(2), total_pnl:+(a.total_pnl+net).toFixed(2) }));
      }
      setTrades(p => [...newTrades, ...p].slice(0,30));
      if (act.pos) {
        setPositions(prev => prev.filter(p => p.id !== act.pos.id));
      } else {
        setPositions([]);
      }
      setPosition(null);
      log(`MANUAL CLOSE | Net: ${totalNet>=0?"+":""}$${totalNet.toFixed(2)}`, totalNet>=0?"success":"warning");
    } else if (act.type === "reset") {
      if (connected) { send("reset_account"); return; }
      lastGoalReachedRef.current = false;
      setAccount({ balance:startBal, daily_pnl:0, total_pnl:0 });
      setPosition(null);
      setPositions([]);
      setTrades([]);
      setDecision(null);
      log(`Account reset to $${startBal}`, "warning");
    }
  };

  // ── Full Trade History (from database) ──────────────────────────────────────
  const [historyTrades,   setHistoryTrades]   = useState([]);
  const [historyTotal,    setHistoryTotal]    = useState(0);
  const [historyStats,    setHistoryStats]    = useState({ wins:0, losses:0, win_rate:0, total_pnl:0 });
  const [historyLoading,  setHistoryLoading]  = useState(false);
  const [historyPage,     setHistoryPage]     = useState(0);
  const [historyLimit]                        = useState(50);
  const [historyFilters,  setHistoryFilters]  = useState({ date_from:"", date_to:"", symbol:"", side:"", result:"", product_type:"" });
  const [showHistory,     setShowHistory]     = useState(false);

  // ── Trade Detail Modal (chart screenshots) ──────────────────────────────────
  const [tradeDetail,     setTradeDetail]     = useState(null);
  const [tradeDetailLoading, setTradeDetailLoading] = useState(false);

  const openTradeDetail = useCallback(async (tr) => {
    setTradeDetail({ trade: tr, screenshots: null, context: null, audit: null });
    setTradeDetailLoading(true);
    try {
      const backendBase = BACKEND_BASE || `${window.location.protocol}//${window.location.hostname}:8000`;
      const res = await fetch(`${backendBase}/api/trade/${tr.id}/context`, { headers: getAuthHeaders() });
      if (res.ok) {
        const data = await res.json();
        setTradeDetail(prev => ({ ...prev, ...data, trade: data.trade || tr }));
      }
    } catch (e) {
      log(`Failed to load trade detail: ${e.message}`, "dim");
    } finally {
      setTradeDetailLoading(false);
    }
  }, [log, getAuthHeaders]);

  const closeTradeDetail = useCallback(() => {
    setTradeDetail(null);
  }, []);

  const fetchHistory = useCallback(async (page = 0, filters = historyFilters) => {
    setHistoryLoading(true);
    try {
      const backendBase = BACKEND_BASE || `${window.location.protocol}//${window.location.hostname}:8000`;
      const params = new URLSearchParams();
      params.set("limit", historyLimit);
      params.set("offset", page * historyLimit);
      if (filters.date_from) params.set("date_from", filters.date_from);
      if (filters.date_to)   params.set("date_to", filters.date_to);
      if (filters.symbol)    params.set("symbol", filters.symbol);
      if (filters.side)      params.set("side", filters.side);
      if (filters.result)    params.set("result", filters.result);
      if (filters.product_type) params.set("product_type", filters.product_type);
      const res = await fetch(`${backendBase}/trades/history?${params}`, { headers: getAuthHeaders() });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setHistoryTrades(data.trades || []);
      setHistoryTotal(data.total || 0);
      setHistoryStats({ wins: data.wins||0, losses: data.losses||0, win_rate: data.win_rate||0, total_pnl: data.total_pnl||0 });
      setHistoryPage(page);
    } catch (e) {
      log(`Failed to load history: ${e.message}`, "error");
    } finally {
      setHistoryLoading(false);
    }
  }, [historyFilters, historyLimit, log, getAuthHeaders]);

  const applyHistoryFilter = (key, value) => {
    const next = { ...historyFilters, [key]: value };
    setHistoryFilters(next);
    fetchHistory(0, next);
  };

  const clearHistoryFilters = () => {
    const blank = { date_from:"", date_to:"", symbol:"", side:"", result:"", product_type:"" };
    setHistoryFilters(blank);
    fetchHistory(0, blank);
  };

  const tradeTypeBadge = (tr) => {
    const exBadge = tr.exchange === "kraken"
      ? <span className="tag" style={{ background:"#7b61ff18", color:"#7b61ff", fontSize:"9px", marginLeft:"3px" }}>KRAKEN</span>
      : tr.exchange === "coinbase"
      ? <span className="tag" style={{ background:"#0052ff18", color:"#4d8ffa", fontSize:"9px", marginLeft:"3px" }}>COINBASE</span>
      : null;
    if (tr.onchain) return <><span className="tag" style={{ background:"#D4AF3718", color:"#D4AF37", fontSize:"9px" }}>ON-CHAIN</span>{exBadge}</>;
    if (tr.product_type === "futures") return <><span className="tag" style={{ background:"#D4AF3718", color:"#D4AF37", fontSize:"9px" }}>FUTURES{tr.leverage ? ` ${tr.leverage}x` : ""}</span>{exBadge}</>;
    return <><span className="tag" style={{ background:"#2a2a2a", color:"#64748b", fontSize:"9px" }}>SPOT</span>{exBadge}</>;
  };

  // ── Export trades as CSV ───────────────────────────────────────────────────────
  const exportTrades = (tradeList) => {
    const list = tradeList || trades;
    if (list.length === 0) return;
    const typeLabel = (t) => t.onchain ? "ON-CHAIN" : (t.product_type === "futures" ? `FUTURES ${t.leverage || 1}x` : "SPOT");
    const header = "Date,Time,Symbol,Side,Type,Entry,Exit,PnL,Reason,Win\n";
    const rows = list.map(t =>
      `${t.created_at||""},${t.ts},${t.symbol||"BTC"},${t.side},${typeLabel(t)},${t.entry},${t.exit},${t.pnl},"${t.reason}",${t.win}`
    ).join("\n");
    const blob = new Blob([header + rows], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = `claudebot_trades_${new Date().toISOString().slice(0,10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
    log("Trade history exported as CSV", "info");
  };

  // ── Stagger-in animations for logs & trades (Anime.js) — only new items to avoid flash
  useLayoutEffect(() => {
    const container = logsContainerRef.current;
    if (!container) return;
    const prev = lastStaggeredLogsRef.current;
    const n = logs.length;
    if (n < prev) lastStaggeredLogsRef.current = 0;
    if (n === 0) return;
    const newCount = Math.min(Math.max(0, n - lastStaggeredLogsRef.current), 8);
    if (newCount > 0) {
      staggerIn(container, ".logrow", { start: 0, limit: newCount, delay: 40, duration: 140 });
      lastStaggeredLogsRef.current = n;
    } else if (lastStaggeredLogsRef.current === 0 && n > 0) {
      staggerIn(container, ".logrow", { limit: 8, delay: 35, duration: 140 });
      lastStaggeredLogsRef.current = n;
    }
  }, [logs]);
  useLayoutEffect(() => {
    const container = tradesContainerRef.current;
    if (!container) return;
    const prev = lastStaggeredTradesRef.current;
    const n = trades.length;
    if (n < prev) lastStaggeredTradesRef.current = 0;
    if (n === 0) return;
    const newCount = Math.min(Math.max(0, n - lastStaggeredTradesRef.current), 6);
    if (newCount > 0) {
      staggerIn(container, ".trow", { start: 0, limit: newCount, delay: 50, duration: 150 });
      lastStaggeredTradesRef.current = n;
    } else if (lastStaggeredTradesRef.current === 0 && n > 0) {
      staggerIn(container, ".trow", { limit: 8, delay: 45, duration: 150 });
      lastStaggeredTradesRef.current = n;
    }
  }, [trades]);

  // ── Coin switching: update view when selected coin changes or its data updates
  useEffect(() => {
    const cd = coins[selectedCoin];
    if (!cd) return;
    if (cd.price != null)           { setPrevPrice(priceRef.current); setPrice(cd.price); setPriceAge(cd.price_age_sec ?? 0); priceTimestampRef.current = Date.now(); }
    if (cd.price_change24h != null) setChange24h(cd.price_change24h);
    if (cd.history)                 setHistory(cd.history);
    if (cd.indicators)              setIndic(cd.indicators);
    if (cd.market_condition)        setRegime(cd.market_condition);
    if (cd.candles)                 setCandles(cd.candles);
  }, [selectedCoin, coins, connected]); // eslint-disable-line

  // ── Derived (memoized to avoid cascade re-renders) ──────────────────────────────
  const priceUp = useMemo(
    () => price >= prevPrice && prevPrice > 0,
    [price, prevPrice]
  );
  const winRate = useMemo(
    () => trades.length ? Math.round(trades.filter(t => t.win).length / trades.length * 100) : 0,
    [trades]
  );
  const totalUnrealized = useMemo(
    () => positions.reduce((sum, pos) => {
      const cp = coins[pos.symbol]?.price || price;
      const sz = pos.coin_size || pos.btc_size || 0;
      return sum + (pos.side === "buy" ? (cp - pos.entry) * sz : (pos.entry - cp) * sz);
    }, 0),
    [positions, coins, price]
  );
  const unrealized = useMemo(() => +totalUnrealized.toFixed(2), [totalUnrealized]);
  const isLiveMode = !paperMode;

  const priceFormat = useCallback((v) => {
    if (v < 10) return v.toFixed(4);
    if (v < 1000) return v.toFixed(2);
    return v.toLocaleString();
  }, []);

  return (
    <div className="app-root" style={{ fontFamily:"'Space Mono',monospace", background:"#0A0A0A", color:"#D4D4D4",  padding:"20px 24px 40px", fontSize:"12px" }}>
      <style>{`
        *{box-sizing:border-box;margin:0;padding:0;-webkit-tap-highlight-color:transparent}
        ::-webkit-scrollbar{width:3px;height:3px}::-webkit-scrollbar-track{background:transparent}::-webkit-scrollbar-thumb{background:rgba(212,175,55,0.2);border-radius:2px}
        *{scrollbar-width:thin;scrollbar-color:rgba(212,175,55,0.2) transparent}
        .card{background:rgba(17,17,17,0.55);backdrop-filter:blur(20px) saturate(1.4);-webkit-backdrop-filter:blur(20px) saturate(1.4);border:1px solid rgba(212,175,55,0.1);border-radius:16px;padding:16px;position:relative;box-shadow:0 8px 32px rgba(0,0,0,0.4),inset 0 1px 0 rgba(255,255,255,0.04);transition:border-color 0.3s ease,box-shadow 0.3s ease}
        .card:hover{border-color:rgba(212,175,55,0.2);box-shadow:0 12px 40px rgba(0,0,0,0.45),0 0 24px rgba(212,175,55,0.06),inset 0 1px 0 rgba(255,255,255,0.06)}
        .card::before,.card::after{content:'';position:absolute;width:16px;height:16px;pointer-events:none;opacity:0.6;transition:opacity 0.3s ease}
        .card:hover::before,.card:hover::after{opacity:1}
        .card::before{top:-1px;left:-1px;border-top:2px solid rgba(212,175,55,0.5);border-left:2px solid rgba(212,175,55,0.5);border-radius:16px 0 0 0}
        .card::after{bottom:-1px;right:-1px;border-bottom:2px solid rgba(212,175,55,0.5);border-right:2px solid rgba(212,175,55,0.5);border-radius:0 0 16px 0}
        .grid{display:grid;grid-template-columns:260px 1fr 260px;gap:14px}
        .grid-bottom{display:grid;grid-template-columns:300px 1fr 300px;gap:16px;margin-top:16px}
        .col{display:flex;flex-direction:column;gap:14px}
        @keyframes pulse{0%,100%{opacity:1}50%{opacity:.3}}
        @keyframes fadein{from{opacity:0;transform:translateY(-6px) scale(0.98)}to{opacity:1;transform:translateY(0) scale(1)}}
        @keyframes skeleton-shimmer{0%{background-position:200% 0}100%{background-position:-200% 0}}
        @keyframes punchImpact{0%{box-shadow:0 0 0 0 rgba(212,175,55,0.6)}50%{box-shadow:0 0 40px 10px rgba(212,175,55,0.3)}100%{box-shadow:0 0 0 0 transparent}}
        .pulse{animation:pulse 2s infinite}.blink{animation:pulse 0.7s infinite}.fadein{animation:fadein 0.35s cubic-bezier(0.4,0,0.2,1)}
        .btn{font-family:'Oswald',sans-serif;font-size:11px;font-weight:600;letter-spacing:2px;text-transform:uppercase;padding:8px 16px;border:none;border-radius:8px;cursor:pointer;transition:all 0.25s cubic-bezier(0.4,0,0.2,1);touch-action:manipulation;min-height:36px;position:relative;overflow:hidden}
        .btn:disabled{opacity:.4;cursor:not-allowed}
        .btn:focus-visible{outline:2px solid rgba(212,175,55,0.5);outline-offset:2px}
        .btn:active:not(:disabled){transform:scale(0.97)}
        .btn-g{background:linear-gradient(180deg,#D4AF37,#B8860B);color:#0A0A0A;font-weight:700;box-shadow:0 4px 16px rgba(212,175,55,0.15)}.btn-g:hover:not(:disabled){background:linear-gradient(180deg,#E5C04B,#D4AF37);transform:translateY(-1px);box-shadow:0 8px 24px rgba(212,175,55,0.3)}
        .btn-r{background:rgba(192,57,43,0.85);backdrop-filter:blur(8px);-webkit-backdrop-filter:blur(8px);color:#fff;box-shadow:0 4px 16px rgba(192,57,43,0.15)}.btn-r:hover:not(:disabled){background:rgba(231,76,60,0.9);box-shadow:0 8px 24px rgba(192,57,43,0.3)}
        .btn-p{background:rgba(212,175,55,0.05);backdrop-filter:blur(8px);-webkit-backdrop-filter:blur(8px);color:#D4AF37;border:1px solid rgba(212,175,55,0.2)}.btn-p:hover:not(:disabled){background:rgba(212,175,55,0.1);border-color:rgba(212,175,55,0.35);box-shadow:0 0 20px rgba(212,175,55,0.1)}
        .btn-d{background:rgba(255,255,255,0.03);backdrop-filter:blur(8px);-webkit-backdrop-filter:blur(8px);color:#5C5C5C;border:1px solid rgba(255,255,255,0.06);font-size:9px;padding:6px 12px;border-radius:6px}.btn-d:hover:not(:disabled){background:rgba(255,255,255,0.06);border-color:rgba(255,255,255,0.1)}
        .row{display:flex;justify-content:space-between;align-items:center;padding:6px 0;border-bottom:1px solid rgba(255,255,255,0.04)}
        .tag{display:inline-block;padding:3px 8px;border-radius:6px;font-size:9px;font-weight:700;letter-spacing:.5px;backdrop-filter:blur(4px);-webkit-backdrop-filter:blur(4px)}
        .logrow{padding:4px 0;border-bottom:1px solid rgba(255,255,255,0.03)}
        .trow{padding:6px 0;border-bottom:1px solid rgba(255,255,255,0.04);display:flex;justify-content:space-between;align-items:center}
        .dot{width:7px;height:7px;border-radius:50%;display:inline-block;flex-shrink:0;box-shadow:0 0 6px currentColor}
        .section-label{font-family:'Oswald',sans-serif;font-size:11px;font-weight:600;letter-spacing:3px;text-transform:uppercase;color:#D4AF37;border-left:3px solid rgba(212,175,55,0.6);padding-left:8px}
        .confirm-overlay{position:fixed;inset:0;background:rgba(0,0,0,0.6);backdrop-filter:blur(24px) saturate(1.5);-webkit-backdrop-filter:blur(24px) saturate(1.5);display:flex;align-items:center;justify-content:center;z-index:9999;animation:fadein 0.2s cubic-bezier(0.4,0,0.2,1);padding:env(safe-area-inset-top) env(safe-area-inset-right) env(safe-area-inset-bottom) env(safe-area-inset-left)}
        .confirm-box{background:rgba(17,17,17,0.72);backdrop-filter:blur(40px) saturate(1.6);-webkit-backdrop-filter:blur(40px) saturate(1.6);border:1px solid rgba(212,175,55,0.15);border-radius:20px;padding:28px 32px;width:calc(100% - 32px);max-width:400px;text-align:center;box-shadow:0 24px 64px rgba(0,0,0,0.5),0 0 0 1px rgba(255,255,255,0.04),inset 0 1px 0 rgba(255,255,255,0.06);box-sizing:border-box}
        select option,select optgroup{background:#111111;color:#D4D4D4;font-family:'Space Mono',monospace;font-size:10px}
        select optgroup{color:#5C5C5C;font-weight:700}
        .live-banner{background:linear-gradient(90deg,rgba(192,57,43,0.1),rgba(255,153,0,0.1));backdrop-filter:blur(12px);-webkit-backdrop-filter:blur(12px);border:1px solid rgba(192,57,43,0.2);border-radius:12px;padding:8px 16px;margin-bottom:14px;display:flex;align-items:center;justify-content:center;gap:10px}
        .app-root{min-height:100vh;min-height:100dvh}
        .brand-ticker-row{display:flex;align-items:center;margin-bottom:14px;position:relative;overflow:hidden;background:rgba(17,17,17,0.55);backdrop-filter:blur(20px) saturate(1.4);-webkit-backdrop-filter:blur(20px) saturate(1.4);border:1px solid rgba(212,175,55,0.1);border-radius:14px;box-shadow:0 8px 32px rgba(0,0,0,0.4),inset 0 1px 0 rgba(255,255,255,0.04)}
        .brand-ticker-row::before{content:'';position:absolute;top:0;left:0;right:0;height:2px;background:linear-gradient(90deg,#D4AF37,#C0392B,#D4AF37);z-index:20;opacity:0.7}
        .brand-ticker-row::after{content:'';position:absolute;bottom:0;left:0;right:0;height:1px;background:linear-gradient(90deg,transparent,rgba(212,175,55,0.15),transparent);z-index:20}
        .ironmike-brand{display:flex;align-items:center;gap:14px;padding:10px 0 10px 16px;position:relative;z-index:10;flex-shrink:0;background:rgba(17,17,17,0.7)}
        .ironmike-brand::after{content:'';position:absolute;top:0;bottom:0;right:-48px;width:48px;background:linear-gradient(90deg,rgba(17,17,17,0.7) 0%,transparent 100%);z-index:6;pointer-events:none}
        .ticker-wrapper{flex:1;min-width:0;overflow:hidden;position:relative;z-index:1;display:flex;align-items:center}
        .ticker-wrapper .ticker-tape{margin-bottom:0;border:none;border-radius:0;box-shadow:none;background:transparent;backdrop-filter:none;-webkit-backdrop-filter:none;padding:0;flex:1;min-width:0}
        .ticker-wrapper .ticker-tape::before{display:none}
        .ticker-tape{margin-bottom:14px;overflow:hidden;position:relative;background:rgba(17,17,17,0.45);backdrop-filter:blur(16px) saturate(1.3);-webkit-backdrop-filter:blur(16px) saturate(1.3);border:1px solid rgba(255,255,255,0.05);border-radius:10px;padding:10px 0;box-shadow:0 4px 24px rgba(0,0,0,0.4);z-index:1}
        .ticker-tape::before,.ticker-tape::after{content:'';position:absolute;top:0;bottom:0;width:48px;z-index:2;pointer-events:none}
        .ticker-tape::before{left:0;background:linear-gradient(90deg,rgba(17,17,17,0.6) 0%,transparent 100%)}
        .ticker-tape::after{right:0;background:linear-gradient(270deg,rgba(17,17,17,0.6) 0%,transparent 100%)}
        .ticker-tape:hover .ticker-track{animation-play-state:paused}
        .ticker-track{display:flex;align-items:center;gap:32px;will-change:transform;animation:tickerScroll 90s linear infinite;width:max-content;backface-visibility:hidden;-webkit-backface-visibility:hidden}
        @keyframes tickerScroll{0%{transform:translate3d(0,0,0)}100%{transform:translate3d(-50%,0,0)}}
        @keyframes lossToastIn{from{opacity:0;transform:translateX(-50%) translateY(16px)}to{opacity:1;transform:translateX(-50%) translateY(0)}}
        /* TABLET 601–1024px: iPad, Android tablets */
        @media(max-width:1024px){
          .app-root{padding:16px 18px}
          .grid{grid-template-columns:1fr 1fr!important}
          .grid>.col:first-child{order:2}.grid>.col:nth-child(2){order:1;grid-column:1/-1}.grid>.col:last-child{order:3}
          .grid-bottom{grid-template-columns:1fr 1fr!important}
          .grid-bottom>.col:nth-child(2){grid-column:1/-1}
          .card{border-radius:12px;padding:18px}
          .btn{min-height:44px;padding:10px 18px}
          .chart-card{height:60vh!important;min-height:400px!important;max-height:600px!important}
          .control-panel{max-width:100%!important}
          .cp-row1{gap:3px!important;flex-wrap:wrap!important}
          .cp-row1 .btn{min-height:28px!important;padding:3px 10px!important}
        }
        /* PHONE ≤600px: iPhone, Android phones, Z Fold cover */
        @media(max-width:600px){
          .app-root{padding:12px 14px;margin:0;max-width:100%;border-radius:0}
          .grid{grid-template-columns:1fr!important}
          .grid>.col{order:unset!important;grid-column:unset!important}
          .grid-bottom{grid-template-columns:1fr!important}
          .grid-bottom>.col{grid-column:unset!important}
          .header-main{grid-template-columns:1fr!important;grid-template-rows:auto!important;gap:14px!important}
          .header-main>*{grid-column:1!important;grid-row:auto!important;justify-self:stretch!important}
          .header-price{justify-self:center!important}
          .control-panel{padding:8px 10px!important;max-width:100%!important}
          .cp-row1{gap:3px!important;justify-content:center!important;flex-wrap:wrap!important}
          .cp-row1 .btn{min-height:32px!important;padding:4px 10px!important;font-size:9px!important}
          .cp-row2{justify-content:center!important;gap:3px!important;flex-wrap:wrap!important}
          .status-bar{flex-wrap:wrap!important;gap:4px!important;padding:5px 10px!important}
          .pos-grid{grid-template-columns:repeat(2,1fr)!important}
          .card{border-radius:16px;padding:16px 18px}
          .btn{min-height:44px;padding:12px 20px;font-size:11px;border-radius:10px}
          .live-banner{border-radius:12px}
          .brand-ticker-row{flex-direction:column;overflow:visible}
          .ironmike-brand{padding:10px 14px 6px}
          .ironmike-brand::after{display:none}
          .ticker-wrapper{width:100%}
          .ticker-wrapper .ticker-tape{border-top:1px solid #1e1e1e}
          .ironmike-brand img{width:44px!important;height:44px!important}
          .coin-btn{min-height:44px;padding:12px 16px;-webkit-tap-highlight-color:transparent}
          .chart-card{height:55vh!important;min-height:320px!important;max-height:500px!important}
        }
        /* NARROW 320–400px: Z Fold cover (323px), Galaxy S25 (360px), legacy Android */
        @media(max-width:400px){
          .app-root{padding:10px 8px}
          .card{padding:12px 10px}
          .section-label{font-size:9px!important;letter-spacing:1px!important}
          .pos-grid{grid-template-columns:1fr!important}
          .cp-row1 .btn{font-size:8px!important;padding:3px 6px!important;letter-spacing:0.5px!important}
          .cp-row2 .btn{font-size:8px!important;padding:3px 6px!important}
          .status-bar{font-size:8px!important;gap:3px!important}
          .ironmike-brand img{width:36px!important;height:36px!important}
        }
      `}</style>

      {/* ══ LIVE MODE WARNING BANNER ══ */}
      {isLiveMode && (
        <div className="live-banner" role="alert">
          <span style={{ fontSize:"14px" }}>&#9888;</span>
          <span style={{ fontFamily:"'Bebas Neue',sans-serif", fontSize:"14px", color:"#C0392B", letterSpacing:"3px" }}>LIVE TRADING MODE</span>
          <span style={{ fontSize:"10px", color:"#ff9900" }}>Real funds at risk — trades execute on-chain</span>
        </div>
      )}

      {/* ══ BRAND + TICKER — horizontal row, ticker fades behind brand ══ */}
      <div className="brand-ticker-row">
        <div className="ironmike-brand">
          <img src="/Bravo.svg" alt="DoYou.trade" style={{ width:"80px", height:"80px", flexShrink:0 }} />
          <div>
            <div style={{ fontFamily:"'Bebas Neue',sans-serif", fontSize:"36px", color:"transparent", letterSpacing:"6px", lineHeight:"1", background:"linear-gradient(180deg,#D4AF37,#B8860B)", WebkitBackgroundClip:"text", WebkitTextFillColor:"transparent" }}>DOYOU.TRADE</div>
            <div style={{ width:"100%", height:"1px", background:"linear-gradient(90deg,#D4AF37,#C0392B,transparent)", margin:"4px 0" }} />
            <TradeQuote />
          </div>
        </div>
        <div className="ticker-wrapper">
          <TickerTape
            marketTickers={marketTickers}
            activeCoins={activeCoins}
            coins={coins}
            price={price}
            selectedCoin={selectedCoin}
            positions={positions}
            onSelectCoin={(sym) => { setSelectedCoin(sym); setChartSymbol(sym); if (!activeCoins.includes(sym)) setActiveCoins(prev => [...prev, sym]); }}
          />
        </div>
      </div>

      {/* ══ HEADER ══ */}
      <div className="header-main" style={{ display:"grid", gridTemplateColumns:"1fr", gridTemplateRows:"auto auto", alignItems:"center", marginBottom:"16px", gap:"12px 16px" }}>
        {/* Price — always centered */}
        <div className="header-price" style={{ gridColumn:"1", gridRow:"1", justifySelf:"center", textAlign:"center", contain:"layout paint", minWidth:0 }}>
          {price > 0 ? (
            <>
              <div style={{ fontFamily:"'Oswald',sans-serif", fontSize:"11px", color:"#D4AF37", letterSpacing:"3px", fontWeight:"600", marginBottom:"2px" }}>{selectedCoin}</div>
              <div style={{ fontFamily:"'Bebas Neue',sans-serif", fontSize:"36px", letterSpacing:"2px", color: priceUp?"#00E676":"#FF1744" }}>
                $<AnimatedNumber value={price} format={(v) => priceFormat(v)} duration={50} />
              </div>
              <div style={{ fontSize:"10px", color: change24h>=0?"#00E676":"#FF1744", marginTop:"2px" }}>
                {change24h>=0?"\u25B2":"\u25BC"} <AnimatedNumber value={Math.abs(change24h)} format={(v) => `${v.toFixed(2)}%`} duration={200} /> 24h
              </div>
              <div style={{ fontSize:"8px", color:"#5C5C5C", marginTop:"2px", letterSpacing:"1px" }}>{priceSource === "coinbase" ? "COINBASE · real-time" : "COINGECKO · may differ from chart"}</div>
            </>
          ) : (
            <FetchingPrice />
          )}
        </div>

        <ControlPanel
          account={account} winRate={winRate} startBal={startBal} targetBal={targetBal}
          thinking={thinking} botOn={botOn} connected={connected}
          claudeModel={claudeModel} handleModelChange={handleModelChange}
          tradingPreset={tradingPreset} presets={presets} presetCategories={presetCategories} handlePresetChange={handlePresetChange}
          profitGoal={profitGoal} setProfitGoal={setProfitGoal}
          handleStart={handleStart} handleStop={handleStop} handleAsk={handleAsk} handleReset={handleReset}
        />
      </div>

      {/* ══ FULL-WIDTH CHART ══ */}
      <ChartSection
        chartSymbol={chartSymbol} setChartSymbol={setChartSymbol}
        selectedCoin={selectedCoin} positions={positions} price={price}
        marketTickers={marketTickers}
        multiExchangePrices={multiExchangePrices} setMultiExchangePrices={setMultiExchangePrices}
      />

      {/* ══ OPEN POSITIONS (full width) ══ */}
      <PositionsPanel
        positions={positions} coins={coins} price={price}
        enableFutures={enableFutures} maxPositions={maxPositions} maxFuturesPositions={maxFuturesPositions}
        unrealized={unrealized} botOn={botOn} handleClose={handleClose}
      />

      {/* ══ 3-COL GRID (panels below chart) ══ */}
      <div className="grid-bottom">
        {/* ═══ LEFT ═══ */}
        <div className="col">
          <ClaudeBrainPanel
            thinking={thinking} botOn={botOn} countdown={countdown}
            decision={decision} lastCall={lastCall} lastAiBlockReason={lastAiBlockReason}
            pendingDecision={pendingDecision} pendingExpiresAt={pendingExpiresAt} pendingCountdown={pendingCountdown}
            handleApprovePending={handleApprovePending} handleRejectPending={handleRejectPending}
          />
          <MarketRegimePanel regime={regime} fearGreed={fearGreed} />
          <AgentKitPanel agentKit={agentKit} isLiveMode={isLiveMode} />
        </div>

        {/* ═══ CENTER ═══ */}
        <div className="col">
          <IndicatorsPanel indic={indic} history={history} />
          <RiskMonitorPanel account={account} startBal={startBal} trades={trades} winRate={winRate} />
        </div>

        {/* ═══ RIGHT ═══ */}
        <div className="col">
          <RecentTradesPanel
            trades={trades} connected={connected} exportTrades={exportTrades}
            tradeTypeBadge={tradeTypeBadge} openTradeDetail={openTradeDetail}
            setShowHistory={setShowHistory} fetchHistory={fetchHistory}
            tradesContainerRef={tradesContainerRef}
          />
          <ActivityLogPanel logs={logs} botOn={botOn} connected={connected} logsContainerRef={logsContainerRef} />
        </div>
      </div>

      {/* ══ ANALYTICS ROW (equity + analytics + memory) ══ */}
      <AnalyticsSection connected={connected} log={log} lossToast={lossToast}
        cbLive={cbLive} krakenEnabled={krakenEnabled} hasClaude={hasClaude}
        isLiveMode={isLiveMode} agentKit={agentKit} paperMode={paperMode}
        directionBias={directionBias} requireTradeApproval={requireTradeApproval}
        price={price} priceAge={priceAge} wsRetrying={wsRetrying} />

      {/* ══ FULL TRADE HISTORY OVERLAY ══ */}
      <TradeHistoryOverlay
        showHistory={showHistory} setShowHistory={setShowHistory}
        historyTrades={historyTrades} historyTotal={historyTotal} historyStats={historyStats}
        historyLoading={historyLoading} historyPage={historyPage} historyLimit={historyLimit}
        historyFilters={historyFilters} applyHistoryFilter={applyHistoryFilter}
        clearHistoryFilters={clearHistoryFilters} fetchHistory={fetchHistory}
        activeCoins={activeCoins} exportTrades={exportTrades}
        tradeTypeBadge={tradeTypeBadge} openTradeDetail={openTradeDetail}
      />

      {/* ══ TRADE DETAIL MODAL (Chart Screenshots) ══ */}
      <TradeDetailModal
        tradeDetail={tradeDetail} closeTradeDetail={closeTradeDetail}
        tradeDetailLoading={tradeDetailLoading} getAuthQueryParam={getAuthQueryParam}
      />

      {/* ══ CONFIRM DIALOG ══ */}
      {confirmAction && (
        <div className="confirm-overlay" onClick={() => setConfirmAction(null)} role="dialog" aria-modal="true" aria-label="Confirmation">
          <div className="confirm-box" onClick={e => e.stopPropagation()}>
            <div style={{ fontFamily:"'Bebas Neue',sans-serif", fontSize:"18px", color:"#D4AF37", letterSpacing:"3px", marginBottom:"16px" }}>CONFIRM ACTION</div>
            <div style={{ fontSize:"11px", color:"#D4D4D4", lineHeight:"1.9", marginBottom:"22px" }}>{confirmAction.label}</div>
            <div style={{ display:"flex", gap:"12px", justifyContent:"center" }}>
              <button className="btn btn-r" onClick={confirmYes} style={{ minWidth:"90px" }}>YES</button>
              <button className="btn btn-d" onClick={() => setConfirmAction(null)} style={{ minWidth:"90px", color:"#D4D4D4" }}>CANCEL</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default function App() {
  return (
    <ErrorBoundary>
      <Dashboard />
    </ErrorBoundary>
  );
}
