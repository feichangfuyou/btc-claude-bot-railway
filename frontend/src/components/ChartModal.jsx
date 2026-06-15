import { X } from "lucide-react";
import TradingViewChart from "../TradingViewChart.jsx";
import { popIn } from "../animations.js";

const LABEL_MAP = {
  "BINANCE:": (pair) => {
    const base = (pair || "").replace(/USDT?\.?P?$/i, "");
    return `${base} / USDT`;
  },
  "COINBASE:": (pair) => {
    const base = (pair || "").replace(/USD(_PERP)?$/i, "");
    return `${base} / USD`;
  },
  "KRAKEN:": (pair) => {
    const base = (pair || "").replace(/USD$/i, "").replace(/^PF_/, "");
    return `${base} / USD`;
  },
};

function getChartLabel(symbol) {
  if (!symbol || typeof symbol !== "string") return "Chart";
  const s = symbol.trim().toUpperCase();
  if (s.includes(":")) {
    const [, pair] = s.split(":", 2);
    for (const [prefix, fn] of Object.entries(LABEL_MAP)) {
      if (s.startsWith(prefix)) return fn(pair);
    }
    return pair || s;
  }
  return `${s} / USD`;
}

export function ChartModal({ symbol, title, onClose }) {
  if (!symbol) return null;

  const label = title || getChartLabel(symbol);

  return (
    <div
      className="glass-overlay fadein"
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 9999,
        display: "flex",
        flexDirection: "column",
        overflow: "auto",
        padding: "env(safe-area-inset-top) env(safe-area-inset-right) env(safe-area-inset-bottom) env(safe-area-inset-left)",
      }}
      onClick={onClose}
    >
      <div
        className="glass-heavy"
        style={{
          maxWidth: "min(1400px, calc(100vw - 24px))",
          width: "100%",
          margin: "12px auto",
          padding: "20px",
          boxSizing: "border-box",
          flex: 1,
          display: "flex",
          flexDirection: "column",
          minHeight: 0,
          position: "relative",
          animation: "fadein 0.35s ease",
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <button
          type="button"
          onClick={onClose}
          className="btn btn-r btn-icon"
          style={{
            position: "absolute",
            top: "20px",
            right: "20px",
            zIndex: 10000,
          }}
          title="Close Chart"
        >
          <X size={18} />
        </button>
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            marginBottom: "16px",
          }}
        >
          <span
            className="section-label"
            style={{
              fontSize: "18px",
              color: "#D4AF37",
              letterSpacing: "3px",
            }}
          >
            {label}
          </span>
        </div>
        <div
          style={{
            flex: 1,
            minHeight: "70vh",
            background: "rgba(6,6,6,0.7)",
            borderRadius: "12px",
            border: "1px solid rgba(255,255,255,0.04)",
            boxShadow: "inset 0 2px 6px rgba(0,0,0,0.35), 0 1px 0 rgba(255,255,255,0.03)",
            overflow: "hidden",
            position: "relative",
          }}
        >
          <TradingViewChart symbol={symbol} />
        </div>
      </div>
    </div>
  );
}
