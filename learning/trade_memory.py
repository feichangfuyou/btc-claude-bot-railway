"""
Trade Memory Engine — learns from every trade to become elite over time.

Analyzes historical trades to discover:
- Which patterns win/lose per coin and regime
- Optimal position sizes, confidence thresholds, and time-of-day edges
- Strategy combos that compound profits vs. drain the account
- Auto-generates trading rules Claude can reference each cycle
"""

import json
from datetime import datetime

from core.database import (
    db_get_active_rules,
    db_get_coin_regime_matrix,
    db_get_confidence_analysis,
    db_get_confidence_calibration,
    db_get_confluence_analysis,
    db_get_dow_performance,
    db_get_exit_reason_stats,
    db_get_fear_greed_performance,
    db_get_hold_duration_analysis,
    db_get_hourly_performance,
    db_get_pattern_stats,
    db_get_preset_performance,
    db_get_recent_losses,
    db_get_recent_trade_contexts,
    db_get_recent_wins,
    db_get_regime_performance,
    db_get_rr_analysis,
    db_get_session_history,
    db_get_shadow_learning_rows,
    db_get_shadow_stats,
    db_get_size_analysis,
    db_get_strategy_stats,
    db_get_total_trade_count,
    db_get_trades_for_vol_analysis,
    db_save_learned_rule,
    db_save_market_snapshot,
    db_save_pattern_outcomes,
    db_save_trade_context,
    db_update_session_stats,
    db_update_strategy_stats,
)


def extract_decision_metadata(decision: dict | None, trading_preset: str = "") -> dict:
    """Pull every learnable field from an AI trade decision."""
    if not decision:
        return {}
    adv = decision.get("_adversary") or {}
    return {
        "reasoning": (decision.get("reasoning") or "")[:500],
        "key_signals": decision.get("key_signals") or decision.get("patterns_detected") or [],
        "trading_preset": trading_preset or decision.get("trading_preset", ""),
        "adversary_verdict": adv.get("verdict", ""),
        "confluence_score": decision.get("confluence_score", 0),
        "market_condition": decision.get("market_condition", ""),
        "reasons_to_trade": (decision.get("reasons_to_trade") or [])[:5],
        "reasons_to_wait": (decision.get("reasons_to_wait") or [])[:5],
        "model_used": decision.get("_model_used", ""),
        "gate_action": decision.get("_gate_action", ""),
    }


def trigger_post_trade_learning(pnl: float, symbol: str = "") -> None:
    """Run full learning cycle after every closed trade — wins AND losses teach."""
    run_learning_cycle()
    _ = symbol  # reserved for future per-coin learning hooks


def record_trade_memory(
    trade: dict,
    position: dict,
    coin_state,
    fear_greed: int,
    balance: float,
    trading_preset: str = "",
):
    """Record full context of a completed trade for learning."""
    symbol = trade.get("symbol", "BTC")
    side = trade.get("side", "buy")
    pnl = trade.get("pnl", 0)
    win = pnl > 0

    hold_sec: float = 0
    if position and position.get("open_ts"):
        try:
            opened = datetime.strptime(position["open_ts"], "%H:%M:%S")
            now = datetime.now()
            opened = opened.replace(year=now.year, month=now.month, day=now.day)
            hold_sec = max(0, (now - opened).total_seconds())
        except ValueError:
            pass

    entry = trade.get("entry", 0)
    exit_p = trade.get("exit", 0)
    tp = (position or {}).get("tp", 0)
    sl = (position or {}).get("sl", 0)
    reward = abs(tp - entry) if tp and entry else 0
    risk = abs(entry - sl) if sl and entry else 1
    rr_ratio = round(reward / max(risk, 0.01), 2)

    patterns = (position or {}).get("patterns", [])
    confidence = (position or {}).get("confidence", 0)
    regime = coin_state.market_cond if coin_state else "unknown"
    indicators = dict(coin_state.indicators) if coin_state else {}
    indicators.pop("_price", None)
    confluence = indicators.get("confluence", {})
    confluence_score = (position or {}).get("confluence_score") or confluence.get("strength", 0)

    decision_meta = (position or {}).get("decision_meta") or {}
    if not decision_meta and position:
        decision_meta = {
            k: position.get(k)
            for k in (
                "reasoning",
                "key_signals",
                "trading_preset",
                "adversary_verdict",
                "reasons_to_trade",
                "reasons_to_wait",
                "model_used",
            )
            if position.get(k)
        }

    preset = trading_preset or decision_meta.get("trading_preset") or (position or {}).get("trading_preset", "")
    exit_reason = trade.get("reason", "")

    usd_size = trade.get("usd_size", 0)
    size_pct = round((usd_size / max(balance, 1)) * 100, 1) if balance > 0 else 0

    product_type = trade.get("product_type", position.get("product_type", "spot") if position else "spot")
    onchain = trade.get("onchain", position.get("onchain", False) if position else False)
    leverage = trade.get("leverage", position.get("leverage", 1) if position else 1) or 1

    ctx = {
        "trade_id": trade.get("id"),
        "symbol": symbol,
        "side": side,
        "entry_price": entry,
        "exit_price": exit_p,
        "pnl": pnl,
        "win": win,
        "confidence": confidence,
        "confluence_score": confluence_score,
        "regime": regime,
        "patterns": patterns,
        "indicators": indicators,
        "fear_greed": fear_greed,
        "size_pct": size_pct,
        "rr_ratio": rr_ratio,
        "hold_duration_sec": hold_sec,
        "product_type": product_type,
        "onchain": onchain,
        "leverage": leverage,
        "reasoning": decision_meta.get("reasoning", ""),
        "key_signals": decision_meta.get("key_signals", []),
        "trading_preset": preset,
        "adversary_verdict": decision_meta.get("adversary_verdict", ""),
        "exit_reason": exit_reason,
        "meta": {
            "model_used": decision_meta.get("model_used", ""),
            "reasons_to_trade": decision_meta.get("reasons_to_trade", []),
            "reasons_to_wait": decision_meta.get("reasons_to_wait", []),
            "gate_action": decision_meta.get("gate_action", ""),
        },
    }
    db_save_trade_context(ctx)

    db_save_pattern_outcomes(patterns, symbol, side, regime, win, pnl, confluence_score)

    db_update_strategy_stats(symbol, side, regime, pnl, win, hold_sec)

    db_update_session_stats(trade, balance)


