import { useState } from "react";
import { X, Camera } from "lucide-react";
import Skeleton from "../Skeleton.jsx";
import { popIn } from "../animations.js";

const BACKEND_BASE = import.meta.env.VITE_BACKEND_URL
  || (import.meta.env.DEV ? "http://localhost:8000" : "");

export function TradeDetailModal({ tradeDetail, closeTradeDetail, tradeDetailLoading, getAuthQueryParam }) {
  const [tradeDetailTab, setTradeDetailTab] = useState("exit");

  if (!tradeDetail) return null;

  const backendBase = BACKEND_BASE || `${window.location.protocol}//${window.location.hostname}:8000`;
  const authParam = getAuthQueryParam();

  return (
    <div style={{ position: "fixed", inset: 0, background: "rgba(6,6,15,0.97)", zIndex: 9999, display: "flex", flexDirection: "column", animation: "fadein 0.2s ease", overflow: "auto" }}
      onClick={closeTradeDetail}>
      <div style={{ maxWidth: "min(1100px, calc(100vw - 24px))", width: "100%", margin: "max(12px, env(safe-area-inset-top)) auto 20px", padding: "0 clamp(12px, 4vw, 20px)", boxSizing: "border-box" }} ref={popIn} onClick={e => e.stopPropagation()}>
        {/* Header */}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "20px" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
            <span style={{ fontFamily: "'Montserrat', sans-serif", fontSize: "22px", color: "#D4AF37", letterSpacing: "4px" }}>TRADE REVIEW</span>
            <span className="tag" style={{ background: tradeDetail.trade?.win ? "#00E67618" : "#FF174418", color: tradeDetail.trade?.win ? "#00E676" : "#FF1744", fontSize: "11px", padding: "3px 10px" }}>
              {tradeDetail.trade?.win ? "WIN" : "LOSS"}
            </span>
          </div>
          <button className="btn btn-d" onClick={closeTradeDetail} style={{ display: "flex", alignItems: "center", gap: "6px", fontSize: "12px", color: "#FF1744", borderColor: "#FF174433", padding: "6px 14px" }}><X size={14} /> CLOSE</button>
        </div>

        {/* Trade Summary Bar */}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(100px, calc(50vw - 16px)), 1fr))", gap: "10px", marginBottom: "20px" }}>
          {[
            { label: "SYMBOL", val: tradeDetail.trade?.symbol || "BTC", color: "#D4AF37" },
            { label: "SIDE", val: tradeDetail.trade?.side?.toUpperCase(), color: tradeDetail.trade?.side === "buy" ? "#00E676" : "#FF1744" },
            { label: "ENTRY", val: `$${(+(tradeDetail.trade?.entry || 0)).toLocaleString()}`, color: "#D4D4D4" },
            { label: "EXIT", val: `$${(+(tradeDetail.trade?.exit || tradeDetail.trade?.exit_price || 0)).toLocaleString()}`, color: "#D4D4D4" },
            { label: "P&L", val: `${(tradeDetail.trade?.pnl || 0) >= 0 ? "+" : ""}$${(+(tradeDetail.trade?.pnl || 0)).toFixed(2)}`, color: (tradeDetail.trade?.pnl || 0) >= 0 ? "#00E676" : "#FF1744" },
            { label: "SIZE", val: `$${(+(tradeDetail.trade?.usd_size || 0)).toFixed(2)}`, color: "#999" },
            { label: "DATE", val: tradeDetail.trade?.created_at || tradeDetail.trade?.ts || "", color: "#5C5C5C" },
          ].map(s => (
            <div key={s.label} style={{ background: "#111111", border: "1px solid #1e1e1e", borderRadius: "6px", padding: "10px 12px", textAlign: "center" }}>
              <div style={{ fontSize: "8px", color: "#3a3a3a", letterSpacing: "1px", marginBottom: "3px" }}>{s.label}</div>
              <div style={{ fontSize: "13px", fontWeight: "700", color: s.color }}>{s.val}</div>
            </div>
          ))}
        </div>

        {/* Reason */}
        {tradeDetail.trade?.reason && (
          <div style={{ background: "#111111", border: "1px solid #1e1e1e", borderRadius: "6px", padding: "12px 16px", marginBottom: "20px" }}>
            <div style={{ fontSize: "8px", color: "#3a3a3a", letterSpacing: "1px", marginBottom: "4px" }}>CLOSE REASON</div>
            <div style={{ fontSize: "12px", color: "#D4D4D4" }}>{tradeDetail.trade.reason}</div>
          </div>
        )}

        {/* Phase Tabs */}
        <div style={{ display: "flex", gap: "8px", marginBottom: "16px" }}>
          {["entry", "exit"].map(phase => (
            <button key={phase} className="btn" onClick={() => setTradeDetailTab(phase)}
              style={{
                padding: "8px 20px", fontSize: "11px", letterSpacing: "2px", fontWeight: "700",
                background: tradeDetailTab === phase ? "#D4AF3722" : "transparent",
                color: tradeDetailTab === phase ? "#D4AF37" : "#5C5C5C",
                border: `1px solid ${tradeDetailTab === phase ? "#D4AF3744" : "#2a2a2a"}`,
              }}>
              {phase.toUpperCase()} CHART
            </button>
          ))}
        </div>

        {/* Chart Screenshots */}
        {tradeDetailLoading ? (
          <div style={{ display: "flex", flexDirection: "column", gap: "8px", padding: "40px 0" }}>
            {[1, 2, 3].map(i => <Skeleton key={i} width="100%" height={200} />)}
          </div>
        ) : (
          <div>
            {(() => {
              const phase = tradeDetailTab;
              const ss = tradeDetail.screenshots?.[phase];
              const meta = ss?.meta;
              const timeframes = ss?.timeframes || [];

              if (!ss || timeframes.length === 0) {
                return (
                  <div style={{ textAlign: "center", padding: "60px 20px", color: "#2a2a2a" }}>
                    <div style={{ fontSize: "48px", marginBottom: "12px", opacity: 0.3, display: "flex", justifyContent: "center" }}><Camera size={48} /></div>
                    <div style={{ fontSize: "12px", color: "#3a3a3a", marginBottom: "6px" }}>No chart screenshots available for {phase}</div>
                    <div style={{ fontSize: "10px", color: "#2a2a2a" }}>
                      Screenshots are captured automatically when trades open and close.
                      {!tradeDetail.screenshots?.entry && !tradeDetail.screenshots?.exit && (
                        <span> This trade was recorded before screenshot capture was enabled.</span>
                      )}
                    </div>
                  </div>
                );
              }

              return (
                <div>
                  {/* Strategy/Context annotation above charts */}
                  {meta && (
                    <div style={{ background: "#0d0d0d", border: "1px solid #1e1e1e", borderRadius: "6px", padding: "14px 16px", marginBottom: "16px" }}>
                      <div style={{ display: "flex", flexWrap: "wrap", gap: "16px", fontSize: "10px" }}>
                        {meta.side && (
                          <div><span style={{ color: "#3a3a3a" }}>SIDE: </span><span style={{ color: meta.side === "buy" ? "#00E676" : "#FF1744", fontWeight: "700" }}>{meta.side.toUpperCase()}</span></div>
                        )}
                        {meta.confidence != null && (
                          <div><span style={{ color: "#3a3a3a" }}>CONFIDENCE: </span><span style={{ color: "#D4AF37", fontWeight: "700" }}>{(meta.confidence * 100).toFixed(0)}%</span></div>
                        )}
                        {meta.market_condition && (
                          <div><span style={{ color: "#3a3a3a" }}>REGIME: </span><span style={{ color: "#D4D4D4" }}>{meta.market_condition}</span></div>
                        )}
                        {meta.strategy && (
                          <div><span style={{ color: "#3a3a3a" }}>STRATEGY: </span><span style={{ color: "#D4D4D4" }}>{meta.strategy}</span></div>
                        )}
                        {meta.entry != null && (
                          <div><span style={{ color: "#3a3a3a" }}>ENTRY: </span><span style={{ color: "#D4D4D4" }}>${(+meta.entry).toLocaleString()}</span></div>
                        )}
                        {meta.tp != null && (
                          <div><span style={{ color: "#3a3a3a" }}>TP: </span><span style={{ color: "#00E676" }}>${(+meta.tp).toLocaleString()}</span></div>
                        )}
                        {meta.sl != null && (
                          <div><span style={{ color: "#3a3a3a" }}>SL: </span><span style={{ color: "#FF1744" }}>${(+meta.sl).toLocaleString()}</span></div>
                        )}
                        {meta.pnl != null && (
                          <div><span style={{ color: "#3a3a3a" }}>P&L: </span><span style={{ color: meta.pnl >= 0 ? "#00E676" : "#FF1744", fontWeight: "700" }}>{meta.pnl >= 0 ? "+" : ""}${(+meta.pnl).toFixed(2)}</span></div>
                        )}
                        {meta.reason && (
                          <div><span style={{ color: "#3a3a3a" }}>REASON: </span><span style={{ color: "#D4D4D4" }}>{meta.reason}</span></div>
                        )}
                      </div>
                      {meta.reasoning && (
                        <div style={{ marginTop: "8px", fontSize: "10px", color: "#5C5C5C", lineHeight: "1.6", borderTop: "1px solid #1a1a1a", paddingTop: "8px" }}>
                          {meta.reasoning}
                        </div>
                      )}
                      {meta.patterns && meta.patterns.length > 0 && (
                        <div style={{ marginTop: "6px", display: "flex", gap: "4px", flexWrap: "wrap" }}>
                          {meta.patterns.map((p, i) => (
                            <span key={i} className="tag" style={{ background: "#D4AF3712", color: "#D4AF37", fontSize: "9px", padding: "2px 6px" }}>{p}</span>
                          ))}
                        </div>
                      )}
                      {meta.indicators && typeof meta.indicators === "object" && (
                        <div style={{ marginTop: "6px", display: "flex", gap: "12px", flexWrap: "wrap", fontSize: "9px" }}>
                          {Object.entries(meta.indicators).filter(([k, v]) => typeof v === "number").slice(0, 8).map(([k, v]) => (
                            <div key={k}><span style={{ color: "#3a3a3a" }}>{k}: </span><span style={{ color: "#5C5C5C" }}>{typeof v === "number" ? v.toFixed(2) : String(v)}</span></div>
                          ))}
                        </div>
                      )}
                    </div>
                  )}

                  {/* Chart images */}
                  <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
                    {timeframes.map(tf => (
                      <div key={tf} style={{ background: "#0A0A0A", border: "1px solid #1e1e1e", borderRadius: "6px", overflow: "hidden" }}>
                        <div style={{ padding: "8px 12px", borderBottom: "1px solid #1a1a1a", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                          <span style={{ fontSize: "10px", color: "#D4AF37", fontWeight: "700", letterSpacing: "1px" }}>
                            {tf.toUpperCase()} TIMEFRAME — {phase.toUpperCase()}
                          </span>
                          <span style={{ fontSize: "9px", color: "#3a3a3a" }}>{tradeDetail.trade?.symbol || "BTC"}/USD</span>
                        </div>
                        <img
                          src={`${backendBase}/api/trade/${tradeDetail.trade?.id}/screenshot/${phase}/${tf}${authParam}`}
                          alt={`${phase} chart ${tf}`}
                          style={{ width: "100%", display: "block" }}
                          onError={e => { e.target.style.display = "none"; e.target.nextSibling && (e.target.nextSibling.style.display = "block"); }}
                        />
                        <div style={{ display: "none", padding: "40px", textAlign: "center", color: "#2a2a2a", fontSize: "11px" }}>
                          Failed to load {tf} chart
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              );
            })()}
          </div>
        )}

        {/* Trade Context (from DB) */}
        {tradeDetail.context && (
          <div style={{ marginTop: "20px", background: "#111111", border: "1px solid #1e1e1e", borderRadius: "6px", padding: "14px 16px" }}>
            <div style={{ fontSize: "9px", color: "#D4AF37", letterSpacing: "2px", fontWeight: "700", marginBottom: "10px" }}>TRADE CONTEXT</div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))", gap: "8px" }}>
              {[
                { label: "REGIME", val: tradeDetail.context.regime },
                { label: "CONFIDENCE", val: tradeDetail.context.confidence ? `${(tradeDetail.context.confidence * 100).toFixed(0)}%` : null },
                { label: "CONFLUENCE", val: tradeDetail.context.confluence_score },
                { label: "FEAR/GREED", val: tradeDetail.context.fear_greed },
                { label: "SIZE %", val: tradeDetail.context.size_pct ? `${tradeDetail.context.size_pct}%` : null },
                { label: "R:R RATIO", val: tradeDetail.context.rr_ratio ? tradeDetail.context.rr_ratio.toFixed(2) : null },
                { label: "HOLD TIME", val: tradeDetail.context.hold_duration_sec ? `${Math.round(tradeDetail.context.hold_duration_sec / 60)}m` : null },
                { label: "HOUR", val: tradeDetail.context.hour_of_day != null ? `${tradeDetail.context.hour_of_day}:00` : null },
              ].filter(s => s.val != null).map(s => (
                <div key={s.label} style={{ background: "#0A0A0A", borderRadius: "4px", padding: "8px 10px" }}>
                  <div style={{ fontSize: "8px", color: "#3a3a3a", letterSpacing: "1px", marginBottom: "2px" }}>{s.label}</div>
                  <div style={{ fontSize: "12px", color: "#D4D4D4", fontWeight: "600" }}>{s.val}</div>
                </div>
              ))}
            </div>
            {tradeDetail.context.patterns && tradeDetail.context.patterns.length > 0 && (
              <div style={{ marginTop: "10px" }}>
                <div style={{ fontSize: "8px", color: "#3a3a3a", letterSpacing: "1px", marginBottom: "4px" }}>PATTERNS DETECTED</div>
                <div style={{ display: "flex", gap: "4px", flexWrap: "wrap" }}>
                  {tradeDetail.context.patterns.map((p, i) => (
                    <span key={i} className="tag" style={{ background: "#D4AF3712", color: "#D4AF37", fontSize: "9px", padding: "2px 8px" }}>{p}</span>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Audit Trail */}
        {tradeDetail.audit && (
          <div style={{ marginTop: "16px", background: "#111111", border: "1px solid #1e1e1e", borderRadius: "6px", padding: "14px 16px", marginBottom: "20px" }}>
            <div style={{ fontSize: "9px", color: "#D4AF37", letterSpacing: "2px", fontWeight: "700", marginBottom: "10px" }}>DECISION AUDIT</div>
            <div style={{ fontSize: "10px", color: "#5C5C5C", lineHeight: "1.8" }}>
              {tradeDetail.audit.reasoning && (
                <div style={{ marginBottom: "8px" }}><span style={{ color: "#3a3a3a" }}>Reasoning: </span>{tradeDetail.audit.reasoning}</div>
              )}
              {tradeDetail.audit.adversary_verdict && tradeDetail.audit.adversary_verdict !== "none" && (
                <div style={{ marginBottom: "4px" }}>
                  <span style={{ color: "#3a3a3a" }}>Adversary: </span>
                  <span style={{ color: tradeDetail.audit.adversary_verdict === "approve" ? "#00E676" : "#FF1744" }}>{tradeDetail.audit.adversary_verdict.toUpperCase()}</span>
                  {tradeDetail.audit.adversary_risk_score > 0 && <span style={{ color: "#5C5C5C" }}> (risk: {tradeDetail.audit.adversary_risk_score})</span>}
                </div>
              )}
              {tradeDetail.audit.vision_structure && tradeDetail.audit.vision_structure !== "" && (
                <div><span style={{ color: "#3a3a3a" }}>Vision: </span>{tradeDetail.audit.vision_structure} (conviction: {tradeDetail.audit.vision_conviction})</div>
              )}
              {tradeDetail.audit.model_used && (
                <div><span style={{ color: "#3a3a3a" }}>Model: </span>{tradeDetail.audit.model_used}</div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
