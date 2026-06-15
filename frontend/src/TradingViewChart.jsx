import { useEffect, useRef, memo } from "react";
import { colors } from "./theme.js";

// Coinbase symbols — same exchange as our price feed, so header price matches chart
const SYMBOL_MAP = {
  BTC:  "COINBASE:BTCUSD",
  ETH:  "COINBASE:ETHUSD",
  SOL:  "COINBASE:SOLUSD",
  DOGE: "COINBASE:DOGEUSD",
  LINK: "COINBASE:LINKUSD",
  AVAX: "COINBASE:AVAXUSD",
  UNI:  "COINBASE:UNIUSD",
  AAVE: "COINBASE:AAVEUSD",
  POL:  "COINBASE:MATICUSD",  // Polygon (MATIC)
  MATIC:"COINBASE:MATICUSD",
};

/** Resolve symbol for TradingView. Accepts:
 * - Full format: "BINANCE:BTCUSDT", "COINBASE:ETHUSD", "KRAKEN:XBTUSD"
 * - Short format: "BTC", "ETH" → maps to COINBASE:XUSD
 */
const VALID_SYMBOLS = new Set(Object.keys(SYMBOL_MAP));

/** Sanitize symbol for TradingView. Whitelist prevents XSS via malicious symbol prop. */
function getSymbol(symbol) {
  if (!symbol || typeof symbol !== "string") return "COINBASE:BTCUSD";
  const s = symbol.trim().toUpperCase();
  if (s.includes(":")) {
    const [ex, sym] = s.split(":", 2);
    if (/^[A-Z0-9]{1,20}$/.test(ex || "") && /^[A-Z0-9]{1,20}$/.test(sym || "")) {
      return `${ex}:${sym}`;
    }
    return "COINBASE:BTCUSD";
  }
  return VALID_SYMBOLS.has(s) ? (SYMBOL_MAP[s] || `COINBASE:${s}USD`) : "COINBASE:BTCUSD";
}

function TradingViewChart({ symbol = "BTC", minimal = false }) {
  const containerRef = useRef(null);

  useEffect(() => {
    if (!containerRef.current) return;
    const container = containerRef.current;
    container.innerHTML = "";

    let timeoutId = null;
    const rafId = requestAnimationFrame(() => {
      timeoutId = setTimeout(() => {
        if (!container.isConnected) return;

        const clean = minimal;

        const script = document.createElement("script");
        script.src = "https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js";
        script.type = "text/javascript";
        script.async = true;
        script.innerHTML = JSON.stringify({
          symbol: getSymbol(symbol),
          interval: "5",
          timezone: "Etc/UTC",
          theme: "dark",
          style: "1",
          locale: "en",
          backgroundColor: "rgba(10, 10, 10, 1)",
          gridColor: "rgba(30, 30, 30, 0.3)",
          allow_symbol_change: !clean,
          withdateranges: true,
          hide_side_toolbar: clean,
          hide_top_toolbar: false,
          hide_legend: clean,
          details: !clean,
          hotlist: !clean,
          calendar: false,
          hide_volume: clean,
          support_host: "https://www.tradingview.com",
          studies: clean ? [] : [
            "STD;EMA",
            "STD;RSI",
            "STD;MACD",
            "STD;Bollinger_Bands",
            "STD;VWAP",
          ],
          show_popup_button: !clean,
          popup_width: "1400",
          popup_height: "900",
          width: "100%",
          height: "100%",
          save_image: !clean,
          enable_publishing: false,
          overrides: {
            "paneProperties.backgroundType": "solid",
            "paneProperties.background": "rgba(10, 10, 10, 1)",
            "paneProperties.vertGridProperties.color": "rgba(30, 30, 30, 0.3)",
            "paneProperties.horzGridProperties.color": "rgba(30, 30, 30, 0.3)",
            "mainSeriesProperties.candleStyle.upColor": colors.gold,
            "mainSeriesProperties.candleStyle.downColor": colors.error,
            "mainSeriesProperties.candleStyle.borderUpColor": colors.gold,
            "mainSeriesProperties.candleStyle.borderDownColor": colors.error,
            "mainSeriesProperties.candleStyle.wickUpColor": colors.gold,
            "mainSeriesProperties.candleStyle.wickDownColor": colors.error,
          },
        });

        const widgetDiv = document.createElement("div");
        widgetDiv.className = "tradingview-widget-container";
        widgetDiv.style.width = "100%";
        widgetDiv.style.height = "100%";

        const inner = document.createElement("div");
        inner.className = "tradingview-widget-container__widget";
        inner.style.width = "100%";
        inner.style.height = "100%";

        widgetDiv.appendChild(inner);
        widgetDiv.appendChild(script);
        container.appendChild(widgetDiv);
      }, 50);
    });

    return () => {
      cancelAnimationFrame(rafId);
      if (timeoutId) clearTimeout(timeoutId);
    };
  }, [symbol, minimal]);

  return (
    <div
      ref={containerRef}
      style={{ width: "100%", height: "100%", position: "absolute", inset: 0 }}
    />
  );
}

export default memo(TradingViewChart);
