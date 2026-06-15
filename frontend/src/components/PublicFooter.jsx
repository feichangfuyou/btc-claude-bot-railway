import { Link } from "react-router-dom";
import { colors } from "../theme.js";

const MARKET_LINKS = [
  { key: "btc", label: "BTC/USD Intelligence" },
  { key: "eth", label: "ETH/USD Strategy" },
  { key: "sol", label: "SOL/USD Execution" },
  { key: "altcoins", label: "Altcoin Execution Engine" },
];

export function PublicFooter({ compact = false }) {
  return (
    <footer className={`public-footer${compact ? " public-footer--compact" : ""}`}>
      {!compact && (
        <div className="public-footer__markets">
          {MARKET_LINKS.map(({ key, label }) => (
            <Link key={key} to={`/market/${key}`} className="public-footer__market-link">
              {label}
            </Link>
          ))}
        </div>
      )}
      <div className="public-footer__links">
        <Link to="/">Home</Link>
        <Link to="/terms">Terms</Link>
        <Link to="/privacy">Privacy</Link>
        <a href="mailto:feichangfuyou@doyou.trade" style={{ color: colors.gold }}>
          Contact
        </a>
      </div>
      <div className="public-footer__copy">© 2026 DOYOU.TRADE. ALL RIGHTS RESERVED.</div>
    </footer>
  );
}