def record_market_snapshot(coin_state, fear_greed: int):
    """Periodic market state recording for pattern discovery."""
    if not coin_state or coin_state.price <= 0:
        return
    db_save_market_snapshot(
        coin_state.symbol,
        coin_state.indicators,
        coin_state.market_cond,
        coin_state.detected_patterns,
        fear_greed,
    )


def run_learning_cycle():
    """Analyze all historical data and generate/update learned trading rules.
    v2: Higher sample requirements, win streak momentum tracking."""
    total_trades = db_get_total_trade_count()
    if total_trades < 5:
        return

    _learn_from_patterns()
    _learn_from_regimes()
    _learn_from_time_of_day()
    _learn_from_confidence_bands()
    _learn_from_size_bands()
    _learn_from_strategy_combos()
    _learn_from_coin_regime_matrix()
    _learn_momentum_rules()
    _learn_from_fear_greed()
    _learn_from_day_of_week()
    _learn_from_confluence()
    _learn_from_volatility_regime()
    _learn_from_hold_duration()
    _learn_from_rr_ratio()
    _learn_from_confidence_calibration()
    _learn_from_recent_wins()
    _learn_from_shadow_outcomes()
    _learn_from_preset_performance()
    _learn_from_exit_reasons()


def _learn_from_shadow_outcomes():
    """Learn whether risk-gate blocks saved capital or cost opportunity."""
    rows = db_get_shadow_learning_rows(limit=80)
    if len(rows) < 5:
        return

    blocked = [r for r in rows if r.get("blocked_by_gate")]
    if len(blocked) < 3:
        return

    saves = [r for r in blocked if (r.get("counterfactual_pnl_1h") or 0) < -0.001]
    missed = [r for r in blocked if (r.get("counterfactual_pnl_1h") or 0) > 0.001]
    save_rate = len(saves) / len(blocked) * 100 if blocked else 0
    miss_rate = len(missed) / len(blocked) * 100 if blocked else 0

    if save_rate >= 55:
        desc = (
            f"GATE VALIDATED: {save_rate:.0f}% of blocked trades would have lost at 1h "
            f"(n={len(blocked)}). Trust risk gate blocks — they save capital."
        )
        db_save_learned_rule(
            "shadow", "shadow|gate_saves", desc, min(0.85, 0.5 + len(blocked) / 50), len(blocked), save_rate, 0
        )
    elif miss_rate >= 55:
        desc = (
            f"GATE TOO TIGHT: {miss_rate:.0f}% of blocked trades would have won at 1h "
            f"(n={len(blocked)}). Raise bar carefully — don't over-filter A+ setups."
        )
        db_save_learned_rule(
            "shadow", "shadow|gate_too_tight", desc, min(0.8, 0.5 + len(blocked) / 40), len(blocked), miss_rate, 0
        )

    # Per-regime block quality
    regime_blocks: dict[str, list] = {}
    for r in blocked:
        regime_blocks.setdefault(r.get("regime") or "unknown", []).append(r)
    for regime, rlist in regime_blocks.items():
        if len(rlist) < 3:
            continue
        regime_saves = sum(1 for r in rlist if (r.get("counterfactual_pnl_1h") or 0) < 0)
        wr = regime_saves / len(rlist) * 100
        if wr >= 65:
            key = f"shadow|regime_block|{regime}"
            desc = (
                f"BLOCK WISELY in {regime}: {wr:.0f}% of gate blocks in {regime} avoided losses "
                f"(n={len(rlist)}). Keep filtering marginal {regime} setups."
            )
            db_save_learned_rule("shadow", key, desc, 0.7, len(rlist), wr, 0)


def _learn_from_preset_performance():
    """Which trader preset actually performs best for this bot."""
    perf = db_get_preset_performance(min_samples=3)
    if not perf:
        return

    best = max(perf, key=lambda p: p.get("avg_pnl", 0))
    worst = min(perf, key=lambda p: p.get("avg_pnl", 0))

    if best.get("avg_pnl", 0) > 0 and best.get("win_rate", 0) >= 50:
        key = f"preset|{best['preset']}"
        desc = (
            f"BEST PRESET: '{best['preset']}' — {best['win_rate']}% win rate, "
            f"avg ${best['avg_pnl']}, n={best['total']}. Favor this strategy philosophy."
        )
        db_save_learned_rule("preset", key, desc, 0.75, best["total"], best["win_rate"], best["avg_pnl"])

    if worst.get("avg_pnl", 0) < 0 and worst.get("win_rate", 0) <= 45 and worst["preset"] != best.get("preset"):
        key = f"preset|{worst['preset']}|weak"
        desc = (
            f"WEAK PRESET: '{worst['preset']}' — only {worst['win_rate']}% win rate, "
            f"avg ${worst['avg_pnl']}, n={worst['total']}. Consider switching preset or tightening entries."
        )
        db_save_learned_rule("preset", key, desc, 0.7, worst["total"], worst["win_rate"], worst["avg_pnl"])


def _learn_from_exit_reasons():
    """Learn from how trades actually closed — TP discipline vs premature exits."""
    stats = db_get_exit_reason_stats(min_samples=3)
    labels = {
        "tp_hit": "Take-profit hits",
        "sl_hit": "Stop-loss hits",
        "stale_exit": "Stale position exits",
        "ai_close": "AI-initiated closes",
        "other": "Other exits",
    }
    for s in stats:
        exit_type = s.get("exit_type", "other")
        total = s.get("total", 0)
        win_rate = s.get("win_rate", 0)
        avg_pnl = s.get("avg_pnl", 0)
        label = labels.get(exit_type, exit_type)
        key = f"exit|{exit_type}"

        if exit_type == "sl_hit" and win_rate <= 10 and avg_pnl < 0:
            desc = (
                f"STOP OUTS: {label} — {win_rate}% win rate, avg ${avg_pnl}, n={total}. "
                f"Review entry quality before SL hits. Tighten filters or widen stops in volatile regimes."
            )
            db_save_learned_rule("exit", key, desc, 0.75, total, win_rate, avg_pnl)
        elif exit_type == "tp_hit" and win_rate >= 90 and avg_pnl > 0:
            desc = (
                f"WINNER PATH: {label} — {win_rate}% win rate, avg ${avg_pnl}, n={total}. "
                f"Replicate the entry conditions that reach TP."
            )
            db_save_learned_rule("exit", key, desc, 0.8, total, win_rate, avg_pnl)
        elif exit_type == "stale_exit" and avg_pnl > 0 and win_rate >= 60:
            desc = (
                f"STALE WORKS: {label} — {win_rate}% win rate, avg ${avg_pnl}, n={total}. "
                f"Taking small wins on dead trades preserves capital."
            )
            db_save_learned_rule("exit", key, desc, 0.65, total, win_rate, avg_pnl)


