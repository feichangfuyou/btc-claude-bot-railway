import { useState, useEffect, useRef, useCallback } from "react";
import TradingViewChart from "./TradingViewChart.jsx";

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
  return { upper: +(mid + 2 * std).toFixed(2), middle: +mid.toFixed(2), lower: +(mid - 2 * std).toFixed(2), width: mid ? +((4 * std / mid) * 100).toFixed(4) : 0 };
}

const BOT_SECRET = import.meta.env.VITE_BOT_SECRET || "";
const BACKEND_WS = (() => {
  const base = import.meta.env.VITE_WS_URL
    || (window.location.protocol === "https:" ? "wss:" : "ws:") + "//" + window.location.host + "/ws";
  return BOT_SECRET ? `${base}?secret=${BOT_SECRET}` : base;
})();
const MAKER_FEE  = 0.004;

export default function App() {
  // ── Connection ──────────────────────────────────────────────────────────────
  const [connected,   setConnected]   = useState(false);
  const [demoMode,    setDemoMode]    = useState(true);
  const [cbLive,      setCbLive]      = useState(false);
  const [hasClaude,   setHasClaude]   = useState(false);
  const [paperMode,   setPaperMode]   = useState(true);
  const [agentKit,    setAgentKit]    = useState({ agentkit_ready:false, wallet_address:null, network:null, error:null });

  // ── Market ──────────────────────────────────────────────────────────────────
  const [price,       setPrice]       = useState(0);
  const [prevPrice,   setPrevPrice]   = useState(0);
  const [change24h,   setChange24h]   = useState(0);
  const [history,     setHistory]     = useState([]);
  const [indic,       setIndic]       = useState({ ema9:null, ema21:null, rsi:50, atr:0, bb_upper:0, bb_middle:0, bb_lower:0, bb_width:0, vwap:null });
  const [regime,      setRegime]      = useState("ranging");
  const [fearGreed,   setFearGreed]   = useState({ value: 50, label: "Neutral" });
  const [candles,     setCandles]     = useState([]);

  // ── Account ─────────────────────────────────────────────────────────────────
  const [startBal,    setStartBal]    = useState(5000);
  const [account,     setAccount]     = useState({ balance: 5000, daily_pnl: 0, total_pnl: 0 });
  const [consecLosses, setConsecLosses] = useState(0);
  const [breakerActive, setBreakerActive] = useState(false);

  // ── Trading ─────────────────────────────────────────────────────────────────
  const [position,    setPosition]    = useState(null);
  const [trades,      setTrades]      = useState([]);
  const [decision,    setDecision]    = useState(null);
  const [thinking,    setThinking]    = useState(false);
  const [botOn,       setBotOn]       = useState(false);
  const [lastCall,    setLastCall]    = useState("--");
  const [countdown,   setCountdown]   = useState(180);
  const [priceAge,    setPriceAge]    = useState(0);

  // ── Logs ────────────────────────────────────────────────────────────────────
  const [logs, setLogs] = useState([{ msg: "Connecting to backend...", type: "info", ts: "--:--:--" }]);
  const log = useCallback((msg, type = "info") =>
    setLogs(prev => [{ msg, type, ts: new Date().toLocaleTimeString() }, ...prev].slice(0, 60)), []);

  // ── Refs (always current, no stale closures) ─────────────────────────────────
  const wsRef        = useRef(null);
  const priceRef     = useRef(price);
  const accountRef   = useRef(account);
  const posRef       = useRef(position);
  const indicRef     = useRef(indic);
  const regimeRef    = useRef(regime);
  const tradesRef    = useRef(trades);
  // FIX: fearGreed in a ref so callClaude never gets stale data
  const fearGreedRef = useRef(fearGreed);
  const demoRef      = useRef(null);
  const botTimerRef  = useRef(null);
  const priceAgeRef  = useRef(null);
  const lastResetRef = useRef("");
  const thinkingRef  = useRef(false);
  const change24hRef = useRef(change24h);

  priceRef.current     = price;
  accountRef.current   = account;
  posRef.current       = position;
  indicRef.current     = indic;
  regimeRef.current    = regime;
  tradesRef.current    = trades;
  fearGreedRef.current = fearGreed;
  thinkingRef.current  = thinking;
  change24hRef.current = change24h;

  // ── Send to backend ──────────────────────────────────────────────────────────
  const send = useCallback((cmd) => {
    if (wsRef.current?.readyState === WebSocket.OPEN)
      wsRef.current.send(JSON.stringify({ cmd }));
  }, []);

  // ── Backend WebSocket ────────────────────────────────────────────────────────
  useEffect(() => {
    let ws, retryTimer;
    function connect() {
      ws = new WebSocket(BACKEND_WS);
      wsRef.current = ws;
      ws.onopen = () => {
        setConnected(true);
        setDemoMode(false);
        if (demoRef.current)    { clearInterval(demoRef.current);    demoRef.current    = null; }
        if (botTimerRef.current){ clearInterval(botTimerRef.current); botTimerRef.current = null; }
        if (priceAgeRef.current){ clearInterval(priceAgeRef.current); priceAgeRef.current = null; }
        log("✅ Backend connected — real-time data active", "success");
      };

      ws.onmessage = (e) => {
        try {
          const m = JSON.parse(e.data);
          // Price / indicators
          if (m.price != null)            { setPrevPrice(priceRef.current); setPrice(m.price); setPriceAge(0); }
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
          // Account / trading
          if (m.account)                  setAccount(m.account);
          if (m.open_position !== undefined) setPosition(m.open_position);
          if (m.trades)                   setTrades(m.trades);
          if (m.claude_decision)          setDecision(m.claude_decision);
          // Bot status
          if (m.bot_running  != null)     setBotOn(m.bot_running);
          if (m.claude_thinking != null)  setThinking(m.claude_thinking);
          if (m.last_claude_call)         setLastCall(m.last_claude_call);
          if (m.countdown != null)        setCountdown(m.countdown);
          // Connection info
          if (m.has_claude_key != null)   setHasClaude(m.has_claude_key);
          if (m.paper_trading  != null)   setPaperMode(m.paper_trading);
          if (m.coinbase_connected != null) setCbLive(m.coinbase_connected);
          if (m.fear_greed)               setFearGreed(m.fear_greed);
          if (m.agentkit)                 setAgentKit(m.agentkit);
          if (m.logs)                     setLogs(m.logs);
          if (m.type === "wallet_status") setAgentKit(prev => ({ ...prev, ...m }));
          if (m.type === "log" && m.entry) setLogs(prev => [m.entry, ...prev].slice(0, 60));
          if (m.consecutive_losses != null) setConsecLosses(m.consecutive_losses);
          if (m.loss_breaker_active != null) setBreakerActive(m.loss_breaker_active);
          if (m.start_balance != null)   setStartBal(m.start_balance);
          if (m.type === "breaker_reset") { setConsecLosses(0); setBreakerActive(false); }
        } catch { /* ignore parse errors */ }
      };

      ws.onerror = () => {};
      ws.onclose = () => {
        setConnected(false);
        setCbLive(false);
        setDemoMode(true);
        if (!demoRef.current) {
          log("Backend offline — running demo mode. Start backend.py for live trading.", "warning");
          startDemo();
        }
        retryTimer = setTimeout(connect, 5000);
      };
    }

    connect();
    return () => { clearTimeout(retryTimer); ws?.close(); };
  }, [log]);

  // ── Demo: price feed (CoinGecko) ─────────────────────────────────────────────
  function startDemo() {
    if (demoRef.current) return;
    if (priceAgeRef.current) { clearInterval(priceAgeRef.current); priceAgeRef.current = null; }
    priceAgeRef.current = setInterval(() => setPriceAge(a => a + 1), 1000);
    demoRef.current = setInterval(async () => {
      try {
        // FIX: include_24hr_change in URL
        const r = await fetch("https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd&include_24hr_change=true");
        const d = await r.json();
        const p   = d.bitcoin?.usd || priceRef.current;
        const chg = d.bitcoin?.usd_24h_change || 0;
        const ts  = new Date().toLocaleTimeString("en-US", { hour12:false, hour:"2-digit", minute:"2-digit" });
        setPrevPrice(priceRef.current);
        setPrice(p);
        setChange24h(+chg.toFixed(2));
        setPriceAge(0);
        setHistory(prev => {
          const next   = [...prev, { t: ts, price: p, change24h: +chg.toFixed(2) }].slice(-100);
          const raw    = next.map(x => x.price);
          const b      = calcBB(raw);
          const e9     = calcEMA(raw, 9);
          const e21    = calcEMA(raw, 21);
          const r14    = calcRSI(raw);
          const a14    = calcATR(raw);
          const newInd = { ema9:e9, ema21:e21, rsi:r14, atr:a14, avg_atr:a14, bb_upper:b.upper, bb_middle:b.middle, bb_lower:b.lower, bb_width:b.width, vwap:null };
          setIndic(newInd);
          if (a14 > 600) setRegime("chaotic");
          else if (e9 && e21 && Math.abs(e9 - e21) > 200) setRegime(e9 > e21 ? "trending_up" : "trending_down");
          else setRegime("ranging");
          return next;
        });
        // Build local OHLC candle for TradingView chart
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
      } catch { /* keep last price */ }
    }, 30000);
  }

  // ── Demo: fetch Fear & Greed ─────────────────────────────────────────────────
  useEffect(() => {
    async function fetchFG() {
      try {
        const r = await fetch("https://api.alternative.me/fng/");
        const d = await r.json();
        setFearGreed({ value: +d.data[0].value, label: d.data[0].value_classification });
      } catch {}
    }
    fetchFG();
    const t = setInterval(fetchFG, 3600000);
    return () => clearInterval(t);
  }, []);

  // ── Demo: initial price fetch ────────────────────────────────────────────────
  useEffect(() => {
    if (!demoMode) return;
    startDemo();
    // Trigger first fetch immediately
    (async () => {
      try {
        const r = await fetch("https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd&include_24hr_change=true");
        const d = await r.json();
        const p   = d.bitcoin?.usd;
        const chg = d.bitcoin?.usd_24h_change || 0;
        if (p) {
          setPrice(p);
          setChange24h(+chg.toFixed(2));
          setPriceAge(0);
          log(`💰 BTC price loaded: $${p.toLocaleString()}`, "success");
        }
      } catch { log("⚠ Price fetch failed — will retry in 30s", "warning"); }
    })();
  }, []); // eslint-disable-line

  // ── Demo: midnight P&L reset ─────────────────────────────────────────────────
  useEffect(() => {
    const t = setInterval(() => {
      const now   = new Date();
      const today = now.toDateString();
      if (now.getHours() === 0 && now.getMinutes() === 0 && lastResetRef.current !== today) {
        lastResetRef.current = today;
        setAccount(a => ({ ...a, daily_pnl: 0 }));
        log("📅 Daily P&L reset (midnight)", "info");
      }
    }, 60000);
    return () => clearInterval(t);
  }, [log]);

  // ── TP/SL checker (demo mode) ────────────────────────────────────────────────
  useEffect(() => {
    const pos = posRef.current;
    if (!demoMode || !pos || price === 0) return;
    let hit = false, pnl = 0, reason = "";
    if (pos.side === "buy") {
      if (price >= pos.tp)  { hit=true; pnl=(pos.tp  -pos.entry)*pos.btc_size; reason="✅ TP HIT"; }
      else if (price<=pos.sl){ hit=true; pnl=(pos.sl  -pos.entry)*pos.btc_size; reason="❌ SL HIT"; }
    } else {
      if (price <= pos.tp)  { hit=true; pnl=(pos.entry-pos.tp)  *pos.btc_size; reason="✅ TP HIT"; }
      else if (price>=pos.sl){ hit=true; pnl=(pos.entry-pos.sl) *pos.btc_size; reason="❌ SL HIT"; }
    }
    if (!hit) return;
    const net = +(pnl - pos.usd_size * MAKER_FEE).toFixed(2);
    setAccount(a => ({ balance:+(a.balance+pos.usd_size+net).toFixed(2), daily_pnl:+(a.daily_pnl+net).toFixed(2), total_pnl:+(a.total_pnl+net).toFixed(2) }));
    setTrades(prev => [{ id:Date.now(), side:pos.side, entry:pos.entry, exit:reason.includes("TP")?pos.tp:pos.sl, pnl:net, reason, ts:new Date().toLocaleTimeString(), win:net>0 }, ...prev].slice(0,30));
    setPosition(null);
    log(`${reason} | ${pos.side.toUpperCase()} | Net: ${net>=0?"+":""}$${net}`, net>=0?"success":"error");
  }, [price, demoMode, log]);

  const callClaude = useCallback(async () => {
    if (thinkingRef.current) return;
    setThinking(true);
    setLastCall(new Date().toLocaleTimeString());
    log("🧠 Claude analyzing live market data...", "claude");

    const snap = {
      price:            priceRef.current,
      price_change24h:  change24hRef.current,
      market_condition: regimeRef.current,
      indicators:       indicRef.current,
      fear_greed:       fearGreedRef.current,
      account:          { ...accountRef.current, can_trade: !posRef.current && accountRef.current.balance > 10 },
      open_position:    posRef.current,
      recent_trades:    tradesRef.current.slice(0, 5),
    };

    try {
      const res = await fetch("https://api.anthropic.com/v1/messages", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          model: "claude-sonnet-4-20250514",
          max_tokens: 600,
          system: `You are an expert Bitcoin scalping bot brain. Analyze the market snapshot and return a precise JSON trading decision.
STRICT RULES:
- If open_position exists OR can_trade is false → action MUST be "wait"
- If market_condition is "chaotic" → action MUST be "wait" or "close_all"
- risk:reward MINIMUM 1.5:1 (take_profit distance >= 1.5x stop_loss distance from entry)
- stop_loss: 0.5-1.5x ATR from entry. take_profit: 1x-2x ATR from entry
- size_percent max 15, max 8 for accounts under $500
- entry_price must be within 0.1% of current price
RESPOND ONLY IN RAW JSON, NO MARKDOWN, NO EXTRA TEXT:
{"reasoning":"1-2 sentences","market_condition":"ranging|trending_up|trending_down|chaotic","action":"buy|sell|wait|close_all","confidence":0.0,"order":{"side":"buy|sell","size_percent":10,"entry_price":0,"take_profit":0,"stop_loss":0}}
Omit "order" if action is "wait" or "close_all".`,
          messages: [{ role: "user", content: `Live snapshot: ${JSON.stringify(snap)}\n\nReturn decision JSON:` }]
        })
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.error?.message || `HTTP ${res.status} — likely CORS. Run backend.py locally.`);
      }

      const data = await res.json();
      let raw = (data.content || []).map(c => c.text || "").join("");
      // Robust extraction
      const mdMatch = raw.match(/```(?:json)?\s*(\{[\s\S]*?\})\s*```/);
      if (mdMatch) raw = mdMatch[1];
      else {
        const s = raw.indexOf("{"), e = raw.lastIndexOf("}") + 1;
        if (s !== -1 && e > s) raw = raw.slice(s, e);
      }

      const dec = JSON.parse(raw.trim());
      setDecision(dec);

      const { action, order } = dec;
      if (action === "wait") {
        log(`⏸ WAIT — ${dec.reasoning?.slice(0, 80)}`, "dim");
      } else if (action === "close_all" && posRef.current) {
        const pos = posRef.current;
        const pnl = pos.side === "buy"
          ? (priceRef.current - pos.entry) * pos.btc_size
          : (pos.entry - priceRef.current) * pos.btc_size;
        const net = +(pnl - pos.usd_size * MAKER_FEE).toFixed(2);
        setAccount(a => ({ balance:+(a.balance+pos.usd_size+net).toFixed(2), daily_pnl:+(a.daily_pnl+net).toFixed(2), total_pnl:+(a.total_pnl+net).toFixed(2) }));
        setTrades(p => [{ id:Date.now(), side:pos.side, entry:pos.entry, exit:priceRef.current, pnl:net, reason:"⚡ FORCE CLOSE", ts:new Date().toLocaleTimeString(), win:net>0 }, ...p].slice(0,30));
        setPosition(null);
        log(`⚡ FORCE CLOSE — Net: ${net>=0?"+":""}$${net}`, "warning");
      } else if ((action === "buy" || action === "sell") && !posRef.current && order?.take_profit && order?.stop_loss) {
        const entry  = order.entry_price || priceRef.current;
        const reward = Math.abs(order.take_profit - entry);
        const risk   = Math.abs(entry - order.stop_loss);
        if (risk === 0 || reward / risk < 1.5) {
          log(`⚠ R:R ${(reward/Math.max(risk,1)).toFixed(2)} < 1.5 — rejected by risk manager`, "warning");
        } else {
          const pct     = Math.min(Math.max(order.size_percent || 10, 5), 15) / 100;
          const usd_sz  = +Math.min(accountRef.current.balance * pct, accountRef.current.balance * 0.15).toFixed(2);
          if (usd_sz >= 5) {
            const btc_size = +(usd_sz / entry).toFixed(8);
            setAccount(a => ({ ...a, balance: +(a.balance - usd_sz).toFixed(2) }));
            setPosition({ side:action, entry, tp:order.take_profit, sl:order.stop_loss, btc_size, usd_size:usd_sz, open_ts:new Date().toLocaleTimeString(), confidence:dec.confidence });
            log(`${action==="buy"?"🟢":"🔴"} ${action.toUpperCase()} @ $${entry.toLocaleString()} | TP $${order.take_profit.toLocaleString()} | SL $${order.stop_loss.toLocaleString()} | Conf ${(dec.confidence*100).toFixed(0)}%`, action==="buy"?"success":"sell");
          } else {
            log("⚠ Trade size too small (< $5) — skipped", "warning");
          }
        }
      }
    } catch (e) {
      if (e.message?.toLowerCase().includes("failed to fetch") || e.message?.toLowerCase().includes("cors") || e.message?.toLowerCase().includes("networkerror")) {
        log("⚠ Claude CORS blocked in browser preview — run python backend.py for live AI trading", "warning");
        setDecision({ reasoning: "CORS blocked: browser can't call Anthropic API directly. Run python backend.py locally — Claude will work perfectly from the backend.", action: "wait", confidence: 0, market_condition: regimeRef.current });
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
    setCountdown(8);
    botTimerRef.current = setInterval(() => {
      setCountdown(prev => {
        if (prev <= 1) { callClaude(); return 180; }
        return prev - 1;
      });
    }, 1000);
    return () => { if (botTimerRef.current) clearInterval(botTimerRef.current); };
  }, [demoMode, botOn, callClaude]);

  // ── Price age counter (demo mode) ────────────────────────────────────────────
  useEffect(() => {
    if (demoMode) return; // backend mode handles this differently
    // priceAgeRef interval is started in startDemo
  }, [demoMode]);

  // ── Handlers ─────────────────────────────────────────────────────────────────
  const handleStart = () => {
    if (connected) { send("start_bot"); }
    else { setBotOn(true); log("🟢 Demo bot started — first analysis in 8s", "success"); }
  };
  const handleStop = () => {
    if (connected) { send("stop_bot"); }
    else { setBotOn(false); log("🔴 Bot stopped", "warning"); }
  };
  const handleAsk = () => connected ? send("ask_claude") : callClaude();
  const handleClose = () => {
    if (connected) { send("close_position"); return; }
    const pos = posRef.current;
    if (!pos) return;
    const pnl = pos.side==="buy" ? (priceRef.current-pos.entry)*pos.btc_size : (pos.entry-priceRef.current)*pos.btc_size;
    const net = +(pnl - pos.usd_size * MAKER_FEE).toFixed(2);
    setAccount(a => ({ balance:+(a.balance+pos.usd_size+net).toFixed(2), daily_pnl:+(a.daily_pnl+net).toFixed(2), total_pnl:+(a.total_pnl+net).toFixed(2) }));
    setTrades(p => [{ id:Date.now(), side:pos.side, entry:pos.entry, exit:priceRef.current, pnl:net, reason:"🖐 MANUAL CLOSE", ts:new Date().toLocaleTimeString(), win:net>0 }, ...p].slice(0,30));
    setPosition(null);
    log(`🖐 MANUAL CLOSE | Net: ${net>=0?"+":""}$${net}`, net>=0?"success":"warning");
  };
  const handleReset = () => {
    if (connected) { send("reset_account"); return; }
    setAccount({ balance:startBal, daily_pnl:0, total_pnl:0 });
    setPosition(null);
    setTrades([]);
    setDecision(null);
    setConsecLosses(0);
    setBreakerActive(false);
    log(`🔄 Account reset to $${startBal}`, "warning");
  };
  const handleResetBreaker = () => {
    if (connected) send("reset_breaker");
    else { setConsecLosses(0); setBreakerActive(false); log("✅ Circuit breaker reset", "success"); }
  };

  // ── Derived ───────────────────────────────────────────────────────────────────
  const priceUp      = price >= prevPrice && prevPrice > 0;
  const winRate      = trades.length ? Math.round(trades.filter(t => t.win).length / trades.length * 100) : 0;
  const unrealized   = position ? +((position.side==="buy" ? price-position.entry : position.entry-price) * position.btc_size).toFixed(2) : 0;
  const condColor    = { ranging:"#00d4ff", trending_up:"#00ff88", trending_down:"#ff3366", chaotic:"#ff9900" }[regime] || "#64748b";
  const condLabel    = { ranging:"◈ RANGING", trending_up:"▲ TRENDING UP", trending_down:"▼ TRENDING DOWN", chaotic:"⚡ CHAOTIC" }[regime] || regime;
  const dailyLossPct = Math.abs(Math.min(0, account.daily_pnl) / Math.max(account.balance, 1) * 100);
  const START_BAL    = startBal;
  const fgColor      = fearGreed.value < 25 ? "#ff3366" : fearGreed.value < 50 ? "#ff9900" : fearGreed.value < 75 ? "#00d4ff" : "#00ff88";

  return (
    <div style={{ fontFamily:"'Space Mono',monospace", background:"#06060f", color:"#b8c8d8", minHeight:"100vh", padding:"10px", fontSize:"12px" }}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=Chakra+Petch:wght@300;400;600;700&display=swap');
        *{box-sizing:border-box;margin:0;padding:0}
        ::-webkit-scrollbar{width:3px;height:3px}::-webkit-scrollbar-track{background:#0a0a16}::-webkit-scrollbar-thumb{background:#1e2a40;border-radius:2px}
        .card{background:#0a0a18;border:1px solid #131828;border-radius:6px;padding:12px}
        .grid{display:grid;grid-template-columns:260px 1fr 260px;gap:10px}
        .col{display:flex;flex-direction:column;gap:10px}
        @keyframes pulse{0%,100%{opacity:1}50%{opacity:.3}}
        @keyframes fadein{from{opacity:0;transform:translateY(-3px)}to{opacity:1;transform:translateY(0)}}
        .pulse{animation:pulse 2s infinite}.blink{animation:pulse 0.7s infinite}.fadein{animation:fadein 0.3s ease}
        .btn{font-family:'Space Mono',monospace;font-size:10px;font-weight:700;letter-spacing:1.5px;padding:7px 14px;border:none;border-radius:4px;cursor:pointer;transition:all 0.15s}
        .btn:disabled{opacity:.4;cursor:not-allowed}
        .btn-g{background:#00ff88;color:#06060f}.btn-g:hover:not(:disabled){background:#00cc6a;transform:translateY(-1px)}
        .btn-r{background:#ff3366;color:#fff}.btn-r:hover:not(:disabled){background:#cc1a44}
        .btn-p{background:transparent;color:#8b5cf6;border:1px solid #8b5cf633}.btn-p:hover:not(:disabled){background:#8b5cf611}
        .btn-d{background:transparent;color:#4a5568;border:1px solid #1e2535;font-size:9px;padding:5px 10px}.btn-d:hover:not(:disabled){background:#0d0d1c}
        .row{display:flex;justify-content:space-between;align-items:center;padding:4px 0;border-bottom:1px solid #0d0d1c}
        .tag{display:inline-block;padding:2px 7px;border-radius:3px;font-size:9px;font-weight:700;letter-spacing:.5px}
        .logrow{padding:3px 0;border-bottom:1px solid #0a0a16;animation:fadein 0.2s ease}
        .trow{padding:5px 0;border-bottom:1px solid #0d0d1c;display:flex;justify-content:space-between;align-items:center}
        .dot{width:7px;height:7px;border-radius:50%;display:inline-block;flex-shrink:0}
      `}</style>

      {/* ══ STATUS BAR ══ */}
      <div style={{ display:"flex", gap:"6px", marginBottom:"8px", flexWrap:"wrap", alignItems:"center" }}>
        {[
          { label:"BACKEND",    ok:connected,  on:"● LIVE",        off:"○ OFFLINE",     okColor:"#00ff88", offColor:"#ff3366" },
          { label:"COINBASE",   ok:cbLive,     on:"● REAL-TIME",   off:"○ COINGECKO",   okColor:"#00ff88", offColor:"#ff9900" },
          { label:"CLAUDE",     ok:hasClaude,  on:"● READY",       off:"⚠ NO KEY",      okColor:"#00ff88", offColor:"#ff9900" },
          { label:"MODE",       ok:!paperMode, on:"💰 LIVE",        off:"📝 PAPER",       okColor:"#ff3366", offColor:"#ff9900" },
          { label:"AGENTKIT",  ok:agentKit.agentkit_ready, on:"● ON-CHAIN",   off: paperMode ? "○ PAPER" : "○ OFFLINE", okColor:"#00d4ff", offColor:"#2d3748" },
        ].map(s => (
          <div key={s.label} style={{ display:"flex", gap:"5px", alignItems:"center", background:"#0a0a18", border:"1px solid #131828", borderRadius:"4px", padding:"4px 8px" }}>
            <span style={{ fontSize:"8px", color:"#2d3748" }}>{s.label}</span>
            <span style={{ fontSize:"9px", fontWeight:"700", color: s.ok ? s.okColor : s.offColor }}>
              {s.ok ? s.on : s.off}
            </span>
          </div>
        ))}
        {breakerActive && (
          <div style={{ display:"flex", gap:"5px", alignItems:"center", background:"#ff336618", border:"1px solid #ff336644", borderRadius:"4px", padding:"4px 8px", cursor:"pointer" }} onClick={handleResetBreaker}>
            <span style={{ fontSize:"9px", fontWeight:"700", color:"#ff3366" }} className="blink">
              🛑 CIRCUIT BREAKER ({consecLosses} losses) — click to reset
            </span>
          </div>
        )}
        {price > 0 && <span style={{ fontSize:"8px", color: priceAge > 60 ? "#ff9900" : "#2d3748", marginLeft:"4px" }}>price {priceAge}s ago</span>}
        {demoMode && <span style={{ fontSize:"8px", color:"#ff9900", marginLeft:"4px" }}>⚠ Run python backend.py for live Claude trading</span>}
      </div>

      {/* ══ HEADER ══ */}
      <div style={{ display:"flex", alignItems:"center", justifyContent:"space-between", marginBottom:"10px", flexWrap:"wrap", gap:"8px" }}>
        {/* Logo */}
        <div style={{ display:"flex", alignItems:"center", gap:"10px" }}>
          <div style={{ background:"linear-gradient(135deg,#8b5cf6,#00d4ff)", width:"42px", height:"42px", borderRadius:"10px", display:"flex", alignItems:"center", justifyContent:"center", fontSize:"22px", color:"#fff", boxShadow:"0 0 24px #8b5cf655", flexShrink:0 }}>₿</div>
          <div>
            <div style={{ fontFamily:"'Chakra Petch',sans-serif", fontSize:"18px", fontWeight:"700", color:"#fff", letterSpacing:"3px" }}>CLAUDE<span style={{ color:"#00d4ff" }}>BOT</span></div>
            <div style={{ fontSize:"8px", color:"#4a5568", letterSpacing:"1px" }}>AI-POWERED BTC SCALPING ENGINE</div>
          </div>
        </div>

        {/* Price */}
        <div style={{ textAlign:"center" }}>
          {price > 0 ? (
            <>
              <div style={{ fontFamily:"'Chakra Petch',sans-serif", fontSize:"30px", fontWeight:"700", letterSpacing:"1px", color: priceUp?"#00ff88":"#ff3366", textShadow:`0 0 24px ${priceUp?"#00ff8844":"#ff336644"}` }}>
                ${price.toLocaleString()}
              </div>
              <div style={{ fontSize:"9px", color: change24h>=0?"#00ff88":"#ff3366", marginTop:"2px" }}>
                {change24h>=0?"▲":"▼"} {Math.abs(change24h).toFixed(2)}% 24h
                <span style={{ color:"#2d3748", marginLeft:"6px" }}>{cbLive?"● Coinbase RT":"● CoinGecko"}</span>
              </div>
            </>
          ) : (
            <div className="blink" style={{ fontFamily:"'Chakra Petch',sans-serif", fontSize:"22px", color:"#2d3748" }}>Fetching price...</div>
          )}
        </div>

        {/* Stats + Controls */}
        <div style={{ display:"flex", gap:"16px", alignItems:"center", flexWrap:"wrap" }}>
          {[
            { label:"BALANCE",   val:`$${account.balance.toFixed(2)}`,                                                    color:"#e2e8f0" },
            { label:"TOTAL P&L", val:`${account.total_pnl>=0?"+":""}$${account.total_pnl.toFixed(2)}`,                   color:account.total_pnl>=0?"#00ff88":"#ff3366" },
            { label:"TODAY",     val:`${account.daily_pnl>=0?"+":""}$${account.daily_pnl.toFixed(2)}`,                   color:account.daily_pnl>=0?"#00ff88":"#ff3366" },
            { label:"WIN RATE",  val:`${winRate}%`,                                                                        color:winRate>=50?"#00ff88":"#ff3366" },
          ].map(s => (
            <div key={s.label} style={{ textAlign:"right" }}>
              <div style={{ fontSize:"8px", color:"#2d3748", letterSpacing:"1px" }}>{s.label}</div>
              <div style={{ fontFamily:"'Chakra Petch',sans-serif", fontSize:"15px", fontWeight:"700", color:s.color }}>{s.val}</div>
            </div>
          ))}
          <div style={{ display:"flex", gap:"6px" }}>
            {!botOn
              ? <button className="btn btn-g" onClick={handleStart}>▶ START</button>
              : <button className="btn btn-r" onClick={handleStop}>■ STOP</button>}
            <button className="btn btn-p" onClick={handleAsk} disabled={thinking}>
              {thinking ? <span className="blink">● THINKING</span> : "⬡ ASK AI"}
            </button>
            <button className="btn btn-d" onClick={handleReset} title="Reset paper balance">↺</button>
          </div>
        </div>
      </div>

      {/* ══ 3-COL GRID ══ */}
      <div className="grid">

        {/* ═══ LEFT ═══ */}
        <div className="col">

          {/* Claude Brain */}
          <div className="card" style={{ border:"1px solid #8b5cf622", boxShadow: thinking?"0 0 30px #8b5cf644":"0 0 12px #8b5cf610" }}>
            <div style={{ display:"flex", alignItems:"center", justifyContent:"space-between", marginBottom:"10px" }}>
              <div style={{ display:"flex", alignItems:"center", gap:"7px" }}>
                <span className="dot" style={{ background: thinking?"#8b5cf6":botOn?"#00ff88":"#2d3748", animation:(thinking||botOn)?"pulse 1.5s infinite":"none", boxShadow:`0 0 8px ${thinking?"#8b5cf6":botOn?"#00ff88":"transparent"}` }} />
                <span style={{ fontFamily:"'Chakra Petch',sans-serif", fontSize:"10px", color:"#8b5cf6", fontWeight:"700", letterSpacing:"2px" }}>CLAUDE BRAIN</span>
              </div>
              {botOn && !thinking && <span style={{ fontSize:"9px", color:"#2d3748" }}>next: {countdown}s</span>}
              {thinking         && <span className="blink" style={{ fontSize:"9px", color:"#8b5cf6" }}>analyzing...</span>}
            </div>

            {decision ? (
              <div className="fadein">
                <div style={{ display:"flex", alignItems:"center", gap:"8px", marginBottom:"10px" }}>
                  <span className="tag" style={{
                    background:{buy:"#00ff8820",sell:"#ff336620",wait:"#ffffff10",close_all:"#ff990020"}[decision.action]||"#ffffff10",
                    color:{buy:"#00ff88",sell:"#ff3366",wait:"#64748b",close_all:"#ff9900"}[decision.action]||"#64748b",
                    fontSize:"12px", padding:"4px 12px"
                  }}>
                    {{buy:"▲ BUY",sell:"▼ SELL",wait:"⏸ WAIT",close_all:"⚡ CLOSE ALL"}[decision.action]||decision.action?.toUpperCase()}
                  </span>
                  {decision.confidence != null && (
                    <div style={{ flex:1 }}>
                      <div style={{ height:"3px", background:"#131828", borderRadius:"2px", overflow:"hidden" }}>
                        <div style={{ height:"100%", width:`${decision.confidence*100}%`, background: decision.confidence>0.7?"#00ff88":decision.confidence>0.5?"#ff9900":"#ff3366", transition:"width 0.6s", borderRadius:"2px" }} />
                      </div>
                      <div style={{ fontSize:"9px", color:"#4a5568", marginTop:"2px" }}>{(decision.confidence*100).toFixed(0)}% confidence</div>
                    </div>
                  )}
                </div>
                <div style={{ fontSize:"10px", color:"#8892a4", lineHeight:"1.75", borderLeft:"2px solid #8b5cf633", paddingLeft:"8px", marginBottom:"10px", fontStyle:"italic" }}>
                  "{decision.reasoning}"
                </div>
                {decision.order && (
                  <div style={{ background:"#06060f", borderRadius:"4px", padding:"8px", border:"1px solid #131828" }}>
                    {[
                      { label:"ENTRY",       val:`$${(decision.order.entry_price||0).toLocaleString()}`,  color:"#00d4ff" },
                      { label:"TAKE PROFIT", val:`$${(decision.order.take_profit||0).toLocaleString()}`,  color:"#00ff88" },
                      { label:"STOP LOSS",   val:`$${(decision.order.stop_loss||0).toLocaleString()}`,    color:"#ff3366" },
                      { label:"SIZE",        val:`${decision.order.size_percent||0}% of balance`,         color:"#8892a4" },
                    ].map(r => (
                      <div key={r.label} className="row" style={{ fontSize:"10px" }}>
                        <span style={{ color:"#2d3748" }}>{r.label}</span>
                        <span style={{ color:r.color, fontWeight:"700" }}>{r.val}</span>
                      </div>
                    ))}
                  </div>
                )}
                <div style={{ fontSize:"8px", color:"#1e2535", marginTop:"6px", textAlign:"right" }}>LAST CALL: {lastCall}</div>
              </div>
            ) : (
              <div style={{ textAlign:"center", padding:"20px 0", color:"#1e2535", fontSize:"10px", lineHeight:"2.2" }}>
                {botOn
                  ? <span className="blink" style={{ color:"#8b5cf6" }}>First analysis in {countdown}s...</span>
                  : <span>Press <span style={{ color:"#00ff88" }}>▶ START</span> or <span style={{ color:"#8b5cf6" }}>⬡ ASK AI</span></span>
                }
              </div>
            )}
          </div>

          {/* Regime + Fear/Greed */}
          <div className="card">
            <div style={{ fontSize:"8px", color:"#2d3748", letterSpacing:"2px", marginBottom:"8px" }}>MARKET REGIME</div>
            <div style={{ padding:"10px", borderRadius:"4px", background:`${condColor}11`, border:`1px solid ${condColor}22`, textAlign:"center", marginBottom:"8px" }}>
              <span style={{ fontFamily:"'Chakra Petch',sans-serif", color:condColor, fontWeight:"700", fontSize:"13px", letterSpacing:"2px" }}>{condLabel}</span>
            </div>
            <div style={{ display:"flex", justifyContent:"space-between", alignItems:"center" }}>
              <span style={{ fontSize:"9px", color:"#2d3748" }}>FEAR & GREED</span>
              <div style={{ display:"flex", alignItems:"center", gap:"8px" }}>
                <div style={{ width:"60px", height:"3px", background:"#131828", borderRadius:"2px", overflow:"hidden" }}>
                  <div style={{ height:"100%", width:`${fearGreed.value}%`, background:`linear-gradient(to right, #ff3366, #ff9900, #00ff88)`, borderRadius:"2px" }} />
                </div>
                <span style={{ fontSize:"9px", fontWeight:"700", color:fgColor }}>{fearGreed.value} {fearGreed.label}</span>
              </div>
            </div>
          </div>

          {/* AgentKit Wallet */}
          {!paperMode && (
            <div className="card" style={{ border: agentKit.agentkit_ready ? "1px solid #00d4ff22" : "1px solid #131828", boxShadow: agentKit.agentkit_ready ? "0 0 12px #00d4ff10" : "none" }}>
              <div style={{ display:"flex", alignItems:"center", justifyContent:"space-between", marginBottom:"8px" }}>
                <div style={{ display:"flex", alignItems:"center", gap:"7px" }}>
                  <span className="dot" style={{ background: agentKit.agentkit_ready ? "#00d4ff" : "#2d3748", boxShadow: agentKit.agentkit_ready ? "0 0 8px #00d4ff" : "none" }} />
                  <span style={{ fontFamily:"'Chakra Petch',sans-serif", fontSize:"10px", color:"#00d4ff", fontWeight:"700", letterSpacing:"2px" }}>AGENTKIT WALLET</span>
                </div>
                <span style={{ fontSize:"8px", color: agentKit.agentkit_ready ? "#00d4ff" : "#ff3366" }}>
                  {agentKit.agentkit_ready ? "ON-CHAIN" : "OFFLINE"}
                </span>
              </div>
              {agentKit.agentkit_ready ? (
                <div>
                  <div className="row" style={{ fontSize:"10px" }}>
                    <span style={{ color:"#2d3748" }}>ADDRESS</span>
                    <span style={{ color:"#00d4ff", fontFamily:"monospace", fontSize:"9px" }}>
                      {agentKit.wallet_address ? `${agentKit.wallet_address.slice(0,6)}...${agentKit.wallet_address.slice(-4)}` : "--"}
                    </span>
                  </div>
                  <div className="row" style={{ fontSize:"10px" }}>
                    <span style={{ color:"#2d3748" }}>NETWORK</span>
                    <span style={{ color:"#e2e8f0", fontWeight:"700" }}>{agentKit.network || "--"}</span>
                  </div>
                  {agentKit.eth_balance && (
                    <div className="row" style={{ fontSize:"10px" }}>
                      <span style={{ color:"#2d3748" }}>ETH</span>
                      <span style={{ color:"#e2e8f0", fontWeight:"700" }}>{agentKit.eth_balance}</span>
                    </div>
                  )}
                  {agentKit.usdc_balance && (
                    <div className="row" style={{ fontSize:"10px" }}>
                      <span style={{ color:"#2d3748" }}>USDC</span>
                      <span style={{ color:"#00ff88", fontWeight:"700" }}>{agentKit.usdc_balance}</span>
                    </div>
                  )}
                </div>
              ) : (
                <div style={{ fontSize:"9px", color:"#2d3748", textAlign:"center", padding:"6px 0" }}>
                  {agentKit.error ? `⚠ ${agentKit.error}` : "Set CDP keys in .env for on-chain trading"}
                </div>
              )}
            </div>
          )}

          {/* Indicators */}
          <div className="card" style={{ flex:"1 1 0" }}>
            <div style={{ fontSize:"8px", color:"#2d3748", letterSpacing:"2px", marginBottom:"8px" }}>LIVE INDICATORS</div>
            {[
              { label:"EMA 9",    val: indic.ema9    ? `$${indic.ema9.toLocaleString()}`    : "warming…", color:"#00ff88" },
              { label:"EMA 21",   val: indic.ema21   ? `$${indic.ema21.toLocaleString()}`   : "warming…", color:"#00d4ff" },
              { label:"RSI 14",   val: indic.ema9    ? `${indic.rsi}${indic.rsi>70?" OB":indic.rsi<30?" OS":""}` : "-", color: indic.rsi>70?"#ff3366":indic.rsi<30?"#00ff88":"#e2e8f0" },
              { label:"ATR 14",   val: indic.ema9    ? `$${indic.atr}` : "-",                 color: indic.atr>500?"#ff9900":"#e2e8f0" },
              { label:"BB UPPER", val: indic.bb_upper  ? `$${indic.bb_upper.toLocaleString()}`  : "-", color:"#ff3366" },
              { label:"BB MID",   val: indic.bb_middle ? `$${indic.bb_middle.toLocaleString()}` : "-", color:"#64748b" },
              { label:"BB LOWER", val: indic.bb_lower  ? `$${indic.bb_lower.toLocaleString()}`  : "-", color:"#00ff88" },
              { label:"BB WIDTH", val: indic.bb_width  ? `${indic.bb_width}%` : "-", color:"#ff9900" },
              { label:"VWAP",     val: indic.vwap      ? `$${indic.vwap.toLocaleString()}`     : "-", color:"#8b5cf6" },
            ].map(ind => (
              <div key={ind.label} className="row" style={{ fontSize:"10px" }}>
                <span style={{ color:"#2d3748" }}>{ind.label}</span>
                <span style={{ color:ind.color, fontWeight:"700" }}>{ind.val}</span>
              </div>
            ))}
            <div style={{ marginTop:"6px", fontSize:"8px", color:"#1e2535", textAlign:"center" }}>
              {history.length < 9 ? `Building: ${history.length}/9 candles` : `${history.length} candles loaded`}
            </div>
          </div>
        </div>

        {/* ═══ CENTER ═══ */}
        <div className="col">
          {/* Chart — TradingView Lightweight Charts */}
          <div className="card" style={{ flex:"1 1 0", minHeight:"300px", display:"flex", flexDirection:"column" }}>
            <div style={{ display:"flex", justifyContent:"space-between", alignItems:"center", marginBottom:"6px" }}>
              <div style={{ display:"flex", alignItems:"center", gap:"8px" }}>
                <span style={{ fontFamily:"'Chakra Petch',sans-serif", fontSize:"10px", color:"#4a5568", letterSpacing:"2px" }}>BTC / USD</span>
                <span style={{ fontSize:"8px", color:"#1e2535" }}>1m candles</span>
              </div>
              <div style={{ display:"flex", gap:"10px", fontSize:"8px", alignItems:"center" }}>
                <span style={{ color:"#00ff88" }}>■ UP</span>
                <span style={{ color:"#ff3366" }}>■ DOWN</span>
                {position && <><span style={{ color:"#00d4ff" }}>┄ ENTRY</span><span style={{ color:"#00ff88" }}>┄ TP</span><span style={{ color:"#ff3366" }}>┄ SL</span></>}
              </div>
            </div>
            {candles.length > 0 ? (
              <div style={{ flex: 1, minHeight: 0 }}>
                <TradingViewChart history={candles} position={position} priceUp={priceUp} />
              </div>
            ) : (
              <div style={{ display:"flex", alignItems:"center", justifyContent:"center", flex:1, flexDirection:"column", gap:"8px" }}>
                <span className="pulse" style={{ color:"#2d3748", fontSize:"11px" }}>Collecting price data...</span>
                <span style={{ color:"#1e2535", fontSize:"9px" }}>Candlestick chart builds after first price tick</span>
              </div>
            )}
          </div>

          {/* Open Position */}
          {position ? (
            <div className="card fadein" style={{ border:`1px solid ${position.side==="buy"?"#00ff8822":"#ff336622"}`, boxShadow:`0 0 20px ${position.side==="buy"?"#00ff8811":"#ff336611"}` }}>
              <div style={{ display:"flex", justifyContent:"space-between", alignItems:"center", marginBottom:"8px" }}>
                <div style={{ display:"flex", alignItems:"center", gap:"8px" }}>
                  <span className="dot pulse" style={{ background:position.side==="buy"?"#00ff88":"#ff3366" }} />
                  <span style={{ fontFamily:"'Chakra Petch',sans-serif", fontSize:"10px", color:position.side==="buy"?"#00ff88":"#ff3366", fontWeight:"700", letterSpacing:"2px" }}>
                    {position.onchain ? "⛓ " : ""}OPEN {position.side?.toUpperCase()} POSITION
                  </span>
                  {position.onchain && <span className="tag" style={{ background:"#00d4ff18", color:"#00d4ff", fontSize:"7px", marginLeft:"4px" }}>ON-CHAIN</span>}
                  {position.trailing_active && <span className="tag" style={{ background:"#ff990018", color:"#ff9900", fontSize:"7px", marginLeft:"4px" }}>🔒 TRAILING</span>}
                </div>
                <div style={{ display:"flex", alignItems:"center", gap:"8px" }}>
                  <span style={{ fontSize:"8px", color:"#2d3748" }}>since {position.open_ts}</span>
                  <button className="btn btn-d" onClick={handleClose} style={{ padding:"3px 8px", fontSize:"9px", color:"#ff9900", borderColor:"#ff990033" }}>✕ CLOSE</button>
                </div>
              </div>
              <div style={{ display:"grid", gridTemplateColumns:"repeat(5,1fr)", gap:"6px" }}>
                {[
                  { label:"ENTRY",       val:`$${position.entry?.toLocaleString()}`,             color:"#e2e8f0" },
                  { label:"TAKE PROFIT", val:`$${position.tp?.toLocaleString()}`,                color:"#00ff88" },
                  { label:"STOP LOSS",   val:`$${position.sl?.toLocaleString()}`,                color:"#ff3366" },
                  { label:"SIZE",        val:`$${(position.usd_size||0).toFixed(2)}`,            color:"#00d4ff" },
                  { label:"UNREALIZED",  val:`${unrealized>=0?"+":""}$${unrealized.toFixed(2)}`, color:unrealized>=0?"#00ff88":"#ff3366" },
                ].map(s => (
                  <div key={s.label} style={{ background:"#06060f", borderRadius:"4px", padding:"6px", textAlign:"center" }}>
                    <div style={{ fontSize:"7px", color:"#2d3748", marginBottom:"2px" }}>{s.label}</div>
                    <div style={{ fontSize:"10px", fontWeight:"700", color:s.color }}>{s.val}</div>
                  </div>
                ))}
              </div>
              <div style={{ marginTop:"8px" }}>
                <div style={{ display:"flex", justifyContent:"space-between", fontSize:"8px", color:"#2d3748", marginBottom:"3px" }}>
                  <span>SL {((Math.abs(position.entry-position.sl)/Math.max(position.entry,1))*100).toFixed(2)}% away</span>
                  <span>TP {((Math.abs(position.tp-position.entry)/Math.max(position.entry,1))*100).toFixed(2)}% away</span>
                </div>
                <div style={{ height:"4px", background:"#131828", borderRadius:"2px", overflow:"hidden" }}>
                  <div style={{ height:"100%", width:`${Math.max(0,Math.min(100,((position.side==="buy"?price-position.sl:position.sl-price)/Math.max(Math.abs(position.tp-position.sl),1))*100))}%`, background:unrealized>=0?"#00ff88":"#ff3366", transition:"width 0.5s", borderRadius:"2px" }} />
                </div>
              </div>
            </div>
          ) : (
            <div className="card" style={{ textAlign:"center", padding:"18px", color:"#1e2535", fontSize:"10px", letterSpacing:"1px" }}>
              ○ NO OPEN POSITION — {botOn ? "Scanning for entry signal..." : "Start bot to begin"}
            </div>
          )}
        </div>

        {/* ═══ RIGHT ═══ */}
        <div className="col">
          {/* Risk Monitor */}
          <div className="card">
            <div style={{ fontSize:"8px", color:"#2d3748", letterSpacing:"2px", marginBottom:"8px" }}>RISK MONITOR</div>
            {[
              { label:"DAILY LOSS",  val:`${dailyLossPct.toFixed(1)}%`, limit:"5% limit",      pct:dailyLossPct/5*100,                                 color:"#ff3366" },
              { label:"GROWTH",      val:`${((account.balance/START_BAL-1)*100).toFixed(1)}%`, limit:`from $${START_BAL}`, pct:Math.min(100,(account.balance/START_BAL-1)*100), color:"#00ff88" },
              { label:"CONSEC LOSS", val:`${consecLosses}`, limit:`/ ${5} max`, pct:consecLosses/5*100, color: consecLosses >= 3 ? "#ff3366" : "#ff9900" },
            ].map(r => (
              <div key={r.label} style={{ marginBottom:"8px" }}>
                <div style={{ display:"flex", justifyContent:"space-between", fontSize:"9px", marginBottom:"3px" }}>
                  <span style={{ color:"#4a5568" }}>{r.label}</span>
                  <span style={{ color:r.pct>80?"#ff3366":r.color, fontWeight:"700" }}>{r.val} <span style={{ color:"#2d3748" }}>{r.limit}</span></span>
                </div>
                <div style={{ height:"3px", background:"#131828", borderRadius:"2px", overflow:"hidden" }}>
                  <div style={{ height:"100%", width:`${Math.max(0,Math.min(100,r.pct))}%`, background:r.pct>80?"#ff3366":r.color, transition:"width 0.5s", borderRadius:"2px" }} />
                </div>
              </div>
            ))}
            <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:"6px", marginTop:"4px" }}>
              {[
                { label:"TRADES",   val:trades.length,                                                                  color:"#e2e8f0" },
                { label:"WIN RATE", val:`${winRate}%`,                                                                  color:winRate>=50?"#00ff88":"#ff3366" },
                { label:"BEST",     val:trades.length?`+$${Math.max(...trades.map(t=>t.pnl)).toFixed(2)}`:"--",       color:"#00ff88" },
                { label:"WORST",    val:trades.length?`$${Math.min(...trades.map(t=>t.pnl)).toFixed(2)}`:"--",        color:"#ff3366" },
              ].map(s => (
                <div key={s.label} style={{ background:"#06060f", padding:"6px", borderRadius:"4px" }}>
                  <div style={{ fontSize:"7px", color:"#2d3748" }}>{s.label}</div>
                  <div style={{ fontFamily:"'Chakra Petch',sans-serif", fontSize:"13px", fontWeight:"700", color:s.color }}>{s.val}</div>
                </div>
              ))}
            </div>
          </div>

          {/* Trade History */}
          <div className="card" style={{ flex:"1 1 0", display:"flex", flexDirection:"column", overflow:"hidden", minHeight:"150px" }}>
            <div style={{ fontSize:"8px", color:"#2d3748", letterSpacing:"2px", marginBottom:"6px" }}>TRADE HISTORY</div>
            <div style={{ flex:"1 1 0", overflowY:"auto" }}>
              {trades.length === 0
                ? <div style={{ textAlign:"center", padding:"20px", color:"#1e2535", fontSize:"10px" }}>No trades yet — start the bot</div>
                : trades.map(tr => (
                  <div key={tr.id} className="trow fadein" style={{ fontSize:"10px" }}>
                    <div>
                      <span className="tag" style={{ background:tr.side==="buy"?"#00ff8818":"#ff336618", color:tr.side==="buy"?"#00ff88":"#ff3366", marginRight:"5px" }}>
                        {tr.side==="buy"?"▲":"▼"} {tr.side?.toUpperCase()}
                      </span>
                      <span style={{ color:"#1e2535", fontSize:"8px" }}>{tr.ts}</span>
                    </div>
                    <div style={{ textAlign:"right" }}>
                      <div style={{ fontWeight:"700", color:tr.win?"#00ff88":"#ff3366" }}>{tr.pnl>=0?"+":""}${(+tr.pnl).toFixed(2)}</div>
                      <div style={{ fontSize:"8px", color:"#2d3748" }}>{tr.reason}</div>
                    </div>
                  </div>
                ))
              }
            </div>
          </div>

          {/* Activity Log */}
          <div className="card" style={{ flex:"1 1 0", display:"flex", flexDirection:"column", overflow:"hidden", minHeight:"150px" }}>
            <div style={{ display:"flex", alignItems:"center", gap:"6px", marginBottom:"6px" }}>
              <span style={{ fontSize:"8px", color:"#2d3748", letterSpacing:"2px" }}>ACTIVITY LOG</span>
              {(botOn||connected) && <span className="blink" style={{ fontSize:"8px", color:"#00ff88" }}>● LIVE</span>}
              {demoMode && <span style={{ fontSize:"8px", color:"#ff9900" }}>DEMO</span>}
            </div>
            <div style={{ flex:"1 1 0", overflowY:"auto" }}>
              {logs.map((e, i) => (
                <div key={i} className="logrow" style={{ fontSize:"9px", lineHeight:"1.5" }}>
                  <span style={{ color:"#1e2535", marginRight:"5px" }}>{e.ts}</span>
                  <span style={{ color:{success:"#00ff88",error:"#ff3366",warning:"#ff9900",claude:"#8b5cf6",sell:"#ff6688",dim:"#2d3748"}[e.type]||"#4a5568" }}>{e.msg}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
