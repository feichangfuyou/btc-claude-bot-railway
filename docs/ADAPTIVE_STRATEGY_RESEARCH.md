# Deep Research: Always-Adjusting-to-the-Market Adaptive Trading Strategy

## Executive Summary

An "always adjusting" strategy continuously adapts parameters (position size, SL/TP, scan frequency, signal thresholds) based on real-time market conditions—regime, volatility, and learned performance. Static parameters fail in crypto because regimes shift frequently (trending ↔ ranging ↔ chaotic) and asset-specific volatility varies wildly (BTC ~40% vs SOL ~80% annualized).

---

## 1. Regime Detection & Adaptation

### What We Have
- **4 regimes**: `trending_up`, `trending_down`, `ranging`, `chaotic`
- **Detection**: EMA/ICH/HA vote + ATR spike (>2.5× avg = chaotic)
- **Regime-weighted confluence**: Different signals boosted/dampened per regime
- **Preset SL/TP by regime**: e.g. chaotic → wider stops (trading_presets.py)

### Research Findings
- **Kalman + Markov-Switching** (2024): Foreign investor predictive power **8.9× higher** in crisis vs bull markets—regime matters enormously.
- **RegimeFolio** (VIX + ML): 137% return, 1.17 Sharpe, 12% lower max drawdown vs benchmarks.
- **Hidden Markov Models**: Dynamic lookback periods + trailing stops by regime outperform static.

### Gaps to Fix
1. **No hysteresis** — Regime flips every tick near boundaries → whipsaw.
2. **Generic ATR threshold** — SOL runs 60–130% vol even when "calm"; BTC different. Asset-specific thresholds needed.
3. **Regime used for confluence, not live sizing** — Learned rules go to memory briefing but execution doesn’t auto-scale.

---

## 2. Volatility Regime & Adaptive Stops

### Research
- **Dynamic ATR trailing**: Stop = k × ATR; k scales: 1.5× low vol, 2× normal, 2.5–3× high vol.
- **Volatility Regime (TradingView/GainzAlgo)**: ATR percentile rank, BB width, ADX → classify Low/Medium/High.
- **Hysteresis bands**: 10pp bands at regime boundaries reduce transitions (e.g. 132 → 36 in backtest).
- **Fractal-Adaptive MA (FRAMA)**: Length adjusts by fractal dimension—slow in noise, fast in trends.

### What We Have
- `_learn_from_volatility_regime()` — learns low/normal/high vol performance, saves rules.
- `vol_adj` in `_handle_open_trade` — reduces size when ATR% > 1.5%.
- Preset-based min SL/TP by regime.

### Gaps
1. **Vol regime not explicitly classified per candle** — Only in post-trade learning.
2. **No hysteresis** — Regime can flip every update.
3. **Asset-specific vol thresholds** — Same 2.5× ATR spike for BTC and SOL.

---

## 3. Meta-Learning & Parameter Selection

### Research (Adaptive Crypto Trading, SSRN 5017215)
- Meta-learning selects hyperparameters from: strategy meta-info, DC indicators, on-chain data, regime stats.
- **Result**: 10× return increase, 3× Sharpe vs static parameters.
- Different feature categories capture different aspects of optimal params at different times.

### What We Have
- `run_learning_cycle()` — 15+ learning modules (patterns, regimes, time, confidence, size, volatility, hold duration, R:R, fear/greed, etc.).
- Rules stored with confidence, fed to Claude via `memory_briefing`.
- Claude told to "scale into" wins, "avoid" losses.

### Gap
- **Rules are advisory** — Claude can ignore. No hard enforcement for critical rules (e.g. "VOL TRAP → reduce size 50%").

---

## 4. Regime-Variable Hedging (Grid Bot Study, Medium 2026)
- Regime-variable hedging: 0% in bull, 100% in bear → **+19pp** vs static.
- Asset-specific vol thresholds: SOL "calm" = 85% ann. vol; generic 60% misclassifies.
- Hysteresis (10pp bands): Cuts regime transitions 132 → 36, protects PnL.

---

## 5. Implementation Recommendations

| Component | Current | Recommended |
|-----------|---------|-------------|
| Regime detection | Instant, no smoothing | Add hysteresis: require N consecutive candles or %-diff threshold before switching |
| Volatility regime | Post-trade only | Classify live: atr_pct vs 20-period percentile (low <33rd, high >66th) |
| SL/TP multipliers | Preset by regime | Scale by vol_regime: low_vol → 0.9×, high_vol → 1.3× |
| Position size | Balance + consecutive losses | Add vol_regime: high_vol → 0.7×, low_vol → 1.0× |
| Scan interval | Regime-based (adaptive_interval) | Already good; add chaos → 25s when positions open |
| Learned rules | Memory briefing only | Enforce critical: vol_trap → max 15% size; regime_danger → min 2.2 R:R |
| Asset-specific | None | Symbol-specific ATR threshold (e.g. BTC 2.2×, SOL 3.0× for chaotic) |

---

## 6. References

- [1] Kalman Filtering & Markov-Switching Regimes (arxiv 2601.05716)
- [2] RegimeFolio ML System (arxiv 2510.14986)
- [3] From Static to Adaptive Grid Bot, +28% SOL (Medium 2026)
- [4] Hidden Markov Model Regime-Adaptive Momentum (PyQuantLab)
- [5] Adaptive Crypto Trading, Directional Change + Meta-Learning (SSRN 5017215)
- [6] Dynamic ATR Trailing Stop (Medium)
- [7] Volatility Regimes (TradingView, GainzAlgo)
- [8] Fractal-Adaptive MA, FRAMA (PyQuantLab)
- [9] ADAPT-Z Feature Adjustment for BTC Regime Shifts
