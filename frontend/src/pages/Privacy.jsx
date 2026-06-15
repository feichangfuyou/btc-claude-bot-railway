import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { PublicNav } from "../components/PublicNav.jsx";
import { PublicFooter } from "../components/PublicFooter.jsx";
import { ArrowLeft } from "lucide-react";

const EFFECTIVE_DATE = "March 5, 2026";
const CONTACT_EMAIL = "feichangfuyou@doyou.trade";

export default function Privacy() {
    const navigate = useNavigate();

    useEffect(() => {
        document.title = "Privacy Policy — DoYou.trade | Encrypted Global Trading Privacy";
        const meta = document.querySelector('meta[name="description"]');
        if (meta) meta.setAttribute("content", "Privacy Policy for DoYou.trade. Learn how we protect your encrypted API keys and private trading data with advanced non-custodial security standards and institutional-grade encryption.");
    }, []);

    return (
        <div className="public-page">
            <PublicNav />
            <div className="legal-page__content">
                <button type="button" className="page-shell__back" onClick={() => navigate(-1)} style={{ marginBottom: 32 }}>
                    <ArrowLeft size={14} /> Back
                </button>
                <h1 className="legal-page__title">PRIVACY POLICY</h1>
                <p className="legal-page__meta">Effective: {EFFECTIVE_DATE}</p>

                <section className="legal-page__section">
                    <h2>1. What We Collect</h2>
                    <p>
                        <strong>Account data:</strong> email address, hashed password (via Supabase Auth).<br /><br />
                        <strong>Trading preferences:</strong> strategy, risk level, selected coins, paper/live mode — stored in our database.<br /><br />
                        <strong>Exchange credentials:</strong> API keys and secrets, encrypted at rest (AES-256 Fernet). We store only the encrypted ciphertext — plaintext keys are never persisted.<br /><br />
                        <strong>Usage data:</strong> trade history, system logs, and automated decisions — used to power the platform and your trade history view.<br /><br />
                        <strong>No financial data:</strong> We do not see your actual exchange balances, withdrawal addresses, or transaction history beyond what your API keys expose to the system.
                    </p>
                </section>

                <section className="legal-page__section">
                    <h2>2. How We Use It</h2>
                    <p>
                        — To operate the trading systems on your behalf<br />
                        — To display your trade history and analytics dashboard<br />
                        — To improve trading strategies (aggregated, never individual)<br />
                        — To send billing-related emails and account notifications<br />
                        — To comply with legal obligations
                    </p>
                </section>

                <section className="legal-page__section">
                    <h2>3. Data Sharing</h2>
                    <p>
                        We do not sell your data. We share data only with:<br /><br />
                        <strong>Supabase</strong> — database and auth provider (SOC 2 compliant)<br />
                        <strong>Stripe</strong> — payment processing (PCI-DSS compliant)<br />
                        <strong>Anthropic</strong> — Systematic inference (market data only, no personal data sent)<br />
                        <strong>Exchange APIs</strong> — your own exchange, using your keys
                    </p>
                </section>

                <section className="legal-page__section">
                    <h2>4. Data Retention</h2>
                    <p>
                        Trading data and preferences are retained while your account is active. Upon account
                        deletion, we delete your personal data within 30 days. Anonymized, aggregated trading
                        statistics may be retained for service improvement.
                    </p>
                </section>

                <section className="legal-page__section">
                    <h2>5. Security</h2>
                    <p>
                        API keys are encrypted using Fernet symmetric encryption before storage. Access to
                        your data within our database is protected by Row-Level Security (RLS) — no user
                        can query another user's rows. All data is transmitted over TLS 1.2+.
                    </p>
                </section>

                <section className="legal-page__section">
                    <h2>6. Your Rights</h2>
                    <p>
                        You may request access to, correction of, or deletion of your data at any time by
                        emailing <a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a>.
                        You can also delete your account directly from the Settings page.
                    </p>
                </section>

                <section className="legal-page__section">
                    <h2>7. Cookies</h2>
                    <p>
                        We use only essential session cookies from Supabase Auth. We do not use tracking
                        cookies or third-party analytics.
                    </p>
                </section>

                <section className="legal-page__section">
                    <h2>8. Changes</h2>
                    <p>
                        We may update this policy. Material changes will be emailed to registered users.
                        Continued use after changes constitutes acceptance.
                    </p>
                </section>

                <section className="legal-page__section">
                    <h2>9. Contact</h2>
                    <p>
                        Privacy questions: <a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a>
                    </p>
                </section>
            </div>
            <PublicFooter compact />
        </div>
    );
}
