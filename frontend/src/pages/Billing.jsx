import { useState, useEffect } from "react";
import { useNavigate, useSearchParams, Link } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext.jsx";
import { useAuthHeaders } from "../hooks/useAuthHeaders.js";
import { isAdminEmail } from "../utils/adminEmails.js";
import { colors, typography } from "../theme.js";
import { ArrowLeft, Check, Lightbulb, Zap, Shield, Code2 } from "lucide-react";

const TIERS = [
  {
    id: "starter",
    name: "Starter",
    price: "$49",
    period: "/mo",
    features: ["1 connector", "Market Analytics", "Top 10 Assets", "Standard execution"],
    color: colors.muted,
  },
  {
    id: "pro",
    name: "Pro",
    price: "$99",
    period: "/mo",
    features: ["Up to 3 connectors", "Enhanced Strategy Engine", "50+ Assets", "Optimized execution paths", "Priority support"],
    color: colors.gold,
    popular: true,
  },
  {
    id: "elite",
    name: "Elite",
    price: "$199",
    period: "/mo",
    features: ["Unlimited connectors", "Ultra-Scale Data Feed", "All 100+ Assets", "Advanced execution engine", "On-chain Intelligence"],
    color: colors.success,
  },
];

const BACKEND_BASE = (import.meta.env.VITE_BACKEND_URL || "").replace(/\/$/, "") || (import.meta.env.DEV ? "http://localhost:8000" : "");