def _learn_from_patterns():
    stats = db_get_pattern_stats(min_samples=5)
    for s in stats:
        pattern = s["pattern"]
        win_rate = s["win_rate"]
        avg_pnl = s["avg_pnl"]
        total = s["total"]
        symbol = s["symbol"]
        side = s["side"]
        regime = s["regime"]

        key = f"pattern|{pattern}|{symbol}|{side}|{regime}"

        if win_rate >= 65 and avg_pnl > 0 and total >= 5:
            desc = (
                f"HIGH-WIN pattern: {pattern} on {symbol} ({side}) in {regime} "
                f"has {win_rate}% win rate (avg ${avg_pnl}, n={total}). "
                f"FAVOR this setup — increase size by 5%."
            )
            confidence = min(0.9, 0.5 + (total / 50) + (win_rate - 50) / 100)
        elif win_rate <= 35 and avg_pnl < 0 and total >= 5:
            desc = (
                f"LOSING pattern: {pattern} on {symbol} ({side}) in {regime} "
                f"has {win_rate}% win rate (avg ${avg_pnl}, n={total}). "
                f"AVOID this setup or reduce size by 10%."
            )
            confidence = min(0.9, 0.5 + (total / 50))
        else:
            continue

        db_save_learned_rule("pattern", key, desc, confidence, total, win_rate, avg_pnl)


def _learn_from_regimes():
    perf = db_get_regime_performance()
    for regime, stats in perf.items():
        total = stats["total"]
        if total < 5:
            continue
        win_rate = stats["win_rate"]
        avg_pnl = stats["avg_pnl"]
        key = f"regime|{regime}"

        if win_rate >= 60 and avg_pnl > 0:
            desc = (
                f"PROFITABLE regime: {regime} markets produce {win_rate}% win rate "
                f"(avg ${avg_pnl}, n={total}). Trade aggressively in {regime}."
            )
        elif win_rate <= 40 and avg_pnl < 0:
            desc = (
                f"DANGEROUS regime: {regime} markets produce only {win_rate}% win rate "
                f"(avg ${avg_pnl}, n={total}). Reduce size or wait for better conditions."
            )
        else:
            desc = f"NEUTRAL regime: {regime} — {win_rate}% win rate, avg ${avg_pnl}, n={total}. Standard sizing."

        db_save_learned_rule("regime", key, desc, min(0.85, 0.4 + total / 40), total, win_rate, avg_pnl)


def _learn_from_time_of_day():
    hours = db_get_hourly_performance()
    for h in hours:
        hour = h["hour_of_day"]
        total = h["total"]
        win_rate = h["win_rate"]
        avg_pnl = h["avg_pnl"]
        key = f"hour|{hour}"

        if win_rate >= 65 and avg_pnl > 0:
            desc = (
                f"BEST trading hour: {hour}:00 UTC has {win_rate}% win rate "
                f"(avg ${avg_pnl}, n={total}). Prioritize trades at this time."
            )
        elif win_rate <= 35 and avg_pnl < 0 and total >= 3:
            desc = (
                f"WORST trading hour: {hour}:00 UTC has {win_rate}% win rate "
                f"(avg ${avg_pnl}, n={total}). Consider skipping trades at this time."
            )
        else:
            continue

        db_save_learned_rule("timing", key, desc, min(0.8, 0.4 + total / 30), total, win_rate, avg_pnl)


def _learn_from_confidence_bands():
    bands = db_get_confidence_analysis()
    for b in bands:
        band = b["confidence_band"]
        total = b["total"]
        win_rate = b["win_rate"]
        avg_pnl = b["avg_pnl"]
        key = f"confidence|{band}"

        if total < 3:
            continue

        if win_rate >= 60:
            desc = (
                f"Confidence band {band}: {win_rate}% win rate, avg ${avg_pnl}, n={total}. "
                f"This confidence level is RELIABLE — size up."
            )
        elif win_rate <= 40:
            desc = (
                f"Confidence band {band}: only {win_rate}% win rate, avg ${avg_pnl}, n={total}. "
                f"Raise minimum confidence threshold or reduce size."
            )
        else:
            continue

        db_save_learned_rule("confidence", key, desc, min(0.8, 0.4 + total / 30), total, win_rate, avg_pnl)


def _learn_from_size_bands():
    bands = db_get_size_analysis()
    for b in bands:
        band = b["size_band"]
        total = b["total"]
        win_rate = b["win_rate"]
        avg_pnl = b["avg_pnl"]
        key = f"sizing|{band}"

        if total < 3:
            continue

        desc = f"Position size band {band}: {win_rate}% win rate, avg ${avg_pnl}, n={total}. "
        if avg_pnl > 0 and win_rate >= 55:
            desc += "This size range is PROFITABLE — use it more."
        elif avg_pnl < 0:
            desc += "This size range is LOSING money — adjust."

        db_save_learned_rule("sizing", key, desc, min(0.75, 0.4 + total / 30), total, win_rate, avg_pnl)


