import { useEffect, useRef, memo } from "react";
import { animate } from "animejs";
import { colors } from "./theme.js";
import { CheckCircle2 } from "lucide-react";

function formatPrice(p) {
  if (!p || p <= 0) return "\u2014";
  if (p < 0.0001) return p.toFixed(8);
  if (p < 0.01) return p.toFixed(6);
  if (p < 10) return p.toFixed(4);
  if (p < 1000) return p.toFixed(2);
  return p.toLocaleString(undefined, { maximumFractionDigits: 0 });
}

function TickerItem({
  sym,
  coinPrice,
  chg24h,
  logoUrl,
  isSelected,
  hasPosition,
  onClick,
  onImgError,
  imgDataSym,
}) {
  const priceElRef = useRef(null);
  const prevPriceRef = useRef(coinPrice);
  const chgElRef = useRef(null);
  const prevChg24hRef = useRef(chg24h);

  useEffect(() => {
    const el = priceElRef.current;
    if (!el) return;
    el.textContent = "$" + formatPrice(coinPrice);

    const prev = prevPriceRef.current;
    prevPriceRef.current = coinPrice;
    if (!prev || !coinPrice || prev === coinPrice) return;

    const color = coinPrice > prev ? colors.gold : colors.error;
    const glow = coinPrice > prev ? `0 0 8px ${colors.gold}66` : `0 0 8px ${colors.error}66`;
    animate(el, {
      color: [color, "#D4D4D4"],
      textShadow: [glow, "0 0 0px transparent"],
      duration: 600,
      ease: "out",
    });
  }, [coinPrice]);

  useEffect(() => {
    const el = chgElRef.current;
    if (!el) return;

    const pct = chg24h ?? 0;
    const isUp = pct > 0;
    const isDown = pct < 0;
    const arrow = isUp ? "\u25B2" : isDown ? "\u25BC" : "";
    const color = isUp ? colors.success : isDown ? colors.error : colors.muted;

    el.textContent = pct !== 0 ? `${arrow} ${Math.abs(pct).toFixed(2)}%` : "";
    el.style.color = color;

    const prev = prevChg24hRef.current ?? 0;
    prevChg24hRef.current = pct;
    if (prev !== 0 && pct !== 0 && Math.sign(prev) !== Math.sign(pct)) {
      animate(el, {
        opacity: [1, 0.85],
        duration: 400,
        ease: "out",
        onComplete: () => { el.style.opacity = "0.85"; },
      });
    }
  }, [chg24h]);

  return (
    <button
      className={`coin-btn ticker-text ${isSelected ? "selected" : ""}`}
      onClick={onClick}
      style={{
        cursor: "pointer",
        border: isSelected
          ? `1px solid ${colors.gold}55`
          : hasPosition
            ? `1px solid ${colors.success}33`
            : "1px solid transparent",
        background: isSelected ? "rgba(212,175,55,0.08)" : "transparent",
        color: isSelected ? "#fff" : colors.text,
        borderBottom: isSelected ? `2px solid ${colors.gold}` : "none",
        boxShadow: isSelected
          ? "0 4px 16px rgba(0,0,0,0.3), inset 0 1px 0 rgba(255,255,255,0.10), inset 0 -1px 0 rgba(0,0,0,0.12), 0 0 12px rgba(212,175,55,0.06)"
          : "none",
        backdropFilter: isSelected ? "blur(12px) saturate(1.3)" : "none",
        WebkitBackdropFilter: isSelected ? "blur(12px) saturate(1.3)" : "none",
        transition: "border-color 0.3s, background 0.3s, color 0.15s, box-shadow 0.35s",
        position: "relative",
        whiteSpace: "nowrap",
      }}
    >
      <img
        src={logoUrl}
        alt=""
        width={18}
        height={18}
        data-sym={imgDataSym || sym}
        style={{ borderRadius: "50%", objectFit: "cover", flexShrink: 0 }}
        onError={onImgError}
      />
      <span style={{ letterSpacing: "1.5px" }}>{sym}</span>
      <span
        ref={priceElRef}
        style={{ color: coinPrice > 0 ? colors.text : colors.muted }}
      >
        {"$" + formatPrice(coinPrice)}
      </span>
      <span
        ref={chgElRef}
        className="ticker-chg"
        style={{
          fontSize: "10px",
          fontWeight: 600,
          opacity: 0.85,
          color: colors.muted,
          minWidth: "52px",
          flexShrink: 0,
        }}
      />
      {hasPosition && (
        <span
          className="ticker-open-label"
          style={{ fontSize: "8px", color: colors.gold, marginLeft: "2px", display: "flex", alignItems: "center", gap: "2px" }}
        >
          <CheckCircle2 size={10} /> OPEN
        </span>
      )}
    </button>
  );
}

export default memo(TickerItem, (prev, next) => {
  return (
    prev.coinPrice === next.coinPrice &&
    prev.chg24h === next.chg24h &&
    prev.isSelected === next.isSelected &&
    prev.hasPosition === next.hasPosition &&
    prev.logoUrl === next.logoUrl
  );
});
