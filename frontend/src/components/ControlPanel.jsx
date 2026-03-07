import AnimatedNumber from "../AnimatedNumber.jsx";
import { StrategyDropdown } from "./StrategyDropdown.jsx";
import { Play, Square, Activity, RotateCcw } from "lucide-react";

export function ControlPanel({
  account, winRate, startBal, targetBal, thinking, botOn, connected,
  claudeModel, handleModelChange,
  tradingPreset, presets, presetCategories, handlePresetChange,
  profitGoal, setProfitGoal,
  handleStart, handleStop, handleAsk, handleReset,
}) {
  return (
    <div className="card control-panel" style={{
      gridColumn: "1 / -1", gridRow: "2", justifySelf: "center",
      width: "100%", maxWidth: "680px",
      background: "linear-gradient(180deg, #141414 0%, #0e0e0e 100%)",
      borderRadius: "10px",
      border: "1px solid #2a2a2a",
      padding: "10px 14px",
      display: "flex", flexDirection: "column", gap: "0",
      boxShadow: "0 4px 24px rgba(0,0,0,0.5), 0 0 12px rgba(212,175,55,0.06), inset 0 1px 0 rgba(255,255,255,0.03)",
      position: "relative", overflow: "hidden",
    }}>
      {/* Canvas texture overlay */}
      <div style={{ position: "absolute", inset: 0, background: "repeating-linear-gradient(45deg, transparent, transparent 2px, rgba(212,175,55,0.008) 2px, rgba(212,175,55,0.008) 4px)", pointerEvents: "none", zIndex: 1 }} />

      {/* Top edge glow */}
      <div style={{ position: "absolute", top: 0, left: "10%", right: "10%", height: "1px", background: "linear-gradient(90deg, transparent, #D4AF3766, #C0392B44, #D4AF3766, transparent)", zIndex: 2 }} />

      {/* Bottom edge glow */}
      <div style={{ position: "absolute", bottom: 0, left: "20%", right: "20%", height: "1px", background: "linear-gradient(90deg, transparent, #D4AF3722, transparent)", zIndex: 2 }} />

      {/* Row 1: Stats readout */}
      <div className="cp-row1" style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: "3px", position: "relative", zIndex: 3, paddingBottom: "7px" }}>
        {[
          { label: "BAL", val: account.balance, fmt: (v) => `$${v.toFixed(0)}`, color: "#D4D4D4", glow: "none" },
          { label: "P&L", val: account.total_pnl, fmt: (v) => `${v >= 0 ? "+" : ""}$${v.toFixed(0)}`, color: account.total_pnl >= 0 ? "#00E676" : "#FF1744", glow: account.total_pnl >= 0 ? "0 0 8px #00E67644" : "0 0 8px #FF174444" },
          { label: "24H", val: account.daily_pnl, fmt: (v) => `${v >= 0 ? "+" : ""}$${v.toFixed(0)}`, color: account.daily_pnl >= 0 ? "#00E676" : "#FF1744", glow: account.daily_pnl >= 0 ? "0 0 8px #00E67644" : "0 0 8px #FF174444" },
          { label: "WIN", val: winRate, fmt: (v) => `${v}%`, color: winRate >= 50 ? "#00E676" : "#FF1744", glow: "none" },
        ].map(s => (
          <div key={s.label} style={{
            textAlign: "center", padding: "3px 10px", flex: "1 1 0",
            background: "rgba(0,0,0,0.4)", borderRadius: "4px",
            borderBottom: `1px solid ${s.color}22`,
          }}>
            <div style={{ fontSize: "7px", color: "#5C5C5C", letterSpacing: "1.2px", lineHeight: 1, marginBottom: "2px", fontFamily: "'Space Mono',monospace" }}>{s.label}</div>
            <div style={{ fontFamily: "'Montserrat', sans-serif", fontSize: "16px", color: s.color, lineHeight: 1, textShadow: s.glow, whiteSpace: "nowrap" }}>
              <AnimatedNumber value={s.val} format={s.fmt} duration={150} />
            </div>
          </div>
        ))}

        {/* Paper wallet tag */}
        <div style={{
          textAlign: "center", padding: "3px 8px", flex: "0 0 auto",
          background: "rgba(0,0,0,0.4)", borderRadius: "4px",
          border: "1px solid #2a2a2a",
        }}>
          <div style={{ fontSize: "7px", color: "#5C5C5C", letterSpacing: "1.2px", lineHeight: 1, marginBottom: "2px", fontFamily: "'Space Mono',monospace" }}>PAPER</div>
          <div style={{ fontSize: "9px", color: "#5C5C5C", fontFamily: "'Space Mono',monospace", fontWeight: "600", lineHeight: 1, whiteSpace: "nowrap" }}>
            ${startBal?.toLocaleString?.() || startBal}{"\u2192"}${targetBal?.toLocaleString?.() || targetBal}
          </div>
        </div>
      </div>

      {/* Separator line */}
      <div style={{ height: "1px", background: "linear-gradient(90deg, transparent, #D4AF3744, #C0392B33, #D4AF3744, transparent)", marginBottom: "7px", position: "relative", zIndex: 3 }} />

      {/* Row 2: Model + Strategy + Goal */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: "10px", position: "relative", zIndex: 3, paddingBottom: "8px", flexWrap: "wrap" }}>
        {/* Model selector */}
        <div style={{ display: "flex", alignItems: "center", gap: "4px" }}>
          <span style={{ fontSize: "7px", color: "#5C5C5C", letterSpacing: "1px", fontFamily: "'Space Mono',monospace" }}>MDL</span>
          <select
            value={claudeModel}
            onChange={e => handleModelChange(e.target.value)}
            disabled={thinking}
            style={{
              fontFamily: "'Space Mono',monospace", fontSize: "9px", fontWeight: "700",
              padding: "3px 20px 3px 6px", borderRadius: "4px",
              backgroundColor: thinking ? "#1a1a1a" : "rgba(0,0,0,0.4)",
              backgroundImage: thinking ? "none" : "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='6' height='4' viewBox='0 0 10 6'%3E%3Cpath fill='%23D4AF37' d='M0 0l5 6 5-6z'/%3E%3C/svg%3E\")",
              backgroundRepeat: "no-repeat", backgroundPosition: "right 6px center",
              color: thinking ? "#3a3a3a" : "#D4AF37",
              border: thinking ? "1px solid #2a2a2a22" : "1px solid #D4AF3722",
              cursor: thinking ? "not-allowed" : "pointer",
              outline: "none", appearance: "none",
              opacity: thinking ? 0.5 : 1,
            }}
            aria-label="Select Model"
          >
            <option value="claude-opus-4-6">NEURAL OPUS 4.6</option>
            <option value="claude-sonnet-4-6">NEURAL SONNET 4.6</option>
            <option value="claude-sonnet-4-5-20250929">NEURAL SONNET 4.5</option>
            <option value="claude-sonnet-4-20250514">NEURAL SONNET 4</option>
            <option value="claude-3-haiku-20240307">NEURAL HAIKU 3</option>
          </select>
          {thinking && <span style={{ fontSize: "6px", color: "#ff9900", letterSpacing: "0.3px" }}>LCK</span>}
        </div>

        <div style={{ width: "1px", height: "18px", background: "linear-gradient(180deg, transparent, #D4AF3733, transparent)", flexShrink: 0 }} />

        {/* Strategy */}
        {connected && (
          <StrategyDropdown
            tradingPreset={tradingPreset}
            presets={presets}
            presetCategories={presetCategories}
            onPresetChange={handlePresetChange}
          />
        )}

        {connected && <div style={{ width: "1px", height: "18px", background: "linear-gradient(180deg, transparent, #D4AF3733, transparent)", flexShrink: 0 }} />}

        {/* Goal picker */}
        <div className="cp-row2" style={{ display: "flex", gap: "4px", alignItems: "center" }}>
          <span style={{ fontSize: "8px", color: "#5C5C5C", letterSpacing: "1px", fontFamily: "'Space Mono',monospace" }}>TGT</span>
          {[100, 500, 1000, 2500, 4000].map(g => (
            <button
              key={g}
              onClick={() => setProfitGoal(profitGoal === g ? 0 : g)}
              style={{
                fontFamily: "'Space Mono',monospace", fontSize: "10px", padding: "3px 7px", borderRadius: "3px",
                border: profitGoal === g ? "1px solid #D4AF37" : "1px solid #2a2a2a",
                background: profitGoal === g ? "#D4AF3718" : "rgba(0,0,0,0.25)",
                color: profitGoal === g ? "#D4AF37" : "#5C5C5C",
                cursor: "pointer", fontWeight: "600", lineHeight: 1,
              }}
            >
              ${g >= 1000 ? `${g / 1000}k` : g}
            </button>
          ))}
          <input
            type="number"
            min="0"
            step="10"
            placeholder="Custom"
            value={profitGoal > 0 && ![100, 500, 1000, 2500, 4000].includes(profitGoal) ? profitGoal : ""}
            onChange={e => setProfitGoal(Math.max(0, +e.target.value || 0))}
            style={{
              width: "56px", fontFamily: "'Space Mono',monospace", fontSize: "10px", padding: "3px 5px",
              background: "rgba(0,0,0,0.25)", border: "1px solid #2a2a2a", borderRadius: "3px", color: "#D4D4D4",
              outline: "none",
            }}
          />
          {profitGoal > 0 && ![100, 500, 1000, 2500, 4000].includes(profitGoal) && (
            <button
              onClick={() => setProfitGoal(0)}
              style={{ fontSize: "10px", color: "#5C5C5C", background: "none", border: "none", cursor: "pointer", padding: "2px 3px", lineHeight: 1 }}
              title="Clear goal"
            >{"\u2715"}</button>
          )}
        </div>
      </div>

      {/* Goal progress bar */}
      {profitGoal > 0 && (
        <div style={{ display: "flex", alignItems: "center", gap: "8px", paddingBottom: "6px", position: "relative", zIndex: 3 }}>
          <div style={{ flex: 1, height: "8px", background: "#1a1a1a", borderRadius: "4px", overflow: "hidden", border: "1px solid #2a2a2a" }}>
            <div style={{
              height: "100%", width: `${Math.min(100, Math.max(0, (account.total_pnl / profitGoal) * 100))}%`,
              background: account.total_pnl >= profitGoal ? "linear-gradient(90deg,#00E676,#00C853)" : "linear-gradient(90deg,#D4AF37,#B8860B)",
              borderRadius: "3px", transition: "width 0.4s ease",
              boxShadow: account.total_pnl >= profitGoal ? "0 0 8px #00E67666" : "0 0 6px #D4AF3744",
            }} />
          </div>
          <span style={{ fontSize: "9px", color: "#5C5C5C", whiteSpace: "nowrap", fontFamily: "'Space Mono',monospace", fontWeight: "600" }}>
            $<AnimatedNumber value={Math.max(0, account.total_pnl)} format={(v) => v.toFixed(0)} duration={200} />
            <span style={{ color: "#3a3a3a" }}>/</span>
            {profitGoal >= 1000 ? `$${profitGoal / 1000}k` : `$${profitGoal}`}
          </span>
        </div>
      )}

      {/* Row 3: Action buttons */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: "6px", position: "relative", zIndex: 3 }}>
        {!botOn
          ? <button className="btn btn-g" onClick={handleStart} aria-label="Start bot" style={{
            padding: "4px 16px", minHeight: "28px", fontSize: "10px", borderRadius: "3px",
            boxShadow: "0 0 14px rgba(212,175,55,0.3), inset 0 1px 0 rgba(255,255,255,0.1)",
            display: "flex", alignItems: "center", gap: "4px"
          }}><Play size={12} /> START BOT</button>
          : <button className="btn btn-r" onClick={handleStop} aria-label="Stop bot" style={{
            padding: "4px 16px", minHeight: "28px", fontSize: "10px", borderRadius: "3px",
            boxShadow: "0 0 14px rgba(192,57,43,0.3), inset 0 1px 0 rgba(255,255,255,0.1)",
            display: "flex", alignItems: "center", gap: "4px"
          }}><Square size={12} /> STOP BOT</button>}
        <button className="btn btn-p" onClick={handleAsk} disabled={thinking} aria-label="Ask Neural Engine for analysis" style={{
          padding: "4px 14px", minHeight: "28px", fontSize: "10px", borderRadius: "3px",
          boxShadow: thinking ? "none" : "0 0 12px rgba(212,175,55,0.15)",
          display: "flex", alignItems: "center", gap: "4px"
        }}>
          <Activity size={12} />
          {thinking ? <span className="blink" style={{ fontSize: "9px" }}>ANALYZING</span> : "ANALYZE"}
        </button>
        <button className="btn btn-d" onClick={handleReset} aria-label="Reset paper trading balance" style={{
          padding: "4px 10px", minHeight: "28px", fontSize: "9px", borderRadius: "3px",
          display: "flex", alignItems: "center", gap: "4px"
        }}><RotateCcw size={10} /> RESET</button>
      </div>
    </div>
  );
}
