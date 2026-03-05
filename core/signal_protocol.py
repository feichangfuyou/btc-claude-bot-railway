"""
Signal Protocol — defines the communication format between
the server (AI brain) and the client execution agent.

Server generates signals, client executes them.
Signals flow over WebSocket or are polled from the database.
"""

import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class TradeSignal:
    """A trade signal from the server to the client agent."""

    signal_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    action: str = "buy"  # buy | sell | close | close_all
    symbol: str = "BTC"
    exchange: Optional[str] = None  # target exchange or None for router to decide
    size_pct: float = 0.15  # % of balance
    price_target: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    confidence: float = 0.0
    reasoning: str = ""
    product_type: str = "spot"  # spot | futures | onchain
    leverage: int = 1
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "TradeSignal":
        valid_fields = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in d.items() if k in valid_fields})


@dataclass
class ExecutionResult:
    """Result from the client agent after executing a signal."""

    signal_id: str
    status: str = "executed"  # executed | rejected | failed | expired
    exchange: str = ""
    fill_price: Optional[float] = None
    fill_size: Optional[float] = None
    fill_usd: Optional[float] = None
    fees: float = 0.0
    order_id: Optional[str] = None
    error: Optional[str] = None
    executed_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "ExecutionResult":
        valid_fields = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in d.items() if k in valid_fields})


def create_signal_from_decision(decision: dict, exchange: str = None) -> TradeSignal:
    """Convert a Claude AI decision into a TradeSignal."""
    action = decision.get("action", "wait")
    if action == "wait":
        return None

    return TradeSignal(
        action=action,
        symbol=decision.get("symbol", "BTC"),
        exchange=exchange,
        size_pct=decision.get("size_pct", 0.15),
        stop_loss=decision.get("stop_loss"),
        take_profit=decision.get("take_profit"),
        confidence=decision.get("confidence", 0),
        reasoning=decision.get("reasoning", ""),
        product_type=decision.get("product_type", "spot"),
        leverage=decision.get("leverage", 1),
    )
