import { useState, useEffect, useRef, useCallback, Component } from "react";
import confetti from "canvas-confetti";
import TradingViewChart from "./TradingViewChart.jsx";

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
        <div style={{ fontFamily:"'Space Mono',monospace", background:"#06060f", color:"#b8c8d8", minHeight:"100vh", display:"flex", alignItems:"center", justifyContent:"center", flexDirection:"column", gap:"16px", padding:"20px", textAlign:"center" }}>
          <div style={{ fontSize:"48px" }}>₿</div>
          <div style={{ fontFamily:"'Chakra Petch',sans-serif", fontSize:"22px", fontWeight:"700", color:"#ff3366", letterSpacing:"2px" }}>SOMETHING WENT WRONG</div>
          <div style={{ fontSize:"12px", color:"#4a5568", maxWidth:"500px", lineHeight:"1.8" }}>
            {this.state.error?.message || "An unexpected error occurred."}
          </div>
          <button
            onClick={() => { this.setState({ hasError: false, error: null }); window.location.reload(); }}
            style={{ fontFamily:"'Space Mono',monospace", fontSize:"11px", fontWeight:"700", letterSpacing:"1.5px", padding:"10px 24px", border:"none", borderRadius:"4px", cursor:"pointer", background:"#8b5cf6", color:"#fff" }}
          >
            RELOAD DASHBOARD
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

// ─── Indicator math (demo mode only — backend computes when connected) ────────
function calcEMA(prices, period) {
  if (prices.length < 2) return null;
  const n = Math.min(period, prices.length), k = 2 / (n + 1);
  let v = prices.slice(0, n).reduce((a, b) => a + b, 0) / n;
  for (let i = n; i < prices.length; i++) v = prices[i] * k + v * (1 - k);
  return +v.toFixed(2);
}
function calcRSI(prices, period = 14) {
  if (prices.length < period + 1) return 50;
  let g = 0, l = 0;
  for (let i = prices.length - period; i < prices.length; i++) {
    const d = prices[i] - prices[i - 1];
    d > 0 ? (g += d) : (l += Math.abs(d));
  }
  return +(100 - 100 / (1 + (g / period) / (l / period + 1e-9))).toFixed(2);
}
function calcATR(prices, period = 14) {
  if (prices.length < 2) return 0;
  const trs = prices.slice(1).map((p, i) => Math.abs(p - prices[i]));
  const r = trs.slice(-period);
  return +(r.reduce((a, b) => a + b, 0) / r.length).toFixed(2);
}
function calcBB(prices, period = 20) {
  const r = prices.slice(-Math.min(period, prices.length));
  const mid = r.reduce((a, b) => a + b, 0) / r.length;
  const std = Math.sqrt(r.reduce((s, p) => s + (p - mid) ** 2, 0) / r.length);
  const width = mid ? +((4 * std / mid) * 100).toFixed(4) : 0;
  return { upper: +(mid + 2 * std).toFixed(2), middle: +mid.toFixed(2), lower: +(mid - 2 * std).toFixed(2), width };
}

// ─── Unique ID generator for logs ─────────────────────────────────────────────
let _logSeq = 0;
function logId() { return `log_${Date.now()}_${++_logSeq}`; }

const API_SECRET = import.meta.env.VITE_BOT_API_SECRET || "";

// Direct backend connection by default (no proxy). More reliable for WebSocket + API.
const BACKEND_BASE = import.meta.env.VITE_BACKEND_URL
  || (import.meta.env.DEV ? "http://localhost:8000" : "");

function getBackendWsUrl() {
  if (import.meta.env.VITE_WS_URL) return import.meta.env.VITE_WS_URL + (API_SECRET ? `?secret=${encodeURIComponent(API_SECRET)}` : "");
  if (BACKEND_BASE) {
    try {
      const u = new URL(BACKEND_BASE.replace(/\/$/, ""));
      const proto = u.protocol === "https:" ? "wss:" : "ws:";
      return `${proto}//${u.host}/ws` + (API_SECRET ? `?secret=${encodeURIComponent(API_SECRET)}` : "");
    } catch {}
  }
  return (window.location.protocol === "https:" ? "wss:" : "ws:") + "//" + window.location.host + "/ws"
    + (API_SECRET ? `?secret=${encodeURIComponent(API_SECRET)}` : "");
}
const ROUND_TRIP_FEE = 0.012;  // 0.6% taker × 2 sides
const DEFAULT_COINS = ["BTC","ETH","SOL","DOGE","LINK","AVAX","UNI","AAVE"];

