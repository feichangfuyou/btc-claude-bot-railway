import { PublicNav } from "./PublicNav.jsx";
import { PublicFooter } from "./PublicFooter.jsx";
import { ArrowLeft } from "lucide-react";

/**
 * Unified page wrapper for secondary app pages (settings, billing, history, etc.)
 * Matches MarketIndex visual language: #050505 bg, sticky nav, glass cards.
 */
export function PageShell({
  children,
  title,
  onBack,
  backLabel = "Dashboard",
  headerRight,
  maxWidth = 800,
  centered = false,
  showFooter = false,
  className = "",
}) {
  return (
    <div className={`page-shell${centered ? " page-shell--centered" : ""} ${className}`.trim()}>
      <PublicNav variant="app" />
      <div
        className="page-shell__inner"
        style={{ maxWidth: typeof maxWidth === "number" ? `${maxWidth}px` : maxWidth }}
      >
        {(title || onBack) && (
          <header className="page-shell__header">
            <div className="page-shell__header-left">
              {onBack && (
                <button type="button" className="page-shell__back" onClick={onBack}>
                  <ArrowLeft size={14} />
                  {backLabel}
                </button>
              )}
              {title && <h1 className="page-shell__title">{title}</h1>}
            </div>
            {headerRight && <div className="page-shell__header-right">{headerRight}</div>}
          </header>
        )}
        {children}
      </div>
      {showFooter && <PublicFooter compact />}
    </div>
  );
}
