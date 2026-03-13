import { useState, useEffect, useRef, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext.jsx";
import { useAuthHeaders } from "../hooks/useAuthHeaders.js";
import { colors, typography } from "../theme.js";
import {
  Shield, ShieldCheck, Lock, AlertTriangle, RefreshCw, QrCode,
  Copy, Check, Users, Zap, Activity, Radio, BarChart2,
  DollarSign, Terminal, ClipboardList, ChevronDown, X, Play, Square, ExternalLink
} from "lucide-react";

const BASE = (import.meta.env.VITE_BACKEND_URL || "").replace(/\/$/, "");

// ─── Helpers ──────────────────────────────────────────────────────────────────
const pnlColor = (v) => (v >= 0 ? colors.success : colors.error);
const fmt2 = (v) => `${v >= 0 ? "+" : ""}$${Math.abs(v).toFixed(2)}`;
const tierBadge = { elite: "#D4AF37", pro: "#60a5fa", starter: "#34d399", none: "#555" };
const tierLabel = { elite: "ELITE", pro: "PRO", starter: "STARTER", none: "FREE" };
function ago(iso) {
  if (!iso) return "—";
  const diff = Date.now() - new Date(iso).getTime();
  const m = Math.floor(diff / 60000);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

// ─── 2FA Gate ─────────────────────────────────────────────────────────────────
function TwoFactorGate({ onVerified }) {
  const getAuthHeaders = useAuthHeaders();
  const [code, setCode] = useState(["", "", "", "", "", ""]);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);
  const [shake, setShake] = useState(false);
  const [showSetup, setShowSetup] = useState(false);
  const [qrData, setQrData] = useState(null);
  const [copied, setCopied] = useState(false);
  const inputRefs = useRef([]);

  useEffect(() => { inputRefs.current[0]?.focus(); }, []);

  const triggerShake = () => { setShake(true); setTimeout(() => setShake(false), 600); };

  const handleDigitChange = (index, value) => {
    const digit = value.replace(/\D/g, "").slice(-1);
    const newCode = [...code];
    newCode[index] = digit;
    setCode(newCode);
    setError(null);
    if (digit && index < 5) inputRefs.current[index + 1]?.focus();
    if (digit && index === 5 && newCode.join("").length === 6) submitCode([...newCode]);
  };

  const handleKeyDown = (index, e) => {
    if (e.key === "Backspace") {
      if (code[index] === "" && index > 0) { inputRefs.current[index - 1]?.focus(); const nc = [...code]; nc[index - 1] = ""; setCode(nc); }
      else { const nc = [...code]; nc[index] = ""; setCode(nc); }
    } else if (e.key === "ArrowLeft" && index > 0) inputRefs.current[index - 1]?.focus();
    else if (e.key === "ArrowRight" && index < 5) inputRefs.current[index + 1]?.focus();
    else if (e.key === "Enter" && code.join("").length === 6) submitCode(code);
  };

  const handlePaste = (e) => {
    e.preventDefault();
    const p = e.clipboardData.getData("text").replace(/\D/g, "").slice(0, 6);
    if (!p.length) return;
    const nc = [...code];
    for (let i = 0; i < 6; i++) nc[i] = p[i] || "";
    setCode(nc);
    inputRefs.current[Math.min(p.length, 5)]?.focus();
    if (p.length === 6) submitCode(nc);
  };

  const submitCode = async (codeArr) => {
    const full = codeArr.join("");
    if (full.length !== 6) return;
    setLoading(true); setError(null);
    try {
      const res = await fetch(`${BASE}/api/admin/verify-2fa`, {
        method: "POST",
        headers: { ...getAuthHeaders(), "Content-Type": "application/json" },
        body: JSON.stringify({ code: full }),
      });
      if (res.ok) { onVerified(); }
      else {
        const d = await res.json().catch(() => ({}));
        setError(d.detail || "Invalid code. Try again.");
        triggerShake();
        setCode(["", "", "", "", "", ""]);
        setTimeout(() => inputRefs.current[0]?.focus(), 50);
      }
    } catch { setError("Network error."); triggerShake(); }
    finally { setLoading(false); }
  };

  const fetchQR = async () => {
    const res = await fetch(`${BASE}/api/admin/2fa-qr`, { headers: getAuthHeaders() }).catch(() => null);
    if (res?.ok) { const d = await res.json(); setQrData(d); setShowSetup(true); }
  };

  const qrUrl = qrData ? `https://api.qrserver.com/v1/create-qr-code/?size=200x200&data=${encodeURIComponent(qrData.uri)}&margin=8&bgcolor=0a0a0a&color=D4AF37` : null;

  return (
    <div style={gs.overlay}>
      <style>{gateCss}</style>
      <div style={gs.card} className={`tfa-card${shake ? " tfa-shake" : ""}`}>
        <div style={gs.iconRing}><Lock size={28} color={colors.gold} strokeWidth={1.5} /></div>
        <h1 style={gs.title}>ADMIN VERIFICATION</h1>
        <p style={gs.sub}>Enter your 6-digit authenticator code</p>

        {!showSetup ? (<>
          <div style={gs.row} onPaste={handlePaste}>
            {code.map((d, i) => (
              <input key={i} ref={el => inputRefs.current[i] = el} type="text" inputMode="numeric"
                maxLength={1} value={d}
                onChange={e => handleDigitChange(i, e.target.value)}
                onKeyDown={e => handleKeyDown(i, e)}
                className="tfa-digit" disabled={loading} autoComplete="off"
                style={{ ...gs.digit, border: error ? `1.5px solid ${colors.error}88` : d ? `1.5px solid ${colors.gold}88` : "1.5px solid rgba(255,255,255,0.08)", boxShadow: d ? `0 0 12px ${colors.gold}22` : "none" }}
              />
            ))}
          </div>
          {error && <div style={gs.err}><AlertTriangle size={12} style={{ marginRight: 6 }} />{error}</div>}
          <button style={{ ...gs.btn, opacity: code.join("").length === 6 && !loading ? 1 : 0.45 }}
            className="tfa-submit" onClick={() => submitCode(code)}
            disabled={code.join("").length !== 6 || loading}>
            {loading ? <RefreshCw size={16} style={{ animation: "tfa-spin 0.8s linear infinite" }} />
              : <><ShieldCheck size={16} style={{ marginRight: 8 }} />Verify &amp; Enter</>}
          </button>
          <button style={gs.link} onClick={fetchQR} className="tfa-link">
            <QrCode size={12} style={{ marginRight: 5 }} />First time? Set up Authenticator
          </button>
        </>) : (
          <div style={{ width: "100%", display: "flex", flexDirection: "column", alignItems: "center", gap: 14 }}>
            <p style={{ fontSize: 12, color: colors.muted, margin: 0 }}>Scan with <strong>Google Authenticator</strong> or <strong>Authy</strong></p>
            {qrUrl && <div style={{ padding: 12, background: "rgba(255,255,255,0.03)", border: `1px solid ${colors.gold}22`, borderRadius: 14 }}>
              <img src={qrUrl} alt="QR" style={{ display: "block", width: 160, height: 160, borderRadius: 8 }} />
            </div>}
            <div style={{ display: "flex", alignItems: "center", gap: 10, background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.06)", borderRadius: 10, padding: "10px 14px", width: "100%" }}>
            <code className="mono-text" style={{ fontSize: 11, color: colors.gold, flex: 1, wordBreak: "break-all", textAlign: "left" }}>{qrData?.secret}</code>
              <button style={{ background: "none", border: "none", color: colors.muted, cursor: "pointer", padding: 4 }}
                onClick={() => { navigator.clipboard.writeText(qrData?.secret || ""); setCopied(true); setTimeout(() => setCopied(false), 2000); }}>
                {copied ? <Check size={14} color="#22c55e" /> : <Copy size={14} />}
              </button>
            </div>
            <button style={gs.btn} className="tfa-submit" onClick={() => { setShowSetup(false); setCode(["", "", "", "", "", ""]); setTimeout(() => inputRefs.current[0]?.focus(), 50); }}>
              Done — Enter Code
            </button>
          </div>
        )}
        <div style={{ marginTop: 28, fontSize: 9, color: "#333", letterSpacing: 2 }}>
          <Shield size={10} style={{ marginRight: 4, opacity: 0.4 }} />DOYOU.TRADE • ADMIN 2FA
        </div>
      </div>
    </div>
  );
}

// ─── Stat Card ────────────────────────────────────────────────────────────────
function StatCard({ label, value, sub, color }) {
  return (
    <div style={s.statCard}>
      <div style={{ fontSize: 10, color: colors.muted, letterSpacing: 1, marginBottom: 6 }}>{label}</div>
      <div className="mono-text" style={{ fontSize: 22, fontWeight: 800, color: color || colors.gold }}>{value}</div>
      {sub && <div style={{ fontSize: 10, color: colors.muted, marginTop: 4 }}>{sub}</div>}
    </div>
  );
}

// ─── Section Wrapper ──────────────────────────────────────────────────────────
function Section({ title, icon: Icon, children, accent }) {
  return (
    <section className="section" style={{ ...s.section, borderColor: accent ? `${accent}44` : "rgba(255,255,255,0.05)" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 20 }}>
        {Icon && <Icon size={14} color={accent || colors.gold} />}
        <h2 style={s.sTitle}>{title}</h2>
      </div>
      {children}
    </section>
  );
}

const SESSION_TIMEOUT = 30 * 60; // 30min

// ─── Main Admin Component ─────────────────────────────────────────────────────
export default function Admin() {
  const { user } = useAuth();
  const getAuthHeaders = useAuthHeaders();
  const navigate = useNavigate();

  const [verified, setVerified] = useState(false);
  const verifiedAtRef = useRef(Date.now());
  const [sessionAge, setSessionAge] = useState(0);

  // Data state
  const [stats, setStats] = useState(null);
  const [users, setUsers] = useState([]);
  const [readiness, setReadiness] = useState(null);
  const [aiCosts, setAiCosts] = useState(null);
  const [breaker, setBreaker] = useState(null);
  const [auditLog, setAuditLog] = useState([]);
    const [liveLogs, setLiveLogs] = useState([]);
    const [manualPayments, setManualPayments] = useState([]);
    const [paymentsFilter, setPaymentsFilter] = useState("pending");
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(false);
  const [lastRefresh, setLastRefresh] = useState(null);
  const [activeTab, setActiveTab] = useState("overview");
  const [userSearch, setUserSearch] = useState("");

  // Broadcast signal form
  const [sigAction, setSigAction] = useState("buy");
  const [sigSymbol, setSigSymbol] = useState("BTC");
  const [sigConfidence, setSigConfidence] = useState(0.65);
  const [sigSize, setSigSize] = useState(0.05);
  const [sigTier, setSigTier] = useState("all");
  const [sigReason, setSigReason] = useState("");
  const [sigResult, setSigResult] = useState(null);

  // Tier modal
  const [tierModal, setTierModal] = useState(null); // { userId, email, currentTier }
  const [tierValue, setTierValue] = useState("none");
  const [brainTest, setBrainTest] = useState(null); // { ok, error?, model? }

  const logsEndRef = useRef(null);

  const api = useCallback(async (path, opts = {}) => {
    const { headers: extraHeaders, ...restOpts } = opts;
    const res = await fetch(`${BASE}${path}`, {
      headers: { ...getAuthHeaders(), ...extraHeaders },
      ...restOpts,
    });
    if (!res.ok) {
      const errBody = await res.json().catch(() => ({}));
      throw new Error(errBody.detail || `HTTP ${res.status}`);
    }
    return res.json();
  }, [getAuthHeaders]);

  const fetchAll = useCallback(async () => {
    try {
      const [st, us, rd, ac, br, al, ll] = await Promise.allSettled([
        api("/api/admin/stats"),
        api("/api/admin/users"),
        api("/api/admin/readiness"),
        api("/api/admin/ai-costs"),
        api("/api/admin/circuit-breaker"),
        api("/api/admin/audit-log"),
        api("/api/admin/logs?limit=80"),
      ]);
      if (st.status === "fulfilled") setStats(st.value);
      if (us.status === "fulfilled") setUsers(us.value.users || []);
      if (rd.status === "fulfilled") setReadiness(rd.value);
      if (ac.status === "fulfilled") setAiCosts(ac.value);
      if (br.status === "fulfilled") setBreaker(br.value);
      if (al.status === "fulfilled") setAuditLog(al.value.entries || []);
      if (ll.status === "fulfilled") setLiveLogs(ll.value.logs || []);
      
      // Fetch manual payments separately or here
      const payRes = await api(`/billing/admin/manual-payments?status=${paymentsFilter}`);
      setManualPayments(payRes || []);

      setLastRefresh(new Date());
    } catch { /* continue */ }
    finally { setLoading(false); }
  }, [api, paymentsFilter]);

  useEffect(() => {
    if (!verified) return;
    fetchAll();
    const iv = setInterval(fetchAll, 15000);
    return () => clearInterval(iv);
  }, [verified, fetchAll]);

  // Session timer — useRef keeps verifiedAt stable across renders
  useEffect(() => {
    if (!verified) return;
    verifiedAtRef.current = Date.now();
    const iv = setInterval(() => {
      const age = Math.floor((Date.now() - verifiedAtRef.current) / 1000);
      setSessionAge(age);
      if (age >= SESSION_TIMEOUT) setVerified(false);
    }, 1000);
    return () => clearInterval(iv);
  }, [verified]);

  useEffect(() => {
    if (logsEndRef.current) logsEndRef.current.scrollTop = logsEndRef.current.scrollHeight;
  }, [liveLogs]);

  // Actions
  const toggleBrain = async () => {
    if (!stats || actionLoading) return;
    const next = !stats.brain_enabled;
    if (!next && !window.confirm("Turn off the AI brain? No new signals will be generated (existing positions stay open).")) return;
    setActionLoading(true);
    try {
      const d = await api(`/api/admin/brain-toggle?enabled=${next}`, { method: "POST" });
      setStats(p => ({ ...p, brain_enabled: d.brain_enabled }));
    } catch (e) { alert(e.message); }
    finally { setActionLoading(false); }
  };

  const togglePause = async () => {
    if (!stats || actionLoading) return;
    setActionLoading(true);
    try {
      const d = await api(`/api/admin/global-pause?pause=${!stats.global_pause}`, { method: "POST" });
      setStats(p => ({ ...p, global_pause: d.global_pause }));
    } catch (e) { alert(e.message); }
    finally { setActionLoading(false); }
  };

  const emergencyStop = async () => {
    if (!window.confirm("CRITICAL: Close ALL positions and stop ALL bots?")) return;
    setActionLoading(true);
    try {
      await api("/emergency/stop", { method: "POST" });
      alert("EMERGENCY STOP EXECUTED");
      fetchAll();
    } catch (e) { alert(e.message); }
    finally { setActionLoading(false); }
  };

  const toggleRiskOff = async () => {
    if (!breaker || actionLoading) return;
    const nextState = !breaker.global_risk_off;
    if (!window.confirm(`Are you sure you want to ${nextState ? 'ENABLE' : 'DISABLE'} Capital Preservation (Risk-Off) mode globally?`)) return;
    setActionLoading(true);
    try {
      const d = await api(`/api/admin/risk-off?risk_off=${nextState}`, { method: "POST" });
      setBreaker(p => ({ ...p, global_risk_off: d.global_risk_off }));
      alert(`Capital Preservation mode ${nextState ? 'ENABLED (Bot sizing halved)' : 'DISABLED (Normal operations)'}`);
    } catch (e) { alert(e.message); }
    finally { setActionLoading(false); }
  };

  const setMaxLoss = async () => {
    if (!breaker || actionLoading) return;
    const input = window.prompt("Enter new Platform Global Max Loss Limit (USD):", breaker.global_max_loss_usd || 1000000);
    if (input === null || isNaN(input) || input <= 0) return;
    setActionLoading(true);
    try {
      const newLimit = parseFloat(input);
      const d = await api("/api/admin/set-max-loss", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ limit: newLimit }),
      });
      setBreaker(p => ({ ...p, global_max_loss_usd: d.global_max_loss_usd }));
      if (stats) setStats(p => ({ ...p, global_max_loss: d.global_max_loss_usd }));
    } catch (e) { alert(e.message); }
    finally { setActionLoading(false); }
  };

  const stopUserBot = async (uid) => {
    try { await api(`/api/admin/users/${uid}/stop`, { method: "POST" }); fetchAll(); } catch (e) { alert(e.message); }
  };

  const startUserBot = async (uid) => {
    try { await api(`/api/admin/users/${uid}/start`, { method: "POST" }); fetchAll(); } catch (e) { alert(e.message); }
  };

  const setTier = async () => {
    if (!tierModal) return;
    try {
      await api(`/api/admin/users/${tierModal.userId}/set-tier`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tier: tierValue }),
      });
      setTierModal(null);
      fetchAll();
    } catch (e) { alert(e.message); }
  };

  const broadcastSignal = async () => {
    setActionLoading(true); setSigResult(null);
    try {
      const d = await api("/api/admin/broadcast-signal", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: sigAction, symbol: sigSymbol, confidence: sigConfidence, size_pct: sigSize, tier: sigTier, reasoning: sigReason }),
      });
      setSigResult({ ok: true, msg: `✓ Signal sent to ${d.active_bots} active bots` });
    } catch (e) { setSigResult({ ok: false, msg: e.message }); }
    finally { setActionLoading(false); }
  };

  const verifyPayment = async (txid, status) => {
    if (!window.confirm(`Are you sure you want to ${status.toUpperCase()} this payment?`)) return;
    setActionLoading(true);
    try {
      const res = await api("/billing/admin/verify-payment", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ txid, status }),
      });
      if (res.success) {
        alert(res.message);
        fetchAll();
      } else {
        alert(res.error || "Action failed.");
      }
    } catch (e) { alert(e.message); }
    finally { setActionLoading(false); }
  };

  if (!verified) return <TwoFactorGate onVerified={() => setVerified(true)} />;

  const sessionLeft = Math.max(0, SESSION_TIMEOUT - sessionAge);
  const sessionPct = (sessionLeft / SESSION_TIMEOUT) * 100;
  const filteredUsers = users.filter(u =>
    !userSearch || u.email?.toLowerCase().includes(userSearch.toLowerCase()) || u.display_name?.toLowerCase().includes(userSearch.toLowerCase())
  );
  const tierCounts = users.reduce((acc, u) => { acc[u.tier] = (acc[u.tier] || 0) + 1; return acc; }, {});

  const TABS = [
    { id: "overview", label: "Overview", icon: BarChart2 },
    { id: "users", label: `Users (${users.length})`, icon: Users },
    { id: "signal", label: "Signal Hub", icon: Radio },
    { id: "readiness", label: "Readiness", icon: Zap },
    { id: "payments", label: "Payments", icon: DollarSign },
    { id: "costs", label: "AI Costs", icon: DollarSign },
    { id: "logs", label: "Live Logs", icon: Terminal },
    { id: "audit", label: "Audit Log", icon: ClipboardList },
  ];

  return (
    <div style={s.container}>
      <style>{adminCss}</style>

      {/* Tier Modal */}
      {tierModal && (
        <div className="glass-overlay fadein" style={{ position: "fixed", inset: 0, zIndex: 9999, display: "flex", alignItems: "center", justifyContent: "center" }} onClick={() => setTierModal(null)}>
          <div className="glass-heavy" style={{ maxWidth: "400px", width: "100%", padding: "28px", boxSizing: "border-box", animation: "fadein 0.35s ease", position: "relative" }} onClick={e => e.stopPropagation()}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
              <h3 style={{ color: colors.gold, margin: 0, fontSize: 14, letterSpacing: 2 }}>SET TIER</h3>
              <button style={{ background: "none", border: "none", color: colors.muted, cursor: "pointer" }} onClick={() => setTierModal(null)}><X size={16} /></button>
            </div>
            <p style={{ fontSize: 12, color: colors.muted, marginBottom: 16 }}>{tierModal.email}</p>
            <select value={tierValue} onChange={e => setTierValue(e.target.value)} style={s.select}>
              {["none", "starter", "pro", "elite"].map(t => <option key={t} value={t}>{t.toUpperCase()}</option>)}
            </select>
            <button style={{ ...s.goldBtn, marginTop: 16 }} onClick={setTier}>Apply</button>
          </div>
        </div>
      )}

      <div style={s.page} className="admin-page">
        {/* Header */}
        <div style={s.header}>
          <button style={s.backBtn} onClick={() => navigate("/dashboard")}>← Dashboard</button>
          <h1 style={s.title}>ADMIN CONSOLE</h1>
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <div style={{ fontSize: 10, color: sessionLeft < 300 ? colors.error : colors.muted }}>
              Session: {Math.floor(sessionLeft / 60)}:{String(sessionLeft % 60).padStart(2, "0")}
              <div style={{ height: 2, background: "rgba(255,255,255,0.05)", borderRadius: 2, marginTop: 4, width: 80, overflow: "hidden" }}>
                <div style={{ height: "100%", width: `${sessionPct}%`, background: sessionLeft < 300 ? colors.error : colors.gold, borderRadius: 2, transition: "width 1s linear" }} />
              </div>
            </div>
            <div style={s.badge}>GOD MODE</div>
          </div>
        </div>

        {lastRefresh && <div style={{ fontSize: 10, color: "#333", marginBottom: 16, textAlign: "right" }}>Last refresh: {lastRefresh.toLocaleTimeString()}</div>}

        {/* Tabs */}
        <div style={s.tabs}>
          {TABS.map(t => (
            <button key={t.id} style={{ ...s.tab, ...(activeTab === t.id ? s.tabActive : {}) }} onClick={() => setActiveTab(t.id)} className="admin-tab">
              <t.icon size={12} style={{ marginRight: 5 }} />{t.label}
            </button>
          ))}
        </div>

        {/* ── OVERVIEW ── */}
        {activeTab === "overview" && (<>
          {/* Emergency Controls */}
          <Section title="GLOBAL CONTROLS" icon={Shield} accent={stats?.global_pause ? colors.error : !stats?.brain_enabled ? colors.gold : null}>
            {/* Brain status banner */}
            {stats && !stats.brain_enabled && (
              <div style={{ marginBottom: 16, padding: "10px 16px", background: "rgba(212,175,55,0.12)", borderRadius: 10, border: "1px solid rgba(212,175,55,0.3)", display: "flex", alignItems: "center", gap: 10 }}>
                <span style={{ fontSize: 18 }}>🧠</span>
                <div>
                  <div style={{ fontSize: 13, fontWeight: 800, color: colors.gold }}>BRAIN IS OFFLINE</div>
                  <div style={{ fontSize: 11, color: colors.muted }}>AI hub scan cycles are paused. No API spend. Users who start bots are queued — they'll receive signals when you turn the brain back on.</div>
                </div>
              </div>
            )}
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 16 }}>
              <div>
                <div style={{ fontSize: 15, fontWeight: 800, color: stats?.global_pause ? colors.error : colors.success }}>
                  PLATFORM: {stats?.global_pause ? "⛔ HALTED" : "✅ OPERATIONAL"}
                </div>
                <div style={{ fontSize: 11, color: colors.muted, marginTop: 4 }}>
                  {stats?.active_users || 0} active bots / {stats?.total_users || 0} total users
                  {breaker?.global_risk_off && <span style={{ marginLeft: 8, color: colors.gold, fontWeight: 700 }}>⚠️ RISK-OFF MODE ACTIVE</span>}
                </div>
              </div>
              <div style={{ display: "flex", gap: 10 }}>
                <button style={{ padding: "14px 24px", borderRadius: 12, border: `1px solid ${stats?.brain_enabled ? "#00e676" : colors.gold}44`, background: stats?.brain_enabled ? "rgba(0,230,118,0.12)" : "rgba(212,175,55,0.15)", color: stats?.brain_enabled ? "#00e676" : colors.gold, fontSize: 12, fontWeight: 800, cursor: "pointer", transition: "all 0.3s ease" }}
                  onClick={toggleBrain} disabled={actionLoading} className="admin-action-btn">
                  🧠 {actionLoading ? "..." : stats?.brain_enabled ? "BRAIN ON" : "BRAIN OFF"}
                </button>
                <button style={{ padding: "14px 24px", borderRadius: 12, border:`1px solid ${breaker?.global_risk_off ? colors.gold : colors.muted}44`, background: breaker?.global_risk_off ? "rgba(212,175,55,0.15)" : "transparent", color: breaker?.global_risk_off ? colors.gold : colors.muted, fontSize: 12, fontWeight: 800, cursor: "pointer", transition: "all 0.3s ease" }}
                  onClick={toggleRiskOff} disabled={actionLoading} className="admin-action-btn">
                  🛡️ {breaker?.global_risk_off ? "DISABLE RISK-OFF" : "ENABLE RISK-OFF"}
                </button>
                <button style={{ ...s.pauseBtn, background: stats?.global_pause ? colors.success : colors.error, boxShadow: `0 0 20px ${stats?.global_pause ? colors.success : colors.error}44` }}
                  onClick={togglePause} disabled={actionLoading} className="admin-action-btn">
                  {actionLoading ? "..." : stats?.global_pause ? "▶ RESUME ALL" : "⏸ HALT ALL"}
                </button>
                <button style={s.stopBtn} onClick={emergencyStop} disabled={actionLoading} className="admin-stop-btn">
                  ☠ STOP &amp; CLOSE ALL
                </button>
              </div>
            </div>
          </Section>

          {/* Platform Metrics */}
          <Section title="PLATFORM METRICS" icon={Activity}>
            <div style={s.statsGrid} className="stats-grid">
              <StatCard label="AI BRAIN" value={stats?.brain_enabled ? "ONLINE" : "OFFLINE"} color={stats?.brain_enabled ? colors.success : colors.gold} />
              <StatCard label="ACTIVE BOTS" value={stats?.active_users ?? "—"} />
              <StatCard label="TOTAL USERS" value={stats?.total_users ?? "—"} />
              <StatCard label="DAILY P&L" value={stats?.global_daily_pnl != null ? fmt2(stats.global_daily_pnl) : "—"} color={pnlColor(stats?.global_daily_pnl || 0)} />
              <StatCard label="TOTAL P&L" value={stats?.global_total_pnl != null ? fmt2(stats.global_total_pnl) : "—"} color={pnlColor(stats?.global_total_pnl || 0)} />
              <StatCard label="MAX LOSS LIMIT" value={`$${(stats?.global_max_loss || 0).toLocaleString()}`} color={colors.error} />
            </div>
          </Section>

          {/* Circuit Breaker */}
          <Section title="CIRCUIT BREAKER" icon={Zap} accent={breaker?.triggered ? colors.error : null}>
            {breaker ? (
              <div style={{ display: "flex", gap: 24, flexWrap: "wrap", justifyContent: "space-between", alignItems: "center" }}>
                <div style={{ display: "flex", gap: 24, flexWrap: "wrap" }}>
                  <div>
                    <div style={{ fontSize: 13, fontWeight: 700, color: breaker.triggered ? colors.error : colors.success }}>
                      {breaker.triggered ? "🚨 TRIGGERED" : "✅ NOMINAL"}
                    </div>
                    <div style={{ fontSize: 11, color: colors.muted, marginTop: 4 }}>
                      Platform daily P&L: <span className="mono-text" style={{ color: pnlColor(breaker.total_daily_pnl) }}>{fmt2(breaker.total_daily_pnl)}</span>
                    </div>
                    <div style={{ fontSize: 11, color: colors.muted, marginTop: 2 }}>
                      Threshold: <span className="mono-text" style={{ color: colors.error }}>${breaker.threshold?.toLocaleString()}</span>
                    </div>
                  </div>
                  <div>
                    <div style={{ fontSize: 11, color: colors.muted }}>Limit: ${(breaker.global_max_loss_usd || 0).toLocaleString()}</div>
                    <div style={{ fontSize: 11, color: colors.muted }}>Global pause: <span style={{ color: breaker.global_pause ? colors.error : colors.success }}>{breaker.global_pause ? "YES" : "NO"}</span></div>
                  </div>
                </div>
                <button 
                  onClick={setMaxLoss}
                  style={{ padding: "8px 14px", borderRadius: 8, background: "rgba(255,255,255,0.05)", border: "1px solid rgba(255,255,255,0.1)", color: colors.muted, fontSize: 11, cursor: "pointer" }}
                  className="admin-action-btn">
                  ⚙️ Update Max Loss Limit
                </button>
              </div>
            ) : <div style={{ color: colors.muted, fontSize: 12 }}>Loading...</div>}
          </Section>

          {/* Tier Breakdown */}
          <Section title="TIER BREAKDOWN" icon={Users}>
            <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
              {Object.entries(tierBadge).map(([t, c]) => (
                <div key={t} style={{ padding: "10px 20px", borderRadius: 10, background: "rgba(255,255,255,0.02)", border: `1px solid ${c}33`, minWidth: 90, textAlign: "center" }}>
                  <div className="mono-text" style={{ fontSize: 20, fontWeight: 800, color: c }}>{tierCounts[t] || 0}</div>
                  <div style={{ fontSize: 10, color: c, marginTop: 4, letterSpacing: 1 }}>{tierLabel[t]}</div>
                </div>
              ))}
            </div>
          </Section>
        </>)}

        {/* ── USERS ── */}
        {activeTab === "users" && (
          <Section title="USER MANAGEMENT" icon={Users}>
            <input placeholder="Search by email or name…" value={userSearch} onChange={e => setUserSearch(e.target.value)}
              style={{ ...s.searchInput, marginBottom: 16 }} />
            <div style={s.tableWrap}>
              <table style={s.table}>
                <thead>
                  <tr>{["Email", "Name", "Tier", "Status", "Bot", "Daily P&L", "Total P&L", "Joined", "Actions"].map(h => (
                    <th key={h} style={s.th}>{h}</th>
                  ))}</tr>
                </thead>
                <tbody>
                  {filteredUsers.map(u => (
                    <tr key={u.id} style={s.tr} className="admin-row">
                      <td style={s.td}><span className="mono-text" style={{ fontSize: 11 }}>{u.email || "—"}</span></td>
                      <td style={s.td}>{u.display_name || "—"}</td>
                      <td style={s.td}>
                        <span style={{ padding: "2px 8px", borderRadius: 6, background: `${tierBadge[u.tier] || "#555"}22`, color: tierBadge[u.tier] || "#555", fontSize: 10, fontWeight: 800, letterSpacing: 1 }}>
                          {tierLabel[u.tier] || u.tier}
                        </span>
                      </td>
                      <td style={s.td}><span style={{ color: u.status === "active" ? colors.success : colors.muted, fontSize: 11 }}>{u.status}</span></td>
                      <td style={s.td}><span style={{ color: u.bot_running ? colors.success : "#444", fontSize: 11 }}>{u.bot_running ? "● RUN" : "○ OFF"}</span></td>
                      <td style={s.td}><span className="mono-text" style={{ color: pnlColor(u.daily_pnl), fontSize: 11 }}>{fmt2(u.daily_pnl)}</span></td>
                      <td style={s.td}><span className="mono-text" style={{ color: pnlColor(u.total_pnl), fontSize: 11 }}>{fmt2(u.total_pnl)}</span></td>
                      <td style={s.td}><span style={{ color: colors.muted, fontSize: 10 }}>{ago(u.created_at)}</span></td>
                      <td style={s.td}>
                        <div style={{ display: "flex", gap: 6 }}>
                          {u.bot_running
                            ? <button style={s.smBtn} onClick={() => stopUserBot(u.id)} title="Stop bot"><Square size={10} /></button>
                            : <button style={{ ...s.smBtn, color: colors.success }} onClick={() => startUserBot(u.id)} title="Start bot"><Play size={10} /></button>
                          }
                          <button style={s.smBtn} onClick={() => { setTierModal({ userId: u.id, email: u.email, currentTier: u.tier }); setTierValue(u.tier); }} title="Set tier">
                            <ChevronDown size={10} />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                  {!filteredUsers.length && <tr><td colSpan={9} style={{ ...s.td, textAlign: "center", color: colors.muted, padding: 24 }}>No users found</td></tr>}
                </tbody>
              </table>
            </div>
          </Section>
        )}

        {/* ── SIGNAL HUB ── */}
        {activeTab === "signal" && (
          <Section title="BROADCAST SIGNAL HUB" icon={Radio} accent={colors.gold}>
            <p style={{ fontSize: 12, color: colors.muted, marginBottom: 20 }}>
              Send a real-time trading signal to all eligible running bots. Each bot applies its own risk checks before executing.
            </p>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
              <div>
                <label style={s.label}>Action</label>
                <select value={sigAction} onChange={e => setSigAction(e.target.value)} style={s.select}>
                  <option value="buy">BUY (Long)</option>
                  <option value="sell">SELL (Short)</option>
                  <option value="take_profit">TAKE PROFIT (Winners Only)</option>
                  <option value="close">CLOSE All Position Types</option>
                </select>
              </div>
              <div>
                <label style={s.label}>Symbol</label>
                <select value={sigSymbol} onChange={e => setSigSymbol(e.target.value)} style={s.select}>
                  {["BTC", "ETH", "SOL", "LINK", "ARB"].map(sym => <option key={sym} value={sym}>{sym}</option>)}
                </select>
              </div>
              <div>
                <label style={s.label}>Confidence: {(sigConfidence * 100).toFixed(0)}%</label>
                <input type="range" min={0.1} max={1} step={0.05} value={sigConfidence} onChange={e => setSigConfidence(parseFloat(e.target.value))} style={{ width: "100%", accentColor: colors.gold }} />
              </div>
              <div>
                <label style={s.label}>Size %: {(sigSize * 100).toFixed(0)}%</label>
                <input type="range" min={0.01} max={0.2} step={0.01} value={sigSize} onChange={e => setSigSize(parseFloat(e.target.value))} style={{ width: "100%", accentColor: colors.gold }} />
              </div>
              <div>
                <label style={s.label}>Target Tier</label>
                <select value={sigTier} onChange={e => setSigTier(e.target.value)} style={s.select}>
                  <option value="all">All Tiers</option>
                  <option value="elite">Elite Only</option>
                  <option value="pro">Pro Only</option>
                  <option value="starter">Starter Only</option>
                </select>
              </div>
              <div>
                <label style={s.label}>Reasoning (optional)</label>
                <input value={sigReason} onChange={e => setSigReason(e.target.value)} placeholder="e.g. Breakout confirmed" style={s.input} />
              </div>
            </div>
            <div style={{ marginTop: 20, padding: 14, background: "rgba(212,175,55,0.05)", border: `1px solid ${colors.gold}22`, borderRadius: 12, fontSize: 12, color: colors.muted, marginBottom: 16 }}>
              📡 This will send <strong style={{ color: colors.gold }}>{sigAction.toUpperCase()} {sigSymbol}</strong> at <strong style={{ color: colors.gold }}>{(sigConfidence * 100).toFixed(0)}% confidence</strong> to <strong style={{ color: colors.gold }}>{sigTier === "all" ? "all" : sigTier}</strong> tier users ({stats?.active_users || 0} active bots).
            </div>
            {sigResult && <div style={{ padding: "10px 14px", borderRadius: 10, marginBottom: 14, background: sigResult.ok ? "rgba(34,197,94,0.08)" : "rgba(192,57,43,0.08)", border: `1px solid ${sigResult.ok ? colors.success : colors.error}33`, color: sigResult.ok ? colors.success : colors.error, fontSize: 12 }}>{sigResult.msg}</div>}
            <button style={{ ...s.goldBtn, width: "100%" }} onClick={broadcastSignal} disabled={actionLoading} className="admin-action-btn">
              <Radio size={14} style={{ marginRight: 8 }} />{actionLoading ? "Broadcasting…" : "BROADCAST SIGNAL"}
            </button>
          </Section>
        )}

        {/* ── READINESS ── */}
        {activeTab === "readiness" && (
          <Section title="PLATFORM READINESS SCORECARD" icon={Zap}>
            {readiness ? (<>
              <div style={{ display: "flex", alignItems: "center", gap: 20, marginBottom: 24 }}>
                <div className="mono-text" style={{ fontSize: 56, fontWeight: 900, color: readiness.score >= 90 ? colors.success : readiness.score >= 75 ? colors.gold : colors.error, lineHeight: 1 }}>{readiness.score}</div>
                <div>
                  <div style={{ fontSize: 28, fontWeight: 900, color: readiness.score >= 90 ? colors.success : colors.gold }}>{readiness.grade}</div>
                  <div style={{ fontSize: 11, color: colors.muted }}>out of {readiness.target}</div>
                </div>
              </div>
              {/* Progress bar */}
              <div style={{ height: 6, background: "rgba(255,255,255,0.05)", borderRadius: 3, marginBottom: 24, overflow: "hidden" }}>
                <div style={{ height: "100%", width: `${readiness.score}%`, background: `linear-gradient(90deg, ${colors.gold}, ${colors.success})`, borderRadius: 3, transition: "width 0.8s ease" }} />
              </div>
              {/* Dimensions */}
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginBottom: 20 }}>
                {Object.entries(readiness.dimensions || {}).map(([key, val]) => (
                  <div key={key} style={{ padding: "12px 14px", background: "rgba(255,255,255,0.02)", borderRadius: 10, border: "1px solid rgba(255,255,255,0.04)" }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                      <span style={{ fontSize: 11, color: colors.muted, textTransform: "capitalize" }}>{key.replace(/_/g, " ")}</span>
                      <span className="mono-text" style={{ fontSize: 13, fontWeight: 800, color: val >= 8 ? colors.success : val >= 5 ? colors.gold : colors.error }}>{val}/10</span>
                    </div>
                    <div style={{ height: 3, background: "rgba(255,255,255,0.05)", borderRadius: 2, marginTop: 6, overflow: "hidden" }}>
                      <div style={{ height: "100%", width: `${val * 10}%`, background: val >= 8 ? colors.success : val >= 5 ? colors.gold : colors.error, borderRadius: 2 }} />
                    </div>
                  </div>
                ))}
              </div>
              {/* Checks */}
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {Object.entries(readiness.checks || {}).slice(0, 12).map(([k, v]) => (
                  <div key={k} style={{ display: "flex", justifyContent: "space-between", padding: "8px 0", borderBottom: "1px solid rgba(255,255,255,0.03)" }}>
                    <span style={{ fontSize: 12, color: colors.muted, textTransform: "capitalize" }}>{k.replace(/_/g, " ")}</span>
                    <span className="mono-text" style={{ fontSize: 11, color: v === true ? colors.success : v === false ? colors.error : colors.gold }}>{typeof v === "boolean" ? (v ? "✓" : "✗") : String(v)}</span>
                  </div>
                ))}
              </div>
              {/* Alert when brain is paused */}
              {readiness.checks?.multi_model_fallback === false && (
                <div style={{ marginTop: 20, padding: 12, background: "rgba(255,23,68,0.12)", borderRadius: 10, border: "1px solid rgba(255,23,68,0.3)", color: colors.error, fontSize: 12 }}>
                  Brain is paused (credits exhausted or API failures). Add credits at{" "}
                  <a href="https://console.anthropic.com" target="_blank" rel="noopener noreferrer" style={{ color: colors.gold, textDecoration: "underline" }}>console.anthropic.com</a>
                  , then click Test Brain below.
                </div>
              )}
              {/* Brain test — verify Claude API & credits after top-up */}
              <div style={{ marginTop: 20, padding: 16, background: "rgba(255,255,255,0.02)", borderRadius: 10, border: "1px solid rgba(255,255,255,0.04)" }}>
                <div style={{ fontSize: 12, color: colors.muted, marginBottom: 6 }}>Verify brain (Claude API + credits)</div>
                <div style={{ fontSize: 11, color: colors.muted, opacity: 0.9, marginBottom: 10, lineHeight: 1.4 }}>
                  If the brain is paused (credits exhausted): add credits at{" "}
                  <a href="https://console.anthropic.com" target="_blank" rel="noopener noreferrer" style={{ color: colors.gold, textDecoration: "underline" }}>console.anthropic.com</a>
                  , then click Test Brain to un-pause and verify.
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                  <button
                    onClick={async () => {
                      setBrainTest(null);
                      try {
                        const r = await api("/api/admin/test-brain", { method: "POST" });
                        setBrainTest(r);
                        fetchAll();
                      } catch (e) {
                        setBrainTest({ ok: false, error: e.message });
                      }
                    }}
                    style={{
                      padding: "8px 16px",
                      borderRadius: 8,
                      fontSize: 12,
                      fontWeight: 700,
                      border: "none",
                      cursor: "pointer",
                      background: colors.gold,
                      color: colors.dark,
                    }}
                  >
                    Test Brain
                  </button>
                  {brainTest && (
                    <span style={{ fontSize: 12, color: brainTest.ok ? colors.success : colors.error }}>
                      {brainTest.ok ? `✓ OK (${brainTest.model || "Claude"})` : `✗ ${brainTest.error || "Failed"}`}
                    </span>
                  )}
                </div>
              </div>
            </>) : <div style={{ color: colors.muted, fontSize: 12 }}>Loading readiness data…</div>}
          </Section>
        )}

        {/* ── AI COSTS ── */}
        {activeTab === "costs" && (
          <Section title="AI COST TRACKER" icon={DollarSign}>
            {aiCosts ? (
              <div style={{ display: "flex", flexDirection: "column", gap: 0 }}>
                {[
                  ["Total Estimated Spend", `$${(aiCosts.total_cost || 0).toFixed(4)}`],
                  ["Scout Calls", aiCosts.scout_calls ?? 0],
                  ["Trade Calls", aiCosts.trade_calls ?? 0],
                  ["Adversary Calls", aiCosts.adversary_calls ?? 0],
                  ["Adversary Kills (vetoed)", aiCosts.adversary_kills ?? 0],
                  ["Adversary Reduces", aiCosts.adversary_reduces ?? 0],
                  ["Escalation Rate", aiCosts.escalation_rate != null ? `${(aiCosts.escalation_rate * 100).toFixed(1)}%` : "—"],
                  ["Model Fallback Active", aiCosts.model_fallback ? "YES" : "NO"],
                  ["Vision Feed", aiCosts.vision_enabled ? "ENABLED" : "DISABLED"],
                  ["Bot DID", aiCosts.bot_did ? `${String(aiCosts.bot_did).slice(0, 16)}…` : "Not set"],
                  ["Savings vs Always-Trade", `$${(aiCosts.savings_vs_always_trade || 0).toFixed(4)}`],
                ].map(([k, v]) => (
                  <div key={k} style={{ display: "flex", justifyContent: "space-between", padding: "12px 0", borderBottom: "1px solid rgba(255,255,255,0.04)" }}>
                    <span style={{ color: colors.muted, fontSize: 13 }}>{k}</span>
                    <span className="mono-text" style={{ color: colors.gold, fontSize: 13, fontWeight: 700 }}>{String(v)}</span>
                  </div>
                ))}
                {aiCosts.error && <div style={{ color: colors.error, fontSize: 12, marginTop: 12 }}>Error: {aiCosts.error}</div>}
              </div>
            ) : <div style={{ color: colors.muted, fontSize: 12 }}>Loading cost data…</div>}
          </Section>
        )}

        {/* ── PAYMENTS ── */}
        {activeTab === "payments" && (
          <Section title="MANUAL CRYPTO PAYMENTS" icon={DollarSign}>
            <div style={{ display: "flex", gap: 8, marginBottom: 20 }}>
              {["pending", "verified", "rejected"].map(s => (
                <button
                  key={s}
                  style={{
                    padding: "6px 14px",
                    borderRadius: 8,
                    fontSize: 10,
                    fontWeight: 800,
                    border: "none",
                    cursor: "pointer",
                    background: paymentsFilter === s ? colors.gold : "rgba(255,255,255,0.05)",
                    color: paymentsFilter === s ? colors.dark : colors.muted,
                  }}
                  onClick={() => setPaymentsFilter(s)}
                >
                  {s.toUpperCase()}
                </button>
              ))}
            </div>

            <div style={s.tableWrap}>
              <table style={s.table}>
                <thead>
                  <tr>{["Date", "User", "Plan", "Amount", "TXID", "Actions"].map(h => (
                    <th key={h} style={s.th}>{h}</th>
                  ))}</tr>
                </thead>
                <tbody>
                  {manualPayments.map(p => (
                    <tr key={p.id} style={s.tr} className="admin-row">
                      <td style={s.td}><span style={{ color: colors.muted, fontSize: 10 }}>{new Date(p.created_at).toLocaleString()}</span></td>
                      <td style={s.td}><div style={{ fontSize: 11 }}>{p.email}</div><div style={{ fontSize: 9, color: "#333" }}>{p.user_id}</div></td>
                      <td style={s.td}><span style={{ fontSize: 10, fontWeight: 800, color: colors.gold }}>{p.tier.toUpperCase()}</span></td>
                      <td style={s.td}><div style={{ fontSize: 12, fontWeight: 700 }}>{p.amount} {p.crypto_type}</div></td>
                      <td style={s.td}>
                        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                          <code style={{ fontSize: 10, color: colors.gold, background: "rgba(0,0,0,0.3)", padding: "2px 6px", borderRadius: 4 }}>{p.txid.slice(0, 16)}...</code>
                          <a 
                            href={
                              p.crypto_type === "BTC" ? `https://blockchair.com/bitcoin/transaction/${p.txid}` :
                              (p.crypto_type === "ETH" || p.crypto_type === "USDT") ? `https://etherscan.io/tx/${p.txid}` :
                              p.crypto_type === "SOL" ? `https://solscan.io/tx/${p.txid}` : "#"
                            }
                            target="_blank" rel="noopener noreferrer" style={{ color: colors.muted }}
                          ><ExternalLink size={12} /></a>
                        </div>
                      </td>
                      <td style={s.td}>
                        {p.status === "pending" ? (
                          <div style={{ display: "flex", gap: 8 }}>
                            <button style={{ ...s.smBtn, color: colors.error }} onClick={() => verifyPayment(p.txid, "rejected")}><X size={10} /> REJECT</button>
                            <button style={{ ...s.smBtn, color: colors.success }} onClick={() => verifyPayment(p.txid, "verified")}><Check size={10} /> APPROVE</button>
                          </div>
                        ) : (
                          <span style={{ fontSize: 10, fontWeight: 800, color: p.status === "verified" ? colors.success : colors.error }}>{p.status.toUpperCase()}</span>
                        )}
                      </td>
                    </tr>
                  ))}
                  {!manualPayments.length && <tr><td colSpan={6} style={{ ...s.td, textAlign: "center", color: colors.muted, padding: 24 }}>No {paymentsFilter} payments</td></tr>}
                </tbody>
              </table>
            </div>
          </Section>
        )}

        {/* ── LIVE LOGS ── */}
        {activeTab === "logs" && (
          <Section title="LIVE PLATFORM LOGS" icon={Terminal}>
            <div style={s.logBox}>
              {liveLogs.length === 0 && <div style={{ color: "#333", fontSize: 11 }}>No logs yet — start the bot to see activity.</div>}
              {liveLogs.map((log, i) => {
                // bot.add_log stores: { msg, type, ts, admin_only }
                const t = log.type || "info";
                const c = t === "error" ? colors.error : t === "warning" ? colors.gold : t === "success" ? colors.success : "#888";
                return (
                  <div key={i} style={{ display: "flex", gap: 10, padding: "4px 0", borderBottom: "1px solid rgba(255,255,255,0.02)", alignItems: "flex-start" }}>
                    <span className="mono-text" style={{ color: "#444", fontSize: 10, flexShrink: 0, paddingTop: 1 }}>{log.ts || ""}</span>
                    <span className="mono-text" style={{ color: c, fontSize: 11, flex: 1, wordBreak: "break-word" }}>
                      {log.admin_only && <span style={{ color: colors.gold, border: `1px solid ${colors.gold}44`, padding: "1px 4px", borderRadius: 4, marginRight: 6, fontSize: 9 }}>DEV</span>}
                      {log.msg || String(log)}
                    </span>
                  </div>
                );
              })}
            </div>
            <button style={{ ...s.refreshBtn, marginTop: 12 }} onClick={fetchAll}>↺ Refresh Logs</button>
          </Section>
        )}

        {/* ── AUDIT LOG ── */}
        {activeTab === "audit" && (
          <Section title="ADMIN SESSION AUDIT LOG" icon={ClipboardList}>
            <div style={s.logBox}>
              {auditLog.length === 0 && <div style={{ color: "#333", fontSize: 11 }}>No admin actions yet this session.</div>}
              {auditLog.map((e, i) => (
                <div key={i} style={{ display: "flex", gap: 10, padding: "6px 0", borderBottom: "1px solid rgba(255,255,255,0.02)" }}>
                  <span className="mono-text" style={{ color: "#444", fontSize: 10, flexShrink: 0 }}>{new Date(e.ts).toLocaleTimeString()}</span>
                  <span style={{ color: colors.gold, fontSize: 10, flexShrink: 0 }}>{e.admin}</span>
                  <span className="mono-text" style={{ color: "#aaa", fontSize: 11 }}>{e.action}</span>
                </div>
              ))}
            </div>
          </Section>
        )}

        <div style={s.footer}>© 2026 DOYOU.TRADE ADMIN SYSTEM • SECURE V4.0 • 2FA ENFORCED</div>
      </div>
    </div>
  );
}