def _learn_from_strategy_combos():
    stats = db_get_strategy_stats()
    for s in stats:
        total = s["total_trades"]
        if total < 5:
            continue
        wins = s["wins"]
        win_rate = round(wins / total * 100, 1) if total else 0
        avg_pnl = s["avg_pnl"]
        symbol = s["symbol"]
        side = s["side"]
        regime = s["regime"]
        key = f"strategy|{s['strategy_key']}"

        if win_rate >= 60 and avg_pnl > 0:
            desc = (
                f"WINNING strategy: {side.upper()} {symbol} in {regime} — "
                f"{win_rate}% win rate, avg ${avg_pnl}, best ${s['best_pnl']}, "
                f"n={total}. DOUBLE DOWN on this combo."
            )
        elif win_rate <= 40 and avg_pnl < 0:
            desc = (
                f"LOSING strategy: {side.upper()} {symbol} in {regime} — "
                f"{win_rate}% win rate, avg ${avg_pnl}, worst ${s['worst_pnl']}, "
                f"n={total}. AVOID or reduce size significantly."
            )
        else:
            continue

        db_save_learned_rule("strategy", key, desc, min(0.85, 0.5 + total / 40), total, win_rate, avg_pnl)


def _learn_from_coin_regime_matrix():
    matrix = db_get_coin_regime_matrix()
    for m in matrix:
        symbol = m["symbol"]
        regime = m["regime"]
        side = m["side"]
        total = m["total"]
        win_rate = m["win_rate"]
        avg_pnl = m["avg_pnl"]
        key = f"matrix|{symbol}|{regime}|{side}"

        if total < 5:
            continue

        if win_rate >= 65:
            desc = (
                f"EDGE FOUND: {side.upper()} {symbol} in {regime} = {win_rate}% win rate, "
                f"avg ${avg_pnl}, n={total}. This is a MONEY MAKER."
            )
        elif win_rate <= 35:
            desc = (
                f"EDGE AGAINST: {side.upper()} {symbol} in {regime} = {win_rate}% win rate, "
                f"avg ${avg_pnl}, n={total}. STOP doing this."
            )
        else:
            continue

        db_save_learned_rule("coin_regime", key, desc, min(0.85, 0.5 + total / 30), total, win_rate, avg_pnl)


def _learn_from_fear_greed():
    """Extreme fear/greed often reverses — learn when to fade vs follow."""
    bands = db_get_fear_greed_performance()
    day_names = {
        "extreme_fear_0-25": "Extreme Fear (0-25)",
        "fear_25-45": "Fear (25-45)",
        "neutral_45-55": "Neutral (45-55)",
        "greed_55-75": "Greed (55-75)",
        "extreme_greed_75-100": "Extreme Greed (75-100)",
    }
    for b in bands:
        band = b["fg_band"]
        total = b["total"]
        win_rate = b["win_rate"]
        avg_pnl = b["avg_pnl"]
        key = f"fear_greed|{band}"
        label = day_names.get(band, band)
        if total < 3:
            continue
        if "extreme_fear" in band and win_rate >= 60 and avg_pnl > 0:
            desc = (
                f"CONTRARIAN EDGE: {label} — {win_rate}% win rate, avg ${avg_pnl}, n={total}. "
                f"Extreme fear often reverses. Consider fading (buying dips) in this zone."
            )
            db_save_learned_rule("fear_greed", key, desc, min(0.75, 0.5 + total / 40), total, win_rate, avg_pnl)
        elif "extreme_greed" in band and win_rate <= 40 and avg_pnl < 0:
            desc = (
                f"DANGER: {label} — only {win_rate}% win rate, avg ${avg_pnl}, n={total}. "
                f"Extreme greed = exhaustion. Reduce size or wait for pullback."
            )
            db_save_learned_rule("fear_greed", key, desc, min(0.75, 0.5 + total / 40), total, win_rate, avg_pnl)
        elif win_rate >= 65 and avg_pnl > 0:
            desc = (
                f"STRONG F&G zone: {label} — {win_rate}% win rate, avg ${avg_pnl}, n={total}. "
                f"Favor trades in this sentiment zone."
            )
            db_save_learned_rule("fear_greed", key, desc, min(0.7, 0.4 + total / 50), total, win_rate, avg_pnl)
        elif win_rate <= 35 and avg_pnl < 0:
            desc = (
                f"WEAK F&G zone: {label} — {win_rate}% win rate, avg ${avg_pnl}, n={total}. "
                f"Reduce size or skip when Fear & Greed is here."
            )
            db_save_learned_rule("fear_greed", key, desc, min(0.75, 0.5 + total / 40), total, win_rate, avg_pnl)


def _learn_from_day_of_week():
    """Monday/Friday/weekends behave differently in crypto."""
    dow_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    rows = db_get_dow_performance()
    for r in rows:
        day_num = r["day_of_week"]
        total = r["total"]
        win_rate = r["win_rate"]
        avg_pnl = r["avg_pnl"]
        key = f"dow|{day_num}"
        day_label = dow_names[day_num] if 0 <= day_num < 7 else f"D{day_num}"
        if total < 3:
            continue
        if win_rate >= 65 and avg_pnl > 0:
            desc = (
                f"BEST day: {day_label} has {win_rate}% win rate, avg ${avg_pnl}, n={total}. "
                f"Prioritize trades on {day_label}s."
            )
        elif win_rate <= 35 and avg_pnl < 0:
            desc = (
                f"WEAK day: {day_label} only {win_rate}% win rate, avg ${avg_pnl}, n={total}. "
                f"Reduce size or be more selective on {day_label}s."
            )
        else:
            continue
        db_save_learned_rule("timing", key, desc, min(0.7, 0.4 + total / 35), total, win_rate, avg_pnl)


def _learn_from_confluence():
    """Calibrate: does higher confluence actually predict better outcomes?"""
    bands = db_get_confluence_analysis()
    for b in bands:
        band = b["confluence_band"]
        total = b["total"]
        win_rate = b["win_rate"]
        avg_pnl = b["avg_pnl"]
        key = f"confluence|{band}"
        if total < 3:
            continue
        if "elite" in band or "strong" in band:
            if win_rate >= 60 and avg_pnl > 0:
                desc = (
                    f"CONFLUENCE WORKS: {band} has {win_rate}% win rate, avg ${avg_pnl}, n={total}. "
                    f"Strong confluence = reliable. Size up on 18+ confluence."
                )
                db_save_learned_rule("confluence", key, desc, min(0.8, 0.5 + total / 30), total, win_rate, avg_pnl)
        elif "weak" in band or "moderate" in band:
            if win_rate <= 40 and avg_pnl < 0:
                desc = (
                    f"LOW CONFLUENCE DANGER: {band} only {win_rate}% win rate, avg ${avg_pnl}, n={total}. "
                    f"Require confluence 18+ or WAIT."
                )
                db_save_learned_rule("confluence", key, desc, min(0.8, 0.5 + total / 30), total, win_rate, avg_pnl)


