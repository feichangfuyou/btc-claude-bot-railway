import { useEffect } from "react";
import { useNavigate } from "react-router-dom";

const EFFECTIVE_DATE = "March 5, 2026";
const COMPANY = "DoYou.Trade";
const CONTACT_EMAIL = "support@doyou.trade";

export default function Terms() {
    const navigate = useNavigate();

    useEffect(() => {
        document.title = "Terms of Service — DoYou.trade";
        const meta = document.querySelector('meta[name="description"]');
        if (meta) meta.setAttribute("content", "Read the Terms of Service for DoYou.trade. Professional-grade non-custodial AI trading terminal services and user agreement.");
    }, []);

    return (
        <div style={s.page}>
            <div style={s.content}>
                <button style={s.back} onClick={() => navigate(-1)}>← Back</button>
                <h1 style={s.h1}>Terms of Service</h1>
                <p style={s.meta}>Effective: {EFFECTIVE_DATE}</p>

                <section style={s.section}>
                    <h2 style={s.h2}>1. Acceptance</h2>
                    <p style={s.p}>
                        By creating an account or using {COMPANY} ("Service"), you agree to these Terms. If you
                        do not agree, do not use the Service.
                    </p>
                </section>

                <section style={s.section}>
                    <h2 style={s.h2}>2. Service Description</h2>
                    <p style={s.p}>
                        {COMPANY} provides an AI-assisted crypto trading dashboard. The Service connects to
                        exchanges on your behalf using API keys you provide. We do not custody funds, hold
                        private keys, or make financial decisions without your configuration.
                    </p>
                </section>

                <section style={s.section}>
                    <h2 style={s.h2}>3. Not Financial Advice</h2>
                    <p style={s.p}>
                        <strong>All content and signals are for informational purposes only.</strong> Nothing
                        on {COMPANY} constitutes financial, investment, or trading advice. Cryptocurrency
                        trading involves substantial risk of loss. You are solely responsible for all trading
                        decisions and their outcomes.
                    </p>
                </section>

                <section style={s.section}>
                    <h2 style={s.h2}>4. Eligibility</h2>
                    <p style={s.p}>
                        You must be at least 18 years old and legally permitted to trade cryptocurrency in
                        your jurisdiction. By using the Service you confirm this.
                    </p>
                </section>

                <section style={s.section}>
                    <h2 style={s.h2}>5. API Keys &amp; Security</h2>
                    <p style={s.p}>
                        Your exchange API keys are encrypted at rest using AES-256 (Fernet) and are never
                        transmitted to third parties. You are responsible for using restricted API keys
                        (no withdrawal permissions). {COMPANY} is not liable for losses caused by
                        misconfigured or compromised API keys.
                    </p>
                </section>

                <section style={s.section}>
                    <h2 style={s.h2}>6. Subscriptions &amp; Billing</h2>
                    <p style={s.p}>
                        Paid plans are billed monthly via Stripe. You may cancel at any time; access continues
                        until the end of your billing period. Refunds are not provided for partial months.
                        We reserve the right to change pricing with 30 days notice.
                    </p>
                </section>

                <section style={s.section}>
                    <h2 style={s.h2}>7. Prohibited Use</h2>
                    <p style={s.p}>You may not: (a) use the Service for market manipulation; (b) reverse-engineer
                        or resell the Service; (c) circumvent rate limits or security measures; (d) use the
                        Service in jurisdictions where crypto trading is prohibited.</p>
                </section>

                <section style={s.section}>
                    <h2 style={s.h2}>8. Disclaimer of Warranties</h2>
                    <p style={s.p}>
                        THE SERVICE IS PROVIDED "AS IS" WITHOUT WARRANTY OF ANY KIND. WE DO NOT GUARANTEE
                        UPTIME, ACCURACY OF AI SIGNALS, OR PROFITABLE TRADING OUTCOMES.
                    </p>
                </section>

                <section style={s.section}>
                    <h2 style={s.h2}>9. Limitation of Liability</h2>
                    <p style={s.p}>
                        TO THE MAXIMUM EXTENT PERMITTED BY LAW, {COMPANY.toUpperCase()} SHALL NOT BE LIABLE
                        FOR ANY TRADING LOSSES, INDIRECT, INCIDENTAL, OR CONSEQUENTIAL DAMAGES ARISING FROM
                        USE OF THE SERVICE.
                    </p>
                </section>

                <section style={s.section}>
                    <h2 style={s.h2}>10. Termination</h2>
                    <p style={s.p}>
                        We may suspend or terminate accounts that violate these Terms. You may delete your
                        account at any time from the Settings page.
                    </p>
                </section>

                <section style={s.section}>
                    <h2 style={s.h2}>11. Contact</h2>
                    <p style={s.p}>Questions? Email <a href={`mailto:${CONTACT_EMAIL}`} style={s.link}>{CONTACT_EMAIL}</a></p>
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
        fontFamily: "'Montserrat', sans-serif",
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
        fontFamily: "'Montserrat', sans-serif",
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