export default function Billing() {
  const { user, profile, signOut, refreshProfile } = useAuth();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const getAuthHeaders = useAuthHeaders();
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState(null);
  const [paymentStep, setPaymentStep] = useState("tiers"); // tiers, crypto-select, pay-details, pending
  const [selectedTier, setSelectedTier] = useState(null);
  const [selectedCrypto, setSelectedCrypto] = useState(null);
  const [txid, setTxid] = useState("");
  const [cryptoAddress, setCryptoAddress] = useState("");
  const [cryptoAmount, setCryptoAmount] = useState(0);
  const [history, setHistory] = useState([]);

  // Admin/dev accounts always get elite — overrides Supabase profile state
  const isDevUser = isAdminEmail(user?.email);
  const currentTier = isDevUser
    ? "elite"
    : (profile?.subscription_status === "active" ? (profile?.subscription_tier || "none") : "none");

  useEffect(() => {
    const success = searchParams.get("success");
    const cancelled = searchParams.get("cancelled");
    if (success === "true") {
      setMessage({ type: "success", text: "Subscription activated. Welcome to your new plan!" });
      refreshProfile?.();
      setSearchParams({}, { replace: true });
    } else if (cancelled === "true") {
      setMessage({ type: "info", text: "Checkout cancelled." });
      setSearchParams({}, { replace: true });
    }
    fetchHistory();
  }, [searchParams, refreshProfile, setSearchParams]);

  async function fetchHistory() {
    try {
      const base = BACKEND_BASE || "";
      const res = await fetch(`${base}/billing/manual-payments`, {
        headers: getAuthHeaders()
      });
      const ct = res.headers.get("content-type") || "";
      if (!ct.includes("application/json")) {
        console.warn("History fetch: non-JSON response (status:", res.status, ")");
        return;
      }
      const data = await res.json();
      if (Array.isArray(data)) setHistory(data);
    } catch (e) {
      console.error("History fetch failed", e);
    }
  }

  const CRYPTO_OPTIONS = [
    { id: "BTC", name: "Bitcoin", icon: "₿", color: "#F7931A" },
    { id: "ETH", name: "Ethereum", icon: "Ξ", color: "#627EEA" },
    { id: "SOL", name: "Solana", icon: "S", color: "#14F195" },
    { id: "USDT", name: "USDT (ERC20)", icon: "₮", color: "#26A17B" },
  ];

  async function fetchCryptoPrice(crypto) {
    try {
      const idMap = { BTC: "bitcoin", ETH: "ethereum", SOL: "solana", USDT: "tether" };
      const res = await fetch(`https://api.coingecko.com/api/v3/simple/price?ids=${idMap[crypto]}&vs_currencies=usd`);
      const data = await res.json();
      return data[idMap[crypto]].usd;
    } catch (e) {
      console.error("Price fetch failed", e);
      return null;
    }
  }

  async function handleStartPayment(tier) {
    setSelectedTier(tier);
    setPaymentStep("crypto-select");
  }

  async function handleSelectCrypto(crypto) {
    setLoading(true);
    setSelectedCrypto(crypto);
    try {
      // 1. Get address from backend (main cold-storage address; users send here)
      const base = BACKEND_BASE || "";
      const addrRes = await fetch(`${base}/billing/address/${crypto.id}`, {
        headers: getAuthHeaders()
      });
      const addrData = await addrRes.json();
      if (!addrData.address) {
        setMessage({ type: "error", text: addrData.error || "Payment address not configured. Please contact support." });
        setLoading(false);
        return;
      }
      setCryptoAddress(addrData.address);

      // 2. Calculate Amount
      const price = await fetchCryptoPrice(crypto.id);
      const tierPrice = parseInt(selectedTier.price.replace("$", ""));
      if (price) {
        setCryptoAmount((tierPrice / price).toFixed(crypto.id === "BTC" ? 8 : 6));
      } else {
        setCryptoAmount(`~${tierPrice} USD equivalent`);
      }

      setPaymentStep("pay-details");
    } catch (e) {
      setMessage({ type: "error", text: "Failed to initialize payment. Try again." });
    } finally {
      setLoading(false);
    }
  }

  async function handleSubmitTxid() {
    if (!txid.trim()) {
      setMessage({ type: "error", text: "Please enter your Transaction ID (TXID)." });
      return;
    }
    setLoading(true);
    try {
      const base = BACKEND_BASE || "";
      const res = await fetch(`${base}/billing/manual-payment`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...getAuthHeaders() },
        body: JSON.stringify({
          tier: selectedTier.id,
          crypto_type: selectedCrypto.id,
          amount: String(cryptoAmount),
          txid: txid
        }),
      });
      const data = await res.json();
      if (data.success) {
        setPaymentStep("pending");
        setMessage({ type: "success", text: data.message });
      } else {
        setMessage({ type: "error", text: data.error || "Submission failed." });
      }
    } catch (e) {
      setMessage({ type: "error", text: "Network error. Please try again." });
    } finally {
      setLoading(false);
    }
  }

  return (
    <>
      <style>{responsiveCss}</style>
      <div style={styles.container}>
        <div style={styles.page} className="billing-page">
          <div style={styles.header}>
            <button style={styles.backBtn} onClick={() => paymentStep === "tiers" ? navigate("/dashboard") : setPaymentStep("tiers")}>
              <ArrowLeft size={14} style={{ marginRight: "4px", verticalAlign: "middle" }} /> 
              {paymentStep === "tiers" ? "Dashboard" : "Back"}
            </button>
            <h1 style={styles.title}>BILLING</h1>
            {user && (
              <button style={styles.signOutBtn} onClick={signOut}>SIGN OUT</button>
            )}
          </div>

          {/* Dev account banner */}
          {isDevUser && (
            <div style={styles.devBanner}>
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <Code2 size={18} color={colors.gold} />
                <div>
                  <div style={{ fontFamily: typography.fontButton, fontSize: 13, color: colors.gold, letterSpacing: 2 }}>DEVELOPER ACCOUNT</div>
                  <div style={{ fontSize: 10, color: colors.muted, marginTop: 2 }}>Full Elite access granted — billing does not apply to this account</div>
                </div>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 6, background: "rgba(212,175,55,0.12)", border: "1px solid rgba(212,175,55,0.3)", borderRadius: 8, padding: "4px 10px" }}>
                <Shield size={12} color={colors.gold} />
                <span style={{ fontFamily: typography.fontButton, fontSize: 10, color: colors.gold, letterSpacing: 1 }}>ELITE</span>
              </div>
            </div>
          )}

          <div style={styles.currentPlan}>
            <span style={{ color: colors.muted, fontSize: 11 }}>Current Plan:</span>
            <span style={{ color: isDevUser ? colors.success : colors.gold, fontFamily: typography.fontButton, fontSize: 16, letterSpacing: 2, textTransform: "uppercase" }}>
              {isDevUser ? "Elite — Developer" : (currentTier === "none" ? "No Active Plan" : currentTier)}
            </span>
          </div>

          {message && (
            <div
              style={{
                ...styles.message,
                background: message.type === "error" ? "rgba(192,57,43,0.15)" : message.type === "success" ? "rgba(39,174,96,0.15)" : "rgba(212,175,55,0.1)",
                borderColor: message.type === "error" ? "rgba(192,57,43,0.5)" : message.type === "success" ? "rgba(39,174,96,0.5)" : "rgba(212,175,55,0.3)",
                color: message.type === "error" ? colors.error : message.type === "success" ? colors.success : colors.gold,
              }}
            >
              {message.text}
            </div>
          )}

          {paymentStep === "tiers" && (
            <>
              <div style={{ marginBottom: 20, padding: 12, borderRadius: 10, background: "rgba(212,175,55,0.05)", border: "1px solid rgba(212,175,55,0.15)", fontSize: 11, color: colors.gold, display: "flex", alignItems: "center", gap: 8 }}>
                <Zap size={14} /> 
                <span>We accept BTC, ETH, SOL and USDT for maximum privacy and manual verification.</span>
              </div>

              <div style={styles.tierGrid} className="tier-grid">
                {TIERS.map(tier => (
                  <div
                    key={tier.id}
                    className="tier-card"
                    style={{
                      ...styles.tierCard,
                      borderColor: tier.popular ? colors.gold : colors.border,
                      ...(currentTier === tier.id ? { background: "rgba(212,175,55,0.03)" } : {}),
                    }}
                  >
                    {tier.popular && <div style={styles.popularBadge}>MOST POPULAR</div>}
                    <div className="tier-name" style={{ ...styles.tierName, color: tier.color }}>{tier.name}</div>
                    <div style={styles.tierPrice}>
                      <span className="price-amount" style={styles.priceAmount}>{tier.price}</span>
                      <span style={styles.pricePeriod}>{tier.period}</span>
                    </div>
                    <ul className="feature-list" style={styles.featureList}>
                      {tier.features.map((f, i) => (
                        <li key={i} className="feature-item" style={styles.featureItem}>
                          <Check size={12} style={{ color: colors.success }} /> {f}
                        </li>
                      ))}
                    </ul>
                    {isDevUser && tier.id === "elite" ? (
                      <div style={{ ...styles.currentBadge, borderColor: "rgba(212,175,55,0.4)", color: colors.gold, background: "rgba(212,175,55,0.06)" }}>✦ Developer Access</div>
                    ) : isDevUser ? (
                      <div style={{ ...styles.currentBadge, color: colors.muted, borderColor: "rgba(255,255,255,0.06)" }}>Included in Dev</div>
                    ) : currentTier === tier.id ? (
                      <div style={styles.currentBadge}>Current Plan</div>
                    ) : (
                      <button
                        style={styles.selectBtn}
                        onClick={() => handleStartPayment(tier)}
                        disabled={loading}
                      >
                        {loading ? "Initializing…" : TIERS.findIndex(t => t.id === tier.id) > TIERS.findIndex(t => t.id === currentTier) ? "Upgrade" : "Downgrade"}
                      </button>
                    )}
                  </div>
                ))}
              </div>
            </>
          )}

          {paymentStep === "crypto-select" && (
            <div style={styles.paymentSection}>
              <h2 style={styles.sectionTitle}>Select Payment Method</h2>
              <div style={styles.cryptoGrid}>
                {CRYPTO_OPTIONS.map(crypto => (
                  <button
                    key={crypto.id}
                    style={{...styles.cryptoBtn, borderColor: crypto.color + "44"}}
                    onClick={() => handleSelectCrypto(crypto)}
                  >
                    <span style={{...styles.cryptoIcon, color: crypto.color}}>{crypto.icon}</span>
                    <span style={styles.cryptoName}>{crypto.name}</span>
                  </button>
                ))}
              </div>
            </div>
          )}

          {paymentStep === "pay-details" && (
            <div style={styles.paymentSection}>
              <h2 style={styles.sectionTitle}>Send Payment</h2>
              <div style={styles.payCard}>
                <div style={styles.payRow}>
                  <span style={styles.payLabel}>Plan:</span>
                  <span style={styles.payValue}>{selectedTier.name} ({selectedTier.price})</span>
                </div>
                <div style={styles.payRow}>
                  <span style={styles.payLabel}>Amount to Send:</span>
                  <span style={{...styles.payValue, color: colors.gold, fontSize: 18}}>{cryptoAmount} {selectedCrypto.id}</span>
                </div>
                <div style={styles.payRow}>
                  <span style={styles.payLabel}>Destination Address:</span>
                  <div style={styles.addressBox}>
                    <code style={styles.addressText}>{cryptoAddress}</code>
                    <button style={styles.copyBtn} onClick={() => {navigator.clipboard.writeText(cryptoAddress); setMessage({type: "info", text: "Address copied!"})}}>Copy</button>
                  </div>
                </div>
                
                <div style={{marginTop: 24, borderTop: "1px solid rgba(255,255,255,0.05)", paddingTop: 20}}>
                  <div style={{fontSize: 12, color: colors.muted, marginBottom: 8}}>Once you have sent the payment, enter the Transaction ID (TXID) below:</div>
                  <input 
                    style={styles.input}
                    placeholder="Enter Transaction ID (TXID)"
                    value={txid}
                    onChange={(e) => setTxid(e.target.value)}
                  />
                  <button 
                    style={styles.submitBtn}
                    onClick={handleSubmitTxid}
                    disabled={loading}
                  >
                    {loading ? "Submitting..." : "Confirm Payment"}
                  </button>
                  <div style={{fontSize: 10, color: "#555", marginTop: 12, textAlign: "center"}}>
                    Verification usually takes 10-60 minutes depending on network congestion.
                  </div>
                </div>
              </div>
            </div>
          )}

          {paymentStep === "pending" && (
            <div style={styles.paymentSection}>
              <div style={{textAlign: "center", padding: "40px 20px"}}>
                <div style={{fontSize: 48, marginBottom: 20}}>⏳</div>
                <h2 style={styles.sectionTitle}>Payment Pending</h2>
                <p style={{color: colors.muted, fontSize: 13, lineHeight: 1.6}}>
                  We've received your transaction details for the <strong>{selectedTier.name}</strong> plan.<br/>
                  Our automated scripts and manual auditors are verifying the payment on-chain.
                </p>
                <div style={{background: "rgba(212,175,55,0.05)", padding: 16, borderRadius: 12, marginTop: 20, textAlign: "left"}}>
                  <div style={{fontSize: 11, color: colors.muted, marginBottom: 4}}>TXID:</div>
                  <code style={{fontSize: 11, color: colors.gold, wordBreak: "break-all"}}>{txid}</code>
                </div>
                <button style={{...styles.backBtn, marginTop: 30, width: "100%"}} onClick={() => navigate("/dashboard")}>Back to Dashboard</button>
              </div>
            </div>
          )}

          <div style={styles.faq}>
            <div style={styles.faqItem}>
              <div style={styles.faqQ}>How does manual verification work?</div>
              <div style={styles.faqA}>After you submit your TXID, our system monitors the blockchain explorer. Once confirmed, your account is automatically upgraded. In rare cases, a manual review by our team may be required.</div>
            </div>
            <div style={styles.faqItem}>
              <div style={styles.faqQ}>Can I cancel anytime?</div>
              <div style={styles.faqA}>Yes. Since this is a manual crypto payment, you simply don't renew at the end of your period. Your strategy execution will continue until the end of your paid period.</div>
            </div>
            <div style={styles.faqItem}>
              <div style={styles.faqQ}>What happens if my payment fails?</div>
              <div style={styles.faqA}>If you send the wrong amount or to the wrong address, please contact support with your TXID immediately.</div>
            </div>
            <div style={styles.faqItem}>
              <div style={styles.faqQ}>Do you touch my funds?</div>
              <div style={styles.faqA}>Never. Your account connectors are encrypted and stored securely. We never see your private keys or enable withdrawals. Our systems execute strategies through your own accounts using restricted permissions.</div>
            </div>

            {/* Capital Requirements Callout */}
            <div style={styles.faqItem}>
              <div style={styles.faqQ}>
                <Lightbulb size={16} /> What are the system requirements for live execution?
              </div>
              <div style={styles.faqA}>
                The system enforces minimum execution parameters to ensure tactical efficiency:
              </div>
              <div style={styles.capitalCallout}>
                <div style={styles.capitalCalloutGrid} className="capital-callout-grid">
                  <div style={styles.calloutStat}>
                    <span style={styles.calloutVal}>$75</span>
                    <span style={styles.calloutLbl}>Min execution size — entries below this are auto-rejected</span>
                  </div>
                  <div style={styles.calloutStat}>
                    <span style={styles.calloutVal}>$750</span>
                    <span style={styles.calloutLbl}>Recommended starting balance — ensures 10% position = $75</span>
                  </div>
                  <div style={styles.calloutStat}>
                    <span style={styles.calloutVal}>1.2%</span>
                    <span style={styles.calloutLbl}>Round-trip fees per trade (0.6% in + 0.6% out)</span>
                  </div>
                  <div style={styles.calloutStat}>
                    <span style={styles.calloutVal}>$5</span>
                    <span style={styles.calloutLbl}>Minimum net profit at take-profit after all costs</span>
                  </div>
                </div>
                <div style={styles.calloutNote}>
                  <Zap size={14} /> The system will bypass any entry that cannot clear efficiency thresholds after all execution costs.
                </div>
              </div>
            </div>
          </div>

          {history.length > 0 && (
            <div style={{...styles.paymentSection, marginTop: 32}}>
              <h3 style={{...styles.sectionTitle, fontSize: 16, textAlign: "left", marginBottom: 16}}>Recent Submissions</h3>
              <div style={styles.historyTable}>
                {history.map((h) => (
                  <div key={h.id} style={styles.historyRow}>
                    <div style={{display: "flex", justifyContent: "space-between", marginBottom: 4}}>
                      <span style={{color: colors.gold, fontSize: 13}}>{h.tier.toUpperCase()}</span>
                      <span style={{
                        fontSize: 10,
                        padding: "2px 8px",
                        borderRadius: 4,
                        background: h.status === "verified" ? "rgba(39,174,96,0.1)" : h.status === "rejected" ? "rgba(192,57,43,0.1)" : "rgba(212,175,55,0.1)",
                        color: h.status === "verified" ? colors.success : h.status === "rejected" ? colors.error : colors.gold,
                        border: "1px solid",
                        borderColor: h.status === "verified" ? "rgba(39,174,96,0.3)" : h.status === "rejected" ? "rgba(192,57,43,0.3)" : "rgba(212,175,55,0.3)",
                      }}>{h.status.toUpperCase()}</span>
                    </div>
                    <div style={{display: "flex", justifyContent: "space-between", fontSize: 11, color: colors.muted}}>
                      <span>{h.amount} {h.crypto_type}</span>
                      <span>{new Date(h.created_at).toLocaleDateString()}</span>
                    </div>
                    <div style={{fontSize: 9, color: "#444", marginTop: 4, fontFamily: typography.fontMono, wordBreak: "break-all"}}>
                      TXID: {h.txid}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        <div style={styles.legalFooter}>
          <Link to="/terms" style={styles.legalLink}>Terms of Service</Link>
          <span style={{ color: "#333" }}> · </span>
          <Link to="/privacy" style={styles.legalLink}>Privacy Policy</Link>
          <span style={{ color: "#333" }}> · </span>
          <a href="mailto:feichangfuyou@doyou.trade" style={styles.legalLink}>Support</a>
        </div>
      </div>
    </>
  );
}

const styles = {
  container: {
    fontFamily: typography.fontMono,
    background: colors.dark,
    color: colors.text,
    minHeight: "100dvh",
    width: "100%",
    maxWidth: "100vw",
    boxSizing: "border-box",
    padding: "20px 16px",
    paddingBottom: "calc(20px + env(safe-area-inset-bottom, 0px))",
  },
  page: { maxWidth: 800, margin: "0 auto", width: "100%", boxSizing: "border-box" },
  header: { display: "flex", alignItems: "center", gap: 16, marginBottom: 24, flexWrap: "wrap" },
  title: {
    fontFamily: typography.fontDisplay,
    fontSize: 28,
    fontWeight: 400,
    letterSpacing: 4,
    color: colors.gold,
    margin: 0,
  },
  backBtn: {
    fontFamily: "'Space Mono', monospace",
    fontSize: 12,
    padding: "6px 12px",
    background: "rgba(255,255,255,0.03)",
    backdropFilter: "blur(8px)",
    WebkitBackdropFilter: "blur(8px)",
    border: "1px solid rgba(255,255,255,0.06)",
    borderRadius: 8,
    color: colors.muted,
    cursor: "pointer",
    transition: "all 0.2s ease",
  },
  signOutBtn: {
    fontFamily: "'Space Mono', monospace",
    fontSize: 11,
    letterSpacing: 1.5,
    padding: "6px 12px",
    background: "transparent",
    border: "1px solid rgba(255,255,255,0.08)",
    borderRadius: 8,
    color: "#5C5C5C",
    cursor: "pointer",
    marginLeft: "auto",
    transition: "all 0.2s ease",
  },
  devBanner: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    background: "linear-gradient(135deg, rgba(212,175,55,0.06), rgba(212,175,55,0.02))",
    border: "1px solid rgba(212,175,55,0.2)",
    borderRadius: 14,
    padding: "14px 18px",
    marginBottom: 20,
    backdropFilter: "blur(10px)",
    WebkitBackdropFilter: "blur(10px)",
    boxShadow: "0 4px 20px rgba(212,175,55,0.06), inset 0 1px 0 rgba(212,175,55,0.1)",
  },
  currentPlan: {
    display: "flex",
    alignItems: "center",
    gap: 10,
    marginBottom: 24,
  },
  message: {
    padding: "12px 16px",
    borderRadius: 10,
    border: "1px solid",
    fontSize: 12,
    marginBottom: 20,
  },
  tierGrid: { display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 16, marginBottom: 32 },
  tierCard: {
    background: "rgba(17,17,17,0.55)",
    backdropFilter: "blur(20px) saturate(1.4)",
    WebkitBackdropFilter: "blur(20px) saturate(1.4)",
    border: "1px solid rgba(212,175,55,0.1)",
    borderRadius: 20,
    padding: "24px 20px",
    position: "relative",
    display: "flex",
    flexDirection: "column",
    boxShadow: "0 8px 32px rgba(0,0,0,0.4), inset 0 1px 0 rgba(255,255,255,0.04)",
    transition: "border-color 0.3s ease, box-shadow 0.3s ease, transform 0.3s ease",
  },
  popularBadge: {
    position: "absolute",
    top: -10,
    left: "50%",
    transform: "translateX(-50%)",
    fontFamily: "'Montserrat', sans-serif",
    fontSize: 9,
    letterSpacing: 2,
    padding: "3px 12px",
    background: colors.gold,
    color: colors.dark,
    borderRadius: 10,
    fontWeight: 600,
    boxShadow: "0 4px 12px rgba(212,175,55,0.3)",
  },
  tierName: {
    fontFamily: "'Montserrat', sans-serif",
    fontSize: 22,
    letterSpacing: 3,
    marginBottom: 4,
  },
  tierPrice: { marginBottom: 16 },
  priceAmount: {
    fontFamily: "'Montserrat', sans-serif",
    fontSize: 36,
    letterSpacing: 2,
  },
  pricePeriod: { fontSize: 12, color: colors.muted },
  featureList: { listStyle: "none", padding: 0, margin: "0 0 20px", flex: 1 },
  featureItem: { fontSize: 11, padding: "4px 0", display: "flex", gap: 6 },
  currentBadge: {
    textAlign: "center",
    fontSize: 11,
    color: colors.success,
    padding: "8px 0",
    border: "1px solid rgba(39,174,96,0.3)",
    borderRadius: 8,
    background: "rgba(39,174,96,0.05)",
  },
  selectBtn: {
    fontFamily: "'Montserrat', sans-serif",
    fontSize: 13,
    fontWeight: 600,
    letterSpacing: 2,
    padding: "10px 0",
    border: "none",
    borderRadius: 10,
    cursor: "pointer",
    background: `linear-gradient(180deg, ${colors.gold}, ${colors.goldDark})`,
    color: colors.dark,
    textAlign: "center",
    boxShadow: "0 4px 20px rgba(212,175,55,0.2)",
    transition: "all 0.25s cubic-bezier(0.4, 0, 0.2, 1)",
  },
  faq: {
    background: "rgba(17,17,17,0.55)",
    backdropFilter: "blur(20px) saturate(1.4)",
    WebkitBackdropFilter: "blur(20px) saturate(1.4)",
    border: "1px solid rgba(212,175,55,0.1)",
    borderRadius: 16,
    padding: 20,
    boxShadow: "0 8px 32px rgba(0,0,0,0.4), inset 0 1px 0 rgba(255,255,255,0.04)",
  },
  faqItem: { marginBottom: 16 },
  faqQ: { fontSize: 12, fontWeight: 600, marginBottom: 4 },
  faqA: { fontSize: 11, color: colors.muted, lineHeight: 1.6 },
  capitalCallout: {
    marginTop: 12,
    background: "rgba(212,175,55,0.04)",
    border: "1px solid rgba(212,175,55,0.16)",
    borderRadius: 12,
    padding: "14px 16px",
  },
  capitalCalloutGrid: {
    display: "grid",
    gridTemplateColumns: "1fr 1fr",
    gap: 8,
    marginBottom: 10,
  },
  calloutStat: {
    display: "flex",
    flexDirection: "column",
    gap: 3,
    background: "rgba(0,0,0,0.2)",
    border: "1px solid rgba(255,255,255,0.04)",
    borderRadius: 8,
    padding: "9px 11px",
  },
  calloutVal: {
    fontFamily: "'Montserrat', sans-serif",
    fontSize: 20,
    fontWeight: 700,
    color: colors.gold,
    lineHeight: 1,
  },
  calloutLbl: {
    fontSize: 10,
    color: "#777",
    lineHeight: 1.4,
  },
  calloutNote: {
    fontSize: 10,
    color: "#777",
    lineHeight: 1.6,
    background: "rgba(0,0,0,0.18)",
    border: "1px solid rgba(255,255,255,0.04)",
    borderRadius: 8,
    padding: "7px 10px",
  },
  legalFooter: {
    textAlign: "center",
    marginTop: 24,
    fontSize: 11,
    color: "#444",
    letterSpacing: 0.5,
  },
  legalLink: {
    color: "#555",
    textDecoration: "none",
    transition: "color 0.2s",
  },
  paymentSection: {
    background: "rgba(17,17,17,0.55)",
    backdropFilter: "blur(20px)",
    WebkitBackdropFilter: "blur(20px)",
    border: "1px solid rgba(212,175,55,0.1)",
    borderRadius: 20,
    padding: "32px 24px",
    marginBottom: 32,
    boxShadow: "0 8px 32px rgba(0,0,0,0.4)",
  },
  sectionTitle: {
    fontFamily: typography.fontDisplay,
    fontSize: 20,
    letterSpacing: 2,
    color: colors.gold,
    marginBottom: 24,
    textAlign: "center",
  },
  cryptoGrid: {
    display: "grid",
    gridTemplateColumns: "1fr 1fr",
    gap: 16,
  },
  cryptoBtn: {
    background: "rgba(255,255,255,0.03)",
    border: "1px solid",
    borderRadius: 16,
    padding: "20px 16px",
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    gap: 12,
    cursor: "pointer",
    transition: "all 0.2s ease",
    color: colors.text,
  },
  cryptoIcon: {
    fontSize: 32,
    fontWeight: 700,
  },
  cryptoName: {
    fontSize: 14,
    fontFamily: typography.fontButton,
    letterSpacing: 1,
  },
  payCard: {
    display: "flex",
    flexDirection: "column",
    gap: 16,
  },
  payRow: {
    display: "flex",
    flexDirection: "column",
    gap: 4,
  },
  payLabel: {
    fontSize: 11,
    color: colors.muted,
    textTransform: "uppercase",
    letterSpacing: 1,
  },
  payValue: {
    fontSize: 15,
    fontFamily: typography.fontMono,
    color: colors.text,
  },
  addressBox: {
    background: "rgba(0,0,0,0.3)",
    border: "1px solid rgba(255,255,255,0.08)",
    borderRadius: 10,
    padding: "12px 16px",
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 12,
  },
  addressText: {
    fontSize: 12,
    color: colors.gold,
    wordBreak: "break-all",
    fontFamily: typography.fontMono,
  },
  copyBtn: {
    background: "rgba(212,175,55,0.1)",
    border: "1px solid rgba(212,175,55,0.3)",
    borderRadius: 6,
    color: colors.gold,
    fontSize: 10,
    padding: "4px 8px",
    cursor: "pointer",
    fontFamily: typography.fontButton,
  },
  input: {
    width: "100%",
    background: "rgba(0,0,0,0.3)",
    border: "1px solid rgba(255,255,255,0.1)",
    borderRadius: 10,
    padding: "14px 16px",
    color: colors.text,
    fontFamily: typography.fontMono,
    fontSize: 13,
    boxSizing: "border-box",
    marginBottom: 16,
    outline: "none",
  },
  submitBtn: {
    width: "100%",
    padding: "14px",
    borderRadius: 12,
    border: "none",
    background: `linear-gradient(180deg, ${colors.gold}, ${colors.goldDark})`,
    color: colors.dark,
    fontFamily: typography.fontButton,
    fontWeight: 700,
    letterSpacing: 2,
    cursor: "pointer",
    boxShadow: "0 4px 20px rgba(212,175,55,0.2)",
  },
};

const responsiveCss = `
@media (max-width: 768px) {
  .billing-page {
    max-width: 100% !important;
  }
  .tier-grid {
    grid-template-columns: 1fr !important;
    gap: 12px !important;
  }
}
@media (max-width: 600px) {
  .billing-page {
    padding: 0 !important;
  }
}
@media (max-width: 375px) {
  .billing-page {
    padding: 0 !important;
  }
}
@media (max-width: 320px) {
  .billing-page {
    padding: 0 !important;
  }
}
@media (max-width: 280px) {
  .billing-page {
    padding: 0 !important;
    max-width: 100% !important;
  }
  .tier-grid {
    gap: 8px !important;
    grid-template-columns: 1fr !important;
  }
  .billing-page .tier-card {
    padding: 12px 10px !important;
    min-width: 0 !important;
  }
  .billing-page .tier-name {
    font-size: 14px !important;
    letter-spacing: 1px !important;
  }
  .billing-page .price-amount {
    font-size: 20px !important;
  }
  .billing-page .feature-item {
    font-size: 9px !important;
  }
  .billing-page .capital-callout-grid {
    grid-template-columns: 1fr !important;
    gap: 6px !important;
  }
  .billing-page .callout-val {
    font-size: 16px !important;
  }
  .billing-page .callout-lbl {
    font-size: 9px !important;
  }
}
`;