def _learn_from_volatility_regime():
    """High vs low vol — same setup, different outcomes."""
    rows = db_get_trades_for_vol_analysis()
    if len(rows) < 5:
        return
    vol_buckets: dict[str, list] = {"low_vol": [], "normal_vol": [], "high_vol": []}
    for r in rows:
        try:
            ind = json.loads(r.get("indicators_json", "{}"))
        except (json.JSONDecodeError, TypeError):
            continue
        atr = ind.get("atr") or ind.get("avg_atr") or 0
        bb_width = ind.get("bb_width") or 0
        entry = r.get("entry_price") or 1
        atr_pct = (atr / entry * 100) if entry > 0 and atr else 0
        if bb_width > 0:
            vol_proxy = bb_width
        else:
            vol_proxy = atr_pct
        if vol_proxy < 1.5:
            vol_buckets["low_vol"].append(r)
        elif vol_proxy < 3.0:
            vol_buckets["normal_vol"].append(r)
        else:
            vol_buckets["high_vol"].append(r)
    for vol_regime, trades in vol_buckets.items():
        if len(trades) < 3:
            continue
        wins = sum(1 for t in trades if t.get("win"))
        total = len(trades)
        avg_pnl = round(sum(t.get("pnl", 0) for t in trades) / total, 2)
        win_rate = round(wins / total * 100, 1)
        key = f"vol_regime|{vol_regime}"
        labels = {"low_vol": "Low vol (squeeze)", "normal_vol": "Normal vol", "high_vol": "High vol (expansion)"}
        if win_rate >= 60 and avg_pnl > 0:
            desc = (
                f"VOL EDGE: {labels.get(vol_regime, vol_regime)} — {win_rate}% win rate, avg ${avg_pnl}, n={total}. "
                f"This vol regime favors your strategy."
            )
            db_save_learned_rule("volatility", key, desc, min(0.7, 0.4 + total / 40), total, win_rate, avg_pnl)
        elif win_rate <= 40 and avg_pnl < 0:
            desc = (
                f"VOL TRAP: {labels.get(vol_regime, vol_regime)} — only {win_rate}% win rate, avg ${avg_pnl}, n={total}. "
                f"Reduce size or wider stops in this vol regime."
            )
            db_save_learned_rule("volatility", key, desc, min(0.75, 0.5 + total / 35), total, win_rate, avg_pnl)


def _learn_from_hold_duration():
    """Quick wins vs slow losers — optimal hold time."""
    bands = db_get_hold_duration_analysis()
    labels = {
        "fast_under_5min": "Fast (<5min)",
        "medium_5_15min": "Medium (5-15min)",
        "long_15_60min": "Long (15-60min)",
        "very_long_60min+": "Very long (60min+)",
    }
    for b in bands:
        band = b["hold_band"]
        total = b["total"]
        win_rate = b["win_rate"]
        avg_pnl = b["avg_pnl"]
        key = f"hold|{band}"
        label = labels.get(band, band)
        if total < 3:
            continue
        if win_rate >= 65 and avg_pnl > 0:
            desc = (
                f"HOLD EDGE: {label} — {win_rate}% win rate, avg ${avg_pnl}, n={total}. "
                f"Your best trades close in this timeframe. Don't hold losers too long."
            )
            db_save_learned_rule("hold_duration", key, desc, min(0.7, 0.4 + total / 40), total, win_rate, avg_pnl)
        elif win_rate <= 35 and avg_pnl < 0:
            desc = (
                f"HOLD TRAP: {label} — only {win_rate}% win rate, avg ${avg_pnl}, n={total}. "
                f"Consider cutting losers faster or taking profits sooner."
            )
            db_save_learned_rule("hold_duration", key, desc, min(0.7, 0.4 + total / 40), total, win_rate, avg_pnl)


def _learn_from_rr_ratio():
    """Does higher R:R improve outcomes? Require 2:1+ in weak regimes."""
    bands = db_get_rr_analysis()
    for b in bands:
        band = b["rr_band"]
        total = b["total"]
        win_rate = b["win_rate"]
        avg_pnl = b["avg_pnl"]
        key = f"rr|{band}"
        if total < 3:
            continue
        if "strong" in band or "good" in band:
            if win_rate >= 60 and avg_pnl > 0:
                desc = (
                    f"R:R WORKS: {band} planned R:R has {win_rate}% win rate, avg ${avg_pnl}, n={total}. "
                    f"Stick to 2:1+ R:R — it compounds."
                )
                db_save_learned_rule("rr_ratio", key, desc, min(0.75, 0.5 + total / 35), total, win_rate, avg_pnl)
        elif "low" in band:
            if win_rate <= 40 and avg_pnl < 0:
                desc = (
                    f"R:R TRAP: {band} — only {win_rate}% win rate, avg ${avg_pnl}, n={total}. "
                    f"Low R:R trades lose. Require 2:1+ minimum."
                )
                db_save_learned_rule("rr_ratio", key, desc, min(0.8, 0.5 + total / 30), total, win_rate, avg_pnl)


def _learn_from_confidence_calibration():
    """When AI predicted X% but actual was Y% — overconfident or underconfident?"""
    bands = db_get_confidence_calibration()
    for b in bands:
        pred = b.get("avg_predicted", 0) or 0
        actual = b.get("actual_win_rate", 0) or 0
        total = b["total"]
        avg_pnl = b["avg_pnl"]
        band_label = b.get("predicted_band", "")
        key = f"calibration|{band_label}"
        if total < 3:
            continue
        diff = actual - pred
        if diff < -15:
            desc = (
                f"OVERCONFIDENT: When you predicted {pred:.0f}%, actual was only {actual:.0f}% (n={total}). "
                f"Reduce confidence in similar setups. Require more signals."
            )
            db_save_learned_rule("calibration", key, desc, min(0.8, 0.5 + total / 25), total, actual, avg_pnl)
        elif diff > 15:
            desc = (
                f"UNDERCONFIDENT: When you predicted {pred:.0f}%, actual was {actual:.0f}% (n={total}). "
                f"You're too cautious here — size up when signals align."
            )
            db_save_learned_rule("calibration", key, desc, min(0.7, 0.4 + total / 30), total, actual, avg_pnl)