// ─── Gate Styles ───────────────────────────────────────────────────────────────
const gs = {
  overlay: { minHeight: "100vh", background: "#050505", display: "flex", alignItems: "center", justifyContent: "center", padding: 20 },
  card: { width: "100%", maxWidth: 420, background: "rgba(12,12,12,0.95)", border: "1px solid rgba(212,175,55,0.12)", borderRadius: 28, padding: "44px 36px 36px", boxShadow: "0 24px 80px rgba(0,0,0,0.7)", display: "flex", flexDirection: "column", alignItems: "center", textAlign: "center", backdropFilter: "blur(20px)" },
  iconRing: { width: 72, height: 72, borderRadius: "50%", background: "rgba(212,175,55,0.06)", border: "1px solid rgba(212,175,55,0.2)", display: "flex", alignItems: "center", justifyContent: "center", boxShadow: "0 0 40px rgba(212,175,55,0.08)", marginBottom: 24 },
  title: { fontFamily: typography.fontDisplay, fontSize: 20, fontWeight: 800, letterSpacing: 4, color: colors.gold, margin: "0 0 10px", textShadow: `0 0 20px ${colors.gold}22` },
  sub: { fontSize: 13, color: colors.muted, lineHeight: 1.6, margin: "0 0 28px", maxWidth: 280 },
  row: { display: "flex", gap: 10, marginBottom: 20 },
  digit: { width: 46, height: 58, borderRadius: 12, background: "rgba(255,255,255,0.03)", color: colors.gold, fontSize: 24, fontWeight: 700, textAlign: "center", outline: "none", transition: "all 0.2s ease", caretColor: "transparent" },
  err: { display: "flex", alignItems: "center", color: colors.error, fontSize: 12, marginBottom: 16, background: "rgba(192,57,43,0.08)", border: `1px solid ${colors.error}22`, padding: "8px 14px", borderRadius: 8, textAlign: "left", width: "100%" },
  btn: { width: "100%", padding: 16, borderRadius: 14, background: `linear-gradient(135deg, ${colors.gold}cc, ${colors.gold}88)`, border: "none", color: "#000", fontSize: 14, fontWeight: 900, letterSpacing: 2, cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center", transition: "all 0.3s ease", marginBottom: 16 },
  link: { background: "none", border: "none", color: colors.muted, fontSize: 11, cursor: "pointer", display: "flex", alignItems: "center", opacity: 0.7, letterSpacing: 0.5 },
};

// ─── Admin Console Styles ──────────────────────────────────────────────────────
const s = {
  container: { minHeight: "100vh", background: "#050505", color: "#E0E0E0", display: "flex", justifyContent: "center", padding: "40px 16px" },
  page: { width: "100%", maxWidth: 1100 },
  header: { display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 24, flexWrap: "wrap", gap: 12 },
  backBtn: { background: "none", border: "none", color: colors.muted, fontSize: 12, cursor: "pointer", display: "flex", alignItems: "center" },
  title: { fontFamily: typography.fontDisplay, fontSize: 28, letterSpacing: 6, color: colors.gold, margin: 0, textShadow: `0 0 20px ${colors.gold}22` },
  badge: { fontSize: 10, letterSpacing: 2, padding: "4px 12px", borderRadius: 20, background: "rgba(212,175,55,0.1)", border: `1px solid ${colors.gold}33`, color: colors.gold, fontWeight: 800 },
  tabs: { display: "flex", gap: 6, marginBottom: 24, flexWrap: "wrap" },
  tab: { padding: "8px 14px", borderRadius: 10, background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.06)", color: colors.muted, fontSize: 11, cursor: "pointer", display: "flex", alignItems: "center", transition: "all 0.2s ease", letterSpacing: 0.5 },
  tabActive: { background: "rgba(212,175,55,0.1)", border: `1px solid ${colors.gold}44`, color: colors.gold },
  section: { background: "rgba(15,15,15,0.6)", backdropFilter: "blur(20px)", border: "1px solid", borderRadius: 20, padding: 28, boxShadow: "0 10px 40px rgba(0,0,0,0.3)", marginBottom: 20 },
  sTitle: { fontSize: 11, letterSpacing: 3, color: colors.muted, textTransform: "uppercase", margin: 0, fontWeight: 700 },
  statsGrid: { display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))", gap: 14 },
  statCard: { background: "rgba(255,255,255,0.02)", border: "1px solid rgba(255,255,255,0.03)", padding: "18px 16px", borderRadius: 14, textAlign: "center" },
  pauseBtn: { padding: "14px 24px", borderRadius: 12, border: "none", color: "#fff", fontSize: 13, fontWeight: 900, letterSpacing: 1.5, cursor: "pointer", transition: "all 0.3s ease" },
  stopBtn: { padding: "14px 20px", borderRadius: 12, border: `1px solid ${colors.error}66`, background: "rgba(0,0,0,0.5)", color: colors.error, fontSize: 12, fontWeight: 800, letterSpacing: 1, cursor: "pointer", transition: "all 0.3s ease" },
  goldBtn: { padding: "14px 24px", borderRadius: 12, background: `linear-gradient(135deg, ${colors.gold}cc, ${colors.gold}88)`, border: "none", color: "#000", fontSize: 13, fontWeight: 900, letterSpacing: 1.5, cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center", transition: "all 0.2s ease" },
  tableWrap: { overflowX: "auto", borderRadius: 12, border: "1px solid rgba(255,255,255,0.04)" },
  table: { width: "100%", borderCollapse: "collapse" },
  th: { padding: "10px 12px", fontSize: 10, color: colors.muted, letterSpacing: 1.5, textAlign: "left", borderBottom: "1px solid rgba(255,255,255,0.05)", background: "rgba(255,255,255,0.02)", whiteSpace: "nowrap" },
  tr: { transition: "background 0.15s ease" },
  td: { padding: "9px 12px", fontSize: 12, borderBottom: "1px solid rgba(255,255,255,0.03)", whiteSpace: "nowrap" },
  smBtn: { padding: "4px 8px", borderRadius: 6, background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.08)", color: colors.muted, cursor: "pointer", fontSize: 10, display: "flex", alignItems: "center" },
  searchInput: { width: "100%", padding: "10px 14px", borderRadius: 10, background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.07)", color: "#E0E0E0", fontSize: 12, outline: "none", boxSizing: "border-box" },
  label: { display: "block", fontSize: 11, color: colors.muted, marginBottom: 8, letterSpacing: 1 },
  select: { width: "100%", padding: "10px 12px", borderRadius: 10, background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.08)", color: "#E0E0E0", fontSize: 12, outline: "none", cursor: "pointer" },
  input: { width: "100%", padding: "10px 12px", borderRadius: 10, background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.08)", color: "#E0E0E0", fontSize: 12, outline: "none", boxSizing: "border-box" },
  logBox: { background: "#0a0a0a", border: "1px solid rgba(255,255,255,0.04)", borderRadius: 12, padding: 16, height: 380, overflowY: "auto", display: "flex", flexDirection: "column", gap: 2 },
  refreshBtn: { background: "none", border: `1px solid ${colors.muted}44`, color: colors.muted, padding: "8px 16px", borderRadius: 8, fontSize: 11, cursor: "pointer" },
  modalOverlay: { position: "fixed", inset: 0, background: "rgba(0,0,0,0.8)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 9999, backdropFilter: "blur(6px)" },
  modal: { background: "#111", border: `1px solid ${colors.gold}33`, borderRadius: 20, padding: 28, width: 340, boxShadow: "0 24px 80px rgba(0,0,0,0.7)" },
  footer: { marginTop: 60, textAlign: "center", color: "#333", fontSize: 10, letterSpacing: 2 },
};

const gateCss = `
  @keyframes tfa-spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
  @keyframes tfa-shake {
    0%,100% { transform: translateX(0); }
    16% { transform: translateX(-10px); }
    33% { transform: translateX(10px); }
    50% { transform: translateX(-8px); }
    66% { transform: translateX(8px); }
    83% { transform: translateX(-4px); }
  }
  .tfa-card { animation: tfa-fadein 0.4s ease; }
  .tfa-shake { animation: tfa-shake 0.6s ease !important; }
  @keyframes tfa-fadein { from { opacity: 0; transform: translateY(16px); } to { opacity: 1; transform: translateY(0); } }
  .tfa-digit:focus { border-color: rgba(212,175,55,0.6) !important; box-shadow: 0 0 20px rgba(212,175,55,0.15) !important; background: rgba(212,175,55,0.04) !important; }
  .tfa-submit:hover:not(:disabled) { opacity: 0.88 !important; transform: translateY(-1px); box-shadow: 0 12px 40px rgba(212,175,55,0.25); }
  .tfa-link:hover { color: #fff !important; opacity: 1 !important; }
`;

const adminCss = `
  .admin-stop-btn:hover { background: ${colors.error} !important; color: #fff !important; box-shadow: 0 0 20px ${colors.error}66; }
  .admin-action-btn:hover:not(:disabled) { transform: translateY(-1px); filter: brightness(1.1); }
  .admin-tab:hover { background: rgba(212,175,55,0.08) !important; color: rgba(212,175,55,0.8) !important; }
  .admin-row:hover td { background: rgba(212,175,55,0.025); }
  @media (max-width: 640px) {
    .admin-page h1 { font-size: 20px !important; letter-spacing: 3px !important; }
  }
  @media (max-width: 375px) {
    .admin-page h1 { font-size: 18px !important; letter-spacing: 2px !important; }
    .admin-page .stats-grid { grid-template-columns: 1fr 1fr !important; gap: 8px !important; }
  }
  @media (max-width: 320px) {
    .admin-page h1 { font-size: 16px !important; letter-spacing: 1px !important; }
    .admin-page .stats-grid { grid-template-columns: 1fr !important; }
    .admin-page .section { padding: 16px !important; }
  }
  @media (max-width: 280px) {
    .admin-page h1 { font-size: 14px !important; }
    .admin-page .section { padding: 12px !important; }
    .modal { width: calc(100vw - 24px) !important; max-width: none !important; }
  }
`;
