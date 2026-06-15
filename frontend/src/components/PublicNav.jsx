import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowRight } from "lucide-react";
import { useLiquidSpecular } from "../hooks/useLiquidSpecular.js";

/**
 * Sticky public nav — matches MarketIndex redesign.
 * variant: "marketing" (login/signup CTAs) | "app" (dashboard link for authed pages)
 */
export function PublicNav({ variant = "marketing" }) {
  const [scrolled, setScrolled] = useState(false);
  const { glareRef, specularRef, glareStyle, specularStyle, onMouseMove, onMouseLeave } =
    useLiquidSpecular();

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 20);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <div className="public-nav-shell">
      <nav
        className={`public-nav${scrolled ? " public-nav--scrolled" : ""}`}
        aria-label="Site navigation"
        onMouseMove={onMouseMove}
        onMouseLeave={onMouseLeave}
      >
        <div ref={specularRef} aria-hidden className="public-nav__specular" style={specularStyle} />
        <div ref={glareRef} aria-hidden className="public-nav__glare" style={glareStyle} />
        <div className="public-nav__caustic" aria-hidden />

        <div className="public-nav__inner">
          <Link
            to={variant === "app" ? "/dashboard" : "/"}
            className="public-nav__brand"
          >
            <span className="public-nav__logo-wrap">
              <img src="/Bravo.svg" alt="" className="public-nav__logo" />
            </span>
            <span className="public-nav__brand-text">
              <span className="public-nav__title">DOYOU.TRADE</span>
              <span className="public-nav__subtitle">Institutional-grade automation</span>
            </span>
          </Link>

          {variant === "marketing" && (
            <div className="public-nav__links" aria-label="Primary">
              <Link to="/market/btc" className="public-nav__navlink">Markets</Link>
              <Link to="/terms" className="public-nav__navlink">Legal</Link>
            </div>
          )}

          <div className="public-nav__actions">
            {variant === "marketing" ? (
              <>
                <Link to="/login" className="public-nav__link">Sign in</Link>
                <Link to="/signup" className="public-nav__cta">
                  Get started <ArrowRight size={13} strokeWidth={2.5} aria-hidden />
                </Link>
              </>
            ) : (
              <Link to="/dashboard" className="public-nav__cta public-nav__cta--ghost">
                Terminal <ArrowRight size={13} strokeWidth={2.5} aria-hidden />
              </Link>
            )}
          </div>
        </div>

        <div className="public-nav__accent" aria-hidden />
      </nav>
    </div>
  );
}