def _learn_from_recent_wins():
    """Extract rules from recent winning trades — what worked? DO MORE."""
    wins = db_get_recent_wins(limit=15)
    if len(wins) < 3:
        return
    from collections import Counter

    combos: Counter[str] = Counter()
    best_pnl = 0
    best_setup = None
    for w in wins:
        key = f"{w['side']}|{w['symbol']}|{w['regime']}"
        combos[key] += 1
        if w.get("pnl", 0) > best_pnl:
            best_pnl = w["pnl"]
            best_setup = (w["symbol"], w["side"], w["regime"], w.get("patterns", []))
    top_combo, count = combos.most_common(1)[0] if combos else (None, 0)
    if count >= 3 and top_combo:
        parts = top_combo.split("|")
        side, symbol, regime = (parts + ["?", "?", "?"])[:3]
        key = f"win_pattern|{top_combo}"
        desc = (
            f"WINNING FORMULA: {side.upper()} {symbol} in {regime} won {count} of last {len(wins)} trades. "
            f"DO MORE of this. Size up when this setup repeats."
        )
        db_save_learned_rule("win_pattern", key, desc, min(0.75, 0.5 + count / 20), count, 100, round(best_pnl, 2))
    if best_setup and best_pnl > 0:
        sym, side, regime, pats = best_setup
        key = f"best_win|{sym}|{side}|{regime}"
        desc = (
            f"BEST TRADE: {side.upper()} {sym} in {regime} (patterns {pats[:3]}) made +${best_pnl:.2f}. "
            f"Replicate this setup when signals align."
        )
        db_save_learned_rule("win_pattern", key, desc, 0.7, 1, 100, round(best_pnl, 2))


