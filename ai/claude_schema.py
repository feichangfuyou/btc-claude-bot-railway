"""
JSON schema validation for Claude AI responses.
Prevents hallucinated or malformed trade parameters from reaching execution.
"""

from __future__ import annotations

from core.config import ACTIVE_COINS


def _coerce_float(v, default: float = 0.0) -> float:
    """Coerce value to float. LLMs sometimes return strings."""
    if v is None:
        return default
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        try:
            return float(v.replace(",", ""))
        except ValueError:
            return default
    return default


def _coerce_int(v, default: int = 0) -> int:
    """Coerce value to int."""
    if v is None:
        return default
    if isinstance(v, int):
        return v
    if isinstance(v, (float, str)):
        try:
            return int(float(str(v).replace(",", "")))
        except (ValueError, TypeError):
            return default
    return default


def _coerce_list_str(v) -> list[str]:
    """Coerce value to list of strings."""
    if v is None:
        return []
    if isinstance(v, list):
        return [str(x) for x in v]
    return []


def _coerce_str(v, default: str = "") -> str:
    """Coerce value to string."""
    if v is None:
        return default
    return str(v).strip()


def validate_scout_response(obj: dict) -> dict:
    """
    Validate and sanitize scout JSON response.
    Returns sanitized dict. Raises ValueError on fatal schema violations.
    """
    if not isinstance(obj, dict):
        raise ValueError("Scout response must be a JSON object")

    verdict = _coerce_str(obj.get("verdict"), "wait").lower()
    if verdict not in ("wait", "escalate"):
        verdict = "wait"

    symbol = _coerce_str(obj.get("symbol"), "BTC").upper()
    if symbol not in ACTIVE_COINS:
        symbol = ACTIVE_COINS[0] if ACTIVE_COINS else "BTC"

    direction = _coerce_str(obj.get("direction"), "none").lower()
    if direction not in ("buy", "sell", "none"):
        direction = "none"

    out = {
        "verdict": verdict,
        "symbol": symbol,
        "direction": direction,
        "signal_count": max(0, min(20, _coerce_int(obj.get("signal_count"), 0))),
        "tier1_count": max(0, min(20, _coerce_int(obj.get("tier1_count"), 0))),
        "confidence": max(0.0, min(1.0, _coerce_float(obj.get("confidence"), 0.0))),
        "top_signals": _coerce_list_str(obj.get("top_signals")),
        "regime": _coerce_str(obj.get("regime"), "ranging").lower().replace(" ", "_"),
        "reasoning": _coerce_str(obj.get("reasoning")),
    }

    regime_valid = ("ranging", "trending_up", "trending_down", "chaotic")
    if out["regime"] not in regime_valid:
        out["regime"] = "ranging"

    return out


def validate_trade_decision(obj: dict) -> dict:
    """
    Validate and sanitize trade decision JSON response.
    Coerces types, clamps ranges, ensures required structure.
    Returns sanitized dict. Raises ValueError on fatal violations.
    """
    if not isinstance(obj, dict):
        raise ValueError("Trade decision must be a JSON object")

    action_raw = _coerce_str(obj.get("action"), "wait").lower()
    valid_actions = ("buy", "sell", "wait", "close_all")
    action = action_raw if action_raw in valid_actions else "wait"

    symbol = _coerce_str(obj.get("symbol"), "BTC").upper()
    if symbol not in ACTIVE_COINS:
        symbol = ACTIVE_COINS[0] if ACTIVE_COINS else "BTC"

    confidence = max(0.0, min(1.0, _coerce_float(obj.get("confidence"), 0.0)))
    confluence_score = max(0, min(20, _coerce_int(obj.get("confluence_score"), 0)))

    market_cond = _coerce_str(obj.get("market_condition"), "ranging").lower().replace(" ", "_")
    if market_cond not in ("ranging", "trending_up", "trending_down", "chaotic"):
        market_cond = "ranging"

    out = {
        "action": action,
        "symbol": symbol,
        "market_condition": market_cond,
        "confidence": confidence,
        "confluence_score": confluence_score,
        "reasons_to_trade": _coerce_list_str(obj.get("reasons_to_trade")),
        "reasons_to_wait": _coerce_list_str(obj.get("reasons_to_wait")),
        "reasoning": _coerce_str(obj.get("reasoning")),
        "patterns_detected": _coerce_list_str(obj.get("patterns_detected")),
        "key_signals": _coerce_list_str(obj.get("key_signals")),
    }

    if action in ("buy", "sell"):
        order_raw = obj.get("order")
        if not isinstance(order_raw, dict):
            raise ValueError("action is buy/sell but order is missing or not an object")

        o = order_raw
        order_side = _coerce_str(o.get("side"), "buy").lower()
        if order_side not in ("buy", "sell"):
            order_side = action
        order_symbol = _coerce_str(o.get("symbol"), symbol).upper()
        if order_symbol not in ACTIVE_COINS:
            order_symbol = symbol

        size_pct = max(10, min(35, _coerce_float(o.get("size_percent"), 20)))
        entry = _coerce_float(o.get("entry_price"), 0)
        tp = _coerce_float(o.get("take_profit"), 0)
        sl = _coerce_float(o.get("stop_loss"), 0)

        if entry <= 0 or tp <= 0 or sl <= 0:
            raise ValueError("entry_price, take_profit, stop_loss must be positive numbers")

        # Sanity: BUY => TP > entry > SL; SELL => SL > entry > TP
        if order_side == "buy" and not (tp > entry > sl):
            raise ValueError("BUY order: take_profit must be above entry, stop_loss below entry")
        if order_side == "sell" and not (sl > entry > tp):
            raise ValueError("SELL order: stop_loss must be above entry, take_profit below entry")

        out["order"] = {
            "side": order_side,
            "symbol": order_symbol,
            "size_percent": size_pct,
            "entry_price": entry,
            "take_profit": tp,
            "stop_loss": sl,
        }
    else:
        out["order"] = None

    if action == "close_all":
        close_sym = obj.get("close_symbol")
        if close_sym is not None and str(close_sym).strip():
            out["close_symbol"] = _coerce_str(close_sym).upper()
        else:
            out["close_symbol"] = None
    else:
        out["close_symbol"] = None

    # Preserve internal fields added by our pipeline (_model_used, _stage, etc.)
    for k, v in obj.items():
        if k.startswith("_") and k not in out:
            out[k] = v

    return out
