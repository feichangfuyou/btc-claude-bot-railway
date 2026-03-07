import AnimatedNumber from "../AnimatedNumber.jsx";
import { 
  ArrowUp, ArrowDown, Hand, Rocket, Smile, Zap, AlertTriangle, 
  Download, Camera, X, Box, Diamond, Circle, HelpCircle
} from "lucide-react";

export function TerminalBrainPanel({
  thinking, botOn, countdown, decision, lastCall, lastAiBlockReason,
  pendingDecision, pendingExpiresAt, pendingCountdown,
  handleApprovePending, handleRejectPending,
}) {
  return (
    <div className="card" style={{ border: "1px solid #D4AF3722", boxShadow: thinking ? "0 0 30px #D4AF3744" : "0 0 12px #D4AF3710" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "14px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
          <span className="dot" style={{ background: thinking ? "#D4AF37" : botOn ? "#00E676" : "#3a3a3a", animation: (thinking || botOn) ? "pulse 1.5s infinite" : "none", boxShadow: `0 0 8px ${thinking ? "#D4AF37" : botOn ? "#00E676" : "transparent"}` }} />
          <span className="section-label">NEURAL ENGINE</span>
        </div>
        {botOn && !thinking && <span style={{ fontSize: "10px", color: "#3a3a3a" }}>next: <AnimatedNumber value={countdown} format={(v) => `${Math.round(v)}s`} duration={150} /></span>}
        {thinking && <span className="blink" style={{ fontSize: "10px", color: "#D4AF37" }}>analyzing...</span>}
      </div>

      {/* Pending trade (approval required) */}
      {pendingDecision && (
        <div className="card fadein" style={{ border: "2px solid #ff9900", background: "#ff990008", marginBottom: "14px" }}>
          <div style={{ fontFamily: "'Montserrat', sans-serif", fontSize: "16px", color: "#ff9900", letterSpacing: "3px", marginBottom: "12px" }}>
            PENDING TRADE — AWAITING YOUR CALL
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: "10px", marginBottom: "10px" }}>
            <span className="tag" style={{
              background: pendingDecision.action === "buy" ? "#00E67620" : "#FF174420",
              color: pendingDecision.action === "buy" ? "#00E676" : "#FF1744",
              fontSize: "12px", padding: "4px 12px"
            }}>
              {pendingDecision.action === "buy" ? <ArrowUp size={12} style={{ marginRight: 4 }} /> : <ArrowDown size={12} style={{ marginRight: 4 }} />}
              {pendingDecision.action === "buy" ? "BUY" : "SELL"} {pendingDecision.symbol || ""}
            </span>
            {pendingExpiresAt > 0 && (
              <span style={{ fontSize: "10px", color: "#ff9900" }}>
                Expires in <AnimatedNumber value={pendingCountdown} format={(v) => `${Math.round(v)}s`} duration={150} />
              </span>
            )}
          </div>
          {pendingDecision.reasoning && (
            <div style={{ fontSize: "11px", color: "#999999", lineHeight: "1.6", marginBottom: "12px", fontStyle: "italic" }}>
              &ldquo;{String(pendingDecision.reasoning).slice(0, 120)}&rdquo;
            </div>
          )}
          {pendingDecision.order && (
            <div style={{ background: "#0A0A0A", borderRadius: "5px", padding: "10px 12px", border: "1px solid #1e1e1e", marginBottom: "12px" }}>
              {[
                { label: "ENTRY", val: `$${(pendingDecision.order.entry_price || 0).toLocaleString()}`, color: "#D4AF37" },
                { label: "TP", val: `$${(pendingDecision.order.take_profit || 0).toLocaleString()}`, color: "#00E676" },
                { label: "SL", val: `$${(pendingDecision.order.stop_loss || 0).toLocaleString()}`, color: "#FF1744" },
                { label: "SIZE", val: `${pendingDecision.order.size_percent || 0}%`, color: "#999999" },
              ].map(r => (
                <div key={r.label} className="row" style={{ fontSize: "11px" }}>
                  <span style={{ color: "#3a3a3a" }}>{r.label}</span>
                  <span style={{ color: r.color, fontWeight: "700" }}>{r.val}</span>
                </div>
              ))}
            </div>
          )}
          <div style={{ display: "flex", gap: "10px" }}>
            <button className="btn btn-g" onClick={handleApprovePending} style={{ flex: 1 }}>APPROVE</button>
            <button className="btn btn-r" onClick={handleRejectPending} style={{ flex: 1 }}>REJECT</button>
          </div>
        </div>
      )}

      {decision ? (
        <div className="fadein">
          <div style={{ display: "flex", alignItems: "center", gap: "10px", marginBottom: "12px" }}>
            <span className="tag" style={{
              background: { buy: "#00E67620", sell: "#FF174420", wait: "#ffffff10", close_all: "#ff990020" }[decision.action] || "#ffffff10",
              color: { buy: "#00E676", sell: "#FF1744", wait: "#5C5C5C", close_all: "#ff9900" }[decision.action] || "#5C5C5C",
              fontSize: "12px", padding: "4px 12px", fontFamily: "'Montserrat', sans-serif", letterSpacing: "2px"
            }}>
              <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
                {decision.action === "buy" && <Rocket size={12} />}
                {decision.action === "sell" && <Smile size={12} />}
                {decision.action === "wait" && <Hand size={12} />}
                {decision.action === "close_all" && <Rocket size={12} style={{ transform: 'rotate(90deg)' }} />}
                {{ buy: "BUY", sell: "SELL", wait: "WAIT", close_all: "CLOSE ALL" }[decision.action] || decision.action?.toUpperCase()}
              </span>
              {decision.symbol && decision.action !== "wait" && <span style={{ marginLeft: "4px" }}>{decision.symbol}</span>}
            </span>
            {decision.confidence != null && (
              <div style={{ flex: 1 }}>
                <div style={{ height: "6px", background: "#1a1a1a", borderRadius: "3px", overflow: "hidden", border: "1px solid #2a2a2a" }}>
                  <div style={{ height: "100%", width: `${decision.confidence * 100}%`, background: decision.confidence > 0.7 ? "linear-gradient(90deg,#D4AF37,#00E676)" : decision.confidence > 0.5 ? "linear-gradient(90deg,#D4AF37,#ff9900)" : "linear-gradient(90deg,#C0392B,#FF1744)", transition: "width 0.6s", borderRadius: "2px" }} />
                </div>
                <div style={{ fontSize: "10px", color: "#5C5C5C", marginTop: "2px", fontFamily: "'Montserrat', sans-serif", letterSpacing: "1px" }}><AnimatedNumber value={decision.confidence * 100} format={(v) => `${v.toFixed(0)}%`} duration={250} /> POWER</div>
              </div>
            )}
          </div>
          <div style={{ fontFamily: "'Playfair Display',serif", fontSize: "11px", color: "#D4D4D4", lineHeight: "1.8", borderLeft: "3px solid #D4AF3744", paddingLeft: "10px", marginBottom: "14px", fontStyle: "italic" }}>
            &ldquo;{decision.reasoning}&rdquo;
          </div>
          {lastAiBlockReason && (
            <div style={{ fontSize: "10px", color: "#ff9900", lineHeight: "1.5", background: "#ff990008", border: "1px solid #ff990033", borderRadius: "5px", padding: "8px 10px", marginBottom: "14px" }}>
              <AlertTriangle size={10} style={{ marginRight: 4 }} /> {lastAiBlockReason}
            </div>
          )}
          {decision.order && (
            <div style={{ background: "#0A0A0A", borderRadius: "5px", padding: "10px 12px", border: "1px solid #1e1e1e" }}>
              {[
                { label: "ENTRY", val: `$${(decision.order.entry_price || 0).toLocaleString()}`, color: "#D4AF37" },
                { label: "TAKE PROFIT", val: `$${(decision.order.take_profit || 0).toLocaleString()}`, color: "#00E676" },
                { label: "STOP LOSS", val: `$${(decision.order.stop_loss || 0).toLocaleString()}`, color: "#FF1744" },
                { label: "SIZE", val: `${decision.order.size_percent || 0}% of balance`, color: "#999999" },
              ].map(r => (
                <div key={r.label} className="row" style={{ fontSize: "11px" }}>
                  <span style={{ color: "#3a3a3a" }}>{r.label}</span>
                  <span style={{ color: r.color, fontWeight: "700" }}>{r.val}</span>
                </div>
              ))}
            </div>
          )}
          <div style={{ fontSize: "9px", color: "#2a2a2a", marginTop: "10px", textAlign: "right" }}>LAST CALL: {lastCall}</div>
        </div>
      ) : (
        <div style={{ textAlign: "center", padding: "20px 0", color: "#3a3a3a", fontSize: "11px", lineHeight: "2.2" }}>
          {botOn
            ? <span className="blink" style={{ color: "#D4AF37" }}>First analysis in <AnimatedNumber value={countdown} format={(v) => `${Math.round(v)}s`} duration={150} />...</span>
            : <span>Press <span style={{ color: "#D4AF37" }}>🕶 RELOAD TERMINAL</span> or <span style={{ color: "#D4AF37" }}>ANALYZE</span></span>
          }
        </div>
      )}
    </div>
  );
}

