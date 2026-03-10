import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext.jsx";
import { useAuthHeaders } from "../hooks/useAuthHeaders.js";
import { colors, typography } from "../theme.js";
import { ArrowLeft, Check, X, ExternalLink, RefreshCw, ShieldAlert } from "lucide-react";

const BACKEND_BASE = (import.meta.env.VITE_BACKEND_URL || "").replace(/\/$/, "") || (import.meta.env.DEV ? "http://localhost:8000" : "");

export default function AdminManualPayments() {
  const { profile } = useAuth();
  const navigate = useNavigate();
  const getAuthHeaders = useAuthHeaders();
  const [payments, setPayments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [filter, setFilter] = useState("pending");

  const isAdmin = profile?.role === "admin";

  useEffect(() => {
    if (profile && !isAdmin) {
      navigate("/dashboard");
    }
  }, [profile, isAdmin, navigate]);

  useEffect(() => {
    if (isAdmin) {
      fetchPayments();
    }
  }, [isAdmin, filter]);

  async function fetchPayments() {
    setLoading(true);
    try {
      const base = BACKEND_BASE || "";
      const res = await fetch(`${base}/billing/admin/manual-payments?status=${filter}`, {
        headers: getAuthHeaders()
      });
      const data = await res.json();
      if (Array.isArray(data)) {
        setPayments(data);
      } else {
        setError("Failed to load payments.");
      }
    } catch (e) {
      setError("Network error.");
    } finally {
      setLoading(false);
    }
  }

  async function handleVerify(txid, status) {
    if (!window.confirm(`Are you sure you want to ${status === "verified" ? "APPROVE" : "REJECT"} this payment?`)) return;
    
    try {
      const base = BACKEND_BASE || "";
      const res = await fetch(`${base}/billing/admin/verify-payment`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...getAuthHeaders() },
        body: JSON.stringify({ txid, status }),
      });
      const data = await res.json();
      if (data.success) {
        alert(data.message);
        fetchPayments();
      } else {
        alert(data.error || "Action failed.");
      }
    } catch (e) {
      alert("Network error.");
    }
  }

  const getExplorerLink = (txid, crypto) => {
    if (crypto === "BTC") return `https://blockchair.com/bitcoin/transaction/${txid}`;
    if (crypto === "ETH" || crypto === "USDT") return `https://etherscan.io/tx/${txid}`;
    if (crypto === "SOL") return `https://solscan.io/tx/${txid}`;
    return "#";
  };

  if (!isAdmin) return null;

  return (
    <div style={styles.container}>
      <div style={styles.header}>
        <button style={styles.backBtn} onClick={() => navigate("/dashboard")}><ArrowLeft size={14} /> Back</button>
        <h1 style={styles.title}>ADMIN: MANUAL PAYMENTS</h1>
      </div>

      <div style={styles.controls}>
        <div style={styles.filters}>
          {["pending", "verified", "rejected"].map(s => (
            <button
              key={s}
              style={{
                ...styles.filterBtn,
                background: filter === s ? colors.gold : "rgba(255,255,255,0.05)",
                color: filter === s ? colors.dark : colors.muted,
              }}
              onClick={() => setFilter(s)}
            >
              {s.toUpperCase()}
            </button>
          ))}
        </div>
        <button style={styles.refreshBtn} onClick={fetchPayments}><RefreshCw size={14} /></button>
      </div>

      {loading ? (
        <div style={styles.loader}>Scanning ledger...</div>
      ) : error ? (
        <div style={styles.error}><ShieldAlert size={20} /> {error}</div>
      ) : payments.length === 0 ? (
        <div style={styles.empty}>No {filter} payments found.</div>
      ) : (
        <div style={styles.grid}>
          {payments.map(p => (
            <div key={p.id} style={styles.card}>
              <div style={styles.cardHeader}>
                <span style={styles.tierBadge}>{p.tier.toUpperCase()}</span>
                <span style={styles.date}>{new Date(p.created_at).toLocaleString()}</span>
              </div>
              
              <div style={styles.userSection}>
                <div style={styles.infoLabel}>User ID / Email</div>
                <div style={styles.infoValue}>{p.email || p.user_id}</div>
              </div>

              <div style={styles.paySection}>
                <div style={styles.amountBox}>
                  <div style={styles.infoLabel}>Amount</div>
                  <div style={{...styles.infoValue, color: colors.gold, fontSize: 18}}>{p.amount} {p.crypto_type}</div>
                </div>
              </div>

              <div style={styles.txSection}>
                <div style={styles.infoLabel}>Transaction ID</div>
                <div style={styles.txBox}>
                  <code style={styles.txText}>{p.txid}</code>
                  <a 
                    href={getExplorerLink(p.txid, p.crypto_type)} 
                    target="_blank" 
                    rel="noopener noreferrer"
                    style={styles.explorerLink}
                  >
                    <ExternalLink size={12} />
                  </a>
                </div>
              </div>

              {p.status === "pending" && (
                <div style={styles.actions}>
                  <button style={styles.rejectBtn} onClick={() => handleVerify(p.txid, "rejected")}>
                    <X size={14} /> REJECT
                  </button>
                  <button style={styles.approveBtn} onClick={() => handleVerify(p.txid, "verified")}>
                    <Check size={14} /> APPROVE
                  </button>
                </div>
              )}

              {p.status !== "pending" && (
                <div style={{
                  ...styles.statusBanner,
                  color: p.status === "verified" ? colors.success : colors.error,
                  borderColor: p.status === "verified" ? "rgba(39,174,96,0.3)" : "rgba(192,57,43,0.3)",
                }}>
                  {p.status.toUpperCase()}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

const styles = {
  container: {
    minHeight: "100vh",
    background: colors.dark,
    color: colors.text,
    padding: "24px",
    fontFamily: typography.fontMono,
  },
  header: { display: "flex", alignItems: "center", gap: 20, marginBottom: 32 },
  title: {
    fontFamily: typography.fontDisplay,
    fontSize: 24,
    color: colors.gold,
    letterSpacing: 2,
    margin: 0,
  },
  backBtn: {
    background: "rgba(255,255,255,0.05)",
    border: "1px solid rgba(255,255,255,0.1)",
    borderRadius: 8,
    color: colors.muted,
    padding: "8px 16px",
    display: "flex",
    alignItems: "center",
    gap: 8,
    cursor: "pointer",
  },
  controls: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: 24,
  },
  filters: { display: "flex", gap: 8 },
  filterBtn: {
    border: "none",
    borderRadius: 8,
    padding: "8px 16px",
    fontSize: 11,
    fontWeight: 700,
    cursor: "pointer",
    transition: "all 0.2s",
  },
  refreshBtn: {
    background: "rgba(255,255,255,0.05)",
    border: "1px solid rgba(255,255,255,0.1)",
    borderRadius: 8,
    color: colors.gold,
    padding: "8px",
    cursor: "pointer",
  },
  loader: { textAlign: "center", padding: "100px", color: colors.muted },
  error: { textAlign: "center", padding: "40px", color: colors.error, background: "rgba(192,57,43,0.1)", borderRadius: 12 },
  empty: { textAlign: "center", padding: "100px", color: colors.muted },
  grid: { 
    display: "grid", 
    gridTemplateColumns: "repeat(auto-fill, minmax(350px, 1fr))", 
    gap: 20 
  },
  card: {
    background: "rgba(17,17,17,0.8)",
    border: "1px solid rgba(255,255,255,0.05)",
    borderRadius: 16,
    padding: "20px",
    display: "flex",
    flexDirection: "column",
    gap: 16,
  },
  cardHeader: { display: "flex", justifyContent: "space-between", alignItems: "center" },
  tierBadge: {
    background: "rgba(212,175,55,0.1)",
    border: "1px solid rgba(212,175,55,0.3)",
    borderRadius: 4,
    padding: "2px 8px",
    fontSize: 10,
    color: colors.gold,
    fontWeight: 700,
  },
  date: { fontSize: 10, color: "#555" },
  userSection: {},
  infoLabel: { fontSize: 10, color: "#444", textTransform: "uppercase", marginBottom: 4 },
  infoValue: { fontSize: 13, color: colors.text, wordBreak: "break-all" },
  txSection: {},
  txBox: {
    background: "rgba(0,0,0,0.3)",
    border: "1px solid rgba(255,255,255,0.05)",
    borderRadius: 8,
    padding: "10px",
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 10,
  },
  txText: { fontSize: 11, color: colors.gold, wordBreak: "break-all", fontFamily: typography.fontMono },
  explorerLink: { color: colors.muted, display: "flex", alignItems: "center" },
  actions: { display: "flex", gap: 12, marginTop: 10 },
  rejectBtn: {
    flex: 1,
    background: "rgba(192,57,43,0.1)",
    border: "1px solid rgba(192,57,43,0.3)",
    borderRadius: 8,
    color: colors.error,
    padding: "10px",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    gap: 8,
    cursor: "pointer",
    fontSize: 11,
    fontWeight: 700,
  },
  approveBtn: {
    flex: 1,
    background: "rgba(39,174,96,0.1)",
    border: "1px solid rgba(39,174,96,0.3)",
    borderRadius: 8,
    color: colors.success,
    padding: "10px",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    gap: 8,
    cursor: "pointer",
    fontSize: 11,
    fontWeight: 700,
  },
  statusBanner: {
    textAlign: "center",
    padding: "8px",
    borderRadius: 8,
    border: "1px solid",
    fontSize: 12,
    fontWeight: 700,
    background: "rgba(255,255,255,0.03)",
  }
};
