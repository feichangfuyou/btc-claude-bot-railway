import { useState } from "react";
import AnimatedNumber from "../AnimatedNumber.jsx";
import { StrategyDropdown } from "./StrategyDropdown.jsx";
import { Play, Square, Activity, RotateCcw, ChevronDown } from "lucide-react";

const GOAL_PRESETS = [100, 500, 1000, 2500, 4000];

export function ControlPanel({
  account, winRate, startBal, targetBal, thinking, botOn, connected,
  analysisModel, handleModelChange,
  tradingPreset, presets, presetCategories, handlePresetChange,
  profitGoal, setProfitGoal,
  scanCoinCount, setScanCoinCount, maxAvailableCoins, allAvailableCoins,
  handleStart, handleStop, handleAsk, handleReset,
}) {
  const [pairsOpen, setPairsOpen] = useState(false);

  const stats = [
    { label: "BAL", val: account.balance, fmt: (v) => `$${v.toFixed(0)}`, color: "#D4D4D4", glow: "none" },
    { label: "P&L", val: account.total_pnl, fmt: (v) => `${v >= 0 ? "+" : ""}$${v.toFixed(0)}`, color: account.total_pnl >= 0 ? "#00E676" : "#FF1744", glow: account.total_pnl >= 0 ? "0 0 8px #00E67644" : "0 0 8px #FF174444" },
    { label: "24H", val: account.daily_pnl, fmt: (v) => `${v >= 0 ? "+" : ""}$${v.toFixed(0)}`, color: account.daily_pnl >= 0 ? "#00E676" : "#FF1744", glow: account.daily_pnl >= 0 ? "0 0 8px #00E67644" : "0 0 8px #FF174444" },
    { label: "WIN", val: winRate, fmt: (v) => `${v}%`, color: winRate >= 50 ? "#00E676" : "#FF1744", glow: "none" },
  ];

  return (
    <div
      className={`control-panel${pairsOpen ? " control-panel--open" : ""}${botOn ? " control-panel--live" : ""}`}
    >
      {/* Stats */}
      <div className="cp-row1">
        {stats.map(s => (
          <div key={s.label} className="cp-stat" style={{ borderBottomColor: `${s.color}22` }}>
            <div className="cp-stat-label">{s.label}</div>
            <div className="cp-stat-value" style={{ color: s.color, textShadow: s.glow }}>
              <AnimatedNumber value={s.val} format={s.fmt} duration={150} />
            </div>
          </div>
        ))}
        <div className="cp-paper">
          <div className="cp-stat-label">PAPER</div>
          <div className="cp-paper-val">
            ${startBal?.toLocaleString?.() || startBal}{"\u2192"}${targetBal?.toLocaleString?.() || targetBal}
          </div>
        </div>
      </div>

      <div className="cp-divider" />

      {/* Config row */}
      <div className="cp-config">
        <div className="cp-field">
          <span className="cp-field-label">MDL</span>
          <select
            className="cp-select"
            value={analysisModel}
            onChange={e => handleModelChange(e.target.value)}
            disabled={thinking}
            aria-label="Select model"
          >
            <option value="claude-opus-4-6">OPUS 4.6</option>
            <option value="claude-sonnet-4-6">SONNET 4.6</option>
            <option value="claude-sonnet-4-5-20250929">SONNET 4.5</option>
            <option value="claude-sonnet-4-20250514">SONNET 4</option>
            <option value="claude-3-haiku-20240307">HAIKU 3</option>
          </select>
          {thinking && <span className="cp-lock">LCK</span>}
        </div>

        {connected && (
          <>
            <div className="cp-vrule" />
            <StrategyDropdown
              tradingPreset={tradingPreset}
              presets={presets}
              presetCategories={presetCategories}
              onPresetChange={handlePresetChange}
            />
            <div className="cp-vrule" />
            <div className="cp-field cp-field--pairs">
              <span className="cp-field-label">PAIRS</span>
              <button
                type="button"
                className={`cp-pairs-btn${pairsOpen ? " cp-pairs-btn--open" : ""}`}
                onClick={() => setPairsOpen(v => !v)}
                aria-expanded={pairsOpen}
                aria-label={`Scan ${scanCoinCount || 5} pairs`}
              >
                {scanCoinCount || 5}
                <ChevronDown size={8} className={`cp-chevron${pairsOpen ? " cp-chevron--up" : ""}`} />
              </button>

              {pairsOpen && (
                <>
                  <div className="cp-pairs-overlay" onClick={() => setPairsOpen(false)} aria-hidden="true" />
                  <div className="cp-pairs-popover" role="dialog" aria-label="Pairs to scan">
                    <div className="cp-pairs-title">
                      SCAN {scanCoinCount} OF {maxAvailableCoins || 20} PAIRS
                    </div>
                    <input
                      type="range"
                      className="cp-range"
                      min={1}
                      max={maxAvailableCoins || 20}
                      value={scanCoinCount || 5}
                      onChange={e => setScanCoinCount(Math.max(1, +e.target.value))}
                      aria-label="Number of pairs to scan"
                    />
                    <div className="cp-pairs-quick">
                      {[1, 3, 5, 10, maxAvailableCoins || 20].map(n => (
                        <button
                          key={n}
                          type="button"
                          className={`cp-goal-btn${scanCoinCount === n ? " cp-goal-btn--on" : ""}`}
                          onClick={() => setScanCoinCount(n)}
                        >
                          {n}
                        </button>
                      ))}
                    </div>
                    <div className="cp-pairs-tags">
                      {(allAvailableCoins || []).slice(0, scanCoinCount).map(sym => (
                        <span key={sym} className="cp-pair-tag">{sym}</span>
                      ))}
                      {(allAvailableCoins || []).length > scanCoinCount && (
                        <span className="cp-pairs-more">
                          +{(allAvailableCoins || []).length - scanCoinCount} more
                        </span>
                      )}
                    </div>
                    <button type="button" className="cp-pairs-done" onClick={() => setPairsOpen(false)}>DONE</button>
                  </div>
                </>
              )}
            </div>
          </>
        )}
      </div>

      <div className="cp-goal-row">
        <span className="cp-field-label">TGT</span>
        {GOAL_PRESETS.map(g => (
          <button
            key={g}
            type="button"
            className={`cp-goal-btn${profitGoal === g ? " cp-goal-btn--on" : ""}`}
            onClick={() => setProfitGoal(profitGoal === g ? 0 : g)}
          >
            ${g >= 1000 ? `${g / 1000}k` : g}
          </button>
        ))}
        <input
          type="number"
          min="0"
          step="10"
          placeholder="Custom"
          className="cp-goal-input"
          value={profitGoal > 0 && !GOAL_PRESETS.includes(profitGoal) ? profitGoal : ""}
          onChange={e => setProfitGoal(Math.max(0, +e.target.value || 0))}
          aria-label="Custom profit goal"
        />
        {profitGoal > 0 && !GOAL_PRESETS.includes(profitGoal) && (
          <button type="button" className="cp-goal-clear" onClick={() => setProfitGoal(0)} title="Clear goal" aria-label="Clear goal">
            {"\u2715"}
          </button>
        )}
      </div>

      {profitGoal > 0 && (
        <div className="cp-progress">
          <div className="cp-progress-track">
            <div
              className="cp-progress-fill"
              style={{
                width: `${Math.min(100, Math.max(0, (account.total_pnl / profitGoal) * 100))}%`,
                background: account.total_pnl >= profitGoal
                  ? "linear-gradient(90deg,#00E676,#00C853)"
                  : "linear-gradient(90deg,#D4AF37,#B8860B)",
                boxShadow: account.total_pnl >= profitGoal ? "0 0 8px #00E67666" : "0 0 6px #D4AF3744",
              }}
            />
          </div>
          <span className="cp-progress-text">
            $<AnimatedNumber value={Math.max(0, account.total_pnl)} format={(v) => v.toFixed(0)} duration={200} />
            <span className="cp-progress-sep">/</span>
            {profitGoal >= 1000 ? `$${profitGoal / 1000}k` : `$${profitGoal}`}
          </span>
        </div>
      )}

      {/* Actions */}
      <div className="cp-actions">
        {!botOn ? (
          <button type="button" className="btn btn-g cp-action-btn" onClick={handleStart} aria-label="Start bot">
            <Play size={11} /> START BOT
          </button>
        ) : (
          <button type="button" className="btn btn-r cp-action-btn" onClick={handleStop} aria-label="Stop bot">
            <Square size={11} /> STOP BOT
          </button>
        )}
        <button type="button" className="btn btn-p cp-action-btn" onClick={handleAsk} disabled={thinking} aria-label="Analyze market">
          <Activity size={11} />
          {thinking ? <span className="blink">ANALYZING</span> : "ANALYZE"}
        </button>
        <button type="button" className="btn btn-d cp-action-btn" onClick={handleReset} aria-label="Reset paper balance">
          <RotateCcw size={10} /> RESET
        </button>
      </div>

    </div>
  );
}