export function MarketRegimePanel({ regime, fearGreed }) {
  const condColor = { ranging: "#D4AF37", trending_up: "#00E676", trending_down: "#FF1744", chaotic: "#ff9900" }[regime] || "#5C5C5C";
  const condLabel = { ranging: "RANGING", trending_up: "TRENDING UP", trending_down: "TRENDING DOWN", chaotic: "CHAOTIC" }[regime] || regime;
  const condIcon = { ranging: <Box size={14} />, trending_up: <ArrowUp size={14} />, trending_down: <ArrowDown size={14} />, chaotic: <Zap size={14} /> }[regime] || null;
  const fgColor = fearGreed.value < 25 ? "#FF1744" : fearGreed.value < 50 ? "#ff9900" : fearGreed.value < 75 ? "#D4AF37" : "#00E676";

  return (
    <div className="card">
      <div className="section-label" style={{ marginBottom: "10px" }}>MARKET REGIME</div>
      <div style={{ padding: "12px", borderRadius: "5px", background: `${condColor}11`, border: `1px solid ${condColor}22`, textAlign: "center", marginBottom: "12px" }}>
        <span style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: "8px", fontFamily: "'Montserrat', sans-serif", color: condColor, fontSize: "16px", letterSpacing: "3px" }}>
          {condIcon} {condLabel}
        </span>
      </div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <span style={{ fontSize: "10px", color: "#5C5C5C" }}>FEAR & GREED</span>
        <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
          <div style={{ width: "60px", height: "3px", background: "#1e1e1e", borderRadius: "2px", overflow: "hidden" }} role="progressbar" aria-valuenow={fearGreed.value} aria-valuemin={0} aria-valuemax={100} aria-label="Fear and Greed Index">
            <div style={{ height: "100%", width: `${fearGreed.value}%`, background: `linear-gradient(to right, #FF1744, #ff9900, #00E676)`, borderRadius: "2px" }} />
          </div>
          <span style={{ fontSize: "10px", fontWeight: "700", color: fgColor }}><AnimatedNumber value={fearGreed.value} format={(v) => `${Math.round(v)}`} duration={300} /> {fearGreed.label}</span>
        </div>
      </div>
    </div>
  );
}

