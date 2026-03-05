"""Tests for CircuitBreaker — consecutive loss protection."""

from unittest.mock import patch

from safety.circuit_breaker import CircuitBreaker


@patch("safety.circuit_breaker.db_load_state", return_value=None)
@patch("safety.circuit_breaker.db_save_state")
def test_initial_state_clean(mock_save, mock_load):
    cb = CircuitBreaker(max_consec_losses=3)
    assert cb.consecutive_losses == 0
    assert not cb.is_tripped()
    assert not cb.loss_breaker_active


@patch("safety.circuit_breaker.db_load_state", return_value=None)
@patch("safety.circuit_breaker.db_save_state")
def test_record_loss_increments(mock_save, mock_load):
    cb = CircuitBreaker(max_consec_losses=5)
    cb.record_loss()
    assert cb.consecutive_losses == 1
    assert not cb.is_tripped()


@patch("safety.circuit_breaker.db_load_state", return_value=None)
@patch("safety.circuit_breaker.db_save_state")
def test_trips_at_threshold(mock_save, mock_load):
    cb = CircuitBreaker(max_consec_losses=3)
    cb.record_loss()
    cb.record_loss()
    just_tripped = cb.record_loss()
    assert just_tripped is True
    assert cb.is_tripped()
    assert cb.consecutive_losses == 3


@patch("safety.circuit_breaker.db_load_state", return_value=None)
@patch("safety.circuit_breaker.db_save_state")
def test_win_resets_breaker(mock_save, mock_load):
    cb = CircuitBreaker(max_consec_losses=3)
    cb.record_loss()
    cb.record_loss()
    cb.record_loss()
    assert cb.is_tripped()
    was_tripped = cb.record_win()
    assert was_tripped is True
    assert not cb.is_tripped()
    assert cb.consecutive_losses == 0


@patch("safety.circuit_breaker.db_load_state", return_value=None)
@patch("safety.circuit_breaker.db_save_state")
def test_manual_reset(mock_save, mock_load):
    cb = CircuitBreaker(max_consec_losses=2)
    cb.record_loss()
    cb.record_loss()
    assert cb.is_tripped()
    cb.reset()
    assert not cb.is_tripped()
    assert cb.consecutive_losses == 0


@patch("safety.circuit_breaker.db_load_state", return_value=None)
@patch("safety.circuit_breaker.db_save_state")
def test_cooldown_multiplier(mock_save, mock_load):
    cb = CircuitBreaker(max_consec_losses=5)
    assert cb.get_cooldown_multiplier() == 1.0
    cb.record_loss()
    assert cb.get_cooldown_multiplier() == 2.0
    cb.record_loss()
    assert cb.get_cooldown_multiplier() == 3.0
    cb.record_loss()
    assert cb.get_cooldown_multiplier() == 3.0  # capped at 1 + min(losses, 2)


@patch("safety.circuit_breaker.db_load_state", return_value=None)
@patch("safety.circuit_breaker.db_save_state")
def test_snapshot(mock_save, mock_load):
    cb = CircuitBreaker(max_consec_losses=4)
    cb.record_loss()
    snap = cb.snapshot()
    assert snap == {
        "consecutive_losses": 1,
        "loss_breaker_active": False,
        "max_consec_losses": 4,
    }


@patch("safety.circuit_breaker.db_load_state", return_value=None)
@patch("safety.circuit_breaker.db_save_state")
def test_second_trip_returns_false(mock_save, mock_load):
    cb = CircuitBreaker(max_consec_losses=2)
    cb.record_loss()
    first = cb.record_loss()
    assert first is True
    second = cb.record_loss()
    assert second is False  # already tripped
    assert cb.is_tripped()
