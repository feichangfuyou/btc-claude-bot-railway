import { memo } from "react";
import AnimatedNumber from "../AnimatedNumber.jsx";
import { colors } from "../theme.js";
import {
  ArrowUp, ArrowDown, Hand, Rocket, Smile, Zap, AlertTriangle,
  Download, Camera, X, Box, Diamond, Circle, HelpCircle
} from "lucide-react";

export const TerminalEnginePanel = memo(function TerminalEnginePanel({
  thinking, botOn, countdown, decision, lastCall, lastAiBlockReason,
  pendingDecision, pendingExpiresAt, pendingCountdown,
  handleApprovePending, handleRejectPending,
}) {
  const engineDot = thinking ? colors.gold : botOn ? colors.success : colors.dim;

  return (
    <div className={`dash-panel${thinking ? " dash-panel--thinking" : ""}`}>
      <div className="dash-panel__header">
        <div className="dash-panel__header-left">
          <span
            className="dot"
            style={{
              background: engineDot,
              animation: (thinking || botOn) ? "pulse 1.5s infinite" : "none",
            }}
          />
          <span className="section-label">ANALYSIS ENGINE</span>
        </div>
        {botOn && !thinking && (
          <span className="dash-panel__meta">
            next: <AnimatedNumber value={countdown} format={(v) => `${Math.round(v)}s`} duration={150} />
          </span>
        )}
        {thinking && <span className="blink dash-panel__meta" style={{ color: colors.gold }}>analyzing...</span>}
      </div>

      {pendingDecision && (
        <div className="dash-panel dash-panel--nested dash-panel--pending fadein">
          <div className="dash-panel__pending-title">PENDING TRADE — AWAITING YOUR CALL</div>
          <div className="dash-panel__pending-row">
            <span
              className="tag"
              style={{
                background: pendingDecision.action === "buy" ? "#00E67620" : "#FF174420",
                color: pendingDecision.action === "buy" ? colors.success : colors.error,
                fontSize: "12px",
                padding: "4px 12px",
              }}
            >
              {pendingDecision.action === "buy" ? <ArrowUp size={12} style={{ marginRight: 4 }} /> : <ArrowDown size={12} style={{ marginRight: 4 }} />}
              {pendingDecision.action === "buy" ? "BUY" : "SELL"} {pendingDecision.symbol || ""}
            </span>
            {pendingExpiresAt > 0 && (
              <span style={{ fontSize: "10px", color: colors.warning }}>
                Expires in <AnimatedNumber value={pendingCountdown} format={(v) => `${Math.round(v)}s`} duration={150} />
              </span>
            )}
          </div>
          {pendingDecision.reasoning && (
            <div className="dash-panel__quote" style={{ fontStyle: "italic", marginBottom: "8px" }}>
              &ldquo;{String(pendingDecision.reasoning).slice(0, 120)}&rdquo;
            </div>
          )}
          {pendingDecision.order && (
            <div className="detail-box" style={{ marginBottom: "8px" }}>
              {[
                { label: "ENTRY", val: `$${(pendingDecision.order.entry_price || 0).toLocaleString()}`, color: colors.gold },
                { label: "TP", val: `$${(pendingDecision.order.take_profit || 0).toLocaleString()}`, color: colors.success },
                { label: "SL", val: `$${(pendingDecision.order.stop_loss || 0).toLocaleString()}`, color: colors.error },
                { label: "SIZE", val: `${pendingDecision.order.size_percent || 0}%`, color: colors.muted },
              ].map(r => (
                <div key={r.label} className="row">
                  <span style={{ color: colors.dim }}>{r.label}</span>
                  <span style={{ color: r.color, fontWeight: "700" }}>{r.val}</span>
                </div>
              ))}
            </div>
          )}
          <div className="dash-panel__pending-actions">
            <button className="btn btn-g" onClick={handleApprovePending}>APPROVE</button>
            <button className="btn btn-r" onClick={handleRejectPending}>REJECT</button>
          </div>
        </div>
      )}

      {decision ? (
        <div className="fadein">
          <div className="dash-panel__decision-row">
            <span
              className="tag"
              style={{
                background: { buy: "#00E67620", sell: "#FF174420", wait: "#ffffff10", close_all: "#ff990020" }[decision.action] || "#ffffff10",
                color: { buy: colors.success, sell: colors.error, wait: colors.muted, close_all: colors.warning }[decision.action] || colors.muted,
                fontSize: "12px",
                padding: "4px 12px",
                letterSpacing: "2px",
              }}
            >
              <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
                {decision.action === "buy" && <Rocket size={12} />}
                {decision.action === "sell" && <Smile size={12} />}
                {decision.action === "wait" && <Hand size={12} />}
                {decision.action === "close_all" && <Rocket size={12} style={{ transform: "rotate(90deg)" }} />}
                {{ buy: "BUY", sell: "SELL", wait: "WAIT", close_all: "CLOSE ALL" }[decision.action] || decision.action?.toUpperCase()}
              </span>
              {decision.symbol && decision.action !== "wait" && <span style={{ marginLeft: "4px" }}>{decision.symbol}</span>}
            </span>
            {decision.confidence != null && (
              <div className="dash-panel__confidence">
                <div className="dash-panel__confidence-track">
                  <div
                    className="dash-panel__confidence-fill"
                    style={{
                      width: `${decision.confidence * 100}%`,
                      background: decision.confidence > 0.7
                        ? "linear-gradient(90deg,#D4AF37,#00E676)"
                        : decision.confidence > 0.5
                          ? "linear-gradient(90deg,#D4AF37,#ff9900)"
                          : "linear-gradient(90deg,#C0392B,#FF1744)",
                    }}
                  />
                </div>
                <div className="dash-panel__confidence-label">
                  <AnimatedNumber value={decision.confidence * 100} format={(v) => `${v.toFixed(0)}%`} duration={250} /> POWER
                </div>
              </div>
            )}
          </div>
          <div className="dash-panel__quote">&ldquo;{decision.reasoning}&rdquo;</div>
          {lastAiBlockReason && (
            <div className="dash-panel__warn">
              <AlertTriangle size={10} style={{ marginRight: 4 }} /> {lastAiBlockReason}
            </div>
          )}
          {decision.order && (
            <div className="detail-box">
              {[
                { label: "ENTRY", val: `$${(decision.order.entry_price || 0).toLocaleString()}`, color: colors.gold },
                { label: "TAKE PROFIT", val: `$${(decision.order.take_profit || 0).toLocaleString()}`, color: colors.success },
                { label: "STOP LOSS", val: `$${(decision.order.stop_loss || 0).toLocaleString()}`, color: colors.error },
                { label: "SIZE", val: `${decision.order.size_percent || 0}% of balance`, color: colors.muted },
              ].map(r => (
                <div key={r.label} className="row">
                  <span style={{ color: colors.dim }}>{r.label}</span>
                  <span style={{ color: r.color, fontWeight: "700" }}>{r.val}</span>
                </div>
              ))}
            </div>
          )}
          <div className="dash-panel__meta dash-panel__meta--right">LAST CALL: {lastCall}</div>
        </div>
      ) : (
        <div className="dash-panel__empty">
          {botOn
            ? <span className="blink" style={{ color: colors.gold }}>First analysis in <AnimatedNumber value={countdown} format={(v) => `${Math.round(v)}s`} duration={150} />...</span>
            : <span>Press <span style={{ color: colors.gold }}>🕶 RELOAD TERMINAL</span> or <span style={{ color: colors.gold }}>ANALYZE</span></span>
          }
        </div>
      )}
    </div>
  );
});

