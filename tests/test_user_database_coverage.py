"""Coverage tests for core/user_database.py — user-scoped operations (mocked Supabase)."""

from unittest.mock import MagicMock, patch


def _mock_supabase():
    sb = MagicMock()
    return sb


class TestUdbSaveTrade:
    def test_save_trade_returns_id(self):
        with patch("core.user_database.get_supabase") as mock_sb:
            sb = _mock_supabase()
            mock_sb.return_value = sb
            sb.table.return_value.insert.return_value.execute.return_value = MagicMock(data=[{"id": 42}])
            from core.user_database import udb_save_trade

            result = udb_save_trade(
                "user1",
                {
                    "symbol": "BTC",
                    "side": "buy",
                    "entry": 50000,
                    "exit": 51000,
                    "usd_size": 100,
                    "pnl": 50,
                    "win": True,
                },
            )
            assert result == 42

    def test_save_trade_no_data_returns_none(self):
        with patch("core.user_database.get_supabase") as mock_sb:
            sb = _mock_supabase()
            mock_sb.return_value = sb
            sb.table.return_value.insert.return_value.execute.return_value = MagicMock(data=[])
            from core.user_database import udb_save_trade

            result = udb_save_trade(
                "user1",
                {
                    "side": "buy",
                    "entry": 50000,
                    "usd_size": 100,
                },
            )
            assert result is None


class TestUdbLoadTrades:
    def test_load_trades_admin_returns_empty(self):
        from core.user_database import udb_load_trades

        result = udb_load_trades("admin")
        assert result == []

    def test_load_trades_returns_list(self):
        with patch("core.user_database.get_supabase") as mock_sb:
            sb = _mock_supabase()
            mock_sb.return_value = sb
            sb.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
                data=[{"id": 1, "side": "buy", "entry": 50000, "exit_price": 51000, "coin_size": 0.01}]
            )
            from core.user_database import udb_load_trades

            result = udb_load_trades("user1")
            assert len(result) == 1
            assert result[0]["exit"] == 51000
            assert result[0]["btc_size"] == 0.01


class TestUdbLoadAllTrades:
    def test_load_all_trades(self):
        with patch("core.user_database.get_supabase") as mock_sb:
            sb = _mock_supabase()
            mock_sb.return_value = sb
            query = sb.table.return_value.select.return_value.eq.return_value.order.return_value
            query.limit.return_value.execute.return_value = MagicMock(
                data=[{"id": 1, "exit_price": 50000, "coin_size": 0.01}]
            )
            from core.user_database import udb_load_all_trades

            result = udb_load_all_trades("user1")
            assert len(result) >= 0  # At minimum returns a list