def build_memory_briefing() -> dict:
    """Build a concise memory briefing for Claude's decision-making.
    Returns structured data about what the bot has learned.
    LOSSES ARE PRIORITY — the AI must internalize every mistake to become elite.

    MEMORY COVERAGE (full checklist):
    - lessons_from_wins, lessons_from_losses, lessons_from_everything (scale_into/avoid)
    - regime_performance, pattern stats, strategy combos, coin_regime matrix
    - fear_greed_performance, day_of_week_performance, hour (time_of_day)
    - confluence_calibration, confidence_calibration
    - hold_duration_performance, rr_ratio_performance
    - volatility_regime (from vol analysis), momentum (streaks, buy/sell edge)
    - top_setups_to_double_down, recent_performance, weekly_stats
    """
    total = db_get_total_trade_count()

    briefing = {
        "total_trades_analyzed": total,
        "learning_active": total >= 5,
        "learning_mantra": (
            "LEARN FROM EVERYTHING. Every win shows what works — DO MORE. "
            "Every loss shows what fails — NEVER REPEAT. Super-tier traders learn from both."
        ),
    }

    if total < 5:
        briefing["message"] = (
            f"Only {total} trades recorded — need 5+ for full pattern learning. "
            "Every trade (win or loss) is captured. Shadow mode learns from blocked decisions too."
        )
        shadow = db_get_shadow_stats()
        if shadow.get("total_logged", 0) >= 5:
            briefing["shadow_bootstrap"] = {
                "total_shadow_decisions": shadow.get("total_logged", 0),
                "blocked_by_gate": shadow.get("blocked_by_gate", 0),
                "hint": "Shadow counterfactuals active — gate quality learning in progress.",
            }
        briefing["memory_dimensions_when_active"] = (
            "wins, losses, lessons_from_everything, patterns, regimes, strategy combos, "
            "fear_greed, dow, hour, confluence, confidence_calibration, hold_duration, "
            "rr_ratio, volatility, momentum, top_setups, shadow_outcomes, preset_performance, exit_reasons"
        )
        return briefing

    # ── LESSONS FROM EVERYTHING (super god tier: wins AND losses) ──
    recent_wins = db_get_recent_wins(limit=8)
    recent_losses = db_get_recent_losses(limit=8)

    if recent_wins:
        briefing["lessons_from_wins"] = [
            {
                "symbol": t["symbol"],
                "side": t["side"],
                "regime": t["regime"],
                "patterns": t.get("patterns", []),
                "confidence_at_entry": round(t.get("confidence", 0) * 100, 0),
                "pnl": t["pnl"],
                "lesson": (
                    f"DO MORE: {t['side'].upper()} {t['symbol']} in {t['regime']} "
                    f"when patterns {t.get('patterns', [])} — won ${t['pnl']:.2f}"
                ),
            }
            for t in recent_wins
        ]
        briefing["win_count_recent"] = len(recent_wins)

    # ── LESSONS FROM LOSSES (never repeat) ──
    if recent_losses:
        briefing["lessons_from_losses"] = [
            {
                "symbol": t["symbol"],
                "side": t["side"],
                "regime": t["regime"],
                "patterns": t.get("patterns", []),
                "confidence_at_entry": round(t.get("confidence", 0) * 100, 0),
                "pnl": t["pnl"],
                "lesson": (
                    f"Avoid {t['side'].upper()} {t['symbol']} in {t['regime']} "
                    f"when patterns {t.get('patterns', [])} — lost ${abs(t['pnl']):.2f}"
                ),
            }
            for t in recent_losses
        ]
        briefing["loss_count_recent"] = len(recent_losses)
        briefing["critical_reminder"] = (
            f"You have {len(recent_losses)} recent loss(es) in memory. "
            "Do NOT take similar setups. Raise your bar. Wait for A+ setups only."
        )

    # ── SYNTHESIS: what to scale into vs avoid ──
    if recent_wins or recent_losses:
        briefing["lessons_from_everything"] = {
            "scale_into": [
                f"{t['side'].upper()} {t['symbol']} in {t['regime']} (patterns {t.get('patterns', [])[:3]})"
                for t in (recent_wins or [])[:5]
            ],
            "avoid": [
                f"{t['side'].upper()} {t['symbol']} in {t['regime']} (patterns {t.get('patterns', [])[:3]})"
                for t in (recent_losses or [])[:5]
            ],
            "mantra": "Scale into what works. Avoid what fails. Learn from EVERYTHING.",
        }

    rules = db_get_active_rules()
    if rules:
        winning_rules = [r for r in rules if r["avg_pnl"] > 0 and r["win_rate"] >= 55]
        losing_rules = [r for r in rules if r["avg_pnl"] < 0 and r["win_rate"] <= 45]

        briefing["winning_edges"] = [
            {
                "rule": r["description"],
                "win_rate": r["win_rate"],
                "avg_pnl": r["avg_pnl"],
                "sample_size": r["sample_size"],
            }
            for r in winning_rules[:8]
        ]
        briefing["losing_patterns"] = [
            {
                "rule": r["description"],
                "win_rate": r["win_rate"],
                "avg_pnl": r["avg_pnl"],
                "sample_size": r["sample_size"],
            }
            for r in losing_rules[:10]
        ]

    regime_perf = db_get_regime_performance()
    if regime_perf:
        briefing["regime_performance"] = {
            regime: {
                "win_rate": stats["win_rate"],
                "avg_pnl": stats["avg_pnl"],
                "total": stats["total"],
            }
            for regime, stats in regime_perf.items()
        }

    fg_perf = db_get_fear_greed_performance()
    if fg_perf:
        briefing["fear_greed_performance"] = {
            b["fg_band"]: {
                "win_rate": b["win_rate"],
                "avg_pnl": b["avg_pnl"],
                "total": b["total"],
            }
            for b in fg_perf
        }

    conf_perf = db_get_confluence_analysis()
    if conf_perf:
        briefing["confluence_calibration"] = {
            b["confluence_band"]: {
                "win_rate": b["win_rate"],
                "avg_pnl": b["avg_pnl"],
                "total": b["total"],
            }
            for b in conf_perf
        }

    hourly_perf = db_get_hourly_performance()
    if hourly_perf:
        briefing["hourly_performance"] = {
            f"{h['hour_of_day']:02d}:00": {
                "win_rate": h["win_rate"],
                "avg_pnl": h["avg_pnl"],
                "total": h["total"],
            }
            for h in hourly_perf[:12]
        }

    dow_perf = db_get_dow_performance()
    if dow_perf:
        dow_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        briefing["day_of_week_performance"] = {
            (dow_names[r["day_of_week"]] if 0 <= r["day_of_week"] < 7 else f"D{r['day_of_week']}"): {
                "win_rate": r["win_rate"],
                "avg_pnl": r["avg_pnl"],
                "total": r["total"],
            }
            for r in dow_perf
        }

    hold_perf = db_get_hold_duration_analysis()
    if hold_perf:
        briefing["hold_duration_performance"] = {
            b["hold_band"]: {
                "win_rate": b["win_rate"],
                "avg_pnl": b["avg_pnl"],
                "total": b["total"],
            }
            for b in hold_perf
        }

    rr_perf = db_get_rr_analysis()
    if rr_perf:
        briefing["rr_ratio_performance"] = {
            b["rr_band"]: {
                "win_rate": b["win_rate"],
                "avg_pnl": b["avg_pnl"],
                "total": b["total"],
            }
            for b in rr_perf
        }

    calibration = db_get_confidence_calibration()
    if calibration:
        briefing["confidence_calibration"] = [
            {
                "predicted": b.get("avg_predicted"),
                "actual_win_rate": b.get("actual_win_rate"),
                "avg_pnl": b.get("avg_pnl"),
                "total": b["total"],
                "overconfident": (b.get("actual_win_rate", 0) or 0) < (b.get("avg_predicted", 0) or 0) - 15,
            }
            for b in calibration
        ]

    strategy_stats = db_get_strategy_stats()
    if strategy_stats:
        top_setups = [s for s in strategy_stats if s.get("avg_pnl", 0) > 0 and s.get("total_trades", 0) >= 3][:5]
        if top_setups:
            briefing["top_setups_to_double_down"] = [
                {
                    "combo": f"{s['side'].upper()} {s['symbol']} in {s['regime']}",
                    "win_rate": round(s["wins"] / s["total_trades"] * 100, 1) if s["total_trades"] else 0,
                    "avg_pnl": s["avg_pnl"],
                    "best_pnl": s["best_pnl"],
                    "total": s["total_trades"],
                }
                for s in top_setups
            ]

    recent = db_get_recent_trade_contexts(limit=10)
    if recent:
        recent_win_count = sum(1 for t in recent if t["win"])
        recent_pnl = sum(t["pnl"] for t in recent)
        briefing["recent_performance"] = {
            "last_10_win_rate": round(recent_win_count / len(recent) * 100, 1),
            "last_10_pnl": round(recent_pnl, 2),
            "trending": "improving" if recent_pnl > 0 else "declining",
        }

        if len(recent) >= 3:
            last_3 = recent[:3]
            last_3_wins = sum(1 for t in last_3 if t["win"])
            briefing["momentum"] = {
                "last_3_wins": last_3_wins,
                "hot_streak": last_3_wins == 3,
                "cold_streak": last_3_wins == 0,
            }

    sessions = db_get_session_history(limit=7)
    if sessions:
        profitable_days = sum(1 for s in sessions if s["total_pnl"] > 0)
        briefing["weekly_stats"] = {
            "profitable_days": profitable_days,
            "total_days": len(sessions),
            "weekly_pnl": round(sum(s["total_pnl"] for s in sessions), 2),
        }

    preset_perf = db_get_preset_performance(min_samples=2)
    if preset_perf:
        briefing["preset_performance"] = [
            {
                "preset": p["preset"],
                "win_rate": p["win_rate"],
                "avg_pnl": p["avg_pnl"],
                "total": p["total"],
            }
            for p in preset_perf[:5]
        ]

    exit_stats = db_get_exit_reason_stats(min_samples=2)
    if exit_stats:
        briefing["exit_reason_insights"] = {
            s["exit_type"]: {"win_rate": s["win_rate"], "avg_pnl": s["avg_pnl"], "total": s["total"]}
            for s in exit_stats
        }

    shadow_stats = db_get_shadow_stats()
    if shadow_stats.get("total_logged", 0) >= 3:
        briefing["shadow_insights"] = {
            "total_logged": shadow_stats.get("total_logged", 0),
            "blocked_by_gate": shadow_stats.get("blocked_by_gate", 0),
            "executed": shadow_stats.get("executed", 0),
            "blocked_saved_pct": shadow_stats.get("blocked_avg_loss_avoided_pct"),
            "blocked_missed_pct": shadow_stats.get("blocked_avg_opportunity_cost_pct"),
            "lesson": (
                "Gate blocks that saved losses = trust filters. "
                "Blocks that missed gains = don't over-filter A+ setups."
            ),
        }

    shadow_rules = [r for r in (db_get_active_rules() or []) if r.get("rule_type") == "shadow"]
    if shadow_rules:
        briefing["shadow_learned_rules"] = [r["description"] for r in shadow_rules[:3]]

    preset_rules = [r for r in (db_get_active_rules() or []) if r.get("rule_type") == "preset"]
    if preset_rules:
        briefing["preset_learned_rules"] = [r["description"] for r in preset_rules[:3]]

    return briefing


