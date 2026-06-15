import AnimatedNumber from "../AnimatedNumber.jsx";
import { Circle, Link, X, ArrowUp, ArrowDown } from "lucide-react";

export function PositionsPanel({
  positions, coins, price, enableFutures, maxPositions, maxFuturesPositions,
  unrealized, botOn, handleClose,
}) {
  if (positions.length === 0) {
    return (
      <div className="card" style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: "8px", textAlign: "center", padding: "16px", color: "#3a3a3a", fontSize: "11px", letterSpacing: "1.5px", position: "relative", zIndex: 2 }}>
        <Circle size={10} /> NO OPEN POSITIONS — {botOn ? `Scanning (0/${enableFutures ? maxPositions + maxFuturesPositions : maxPositions} slots)...` : "Start bot to begin"}
      </div>
    );
  }

  return (
    <div style={{ position: "relative", zIndex: 2 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "8px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
          <span style={{ fontSize: "9px", color: "#3a3a3a", letterSpacing: "2px" }}>
            OPEN POSITIONS ({positions.length}/{enableFutures ? maxPositions + maxFuturesPositions : maxPositions})
          </span>
          {unrealized !== 0 && (
            <span style={{ fontSize: "10px", fontWeight: "700", color: unrealized >= 0 ? "#00E676" : "#FF1744" }}>
              Total: <AnimatedNumber value={unrealized} format={(v) => `${v >= 0 ? "+" : ""}$${v.toFixed(2)}`} duration={180} />
            </span>
          )}
        </div>
        {positions.length > 1 && (
          <button className="btn btn-d" onClick={() => handleClose()} style={{ color: "#ff9900", borderColor: "#ff990033" }}>CLOSE ALL</button>
        )}
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
        {positions.map(pos => {
          const cp = coins[pos.symbol]?.price || price;
          const sz = pos.coin_size || pos.btc_size || 0;
          const posUnrealized = +((pos.side === "buy" ? cp - pos.entry : pos.entry - cp) * sz).toFixed(2);
          const range = Math.abs(pos.tp - pos.sl);
          let progress = 50;
          if (range > 0) {
            progress = pos.side === "buy"
              ? ((cp - pos.sl) / range) * 100
              : ((pos.sl - cp) / range) * 100;
            progress = Math.max(0, Math.min(100, progress));
          }
          return (
            <div key={pos.id || pos.symbol} className="card fadein" style={{ border: `1px solid ${pos.side === "buy" ? "#00E67622" : "#FF174422"}` }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "10px" }}>
                <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
                  <span className="dot pulse" style={{ background: pos.side === "buy" ? "#00E676" : "#FF1744" }} />
                  <span style={{ display: "flex", alignItems: "center", gap: "6px", fontFamily: "'Montserrat', sans-serif", fontSize: "11px", color: pos.side === "buy" ? "#00E676" : "#FF1744", fontWeight: "700", letterSpacing: "2px" }}>
                    {pos.onchain && <Link size={12} />}
                    {pos.side === "buy" ? <ArrowUp size={12} /> : <ArrowDown size={12} />}
                    {pos.side?.toUpperCase()} {pos.symbol || "BTC"}
                  </span>
                  {pos.onchain && <span className="tag" style={{ background: "#D4AF3718", color: "#D4AF37", fontSize: "9px" }}>ON-CHAIN</span>}
                  {pos.product_type === "futures" && <span className="tag" style={{ background: "#D4AF3718", color: "#D4AF37", fontSize: "9px" }}>FUTURES{pos.leverage ? ` ${pos.leverage}x` : ""}</span>}
                  {pos.exchange === "kraken" && <span className="tag" style={{ background: "#7b61ff18", color: "#7b61ff", fontSize: "9px" }}>KRAKEN</span>}
                  {pos.exchange === "coinbase" && <span className="tag" style={{ background: "#0052ff18", color: "#4d8ffa", fontSize: "9px" }}>COINBASE</span>}
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
                  <span style={{ fontSize: "9px", color: "#3a3a3a" }}>since {pos.open_ts}</span>
                  <button className="btn btn-d btn-icon" onClick={() => handleClose(pos)} style={{ color: "#ff9900", borderColor: "#ff990033" }} aria-label="Close position"><X size={12} /></button>
                </div>
              </div>
              <div className="pos-grid" style={{ display: "grid", gridTemplateColumns: "repeat(5,1fr)", gap: "8px" }}>
                {[
                  { label: "ENTRY", num: pos.entry || 0, fmt: (v) => `$${v.toLocaleString()}`, color: "#D4D4D4" },
                  { label: "TAKE PROFIT", num: pos.tp || 0, fmt: (v) => `$${v.toLocaleString()}`, color: "#00E676" },
                  { label: "STOP LOSS", num: pos.sl || 0, fmt: (v) => `$${v.toLocaleString()}`, color: "#FF1744" },
                  { label: "SIZE", num: pos.usd_size || 0, fmt: (v) => `$${v.toFixed(2)}`, color: "#D4AF37" },
                  { label: "UNREALIZED", num: posUnrealized, fmt: (v) => `${v >= 0 ? "+" : ""}$${v.toFixed(2)}`, color: posUnrealized >= 0 ? "#00E676" : "#FF1744" },
                ].map(s => (
                  <div key={s.label} style={{ background: "rgba(6,6,6,0.6)", borderRadius: "6px", padding: "8px 6px", textAlign: "center", boxShadow: "inset 0 1px 3px rgba(0,0,0,0.3), 0 1px 0 rgba(255,255,255,0.03)" }}>
                    <div style={{ fontSize: "8px", color: "#3a3a3a", marginBottom: "3px" }}>{s.label}</div>
                    <div style={{ fontSize: "10px", fontWeight: "700", color: s.color }}>
                      <AnimatedNumber value={s.num} format={s.fmt} duration={180} />
                    </div>
                  </div>
                ))}
              </div>
              <div style={{ marginTop: "8px" }}>
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: "8px", color: "#3a3a3a", marginBottom: "4px" }}>
                  <span>SL <AnimatedNumber value={(Math.abs(pos.entry - pos.sl) / Math.max(pos.entry, 1)) * 100} format={(v) => `${v.toFixed(2)}%`} duration={180} /></span>
                  <span>TP <AnimatedNumber value={(Math.abs(pos.tp - pos.entry) / Math.max(pos.entry, 1)) * 100} format={(v) => `${v.toFixed(2)}%`} duration={180} /></span>
                </div>
                <div style={{ height: "3px", background: "#1e1e1e", borderRadius: "2px", overflow: "hidden" }}>
                  <div style={{ height: "100%", width: `${progress}%`, background: posUnrealized >= 0 ? "#00E676" : "#FF1744", transition: "width 0.5s", borderRadius: "2px" }} />
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
