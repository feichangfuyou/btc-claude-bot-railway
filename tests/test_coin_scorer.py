"""Tests for dynamic coin scoring."""

from unittest.mock import patch

from learning.coin_scorer import get_effective_blocklist, sort_coins_for_scan


@patch(
    "learning.coin_scorer.get_coin_scores",
    return_value={
        "ETH": {"n": 5, "win_rate": 60.0, "total_pnl": 6.0, "tier": "priority"},
        "SOL": {"n": 7, "win_rate": 20.0, "total_pnl": -9.0, "tier": "block"},
        "BTC": {"n": 3, "win_rate": 33.0, "total_pnl": 1.0, "tier": "neutral"},
    },
)
def test_sort_coins_eth_first_excludes_block(mock_scores):
    order = sort_coins_for_scan(["SOL", "BTC", "ETH", "BNB"])
    assert order[0] == "ETH"
    assert "SOL" not in order


@patch(
    "learning.coin_scorer.get_dynamic_blocklist",
    return_value={"SOL"},
)
def test_effective_blocklist_merges_static(mock_dyn):
    blocked = get_effective_blocklist(["LINK"])
    assert blocked == {"LINK", "SOL"}