function Dashboard() {
  // ── Connection ──────────────────────────────────────────────────────────────
  const [connected,   setConnected]   = useState(false);
  const [demoMode,    setDemoMode]    = useState(true);
  const [cbLive,      setCbLive]      = useState(false);
  const [hasClaude,   setHasClaude]   = useState(false);
  const [paperMode,   setPaperMode]   = useState(true);
  const [agentKit,    setAgentKit]    = useState({ agentkit_ready:false, wallet_address:null, network:null, error:null });
  const [wsRetrying,  setWsRetrying]  = useState(false);

  // ── Multi-coin ──────────────────────────────────────────────────────────────
  const [coins,       setCoins]       = useState({});
  const [activeCoins, setActiveCoins] = useState(DEFAULT_COINS);
  const [selectedCoin, setSelectedCoin] = useState("BTC");
  const selectedCoinRef = useRef("BTC");

  // ── Market (derived from selected coin) ───────────────────────────────────
  const [price,       setPrice]       = useState(0);
  const [prevPrice,   setPrevPrice]   = useState(0);
  const [change24h,   setChange24h]   = useState(0);
  const [history,     setHistory]     = useState([]);
  const [indic,       setIndic]       = useState({ ema9:null, ema21:null, rsi:50, atr:0, bb_upper:0, bb_middle:0, bb_lower:0, bb_width:0, vwap:null });
  const [regime,      setRegime]      = useState("ranging");
  const [fearGreed,   setFearGreed]   = useState({ value: 50, label: "Neutral" });
  const [candles,     setCandles]     = useState([]);
  const [priceFailed, setPriceFailed] = useState(false);

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

  // ── Trading preset (legendary trader strategies) ───────────────────────────
  const [tradingPreset, setTradingPreset] = useState("turtle");
  const [presets, setPresets] = useState([]);

  // ── Profit goal (configurable target, progress bar) ────────────────────────
  const [profitGoal, setProfitGoal] = useState(() => {
    try { const v = localStorage.getItem("claudebot_profit_goal"); return v ? Math.max(0, +v) : 4000; } catch { return 4000; }
  });
  useEffect(() => { if (profitGoal > 0) try { localStorage.setItem("claudebot_profit_goal", String(profitGoal)); } catch {} }, [profitGoal]);

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
  const demoRef      = useRef(null);
  const botTimerRef  = useRef(null);
  const priceAgeRef  = useRef(null);
  const lastResetRef = useRef("");
  const thinkingRef  = useRef(false);
  const lastGoalReachedRef = useRef(false);
  const profitGoalRef = useRef(profitGoal);
  const change24hRef = useRef(change24h);
  const priceTimestampRef = useRef(0);

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
      ws = new WebSocket(getBackendWsUrl());
      wsRef.current = ws;

      ws.onopen = () => {
        if (disposed) { ws.close(); return; }
        retryDelay = 2000;
        hadConnection = true;
        setConnected(true);
        setDemoMode(false);
        setWsRetrying(false);
        if (demoRef.current)    { clearInterval(demoRef.current);    demoRef.current    = null; }
        if (botTimerRef.current){ clearInterval(botTimerRef.current); botTimerRef.current = null; }
        if (priceAgeRef.current){ clearInterval(priceAgeRef.current); priceAgeRef.current = null; }
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
          }
          if (m.active_coins) setActiveCoins(m.active_coins);

          const isBtcSelected = selectedCoinRef.current === "BTC";
          if (isBtcSelected) {
            if (m.price != null)            { setPrevPrice(priceRef.current); setPrice(m.price); setPriceAge(0); priceTimestampRef.current = Date.now(); setPriceFailed(false); }
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
              confetti({ particleCount: 150, spread: 100, origin: { y: 0.6 } });
              setTimeout(() => confetti({ particleCount: 100, spread: 80, origin: { y: 0.5, x: 0.3 } }), 150);
              setTimeout(() => confetti({ particleCount: 100, spread: 80, origin: { y: 0.5, x: 0.7 } }), 300);
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
                confetti({ particleCount: 100, spread: 100, origin: { y: 0.6 } });
                setTimeout(() => confetti({ particleCount: 60, spread: 80, origin: { y: 0.5, x: 0.3 } }), 120);
                setTimeout(() => confetti({ particleCount: 60, spread: 80, origin: { y: 0.5, x: 0.7 } }), 240);
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
          if (m.fear_greed)               setFearGreed(m.fear_greed);
          if (m.agentkit)                 setAgentKit(m.agentkit);
          if (m.start_balance != null)    setStartBal(m.start_balance);
          if (m.target_balance != null)   setTargetBal(m.target_balance);
          if (m.profit_to_target != null && profitGoalRef.current === 0) setProfitGoal(m.profit_to_target);
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
        setConnected(false);
        setCbLive(false);
        setDemoMode(true);
        setWsRetrying(true);
        if (!demoRef.current) {
          if (hadConnection) {
            log("Backend disconnected — reconnecting...", "warning");
          } else {
            log("Backend offline — running demo mode. Start backend.py for live trading.", "warning");
          }
          startDemo();
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
  }, [log]);

  // ── Periodic account sync (failsafe so balance/P&L always reflect backend) ───
  useEffect(() => {
    if (!connected) return;
    const apiBase = BACKEND_BASE;
    const url = apiBase ? `${apiBase.replace(/\/$/, "")}/account` : "/account";
    const headers = {};
    if (API_SECRET) headers["x-bot-secret"] = API_SECRET;
    const sync = async () => {
      try {
        const ctrl = new AbortController();
        const to = setTimeout(() => ctrl.abort(), 5000);
        const r = await fetch(url, { headers, signal: ctrl.signal });
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
    const id = setInterval(sync, 5000); // 5s — crypto moves fast, keep P&L fresh
    return () => clearInterval(id);
  }, [connected]);

  // ── Demo: price feed (Coinbase REST) — same source as live trading ─
  const FETCH_TIMEOUT_MS = 5000;
  const DEMO_POLL_MS = 30000;  // 30s — Coinbase REST, no rate limit concerns
  let _fetchFailCount = useRef(0);
  const COINBASE_TICKER_URL = "/api/coinbase/ticker";
  function startDemo() {
    if (demoRef.current) return;
    priceAgeRef.current = setInterval(() => setPriceAge(a => a + 1), 1000);
    demoRef.current = setInterval(async () => {
      try {
        const ctrl = new AbortController();
        const to = setTimeout(() => ctrl.abort(), FETCH_TIMEOUT_MS);
        const r = await fetch(COINBASE_TICKER_URL, { signal: ctrl.signal });
        clearTimeout(to);
        if (!r.ok) {
          setPriceFailed(true);
          return;
        }
        const d = await r.json();
        const p   = d.bitcoin?.usd || priceRef.current;
        const chg = d.bitcoin?.usd_24h_change || 0;
        const ts  = new Date().toLocaleTimeString("en-US", { hour12:false, hour:"2-digit", minute:"2-digit" });
        setPrevPrice(priceRef.current);
        setPrice(p);
        setChange24h(+chg.toFixed(2));
        setPriceAge(0);
        setPriceFailed(false);
        priceTimestampRef.current = Date.now();
        _fetchFailCount.current = 0;
        setHistory(prev => {
          const next   = [...prev, { t: ts, price: p, change24h: +chg.toFixed(2) }].slice(-100);
          const raw    = next.map(x => x.price);
          const b      = calcBB(raw);
          const e9     = calcEMA(raw, 9);
          const e21    = calcEMA(raw, 21);
          const r14    = calcRSI(raw);
          const a14    = calcATR(raw);
          const newInd = { ema9:e9, ema21:e21, rsi:r14, atr:a14, bb_upper:b.upper, bb_middle:b.middle, bb_lower:b.lower, bb_width:b.width, vwap:null };
          setIndic(newInd);
          if (a14 > 600) setRegime("chaotic");
          else if (e9 && e21 && Math.abs(e9 - e21) > 200) setRegime(e9 > e21 ? "trending_up" : "trending_down");
          else setRegime("ranging");
          return next;
        });
        const now = Math.floor(Date.now() / 1000);
        const candleTime = now - (now % 60);
        setCandles(prev => {
          const arr = [...prev];
          const last = arr.length > 0 ? arr[arr.length - 1] : null;
          if (last && last.time === candleTime) {
            arr[arr.length - 1] = { ...last, high: Math.max(last.high, p), low: Math.min(last.low, p), close: p };
          } else {
            arr.push({ time: candleTime, open: p, high: p, low: p, close: p, volume: 0 });
          }
          return arr.slice(-300);
        });
      } catch {
        _fetchFailCount.current++;
        if (_fetchFailCount.current >= 3) setPriceFailed(true);
      }
    }, DEMO_POLL_MS);
  }

  // ── Demo: fetch Fear & Greed — fail-fast timeout ─────────────────────────────
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

  // ── Demo: initial price fetch — fail-fast, instant load ────────────────────────
  useEffect(() => {
    if (!demoMode) return;
    startDemo();
    (async () => {
      try {
        const ctrl = new AbortController();
        const to = setTimeout(() => ctrl.abort(), 5000);
        const r = await fetch(COINBASE_TICKER_URL, { signal: ctrl.signal });
        clearTimeout(to);
        if (!r.ok) {
          setPriceFailed(true);
          log("Price fetch failed — start backend for live data", "warning");
          return;
        }
        const d = await r.json();
        const p   = d.bitcoin?.usd;
        const chg = d.bitcoin?.usd_24h_change || 0;
        if (p) {
          setPrice(p);
          setChange24h(+chg.toFixed(2));
          setPriceAge(0);
          setPriceFailed(false);
          priceTimestampRef.current = Date.now();
          log(`BTC price loaded: $${p.toLocaleString()}`, "success");
        }
      } catch {
        setPriceFailed(true);
        log("Price fetch failed — will retry in 60s", "warning");
      }
    })();
  }, []); // eslint-disable-line

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
    fetch(url).then(r => r.ok && r.json()).then(d => d?.presets && setPresets(d.presets)).catch(() => {});
  }, [connected]);

  // ── Demo: midnight P&L reset ─────────────────────────────────────────────────
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

  // ── TP/SL checker (demo mode) ────────────────────────────────────────────────
  useEffect(() => {
    if (!demoMode || !positionsRef.current.length || price === 0) return;
    for (const pos of [...positionsRef.current]) {
      const coinPrice = coins[pos.symbol]?.price || price;
      if (coinPrice === 0) continue;
      const sz = pos.coin_size || pos.btc_size || 0;
      let hit = false, pnl = 0, reason = "";
      if (pos.side === "buy") {
        if (coinPrice >= pos.tp)  { hit=true; pnl=(pos.tp  -pos.entry)*sz; reason="TP HIT"; }
        else if (coinPrice<=pos.sl){ hit=true; pnl=(pos.sl  -pos.entry)*sz; reason="SL HIT"; }
      } else {
        if (coinPrice <= pos.tp)  { hit=true; pnl=(pos.entry-pos.tp)  *sz; reason="TP HIT"; }
        else if (coinPrice>=pos.sl){ hit=true; pnl=(pos.entry-pos.sl) *sz; reason="SL HIT"; }
      }
      if (!hit) continue;
      const net = +(pnl - pos.usd_size * ROUND_TRIP_FEE).toFixed(2);
      setAccount(a => ({ balance:+(a.balance+pos.usd_size+net).toFixed(2), daily_pnl:+(a.daily_pnl+net).toFixed(2), total_pnl:+(a.total_pnl+net).toFixed(2) }));
      setTrades(prev => [{ id:Date.now()+Math.random(), symbol:pos.symbol, side:pos.side, entry:pos.entry, exit:reason.includes("TP")?pos.tp:pos.sl, pnl:net, reason: (net > 0 ? "+" : "-") + " " + reason, ts:new Date().toLocaleTimeString(), win:net>0 }, ...prev].slice(0,30));
      setPositions(prev => prev.filter(p => p.id !== pos.id));
      log(`${reason} | ${pos.symbol} ${pos.side.toUpperCase()} | Net: ${net>=0?"+":""}$${net}`, net>=0?"success":"error");
    }
    setPosition(positionsRef.current[0] || null);
  }, [price, demoMode, log, coins]);

  const callClaude = useCallback(async () => {
    if (thinkingRef.current) return;
    setThinking(true);
    setLastCall(new Date().toLocaleTimeString());
    log("Claude analyzing live market data...", "claude");

    try {
      const backendBase = BACKEND_BASE || `${window.location.protocol}//${window.location.hostname}:8000`;
      const headers = {};
      if (API_SECRET) headers["x-bot-secret"] = API_SECRET;
      const res = await fetch(`${backendBase}/ask_claude`, { method: "POST", headers });

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
  }, [log]);

  // ── Bot auto-cycle (demo mode) ───────────────────────────────────────────────
  useEffect(() => {
    if (!demoMode || !botOn) {
      if (botTimerRef.current) { clearInterval(botTimerRef.current); botTimerRef.current = null; }
      return;
    }
    setCountdown(5);
    botTimerRef.current = setInterval(() => {
      setCountdown(prev => {
        if (prev <= 1) { callClaude(); return 180; }
        return prev - 1;
      });
    }, 1000);
    return () => { if (botTimerRef.current) clearInterval(botTimerRef.current); };
  }, [demoMode, botOn, callClaude]);

  // ── Handlers ─────────────────────────────────────────────────────────────────
  const handleStart = () => {
    if (connected) { send("start_bot"); }
    else { setBotOn(true); log("Demo bot started — first analysis in 5s", "success"); }
  };
  const handleStop = () => {
    if (connected) { send("stop_bot"); }
    else { setBotOn(false); log("Bot stopped", "warning"); }
  };
  const handleAsk = () => connected ? send("ask_claude", { direct: true }) : callClaude();
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
        const net = +(pnl - pos.usd_size * ROUND_TRIP_FEE).toFixed(2);
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
      const res = await fetch(`${backendBase}/trades/history?${params}`);
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
  }, [historyFilters, historyLimit, log]);

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
    if (tr.onchain) return <span className="tag" style={{ background:"#00d4ff18", color:"#00d4ff", fontSize:"9px" }}>ON-CHAIN</span>;
    if (tr.product_type === "futures") return <span className="tag" style={{ background:"#8b5cf618", color:"#8b5cf6", fontSize:"9px" }}>FUTURES{tr.leverage ? ` ${tr.leverage}x` : ""}</span>;
    return <span className="tag" style={{ background:"#1e2535", color:"#64748b", fontSize:"9px" }}>SPOT</span>;
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

  // ── Coin switching: update view when selected coin changes or its data updates
  useEffect(() => {
    const cd = coins[selectedCoin];
    if (!cd || !connected) return;
    if (cd.price != null)           { setPrevPrice(priceRef.current); setPrice(cd.price); setPriceAge(0); priceTimestampRef.current = Date.now(); }
    if (cd.price_change24h != null) setChange24h(cd.price_change24h);
    if (cd.history)                 setHistory(cd.history);
    if (cd.indicators)              setIndic(cd.indicators);
    if (cd.market_condition)        setRegime(cd.market_condition);
    if (cd.candles)                 setCandles(cd.candles);
  }, [selectedCoin, coins, connected]); // eslint-disable-line

  // ── Derived ───────────────────────────────────────────────────────────────────
  const priceUp      = demoMode
    ? (change24h >= 0)
    : (price >= prevPrice && prevPrice > 0);
  const winRate      = trades.length ? Math.round(trades.filter(t => t.win).length / trades.length * 100) : 0;
  const totalUnrealized = positions.reduce((sum, pos) => {
    const cp = coins[pos.symbol]?.price || price;
    const sz = pos.coin_size || pos.btc_size || 0;
    return sum + (pos.side === "buy" ? (cp - pos.entry) * sz : (pos.entry - cp) * sz);
  }, 0);
  const unrealized   = +totalUnrealized.toFixed(2);
  const condColor    = { ranging:"#00d4ff", trending_up:"#00ff88", trending_down:"#ff3366", chaotic:"#ff9900" }[regime] || "#64748b";
  const condLabel    = { ranging:"RANGING", trending_up:"TRENDING UP", trending_down:"TRENDING DOWN", chaotic:"CHAOTIC" }[regime] || regime;
  const condIcon     = { ranging:"\u25C8", trending_up:"\u25B2", trending_down:"\u25BC", chaotic:"\u26A1" }[regime] || "";
  const dailyLossPct = Math.abs(Math.min(0, account.daily_pnl) / Math.max(account.balance, 1) * 100);
  const fgColor      = fearGreed.value < 25 ? "#ff3366" : fearGreed.value < 50 ? "#ff9900" : fearGreed.value < 75 ? "#00d4ff" : "#00ff88";
  const isLiveMode   = !paperMode;

  return (
    <div className="app-root" style={{ fontFamily:"'Space Mono',monospace", background:"#06060f", color:"#b8c8d8",  padding:"20px 24px", fontSize:"12px" }}>
      <style>{`
        *{box-sizing:border-box;margin:0;padding:0;-webkit-tap-highlight-color:transparent}
        ::-webkit-scrollbar{width:3px;height:3px}::-webkit-scrollbar-track{background:#0a0a16}::-webkit-scrollbar-thumb{background:#1e2a40;border-radius:2px}
        *{scrollbar-width:thin;scrollbar-color:#1e2a40 #0a0a16}
        .card{background:#0a0a18;border:1px solid #131828;border-radius:8px;padding:16px}
        .grid{display:grid;grid-template-columns:260px 1fr 260px;gap:14px}
        .grid-bottom{display:grid;grid-template-columns:300px 1fr 300px;gap:16px;margin-top:16px}
        .col{display:flex;flex-direction:column;gap:14px}
        @keyframes pulse{0%,100%{opacity:1}50%{opacity:.3}}
        @keyframes fadein{from{opacity:0;transform:translateY(-3px)}to{opacity:1;transform:translateY(0)}}
        .pulse{animation:pulse 2s infinite}.blink{animation:pulse 0.7s infinite}.fadein{animation:fadein 0.3s ease}
        .btn{font-family:'Space Mono',monospace;font-size:10px;font-weight:700;letter-spacing:1.5px;padding:8px 16px;border:none;border-radius:5px;cursor:pointer;transition:all 0.15s;touch-action:manipulation;min-height:36px}
        .btn:disabled{opacity:.4;cursor:not-allowed}
        .btn:focus-visible{outline:2px solid #8b5cf6;outline-offset:2px}
        .btn-g{background:#00ff88;color:#06060f}.btn-g:hover:not(:disabled){background:#00cc6a;transform:translateY(-1px)}
        .btn-r{background:#ff3366;color:#fff}.btn-r:hover:not(:disabled){background:#cc1a44}
        .btn-p{background:transparent;color:#8b5cf6;border:1px solid #8b5cf633}.btn-p:hover:not(:disabled){background:#8b5cf611}
        .btn-d{background:transparent;color:#4a5568;border:1px solid #1e2535;font-size:9px;padding:6px 12px}.btn-d:hover:not(:disabled){background:#0d0d1c}
        .row{display:flex;justify-content:space-between;align-items:center;padding:6px 0;border-bottom:1px solid #0d0d1c}
        .tag{display:inline-block;padding:3px 8px;border-radius:3px;font-size:9px;font-weight:700;letter-spacing:.5px}
        .logrow{padding:4px 0;border-bottom:1px solid #0a0a16;animation:fadein 0.2s ease}
        .trow{padding:6px 0;border-bottom:1px solid #0d0d1c;display:flex;justify-content:space-between;align-items:center}
        .dot{width:7px;height:7px;border-radius:50%;display:inline-block;flex-shrink:0}
        .confirm-overlay{position:fixed;inset:0;background:rgba(0,0,0,0.7);display:flex;align-items:center;justify-content:center;z-index:9999;animation:fadein 0.15s ease;padding:env(safe-area-inset-top) env(safe-area-inset-right) env(safe-area-inset-bottom) env(safe-area-inset-left)}
        .confirm-box{background:#0a0a18;border:1px solid #ff990044;border-radius:8px;padding:24px 28px;max-width:400px;text-align:center}
        select option,select optgroup{background:#0a0a18;color:#b8c8d8;font-family:'Space Mono',monospace;font-size:10px}
        select optgroup{color:#4a5568;font-weight:700}
        .live-banner{background:linear-gradient(90deg,#ff336622,#ff990022);border:1px solid #ff336644;border-radius:6px;padding:8px 16px;margin-bottom:14px;display:flex;align-items:center;justify-content:center;gap:10px}
        .app-root{min-height:100vh;min-height:100dvh}
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
        }
        /* PHONE ≤600px: iPhone, Android phones, Z Fold cover */
        @media(max-width:600px){
          .app-root{padding:12px 14px;margin:0;max-width:100%;border-radius:0}
          .grid{grid-template-columns:1fr!important}
          .grid>.col{order:unset!important;grid-column:unset!important}
          .grid-bottom{grid-template-columns:1fr!important}
          .grid-bottom>.col{grid-column:unset!important}
          .header-main{flex-direction:column!important;align-items:stretch!important;gap:14px!important}
          .header-stats{justify-content:space-around!important;flex-wrap:wrap;gap:10px!important}
          .header-price{text-align:center}
          .status-bar{justify-content:center!important}
          .pos-grid{grid-template-columns:repeat(2,1fr)!important}
          .card{border-radius:16px;padding:16px 18px}
          .btn{min-height:44px;padding:12px 20px;font-size:11px;border-radius:10px}
          .live-banner{border-radius:12px}
          .coin-btn{min-height:44px;padding:12px 16px;-webkit-tap-highlight-color:transparent}
          .chart-card{height:55vh!important;min-height:320px!important;max-height:500px!important}
        }
        /* NARROW 320–400px: Z Fold cover (323px), Galaxy S25 (360px), legacy Android */
        @media(max-width:400px){
          .app-root{padding:10px 12px}
        }
      `}</style>

      {/* ══ LIVE MODE WARNING BANNER ══ */}
      {isLiveMode && (
        <div className="live-banner" role="alert">
          <span style={{ fontSize:"14px" }}>&#9888;</span>
          <span style={{ fontFamily:"'Chakra Petch',sans-serif", fontSize:"11px", fontWeight:"700", color:"#ff3366", letterSpacing:"1.5px" }}>LIVE TRADING MODE</span>
          <span style={{ fontSize:"10px", color:"#ff9900" }}>Real funds at risk — trades execute on-chain</span>
        </div>
      )}

      {/* ══ STATUS BAR ══ */}
      <div className="status-bar" style={{ display:"flex", gap:"8px", marginBottom:"14px", flexWrap:"wrap", alignItems:"center" }}>
        {[
          { label:"BACKEND",    ok:connected,  on:"LIVE",        off:"OFFLINE",     okColor:"#00ff88", offColor:"#ff3366" },
          { label:"COINBASE",   ok:cbLive,     on:"REAL-TIME",   off:"REST",        okColor:"#00ff88", offColor:"#ff9900" },
          { label:"CLAUDE",     ok:hasClaude,  on:"READY",       off:"NO KEY",      okColor:"#00ff88", offColor:"#ff9900" },
          { label:"MODE",       ok:isLiveMode, on:"LIVE",        off:"PAPER",       okColor:"#ff3366", offColor:"#ff9900" },
          { label:"AGENTKIT",  ok:agentKit.agentkit_ready, on:"ON-CHAIN",   off: paperMode ? "PAPER" : "OFFLINE", okColor:"#00d4ff", offColor:"#2d3748" },
        ].map(s => (
          <div key={s.label} style={{ display:"flex", gap:"6px", alignItems:"center", background:"#0a0a18", border:"1px solid #131828", borderRadius:"5px", padding:"6px 10px" }} role="status" aria-label={`${s.label}: ${s.ok ? s.on : s.off}`}>
            <span style={{ fontSize:"8px", color:"#2d3748" }}>{s.label}</span>
            <span style={{ fontSize:"10px", fontWeight:"700", color: s.ok ? s.okColor : s.offColor }}>
              <span className="dot" style={{ background: s.ok ? s.okColor : s.offColor, width:"5px", height:"5px", marginRight:"3px", verticalAlign:"middle" }} />
              {s.ok ? s.on : s.off}
            </span>
          </div>
        ))}
        {directionBias !== "both" && (
          <div style={{ display:"flex", gap:"6px", alignItems:"center", background:"#0a0a18", border:"1px solid #131828", borderRadius:"5px", padding:"6px 10px" }}>
            <span style={{ fontSize:"8px", color:"#2d3748" }}>DIRECTION</span>
            <span style={{ fontSize:"10px", fontWeight:"700", color: directionBias === "long" ? "#00ff88" : "#ff3366" }}>
              {directionBias === "long" ? "\u25B2 LONG ONLY" : "\u25BC SHORT ONLY"}
            </span>
          </div>
        )}
        {requireTradeApproval && (
          <div style={{ display:"flex", gap:"6px", alignItems:"center", background:"#ff990018", border:"1px solid #ff990044", borderRadius:"5px", padding:"6px 10px" }}>
            <span style={{ fontSize:"8px", color:"#ff9900" }}>APPROVAL</span>
            <span style={{ fontSize:"10px", fontWeight:"700", color:"#ff9900" }}>ON</span>
          </div>
        )}
        {price > 0 && <span style={{ fontSize:"9px", color: priceAge > 60 ? "#ff9900" : "#2d3748", marginLeft:"4px" }}>price {priceAge}s ago</span>}
        {wsRetrying && !connected && <span style={{ fontSize:"9px", color:"#ff9900", marginLeft:"4px" }}>Reconnecting...</span>}
        {demoMode && <span style={{ fontSize:"9px", color:"#ff9900", marginLeft:"4px" }}>Run python backend.py for live Claude trading</span>}
      </div>

      {/* ══ HEADER ══ */}
      <div className="header-main" style={{ display:"flex", alignItems:"center", justifyContent:"space-between", marginBottom:"16px", flexWrap:"wrap", gap:"12px" }}>
        {/* Logo */}
        <div style={{ display:"flex", alignItems:"center", gap:"10px" }}>
          <div style={{ background:"linear-gradient(135deg,#8b5cf6,#00d4ff)", width:"42px", height:"42px", borderRadius:"10px", display:"flex", alignItems:"center", justifyContent:"center", fontSize:"22px", color:"#fff", boxShadow:"0 0 24px #8b5cf655", flexShrink:0 }} aria-hidden="true">&#x20BF;</div>
          <div>
            <div style={{ fontFamily:"'Chakra Petch',sans-serif", fontSize:"18px", fontWeight:"700", color:"#fff", letterSpacing:"3px" }}>CLAUDE<span style={{ color:"#00d4ff" }}>BOT</span></div>
            <div style={{ fontSize:"9px", color:"#4a5568", letterSpacing:"1px" }}>AI-POWERED MULTI-COIN TRADING ENGINE</div>
          </div>
        </div>

        {/* Price */}
        <div className="header-price" style={{ textAlign:"center" }}>
          {priceFailed && price === 0 ? (
            <div style={{ fontFamily:"'Chakra Petch',sans-serif", fontSize:"16px", color:"#ff3366" }}>
              Price unavailable
              <div style={{ fontSize:"10px", color:"#4a5568", marginTop:"4px" }}>Price feed retrying...</div>
            </div>
          ) : price > 0 ? (
            <>
              <div style={{ fontSize:"10px", color:"#8b5cf6", letterSpacing:"2px", fontWeight:"700", marginBottom:"2px" }}>{selectedCoin}</div>
              <div style={{ fontFamily:"'Chakra Petch',sans-serif", fontSize:"30px", fontWeight:"700", letterSpacing:"1px", color: priceUp?"#00ff88":"#ff3366", textShadow:`0 0 24px ${priceUp?"#00ff8844":"#ff336644"}` }}>
                ${price < 10 ? price.toFixed(4) : price < 1000 ? price.toFixed(2) : price.toLocaleString()}
              </div>
              <div style={{ fontSize:"10px", color: change24h>=0?"#00ff88":"#ff3366", marginTop:"2px" }}>
                {change24h>=0?"\u25B2":"\u25BC"} {Math.abs(change24h).toFixed(2)}% 24h
              </div>
            </>
          ) : (
            <div className="blink" style={{ fontFamily:"'Chakra Petch',sans-serif", fontSize:"22px", color:"#2d3748" }}>Fetching price...</div>
          )}
        </div>

        {/* Stats + Controls */}
        <div className="header-stats" style={{ display:"flex", gap:"20px", alignItems:"center", flexWrap:"wrap" }}>
          {[
            { label:"BALANCE",   val:`$${account.balance.toFixed(2)}`,                                                    color:"#e2e8f0" },
            { label:"TOTAL P&L", val:`${account.total_pnl>=0?"+":""}$${account.total_pnl.toFixed(2)}`,                   color:account.total_pnl>=0?"#00ff88":"#ff3366" },
            { label:"TODAY",     val:`${account.daily_pnl>=0?"+":""}$${account.daily_pnl.toFixed(2)}`,                   color:account.daily_pnl>=0?"#00ff88":"#ff3366" },
            { label:"WIN RATE",  val:`${winRate}%`,                                                                        color:winRate>=50?"#00ff88":"#ff3366" },
          ].map(s => (
            <div key={s.label} style={{ textAlign:"right" }}>
              <div style={{ fontSize:"9px", color:"#2d3748", letterSpacing:"1px" }}>{s.label}</div>
              <div style={{ fontFamily:"'Chakra Petch',sans-serif", fontSize:"15px", fontWeight:"700", color:s.color }}>{s.val}</div>
            </div>
          ))}
          {connected && (
            <div style={{ textAlign:"right" }}>
              <div style={{ fontSize:"9px", color:"#2d3748", letterSpacing:"1px" }}>STRATEGY</div>
              <select
                value={tradingPreset}
                onChange={e => handlePresetChange(e.target.value)}
                title={presets.find(p => p.id === tradingPreset)?.description}
                style={{
                  fontFamily:"'Space Mono',monospace", fontSize:"10px", padding:"6px 8px", borderRadius:"4px",
                  border:"1px solid #131828", background:"#0a0a18", color:"#b8c8d8", outline:"none",
                  cursor:"pointer", minWidth:"140px",
                }}
              >
                {(presets.length ? presets : [{ id:tradingPreset, name:tradingPreset, trader:"" }]).map(p => (
                  <option key={p.id} value={p.id}>{p.name}</option>
                ))}
              </select>
            </div>
          )}
          <div style={{ display:"flex", gap:"8px" }}>
            {!botOn
              ? <button className="btn btn-g" onClick={handleStart} aria-label="Start bot">{"\u25B6"} START</button>
              : <button className="btn btn-r" onClick={handleStop} aria-label="Stop bot">{"\u25A0"} STOP</button>}
            <button className="btn btn-p" onClick={handleAsk} disabled={thinking} aria-label="Ask Claude AI for analysis">
              {thinking ? <span className="blink">THINKING</span> : "\u2B21 ASK AI"}
            </button>
            <button className="btn btn-d" onClick={handleReset} aria-label="Reset paper trading balance">{"\u21BA"} RESET</button>
          </div>
        </div>
      </div>

      {/* ══ PAPER WALLET: $1K → $5K + PROFIT GOAL BAR ══ */}
      <div style={{ marginBottom:"14px", padding:"10px 14px", background:"#0a0a18", borderRadius:"8px", border:"1px solid #131828" }}>
        <div style={{ display:"flex", alignItems:"center", gap:"12px", flexWrap:"wrap" }}>
          <span style={{ fontSize:"9px", color:"#2d3748", letterSpacing:"1.5px" }}>
            PAPER WALLET ${startBal?.toLocaleString?.() || startBal} → ${targetBal?.toLocaleString?.() || targetBal}
          </span>
          <span style={{ fontSize:"9px", color:"#2d3748", letterSpacing:"1.5px" }}>|</span>
          <span style={{ fontSize:"9px", color:"#2d3748", letterSpacing:"1.5px" }}>PROFIT GOAL</span>
          <div style={{ display:"flex", gap:"6px", flexWrap:"wrap" }}>
            {[50, 100, 250, 500, 1000, 2500, 4000].map(g => (
              <button
                key={g}
                onClick={() => setProfitGoal(g)}
                style={{
                  fontFamily:"'Space Mono',monospace", fontSize:"10px", padding:"6px 10px", borderRadius:"4px",
                  border: profitGoal === g ? "1px solid #00ff88" : "1px solid #131828",
                  background: profitGoal === g ? "#00ff8818" : "#06060f", color: profitGoal === g ? "#00ff88" : "#8892a4",
                  cursor:"pointer", fontWeight:"600",
                }}
              >
                ${g}
              </button>
            ))}
            <input
              type="number"
              min="0"
              step="10"
              placeholder="Set target"
              value={profitGoal > 0 ? profitGoal : ""}
              onChange={e => setProfitGoal(Math.max(0, +e.target.value || 0))}
              style={{
                width:"70px", fontFamily:"'Space Mono',monospace", fontSize:"10px", padding:"6px 8px",
                background:"#06060f", border:"1px solid #131828", borderRadius:"4px", color:"#e2e8f0",
              }}
            />
            {profitGoal > 0 && (
              <button
                onClick={() => setProfitGoal(0)}
                style={{ fontSize:"10px", color:"#4a5568", background:"none", border:"none", cursor:"pointer", padding:"6px 4px" }}
                title="Clear goal"
              >
                ✕
              </button>
            )}
          </div>
          {profitGoal > 0 && (
            <div style={{ flex:1, minWidth:"120px", maxWidth:"280px" }}>
              <div style={{ height:"6px", background:"#131828", borderRadius:"3px", overflow:"hidden" }}>
                <div
                  style={{
                    height:"100%", width:`${Math.min(100, Math.max(0, (account.total_pnl / profitGoal) * 100))}%`,
                    background: account.total_pnl >= profitGoal ? "#00ff88" : "linear-gradient(90deg,#8b5cf6,#00d4ff)",
                    borderRadius:"3px", transition:"width 0.4s ease",
                  }}
                />
              </div>
              <div style={{ fontSize:"9px", color:"#4a5568", marginTop:"4px" }}>
                ${Math.max(0, account.total_pnl).toFixed(0)} / ${profitGoal}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* ══ COIN TICKER STRIP ══ */}
      <div style={{ display:"flex", gap:"8px", marginBottom:"14px", overflowX:"auto", paddingBottom:"6px" }}>
        {activeCoins.map(sym => {
          const cd = coins[sym];
          const coinPrice = cd?.price || 0;
          const coinChg = cd?.price_change24h || 0;
          const isSelected = sym === selectedCoin;
          const hasPosition = positions.some(p => p.symbol === sym);
          return (
            <button
              key={sym}
              className="coin-btn"
              onClick={() => setSelectedCoin(sym)}
              style={{
                fontFamily:"'Space Mono',monospace", fontSize:"10px", fontWeight:"700",
                padding:"8px 14px", borderRadius:"5px", cursor:"pointer", flexShrink:0,
                border: isSelected ? "1px solid #8b5cf666" : hasPosition ? "1px solid #00ff8844" : "1px solid #131828",
                background: isSelected ? "#8b5cf611" : "#0a0a18",
                color: isSelected ? "#fff" : "#8892a4",
                transition:"all 0.15s",
              }}
            >
              <div style={{ letterSpacing:"1.5px" }}>{sym}</div>
              {coinPrice > 0 && (
                <div style={{ fontSize:"9px", color: coinChg >= 0 ? "#00ff88" : "#ff3366", marginTop:"2px" }}>
                  ${coinPrice < 10 ? coinPrice.toFixed(4) : coinPrice < 1000 ? coinPrice.toFixed(2) : coinPrice.toLocaleString()}
                  <span style={{ marginLeft:"4px" }}>{coinChg >= 0 ? "\u25B2" : "\u25BC"}{Math.abs(coinChg).toFixed(1)}%</span>
                </div>
              )}
              {hasPosition && <div style={{ fontSize:"8px", color:"#00ff88", marginTop:"1px" }}>{"\u25CF"} OPEN</div>}
            </button>
          );
        })}
      </div>

      {/* ══ FULL-WIDTH CHART ══ */}
      <div className="card chart-card" style={{ height:"65vh", minHeight:"500px", maxHeight:"700px", display:"flex", flexDirection:"column", marginBottom:"16px", padding:"12px", position:"relative", zIndex:1, overflow:"hidden" }}>
        <div style={{ display:"flex", justifyContent:"space-between", alignItems:"center", marginBottom:"10px", padding:"0 4px" }}>
          <div style={{ display:"flex", alignItems:"center", gap:"10px" }}>
            <span style={{ fontFamily:"'Chakra Petch',sans-serif", fontSize:"13px", color:"#e2e8f0", fontWeight:"700", letterSpacing:"2px" }}>{selectedCoin} / USD</span>
            <span style={{ fontSize:"9px", color:"#4a5568", letterSpacing:"1px" }}>TRADINGVIEW PRO</span>
          </div>
          {positions.length > 0 && (
            <div style={{ display:"flex", gap:"10px", fontSize:"9px", alignItems:"center", flexWrap:"wrap" }}>
              {positions.filter(p => p.symbol === selectedCoin).map(pos => (
                <div key={pos.id} style={{ display:"flex", gap:"8px", padding:"2px 6px", borderRadius:"3px", background: pos.side==="buy"?"#00ff8808":"#ff336608" }}>
                  <span style={{ color: pos.side==="buy"?"#00ff88":"#ff3366", fontWeight:"700" }}>{pos.side?.toUpperCase()}</span>
                  <span style={{ color:"#00d4ff" }}>E ${pos.entry?.toLocaleString()}</span>
                  <span style={{ color:"#00ff88" }}>TP ${pos.tp?.toLocaleString()}</span>
                  <span style={{ color:"#ff3366" }}>SL ${pos.sl?.toLocaleString()}</span>
                </div>
              ))}
            </div>
          )}
        </div>
        <div style={{ flex: 1, minHeight: 0 }}>
          <TradingViewChart symbol={selectedCoin} />
        </div>
      </div>

      {/* ══ OPEN POSITIONS (full width) ══ */}
      {positions.length > 0 ? (
        <div style={{ marginBottom:"16px", position:"relative", zIndex:2 }}>
          <div style={{ display:"flex", justifyContent:"space-between", alignItems:"center", marginBottom:"8px" }}>
            <div style={{ display:"flex", alignItems:"center", gap:"10px" }}>
              <span style={{ fontSize:"9px", color:"#2d3748", letterSpacing:"2px" }}>
                OPEN POSITIONS ({positions.length}/{enableFutures ? maxPositions + maxFuturesPositions : maxPositions})
              </span>
              {unrealized !== 0 && (
                <span style={{ fontSize:"10px", fontWeight:"700", color: unrealized >= 0 ? "#00ff88" : "#ff3366" }}>
                  Total: {unrealized >= 0 ? "+" : ""}${unrealized.toFixed(2)}
                </span>
              )}
            </div>
            {positions.length > 1 && (
              <button className="btn btn-d" onClick={() => handleClose()} style={{ padding:"4px 10px", fontSize:"9px", color:"#ff9900", borderColor:"#ff990033" }}>CLOSE ALL</button>
            )}
          </div>
          <div style={{ display:"flex", flexDirection:"column", gap:"10px" }}>
            {positions.map(pos => {
              const cp = coins[pos.symbol]?.price || price;
              const sz = pos.coin_size || pos.btc_size || 0;
              const posUnrealized = +((pos.side === "buy" ? cp - pos.entry : pos.entry - cp) * sz).toFixed(2);
              const range = Math.abs(pos.tp - pos.sl);
              let progress = 50;
              if (range > 0) {
                progress = pos.side === "buy"
                  ? ((cp - pos.sl) / range) * 100
                  : ((pos.sl - cp) / range) * 100;
                progress = Math.max(0, Math.min(100, progress));
              }
              return (
                <div key={pos.id || pos.symbol} className="card fadein" style={{ border:`1px solid ${pos.side==="buy"?"#00ff8822":"#ff336622"}`, boxShadow:`0 0 20px ${pos.side==="buy"?"#00ff8811":"#ff336611"}` }}>
                  <div style={{ display:"flex", justifyContent:"space-between", alignItems:"center", marginBottom:"10px" }}>
                    <div style={{ display:"flex", alignItems:"center", gap:"10px" }}>
                      <span className="dot pulse" style={{ background:pos.side==="buy"?"#00ff88":"#ff3366" }} />
                      <span style={{ fontFamily:"'Chakra Petch',sans-serif", fontSize:"11px", color:pos.side==="buy"?"#00ff88":"#ff3366", fontWeight:"700", letterSpacing:"2px" }}>
                        {pos.onchain ? "\u26D3 " : ""}{pos.side?.toUpperCase()} {pos.symbol || "BTC"}
                      </span>
                      {pos.onchain && <span className="tag" style={{ background:"#00d4ff18", color:"#00d4ff", fontSize:"9px" }}>ON-CHAIN</span>}
                      {pos.product_type === "futures" && <span className="tag" style={{ background:"#8b5cf618", color:"#8b5cf6", fontSize:"9px" }}>FUTURES{pos.leverage ? ` ${pos.leverage}x` : ""}</span>}
                    </div>
                    <div style={{ display:"flex", alignItems:"center", gap:"10px" }}>
                      <span style={{ fontSize:"9px", color:"#2d3748" }}>since {pos.open_ts}</span>
                      <button className="btn btn-d" onClick={() => handleClose(pos)} style={{ padding:"4px 8px", fontSize:"9px", color:"#ff9900", borderColor:"#ff990033" }}>{"\u2715"}</button>
                    </div>
                  </div>
                  <div className="pos-grid" style={{ display:"grid", gridTemplateColumns:"repeat(5,1fr)", gap:"8px" }}>
                    {[
                      { label:"ENTRY",       val:`$${pos.entry?.toLocaleString()}`,          color:"#e2e8f0" },
                      { label:"TAKE PROFIT", val:`$${pos.tp?.toLocaleString()}`,             color:"#00ff88" },
                      { label:"STOP LOSS",   val:`$${pos.sl?.toLocaleString()}`,             color:"#ff3366" },
                      { label:"SIZE",        val:`$${(pos.usd_size||0).toFixed(2)}`,         color:"#00d4ff" },
                      { label:"UNREALIZED",  val:`${posUnrealized>=0?"+":""}$${posUnrealized.toFixed(2)}`, color:posUnrealized>=0?"#00ff88":"#ff3366" },
                    ].map(s => (
                      <div key={s.label} style={{ background:"#06060f", borderRadius:"5px", padding:"8px 6px", textAlign:"center" }}>
                        <div style={{ fontSize:"8px", color:"#2d3748", marginBottom:"3px" }}>{s.label}</div>
                        <div style={{ fontSize:"10px", fontWeight:"700", color:s.color }}>{s.val}</div>
                      </div>
                    ))}
                  </div>
                  <div style={{ marginTop:"8px" }}>
                    <div style={{ display:"flex", justifyContent:"space-between", fontSize:"8px", color:"#2d3748", marginBottom:"4px" }}>
                      <span>SL {((Math.abs(pos.entry-pos.sl)/Math.max(pos.entry,1))*100).toFixed(2)}%</span>
                      <span>TP {((Math.abs(pos.tp-pos.entry)/Math.max(pos.entry,1))*100).toFixed(2)}%</span>
                    </div>
                    <div style={{ height:"3px", background:"#131828", borderRadius:"2px", overflow:"hidden" }}>
                      <div style={{ height:"100%", width:`${progress}%`, background:posUnrealized>=0?"#00ff88":"#ff3366", transition:"width 0.5s", borderRadius:"2px" }} />
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      ) : (
        <div className="card" style={{ textAlign:"center", padding:"16px", color:"#2d3748", fontSize:"11px", letterSpacing:"1.5px", marginBottom:"16px", position:"relative", zIndex:2 }}>
          {"\u25CB"} NO OPEN POSITIONS — {botOn ? `Scanning (0/${enableFutures ? maxPositions + maxFuturesPositions : maxPositions} slots)...` : "Start bot to begin"}
        </div>
      )}

      {/* ══ 3-COL GRID (panels below chart) ══ */}
      <div className="grid-bottom">

        {/* ═══ LEFT ═══ */}
        <div className="col">

          {/* Claude Brain */}
          <div className="card" style={{ border:"1px solid #8b5cf622", boxShadow: thinking?"0 0 30px #8b5cf644":"0 0 12px #8b5cf610" }}>
            <div style={{ display:"flex", alignItems:"center", justifyContent:"space-between", marginBottom:"14px" }}>
              <div style={{ display:"flex", alignItems:"center", gap:"8px" }}>
                <span className="dot" style={{ background: thinking?"#8b5cf6":botOn?"#00ff88":"#2d3748", animation:(thinking||botOn)?"pulse 1.5s infinite":"none", boxShadow:`0 0 8px ${thinking?"#8b5cf6":botOn?"#00ff88":"transparent"}` }} />
                <span style={{ fontFamily:"'Chakra Petch',sans-serif", fontSize:"11px", color:"#8b5cf6", fontWeight:"700", letterSpacing:"2px" }}>CLAUDE BRAIN</span>
              </div>
              {botOn && !thinking && <span style={{ fontSize:"10px", color:"#2d3748" }}>next: {countdown}s</span>}
              {thinking         && <span className="blink" style={{ fontSize:"10px", color:"#8b5cf6" }}>analyzing...</span>}
            </div>

            <div style={{ marginBottom:"12px" }}>
              <div style={{ display:"flex", justifyContent:"space-between", alignItems:"center", marginBottom:"5px" }}>
                <span style={{ fontSize:"9px", color:"#2d3748", letterSpacing:"1px" }}>MODEL</span>
                {thinking && <span style={{ fontSize:"8px", color:"#ff9900", letterSpacing:"0.5px" }}>LOCKED — AI THINKING</span>}
              </div>
              <select
                value={claudeModel}
                onChange={e => handleModelChange(e.target.value)}
                disabled={thinking}
                style={{
                  fontFamily:"'Space Mono',monospace", fontSize:"10px", fontWeight:"700",
                  width:"100%", padding:"7px 10px", borderRadius:"5px",
                  backgroundColor: thinking ? "#0d0d1c" : "#06060f",
                  backgroundImage: thinking ? "none" : "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='6' viewBox='0 0 10 6'%3E%3Cpath fill='%238b5cf6' d='M0 0l5 6 5-6z'/%3E%3C/svg%3E\")",
                  backgroundRepeat:"no-repeat", backgroundPosition:"right 10px center",
                  color: thinking ? "#2d3748" : "#8b5cf6",
                  border: thinking ? "1px solid #1e253522" : "1px solid #8b5cf622",
                  cursor: thinking ? "not-allowed" : "pointer",
                  outline:"none", appearance:"none",
                  opacity: thinking ? 0.5 : 1,
                  transition:"all 0.2s",
                }}
                aria-label="Select Claude model"
              >
                <optgroup label="Claude 4.6 — Latest">
                  <option value="claude-opus-4-6">Opus 4.6 — Most Powerful</option>
                  <option value="claude-sonnet-4-6">Sonnet 4.6 — Fast + Smart</option>
                </optgroup>
                <optgroup label="Claude 4.5">
                  <option value="claude-opus-4-5-20251101">Opus 4.5</option>
                  <option value="claude-sonnet-4-5-20250929">Sonnet 4.5</option>
                  <option value="claude-haiku-4-5-20251001">Haiku 4.5 — Fastest</option>
                </optgroup>
                <optgroup label="Claude 4.x">
                  <option value="claude-opus-4-1-20250805">Opus 4.1</option>
                  <option value="claude-opus-4-20250514">Opus 4</option>
                  <option value="claude-sonnet-4-20250514">Sonnet 4</option>
                </optgroup>
                <optgroup label="Legacy">
                  <option value="claude-3-haiku-20240307">Haiku 3 (Deprecated)</option>
                </optgroup>
              </select>
            </div>

            {/* ══ PENDING TRADE (approval required) ══ */}
            {pendingDecision && (
              <div className="card fadein" style={{ border:"2px solid #ff9900", background:"#ff990008", marginBottom:"14px" }}>
                <div style={{ fontFamily:"'Chakra Petch',sans-serif", fontSize:"11px", fontWeight:"700", color:"#ff9900", letterSpacing:"2px", marginBottom:"12px" }}>
                  PENDING TRADE — AWAITING YOUR APPROVAL
                </div>
                <div style={{ display:"flex", alignItems:"center", gap:"10px", marginBottom:"10px" }}>
                  <span className="tag" style={{
                    background: pendingDecision.action === "buy" ? "#00ff8820" : "#ff336620",
                    color: pendingDecision.action === "buy" ? "#00ff88" : "#ff3366",
                    fontSize:"12px", padding:"4px 12px"
                  }}>
                    {pendingDecision.action === "buy" ? "\u25B2 BUY" : "\u25BC SELL"} {pendingDecision.symbol || ""}
                  </span>
                  {pendingExpiresAt > 0 && (
                    <span style={{ fontSize:"10px", color:"#ff9900" }}>
                      Expires in {pendingCountdown}s
                    </span>
                  )}
                </div>
                {pendingDecision.reasoning && (
                  <div style={{ fontSize:"11px", color:"#8892a4", lineHeight:"1.6", marginBottom:"12px", fontStyle:"italic" }}>
                    &ldquo;{String(pendingDecision.reasoning).slice(0, 120)}&rdquo;
                  </div>
                )}
                {pendingDecision.order && (
                  <div style={{ background:"#06060f", borderRadius:"5px", padding:"10px 12px", border:"1px solid #131828", marginBottom:"12px" }}>
                    {[
                      { label:"ENTRY", val:`$${(pendingDecision.order.entry_price||0).toLocaleString()}`, color:"#00d4ff" },
                      { label:"TP", val:`$${(pendingDecision.order.take_profit||0).toLocaleString()}`, color:"#00ff88" },
                      { label:"SL", val:`$${(pendingDecision.order.stop_loss||0).toLocaleString()}`, color:"#ff3366" },
                      { label:"SIZE", val:`${pendingDecision.order.size_percent||0}%`, color:"#8892a4" },
                    ].map(r => (
                      <div key={r.label} className="row" style={{ fontSize:"11px" }}>
                        <span style={{ color:"#2d3748" }}>{r.label}</span>
                        <span style={{ color:r.color, fontWeight:"700" }}>{r.val}</span>
                      </div>
                    ))}
                  </div>
                )}
                <div style={{ display:"flex", gap:"10px" }}>
                  <button className="btn btn-g" onClick={handleApprovePending} style={{ flex:1 }}>APPROVE</button>
                  <button className="btn btn-r" onClick={handleRejectPending} style={{ flex:1 }}>REJECT</button>
                </div>
              </div>
            )}

            {decision ? (
              <div className="fadein">
                <div style={{ display:"flex", alignItems:"center", gap:"10px", marginBottom:"12px" }}>
                  <span className="tag" style={{
                    background:{buy:"#00ff8820",sell:"#ff336620",wait:"#ffffff10",close_all:"#ff990020"}[decision.action]||"#ffffff10",
                    color:{buy:"#00ff88",sell:"#ff3366",wait:"#64748b",close_all:"#ff9900"}[decision.action]||"#64748b",
                    fontSize:"12px", padding:"4px 12px"
                  }}>
                    {{buy:"\u25B2 BUY",sell:"\u25BC SELL",wait:"\u23F8 WAIT",close_all:"\u26A1 CLOSE ALL"}[decision.action]||decision.action?.toUpperCase()}
                    {decision.symbol && decision.action !== "wait" && <span style={{ marginLeft:"4px" }}>{decision.symbol}</span>}
                  </span>
                  {decision.confidence != null && (
                    <div style={{ flex:1 }}>
                      <div style={{ height:"3px", background:"#131828", borderRadius:"2px", overflow:"hidden" }}>
                        <div style={{ height:"100%", width:`${decision.confidence*100}%`, background: decision.confidence>0.7?"#00ff88":decision.confidence>0.5?"#ff9900":"#ff3366", transition:"width 0.6s", borderRadius:"2px" }} />
                      </div>
                      <div style={{ fontSize:"10px", color:"#4a5568", marginTop:"2px" }}>{(decision.confidence*100).toFixed(0)}% confidence</div>
                    </div>
                  )}
                </div>
                <div style={{ fontSize:"11px", color:"#8892a4", lineHeight:"1.8", borderLeft:"2px solid #8b5cf633", paddingLeft:"10px", marginBottom:"14px", fontStyle:"italic" }}>
                  &ldquo;{decision.reasoning}&rdquo;
                </div>
                {lastAiBlockReason && (
                  <div style={{ fontSize:"10px", color:"#ff9900", lineHeight:"1.5", background:"#ff990008", border:"1px solid #ff990033", borderRadius:"5px", padding:"8px 10px", marginBottom:"14px" }}>
                    ⚠ {lastAiBlockReason}
                  </div>
                )}
                {decision.order && (
                  <div style={{ background:"#06060f", borderRadius:"5px", padding:"10px 12px", border:"1px solid #131828" }}>
                    {[
                      { label:"ENTRY",       val:`$${(decision.order.entry_price||0).toLocaleString()}`,  color:"#00d4ff" },
                      { label:"TAKE PROFIT", val:`$${(decision.order.take_profit||0).toLocaleString()}`,  color:"#00ff88" },
                      { label:"STOP LOSS",   val:`$${(decision.order.stop_loss||0).toLocaleString()}`,    color:"#ff3366" },
                      { label:"SIZE",        val:`${decision.order.size_percent||0}% of balance`,         color:"#8892a4" },
                    ].map(r => (
                      <div key={r.label} className="row" style={{ fontSize:"11px" }}>
                        <span style={{ color:"#2d3748" }}>{r.label}</span>
                        <span style={{ color:r.color, fontWeight:"700" }}>{r.val}</span>
                      </div>
                    ))}
                  </div>
                )}
                <div style={{ fontSize:"9px", color:"#1e2535", marginTop:"10px", textAlign:"right" }}>LAST CALL: {lastCall}</div>
              </div>
            ) : (
              <div style={{ textAlign:"center", padding:"20px 0", color:"#1e2535", fontSize:"11px", lineHeight:"2.2" }}>
                {botOn
                  ? <span className="blink" style={{ color:"#8b5cf6" }}>First analysis in {countdown}s...</span>
                  : <span>Press <span style={{ color:"#00ff88" }}>{"\u25B6"} START</span> or <span style={{ color:"#8b5cf6" }}>{"\u2B21"} ASK AI</span></span>
                }
              </div>
            )}
          </div>

          {/* Regime + Fear/Greed */}
          <div className="card">
            <div style={{ fontSize:"9px", color:"#2d3748", letterSpacing:"2px", marginBottom:"10px" }}>MARKET REGIME</div>
            <div style={{ padding:"12px", borderRadius:"5px", background:`${condColor}11`, border:`1px solid ${condColor}22`, textAlign:"center", marginBottom:"12px" }}>
              <span style={{ fontFamily:"'Chakra Petch',sans-serif", color:condColor, fontWeight:"700", fontSize:"13px", letterSpacing:"2px" }}>{condIcon} {condLabel}</span>
            </div>
            <div style={{ display:"flex", justifyContent:"space-between", alignItems:"center" }}>
              <span style={{ fontSize:"10px", color:"#2d3748" }}>FEAR & GREED</span>
              <div style={{ display:"flex", alignItems:"center", gap:"8px" }}>
                <div style={{ width:"60px", height:"3px", background:"#131828", borderRadius:"2px", overflow:"hidden" }} role="progressbar" aria-valuenow={fearGreed.value} aria-valuemin={0} aria-valuemax={100} aria-label="Fear and Greed Index">
                  <div style={{ height:"100%", width:`${fearGreed.value}%`, background:`linear-gradient(to right, #ff3366, #ff9900, #00ff88)`, borderRadius:"2px" }} />
                </div>
                <span style={{ fontSize:"10px", fontWeight:"700", color:fgColor }}>{fearGreed.value} {fearGreed.label}</span>
              </div>
            </div>
          </div>

          {/* AgentKit Wallet */}
          {isLiveMode && (
            <div className="card" style={{ border: agentKit.agentkit_ready ? "1px solid #00d4ff22" : "1px solid #131828", boxShadow: agentKit.agentkit_ready ? "0 0 12px #00d4ff10" : "none" }}>
              <div style={{ display:"flex", alignItems:"center", justifyContent:"space-between", marginBottom:"12px" }}>
                <div style={{ display:"flex", alignItems:"center", gap:"8px" }}>
                  <span className="dot" style={{ background: agentKit.agentkit_ready ? "#00d4ff" : "#2d3748", boxShadow: agentKit.agentkit_ready ? "0 0 8px #00d4ff" : "none" }} />
                  <span style={{ fontFamily:"'Chakra Petch',sans-serif", fontSize:"11px", color:"#00d4ff", fontWeight:"700", letterSpacing:"2px" }}>AGENTKIT WALLET</span>
                </div>
                <span style={{ fontSize:"9px", color: agentKit.agentkit_ready ? "#00d4ff" : "#ff3366" }}>
                  {agentKit.agentkit_ready ? "ON-CHAIN" : "OFFLINE"}
                </span>
              </div>
              {agentKit.agentkit_ready ? (
                <div>
                  <div className="row" style={{ fontSize:"11px" }}>
                    <span style={{ color:"#2d3748" }}>ADDRESS</span>
                    <span style={{ color:"#00d4ff", fontFamily:"monospace", fontSize:"10px" }}>
                      {agentKit.wallet_address ? `${agentKit.wallet_address.slice(0,6)}...${agentKit.wallet_address.slice(-4)}` : "--"}
                    </span>
                  </div>
                  <div className="row" style={{ fontSize:"11px" }}>
                    <span style={{ color:"#2d3748" }}>NETWORK</span>
                    <span style={{ color:"#e2e8f0", fontWeight:"700" }}>{agentKit.network || "--"}</span>
                  </div>
                  {agentKit.eth_balance && (
                    <div className="row" style={{ fontSize:"11px" }}>
                      <span style={{ color:"#2d3748" }}>ETH</span>
                      <span style={{ color:"#e2e8f0", fontWeight:"700" }}>{agentKit.eth_balance}</span>
                    </div>
                  )}
                  {agentKit.usdc_balance && (
                    <div className="row" style={{ fontSize:"11px" }}>
                      <span style={{ color:"#2d3748" }}>USDC</span>
                      <span style={{ color:"#00ff88", fontWeight:"700" }}>{agentKit.usdc_balance}</span>
                    </div>
                  )}
                </div>
              ) : (
                <div style={{ fontSize:"10px", color:"#2d3748", textAlign:"center", padding:"6px 0" }}>
                  {agentKit.error ? `${agentKit.error}` : "Set CDP keys in .env for on-chain trading"}
                </div>
              )}
            </div>
          )}
        </div>

        {/* ═══ CENTER ═══ */}
        <div className="col">

          {/* Indicators */}
          <div className="card">
            <div style={{ fontSize:"9px", color:"#2d3748", letterSpacing:"2px", marginBottom:"10px" }}>LIVE INDICATORS</div>
            <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:"0 20px" }}>
              {[
                { label:"EMA 9",    val: indic.ema9    ? `$${indic.ema9.toLocaleString()}`    : "warming\u2026", color:"#00ff88" },
                { label:"EMA 21",   val: indic.ema21   ? `$${indic.ema21.toLocaleString()}`   : "warming\u2026", color:"#00d4ff" },
                { label:"RSI 14",   val: indic.ema9    ? `${indic.rsi}${indic.rsi>70?" OB":indic.rsi<30?" OS":""}` : "-", color: indic.rsi>70?"#ff3366":indic.rsi<30?"#00ff88":"#e2e8f0" },
                { label:"ATR 14",   val: indic.ema9    ? `$${indic.atr}` : "-",                 color: indic.atr>500?"#ff9900":"#e2e8f0" },
                { label:"BB UPPER", val: indic.bb_upper  ? `$${indic.bb_upper.toLocaleString()}`  : "-", color:"#ff3366" },
                { label:"BB MID",   val: indic.bb_middle ? `$${indic.bb_middle.toLocaleString()}` : "-", color:"#64748b" },
                { label:"BB LOWER", val: indic.bb_lower  ? `$${indic.bb_lower.toLocaleString()}`  : "-", color:"#00ff88" },
                { label:"BB WIDTH", val: indic.bb_width  ? `${indic.bb_width}%` : "-", color:"#ff9900" },
                { label:"VWAP",     val: indic.vwap      ? `$${indic.vwap.toLocaleString()}`     : "-", color:"#8b5cf6" },
                { label:"MACD",     val: indic.macd != null ? `${indic.macd}` : "-", color: (indic.macd||0) >= 0 ? "#00ff88" : "#ff3366" },
                { label:"MACD SIG", val: indic.macd_signal != null ? `${indic.macd_signal}` : "-", color: "#ff9900" },
                { label:"MACD HIST",val: indic.macd_histogram != null ? `${indic.macd_histogram}` : "-", color: (indic.macd_histogram||0) >= 0 ? "#00ff88" : "#ff3366" },
                { label:"MOMENTUM", val: indic.momentum != null ? `${indic.momentum}%` : "-", color: (indic.momentum||0) >= 0 ? "#00ff88" : "#ff3366" },
              ].map(ind => (
                <div key={ind.label} className="row" style={{ fontSize:"11px" }}>
                  <span style={{ color:"#2d3748" }}>{ind.label}</span>
                  <span style={{ color:ind.color, fontWeight:"700" }}>{ind.val}</span>
                </div>
              ))}
            </div>
            <div style={{ marginTop:"10px", fontSize:"9px", color:"#1e2535", textAlign:"center" }}>
              {history.length < 9 ? `Building: ${history.length}/9 candles` : `${history.length} candles loaded`}
            </div>
          </div>

          {/* Risk Monitor */}
          <div className="card">
            <div style={{ fontSize:"9px", color:"#2d3748", letterSpacing:"2px", marginBottom:"10px" }}>RISK MONITOR</div>
            {[
              { label:"DAILY LOSS",  val:`${dailyLossPct.toFixed(1)}%`, limit:"5% limit",      pct:dailyLossPct/5*100,                                 color:"#ff3366" },
              { label:"GROWTH",      val:`${((account.balance/startBal-1)*100).toFixed(1)}%`, limit:`from $${startBal}`, pct:Math.min(100,Math.max(0,(account.balance/startBal-1)*100)), color:"#00ff88" },
            ].map(r => (
              <div key={r.label} style={{ marginBottom:"12px" }}>
                <div style={{ display:"flex", justifyContent:"space-between", fontSize:"10px", marginBottom:"5px" }}>
                  <span style={{ color:"#4a5568" }}>{r.label}</span>
                  <span style={{ color:r.pct>80?"#ff3366":r.color, fontWeight:"700" }}>{r.val} <span style={{ color:"#2d3748" }}>{r.limit}</span></span>
                </div>
                <div style={{ height:"3px", background:"#131828", borderRadius:"2px", overflow:"hidden" }}>
                  <div style={{ height:"100%", width:`${Math.max(0,Math.min(100,r.pct))}%`, background:r.pct>80?"#ff3366":r.color, transition:"width 0.5s", borderRadius:"2px" }} />
                </div>
              </div>
            ))}
            <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:"8px", marginTop:"6px" }}>
              {[
                { label:"TRADES",   val:trades.length,                                                                  color:"#e2e8f0" },
                { label:"WIN RATE", val:`${winRate}%`,                                                                  color:winRate>=50?"#00ff88":"#ff3366" },
                { label:"BEST",     val:trades.length?`+$${Math.max(...trades.map(t=>t.pnl)).toFixed(2)}`:"--",       color:"#00ff88" },
                { label:"WORST",    val:trades.length?`$${Math.min(...trades.map(t=>t.pnl)).toFixed(2)}`:"--",        color:"#ff3366" },
              ].map(s => (
                <div key={s.label} style={{ background:"#06060f", padding:"8px", borderRadius:"5px" }}>
                  <div style={{ fontSize:"9px", color:"#2d3748", marginBottom:"2px" }}>{s.label}</div>
                  <div style={{ fontFamily:"'Chakra Petch',sans-serif", fontSize:"13px", fontWeight:"700", color:s.color }}>{s.val}</div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* ═══ RIGHT ═══ */}
        <div className="col">

          {/* Trade History (recent) */}
          <div className="card" style={{ flex:"1 1 0", display:"flex", flexDirection:"column", overflow:"hidden", minHeight:"180px" }}>
            <div style={{ display:"flex", justifyContent:"space-between", alignItems:"center", marginBottom:"10px" }}>
              <span style={{ fontSize:"9px", color:"#2d3748", letterSpacing:"2px" }}>RECENT TRADES</span>
              <div style={{ display:"flex", gap:"6px" }}>
                {trades.length > 0 && (
                  <button className="btn btn-d" onClick={() => exportTrades()} style={{ padding:"2px 6px", fontSize:"9px" }} aria-label="Export trade history as CSV">{"\u21E9"} CSV</button>
                )}
                {connected && (
                  <button className="btn btn-d" onClick={() => { setShowHistory(true); fetchHistory(0); }} style={{ padding:"2px 6px", fontSize:"9px", color:"#8b5cf6", borderColor:"#8b5cf633" }} aria-label="View full trade history">ALL HISTORY</button>
                )}
              </div>
            </div>
            <div style={{ flex:"1 1 0", overflowY:"auto" }}>
              {trades.length === 0
                ? <div style={{ textAlign:"center", padding:"20px", color:"#1e2535", fontSize:"11px" }}>No trades yet — start the bot</div>
                : trades.map(tr => (
                  <div key={tr.id} className="trow fadein" style={{ fontSize:"11px" }}>
                    <div>
                      <span className="tag" style={{ background:tr.side==="buy"?"#00ff8818":"#ff336618", color:tr.side==="buy"?"#00ff88":"#ff3366", marginRight:"5px" }}>
                        {tr.side==="buy"?"\u25B2":"\u25BC"} {tr.side?.toUpperCase()}
                      </span>
                      <span style={{ color:"#8b5cf6", fontSize:"9px", fontWeight:"700", marginRight:"4px" }}>{tr.symbol || "BTC"}</span>
                      {tradeTypeBadge(tr)}
                      <span style={{ color:"#1e2535", fontSize:"9px", marginLeft:"4px" }}>{tr.ts}</span>
                    </div>
                    <div style={{ textAlign:"right" }}>
                      <div style={{ fontWeight:"700", color:tr.win?"#00ff88":"#ff3366" }}>{tr.pnl>=0?"+":""}${(+tr.pnl).toFixed(2)}</div>
                      <div style={{ fontSize:"9px", color:"#2d3748" }}>{tr.reason}</div>
                    </div>
                  </div>
                ))
              }
            </div>
          </div>

          {/* Activity Log */}
          <div className="card" style={{ flex:"1 1 0", display:"flex", flexDirection:"column", overflow:"hidden", minHeight:"180px" }}>
            <div style={{ display:"flex", alignItems:"center", gap:"8px", marginBottom:"10px" }}>
              <span style={{ fontSize:"9px", color:"#2d3748", letterSpacing:"2px" }}>ACTIVITY LOG</span>
              {(botOn||connected) && <span className="blink" style={{ fontSize:"9px", color:"#00ff88" }}>LIVE</span>}
              {demoMode && <span style={{ fontSize:"9px", color:"#ff9900" }}>DEMO</span>}
            </div>
            <div style={{ flex:"1 1 0", overflowY:"auto" }} role="log" aria-label="Activity log">
              {logs.map((e) => (
                <div key={e.id} className="logrow" style={{ fontSize:"10px", lineHeight:"1.7" }}>
                  <span style={{ color:"#1e2535", marginRight:"5px" }}>{e.ts}</span>
                  <span style={{ color:{success:"#00ff88",error:"#ff3366",warning:"#ff9900",claude:"#8b5cf6",sell:"#ff6688",dim:"#2d3748"}[e.type]||"#4a5568" }}>
                    <span aria-hidden="true">{({success:"+",error:"\u2715",warning:"!",claude:"\u25C6",sell:"\u25BC",dim:"\u00B7"})[e.type]||"\u203A"} </span>
                    {e.msg}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* ══ ANALYTICS ROW (equity + analytics + memory) ══ */}
      <AnalyticsSection connected={connected} log={log} lossToast={lossToast} />

      {/* ══ FULL TRADE HISTORY OVERLAY ══ */}
      {showHistory && (
        <div style={{ position:"fixed", inset:0, background:"rgba(6,6,15,0.95)", zIndex:9998, display:"flex", flexDirection:"column", animation:"fadein 0.2s ease" }}>
          {/* Header */}
          <div style={{ padding:"20px 24px 0", flexShrink:0 }}>
            <div style={{ display:"flex", justifyContent:"space-between", alignItems:"center", marginBottom:"16px" }}>
              <div style={{ display:"flex", alignItems:"center", gap:"12px" }}>
                <span style={{ fontFamily:"'Chakra Petch',sans-serif", fontSize:"16px", fontWeight:"700", color:"#fff", letterSpacing:"3px" }}>TRADE HISTORY</span>
                <span style={{ fontSize:"10px", color:"#4a5568" }}>{historyTotal} total trades in database</span>
              </div>
              <div style={{ display:"flex", gap:"8px" }}>
                {historyTrades.length > 0 && (
                  <button className="btn btn-d" onClick={() => exportTrades(historyTrades)} style={{ fontSize:"9px" }}>{"\u21E9"} EXPORT CSV</button>
                )}
                <button className="btn btn-d" onClick={() => setShowHistory(false)} style={{ fontSize:"12px", color:"#ff3366", borderColor:"#ff336633", padding:"6px 14px" }}>{"\u2715"} CLOSE</button>
              </div>
            </div>

            {/* Filters */}
            <div style={{ display:"flex", gap:"10px", flexWrap:"wrap", alignItems:"flex-end", marginBottom:"14px" }}>
              <div>
                <div style={{ fontSize:"8px", color:"#2d3748", letterSpacing:"1px", marginBottom:"3px" }}>FROM</div>
                <input type="date" value={historyFilters.date_from} onChange={e => applyHistoryFilter("date_from", e.target.value)}
                  style={{ fontFamily:"'Space Mono',monospace", fontSize:"10px", padding:"6px 10px", borderRadius:"4px", border:"1px solid #1e2535", background:"#0a0a18", color:"#b8c8d8", outline:"none" }} />
              </div>
              <div>
                <div style={{ fontSize:"8px", color:"#2d3748", letterSpacing:"1px", marginBottom:"3px" }}>TO</div>
                <input type="date" value={historyFilters.date_to} onChange={e => applyHistoryFilter("date_to", e.target.value)}
                  style={{ fontFamily:"'Space Mono',monospace", fontSize:"10px", padding:"6px 10px", borderRadius:"4px", border:"1px solid #1e2535", background:"#0a0a18", color:"#b8c8d8", outline:"none" }} />
              </div>
              <div>
                <div style={{ fontSize:"8px", color:"#2d3748", letterSpacing:"1px", marginBottom:"3px" }}>COIN</div>
                <select value={historyFilters.symbol} onChange={e => applyHistoryFilter("symbol", e.target.value)}
                  style={{ fontFamily:"'Space Mono',monospace", fontSize:"10px", padding:"6px 10px", borderRadius:"4px", border:"1px solid #1e2535", background:"#0a0a18", color:"#b8c8d8", outline:"none", appearance:"none", minWidth:"80px" }}>
                  <option value="">ALL</option>
                  {activeCoins.map(c => <option key={c} value={c}>{c}</option>)}
                </select>
              </div>
              <div>
                <div style={{ fontSize:"8px", color:"#2d3748", letterSpacing:"1px", marginBottom:"3px" }}>SIDE</div>
                <select value={historyFilters.side} onChange={e => applyHistoryFilter("side", e.target.value)}
                  style={{ fontFamily:"'Space Mono',monospace", fontSize:"10px", padding:"6px 10px", borderRadius:"4px", border:"1px solid #1e2535", background:"#0a0a18", color:"#b8c8d8", outline:"none", appearance:"none", minWidth:"80px" }}>
                  <option value="">ALL</option>
                  <option value="buy">BUY</option>
                  <option value="sell">SELL</option>
                </select>
              </div>
              <div>
                <div style={{ fontSize:"8px", color:"#2d3748", letterSpacing:"1px", marginBottom:"3px" }}>RESULT</div>
                <select value={historyFilters.result} onChange={e => applyHistoryFilter("result", e.target.value)}
                  style={{ fontFamily:"'Space Mono',monospace", fontSize:"10px", padding:"6px 10px", borderRadius:"4px", border:"1px solid #1e2535", background:"#0a0a18", color:"#b8c8d8", outline:"none", appearance:"none", minWidth:"80px" }}>
                  <option value="">ALL</option>
                  <option value="win">WINS</option>
                  <option value="loss">LOSSES</option>
                </select>
              </div>
              <div>
                <div style={{ fontSize:"8px", color:"#2d3748", letterSpacing:"1px", marginBottom:"3px" }}>TYPE</div>
                <select value={historyFilters.product_type} onChange={e => applyHistoryFilter("product_type", e.target.value)}
                  style={{ fontFamily:"'Space Mono',monospace", fontSize:"10px", padding:"6px 10px", borderRadius:"4px", border:"1px solid #1e2535", background:"#0a0a18", color:"#b8c8d8", outline:"none", appearance:"none", minWidth:"90px" }}>
                  <option value="">ALL</option>
                  <option value="spot">SPOT</option>
                  <option value="futures">FUTURES</option>
                  <option value="onchain">ON-CHAIN</option>
                </select>
              </div>
              {(historyFilters.date_from || historyFilters.date_to || historyFilters.symbol || historyFilters.side || historyFilters.result || historyFilters.product_type) && (
                <button className="btn btn-d" onClick={clearHistoryFilters} style={{ fontSize:"9px", color:"#ff9900", borderColor:"#ff990033", padding:"6px 12px", alignSelf:"flex-end" }}>CLEAR FILTERS</button>
              )}
              <button className="btn btn-d" onClick={() => fetchHistory(historyPage)} style={{ fontSize:"9px", color:"#00d4ff", borderColor:"#00d4ff33", padding:"6px 12px", alignSelf:"flex-end" }}>{"\u21BB"} REFRESH</button>
            </div>

            {/* Summary stats */}
            <div style={{ display:"flex", gap:"16px", marginBottom:"14px", flexWrap:"wrap" }}>
              {[
                { label:"SHOWING", val:`${historyTrades.length} of ${historyTotal}`, color:"#e2e8f0" },
                { label:"WINS", val:historyStats.wins, color:"#00ff88" },
                { label:"LOSSES", val:historyStats.losses, color:"#ff3366" },
                { label:"WIN RATE", val:`${historyStats.win_rate}%`, color:historyStats.win_rate >= 50 ? "#00ff88" : "#ff3366" },
                { label:"NET P&L", val:`${historyStats.total_pnl >= 0 ? "+" : ""}$${historyStats.total_pnl.toFixed(2)}`, color:historyStats.total_pnl >= 0 ? "#00ff88" : "#ff3366" },
              ].map(s => (
                <div key={s.label} style={{ background:"#0a0a18", border:"1px solid #131828", borderRadius:"5px", padding:"8px 14px" }}>
                  <div style={{ fontSize:"8px", color:"#2d3748", letterSpacing:"1px" }}>{s.label}</div>
                  <div style={{ fontFamily:"'Chakra Petch',sans-serif", fontSize:"14px", fontWeight:"700", color:s.color }}>{s.val}</div>
                </div>
              ))}
            </div>

            {/* Table header */}
            <div style={{ display:"grid", gridTemplateColumns:"140px 55px 55px 55px 90px 90px 80px 70px 1fr", gap:"8px", padding:"8px 12px", background:"#0a0a18", borderRadius:"5px 5px 0 0", border:"1px solid #131828", borderBottom:"none" }}>
              {["DATE / TIME", "COIN", "SIDE", "TYPE", "ENTRY", "EXIT", "P&L", "RESULT", "REASON"].map(h => (
                <span key={h} style={{ fontSize:"8px", color:"#2d3748", letterSpacing:"1.5px", fontWeight:"700" }}>{h}</span>
              ))}
            </div>
          </div>

          {/* Trade rows */}
          <div style={{ flex:1, overflowY:"auto", padding:"0 24px", minHeight:0 }}>
            <div style={{ border:"1px solid #131828", borderTop:"none", borderRadius:"0 0 5px 5px", background:"#0a0a18" }}>
              {historyLoading ? (
                <div style={{ textAlign:"center", padding:"40px", color:"#4a5568" }}>
                  <span className="blink">Loading trades...</span>
                </div>
              ) : historyTrades.length === 0 ? (
                <div style={{ textAlign:"center", padding:"40px", color:"#1e2535", fontSize:"11px" }}>
                  No trades found{(historyFilters.date_from || historyFilters.date_to || historyFilters.symbol || historyFilters.side || historyFilters.result) ? " matching filters" : ""}
                </div>
              ) : (
                historyTrades.map(tr => (
                  <div key={tr.id} style={{ display:"grid", gridTemplateColumns:"140px 55px 55px 55px 90px 90px 80px 70px 1fr", gap:"8px", padding:"8px 12px", borderBottom:"1px solid #0d0d1c", fontSize:"11px", transition:"background 0.1s" }}
                    onMouseEnter={e => e.currentTarget.style.background="#0d0d1c"}
                    onMouseLeave={e => e.currentTarget.style.background="transparent"}>
                    <span style={{ color:"#4a5568", fontSize:"10px" }}>
                      {tr.created_at || tr.ts}
                    </span>
                    <span style={{ color:"#8b5cf6", fontWeight:"700" }}>{tr.symbol || "BTC"}</span>
                    <span>
                      <span className="tag" style={{ background:tr.side==="buy"?"#00ff8818":"#ff336618", color:tr.side==="buy"?"#00ff88":"#ff3366", padding:"2px 6px" }}>
                        {tr.side==="buy"?"\u25B2":"\u25BC"} {tr.side?.toUpperCase()}
                      </span>
                    </span>
                    <span>{tradeTypeBadge(tr)}</span>
                    <span style={{ color:"#e2e8f0" }}>${(+tr.entry).toLocaleString()}</span>
                    <span style={{ color:"#e2e8f0" }}>${(+tr.exit).toLocaleString()}</span>
                    <span style={{ fontWeight:"700", color:tr.win?"#00ff88":"#ff3366" }}>{tr.pnl>=0?"+":""}${(+tr.pnl).toFixed(2)}</span>
                    <span>
                      <span className="tag" style={{ background:tr.win?"#00ff8818":"#ff336618", color:tr.win?"#00ff88":"#ff3366", padding:"2px 6px" }}>
                        {tr.win ? "WIN" : "LOSS"}
                      </span>
                    </span>
                    <span style={{ color:"#2d3748", fontSize:"10px", overflow:"hidden", textOverflow:"ellipsis", whiteSpace:"nowrap" }}>{tr.reason}</span>
                  </div>
                ))
              )}
            </div>
          </div>

          {/* Pagination */}
          {historyTotal > historyLimit && (
            <div style={{ padding:"12px 24px", flexShrink:0, display:"flex", justifyContent:"center", alignItems:"center", gap:"12px" }}>
              <button className="btn btn-d" disabled={historyPage === 0} onClick={() => fetchHistory(historyPage - 1)}
                style={{ padding:"6px 14px", fontSize:"10px" }}>{"\u25C0"} PREV</button>
              <span style={{ fontSize:"10px", color:"#4a5568" }}>
                Page {historyPage + 1} of {Math.ceil(historyTotal / historyLimit)}
              </span>
              <button className="btn btn-d" disabled={(historyPage + 1) * historyLimit >= historyTotal} onClick={() => fetchHistory(historyPage + 1)}
                style={{ padding:"6px 14px", fontSize:"10px" }}>NEXT {"\u25B6"}</button>
            </div>
          )}
        </div>
      )}

      {/* ══ CONFIRM DIALOG ══ */}
      {confirmAction && (
        <div className="confirm-overlay" onClick={() => setConfirmAction(null)} role="dialog" aria-modal="true" aria-label="Confirmation">
          <div className="confirm-box" onClick={e => e.stopPropagation()}>
            <div style={{ fontFamily:"'Chakra Petch',sans-serif", fontSize:"13px", fontWeight:"700", color:"#ff9900", letterSpacing:"1px", marginBottom:"16px" }}>CONFIRM ACTION</div>
            <div style={{ fontSize:"11px", color:"#b8c8d8", lineHeight:"1.9", marginBottom:"22px" }}>{confirmAction.label}</div>
            <div style={{ display:"flex", gap:"12px", justifyContent:"center" }}>
              <button className="btn btn-r" onClick={confirmYes} style={{ minWidth:"90px" }}>YES</button>
              <button className="btn btn-d" onClick={() => setConfirmAction(null)} style={{ minWidth:"90px", color:"#b8c8d8" }}>CANCEL</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ─── Analytics Section (Equity Curve + Trade Analytics + Memory + Backtest) ────
function AnalyticsSection({ connected, log, lossToast }) {
  const [activeTab, setActiveTab] = useState("equity");
  const [equityData, setEquityData] = useState(null);
  const [analyticsData, setAnalyticsData] = useState(null);
  const [memoryData, setMemoryData] = useState(null);
  const [calibrationData, setCalibrationData] = useState(null);
  const [backtestResult, setBacktestResult] = useState(null);
  const [backtestLoading, setBacktestLoading] = useState(false);
  const [btParams, setBtParams] = useState({ symbol:"BTC", days:30, tp:2.5, sl:1.0, confluence:5, rr:1.8 });
  const [loading, setLoading] = useState(false);

  const backendBase = BACKEND_BASE || `${window.location.protocol}//${window.location.hostname}:8000`;

  const fetchData = useCallback(async (tab) => {
    if (!connected) return;
    setLoading(true);
    try {
      if (tab === "equity") {
        const r = await fetch(`${backendBase}/equity`);
        if (r.ok) setEquityData(await r.json());
      } else if (tab === "analytics") {
        const r = await fetch(`${backendBase}/memory/analysis`);
        if (r.ok) setAnalyticsData(await r.json());
      } else if (tab === "memory") {
        const [rulesR, patternsR] = await Promise.all([
          fetch(`${backendBase}/memory/rules`),
          fetch(`${backendBase}/memory/patterns`),
        ]);
        const rules = rulesR.ok ? await rulesR.json() : { rules: [] };
        const patterns = patternsR.ok ? await patternsR.json() : { patterns: [] };
        setMemoryData({ ...rules, ...patterns });
      } else if (tab === "calibration") {
        const r = await fetch(`${backendBase}/memory/calibration`);
        if (r.ok) setCalibrationData(await r.json());
      }
    } catch (e) {
      log?.(`Analytics fetch error: ${e.message}`, "error");
    } finally {
      setLoading(false);
    }
  }, [connected, backendBase, log]);

  useEffect(() => { fetchData(activeTab); }, [activeTab, fetchData]);

  const runBacktest = async () => {
    setBacktestLoading(true);
    try {
      const params = new URLSearchParams({
        symbol: btParams.symbol, days: btParams.days,
        tp_atr_mult: btParams.tp, sl_atr_mult: btParams.sl,
        min_confluence: btParams.confluence, min_rr: btParams.rr,
      });
      const r = await fetch(`${backendBase}/backtest?${params}`, { method: "POST" });
      if (r.ok) {
        const data = await r.json();
        setBacktestResult(data);
        log?.(`Backtest: ${data.total_trades} trades, ${data.return_pct >= 0 ? "+" : ""}${data.return_pct}% return`, "info");
      }
    } catch (e) {
      log?.(`Backtest error: ${e.message}`, "error");
    } finally {
      setBacktestLoading(false);
    }
  };

  const tabs = [
    { id:"equity", label:"EQUITY CURVE" },
    { id:"analytics", label:"TRADE ANALYTICS" },
    { id:"memory", label:"BRAIN / MEMORY" },
    { id:"calibration", label:"CONFIDENCE" },
    { id:"backtest", label:"BACKTEST" },
  ];

  if (!connected) return null;

  return (
    <div style={{ marginTop:"16px" }}>
      <div style={{ display:"flex", gap:"6px", marginBottom:"12px", overflowX:"auto" }}>
        {tabs.map(t => (
          <button key={t.id} onClick={() => setActiveTab(t.id)}
            className="btn" style={{
              padding:"6px 14px", fontSize:"9px", letterSpacing:"1.5px",
              background: activeTab === t.id ? "#8b5cf611" : "transparent",
              color: activeTab === t.id ? "#8b5cf6" : "#4a5568",
              border: `1px solid ${activeTab === t.id ? "#8b5cf633" : "#131828"}`,
            }}>{t.label}</button>
        ))}
        <button className="btn btn-d" onClick={() => fetchData(activeTab)} style={{ marginLeft:"auto", padding:"4px 10px", fontSize:"9px" }}>{"\u21BB"}</button>
      </div>

      <div className="card" style={{ minHeight:"200px" }}>
        {loading && <div style={{ textAlign:"center", padding:"40px", color:"#4a5568" }}><span className="blink">Loading...</span></div>}

        {/* ── EQUITY CURVE ── */}
        {activeTab === "equity" && !loading && equityData && (
          <div>
            <div style={{ fontSize:"9px", color:"#2d3748", letterSpacing:"2px", marginBottom:"12px" }}>EQUITY CURVE</div>
            {equityData.curve?.length > 0 ? (
              <div>
                <div style={{ display:"flex", gap:"16px", marginBottom:"14px", flexWrap:"wrap" }}>
                  {equityData.sessions?.slice(0, 7).map(s => (
                    <div key={s.date} style={{ background:"#06060f", borderRadius:"5px", padding:"8px 12px", minWidth:"100px" }}>
                      <div style={{ fontSize:"8px", color:"#2d3748" }}>{s.date}</div>
                      <div style={{ fontSize:"11px", fontWeight:"700", color: s.total_pnl >= 0 ? "#00ff88" : "#ff3366" }}>
                        {s.total_pnl >= 0 ? "+" : ""}${s.total_pnl?.toFixed(2)}
                      </div>
                      <div style={{ fontSize:"8px", color:"#4a5568" }}>{s.trades_taken} trades | {s.wins}W/{s.losses}L</div>
                    </div>
                  ))}
                </div>
                <div style={{ height:"120px", display:"flex", alignItems:"flex-end", gap:"1px", padding:"0 4px" }}>
                  {(() => {
                    const pts = equityData.curve;
                    const balances = pts.map(p => p.balance);
                    const mn = Math.min(...balances);
                    const mx = Math.max(...balances);
                    const range = mx - mn || 1;
                    const step = Math.max(1, Math.floor(pts.length / 80));
                    const sampled = pts.filter((_, i) => i % step === 0 || i === pts.length - 1);
                    return sampled.map((p, i) => {
                      const h = Math.max(2, ((p.balance - mn) / range) * 110);
                      const isUp = i > 0 ? p.balance >= sampled[i-1].balance : true;
                      return <div key={i} title={`${p.ts}: $${p.balance.toFixed(2)}`} style={{ flex:1, minWidth:"2px", maxWidth:"8px", height:`${h}px`, background: isUp ? "#00ff8888" : "#ff336688", borderRadius:"1px 1px 0 0", transition:"height 0.3s" }} />;
                    });
                  })()}
                </div>
                <div style={{ display:"flex", justifyContent:"space-between", fontSize:"9px", color:"#2d3748", marginTop:"4px" }}>
                  <span>{equityData.curve[0]?.ts?.split(" ")[0]}</span>
                  <span>{equityData.curve[equityData.curve.length-1]?.ts?.split(" ")[0]}</span>
                </div>
              </div>
            ) : (
              <div style={{ textAlign:"center", padding:"30px", color:"#1e2535", fontSize:"11px" }}>
                No snapshots yet — run the bot for a few hours to build the equity curve
              </div>
            )}
          </div>
        )}

        {/* ── TRADE ANALYTICS ── */}
        {activeTab === "analytics" && !loading && analyticsData && (
          <div>
            <div style={{ fontSize:"9px", color:"#2d3748", letterSpacing:"2px", marginBottom:"12px" }}>TRADE ANALYTICS</div>
            <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:"14px" }}>
              {/* Regime performance */}
              <div>
                <div style={{ fontSize:"9px", color:"#4a5568", letterSpacing:"1px", marginBottom:"8px" }}>BY REGIME</div>
                {Object.entries(analyticsData.regime || {}).map(([regime, data]) => (
                  <div key={regime} className="row" style={{ fontSize:"10px" }}>
                    <span style={{ color: {trending_up:"#00ff88", trending_down:"#ff3366", ranging:"#00d4ff", chaotic:"#ff9900"}[regime] || "#4a5568", fontWeight:"700", textTransform:"uppercase" }}>{regime}</span>
                    <span>
                      <span style={{ color: data.win_rate >= 50 ? "#00ff88" : "#ff3366", fontWeight:"700" }}>{data.win_rate}%</span>
                      <span style={{ color:"#2d3748", marginLeft:"6px" }}>{data.total} trades</span>
                      <span style={{ color: data.total_pnl >= 0 ? "#00ff88" : "#ff3366", marginLeft:"6px" }}>{data.total_pnl >= 0 ? "+" : ""}${data.total_pnl}</span>
                    </span>
                  </div>
                ))}
              </div>
              {/* Hourly performance */}
              <div>
                <div style={{ fontSize:"9px", color:"#4a5568", letterSpacing:"1px", marginBottom:"8px" }}>BEST HOURS (UTC)</div>
                {(analyticsData.hourly || []).slice(0, 6).map(h => (
                  <div key={h.hour_of_day} className="row" style={{ fontSize:"10px" }}>
                    <span style={{ color:"#e2e8f0" }}>{String(h.hour_of_day).padStart(2, "0")}:00</span>
                    <span>
                      <span style={{ color: h.win_rate >= 50 ? "#00ff88" : "#ff3366", fontWeight:"700" }}>{h.win_rate}% WR</span>
                      <span style={{ color:"#2d3748", marginLeft:"6px" }}>avg ${h.avg_pnl}</span>
                    </span>
                  </div>
                ))}
              </div>
              {/* Sizing analysis */}
              <div>
                <div style={{ fontSize:"9px", color:"#4a5568", letterSpacing:"1px", marginBottom:"8px" }}>BY SIZE</div>
                {(analyticsData.sizing || []).map(s => (
                  <div key={s.size_band} className="row" style={{ fontSize:"10px" }}>
                    <span style={{ color:"#e2e8f0" }}>{s.size_band.replace("_"," ")}</span>
                    <span>
                      <span style={{ color: s.win_rate >= 50 ? "#00ff88" : "#ff3366", fontWeight:"700" }}>{s.win_rate}% WR</span>
                      <span style={{ color:"#2d3748", marginLeft:"6px" }}>{s.total} trades</span>
                    </span>
                  </div>
                ))}
              </div>
              {/* Confidence analysis */}
              <div>
                <div style={{ fontSize:"9px", color:"#4a5568", letterSpacing:"1px", marginBottom:"8px" }}>BY CONFIDENCE</div>
                {(analyticsData.confidence || []).map(c => (
                  <div key={c.confidence_band} className="row" style={{ fontSize:"10px" }}>
                    <span style={{ color:"#8b5cf6" }}>{c.confidence_band.replace("_"," ")}</span>
                    <span>
                      <span style={{ color: c.win_rate >= 50 ? "#00ff88" : "#ff3366", fontWeight:"700" }}>{c.win_rate}% WR</span>
                      <span style={{ color:"#2d3748", marginLeft:"6px" }}>avg ${c.avg_pnl}</span>
                    </span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* ── BRAIN / MEMORY ── */}
        {activeTab === "memory" && !loading && memoryData && (
          <div>
            <div style={{ fontSize:"9px", color:"#2d3748", letterSpacing:"2px", marginBottom:"12px" }}>LEARNED RULES & PATTERNS</div>
            <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:"14px" }}>
              <div>
                <div style={{ fontSize:"9px", color:"#4a5568", letterSpacing:"1px", marginBottom:"8px" }}>
                  ACTIVE RULES ({memoryData.total_rules || 0})
                </div>
                {(memoryData.rules || []).length === 0 ? (
                  <div style={{ fontSize:"10px", color:"#1e2535", padding:"12px 0" }}>No rules learned yet — need 5+ trades</div>
                ) : (
                  (memoryData.rules || []).slice(0, 10).map(rule => (
                    <div key={rule.rule_key} style={{ background:"#06060f", borderRadius:"5px", padding:"8px 10px", marginBottom:"6px", border:"1px solid #131828" }}>
                      <div style={{ display:"flex", justifyContent:"space-between", marginBottom:"4px" }}>
                        <span className="tag" style={{ background: rule.rule_type === "avoid" ? "#ff336618" : "#00ff8818", color: rule.rule_type === "avoid" ? "#ff3366" : "#00ff88", fontSize:"8px" }}>
                          {rule.rule_type?.toUpperCase()}
                        </span>
                        <span style={{ fontSize:"8px", color:"#2d3748" }}>
                          {rule.sample_size} samples | {rule.win_rate}% WR
                        </span>
                      </div>
                      <div style={{ fontSize:"10px", color:"#8892a4", lineHeight:"1.6" }}>{rule.description}</div>
                    </div>
                  ))
                )}
              </div>
              <div>
                <div style={{ fontSize:"9px", color:"#4a5568", letterSpacing:"1px", marginBottom:"8px" }}>
                  PATTERN PERFORMANCE ({memoryData.total_trades || 0} trades analyzed)
                </div>
                {(memoryData.patterns || []).length === 0 ? (
                  <div style={{ fontSize:"10px", color:"#1e2535", padding:"12px 0" }}>No pattern data yet</div>
                ) : (
                  (memoryData.patterns || []).slice(0, 12).map((p, i) => (
                    <div key={i} className="row" style={{ fontSize:"10px" }}>
                      <div>
                        <span style={{ color:"#e2e8f0" }}>{p.pattern}</span>
                        <span style={{ color:"#2d3748", fontSize:"8px", marginLeft:"4px" }}>{p.symbol} {p.side} ({p.regime})</span>
                      </div>
                      <span>
                        <span style={{ color: p.win_rate >= 50 ? "#00ff88" : "#ff3366", fontWeight:"700" }}>{p.win_rate}%</span>
                        <span style={{ color:"#2d3748", marginLeft:"4px" }}>{p.total}x</span>
                      </span>
                    </div>
                  ))
                )}
              </div>
            </div>
          </div>
        )}

        {/* ── CONFIDENCE CALIBRATION ── */}
        {activeTab === "calibration" && !loading && calibrationData && (
          <div>
            <div style={{ fontSize:"9px", color:"#2d3748", letterSpacing:"2px", marginBottom:"6px" }}>CONFIDENCE CALIBRATION</div>
            <div style={{ fontSize:"10px", color:"#4a5568", marginBottom:"14px" }}>
              Does Claude&apos;s confidence actually predict win rate? Perfect calibration = predicted matches actual.
            </div>
            {(calibrationData.calibration || []).length === 0 ? (
              <div style={{ fontSize:"10px", color:"#1e2535", padding:"20px", textAlign:"center" }}>Need more trades with confidence data</div>
            ) : (
              <div style={{ display:"grid", gridTemplateColumns:"repeat(auto-fill, minmax(140px, 1fr))", gap:"10px" }}>
                {(calibrationData.calibration || []).map(c => {
                  const predicted = c.avg_predicted;
                  const actual = c.actual_win_rate;
                  const gap = Math.abs(predicted - actual);
                  const calibrated = gap < 10;
                  return (
                    <div key={c.predicted_band} style={{ background:"#06060f", borderRadius:"5px", padding:"12px", border:`1px solid ${calibrated ? "#00ff8822" : "#ff990022"}`, textAlign:"center" }}>
                      <div style={{ fontSize:"8px", color:"#2d3748", letterSpacing:"1px", marginBottom:"6px" }}>PREDICTED {c.predicted_band}</div>
                      <div style={{ fontSize:"16px", fontFamily:"'Chakra Petch',sans-serif", fontWeight:"700", color:"#8b5cf6" }}>{predicted}%</div>
                      <div style={{ fontSize:"8px", color:"#2d3748", margin:"4px 0" }}>vs actual</div>
                      <div style={{ fontSize:"16px", fontFamily:"'Chakra Petch',sans-serif", fontWeight:"700", color: actual >= 50 ? "#00ff88" : "#ff3366" }}>{actual}%</div>
                      <div style={{ fontSize:"8px", color: calibrated ? "#00ff88" : "#ff9900", marginTop:"6px" }}>
                        {calibrated ? "CALIBRATED" : `${gap.toFixed(0)}% OFF`}
                      </div>
                      <div style={{ fontSize:"8px", color:"#2d3748", marginTop:"2px" }}>{c.total} trades | ${c.total_pnl}</div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}

        {/* ── BACKTEST ── */}
        {activeTab === "backtest" && !loading && (
          <div>
            <div style={{ fontSize:"9px", color:"#2d3748", letterSpacing:"2px", marginBottom:"12px" }}>HISTORICAL BACKTEST</div>
            <div style={{ display:"flex", gap:"10px", flexWrap:"wrap", alignItems:"flex-end", marginBottom:"14px" }}>
              {[
                { label:"COIN", key:"symbol", type:"select", options:["BTC","ETH","SOL","LINK","DOGE","AVAX"] },
                { label:"DAYS", key:"days", type:"number", min:7, max:365 },
                { label:"TP (ATR x)", key:"tp", type:"number", step:0.5, min:1 },
                { label:"SL (ATR x)", key:"sl", type:"number", step:0.25, min:0.5 },
                { label:"MIN CONFLUENCE", key:"confluence", type:"number", min:1, max:20 },
                { label:"MIN R:R", key:"rr", type:"number", step:0.2, min:1 },
              ].map(f => (
                <div key={f.key}>
                  <div style={{ fontSize:"8px", color:"#2d3748", letterSpacing:"1px", marginBottom:"3px" }}>{f.label}</div>
                  {f.type === "select" ? (
                    <select value={btParams[f.key]} onChange={e => setBtParams(p => ({ ...p, [f.key]: e.target.value }))}
                      style={{ fontFamily:"'Space Mono',monospace", fontSize:"10px", padding:"6px 10px", borderRadius:"4px", border:"1px solid #1e2535", background:"#0a0a18", color:"#b8c8d8", outline:"none" }}>
                      {f.options.map(o => <option key={o} value={o}>{o}</option>)}
                    </select>
                  ) : (
                    <input type="number" value={btParams[f.key]} onChange={e => setBtParams(p => ({ ...p, [f.key]: +e.target.value }))}
                      min={f.min} max={f.max} step={f.step || 1}
                      style={{ fontFamily:"'Space Mono',monospace", fontSize:"10px", padding:"6px 10px", borderRadius:"4px", border:"1px solid #1e2535", background:"#0a0a18", color:"#b8c8d8", outline:"none", width:"70px" }} />
                  )}
                </div>
              ))}
              <button className="btn btn-p" onClick={runBacktest} disabled={backtestLoading} style={{ alignSelf:"flex-end" }}>
                {backtestLoading ? <span className="blink">RUNNING...</span> : "RUN BACKTEST"}
              </button>
            </div>

            {backtestResult && !backtestResult.error && (
              <div>
                <div style={{ display:"grid", gridTemplateColumns:"repeat(auto-fill, minmax(120px, 1fr))", gap:"8px", marginBottom:"14px" }}>
                  {[
                    { label:"RETURN", val:`${backtestResult.return_pct >= 0 ? "+" : ""}${backtestResult.return_pct}%`, color: backtestResult.return_pct >= 0 ? "#00ff88" : "#ff3366" },
                    { label:"TOTAL P&L", val:`${backtestResult.total_pnl >= 0 ? "+" : ""}$${backtestResult.total_pnl}`, color: backtestResult.total_pnl >= 0 ? "#00ff88" : "#ff3366" },
                    { label:"TRADES", val:backtestResult.total_trades, color:"#e2e8f0" },
                    { label:"WIN RATE", val:`${backtestResult.win_rate}%`, color: backtestResult.win_rate >= 50 ? "#00ff88" : "#ff3366" },
                    { label:"AVG WIN", val:`+$${backtestResult.avg_win}`, color:"#00ff88" },
                    { label:"AVG LOSS", val:`$${backtestResult.avg_loss}`, color:"#ff3366" },
                    { label:"MAX DD", val:`${backtestResult.max_drawdown_pct}%`, color: backtestResult.max_drawdown_pct > 15 ? "#ff3366" : "#ff9900" },
                    { label:"PROFIT FACTOR", val:backtestResult.profit_factor, color: backtestResult.profit_factor >= 1.5 ? "#00ff88" : "#ff9900" },
                  ].map(s => (
                    <div key={s.label} style={{ background:"#06060f", borderRadius:"5px", padding:"8px 10px", textAlign:"center" }}>
                      <div style={{ fontSize:"8px", color:"#2d3748", marginBottom:"3px" }}>{s.label}</div>
                      <div style={{ fontFamily:"'Chakra Petch',sans-serif", fontSize:"13px", fontWeight:"700", color:s.color }}>{s.val}</div>
                    </div>
                  ))}
                </div>
                {backtestResult.trades?.length > 0 && (
                  <div style={{ maxHeight:"200px", overflowY:"auto" }}>
                    {backtestResult.trades.map((t, i) => (
                      <div key={i} className="trow" style={{ fontSize:"10px" }}>
                        <div>
                          <span className="tag" style={{ background: t.side==="buy"?"#00ff8818":"#ff336618", color: t.side==="buy"?"#00ff88":"#ff3366", marginRight:"4px" }}>
                            {t.side?.toUpperCase()}
                          </span>
                          <span style={{ color:"#e2e8f0" }}>${t.entry?.toLocaleString()} → ${t.exit?.toLocaleString()}</span>
                        </div>
                        <div style={{ textAlign:"right" }}>
                          <span style={{ fontWeight:"700", color: t.win ? "#00ff88" : "#ff3366" }}>{t.pnl >= 0 ? "+" : ""}${t.pnl}</span>
                          <span style={{ color:"#2d3748", marginLeft:"6px", fontSize:"9px" }}>{t.reason}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
            {backtestResult?.error && (
              <div style={{ fontSize:"11px", color:"#ff3366", padding:"16px", textAlign:"center" }}>{backtestResult.error}</div>
            )}
            {!backtestResult && (
              <div style={{ textAlign:"center", padding:"30px", color:"#1e2535", fontSize:"11px" }}>
                Configure parameters and click RUN BACKTEST to test your strategy against historical data
              </div>
            )}
          </div>
        )}
      </div>

      {/* Loss notification toast */}
      {lossToast && (
        <div
          style={{
            position: "fixed", bottom: "24px", left: "50%", transform: "translateX(-50%)",
            background: "#1a0a0f", border: "1px solid #ff336655", borderRadius: "8px",
            padding: "12px 20px", boxShadow: "0 4px 24px rgba(255,51,102,0.2)",
            fontFamily: "'Chakra Petch',sans-serif", fontSize: "12px", fontWeight: "600",
            color: "#ff3366", letterSpacing: "1px", zIndex: 9999,
            animation: "lossToastIn 0.3s ease-out",
          }}
          role="alert"
        >
          {lossToast.msg}
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
