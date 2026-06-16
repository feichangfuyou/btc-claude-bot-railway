"""
Know Your Agent (KYA) & Compliance Guardrails.

Since non-human identities now outnumber humans, exchanges are implementing
"Agentic Firewalls." This module provides:

1. Cryptographic Identity (DID): The bot gets its own Decentralized Identifier
   so it can sign its own "Reasoning Traces."

2. Reasoning Hash: Every trade decision is hashed and stored alongside the trade.
   If the bot ever does something "crazy," there's a verifiable trace of *why*
   it thought that was a good idea.

3. Decision Audit Log: Full reasoning chain stored in the database — not just
   the trade, but the complete decision context with a tamper-evident hash.

4. Multi-Model Fallback: If the primary model (Anthropic) is down, the bot
   gracefully degrades instead of freezing positions.

Requires:
  - BOT_DID_SEED env var (optional — auto-generated if not set)
  - ENABLE_AUDIT_LOG env var (default: true)
"""

import hashlib
import json
import logging
import os
import time
import uuid
from datetime import UTC, datetime

logger = logging.getLogger("claudebot.kya")

ENABLE_AUDIT_LOG = os.getenv("ENABLE_AUDIT_LOG", "true").lower() == "true"
BOT_DID_SEED = os.getenv("BOT_DID_SEED", "")


_bot_did: str | None = None
_bot_did_key_hash: str | None = None


def _generate_did() -> tuple[str, str]:
    """Generate a DID:key identifier for the bot.
    Uses a deterministic seed if BOT_DID_SEED is set, otherwise random."""
    if BOT_DID_SEED:
        seed = BOT_DID_SEED.encode()
    else:
        seed = uuid.uuid4().bytes

    key_hash = hashlib.sha256(seed).hexdigest()
    did = f"did:key:z{key_hash[:48]}"
    return did, key_hash


def get_bot_did() -> str:
    """Return the bot's DID (Decentralized Identifier)."""
    global _bot_did, _bot_did_key_hash
    if _bot_did is None:
        _bot_did, _bot_did_key_hash = _generate_did()
        logger.info(f"Bot DID initialized: {_bot_did}")
    return _bot_did


def get_bot_key_hash() -> str:
    """Return the bot's key hash for signing."""
    global _bot_did_key_hash
    if _bot_did_key_hash is None:
        get_bot_did()
    return _bot_did_key_hash or ""


def hash_reasoning(decision: dict) -> str:
    """Create a tamper-evident hash of a trade decision's reasoning chain.

    The hash covers:
    - action, symbol, confidence, reasoning
    - reasons_to_trade, reasons_to_wait
    - key_signals, patterns_detected
    - order details (entry, tp, sl, size)
    - adversary verdict (if present)
    - timestamp

    This creates a verifiable audit trail: if someone asks "why did the bot
    do X?", the hash proves the stored reasoning hasn't been altered.
    """
    canonical = {
        "action": decision.get("action", "wait"),
        "symbol": decision.get("symbol", "BTC"),
        "confidence": decision.get("confidence", 0),
        "reasoning": decision.get("reasoning", ""),
        "reasons_to_trade": sorted(decision.get("reasons_to_trade", [])),
        "reasons_to_wait": sorted(decision.get("reasons_to_wait", [])),
        "key_signals": sorted(decision.get("key_signals", [])),
        "patterns_detected": sorted(decision.get("patterns_detected", [])),
        "market_condition": decision.get("market_condition", ""),
        "regime": decision.get("regime", decision.get("market_condition", "")),
        "confluence_score": decision.get("confluence_score", 0),
    }

    order = decision.get("order", {})
    if order:
        canonical["order"] = {
            "side": order.get("side", ""),
            "entry_price": order.get("entry_price", 0),
            "take_profit": order.get("take_profit", 0),
            "stop_loss": order.get("stop_loss", 0),
            "size_percent": order.get("size_percent", 0),
        }

    adversary = decision.get("_adversary", {})
    if adversary:
        canonical["adversary_verdict"] = adversary.get("verdict", "pass")
        canonical["adversary_risk_score"] = adversary.get("risk_score", 0)

    canonical["timestamp"] = decision.get(
        "timestamp",
        datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S"),
    )

    raw = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()


