import { useRef, useState, useEffect, memo } from "react";
import TradingViewChart from "../TradingViewChart.jsx";
import AnimatedNumber from "../AnimatedNumber.jsx";
import { Search, Zap } from "lucide-react";

const BACKEND_BASE = import.meta.env.VITE_BACKEND_URL
  || (import.meta.env.DEV ? "http://localhost:8000" : "");
const API_SECRET = import.meta.env.DEV ? (import.meta.env.VITE_BOT_API_SECRET || "") : "";

export const ChartSection = memo(function ChartSection({
  chartSymbol, setChartSymbol, selectedCoin, positions, price,
  marketTickers, multiExchangePrices, setMultiExchangePrices,
}) {
  const [tickerSearch, setTickerSearch] = useState("");
  const [tickerSearchOpen, setTickerSearchOpen] = useState(false);
  const tickerSearchRef = useRef(null);

  useEffect(() => {
    if (!tickerSearchOpen) return;
    const handler = (e) => {
      if (tickerSearchRef.current && !tickerSearchRef.current.contains(e.target)) setTickerSearchOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [tickerSearchOpen]);

  useEffect(() => {
    if (!tickerSearchOpen) return;
    const q = tickerSearch.trim().toUpperCase();
    const matches = q
      ? marketTickers.filter(t => (t.sym || "").toUpperCase().includes(q)).slice(0, 8)
      : marketTickers.slice(0, 6);
    let syms = [...new Set(matches.map(t => (t.sym || "").toUpperCase()).filter(Boolean))];
    if (q && !syms.includes(q)) syms.push(q);
    if (syms.length === 0) syms = ["BTC", "ETH", "SOL", "XRP", "DOGE"];
    const base = (BACKEND_BASE || "").replace(/\/$/, "");
    const url = base ? `${base}/api/prices/multi` : "/api/prices/multi";
    const headers = {};
    if (API_SECRET) headers["x-bot-secret"] = API_SECRET;
    fetch(`${url}?symbols=${encodeURIComponent(syms.join(","))}`, { headers })
      .then(r => r.ok && r.json())
      .then(d => d && typeof d === "object" && setMultiExchangePrices(d))
      .catch(() => { });
  }, [tickerSearchOpen, tickerSearch, marketTickers, setMultiExchangePrices]);

  return (
    <div className="card chart-card" style={{ height: "65vh", minHeight: "500px", maxHeight: "700px", display: "flex", flexDirection: "column", padding: "12px", position: "relative", zIndex: 1, overflow: "hidden" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "10px", padding: "0 4px", flexWrap: "wrap", gap: "10px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "10px", flexWrap: "wrap" }}>
          <span style={{ fontFamily: "'Montserrat', sans-serif", fontSize: "14px", color: "#D4D4D4", fontWeight: "800", letterSpacing: "3px" }}>
            {chartSymbol.includes(":")
              ? (() => { const [, pair] = chartSymbol.split(":"); const base = (pair || "").replace(/USDT?$/i, ""); return `${base} / ${(pair || "").includes("USDT") ? "USDT" : "USD"}`; })()
              : `${chartSymbol} / USD`}
          </span>
          <span style={{ fontSize: "9px", color: "#5C5C5C", letterSpacing: "1px" }}>TRADINGVIEW PRO</span>
          {/* Ticker search */}
          <div ref={tickerSearchRef} style={{ position: "relative" }}>
            <div style={{ display: "flex", alignItems: "center", background: "#111111", border: "1px solid #1e1e1e", borderRadius: "6px", padding: "2px 8px", gap: "6px" }}>
              <Search size={10} color="#5C5C5C" />
              <input
                type="text"
                placeholder="Search ticker..."
                value={tickerSearch}
                onChange={(e) => { setTickerSearch(e.target.value); setTickerSearchOpen(true); }}
                onFocus={() => setTickerSearchOpen(true)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    const q = tickerSearch.trim().toUpperCase();
                    if (q.includes(":")) setChartSymbol(q);
                    else if (q) setChartSymbol(`BINANCE:${q}USDT`);
                    setTickerSearchOpen(false);
                    setTickerSearch("");
                  } else if (e.key === "Escape") { setTickerSearchOpen(false); setTickerSearch(""); }
                }}
                style={{ width: "140px", fontFamily: "'Space Mono',monospace", fontSize: "11px", background: "transparent", border: "none", color: "#D4D4D4", outline: "none" }}
              />
            </div>
            {tickerSearchOpen && (
              <div
                style={{
                  position: "absolute", top: "100%", left: 0, marginTop: "4px", minWidth: "min(300px, calc(100vw - 32px))", maxHeight: "320px", overflowY: "auto",
                  background: "#111111", border: "1px solid #1a1f2e", borderRadius: "6px", boxShadow: "0 8px 24px rgba(0,0,0,0.4)", zIndex: 100,
                }}
              >
                {(() => {
                  const q = tickerSearch.trim().toUpperCase();
                  const matches = q
                    ? marketTickers.filter(t => (t.sym || "").toUpperCase().includes(q)).slice(0, 8)
                    : marketTickers.slice(0, 6);
                  const opts = [];
                  for (const t of matches) {
                    const sym = (t.sym || "").toUpperCase();
                    if (!sym) continue;
                    // Spot
                    opts.push({ label: `${sym} — Binance Spot`, symbol: `BINANCE:${sym}USDT`, exchange: "binance", type: "spot", sym });
                    opts.push({ label: `${sym} — Coinbase Spot`, symbol: `COINBASE:${sym}USD`, exchange: "coinbase", type: "spot", sym });
                    opts.push({ label: `${sym} — Kraken Spot`, symbol: `KRAKEN:${sym}USD`, exchange: "kraken", type: "spot", sym });
                    // Futures / Perps
                    opts.push({ label: `${sym} — Binance Perp`, symbol: `BINANCE:${sym}USDT.P`, exchange: "binance", type: "futures", sym });
                    opts.push({ label: `${sym} — Coinbase Fut`, symbol: `COINBASE:${sym}USD_PERP`, exchange: "coinbase", type: "futures", sym });
                    opts.push({ label: `${sym} — Kraken Fut`, symbol: `KRAKEN:PF_${sym}USD`, exchange: "kraken", type: "futures", sym });
                  }
                  if (q && !matches.some(t => (t.sym || "").toUpperCase() === q)) {
                    opts.push({ label: `${q} — Binance Spot`, symbol: `BINANCE:${q}USDT`, exchange: "binance", type: "spot", sym: q });
                    opts.push({ label: `${q} — Coinbase Spot`, symbol: `COINBASE:${q}USD`, exchange: "coinbase", type: "spot", sym: q });
                    opts.push({ label: `${q} — Kraken Spot`, symbol: `KRAKEN:${q}USD`, exchange: "kraken", type: "spot", sym: q });
                    opts.push({ label: `${q} — Binance Perp`, symbol: `BINANCE:${q}USDT.P`, exchange: "binance", type: "futures", sym: q });
                    opts.push({ label: `${q} — Coinbase Fut`, symbol: `COINBASE:${q}USD_PERP`, exchange: "coinbase", type: "futures", sym: q });
                    opts.push({ label: `${q} — Kraken Fut`, symbol: `KRAKEN:PF_${q}USD`, exchange: "kraken", type: "futures", sym: q });
                  }
                  if (opts.length === 0) {
                    for (const sym of ["BTC", "ETH", "SOL", "XRP", "DOGE"]) {
                      opts.push({ label: `${sym} — Binance Spot`, symbol: `BINANCE:${sym}USDT`, exchange: "binance", type: "spot", sym });
                      opts.push({ label: `${sym} — Coinbase Spot`, symbol: `COINBASE:${sym}USD`, exchange: "coinbase", type: "spot", sym });
                      opts.push({ label: `${sym} — Kraken Spot`, symbol: `KRAKEN:${sym}USD`, exchange: "kraken", type: "spot", sym });
                      opts.push({ label: <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>{sym} — Binance Perp <Zap size={10} fill="currentColor" /></span>, symbol: `BINANCE:${sym}USDT.P`, exchange: "binance", type: "futures", sym });
                      opts.push({ label: <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>{sym} — Coinbase Fut <Zap size={10} fill="currentColor" /></span>, symbol: `COINBASE:${sym}USD_PERP`, exchange: "coinbase", type: "futures", sym });
                      opts.push({ label: <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>{sym} — Kraken Fut <Zap size={10} fill="currentColor" /></span>, symbol: `KRAKEN:PF_${sym}USD`, exchange: "kraken", type: "futures", sym });
                    }
                  }
                  return opts;
                })().map((opt) => {
                  const px = multiExchangePrices[opt.sym]?.[opt.exchange];
                  const priceStr = px != null && px > 0
                    ? (px < 0.0001 ? px.toFixed(8) : px < 0.01 ? px.toFixed(6) : px < 10 ? px.toFixed(4) : px < 1000 ? px.toFixed(2) : px.toLocaleString())
                    : null;
                  return (
                    <button
                      key={opt.symbol}
                      type="button"
                      onClick={() => { setChartSymbol(opt.symbol); setTickerSearch(""); setTickerSearchOpen(false); }}
                      style={{
                        display: "flex", width: "100%", justifyContent: "space-between", alignItems: "center", padding: "7px 12px",
                        fontFamily: "'Space Mono',monospace", fontSize: "10px", border: "none",
                        background: opt.type === "futures" ? "rgba(212,175,55,0.03)" : "transparent",
                        borderLeft: opt.type === "futures" ? "2px solid rgba(212,175,55,0.2)" : "2px solid transparent",
                        color: "#D4D4D4", cursor: "pointer", whiteSpace: "nowrap", gap: "12px",
                      }}
                      onMouseEnter={(e) => { e.currentTarget.style.background = "#1e1e1e"; e.currentTarget.style.color = "#fff"; }}
                      onMouseLeave={(e) => { e.currentTarget.style.background = opt.type === "futures" ? "rgba(212,175,55,0.03)" : "transparent"; e.currentTarget.style.color = "#D4D4D4"; }}
                    >
                      <span style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                        <span style={{
                          fontSize: "7px", fontWeight: "800", padding: "1px 4px", borderRadius: "3px",
                          background: opt.type === "futures" ? "rgba(212,175,55,0.15)" : "rgba(0,230,118,0.1)",
                          color: opt.type === "futures" ? "#D4AF37" : "#00E676",
                        }}>
                          {opt.type === "futures" ? "PERP" : "SPOT"}
                        </span>
                        {opt.label}
                      </span>
                      <span style={{ color: priceStr ? "#D4AF37" : "#5C5C5C", fontSize: "11px", fontWeight: priceStr ? "700" : "400" }}>
                        {priceStr != null ? `$${priceStr}` : "—"}
                      </span>
                    </button>
                  );
                })}
                {tickerSearch && (
                  <div style={{ padding: "6px 12px", fontSize: "9px", color: "#5C5C5C", borderTop: "1px solid #1e1e1e" }}>
                    Spot &amp; Futures/Perps on Binance, Coinbase &amp; Kraken
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
        {positions.length > 0 && (
          <div style={{ display: "flex", gap: "10px", fontSize: "9px", alignItems: "center", flexWrap: "wrap" }}>
            {positions.filter(p => p.symbol === selectedCoin).map(pos => (
              <div key={pos.id} style={{ display: "flex", gap: "8px", padding: "2px 6px", borderRadius: "3px", background: pos.side === "buy" ? "#00E67608" : "#FF174408" }}>
                <span style={{ color: pos.side === "buy" ? "#00E676" : "#FF1744", fontWeight: "700" }}>{pos.side?.toUpperCase()}</span>
                <span style={{ color: "#D4AF37" }}>E $<AnimatedNumber value={pos.entry || 0} format={(v) => v.toLocaleString()} duration={150} /></span>
                <span style={{ color: "#00E676" }}>TP $<AnimatedNumber value={pos.tp || 0} format={(v) => v.toLocaleString()} duration={150} /></span>
                <span style={{ color: "#FF1744" }}>SL $<AnimatedNumber value={pos.sl || 0} format={(v) => v.toLocaleString()} duration={150} /></span>
              </div>
            ))}
          </div>
        )}
      </div>
      <div style={{ flex: 1, minHeight: 0 }}>
        <TradingViewChart symbol={chartSymbol} />
      </div>
    </div>
  );
});
