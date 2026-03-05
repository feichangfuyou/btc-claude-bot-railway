"""
CircuitBreaker — robust consecutive-loss protection for the trading bot.
Pauses trading after N consecutive losses; clears on first win.
State is persisted so breaker survives restarts.
"""

from core.config import MAX_CONSEC_LOSSES
from core.database import db_load_state, db_save_state


class CircuitBreaker:
    """
    Tracks consecutive losses and trips when threshold is exceeded.
    Persists both streak count and tripped state across restarts.
    """

    def __init__(self, max_consec_losses: int | None = None):
        self._max = max_consec_losses if max_consec_losses is not None else MAX_CONSEC_LOSSES
        self._consecutive_losses = db_load_state("consecutive_losses") or 0
        # Persist loss_breaker_active so it survives restarts
        saved_active = db_load_state("loss_breaker_active")
        if saved_active is not None:
            self._tripped = bool(saved_active)
        else:
            # Key missing (first run or legacy) — derive from streak
            self._tripped = self._consecutive_losses >= self._max
        if self._tripped:
            self._persist_tripped()

    @property
    def consecutive_losses(self) -> int:
        return self._consecutive_losses

    @property
    def loss_breaker_active(self) -> bool:
        """Alias for is_tripped — backward compat."""
        return self._tripped

    def is_tripped(self) -> bool:
        """True if trading should be blocked."""
        return self._tripped

    def get_cooldown_multiplier(self) -> float:
        """Multiplier for TRADE_COOLDOWN_SEC (1 + min(losses, 2))."""
        return 1.0 + min(self._consecutive_losses, 2)

    def record_loss(self, on_tripped_callback=None) -> bool:
        """
        Record a losing trade. Returns True if breaker just tripped.
        on_tripped_callback: optional async callable () for notification.
        """
        self._consecutive_losses += 1
        db_save_state("consecutive_losses", self._consecutive_losses)

        if self._consecutive_losses >= self._max:
            just_tripped = not self._tripped
            self._tripped = True
            self._persist_tripped()
            if just_tripped and on_tripped_callback:
                try:
                    import asyncio

                    asyncio.create_task(on_tripped_callback())
                except Exception:
                    pass
            return just_tripped
        return False

    def record_win(self) -> bool:
        """
        Record a winning trade. Clears streak and resets breaker.
        Returns True if breaker was tripped and is now cleared.
        """
        was_tripped = self._tripped
        self._consecutive_losses = 0
        self._tripped = False
        db_save_state("consecutive_losses", self._consecutive_losses)
        self._persist_tripped()
        return was_tripped

    def reset(self) -> None:
        """Manual reset — clears streak and breaker regardless of last trade."""
        self._consecutive_losses = 0
        self._tripped = False
        db_save_state("consecutive_losses", 0)
        self._persist_tripped()

    def _persist_tripped(self) -> None:
        db_save_state("loss_breaker_active", self._tripped)

    def snapshot(self) -> dict:
        """For API / frontend — current state."""
        return {
            "consecutive_losses": self._consecutive_losses,
            "loss_breaker_active": self._tripped,
            "max_consec_losses": self._max,
        }