def sign_reasoning_trace(decision: dict) -> dict:
    """Sign a reasoning trace with the bot's DID.

    Returns a signed envelope containing:
    - reasoning_hash: SHA-256 of the canonical decision
    - bot_did: the bot's decentralized identifier
    - signed_at: UTC timestamp
    - key_fingerprint: first 16 chars of the signing key hash
    """
    reasoning_hash = hash_reasoning(decision)
    did = get_bot_did()
    key_hash = get_bot_key_hash()

    signature_input = f"{reasoning_hash}:{did}:{key_hash}"
    signature = hashlib.sha256(signature_input.encode()).hexdigest()

    return {
        "reasoning_hash": reasoning_hash,
        "bot_did": did,
        "signed_at": datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S"),
        "key_fingerprint": key_hash[:16],
        "signature": signature,
    }


def build_audit_entry(
    decision: dict,
    trade_result: dict | None = None,
    vision_result: dict | None = None,
    solver_result: dict | None = None,
) -> dict:
    """Build a complete audit log entry for a trade decision.

    This is the "black box flight recorder" — everything needed to
    reconstruct why the bot made a specific decision.
    """
    signed_trace = sign_reasoning_trace(decision)

    entry = {
        "audit_id": str(uuid.uuid4()),
        "timestamp": datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S"),
        "bot_did": signed_trace["bot_did"],
        "reasoning_hash": signed_trace["reasoning_hash"],
        "signature": signed_trace["signature"],
        "decision": {
            "action": decision.get("action", "wait"),
            "symbol": decision.get("symbol", "BTC"),
            "confidence": decision.get("confidence", 0),
            "reasoning": decision.get("reasoning", ""),
            "reasons_to_trade": decision.get("reasons_to_trade", []),
            "reasons_to_wait": decision.get("reasons_to_wait", []),
            "key_signals": decision.get("key_signals", []),
            "patterns_detected": decision.get("patterns_detected", []),
            "market_condition": decision.get("market_condition", ""),
            "regime": decision.get("regime", decision.get("market_condition", "")),
            "confluence_score": decision.get("confluence_score", 0),
        },
        "order": decision.get("order"),
        "model_used": decision.get("_model_used", "unknown"),
        "stage": decision.get("_stage", "unknown"),
        "scout_agreed": decision.get("_scout_agreed", False),
        "adversary": {
            "verdict": decision.get("_adversary", {}).get("verdict", "none"),
            "risk_score": decision.get("_adversary", {}).get("risk_score", 0),
            "kill_signals": decision.get("_adversary", {}).get("kill_signals", []),
            "reasoning": decision.get("_adversary", {}).get("reasoning", ""),
        },
    }

    if vision_result:
        entry["vision"] = {
            "structure": vision_result.get("structure", "neutral"),
            "conviction": vision_result.get("conviction", 0.5),
            "momentum": vision_result.get("momentum", "building"),
            "confirms_trade": vision_result.get("confirms_trade", True),
            "pattern": vision_result.get("pattern", "none"),
            "risk_flag": vision_result.get("risk_flag", "none"),
        }

    if solver_result:
        entry["solver"] = {
            "used": True,
            "network": solver_result.get("intent", {}).get("solver_used", "none"),
            "slippage_saved": solver_result.get("intent", {}).get("slippage_saved", 0),
            "gas_saved": solver_result.get("intent", {}).get("gas_saved", 0),
            "fill_time_sec": solver_result.get("execution_time_sec", 0),
        }

    if trade_result:
        entry["trade_result"] = {
            "pnl": trade_result.get("pnl", 0),
            "win": trade_result.get("win", False),
            "exit_price": trade_result.get("exit", 0),
            "reason": trade_result.get("reason", ""),
        }

    return entry


