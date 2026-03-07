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
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(6,6,15,0.97)",
        zIndex: 9999,
        display: "flex",
        flexDirection: "column",
        animation: "fadein 0.2s ease",
        overflow: "auto",
      }}
      onClick={onClose}
    >
      <div
        style={{
          maxWidth: "min(1400px, calc(100vw - 24px))",
          width: "100%",
          margin: "max(12px, env(safe-area-inset-top)) auto 20px",
          padding: "0 clamp(12px, 4vw, 20px)",
          boxSizing: "border-box",
          flex: 1,
          display: "flex",
          flexDirection: "column",
          minHeight: 0,
        }}
        ref={popIn}
        onClick={(e) => e.stopPropagation()}
      >
        <button
          type="button"
          onClick={onClose}
          style={{
            position: "absolute",
            top: "16px",
            right: "16px",
            background: "rgba(0,0,0,0.7)",
            border: "1px solid rgba(255, 23, 68, 0.4)",
            color: "#FF1744",
            borderRadius: "50%",
            width: "40px",
            height: "40px",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            cursor: "pointer",
            zIndex: 10000,
            boxShadow: "0 4px 12px rgba(0,0,0,0.5)",
          }}
          title="Close Chart"
        >
          <X size={24} />
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
            style={{
              fontFamily: "'Montserrat', sans-serif",
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
            background: "#0a0a0a",
            borderRadius: "8px",
            border: "1px solid #1e1e1e",
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