def _learn_momentum_rules():
    """Learn from win/loss streaks to calibrate aggression."""
    recent = db_get_recent_trade_contexts(limit=20)
    if len(recent) < 10:
        return

    last_5 = recent[:5]
    last_5_wins = sum(1 for t in last_5 if t["win"])
    last_5_pnl = sum(t["pnl"] for t in last_5)

    key = "momentum|recent_5"
    if last_5_wins >= 4 and last_5_pnl > 0:
        desc = (
            f"HOT STREAK: Won {last_5_wins}/5 recent trades, +${last_5_pnl:.2f}. "
            f"Momentum is strong — maintain sizing or size up slightly on A+ setups."
        )
        db_save_learned_rule("momentum", key, desc, 0.7, 5, last_5_wins / 5 * 100, round(last_5_pnl / 5, 2))
    elif last_5_wins <= 1 and last_5_pnl < 0:
        desc = (
            f"COLD STREAK: Won only {last_5_wins}/5 recent trades, ${last_5_pnl:.2f}. "
            f"Reduce size to 20%, wait for 4+ signal setups, skip marginal trades."
        )
        db_save_learned_rule("momentum", key, desc, 0.8, 5, last_5_wins / 5 * 100, round(last_5_pnl / 5, 2))

    last_10 = recent[:10]
    buy_trades = [t for t in last_10 if t["side"] == "buy"]
    sell_trades = [t for t in last_10 if t["side"] == "sell"]

    if len(buy_trades) >= 5:
        buy_wr = sum(1 for t in buy_trades if t["win"]) / len(buy_trades) * 100
        buy_pnl = sum(t["pnl"] for t in buy_trades) / len(buy_trades)
        if buy_wr >= 70:
            db_save_learned_rule(
                "momentum",
                "momentum|buy_edge",
                f"BUY edge active: {buy_wr:.0f}% win rate on buys recently. Favor long setups.",
                0.65,
                len(buy_trades),
                buy_wr,
                round(buy_pnl, 2),
            )
        elif buy_wr <= 30:
            db_save_learned_rule(
                "momentum",
                "momentum|buy_weak",
                f"BUY weakness: only {buy_wr:.0f}% win rate on buys recently. Avoid or reduce buy size.",
                0.65,
                len(buy_trades),
                buy_wr,
                round(buy_pnl, 2),
            )

    if len(sell_trades) >= 5:
        sell_wr = sum(1 for t in sell_trades if t["win"]) / len(sell_trades) * 100
        sell_pnl = sum(t["pnl"] for t in sell_trades) / len(sell_trades)
        if sell_wr >= 70:
            db_save_learned_rule(
                "momentum",
                "momentum|sell_edge",
                f"SELL edge active: {sell_wr:.0f}% win rate on sells recently. Favor short setups.",
                0.65,
                len(sell_trades),
                sell_wr,
                round(sell_pnl, 2),
            )
        elif sell_wr <= 30:
            db_save_learned_rule(
                "momentum",
                "momentum|sell_weak",
                f"SELL weakness: only {sell_wr:.0f}% win rate on sells recently. Avoid or reduce sell size.",
                0.65,
                len(sell_trades),
                sell_wr,
                round(sell_pnl, 2),
            )


def get_pattern_verdict(patterns: list, symbol: str, side: str, regime: str) -> dict:
    """Quick lookup: given current patterns, what does history say about this trade?"""
    if not patterns:
        return {"verdict": "neutral", "reason": "No patterns detected"}

    all_stats = db_get_pattern_stats(min_samples=2)
    relevant = [
        s
        for s in all_stats
        if s["pattern"] in patterns
        and (s["symbol"] == symbol or s["symbol"] == "ALL")
        and (s["side"] == side or s["side"] == "ALL")
    ]

    if not relevant:
        return {"verdict": "neutral", "reason": "No historical data for these patterns yet"}

    avg_wr = sum(s["win_rate"] for s in relevant) / len(relevant)
    avg_pnl = sum(s["avg_pnl"] for s in relevant) / len(relevant)
    total_samples = sum(s["total"] for s in relevant)

    winners = [s for s in relevant if s["win_rate"] >= 60]
    losers = [s for s in relevant if s["win_rate"] <= 40]

    if avg_wr >= 60 and avg_pnl > 0:
        verdict = "strong_buy" if side == "buy" else "strong_sell"
        reason = (
            f"History SUPPORTS this trade: {len(winners)} winning patterns found, "
            f"avg {avg_wr:.0f}% win rate across {total_samples} trades"
        )
    elif avg_wr <= 40 and avg_pnl < 0:
        verdict = "avoid"
        reason = (
            f"History WARNS against this trade: {len(losers)} losing patterns found, "
            f"avg {avg_wr:.0f}% win rate across {total_samples} trades"
        )
    else:
        verdict = "neutral"
        reason = f"Mixed history: {avg_wr:.0f}% avg win rate across {total_samples} trades"

    return {
        "verdict": verdict,
        "reason": reason,
        "avg_win_rate": round(avg_wr, 1),
        "avg_pnl": round(avg_pnl, 2),
        "sample_size": total_samples,
        "winning_patterns": [s["pattern"] for s in winners],
        "losing_patterns": [s["pattern"] for s in losers],
    }
