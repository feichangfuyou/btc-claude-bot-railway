"""Unit tests for readiness dimension scoring."""

from core.readiness_scores import (
    adversary_vision_score,
    grade_from_score,
    learning_score,
    multi_model_fallback_score,
    reasoning_audit_score,
    slippage_protection_score,
)


def test_learning_score_empty():
    assert learning_score(0, 0) == 2


def test_learning_score_with_trades_and_rules():
    # 29 trades + 22 rules (typical dev bot)
    assert learning_score(29, 22) == 10


def test_learning_score_caps_at_10():
    assert learning_score(500, 100) == 10


def test_reasoning_audit_with_did():
    assert reasoning_audit_score(True) == 10


def test_multi_model_fallback_normal():
    assert multi_model_fallback_score(False) == 10


def test_multi_model_fallback_defensive():
    assert multi_model_fallback_score(True) == 10


def test_slippage_auto_default():
    assert slippage_protection_score("", 0) == 10
    assert slippage_protection_score("auto", 0) == 10


def test_adversary_always_10():
    assert adversary_vision_score() == 10


def test_grade_a_plus():
    assert grade_from_score(100) == "A+"
    assert grade_from_score(95) == "A+"
