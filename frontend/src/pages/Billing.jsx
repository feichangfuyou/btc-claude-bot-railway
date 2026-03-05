import { useNavigate } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext.jsx";

const GOLD = "#D4AF37";
const DARK = "#0A0A0A";
const CARD = "#111111";
const BORDER = "#1A1A1A";
const MUTED = "#5C5C5C";
const GREEN = "#27AE60";

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
    color: GOLD,
    popular: true,
  },
  {
    id: "elite",
    name: "Elite",
    price: "$149",
    period: "/mo",
    features: ["All exchanges + on-chain", "Cross-exchange arbitrage", "DeFi integration", "Futures trading", "Dedicated support"],
    color: GREEN,
  },
];

export default function Billing() {
  const { profile } = useAuth();
  const navigate = useNavigate();
  const currentTier = profile?.subscription_tier || "starter";

  function handleSelectPlan(tierId) {
    // Stripe Checkout integration will go here
    alert(`Stripe checkout for ${tierId} plan coming soon!`);
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
          <span style={{ color: MUTED, fontSize: 11 }}>Current Plan:</span>
          <span style={{ color: GOLD, fontFamily: "'Oswald', sans-serif", fontSize: 16, letterSpacing: 2, textTransform: "uppercase" }}>
            {currentTier}
          </span>
        </div>

        <div style={styles.tierGrid} className="tier-grid">
          {TIERS.map(tier => (
            <div
              key={tier.id}
              style={{
                ...styles.tierCard,
                borderColor: tier.popular ? GOLD : BORDER,
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
                    <span style={{ color: GREEN }}>&#10003;</span> {f}
                  </li>
                ))}
              </ul>
              {currentTier === tier.id ? (
                <div style={styles.currentBadge}>Current Plan</div>
              ) : (
                <button style={styles.selectBtn} onClick={() => handleSelectPlan(tier.id)}>
                  {TIERS.findIndex(t => t.id === tier.id) > TIERS.findIndex(t => t.id === currentTier) ? "Upgrade" : "Downgrade"}
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
    fontFamily: "'Space Mono', monospace",
    background: DARK,
    color: "#D4D4D4",
    minHeight: "100dvh",
    padding: "20px 16px",
    paddingBottom: "calc(20px + env(safe-area-inset-bottom, 0px))",
  },
  page: { maxWidth: 800, margin: "0 auto" },
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
    background: "rgba(255,255,255,0.03)",
    backdropFilter: "blur(8px)",
    WebkitBackdropFilter: "blur(8px)",
    border: "1px solid rgba(255,255,255,0.06)",
    borderRadius: 8,
    color: MUTED,
    cursor: "pointer",
    transition: "all 0.2s ease",
  },
  currentPlan: {
    display: "flex",
    alignItems: "center",
    gap: 10,
    marginBottom: 24,
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
    background: GOLD,
    color: DARK,
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
  pricePeriod: { fontSize: 12, color: MUTED },
  featureList: { listStyle: "none", padding: 0, margin: "0 0 20px", flex: 1 },
  featureItem: { fontSize: 11, padding: "4px 0", display: "flex", gap: 6 },
  currentBadge: {
    textAlign: "center",
    fontSize: 11,
    color: GREEN,
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
    background: `linear-gradient(180deg, ${GOLD}, #B8860B)`,
    color: DARK,
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
  faqA: { fontSize: 11, color: MUTED, lineHeight: 1.6 },
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