export const MarketRegimePanel = memo(function MarketRegimePanel({ regime, fearGreed }) {
  const condColor = { ranging: colors.gold, trending_up: colors.success, trending_down: colors.error, chaotic: colors.warning }[regime] || colors.muted;
  const condLabel = { ranging: "RANGING", trending_up: "TRENDING UP", trending_down: "TRENDING DOWN", chaotic: "CHAOTIC" }[regime] || regime;
  const condIcon = { ranging: <Box size={14} />, trending_up: <ArrowUp size={14} />, trending_down: <ArrowDown size={14} />, chaotic: <Zap size={14} /> }[regime] || null;
  const fgColor = fearGreed.value < 25 ? colors.error : fearGreed.value < 50 ? colors.warning : fearGreed.value < 75 ? colors.gold : colors.success;

  return (
    <div className="dash-panel">
      <div className="section-label">MARKET REGIME</div>
      <div className="regime-badge" style={{ background: `${condColor}11`, border: `1px solid ${condColor}22` }}>
        <span className="regime-badge__label" style={{ color: condColor }}>
          {condIcon} {condLabel}
        </span>
      </div>
      <div className="fg-row">
        <span className="fg-row__label">FEAR & GREED</span>
        <div className="fg-row__meter">
          <div className="fg-row__track" role="progressbar" aria-valuenow={fearGreed.value} aria-valuemin={0} aria-valuemax={100} aria-label="Fear and Greed Index">
            <div className="fg-row__fill" style={{ width: `${fearGreed.value}%` }} />
          </div>
          <span className="fg-row__value" style={{ color: fgColor }}>
            <AnimatedNumber value={fearGreed.value} format={(v) => `${Math.round(v)}`} duration={300} /> {fearGreed.label}
          </span>
        </div>
      </div>
    </div>
  );
});

