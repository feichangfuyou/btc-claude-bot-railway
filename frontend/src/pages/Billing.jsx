import { useState, useEffect } from "react";
import { useNavigate, useSearchParams, Link } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext.jsx";
import { useAuthHeaders } from "../hooks/useAuthHeaders.js";
import { colors, typography } from "../theme.js";
import { ArrowLeft, Check, Lightbulb, Zap, Shield, Code2 } from "lucide-react";

const TIERS = [
  {
    id: "starter",
    name: "Starter",
    price: "$49",
    period: "/mo",
    features: ["1 exchange", "Standard Intelligence", "Top 10 Coins", "Paper + live trading"],
    color: colors.muted,
  },
  {
    id: "pro",
    name: "Pro",
    price: "$99",
    period: "/mo",
    features: ["Up to 3 exchanges", "Enhanced Strategy Engine", "50+ Coins", "Smart routing", "Priority support"],
    color: colors.gold,
    popular: true,
  },
  {
    id: "elite",
    name: "Elite",
    price: "$199",
    period: "/mo",
    features: ["Unlimited exchanges", "Ultra-Scale Execution", "All 100+ Coins", "Futures (10x leverage)", "On-chain + Vision"],
    color: colors.success,
  },
];

const BACKEND_BASE = (import.meta.env.VITE_BACKEND_URL || "").replace(/\/$/, "") || (import.meta.env.DEV ? "http://localhost:8000" : "");

const DEV_EMAIL = "feichangfuyou@gmail.com";

export default function Billing() {
  const { user, profile, signOut, refreshProfile } = useAuth();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const getAuthHeaders = useAuthHeaders();
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState(null);

  // Dev account always gets elite — overrides Supabase profile state
  const isDevUser = user?.email?.toLowerCase() === DEV_EMAIL;
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
  }, [searchParams, refreshProfile, setSearchParams]);

  async function handleSelectPlan(tierId) {
    setLoading(true);
    setMessage(null);
    try {
      const base = BACKEND_BASE || "";
      const url = base ? `${base}/billing/checkout` : "/billing/checkout";
      const res = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...getAuthHeaders() },
        body: JSON.stringify({ tier: tierId }),
      });
      const data = await res.json().catch(() => ({}));
      if (data.url) {
        window.location.href = data.url;
        return;
      }
      setMessage({ type: "error", text: data.error || "Stripe checkout unavailable. Please try again." });
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
            <button style={styles.backBtn} onClick={() => navigate("/dashboard")}><ArrowLeft size={14} style={{ marginRight: "4px", verticalAlign: "middle" }} /> Dashboard</button>
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
                    onClick={() => handleSelectPlan(tier.id)}
                    disabled={loading}
                  >
                    {loading ? "Redirecting…" : TIERS.findIndex(t => t.id === tier.id) > TIERS.findIndex(t => t.id === currentTier) ? "Upgrade" : "Downgrade"}
                  </button>
                )}
              </div>
            ))}
          </div>

          <div style={styles.faq}>
            <div style={styles.faqItem}>
              <div style={styles.faqQ}>Can I cancel anytime?</div>
              <div style={styles.faqA}>Yes. Cancel anytime from this page. Your automated systems will continue until the end of your billing period.</div>
            </div>
            <div style={styles.faqItem}>
              <div style={styles.faqQ}>What happens if my payment fails?</div>
              <div style={styles.faqA}>You get a 3-day grace period. After that, your platform pauses but your data is preserved.</div>
            </div>
            <div style={styles.faqItem}>
              <div style={styles.faqQ}>Do you touch my funds?</div>
              <div style={styles.faqA}>Never. Your exchange API keys are encrypted with AES-256 and stored securely. We never see your private keys or enable withdrawals. Our systems execute trades through your own exchange account using restricted API keys.</div>
            </div>

            {/* Capital Requirements Callout */}
            <div style={styles.faqItem}>
              <div style={styles.faqQ} id="capital-requirements">
                <Lightbulb size={16} /> How much capital do I need to trade live?
              </div>
              <div style={styles.faqA}>
                The system enforces strict minimums to ensure every trade is actually profitable after fees and execution costs:
              </div>
              <div style={styles.capitalCallout}>
                <div style={styles.capitalCalloutGrid} className="capital-callout-grid">
                  <div style={styles.calloutStat}>
                    <span style={styles.calloutVal}>$75</span>
                    <span style={styles.calloutLbl}>Min trade size — trades below this are auto-rejected</span>
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
                  <Zap size={14} /> The system will silently block any trade that can't clear $5 net profit at its take-profit price — protecting you from entering trades where fees eat all the gains.
                </div>
              </div>
            </div>
          </div>
        </div>

        <div style={styles.legalFooter}>
          <Link to="/terms" style={styles.legalLink}>Terms of Service</Link>
          <span style={{ color: "#333" }}> · </span>
          <Link to="/privacy" style={styles.legalLink}>Privacy Policy</Link>
          <span style={{ color: "#333" }}> · </span>
          <a href="mailto:support@doyou.trade" style={styles.legalLink}>Support</a>
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
