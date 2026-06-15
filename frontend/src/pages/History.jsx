import { useState, useEffect, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext.jsx";
import { supabase } from "../supabaseClient.js";
import { colors } from "../theme.js";
import { PageShell } from "../components/PageShell.jsx";

export default function History() {
  const { user, signOut } = useAuth();
  const navigate = useNavigate();
  const [trades, setTrades] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState({ symbol: "", side: "", win: "" });
  const [stats, setStats] = useState({ total: 0, wins: 0, totalPnl: 0 });

  const loadTrades = useCallback(async () => {
    if (!user) return;
    setLoading(true);
    let query = supabase
      .from("user_trades")
      .select("*", { count: "exact" })
      .eq("user_id", user.id)
      .order("created_at", { ascending: false })
      .limit(100);

    if (filter.symbol) query = query.eq("symbol", filter.symbol);
    if (filter.side) query = query.eq("side", filter.side);
    if (filter.win === "true") query = query.eq("win", true);
    if (filter.win === "false") query = query.eq("win", false);

    const { data, count } = await query;
    setTrades(data || []);

    const wins = (data || []).filter(t => t.win).length;
    const totalPnl = (data || []).reduce((sum, t) => sum + (t.pnl || 0), 0);
    setStats({ total: count || 0, wins, totalPnl });
    setLoading(false);
  }, [user, filter]);

  useEffect(() => {
    let ignore = false;
    async function start() {
      if (!ignore) await loadTrades();
    }
    start();
    return () => { ignore = true; };
  }, [loadTrades]);

  return (
    <>
    <style>{responsiveCss}</style>
    <PageShell
      title="TRADE HISTORY"
      onBack={() => navigate("/dashboard")}
      maxWidth={900}
      headerRight={user && (
        <button type="button" className="page-shell__sign-out" onClick={signOut}>SIGN OUT</button>
      )}
    >
      <div className="history-page">

        {/* Stats Summary */}
        <div style={styles.statsRow} className="stats-row">
          <div style={styles.statCard}>
            <div style={styles.statLabel}>Total Trades</div>
            <div style={styles.statValue}>{stats.total}</div>
          </div>
          <div style={styles.statCard}>
            <div style={styles.statLabel}>Win Rate</div>
            <div style={{ ...styles.statValue, color: stats.wins / Math.max(stats.total, 1) >= 0.5 ? colors.success : colors.error }}>
              {stats.total > 0 ? ((stats.wins / stats.total) * 100).toFixed(1) : 0}%
            </div>
          </div>
          <div style={styles.statCard}>
            <div style={styles.statLabel}>Total P&L</div>
            <div style={{ ...styles.statValue, color: stats.totalPnl >= 0 ? colors.success : colors.error }}>
              {stats.totalPnl >= 0 ? "+" : ""}${stats.totalPnl.toFixed(2)}
            </div>
          </div>
        </div>

        {/* Filters */}
        <div style={styles.filterRow} className="filter-row">
          <select value={filter.symbol} onChange={e => setFilter(f => ({ ...f, symbol: e.target.value }))} style={styles.filterSelect}>
            <option value="">All Coins</option>
            {["BTC", "ETH", "SOL", "LINK", "DOGE", "AVAX"].map(s => <option key={s} value={s}>{s}</option>)}
          </select>
          <select value={filter.side} onChange={e => setFilter(f => ({ ...f, side: e.target.value }))} style={styles.filterSelect}>
            <option value="">All Sides</option>
            <option value="buy">Buy</option>
            <option value="sell">Sell</option>
          </select>
          <select value={filter.win} onChange={e => setFilter(f => ({ ...f, win: e.target.value }))} style={styles.filterSelect}>
            <option value="">All Results</option>
            <option value="true">Wins</option>
            <option value="false">Losses</option>
          </select>
        </div>

        {/* Trade Table */}
        <div style={styles.tableContainer} className="table-wrap">
          {loading ? (
            <div style={{ textAlign: "center", padding: 40, color: colors.muted, fontSize: 12 }}>Loading trades...</div>
          ) : trades.length === 0 ? (
            <div style={{ textAlign: "center", padding: 40, color: colors.muted, fontSize: 12 }}>No trades yet. Start the bot to begin trading.</div>
          ) : (
            <table style={styles.table}>
              <thead>
                <tr>
                  <th style={styles.th}>Time</th>
                  <th style={styles.th}>Coin</th>
                  <th style={styles.th}>Side</th>
                  <th style={styles.th}>Entry</th>
                  <th style={styles.th}>Exit</th>
                  <th style={styles.th}>Size</th>
                  <th style={styles.th}>P&L</th>
                  <th style={styles.th}>Result</th>
                </tr>
              </thead>
              <tbody>
                {trades.map(t => (
                  <tr key={t.id} style={styles.tr}>
                    <td style={styles.td}>{new Date(t.created_at).toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })}</td>
                    <td style={{ ...styles.td, fontWeight: 600 }}>{t.symbol}</td>
                    <td style={{ ...styles.td, color: t.side === "buy" ? colors.success : colors.error }}>{t.side?.toUpperCase()}</td>
                    <td style={styles.td}>${Number(t.entry).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</td>
                    <td style={styles.td}>${Number(t.exit_price || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</td>
                    <td style={styles.td}>${Number(t.usd_size).toFixed(2)}</td>
                    <td style={{ ...styles.td, color: (t.pnl || 0) >= 0 ? colors.success : colors.error, fontWeight: 600 }}>
                      {(t.pnl || 0) >= 0 ? "+" : ""}${Number(t.pnl || 0).toFixed(2)}
                    </td>
                    <td style={styles.td}>
                      <span style={{ color: t.win ? colors.success : colors.error, fontWeight: 600 }}>
                        {t.win ? "WIN" : "LOSS"}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </PageShell>
    </>
  );
}

const styles = {
  statsRow: { display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 12, marginBottom: 16 },
  statCard: {
    background: "rgba(14, 14, 14, 0.62)",
    backdropFilter: "blur(24px) saturate(1.5)",
    WebkitBackdropFilter: "blur(24px) saturate(1.5)",
    border: "1px solid rgba(212,175,55,0.1)",
    borderRadius: 14,
    padding: "14px 16px",
    textAlign: "center",
    boxShadow: "0 14px 44px rgba(0,0,0,0.50), 0 2px 6px rgba(0,0,0,0.35), inset 0 1px 0 rgba(255,255,255,0.11), inset 1px 0 0 rgba(255,255,255,0.05), inset 0 -1px 0 rgba(0,0,0,0.18), inset -1px 0 0 rgba(0,0,0,0.08)",
    transition: "border-color 0.3s ease, box-shadow 0.3s ease",
  },
  statLabel: { fontSize: 10, color: colors.muted, letterSpacing: 1, marginBottom: 4 },
  statValue: { fontFamily: "'Montserrat', sans-serif", fontSize: 24, letterSpacing: 2 },
  filterRow: { display: "flex", gap: 8, marginBottom: 16 },
  filterSelect: {
    fontFamily: "'Space Mono', monospace",
    fontSize: 11,
    padding: "6px 10px",
    background: "rgba(14, 14, 14, 0.62)",
    backdropFilter: "blur(24px) saturate(1.5)",
    WebkitBackdropFilter: "blur(24px) saturate(1.5)",
    border: "1px solid rgba(255,255,255,0.06)",
    borderRadius: 8,
    color: "#D4D4D4",
    transition: "border-color 0.2s ease",
  },
  tableContainer: {
    background: "rgba(14, 14, 14, 0.62)",
    backdropFilter: "blur(24px) saturate(1.5)",
    WebkitBackdropFilter: "blur(24px) saturate(1.5)",
    border: "1px solid rgba(255,255,255,0.04)",
    borderRadius: 18,
    overflow: "auto",
    boxShadow: "0 14px 44px rgba(0,0,0,0.50), 0 2px 6px rgba(0,0,0,0.35), inset 0 1px 0 rgba(255,255,255,0.11), inset 1px 0 0 rgba(255,255,255,0.05), inset 0 -1px 0 rgba(0,0,0,0.18), inset -1px 0 0 rgba(0,0,0,0.08)",
  },
  table: { width: "100%", borderCollapse: "collapse", fontSize: 11 },
  th: {
    textAlign: "left",
    padding: "10px 12px",
    color: colors.muted,
    fontSize: 10,
    letterSpacing: 1,
    borderBottom: "1px solid rgba(255,255,255,0.04)",
    fontWeight: 400,
  },
  tr: { borderBottom: "1px solid rgba(255,255,255,0.04)" },
  td: { padding: "8px 12px", whiteSpace: "nowrap" },
};

const responsiveCss = `
@media (max-width: 768px) {
  .history-page {
    max-width: 100% !important;
  }
  .history-page .stats-row {
    grid-template-columns: 1fr 1fr 1fr !important;
    gap: 8px !important;
  }
  .history-page .filter-row {
    flex-wrap: wrap !important;
  }
  .history-page .filter-row select {
    flex: 1 1 auto !important;
    min-width: 0 !important;
  }
}
@media (max-width: 600px) {
  .history-page {
    padding: 0 !important;
  }
  .history-page .stats-row {
    grid-template-columns: 1fr 1fr 1fr !important;
    gap: 6px !important;
  }
}
@media (max-width: 375px) {
  .history-page {
    padding: 0 !important;
  }
  .history-page .stats-row {
    gap: 4px !important;
  }
}
@media (max-width: 320px) {
  .history-page .filter-row select {
    font-size: 10px !important;
    padding: 5px 6px !important;
  }
}
@media (max-width: 280px) {
  .history-page {
    max-width: 100% !important;
  }
  .history-page .stats-row {
    grid-template-columns: 1fr 1fr !important;
    gap: 4px !important;
  }
  .history-page .stat-card {
    padding: 10px 8px !important;
  }
  .history-page .stat-value {
    font-size: 18px !important;
  }
  .history-page .filter-row {
    flex-wrap: wrap !important;
    gap: 6px !important;
  }
  .history-page .filter-row select {
    font-size: 9px !important;
    padding: 4px 4px !important;
    min-width: 0 !important;
  }
  .history-page .table-wrap {
    overflow-x: auto !important;
    -webkit-overflow-scrolling: touch;
    margin: 0 -4px;
  }
  .history-page table {
    min-width: 480px;
  }
  .history-page td,
  .history-page th {
    padding: 5px 6px !important;
    font-size: 8px !important;
  }
}
`;