export const AgentKitPanel = memo(function AgentKitPanel({ agentKit, isLiveMode }) {
  if (!isLiveMode) return null;

  return (
    <div className={`dash-panel${agentKit.agentkit_ready ? " dash-panel--ready" : ""}`}>
      <div className="dash-panel__header">
        <div className="dash-panel__header-left">
          <span
            className="dot"
            style={{
              background: agentKit.agentkit_ready ? colors.gold : colors.dim,
              boxShadow: agentKit.agentkit_ready ? `0 0 8px ${colors.gold}` : "none",
            }}
          />
          <span className="section-label" style={{ marginBottom: 0 }}>AGENTKIT WALLET</span>
        </div>
        <span className="dash-panel__meta" style={{ color: agentKit.agentkit_ready ? colors.gold : colors.error }}>
          {agentKit.agentkit_ready ? "ON-CHAIN" : "OFFLINE"}
        </span>
      </div>
      {agentKit.agentkit_ready ? (
        <div>
          <div className="row" style={{ fontSize: "11px" }}>
            <span style={{ color: colors.dim }}>ADDRESS</span>
            <span className="mono-text" style={{ color: colors.gold, fontSize: "10px" }}>
              {agentKit.wallet_address ? `${agentKit.wallet_address.slice(0, 6)}...${agentKit.wallet_address.slice(-4)}` : "--"}
            </span>
          </div>
          <div className="row" style={{ fontSize: "11px" }}>
            <span style={{ color: colors.dim }}>NETWORK</span>
            <span style={{ color: colors.text, fontWeight: "700" }}>{agentKit.network || "--"}</span>
          </div>
          {agentKit.eth_balance && (
            <div className="row" style={{ fontSize: "11px" }}>
              <span style={{ color: colors.dim }}>ETH</span>
              <span style={{ color: colors.text, fontWeight: "700" }}>{agentKit.eth_balance}</span>
            </div>
          )}
          {agentKit.usdc_balance && (
            <div className="row" style={{ fontSize: "11px" }}>
              <span style={{ color: colors.dim }}>USDC</span>
              <span style={{ color: colors.success, fontWeight: "700" }}>{agentKit.usdc_balance}</span>
            </div>
          )}
        </div>
      ) : (
        <div className="dash-panel__empty" style={{ padding: "6px 0" }}>
          {agentKit.error ? `${agentKit.error}` : "Set CDP keys in .env for on-chain trading"}
        </div>
      )}
    </div>
  );
});

