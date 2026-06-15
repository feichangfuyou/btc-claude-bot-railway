import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { PublicNav } from "../components/PublicNav.jsx";
import { PublicFooter } from "../components/PublicFooter.jsx";
import { ArrowLeft } from "lucide-react";

const EFFECTIVE_DATE = "March 5, 2026";
const COMPANY = "DoYou.Trade";
const CONTACT_EMAIL = "feichangfuyou@doyou.trade";

export default function Terms() {
    const navigate = useNavigate();

    useEffect(() => {
        document.title = "Terms of Service — DoYou.trade | Professional Trading Agreement";
        const meta = document.querySelector('meta[name="description"]');
        if (meta) meta.setAttribute("content", "Read the Terms of Service for DoYou.trade. Professional-grade non-custodial trading terminal services, risk disclosure, and user agreement.");
    }, []);

    return (
        <div className="public-page">
            <PublicNav />
            <div className="legal-page__content">
                <button type="button" className="page-shell__back" onClick={() => navigate(-1)} style={{ marginBottom: 32 }}>
                    <ArrowLeft size={14} /> Back
                </button>
                <h1 className="legal-page__title">TERMS OF SERVICE</h1>
                <p className="legal-page__meta">Effective: {EFFECTIVE_DATE}</p>

                <section className="legal-page__section">
                    <h2>1. Acceptance</h2>
                    <p>
                        By creating an account or using {COMPANY} ("Service"), you agree to these Terms. If you
                        do not agree, do not use the Service.
                    </p>
                </section>

                <section className="legal-page__section">
                    <h2>2. Service Description</h2>
                    <p>
                        {COMPANY} provides an advanced crypto trading dashboard. The Service connects to
                        exchanges on your behalf using API keys you provide. We do not custody funds, hold
                        private keys, or make financial decisions without your configuration.
                    </p>
                </section>

                <section className="legal-page__section">
                    <h2>3. Not Financial Advice</h2>
                    <p>
                        <strong>All content and signals are for informational purposes only.</strong> Nothing
                        on {COMPANY} constitutes financial, investment, or trading advice. Cryptocurrency
                        trading involves substantial risk of loss. You are solely responsible for all trading
                        decisions and their outcomes.
                    </p>
                </section>

                <section className="legal-page__section">
                    <h2>4. Eligibility</h2>
                    <p>
                        You must be at least 18 years old and legally permitted to trade cryptocurrency in
                        your jurisdiction. By using the Service you confirm this.
                    </p>
                </section>

                <section className="legal-page__section">
                    <h2>5. API Keys &amp; Security</h2>
                    <p>
                        Your exchange API keys are encrypted at rest using AES-256 (Fernet) and are never
                        transmitted to third parties. You are responsible for using restricted API keys
                        (no withdrawal permissions). {COMPANY} is not liable for losses caused by
                        misconfigured or compromised API keys.
                    </p>
                </section>

                <section className="legal-page__section">
                    <h2>6. Subscriptions &amp; Billing</h2>
                    <p>
                        Paid plans are billed monthly via Stripe. You may cancel at any time; access continues
                        until the end of your billing period. Refunds are not provided for partial months.
                        We reserve the right to change pricing with 30 days notice.
                    </p>
                </section>

                <section className="legal-page__section">
                    <h2>7. Prohibited Use</h2>
                    <p>You may not: (a) use the Service for market manipulation; (b) reverse-engineer
                        or resell the Service; (c) circumvent rate limits or security measures; (d) use the
                        Service in jurisdictions where crypto trading is prohibited.</p>
                </section>

                <section className="legal-page__section">
                    <h2>8. Disclaimer of Warranties</h2>
                    <p>
                        THE SERVICE IS PROVIDED "AS IS" WITHOUT WARRANTY OF ANY KIND. WE DO NOT GUARANTEE
                        UPTIME, ACCURACY OF SYSTEM SIGNALS, OR PROFITABLE TRADING OUTCOMES.
                    </p>
                </section>

                <section className="legal-page__section">
                    <h2>9. Limitation of Liability</h2>
                    <p>
                        TO THE MAXIMUM EXTENT PERMITTED BY LAW, {COMPANY.toUpperCase()} SHALL NOT BE LIABLE
                        FOR ANY TRADING LOSSES, INDIRECT, INCIDENTAL, OR CONSEQUENTIAL DAMAGES ARISING FROM
                        USE OF THE SERVICE.
                    </p>
                </section>

                <section className="legal-page__section">
                    <h2>10. Termination</h2>
                    <p>
                        We may suspend or terminate accounts that violate these Terms. You may delete your
                        account at any time from the Settings page.
                    </p>
                </section>

                <section className="legal-page__section">
                    <h2>11. Contact</h2>
                    <p>Questions? Email <a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a></p>
                </section>
            </div>
            <PublicFooter compact />
        </div>
    );
}
