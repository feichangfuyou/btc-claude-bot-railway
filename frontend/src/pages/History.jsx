import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext.jsx";
import { supabase } from "../supabaseClient.js";

const GOLD = "#D4AF37";
const DARK = "#0A0A0A";
const CARD = "#111111";
const BORDER = "#1A1A1A";
const MUTED = "#5C5C5C";
const GREEN = "#27AE60";
const RED = "#C0392B";

export default function History() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [trades, setTrades] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState({ symbol: "", side: "", win: "" });
  const [stats, setStats] = useState({ total: 0, wins: 0, totalPnl: 0 });

  useEffect(() => {
    if (!user) return;
    loadTrades();
  }, [user, filter]);

  async function loadTrades() {
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
  }

  return (
    <div style={styles.container}>
      <div style={styles.page}>
        <div style={styles.header}>
          <button style={styles.backBtn} onClick={() => navigate("/dashboard")}>&larr; Dashboard</button>
          <h1 style={styles.title}>TRADE HISTORY</h1>
        </div>

        {/* Stats Summary */}
        <div style={styles.statsRow}>
          <div style={styles.statCard}>
            <div style={styles.statLabel}>Total Trades</div>
            <div style={styles.statValue}>{stats.total}</div>
          </div>
          <div style={styles.statCard}>
            <div style={styles.statLabel}>Win Rate</div>
            <div style={{ ...styles.statValue, color: stats.wins / Math.max(stats.total, 1) >= 0.5 ? GREEN : RED }}>
              {stats.total > 0 ? ((stats.wins / stats.total) * 100).toFixed(1) : 0}%
            </div>
          </div>
          <div style={styles.statCard}>
            <div style={styles.statLabel}>Total P&L</div>
            <div style={{ ...styles.statValue, color: stats.totalPnl >= 0 ? GREEN : RED }}>
              {stats.totalPnl >= 0 ? "+" : ""}${stats.totalPnl.toFixed(2)}
            </div>
          </div>
        </div>

        {/* Filters */}
        <div style={styles.filterRow}>
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
        <div style={styles.tableContainer}>
          {loading ? (
            <div style={{ textAlign: "center", padding: 40, color: MUTED, fontSize: 12 }}>Loading trades...</div>
          ) : trades.length === 0 ? (
            <div style={{ textAlign: "center", padding: 40, color: MUTED, fontSize: 12 }}>No trades yet. Start the bot to begin trading.</div>
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
                    <td style={{ ...styles.td, color: t.side === "buy" ? GREEN : RED }}>{t.side?.toUpperCase()}</td>
                    <td style={styles.td}>${Number(t.entry).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</td>
                    <td style={styles.td}>${Number(t.exit_price || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</td>
                    <td style={styles.td}>${Number(t.usd_size).toFixed(2)}</td>
                    <td style={{ ...styles.td, color: (t.pnl || 0) >= 0 ? GREEN : RED, fontWeight: 600 }}>
                      {(t.pnl || 0) >= 0 ? "+" : ""}${Number(t.pnl || 0).toFixed(2)}
                    </td>
                    <td style={styles.td}>
                      <span style={{ color: t.win ? GREEN : RED, fontWeight: 600 }}>
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
    </div>
  );
}

const styles = {
  container: {
    fontFamily: "'Space Mono', monospace",
    background: DARK,
    color: "#D4D4D4",
    minHeight: "100vh",
    padding: 20,
  },
  page: { maxWidth: 900, margin: "0 auto" },
  header: { display: "flex", alignItems: "center", gap: 16, marginBottom: 24 },
  title: {
    fontFamily: "'Bebas Neue', sans-serif",
    fontSize: 28,
    fontWeight: 400,
    letterSpacing: 4,
    color: GOLD,
    margin: 0,
  },
  backBtn: {
    fontFamily: "'Space Mono', monospace",
    fontSize: 12,
    padding: "6px 12px",
    background: "transparent",
    border: `1px solid ${BORDER}`,
    borderRadius: 4,
    color: MUTED,
    cursor: "pointer",
  },
  statsRow: { display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 12, marginBottom: 16 },
  statCard: {
    background: CARD,
    border: `1px solid ${BORDER}`,
    borderRadius: 6,
    padding: "14px 16px",
    textAlign: "center",
  },
  statLabel: { fontSize: 10, color: MUTED, letterSpacing: 1, marginBottom: 4 },
  statValue: { fontFamily: "'Bebas Neue', sans-serif", fontSize: 24, letterSpacing: 2 },
  filterRow: { display: "flex", gap: 8, marginBottom: 16 },
  filterSelect: {
    fontFamily: "'Space Mono', monospace",
    fontSize: 11,
    padding: "6px 10px",
    background: CARD,
    border: `1px solid ${BORDER}`,
    borderRadius: 4,
    color: "#D4D4D4",
  },
  tableContainer: {
    background: CARD,
    border: `1px solid ${BORDER}`,
    borderRadius: 8,
    overflow: "auto",
  },
  table: { width: "100%", borderCollapse: "collapse", fontSize: 11 },
  th: {
    textAlign: "left",
    padding: "10px 12px",
    color: MUTED,
    fontSize: 10,
    letterSpacing: 1,
    borderBottom: `1px solid ${BORDER}`,
    fontWeight: 400,
  },
  tr: { borderBottom: `1px solid ${BORDER}` },
  td: { padding: "8px 12px", whiteSpace: "nowrap" },
};