export function AgentKitPanel({ agentKit, isLiveMode }) {
  if (!isLiveMode) return null;

  return (
    <div className="card" style={{ border: agentKit.agentkit_ready ? "1px solid #D4AF3722" : "1px solid #1e1e1e", boxShadow: agentKit.agentkit_ready ? "0 0 12px #D4AF3710" : "none" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "12px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
          <span className="dot" style={{ background: agentKit.agentkit_ready ? "#D4AF37" : "#3a3a3a", boxShadow: agentKit.agentkit_ready ? "0 0 8px #D4AF37" : "none" }} />
          <span style={{ fontFamily: "'Montserrat', sans-serif", fontSize: "11px", color: "#D4AF37", fontWeight: "700", letterSpacing: "2px" }}>AGENTKIT WALLET</span>
        </div>
        <span style={{ fontSize: "9px", color: agentKit.agentkit_ready ? "#D4AF37" : "#FF1744" }}>
          {agentKit.agentkit_ready ? "ON-CHAIN" : "OFFLINE"}
        </span>
      </div>
      {agentKit.agentkit_ready ? (
        <div>
          <div className="row" style={{ fontSize: "11px" }}>
            <span style={{ color: "#3a3a3a" }}>ADDRESS</span>
            <span style={{ color: "#D4AF37", fontFamily: "monospace", fontSize: "10px" }}>
              {agentKit.wallet_address ? `${agentKit.wallet_address.slice(0, 6)}...${agentKit.wallet_address.slice(-4)}` : "--"}
            </span>
          </div>
          <div className="row" style={{ fontSize: "11px" }}>
            <span style={{ color: "#3a3a3a" }}>NETWORK</span>
            <span style={{ color: "#D4D4D4", fontWeight: "700" }}>{agentKit.network || "--"}</span>
          </div>
          {agentKit.eth_balance && (
            <div className="row" style={{ fontSize: "11px" }}>
              <span style={{ color: "#3a3a3a" }}>ETH</span>
              <span style={{ color: "#D4D4D4", fontWeight: "700" }}>{agentKit.eth_balance}</span>
            </div>
          )}
          {agentKit.usdc_balance && (
            <div className="row" style={{ fontSize: "11px" }}>
              <span style={{ color: "#3a3a3a" }}>USDC</span>
              <span style={{ color: "#00E676", fontWeight: "700" }}>{agentKit.usdc_balance}</span>
            </div>
          )}
        </div>
      ) : (
        <div style={{ fontSize: "10px", color: "#3a3a3a", textAlign: "center", padding: "6px 0" }}>
          {agentKit.error ? `${agentKit.error}` : "Set CDP keys in .env for on-chain trading"}
        </div>
      )}
    </div>
  );
}

export function IndicatorsPanel({ indic, history }) {
  return (
    <div className="card">
      <div className="section-label" style={{ marginBottom: "10px" }}>LIVE INDICATORS</div>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0 20px" }}>
        {[
          { label: "EMA 9", num: indic.ema9, fmt: (v) => `$${v.toLocaleString()}`, fallback: "warming\u2026", color: "#00E676" },
          { label: "EMA 21", num: indic.ema21, fmt: (v) => `$${v.toLocaleString()}`, fallback: "warming\u2026", color: "#D4AF37" },
          { label: "RSI 14", num: indic.ema9 ? indic.rsi : null, fmt: (v) => `${v.toFixed(1)}${v > 70 ? " OB" : v < 30 ? " OS" : ""}`, fallback: "-", color: indic.rsi > 70 ? "#FF1744" : indic.rsi < 30 ? "#00E676" : "#D4D4D4" },
          { label: "ATR 14", num: indic.ema9 ? indic.atr : null, fmt: (v) => `$${v.toFixed(2)}`, fallback: "-", color: indic.atr > 500 ? "#ff9900" : "#D4D4D4" },
          { label: "BB UPPER", num: indic.bb_upper, fmt: (v) => `$${v.toLocaleString()}`, fallback: "-", color: "#FF1744" },
          { label: "BB MID", num: indic.bb_middle, fmt: (v) => `$${v.toLocaleString()}`, fallback: "-", color: "#64748b" },
          { label: "BB LOWER", num: indic.bb_lower, fmt: (v) => `$${v.toLocaleString()}`, fallback: "-", color: "#00E676" },
          { label: "BB WIDTH", num: indic.bb_width || null, fmt: (v) => `${v.toFixed(4)}%`, fallback: "-", color: "#ff9900" },
          { label: "VWAP", num: indic.vwap, fmt: (v) => `$${v.toLocaleString()}`, fallback: "-", color: "#D4AF37" },
          { label: "MACD", num: indic.macd, fmt: (v) => `${v.toFixed(2)}`, fallback: "-", color: (indic.macd || 0) >= 0 ? "#00E676" : "#FF1744" },
          { label: "MACD SIG", num: indic.macd_signal, fmt: (v) => `${v.toFixed(2)}`, fallback: "-", color: "#ff9900" },
          { label: "MACD HIST", num: indic.macd_histogram, fmt: (v) => `${v.toFixed(2)}`, fallback: "-", color: (indic.macd_histogram || 0) >= 0 ? "#00E676" : "#FF1744" },
          { label: "MOMENTUM", num: indic.momentum, fmt: (v) => `${v.toFixed(2)}%`, fallback: "-", color: (indic.momentum || 0) >= 0 ? "#00E676" : "#FF1744" },
        ].map(ind => (
          <div key={ind.label} className="row" style={{ fontSize: "11px" }}>
            <span style={{ color: "#3a3a3a" }}>{ind.label}</span>
            <span style={{ color: ind.color, fontWeight: "700" }}>
              {ind.num != null ? <AnimatedNumber value={ind.num} format={ind.fmt} duration={180} /> : ind.fallback}
            </span>
          </div>
        ))}
      </div>
      <div style={{ marginTop: "10px", fontSize: "9px", color: "#2a2a2a", textAlign: "center" }}>
        {history.length < 9 ? `Building: ${history.length}/9 candles` : `${history.length} candles loaded`}
      </div>
    </div>
  );
}

export function RiskMonitorPanel({ account, startBal, trades, winRate }) {
  const dailyLossPct = Math.abs(Math.min(0, account.daily_pnl) / Math.max(account.balance, 1) * 100);

  return (
    <div className="card">
      <div className="section-label" style={{ marginBottom: "10px" }}>RISK MONITOR</div>
      {[
        { label: "DAILY LOSS", num: dailyLossPct, fmt: (v) => `${v.toFixed(1)}%`, limit: "5% limit", pct: dailyLossPct / 5 * 100, color: "#FF1744" },
        { label: "GROWTH", num: (account.balance / startBal - 1) * 100, fmt: (v) => `${v.toFixed(1)}%`, limit: `from $${startBal}`, pct: Math.min(100, Math.max(0, (account.balance / startBal - 1) * 100)), color: "#00E676" },
      ].map(r => (
        <div key={r.label} style={{ marginBottom: "12px" }}>
          <div style={{ display: "flex", justifyContent: "space-between", fontSize: "10px", marginBottom: "5px" }}>
            <span style={{ color: "#5C5C5C" }}>{r.label}</span>
            <span style={{ color: r.pct > 80 ? "#FF1744" : r.color, fontWeight: "700" }}><AnimatedNumber value={r.num} format={r.fmt} duration={200} /> <span style={{ color: "#3a3a3a" }}>{r.limit}</span></span>
          </div>
          <div style={{ height: "3px", background: "#1e1e1e", borderRadius: "2px", overflow: "hidden" }}>
            <div style={{ height: "100%", width: `${Math.max(0, Math.min(100, r.pct))}%`, background: r.pct > 80 ? "#FF1744" : r.color, transition: "width 0.5s", borderRadius: "2px" }} />
          </div>
        </div>
      ))}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "8px", marginTop: "6px" }}>
        {[
          { label: "TRADES", num: trades.length, fmt: (v) => `${Math.round(v)}`, color: "#D4D4D4" },
          { label: "WIN RATE", num: winRate, fmt: (v) => `${Math.round(v)}%`, color: winRate >= 50 ? "#00E676" : "#FF1744" },
          { label: "BEST", num: trades.length ? Math.max(...trades.map(t => t.pnl)) : null, fmt: (v) => `+$${v.toFixed(2)}`, color: "#00E676" },
          { label: "WORST", num: trades.length ? Math.min(...trades.map(t => t.pnl)) : null, fmt: (v) => `$${v.toFixed(2)}`, color: "#FF1744" },
        ].map(s => (
          <div key={s.label} style={{ background: "#0A0A0A", padding: "8px", borderRadius: "5px" }}>
            <div style={{ fontSize: "9px", color: "#3a3a3a", marginBottom: "2px" }}>{s.label}</div>
            <div style={{ fontFamily: "'Montserrat', sans-serif", fontSize: "13px", fontWeight: "700", color: s.color }}>
              {s.num != null ? <AnimatedNumber value={s.num} format={s.fmt} duration={200} /> : "--"}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export function RecentTradesPanel({
  trades, connected, exportTrades, tradeTypeBadge, openTradeDetail,
  setShowHistory, fetchHistory, tradesContainerRef,
}) {
  return (
    <div className="card" style={{ flex: "1 1 0", display: "flex", flexDirection: "column", overflow: "hidden", minHeight: "180px" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "10px" }}>
        <span className="section-label">THE RECORD</span>
        <div style={{ display: "flex", gap: "6px" }}>
          {trades.length > 0 && (
            <button className="btn btn-d" onClick={() => exportTrades()} style={{ display: "flex", alignItems: "center", gap: "4px", padding: "2px 6px", fontSize: "9px" }} aria-label="Export trade history as CSV"><Download size={10} /> CSV</button>
          )}
          {connected && (
            <button className="btn btn-d" onClick={() => { setShowHistory(true); fetchHistory(0); }} style={{ padding: "2px 6px", fontSize: "9px", color: "#D4AF37", borderColor: "#D4AF3733" }} aria-label="View full trade history">ALL HISTORY</button>
          )}
        </div>
      </div>
      <div ref={tradesContainerRef} style={{ flex: "1 1 0", overflowY: "auto" }}>
        {trades.length === 0
          ? <div style={{ textAlign: "center", padding: "20px", color: "#2a2a2a", fontSize: "11px" }}>No trades yet — start the bot</div>
          : trades.map(tr => (
            <div key={tr.id} className="trow fadein" style={{ fontSize: "11px", cursor: "pointer" }}
              onClick={() => openTradeDetail(tr)} title="Click to view trade chart">
              <div>
                <span className="tag" style={{ display: "flex", alignItems: "center", gap: "4px", background: tr.side === "buy" ? "#00E67618" : "#FF174418", color: tr.side === "buy" ? "#00E676" : "#FF1744", marginRight: "5px" }}>
                  {tr.side === "buy" ? <ArrowUp size={10} /> : <ArrowDown size={10} />} {tr.side?.toUpperCase()}
                </span>
                <span style={{ color: "#D4AF37", fontSize: "9px", fontWeight: "700", marginRight: "4px" }}>{tr.symbol || "BTC"}</span>
                {tradeTypeBadge(tr)}
                <span style={{ color: "#2a2a2a", fontSize: "9px", marginLeft: "4px" }}>{tr.ts}</span>
              </div>
              <div style={{ textAlign: "right" }}>
                <div style={{ fontWeight: "700", color: tr.win ? "#00E676" : "#FF1744" }}>{tr.pnl >= 0 ? "+" : ""}${(+tr.pnl).toFixed(2)}</div>
                <div style={{ fontSize: "9px", color: "#3a3a3a", display: "flex", alignItems: "center", justifyContent: "flex-end", gap: "3px" }}>{tr.reason} <Camera size={10} style={{ color: "#D4AF3766" }} /></div>
              </div>
            </div>
          ))
        }
      </div>
    </div>
  );
}

export function ActivityLogPanel({ logs, botOn, connected, logsContainerRef }) {
  return (
    <div className="card" style={{ flex: "1 1 0", display: "flex", flexDirection: "column", overflow: "hidden", minHeight: "180px" }}>
      <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "10px" }}>
        <span className="section-label">MAMA'S BOY LOG</span>
        {(botOn || connected) && <span className="blink" style={{ fontSize: "9px", color: "#00E676" }}>LIVE</span>}
      </div>
      <div ref={logsContainerRef} style={{ flex: "1 1 0", overflowY: "auto" }} role="log" aria-label="Activity log">
        {logs.map((e) => (
          <div key={e.id} className="logrow" style={{ fontSize: "10px", lineHeight: "1.7" }}>
            <span style={{ color: "#2a2a2a", marginRight: "5px" }}>{e.ts}</span>
            <span style={{ color: { success: "#00E676", error: "#FF1744", warning: "#ff9900", claude: "#D4AF37", sell: "#ff6688", dim: "#3a3a3a" }[e.type] || "#5C5C5C" }}>
              <span aria-hidden="true" style={{ display: "inline-flex", alignItems: "center", width: "12px" }}>
                {({ 
                  success: <ArrowUp size={8} />, 
                  error: <X size={8} />, 
                  warning: <AlertTriangle size={8} />, 
                  claude: <Diamond size={8} />, 
                  sell: <ArrowDown size={8} />, 
                  dim: <Circle size={4} fill="currentColor" /> 
                })[e.type] || <HelpCircle size={8} />} 
              </span> 
              {e.msg}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
