import AnimatedNumber from "../AnimatedNumber.jsx";
import Skeleton from "../Skeleton.jsx";
import { Download, X, RefreshCcw, ArrowUp, ArrowDown, Camera, ChevronLeft, ChevronRight } from "lucide-react";

export function TradeHistoryOverlay({
  showHistory, setShowHistory,
  historyTrades, historyTotal, historyStats, historyLoading, historyPage, historyLimit,
  historyFilters, applyHistoryFilter, clearHistoryFilters, fetchHistory,
  activeCoins, exportTrades, tradeTypeBadge, openTradeDetail,
}) {
  if (!showHistory) return null;

  return (
    <div style={{ position:"fixed", inset:0, background:"rgba(6,6,15,0.95)", zIndex:9998, display:"flex", flexDirection:"column", animation:"fadein 0.2s ease" }}>
      {/* Header */}
      <div style={{ padding:"20px 24px 0", flexShrink:0 }}>
        <div style={{ display:"flex", justifyContent:"space-between", alignItems:"center", marginBottom:"16px" }}>
          <div style={{ display:"flex", alignItems:"center", gap:"12px" }}>
            <span style={{ fontFamily:"'Montserrat', sans-serif", fontSize:"20px", color:"#D4AF37", letterSpacing:"4px" }}>THE RECORD</span>
            <span style={{ fontSize:"10px", color:"#5C5C5C" }}>{historyTotal} total trades in database</span>
          </div>
          <div style={{ display:"flex", gap:"8px" }}>
            {historyTrades.length > 0 && (
              <button className="btn btn-d" onClick={() => exportTrades(historyTrades)} style={{ display: "flex", alignItems: "center", gap: "6px", fontSize: "9px" }}><Download size={14} /> EXPORT CSV</button>
            )}
            <button className="btn btn-d" onClick={() => setShowHistory(false)} style={{ display: "flex", alignItems: "center", gap: "6px", fontSize: "12px", color: "#FF1744", borderColor: "#FF174433", padding: "6px 14px" }}><X size={14} /> CLOSE</button>
          </div>
        </div>

        {/* Filters */}
        <div style={{ display:"flex", gap:"10px", flexWrap:"wrap", alignItems:"flex-end", marginBottom:"14px" }}>
          <div>
            <div style={{ fontSize:"8px", color:"#3a3a3a", letterSpacing:"1px", marginBottom:"3px" }}>FROM</div>
            <input type="date" value={historyFilters.date_from} onChange={e => applyHistoryFilter("date_from", e.target.value)}
              style={{ fontFamily:"'Space Mono',monospace", fontSize:"10px", padding:"6px 10px", borderRadius:"4px", border:"1px solid #2a2a2a", background:"#111111", color:"#D4D4D4", outline:"none" }} />
          </div>
          <div>
            <div style={{ fontSize:"8px", color:"#3a3a3a", letterSpacing:"1px", marginBottom:"3px" }}>TO</div>
            <input type="date" value={historyFilters.date_to} onChange={e => applyHistoryFilter("date_to", e.target.value)}
              style={{ fontFamily:"'Space Mono',monospace", fontSize:"10px", padding:"6px 10px", borderRadius:"4px", border:"1px solid #2a2a2a", background:"#111111", color:"#D4D4D4", outline:"none" }} />
          </div>
          <div>
            <div style={{ fontSize:"8px", color:"#3a3a3a", letterSpacing:"1px", marginBottom:"3px" }}>COIN</div>
            <select value={historyFilters.symbol} onChange={e => applyHistoryFilter("symbol", e.target.value)}
              style={{ fontFamily:"'Space Mono',monospace", fontSize:"10px", padding:"6px 10px", borderRadius:"4px", border:"1px solid #2a2a2a", background:"#111111", color:"#D4D4D4", outline:"none", appearance:"none", minWidth:"80px" }}>
              <option value="">ALL</option>
              {activeCoins.map(c => <option key={c} value={c}>{c}</option>)}
            </select>
          </div>
          <div>
            <div style={{ fontSize:"8px", color:"#3a3a3a", letterSpacing:"1px", marginBottom:"3px" }}>SIDE</div>
            <select value={historyFilters.side} onChange={e => applyHistoryFilter("side", e.target.value)}
              style={{ fontFamily:"'Space Mono',monospace", fontSize:"10px", padding:"6px 10px", borderRadius:"4px", border:"1px solid #2a2a2a", background:"#111111", color:"#D4D4D4", outline:"none", appearance:"none", minWidth:"80px" }}>
              <option value="">ALL</option>
              <option value="buy">BUY</option>
              <option value="sell">SELL</option>
            </select>
          </div>
          <div>
            <div style={{ fontSize:"8px", color:"#3a3a3a", letterSpacing:"1px", marginBottom:"3px" }}>RESULT</div>
            <select value={historyFilters.result} onChange={e => applyHistoryFilter("result", e.target.value)}
              style={{ fontFamily:"'Space Mono',monospace", fontSize:"10px", padding:"6px 10px", borderRadius:"4px", border:"1px solid #2a2a2a", background:"#111111", color:"#D4D4D4", outline:"none", appearance:"none", minWidth:"80px" }}>
              <option value="">ALL</option>
              <option value="win">WINS</option>
              <option value="loss">LOSSES</option>
            </select>
          </div>
          <div>
            <div style={{ fontSize:"8px", color:"#3a3a3a", letterSpacing:"1px", marginBottom:"3px" }}>TYPE</div>
            <select value={historyFilters.product_type} onChange={e => applyHistoryFilter("product_type", e.target.value)}
              style={{ fontFamily:"'Space Mono',monospace", fontSize:"10px", padding:"6px 10px", borderRadius:"4px", border:"1px solid #2a2a2a", background:"#111111", color:"#D4D4D4", outline:"none", appearance:"none", minWidth:"90px" }}>
              <option value="">ALL</option>
              <option value="spot">SPOT</option>
              <option value="futures">FUTURES</option>
              <option value="onchain">ON-CHAIN</option>
            </select>
          </div>
          {(historyFilters.date_from || historyFilters.date_to || historyFilters.symbol || historyFilters.side || historyFilters.result || historyFilters.product_type) && (
            <button className="btn btn-d" onClick={clearHistoryFilters} style={{ fontSize:"9px", color:"#ff9900", borderColor:"#ff990033", padding:"6px 12px", alignSelf:"flex-end" }}>CLEAR FILTERS</button>
          )}
          <button className="btn btn-d" onClick={() => fetchHistory(historyPage)} style={{ display: "flex", alignItems: "center", gap: "6px", fontSize: "9px", color: "#D4AF37", borderColor: "#D4AF3733", padding: "6px 12px", alignSelf: "flex-end" }}><RefreshCcw size={12} /> REFRESH</button>
        </div>

        {/* Summary stats */}
        <div style={{ display:"flex", gap:"16px", marginBottom:"14px", flexWrap:"wrap" }}>
          {[
            { label:"SHOWING", val:`${historyTrades.length} of ${historyTotal}`, color:"#D4D4D4" },
            { label:"WINS", val:historyStats.wins, color:"#00E676" },
            { label:"LOSSES", val:historyStats.losses, color:"#FF1744" },
            { label:"WIN RATE", val:`${historyStats.win_rate}%`, color:historyStats.win_rate >= 50 ? "#00E676" : "#FF1744" },
            { label:"NET P&L", val:`${historyStats.total_pnl >= 0 ? "+" : ""}$${historyStats.total_pnl.toFixed(2)}`, color:historyStats.total_pnl >= 0 ? "#00E676" : "#FF1744" },
          ].map(s => (
            <div key={s.label} style={{ background:"#111111", border:"1px solid #1e1e1e", borderRadius:"5px", padding:"8px 14px" }}>
              <div style={{ fontSize:"8px", color:"#3a3a3a", letterSpacing:"1px" }}>{s.label}</div>
              <div style={{ fontFamily:"'Montserrat', sans-serif", fontSize:"14px", fontWeight:"700", color:s.color }}>{s.val}</div>
            </div>
          ))}
        </div>

        {/* Table header */}
        <div style={{ display:"grid", gridTemplateColumns:"140px 55px 55px 55px 90px 90px 80px 70px 1fr", gap:"8px", padding:"8px 12px", background:"#111111", borderRadius:"5px 5px 0 0", border:"1px solid #1e1e1e", borderBottom:"none" }}>
          {["DATE / TIME", "COIN", "SIDE", "TYPE", "ENTRY", "EXIT", "P&L", "RESULT", "REASON"].map(h => (
            <span key={h} style={{ fontSize:"8px", color:"#3a3a3a", letterSpacing:"1.5px", fontWeight:"700" }}>{h}</span>
          ))}
        </div>
      </div>

      {/* Trade rows */}
      <div style={{ flex:1, overflowY:"auto", padding:"0 24px", minHeight:0 }}>
        <div style={{ border:"1px solid #1e1e1e", borderTop:"none", borderRadius:"0 0 5px 5px", background:"#111111" }}>
          {historyLoading ? (
            <div style={{ padding:"24px", display:"flex", flexDirection:"column", gap:"8px" }}>
              {[1,2,3,4,5,6,7,8].map(i => <Skeleton key={i} width="100%" height={28} />)}
            </div>
          ) : historyTrades.length === 0 ? (
            <div style={{ textAlign:"center", padding:"40px", color:"#2a2a2a", fontSize:"11px" }}>
              No trades found{(historyFilters.date_from || historyFilters.date_to || historyFilters.symbol || historyFilters.side || historyFilters.result) ? " matching filters" : ""}
            </div>
          ) : (
            historyTrades.map(tr => (
              <div key={tr.id} style={{ display:"grid", gridTemplateColumns:"140px 55px 55px 55px 90px 90px 80px 70px 1fr", gap:"8px", padding:"8px 12px", borderBottom:"1px solid #1a1a1a", fontSize:"11px", transition:"background 0.1s", cursor:"pointer" }}
                onMouseEnter={e => e.currentTarget.style.background="#1a1a1a"}
                onMouseLeave={e => e.currentTarget.style.background="transparent"}
                onClick={() => openTradeDetail(tr)}
                title="Click to view trade chart screenshots">
                <span style={{ color:"#5C5C5C", fontSize:"10px" }}>
                  {tr.created_at || tr.ts}
                </span>
                <span style={{ color:"#D4AF37", fontWeight:"700" }}>{tr.symbol || "BTC"}</span>
                <span>
                  <span className="tag" style={{ display: "flex", alignItems: "center", gap: "4px", background: tr.side === "buy" ? "#00E67618" : "#FF174418", color: tr.side === "buy" ? "#00E676" : "#FF1744", padding: "2px 6px" }}>
                    {tr.side === "buy" ? <ArrowUp size={10} /> : <ArrowDown size={10} />} {tr.side?.toUpperCase()}
                  </span>
                </span>
                <span>{tradeTypeBadge(tr)}</span>
                <span style={{ color:"#D4D4D4" }}>${(+tr.entry).toLocaleString()}</span>
                <span style={{ color:"#D4D4D4" }}>${(+tr.exit).toLocaleString()}</span>
                <span style={{ fontWeight:"700", color:tr.win?"#00E676":"#FF1744" }}>{tr.pnl>=0?"+":""}${(+tr.pnl).toFixed(2)}</span>
                <span>
                  <span className="tag" style={{ background:tr.win?"#00E67618":"#FF174418", color:tr.win?"#00E676":"#FF1744", padding:"2px 6px" }}>
                    {tr.win ? "WIN" : "LOSS"}
                  </span>
                </span>
                <span style={{ color:"#3a3a3a", fontSize:"10px", overflow:"hidden", textOverflow:"ellipsis", whiteSpace:"nowrap", display:"flex", alignItems:"center", gap:"4px" }}>
                  {tr.reason}
                  <Camera size={10} style={{ color: "#D4AF3766", flexShrink: 0 }} />
                </span>
              </div>
            ))
          )}
        </div>
      </div>

      {/* Pagination */}
      {historyTotal > historyLimit && (
        <div style={{ padding:"12px 24px", flexShrink:0, display:"flex", justifyContent:"center", alignItems:"center", gap:"12px" }}>
          <button className="btn btn-d" disabled={historyPage === 0} onClick={() => fetchHistory(historyPage - 1)}
            style={{ display: "flex", alignItems: "center", gap: "6px", padding: "6px 14px", fontSize: "10px" }}><ChevronLeft size={14} /> PREV</button>
          <span style={{ fontSize:"10px", color:"#5C5C5C" }}>
            Page {historyPage + 1} of {Math.ceil(historyTotal / historyLimit)}
          </span>
          <button className="btn btn-d" disabled={(historyPage + 1) * historyLimit >= historyTotal} onClick={() => fetchHistory(historyPage + 1)}
            style={{ display: "flex", alignItems: "center", gap: "6px", padding: "6px 14px", fontSize: "10px" }}>NEXT <ChevronRight size={14} /></button>
        </div>
      )}
    </div>
  );
}
