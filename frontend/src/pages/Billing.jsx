import { useState, useEffect } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext.jsx";
import { useAuthHeaders } from "../hooks/useAuthHeaders.js";
import { colors, typography } from "../theme.js";

const TIERS = [
  {
    id: "starter",
    name: "Starter",
    price: "$29",
    period: "/mo",
    features: ["1 exchange", "Basic strategies", "Paper + live trading", "Email support"],
    color: "#888",
  },
  {
    id: "pro",
    name: "Pro",
    price: "$79",
    period: "/mo",
    features: ["Up to 3 exchanges", "All strategies", "Smart order routing", "Priority AI", "Telegram alerts"],
    color: colors.gold,
    popular: true,
  },
  {
    id: "elite",
    name: "Elite",
    price: "$149",
    period: "/mo",
    features: ["All exchanges + on-chain", "Cross-exchange arbitrage", "DeFi integration", "Futures trading", "Dedicated support"],
    color: colors.success,
  },
];

const BACKEND_BASE = (import.meta.env.VITE_BACKEND_URL || "").replace(/\/$/, "") || (import.meta.env.DEV ? "http://localhost:8000" : "");

export default function Billing() {
  const { profile, refreshProfile } = useAuth();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const getAuthHeaders = useAuthHeaders();
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState(null);
  const currentTier = profile?.subscription_tier || "starter";

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
  }, [searchParams]);

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
          <button style={styles.backBtn} onClick={() => navigate("/dashboard")}>&larr; Dashboard</button>
          <h1 style={styles.title}>BILLING</h1>
        </div>

        <div style={styles.currentPlan}>
          <span style={{ color: colors.muted, fontSize: 11 }}>Current Plan:</span>
          <span style={{ color: colors.gold, fontFamily: typography.fontButton, fontSize: 16, letterSpacing: 2, textTransform: "uppercase" }}>
            {currentTier}
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
              style={{
                ...styles.tierCard,
                borderColor: tier.popular ? colors.gold : colors.border,
                ...(currentTier === tier.id ? { background: "rgba(212,175,55,0.03)" } : {}),
              }}
            >
              {tier.popular && <div style={styles.popularBadge}>MOST POPULAR</div>}
              <div style={{ ...styles.tierName, color: tier.color }}>{tier.name}</div>
              <div style={styles.tierPrice}>
                <span style={styles.priceAmount}>{tier.price}</span>
                <span style={styles.pricePeriod}>{tier.period}</span>
              </div>
              <ul style={styles.featureList}>
                {tier.features.map((f, i) => (
                  <li key={i} style={styles.featureItem}>
                    <span style={{ color: colors.success }}>&#10003;</span> {f}
                  </li>
                ))}
              </ul>
              {currentTier === tier.id ? (
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
            <div style={styles.faqA}>Yes. Cancel anytime from this page. Your bot will continue until the end of your billing period.</div>
          </div>
          <div style={styles.faqItem}>
            <div style={styles.faqQ}>What happens if my payment fails?</div>
            <div style={styles.faqA}>You get a 3-day grace period. After that, your bot pauses but your data is preserved.</div>
          </div>
          <div style={styles.faqItem}>
            <div style={styles.faqQ}>Do you touch my funds?</div>
            <div style={styles.faqA}>Never. Your API keys stay on your device. We send trade signals, your agent executes them.</div>
          </div>
        </div>
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
    padding: "20px 16px",
    paddingBottom: "calc(20px + env(safe-area-inset-bottom, 0px))",
  },
  page: { maxWidth: 800, margin: "0 auto" },
  header: { display: "flex", alignItems: "center", gap: 16, marginBottom: 24 },
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
    fontFamily: "'Oswald', sans-serif",
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
    fontFamily: "'Bebas Neue', sans-serif",
    fontSize: 22,
    letterSpacing: 3,
    marginBottom: 4,
  },
  tierPrice: { marginBottom: 16 },
  priceAmount: {
    fontFamily: "'Bebas Neue', sans-serif",
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
    fontFamily: "'Oswald', sans-serif",
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
`;
