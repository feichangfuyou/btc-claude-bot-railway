"""
Trading presets inspired by legendary traders and institutional strategies.
Deep research from Jesse Livermore, George Soros, Paul Tudor Jones, Turtle Traders,
Ed Seykota, Stanley Druckenmiller, Bruce Kovner, Mark Minervini, and crypto best practices.

Each preset defines SL/TP ATR multipliers per regime (ranging, trending, chaotic).
Values are MINIMUMS—the bot widens AI suggestions if they fall below these.
"""

# Format: (min_sl_atr, min_tp_atr) per regime -> (ranging, trending, chaotic)
# min_rr = minimum reward:risk ratio

PRESETS = {
    "default": {
        "name": "Default (Balanced)",
        "trader": "Bot default",
        "description": "Moderate risk, 1.5–2:1 R:R. General-purpose crypto swing.",
        "ranging": {"sl": 1.2, "tp": 2.0},
        "trending": {"sl": 1.5, "tp": 2.5},
        "chaotic": {"sl": 2.0, "tp": 3.0},
        "min_rr": 1.5,
        "ai_guidance": "TP at 2.5–4x ATR, SL at 1.5–2.5x ATR.",
    },
    "turtle": {
        "name": "Turtle Traders",
        "trader": "Richard Dennis",
        "description": "2N (2×ATR) stops, mechanical trend-following. Max 2% risk/trade.",
        "ranging": {"sl": 2.0, "tp": 4.0},
        "trending": {"sl": 2.0, "tp": 4.0},
        "chaotic": {"sl": 2.5, "tp": 5.0},
        "min_rr": 1.8,
        "ai_guidance": "SL at 2×ATR. TP at 4×ATR. Mechanical trend follow—let winners run.",
    },
    "soros": {
        "name": "Soros Reflexivity",
        "trader": "George Soros",
        "description": "Always has SL. Decisive macro bets. Asymmetric when right.",
        "ranging": {"sl": 1.8, "tp": 3.5},
        "trending": {"sl": 2.0, "tp": 4.0},
        "chaotic": {"sl": 2.5, "tp": 5.0},
        "min_rr": 1.8,
        "ai_guidance": "Never enter without defined SL. TP 2–3× risk. Cut losers, press winners.",
    },
    "ptj": {
        "name": "Paul Tudor Jones",
        "trader": "Paul Tudor Jones",
        "description": "Great defense > offense. Mental stops. Assume every position is wrong.",
        "ranging": {"sl": 2.0, "tp": 3.5},
        "trending": {"sl": 2.0, "tp": 4.0},
        "chaotic": {"sl": 2.5, "tp": 5.0},
        "min_rr": 1.5,
        "ai_guidance": "SL 2×ATR minimum. Capital preservation first. Time stops if trade stalls.",
    },
    "livermore": {
        "name": "Livermore Pivots",
        "trader": "Jesse Livermore",
        "description": "Cut at pivot failure. Pyramid into winners. Never average down.",
        "ranging": {"sl": 1.5, "tp": 3.0},
        "trending": {"sl": 1.8, "tp": 3.5},
        "chaotic": {"sl": 2.0, "tp": 4.0},
        "min_rr": 1.8,
        "ai_guidance": "SL at pivot invalidation (~1.5–2×ATR). Add to winners only. Cut fast when wrong.",
    },
    "seykota": {
        "name": "Ed Seykota",
        "trader": "Ed Seykota",
        "description": "ATR position sizing. 1% risk. Trailing stops where chart sours.",
        "ranging": {"sl": 2.0, "tp": 4.0},
        "trending": {"sl": 2.5, "tp": 5.0},
        "chaotic": {"sl": 2.5, "tp": 5.0},
        "min_rr": 1.8,
        "ai_guidance": "SL 2–2.5×ATR. Let winners run with trailing stops. Risk 1% per trade.",
    },
    "druckenmiller": {
        "name": "Druckenmiller Macro",
        "trader": "Stanley Druckenmiller",
        "description": "Cut fast when wrong. Press hard when right. Concentrated conviction.",
        "ranging": {"sl": 1.8, "tp": 4.0},
        "trending": {"sl": 2.0, "tp": 5.0},
        "chaotic": {"sl": 2.0, "tp": 4.5},
        "min_rr": 2.0,
        "ai_guidance": "Cut losers fast. TP 2–2.5× SL when thesis confirms. Asymmetric sizing.",
    },
    "kovner": {
        "name": "Kovner Conservative",
        "trader": "Bruce Kovner",
        "description": "Undertrade. Volatility-adjusted. Preserve capital first.",
        "ranging": {"sl": 2.0, "tp": 3.5},
        "trending": {"sl": 2.5, "tp": 4.5},
        "chaotic": {"sl": 3.0, "tp": 5.5},
        "min_rr": 1.5,
        "ai_guidance": "Wide SL (2–3×ATR). Avoid overtrading. Preserve capital.",
    },
    "minervini": {
        "name": "Minervini Momentum",
        "trader": "Mark Minervini",
        "description": "7–8% stop, let winners run 20–30%. Risk management over win rate.",
        "ranging": {"sl": 2.0, "tp": 4.5},
        "trending": {"sl": 2.0, "tp": 5.0},
        "chaotic": {"sl": 2.5, "tp": 5.0},
        "min_rr": 2.2,
        "ai_guidance": "SL ~2×ATR. TP 2.2–2.5× risk. Let winners run. Cut losers at 7–8% equivalent.",
    },
    "williams_balanced": {
        "name": "Williams Balanced",
        "trader": "Larry Williams",
        "description": "2× ATR industry standard. Balanced risk/reward.",
        "ranging": {"sl": 1.8, "tp": 3.0},
        "trending": {"sl": 2.0, "tp": 3.5},
        "chaotic": {"sl": 2.5, "tp": 4.5},
        "min_rr": 1.5,
        "ai_guidance": "SL 2×ATR (industry standard). TP 1.5–2× SL.",
    },
    "williams_swing": {
        "name": "Williams Swing",
        "trader": "Larry Williams",
        "description": "3× ATR for volatile markets. Swing trading timeframe.",
        "ranging": {"sl": 2.5, "tp": 4.5},
        "trending": {"sl": 2.5, "tp": 5.0},
        "chaotic": {"sl": 3.0, "tp": 6.0},
        "min_rr": 1.5,
        "ai_guidance": "SL 2.5–3×ATR for crypto volatility. TP 2× SL.",
    },
    "raschke": {
        "name": "Raschke Short-Term",
        "trader": "Linda Raschke",
        "description": "Keltner-style (2.5 ATR). Cut losers quickly. ATR-based tools.",
        "ranging": {"sl": 1.5, "tp": 3.5},
        "trending": {"sl": 2.0, "tp": 4.0},
        "chaotic": {"sl": 2.0, "tp": 4.0},
        "min_rr": 1.8,
        "ai_guidance": "SL 1.5–2×ATR. Keltner-style bands. Cut losers fast.",
    },
    "crypto_swing": {
        "name": "Crypto Swing Pro",
        "trader": "Crypto best practices",
        "description": "2–3× ATR for 4h–1D. Accommodates crypto volatility.",
        "ranging": {"sl": 2.0, "tp": 4.0},
        "trending": {"sl": 2.5, "tp": 5.0},
        "chaotic": {"sl": 3.0, "tp": 6.0},
        "min_rr": 1.8,
        "ai_guidance": "SL 2–3×ATR. Crypto needs room. Avoid whipsaws.",
    },
    "crypto_conservative": {
        "name": "Crypto Maximum Room",
        "trader": "High-volatility best practices",
        "description": "3× ATR+ stops. For extreme volatility. Fewer trades, wider stops.",
        "ranging": {"sl": 2.5, "tp": 5.0},
        "trending": {"sl": 3.0, "tp": 6.0},
        "chaotic": {"sl": 3.5, "tp": 7.0},
        "min_rr": 1.5,
        "ai_guidance": "SL 2.5–3.5×ATR. Maximum breathing room. Reduce false stops.",
    },
}


def get_preset(preset_id: str | None) -> dict:
    """Return preset config. Falls back to 'turtle' if invalid."""
    pid = (preset_id or "").strip().lower() or "turtle"
    return PRESETS.get(pid, PRESETS["turtle"])


def get_sl_tp_for_regime(preset_id: str | None, regime: str) -> tuple[float, float]:
    """Return (min_sl_atr, min_tp_atr) for the given preset and regime."""
    p = get_preset(preset_id)
    regime = (regime or "ranging").lower()
    if regime == "chaotic":
        r = p["chaotic"]
    elif regime in ("trending_up", "trending_down"):
        r = p["trending"]
    else:
        r = p["ranging"]
    return r["sl"], r["tp"]


def get_min_rr(preset_id: str | None) -> float:
    """Return minimum R:R for the preset."""
    return get_preset(preset_id).get("min_rr", 1.5)


def list_presets() -> list[dict]:
    """Return all presets for UI selection."""
    return [
        {
            "id": k,
            "name": v["name"],
            "trader": v["trader"],
            "description": v["description"],
        }
        for k, v in PRESETS.items()
    ]