def _is_account_level_error(error: str) -> bool:
    """True when the failure is account-wide (billing, auth) — switching models won't help."""
    lower = error.lower()
    return any(
        phrase in lower
        for phrase in (
            "credit balance",
            "balance is zero",
            "balance is too low",
            "no anthropic api key",
            "invalid api key",
            "authentication",
            "permission denied",
        )
    )


class MultiModelFallback:
    """Handles graceful degradation when the primary AI model is unavailable.

    Instead of freezing positions when Anthropic is down, the bot:
    1. Tries the primary model
    2. Falls back to a cheaper/faster model
    3. If all models fail, enters "defensive mode" — tighten stops, no new trades
    """

    FALLBACK_CHAIN = [
        "claude-opus-4-6",
        "claude-sonnet-4-6",
        "claude-haiku-4-5-20251001",
    ]

    def __init__(self):
        self.primary_failures: int = 0
        self.last_failure_ts: float = 0
        self.last_error: str = ""
        self.current_model_idx: int = 0
        self.defensive_mode: bool = False
        self._failure_window_sec = 300  # 5 min window for counting failures
        self._max_failures_before_fallback = 3
        self._defensive_threshold = len(self.FALLBACK_CHAIN)

    def record_success(self, model: str):
        """Record a successful API call — reset failure counters.
        Keeps current_model_idx so we don't immediately retry a broken primary."""
        self.primary_failures = 0
        self.defensive_mode = False

    def record_failure(self, model: str, error: str) -> str | None:
        """Record a failed API call. Returns next model to try, or None for defensive mode."""
        now = time.time()
        if now - self.last_failure_ts > self._failure_window_sec:
            self.primary_failures = 0
        self.last_failure_ts = now
        self.last_error = error
        self.primary_failures += 1

        logger.warning(f"Model {model} failed ({self.primary_failures}x): {error[:60]}")

        # Billing/auth errors affect every model — don't waste calls cycling the fallback chain.
        if _is_account_level_error(error):
            self.defensive_mode = True
            logger.error("Account-level API error — entering DEFENSIVE MODE: %s", error[:80])
            return None

        if self.primary_failures >= self._defensive_threshold:
            self.defensive_mode = True
            logger.error("All models failed — entering DEFENSIVE MODE")
            return None

        self.current_model_idx = min(
            self.current_model_idx + 1,
            len(self.FALLBACK_CHAIN) - 1,
        )
        next_model = self.FALLBACK_CHAIN[self.current_model_idx]
        logger.info(f"Falling back to {next_model}")
        return next_model

    def get_current_model(self, preferred: str) -> str:
        """Get the model to use, considering fallback state."""
        if self.primary_failures == 0:
            return preferred
        if self.current_model_idx < len(self.FALLBACK_CHAIN):
            return self.FALLBACK_CHAIN[self.current_model_idx]
        return preferred

    def is_defensive(self) -> bool:
        """True if all models have failed and bot should enter defensive mode."""
        return self.defensive_mode

    def defensive_reason(self) -> str:
        """Human-readable reason defensive mode was entered."""
        if self.last_error:
            return self.last_error
        return "All AI models failed"

    def reset(self) -> None:
        """Clear defensive mode and failure counters. Use after adding Anthropic credits."""
        self.primary_failures = 0
        self.current_model_idx = 0
        self.defensive_mode = False
        self.last_failure_ts = 0
        self.last_error = ""
        logger.info("Model fallback reset — brain ready for new API calls")

    def snapshot(self) -> dict:
        return {
            "primary_failures": self.primary_failures,
            "current_fallback_idx": self.current_model_idx,
            "current_model": self.FALLBACK_CHAIN[self.current_model_idx]
            if self.current_model_idx < len(self.FALLBACK_CHAIN)
            else "none",
            "defensive_mode": self.defensive_mode,
            "last_error": self.last_error or None,
            "last_failure_age_sec": round(time.time() - self.last_failure_ts, 1) if self.last_failure_ts else None,
        }


model_fallback = MultiModelFallback()