export const IndicatorsPanel = memo(function IndicatorsPanel({ indic, history }) {
  return (
    <div className="dash-panel">
      <div className="section-label">LIVE INDICATORS</div>
      <div className="indicators-grid">
        {[
          { label: "EMA 9", num: indic.ema9, fmt: (v) => `$${v.toLocaleString()}`, fallback: "warming\u2026", color: colors.success },
          { label: "EMA 21", num: indic.ema21, fmt: (v) => `$${v.toLocaleString()}`, fallback: "warming\u2026", color: colors.gold },
          { label: "RSI 14", num: indic.ema9 ? indic.rsi : null, fmt: (v) => `${v.toFixed(1)}${v > 70 ? " OB" : v < 30 ? " OS" : ""}`, fallback: "-", color: indic.rsi > 70 ? colors.error : indic.rsi < 30 ? colors.success : colors.text },
          { label: "ATR 14", num: indic.ema9 ? indic.atr : null, fmt: (v) => `$${v.toFixed(2)}`, fallback: "-", color: indic.atr > 500 ? colors.warning : colors.text },
          { label: "BB UPPER", num: indic.bb_upper, fmt: (v) => `$${v.toLocaleString()}`, fallback: "-", color: colors.error },
          { label: "BB MID", num: indic.bb_middle, fmt: (v) => `$${v.toLocaleString()}`, fallback: "-", color: "#64748b" },
          { label: "BB LOWER", num: indic.bb_lower, fmt: (v) => `$${v.toLocaleString()}`, fallback: "-", color: colors.success },
          { label: "BB WIDTH", num: indic.bb_width || null, fmt: (v) => `${v.toFixed(4)}%`, fallback: "-", color: colors.warning },
          { label: "VWAP", num: indic.vwap, fmt: (v) => `$${v.toLocaleString()}`, fallback: "-", color: colors.gold },
          { label: "MACD", num: indic.macd, fmt: (v) => `${v.toFixed(2)}`, fallback: "-", color: (indic.macd || 0) >= 0 ? colors.success : colors.error },
          { label: "MACD SIG", num: indic.macd_signal, fmt: (v) => `${v.toFixed(2)}`, fallback: "-", color: colors.warning },
          { label: "MACD HIST", num: indic.macd_histogram, fmt: (v) => `${v.toFixed(2)}`, fallback: "-", color: (indic.macd_histogram || 0) >= 0 ? colors.success : colors.error },
          { label: "MOMENTUM", num: indic.momentum, fmt: (v) => `${v.toFixed(2)}%`, fallback: "-", color: (indic.momentum || 0) >= 0 ? colors.success : colors.error },
        ].map(ind => (
          <div key={ind.label} className="row">
            <span>{ind.label}</span>
            <span style={{ color: ind.color }}>
              {ind.num != null ? <AnimatedNumber value={ind.num} format={ind.fmt} duration={180} /> : ind.fallback}
            </span>
          </div>
        ))}
      </div>
      <div className="dash-panel__footer">
        {history.length < 9 ? `Building: ${history.length}/9 candles` : `${history.length} candles loaded`}
      </div>
    </div>
  );
});

