import { useNavigate } from "react-router-dom";

const EFFECTIVE_DATE = "March 5, 2026";
const COMPANY = "DoYou.Trade";
const CONTACT_EMAIL = "support@doyou.trade";

export default function Privacy() {
    const navigate = useNavigate();
    return (
        <div style={s.page}>
            <div style={s.content}>
                <button style={s.back} onClick={() => navigate(-1)}>← Back</button>
                <h1 style={s.h1}>Privacy Policy</h1>
                <p style={s.meta}>Effective: {EFFECTIVE_DATE}</p>

                <section style={s.section}>
                    <h2 style={s.h2}>1. What We Collect</h2>
                    <p style={s.p}>
                        <strong>Account data:</strong> email address, hashed password (via Supabase Auth).<br /><br />
                        <strong>Trading preferences:</strong> strategy, risk level, selected coins, paper/live mode — stored in our database.<br /><br />
                        <strong>Exchange credentials:</strong> API keys and secrets, encrypted at rest (AES-256 Fernet). We store only the encrypted ciphertext — plaintext keys are never persisted.<br /><br />
                        <strong>Usage data:</strong> trade history, bot logs, and AI decisions — used to power the learning system and your trade history view.<br /><br />
                        <strong>No financial data:</strong> We do not see your actual exchange balances, withdrawal addresses, or transaction history beyond what your API keys expose to the bot.
                    </p>
                </section>

                <section style={s.section}>
                    <h2 style={s.h2}>2. How We Use It</h2>
                    <p style={s.p}>
                        — To operate the trading bot on your behalf<br />
                        — To display your trade history and analytics dashboard<br />
                        — To improve AI trading strategies (aggregated, never individual)<br />
                        — To send billing-related emails and account notifications<br />
                        — To comply with legal obligations
                    </p>
                </section>

                <section style={s.section}>
                    <h2 style={s.h2}>3. Data Sharing</h2>
                    <p style={s.p}>
                        We do not sell your data. We share data only with:<br /><br />
                        <strong>Supabase</strong> — database and auth provider (SOC 2 compliant)<br />
                        <strong>Stripe</strong> — payment processing (PCI-DSS compliant)<br />
                        <strong>Anthropic</strong> — AI inference (market data only, no personal data sent)<br />
                        <strong>Exchange APIs</strong> — your own exchange, using your keys
                    </p>
                </section>

                <section style={s.section}>
                    <h2 style={s.h2}>4. Data Retention</h2>
                    <p style={s.p}>
                        Trading data and preferences are retained while your account is active. Upon account
                        deletion, we delete your personal data within 30 days. Anonymized, aggregated trading
                        statistics may be retained for service improvement.
                    </p>
                </section>

                <section style={s.section}>
                    <h2 style={s.h2}>5. Security</h2>
                    <p style={s.p}>
                        API keys are encrypted using Fernet symmetric encryption before storage. Access to
                        your data within our database is protected by Row-Level Security (RLS) — no user
                        can query another user's rows. All data is transmitted over TLS 1.2+.
                    </p>
                </section>

                <section style={s.section}>
                    <h2 style={s.h2}>6. Your Rights</h2>
                    <p style={s.p}>
                        You may request access to, correction of, or deletion of your data at any time by
                        emailing <a href={`mailto:${CONTACT_EMAIL}`} style={s.link}>{CONTACT_EMAIL}</a>.
                        You can also delete your account directly from the Settings page.
                    </p>
                </section>

                <section style={s.section}>
                    <h2 style={s.h2}>7. Cookies</h2>
                    <p style={s.p}>
                        We use only essential session cookies from Supabase Auth. We do not use tracking
                        cookies or third-party analytics.
                    </p>
                </section>

                <section style={s.section}>
                    <h2 style={s.h2}>8. Changes</h2>
                    <p style={s.p}>
                        We may update this policy. Material changes will be emailed to registered users.
                        Continued use after changes constitutes acceptance.
                    </p>
                </section>

                <section style={s.section}>
                    <h2 style={s.h2}>9. Contact</h2>
                    <p style={s.p}>
                        Privacy questions: <a href={`mailto:${CONTACT_EMAIL}`} style={s.link}>{CONTACT_EMAIL}</a>
                    </p>
                </section>
            </div>
        </div>
    );
}

const s = {
    page: {
        background: "#0A0A0A",
        minHeight: "100dvh",
        color: "#D4D4D4",
        fontFamily: "'Space Mono', monospace",
        padding: "32px 16px",
    },
    content: {
        maxWidth: 720,
        margin: "0 auto",
    },
    back: {
        fontFamily: "'Space Mono', monospace",
        fontSize: 12,
        padding: "6px 12px",
        background: "rgba(255,255,255,0.03)",
        border: "1px solid rgba(255,255,255,0.08)",
        borderRadius: 8,
        color: "#888",
        cursor: "pointer",
        marginBottom: 32,
        display: "block",
    },
    h1: {
        fontFamily: "'Bebas Neue', sans-serif",
        fontSize: 40,
        letterSpacing: 4,
        color: "#D4AF37",
        margin: "0 0 4px",
    },
    meta: {
        fontSize: 11,
        color: "#555",
        marginBottom: 40,
        letterSpacing: 1,
    },
    section: {
        marginBottom: 32,
        paddingBottom: 32,
        borderBottom: "1px solid rgba(255,255,255,0.04)",
    },
    h2: {
        fontFamily: "'Oswald', sans-serif",
        fontSize: 14,
        letterSpacing: 2,
        color: "#888",
        textTransform: "uppercase",
        margin: "0 0 12px",
    },
    p: {
        fontSize: 13,
        lineHeight: 1.8,
        color: "#C0C0C0",
        margin: 0,
    },
    link: {
        color: "#D4AF37",
        textDecoration: "none",
    },
};
