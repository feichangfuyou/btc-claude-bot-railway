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
          <button
            type="button"
            className="btn btn-d"
            onClick={onClose}
            style={{
              display: "flex",
              alignItems: "center",
              gap: "6px",
              fontSize: "12px",
              color: "#FF1744",
              borderColor: "#FF174433",
              padding: "6px 14px",
            }}
          >
            <X size={14} /> CLOSE
          </button>
        </div>
        <div
          style={{
            flex: 1,
            minHeight: "70vh",
            background: "#0a0a0a",
            borderRadius: "8px",
            border: "1px solid #1e1e1e",
            overflow: "hidden",
          }}
        >
          <TradingViewChart symbol={symbol} />
        </div>
      </div>
    </div>
  );
}