export const RiskMonitorPanel = memo(function RiskMonitorPanel({ account, startBal, trades, winRate }) {
  const dailyLossPct = Math.abs(Math.min(0, account.daily_pnl) / Math.max(account.balance, 1) * 100);

  return (
    <div className="dash-panel">
      <div className="section-label">RISK MONITOR</div>
      {[
        { label: "DAILY LOSS", num: dailyLossPct, fmt: (v) => `${v.toFixed(1)}%`, limit: "5% limit", pct: dailyLossPct / 5 * 100, color: colors.error },
        { label: "GROWTH", num: (account.balance / startBal - 1) * 100, fmt: (v) => `${v.toFixed(1)}%`, limit: `from $${startBal}`, pct: Math.min(100, Math.max(0, (account.balance / startBal - 1) * 100)), color: colors.success },
      ].map(r => (
        <div key={r.label} className="risk-bar">
          <div className="risk-bar__head">
            <span style={{ color: colors.muted }}>{r.label}</span>
            <span style={{ color: r.pct > 80 ? colors.error : r.color, fontWeight: "700" }}>
              <AnimatedNumber value={r.num} format={r.fmt} duration={200} /> <span style={{ color: colors.dim }}>{r.limit}</span>
            </span>
          </div>
          <div className="risk-bar__track">
            <div
              className="risk-bar__fill"
              style={{
                width: `${Math.max(0, Math.min(100, r.pct))}%`,
                background: r.pct > 80 ? colors.error : r.color,
              }}
            />
          </div>
        </div>
      ))}
      <div className="stat-grid">
        {[
          { label: "TRADES", num: trades.length, fmt: (v) => `${Math.round(v)}`, color: colors.text },
          { label: "WIN RATE", num: winRate, fmt: (v) => `${Math.round(v)}%`, color: winRate >= 50 ? colors.success : colors.error },
          { label: "BEST", num: trades.length ? Math.max(...trades.map(t => t.pnl)) : null, fmt: (v) => `+$${v.toFixed(2)}`, color: colors.success },
          { label: "WORST", num: trades.length ? Math.min(...trades.map(t => t.pnl)) : null, fmt: (v) => `$${v.toFixed(2)}`, color: colors.error },
        ].map(s => (
          <div key={s.label} className="stat-tile">
            <div className="stat-tile__label">{s.label}</div>
            <div className="stat-tile__value" style={{ color: s.color }}>
              {s.num != null ? <AnimatedNumber value={s.num} format={s.fmt} duration={200} /> : "--"}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
});

export const RecentTradesPanel = memo(function RecentTradesPanel({
  trades, connected, exportTrades, tradeTypeBadge, openTradeDetail,
  setShowHistory, fetchHistory, tradesContainerRef,
}) {
  return (
    <div className="dash-panel dash-panel--flex">
      <div className="dash-panel__header">
        <span className="section-label" style={{ marginBottom: 0 }}>THE RECORD</span>
        <div className="dash-panel__header-actions">
          {trades.length > 0 && (
            <button className="btn btn-d" onClick={() => exportTrades()} aria-label="Export trade history as CSV"><Download size={12} /> CSV</button>
          )}
          {connected && (
            <button className="btn btn-d" onClick={() => { setShowHistory(true); fetchHistory(0); }} style={{ color: colors.gold, borderColor: "#D4AF3733" }} aria-label="View full trade history">ALL HISTORY</button>
          )}
        </div>
      </div>
      <div ref={tradesContainerRef} className="dash-panel__scroll">
        {trades.length === 0
          ? <div className="dash-panel__empty">No trades yet — start the bot</div>
          : trades.map(tr => (
            <div key={tr.id} className="trow" style={{ fontSize: "11px", cursor: "pointer" }}
              onClick={() => openTradeDetail(tr)} title="Click to view trade chart">
              <div>
                <span className="tag" style={{ display: "flex", alignItems: "center", gap: "4px", background: tr.side === "buy" ? "#00E67618" : "#FF174418", color: tr.side === "buy" ? colors.success : colors.error, marginRight: "5px" }}>
                  {tr.side === "buy" ? <ArrowUp size={10} /> : <ArrowDown size={10} />} {tr.side?.toUpperCase()}
                </span>
                <span style={{ color: colors.gold, fontSize: "9px", fontWeight: "700", marginRight: "4px" }}>{tr.symbol || "BTC"}</span>
                {tradeTypeBadge(tr)}
                <span style={{ color: "#2a2a2a", fontSize: "9px", marginLeft: "4px" }}>{tr.ts}</span>
              </div>
              <div style={{ textAlign: "right" }}>
                <div style={{ fontWeight: "700", color: tr.win ? colors.success : colors.error }}>{tr.pnl >= 0 ? "+" : ""}${(+tr.pnl).toFixed(2)}</div>
                <div style={{ fontSize: "9px", color: colors.dim, display: "flex", alignItems: "center", justifyContent: "flex-end", gap: "3px" }}>{tr.reason} <Camera size={10} style={{ color: "#D4AF3766" }} /></div>
              </div>
            </div>
          ))
        }
      </div>
    </div>
  );
});

export const ActivityLogPanel = memo(function ActivityLogPanel({ logs, botOn, connected, logsContainerRef }) {
  return (
    <div className="dash-panel dash-panel--flex">
      <div className="dash-panel__header">
        <div className="dash-panel__header-left">
          <span className="section-label" style={{ marginBottom: 0 }}>SYSTEM ACTIVITY</span>
          {(botOn || connected) && <span className="blink" style={{ fontSize: "9px", color: colors.success }}>LIVE</span>}
        </div>
      </div>
      <div ref={logsContainerRef} className="dash-panel__scroll" role="log" aria-label="Activity log">
        {logs.map((e) => (
          <div key={e.id} className="logrow" style={{ fontSize: "10px", lineHeight: "1.7" }}>
            <span style={{ color: "#2a2a2a", marginRight: "5px" }}>{e.ts}</span>
            <span style={{ color: { success: colors.success, error: colors.error, warning: colors.warning, claude: colors.gold, sell: "#ff6688", dim: colors.dim }[e.type] || colors.muted }}>
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
});
