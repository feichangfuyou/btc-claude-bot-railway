import { useState, useEffect, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext.jsx";
import AnimatedNumber from "../AnimatedNumber.jsx";
import Skeleton from "../Skeleton.jsx";
import { useAuthHeaders } from "../hooks/useAuthHeaders.js";
import { isAdminEmail } from "../utils/adminEmails.js";
import { colors } from "../theme.js";
import { RefreshCcw, ArrowUp, ArrowDown } from "lucide-react";

export function AnalyticsSection({ connected, log, lossToast, cbLive, krakenEnabled, binanceEnabled, hasEngine, isLiveMode, agentKit, paperMode, directionBias, requireTradeApproval, price, priceAge, wsRetrying, news, send }) {
  const { user, profile, signOut } = useAuth();
  const getAuthHeaders = useAuthHeaders();
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState("equity");
  const [equityData, setEquityData] = useState(null);
  const [analyticsData, setAnalyticsData] = useState(null);
  const [memoryData, setMemoryData] = useState(null);
  const [calibrationData, setCalibrationData] = useState(null);
  const [newsData, setNewsData] = useState(null);
  const [backtestResult, setBacktestResult] = useState(null);
  const [backtestLoading, setBacktestLoading] = useState(false);
  const [btParams, setBtParams] = useState({ symbol: "BTC", days: 30, tp: 2.5, sl: 1.0, confluence: 5, rr: 1.8 });
  const [loading, setLoading] = useState(false);
  const [adversaryStats, setAdversaryStats] = useState(null);

  const [selectedNews, setSelectedNews] = useState(null);


  const fetchData = useCallback(async (tab) => {
    if (!connected) return;
    setLoading(true);
    try {
      const safeFetch = async (url) => {
        const headers = {
          ...getAuthHeaders(),
          "Accept": "application/json",
        };
        const resp = await fetch(url, { headers });
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const type = resp.headers.get("content-type");
        if (!type || !type.includes("application/json")) {
          throw new Error("Backend returned HTML instead of JSON. Check if server is running on port 8000.");
        }
        return await resp.json();
      };

      if (tab === "equity") {
        const d = await safeFetch(`/equity`);
        setEquityData(d);
      } else if (tab === "analytics") {
        const d = await safeFetch(`/memory/analysis`);
        setAnalyticsData(d);
      } else if (tab === "memory") {
        const [rules, patterns] = await Promise.all([
          safeFetch(`/memory/rules`),
          safeFetch(`/memory/patterns`),
        ]);
        setMemoryData({ ...rules, ...patterns });
      } else if (tab === "calibration") {
        const d = await safeFetch(`/memory/calibration`);
        setCalibrationData(d);
      } else if (tab === "news") {
        const [n, a] = await Promise.all([
          safeFetch(`/api/market/news?symbol=all`),
          safeFetch(`/api/analytics/adversary`),
        ]);
        setNewsData(n);
        setAdversaryStats(a);
      }
    } catch (e) {
      log?.(`Analytics: ${e.message}`, "error");
    } finally {
      setLoading(false);
    }
  }, [connected, log, getAuthHeaders]);

  useEffect(() => { fetchData(activeTab); }, [activeTab, fetchData]);

  // Sync WebSocket news to newsData
  useEffect(() => {
    if (news) {
      setNewsData(news);
    }
  }, [news]);

  const runBacktest = async () => {
    setBacktestLoading(true);
    try {
      const params = new URLSearchParams({
        symbol: btParams.symbol, days: btParams.days,
        tp_atr_mult: btParams.tp, sl_atr_mult: btParams.sl,
        min_confluence: btParams.confluence, min_rr: btParams.rr,
      });
      const r = await fetch(`/backtest?${params}`, { method: "POST", headers: getAuthHeaders() });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const type = r.headers.get("content-type");
      if (!type || !type.includes("application/json")) {
        throw new Error("Invalid backtest response format");
      }
      const data = await r.json();
      setBacktestResult(data);
      log?.(`Backtest: ${data.total_trades} trades, ${data.return_pct >= 0 ? "+" : ""}${data.return_pct}% return`, "info");
    } catch (e) {
      log?.(`Backtest error: ${e.message}`, "error");
    } finally {
      setBacktestLoading(false);
    }
  };

  const tabs = [
    { id: "equity", label: "PERFORMANCE CURVE" },
    { id: "analytics", label: "STRATEGY INSIGHTS" },
    { id: "memory", label: "DECISION ENGINE" },
    { id: "calibration", label: "CONFIDENCE" },
    { id: "news", label: "INSTITUTIONAL PULSE" },
    { id: "backtest", label: "STRATEGY RESEARCH" },
  ];

  if (!connected) return null;

  return (
    <>
      <div className="tab-logs">
        <div style={{ display: "flex", gap: "6px", marginBottom: "12px", overflowX: "auto" }}>
          {tabs.map(t => (
            <button key={t.id} onClick={() => setActiveTab(t.id)}
              className="btn" style={{
                padding: "6px 14px", fontSize: "9px", letterSpacing: "1.5px",
                background: activeTab === t.id ? "#D4AF3711" : "transparent",
                color: activeTab === t.id ? "#D4AF37" : "#5C5C5C",
                border: `1px solid ${activeTab === t.id ? "#D4AF3733" : "#1e1e1e"}`,
              }}>{t.label}</button>
          ))}
          <button className="btn btn-d" onClick={() => fetchData(activeTab)} style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: "4px", padding: "4px 10px", fontSize: "9px" }}><RefreshCcw size={12} /></button>
        </div>

        <div className="card" style={{ minHeight: "200px" }}>
          {loading && (
            <div style={{ padding: "24px", display: "flex", flexDirection: "column", gap: "12px" }}>
              <Skeleton width="40%" height={14} />
              <Skeleton width="100%" height={80} />
              <Skeleton width="60%" height={14} />
              <Skeleton width="100%" height={60} />
            </div>
          )}

          {/* ── EQUITY CURVE ── */}
          {activeTab === "equity" && !loading && equityData && (
            <div>
              <div className="section-label" style={{ marginBottom: "12px" }}>PERFORMANCE CURVE</div>
              {equityData.curve?.length > 0 ? (
                <div>
                  <div style={{ display: "flex", gap: "16px", marginBottom: "14px", flexWrap: "wrap" }}>
                    {equityData.sessions?.slice(0, 7).map(s => (
                      <div key={s.date} style={{ background: "#0A0A0A", borderRadius: "5px", padding: "8px 12px", minWidth: "100px" }}>
                        <div style={{ fontSize: "8px", color: "#3a3a3a" }}>{s.date}</div>
                        <div style={{ fontSize: "11px", fontWeight: "700", color: s.total_pnl >= 0 ? "#00E676" : "#FF1744" }}>
                          {s.total_pnl >= 0 ? "+" : ""}${s.total_pnl?.toFixed(2)}
                        </div>
                        <div style={{ fontSize: "8px", color: "#5C5C5C" }}>{s.trades_taken} trades | {s.wins}W/{s.losses}L</div>
                      </div>
                    ))}
                  </div>
                  <div style={{ height: "120px", display: "flex", alignItems: "flex-end", gap: "1px", padding: "0 4px" }}>
                    {(() => {
                      const pts = equityData.curve;
                      const balances = pts.map(p => p.balance);
                      const mn = Math.min(...balances);
                      const mx = Math.max(...balances);
                      const range = mx - mn || 1;
                      const step = Math.max(1, Math.floor(pts.length / 80));
                      const sampled = pts.filter((_, i) => i % step === 0 || i === pts.length - 1);
                      return sampled.map((p, i) => {
                        const h = Math.max(2, ((p.balance - mn) / range) * 110);
                        const isUp = i > 0 ? p.balance >= sampled[i - 1].balance : true;
                        return <div key={i} title={`${p.ts}: $${p.balance.toFixed(2)}`} style={{ flex: 1, minWidth: "2px", maxWidth: "8px", height: `${h}px`, background: isUp ? "#00E67688" : "#FF174488", borderRadius: "1px 1px 0 0", transition: "height 0.3s" }} />;
                      });
                    })()}
                  </div>
                  <div style={{ display: "flex", justifyContent: "space-between", fontSize: "9px", color: "#3a3a3a", marginTop: "4px" }}>
                    <span>{equityData.curve[0]?.ts?.split(" ")[0]}</span>
                    <span>{equityData.curve[equityData.curve.length - 1]?.ts?.split(" ")[0]}</span>
                  </div>
                </div>
              ) : (
                <div style={{ textAlign: "center", padding: "30px", color: "#2a2a2a", fontSize: "11px" }}>
                  No snapshots yet — run the bot for a few hours to build the equity curve
                </div>
              )}
            </div>
          )}

          {/* ── TRADE ANALYTICS ── */}
          {activeTab === "analytics" && !loading && analyticsData && (
            <div>
              <div className="section-label" style={{ marginBottom: "12px" }}>STRATEGY INSIGHTS</div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "14px" }} className="analytics-grid">
                {/* Regime performance */}
                <div>
                  <div style={{ fontSize: "9px", color: "#5C5C5C", letterSpacing: "1px", marginBottom: "8px" }}>BY REGIME</div>
                  {Object.entries(analyticsData.regime || {}).map(([regime, data]) => (
                    <div key={regime} className="row" style={{ fontSize: "10px" }}>
                      <span style={{ color: { trending_up: "#00E676", trending_down: "#FF1744", ranging: "#D4AF37", chaotic: "#ff9900" }[regime] || "#5C5C5C", fontWeight: "700", textTransform: "uppercase" }}>{regime}</span>
                      <span>
                        <span style={{ color: data.win_rate >= 50 ? "#00E676" : "#FF1744", fontWeight: "700" }}>{data.win_rate}% ACCURACY</span>
                        <span style={{ color: "#3a3a3a", marginLeft: "6px" }}>{data.total} SAMPLES</span>
                        <span style={{ color: data.total_pnl >= 0 ? "#00E676" : "#FF1744", marginLeft: "6px" }}>{data.total_pnl >= 0 ? "+" : ""}${data.total_pnl}</span>
                      </span>
                    </div>
                  ))}
                </div>
                {/* Hourly performance */}
                <div>
                  <div style={{ fontSize: "9px", color: "#5C5C5C", letterSpacing: "1px", marginBottom: "8px" }}>BEST HOURS (UTC)</div>
                  {(analyticsData.hourly || []).slice(0, 6).map(h => (
                    <div key={h.hour_of_day} className="row" style={{ fontSize: "10px" }}>
                      <span style={{ color: "#D4D4D4" }}>{String(h.hour_of_day).padStart(2, "0")}:00</span>
                      <span>
                        <span style={{ color: h.win_rate >= 50 ? "#00E676" : "#FF1744", fontWeight: "700" }}>{h.win_rate}% ACC</span>
                        <span style={{ color: "#3a3a3a", marginLeft: "6px" }}>avg ${h.avg_pnl}</span>
                      </span>
                    </div>
                  ))}
                </div>
                {/* Sizing analysis */}
                <div>
                  <div style={{ fontSize: "9px", color: "#5C5C5C", letterSpacing: "1px", marginBottom: "8px" }}>BY SIZE</div>
                  {(analyticsData.sizing || []).map(s => (
                    <div key={s.size_band} className="row" style={{ fontSize: "10px" }}>
                      <span style={{ color: "#D4D4D4" }}>{s.size_band.replace("_", " ")}</span>
                      <span>
                        <span style={{ color: s.win_rate >= 50 ? "#00E676" : "#FF1744", fontWeight: "700" }}>{s.win_rate}% ACC</span>
                        <span style={{ color: "#3a3a3a", marginLeft: "6px" }}>{s.total} SAMPLES</span>
                      </span>
                    </div>
                  ))}
                </div>
                {/* Confidence analysis */}
                <div>
                  <div style={{ fontSize: "9px", color: "#5C5C5C", letterSpacing: "1px", marginBottom: "8px" }}>BY CONFIDENCE</div>
                  {(analyticsData.confidence || []).map(c => (
                    <div key={c.confidence_band} className="row" style={{ fontSize: "10px" }}>
                      <span style={{ color: "#D4AF37" }}>{c.confidence_band.replace("_", " ")}</span>
                      <span>
                        <span style={{ color: c.win_rate >= 50 ? "#00E676" : "#FF1744", fontWeight: "700" }}>{c.win_rate}% ACC</span>
                        <span style={{ color: "#3a3a3a", marginLeft: "6px" }}>avg ${c.avg_pnl}</span>
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* ── DECISION ENGINE ── */}
          {activeTab === "memory" && !loading && memoryData && (
            <div>
              <div className="section-label" style={{ marginBottom: "12px" }}>LEARNED RULES & SIGNALS</div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "14px" }} className="analytics-grid">
                <div>
                  <div style={{ fontSize: "9px", color: "#5C5C5C", letterSpacing: "1px", marginBottom: "8px" }}>
                    ACTIVE HEURISTICS ({memoryData.total_rules || 0})
                  </div>
                  {(memoryData.rules || []).length === 0 ? (
                    <div style={{ fontSize: "10px", color: "#2a2a2a", padding: "12px 0" }}>No rules learned yet — need 5+ trades</div>
                  ) : (
                    (memoryData.rules || []).slice(0, 10).map(rule => (
                      <div key={rule.rule_key} style={{ background: "#0A0A0A", borderRadius: "5px", padding: "8px 10px", marginBottom: "6px", border: "1px solid #1e1e1e" }}>
                        <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "4px" }}>
                          <span className="tag" style={{ background: rule.rule_type === "avoid" ? "#FF174418" : "#00E67618", color: rule.rule_type === "avoid" ? "#FF1744" : "#00E676", fontSize: "8px" }}>
                            {rule.rule_type?.toUpperCase()}
                          </span>
                          <span style={{ fontSize: "8px", color: "#3a3a3a" }}>
                            {rule.sample_size} samples | {rule.win_rate}% ACC
                          </span>
                        </div>
                        <div style={{ fontSize: "10px", color: "#999999", lineHeight: "1.6" }}>{rule.description}</div>
                      </div>
                    ))
                  )}
                </div>
                <div>
                  <div style={{ fontSize: "9px", color: "#5C5C5C", letterSpacing: "1px", marginBottom: "8px" }}>
                    PATTERN PERFORMANCE ({memoryData.total_trades || 0} SAMPLES analyzed)
                  </div>
                  {(memoryData.patterns || []).length === 0 ? (
                    <div style={{ fontSize: "10px", color: "#2a2a2a", padding: "12px 0" }}>No pattern data yet</div>
                  ) : (
                    (memoryData.patterns || []).slice(0, 12).map((p, i) => (
                      <div key={i} className="row" style={{ fontSize: "10px" }}>
                        <div>
                          <span style={{ color: "#D4D4D4" }}>{p.pattern}</span>
                          <span style={{ color: "#3a3a3a", fontSize: "8px", marginLeft: "4px" }}>{p.symbol} {p.side} ({p.regime})</span>
                        </div>
                        <span>
                          <span style={{ color: p.win_rate >= 50 ? "#00E676" : "#FF1744", fontWeight: "700" }}>{p.win_rate}%</span>
                          <span style={{ color: "#3a3a3a", marginLeft: "4px" }}>{p.total}x</span>
                        </span>
                      </div>
                    ))
                  )}
                </div>
              </div>
            </div>
          )}

          {/* ── CONFIDENCE CALIBRATION ── */}
          {activeTab === "calibration" && !loading && calibrationData && (
            <div>
              <div className="section-label" style={{ marginBottom: "6px" }}>CONFIDENCE CALIBRATION</div>
              <div style={{ fontSize: "10px", color: "#5C5C5C", marginBottom: "14px" }}>
                Does signal confidence actually predict outcome efficiency? Perfect calibration = predicted matches actual.
              </div>
              {(calibrationData.calibration || []).length === 0 ? (
                <div style={{ fontSize: "10px", color: "#2a2a2a", padding: "20px", textAlign: "center" }}>Need more trades with confidence data</div>
              ) : (
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(140px, 1fr))", gap: "10px" }}>
                  {(calibrationData.calibration || []).map(c => {
                    const predicted = c.avg_predicted;
                    const actual = c.actual_win_rate;
                    const gap = Math.abs(predicted - actual);
                    const calibrated = gap < 10;
                    return (
                      <div key={c.predicted_band} style={{ background: "#0A0A0A", borderRadius: "5px", padding: "12px", border: `1px solid ${calibrated ? "#00E67622" : "#ff990022"}`, textAlign: "center" }}>
                        <div style={{ fontSize: "8px", color: "#3a3a3a", letterSpacing: "1px", marginBottom: "6px" }}>PREDICTED {c.predicted_band}</div>
                        <div style={{ fontSize: "16px", fontWeight: "700", color: "#D4AF37" }}>{predicted}%</div>
                        <div style={{ fontSize: "8px", color: "#3a3a3a", margin: "4px 0" }}>vs actual</div>
                        <div style={{ fontSize: "16px", fontWeight: "700", color: actual >= 50 ? "#00E676" : "#FF1744" }}>{actual}%</div>
                        <div style={{ fontSize: "8px", color: calibrated ? "#00E676" : "#ff9900", marginTop: "6px" }}>
                          {calibrated ? "CALIBRATED" : `${gap.toFixed(0)}% OFF`}
                        </div>
                        <div style={{ fontSize: "8px", color: "#3a3a3a", marginTop: "2px" }}>{c.total} trades | ${c.total_pnl}</div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          )}

          {/* ── INSTITUTIONAL PULSE ── */}
          {activeTab === "news" && !loading && newsData && (
            <div>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "14px" }}>
                <div style={{ fontSize: "10px", color: "#5C5C5C", maxWidth: "80%" }}>
                  Real-time sentiment and headlines from our proprietary intelligence stream. Processed by institutional models for trade screening.
                </div>
                {connected && (
                  <button 
                    onClick={() => send("refresh_news")}
                    className="btn"
                    style={{ 
                      fontSize: "9px", 
                      padding: "6px 12px", 
                      background: "#121212", 
                      border: "1px solid #D4AF3744", 
                      color: "#D4AF37",
                      fontWeight: "700",
                      letterSpacing: "1px"
                    }}
                  >
                    REFRESH PULSE
                  </button>
                )}
              </div>
              
              {newsData.error ? (
                <div style={{ fontSize: "11px", color: "#FF1744", padding: "20px", textAlign: "center" }}>{newsData.error}</div>
              ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
                  {/* Sentiment Summary Dashboard */}
                  <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(130px, 1fr))", gap: "10px", marginBottom: "20px" }}>
                    <div style={{ background: "#0A0A0A", borderRadius: "8px", padding: "12px", border: "1px solid #D4AF3733", textAlign: "center" }}>
                      <div style={{ fontSize: "8px", color: "#3a3a3a", letterSpacing: "1px", marginBottom: "4px" }}>COMPOSITE SCORE</div>
                      <div style={{ fontSize: "18px", fontWeight: "700", color: newsData.sentiment_score >= 0 ? "#00E676" : "#FF1744" }}>
                        {newsData.sentiment_score > 0 ? "+" : ""}{newsData.sentiment_score}
                      </div>
                      <div style={{ fontSize: "8px", color: "#5C5C5C", marginTop: "2px" }}>{newsData.sentiment?.replace("_", " ").toUpperCase()}</div>
                    </div>
                    <div style={{ background: "#0A0A0A", borderRadius: "8px", padding: "12px", border: "1px solid #1e1e1e", textAlign: "center" }}>
                      <div style={{ fontSize: "8px", color: "#3a3a3a", letterSpacing: "1px", marginBottom: "4px" }}>FEAR & GREED</div>
                      <div style={{ fontSize: "18px", fontWeight: "700", color: "#D4AF37" }}>
                        {newsData.fear_greed?.value}
                      </div>
                      <div style={{ fontSize: "8px", color: "#5C5C5C", marginTop: "2px" }}>{newsData.fear_greed?.classification?.toUpperCase()}</div>
                    </div>
                    {newsData.social_pulse && (
                      <div style={{ background: "#0A0A0A", borderRadius: "8px", padding: "12px", border: "1px solid #1e1e1e", textAlign: "center" }}>
                        <div style={{ fontSize: "8px", color: "#3a3a3a", letterSpacing: "1px", marginBottom: "4px" }}>SOCIAL PULSE</div>
                        <div style={{ fontSize: "18px", fontWeight: "700", color: "#60A5FA" }}>
                          {newsData.social_pulse.galaxy_score}
                        </div>
                        <div style={{ fontSize: "8px", color: "#5C5C5C", marginTop: "2px" }}>{newsData.social_pulse.sentiment?.toUpperCase()}</div>
                      </div>
                    )}
                    {newsData.macro_event && newsData.macro_event !== "none" && (
                      <div style={{ background: "#C0392B15", borderRadius: "8px", padding: "12px", border: "1px solid #C0392B44", textAlign: "center" }}>
                        <div style={{ fontSize: "8px", color: "#FF1744", letterSpacing: "1px", marginBottom: "4px" }}>MACRO ALERT</div>
                        <div style={{ fontSize: "11px", fontWeight: "700", color: "#FF1744" }}>
                          {newsData.macro_event}
                        </div>
                        <div style={{ fontSize: "8px", color: "#FF174488", marginTop: "2px" }}>DANGER ZONE</div>
                      </div>
                    )}
                  </div>
                  
                  {/* Adversary Security Dashboard */}
                  {adversaryStats && (adversaryStats.total_vetoes > 0 || adversaryStats.total_reduces > 0) && (
                    <div style={{ padding: "16px", background: "#FF174408", border: "1px solid #FF174422", borderRadius: "10px", marginBottom: "20px" }}>
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "12px" }}>
                        <div style={{ fontSize: "9px", color: "#FF1744", fontWeight: "700", letterSpacing: "1px" }}>ADVERSARY SECURITY MITIGATION</div>
                        <div className="tag" style={{ background: "#FF174415", color: "#FF1744", fontSize: "8px", border: "1px solid #FF174433" }}>PROTECTION ACTIVE</div>
                      </div>
                      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "14px", marginBottom: "14px" }}>
                        <div style={{ background: "#000000", padding: "10px", borderRadius: "6px", border: "1px solid #1e1e1e" }}>
                          <div style={{ fontSize: "8px", color: "#5C5C5C", marginBottom: "4px" }}>SIGNALS SUPPRESSED</div>
                          <div style={{ fontSize: "20px", fontWeight: "700", color: "#FF1744" }}>{adversaryStats.total_vetoes}</div>
                        </div>
                        <div style={{ background: "#000000", padding: "10px", borderRadius: "6px", border: "1px solid #1e1e1e" }}>
                          <div style={{ fontSize: "8px", color: "#5C5C5C", marginBottom: "4px" }}>SIZE REDUCTIONS</div>
                          <div style={{ fontSize: "20px", fontWeight: "700", color: "#D4AF37" }}>{adversaryStats.total_reduces}</div>
                        </div>
                      </div>
                      {adversaryStats.latest_vetoes?.length > 0 && (
                        <div>
                          <div style={{ fontSize: "8px", color: "#3a3a3a", letterSpacing: "1px", marginBottom: "8px" }}>LATEST SUPPRESSED SIGNALS</div>
                          <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
                            {adversaryStats.latest_vetoes.map((v, idx) => (
                              <div key={idx} style={{ display: "flex", justifyContent: "space-between", alignItems: "start", fontSize: "10px", borderBottom: "1px solid #1e1e1e", paddingBottom: "6px" }}>
                                <div style={{ display: "flex", flexDirection: "column" }}>
                                  <span style={{ color: "#D4D4D4", fontWeight: "700" }}>{v.symbol}</span>
                                  <span style={{ color: "#5C5C5C", fontSize: "9px", marginTop: "2px" }}>{v.reasoning?.substring(0, 100)}...</span>
                                </div>
                                <span style={{ color: "#3a3a3a", fontSize: "8px" }}>{v.ts?.split(" ")[1]}</span>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  )}

                  {(newsData.headlines || []).length === 0 ? (
                    <div style={{ fontSize: "10px", color: "#2a2a2a", padding: "20px", textAlign: "center" }}>No headlines found</div>
                  ) : (
                    (newsData.headlines || []).map((h, i) => (
                      <div 
                        key={i} 
                        onClick={() => setSelectedNews(h)}
                        style={{ 
                          background: "#0A0A0A", 
                          borderRadius: "8px", 
                          padding: "16px", 
                          border: "1px solid #1e1e1e",
                          textDecoration: "none",
                          display: "block",
                          transition: "all 0.2s ease",
                          cursor: "pointer"
                        }}
                        onMouseEnter={(e) => {
                          e.currentTarget.style.borderColor = "#D4AF3744";
                          e.currentTarget.style.background = "#0F0F0F";
                          e.currentTarget.style.transform = "translateY(-1px)";
                        }}
                        onMouseLeave={(e) => {
                          e.currentTarget.style.borderColor = "#1e1e1e";
                          e.currentTarget.style.background = "#0A0A0A";
                          e.currentTarget.style.transform = "none";
                        }}
                      >
                        <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "8px", alignItems: "flex-start" }}>
                          <span style={{ fontSize: "12px", fontWeight: "700", color: "#D4AF37", lineHeight: "1.5", paddingRight: "10px" }}>{h.title}</span>
                          <span style={{ fontSize: "9px", color: "#3a3a3a", whiteSpace: "nowrap", marginTop: "2px" }}>
                            {newsData.last_updated}
                          </span>
                        </div>
                        {h.description && (
                          <div style={{ fontSize: "11px", color: "#888", lineHeight: "1.7", marginBottom: "12px", display: "-webkit-box", WebkitLineClamp: "3", WebkitBoxOrient: "vertical", overflow: "hidden" }}>
                            {h.description}
                          </div>
                        )}
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                          <div style={{ display: "flex", gap: "8px" }}>
                            <span className="tag" style={{ background: "#D4AF3715", color: "#D4AF37", fontSize: "9px", border: "1px solid #D4AF3733" }}>
                              SENTIMENT: {h.sentiment?.toUpperCase() || "NEUTRAL"}
                            </span>
                          </div>
                          <span style={{ fontSize: "9px", color: "#5C5C5C", fontWeight: "600", letterSpacing: "1px" }}>VIEW DETAILS &rarr;</span>
                        </div>
                      </div>
                    ))
                  )}
                </div>
              )}
            </div>
          )}

          {/* ── BACKTEST ── */}
          {activeTab === "backtest" && !loading && (
            <div>
              <div className="section-label" style={{ marginBottom: "12px" }}>STRATEGY EVALUATION</div>
              <div style={{ display: "flex", gap: "10px", flexWrap: "wrap", alignItems: "flex-end", marginBottom: "14px" }}>
                {[
                  { label: "COIN", key: "symbol", type: "select", options: ["BTC", "ETH", "SOL", "LINK", "DOGE", "AVAX"] },
                  { label: "DAYS", key: "days", type: "number", min: 7, max: 365 },
                  { label: "TP (ATR x)", key: "tp", type: "number", step: 0.5, min: 1 },
                  { label: "SL (ATR x)", key: "sl", type: "number", step: 0.25, min: 0.5 },
                  { label: "MIN CONFLUENCE", key: "confluence", type: "number", min: 1, max: 20 },
                  { label: "MIN R:R", key: "rr", type: "number", step: 0.2, min: 1 },
                ].map(f => (
                  <div key={f.key}>
                    <div style={{ fontSize: "8px", color: "#3a3a3a", letterSpacing: "1px", marginBottom: "3px" }}>{f.label}</div>
                    {f.type === "select" ? (
                      <select value={btParams[f.key]} onChange={e => setBtParams(p => ({ ...p, [f.key]: e.target.value }))}
                        className="mono-text"
                        style={{ fontSize: "10px", padding: "6px 10px", borderRadius: "4px", border: "1px solid #2a2a2a", background: "#111111", color: "#D4D4D4", outline: "none" }}>
                        {f.options.map(o => <option key={o} value={o}>{o}</option>)}
                      </select>
                    ) : (
                      <input type="number" value={btParams[f.key]} onChange={e => setBtParams(p => ({ ...p, [f.key]: +e.target.value }))}
                        className="mono-text"
                        min={f.min} max={f.max} step={f.step || 1}
                        style={{ fontSize: "10px", padding: "6px 10px", borderRadius: "4px", border: "1px solid #2a2a2a", background: "#111111", color: "#D4D4D4", outline: "none", width: "70px" }} />
                    )}
                  </div>
                ))}
                <button className="btn btn-p" onClick={runBacktest} disabled={backtestLoading} style={{ alignSelf: "flex-end" }}>
                  {backtestLoading ? <span className="blink">PROCESSING...</span> : "EVALUATE STRATEGY"}
                </button>
              </div>

              {backtestResult && !backtestResult.error && (
                <div>
                  <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(120px, 1fr))", gap: "8px", marginBottom: "14px" }}>
                    {[
                      { label: "RETURN", val: `${backtestResult.return_pct >= 0 ? "+" : ""}${backtestResult.return_pct}%`, color: backtestResult.return_pct >= 0 ? "#00E676" : "#FF1744" },
                      { label: "TOTAL P&L", val: `${backtestResult.total_pnl >= 0 ? "+" : ""}$${backtestResult.total_pnl}`, color: backtestResult.total_pnl >= 0 ? "#00E676" : "#FF1744" },
                      { label: "SAMPLES", val: backtestResult.total_trades, color: "#D4D4D4" },
                      { label: "ACCURACY", val: `${backtestResult.win_rate}%`, color: backtestResult.win_rate >= 50 ? "#00E676" : "#FF1744" },
                      { label: "AVG WIN", val: `+$${backtestResult.avg_win}`, color: "#00E676" },
                      { label: "AVG LOSS", val: `$${backtestResult.avg_loss}`, color: "#FF1744" },
                      { label: "MAX DD", val: `${backtestResult.max_drawdown_pct}%`, color: backtestResult.max_drawdown_pct > 15 ? "#FF1744" : "#ff9900" },
                      { label: "PROFIT FACTOR", val: backtestResult.profit_factor, color: backtestResult.profit_factor >= 1.5 ? "#00E676" : "#ff9900" },
                    ].map(s => (
                      <div key={s.label} style={{ background: "#0A0A0A", borderRadius: "5px", padding: "8px 10px", textAlign: "center" }}>
                        <div style={{ fontSize: "8px", color: "#3a3a3a", marginBottom: "3px" }}>{s.label}</div>
                        <div style={{ fontSize: "13px", fontWeight: "700", color: s.color }}>{s.val}</div>
                      </div>
                    ))}
                  </div>
                  {backtestResult.trades?.length > 0 && (
                    <div style={{ maxHeight: "200px", overflowY: "auto" }}>
                      {backtestResult.trades.map((t, i) => (
                        <div key={i} className="trow" style={{ fontSize: "10px" }}>
                          <div>
                            <span className="tag" style={{ background: t.side === "buy" ? "#00E67618" : "#FF174418", color: t.side === "buy" ? "#00E676" : "#FF1744", marginRight: "4px" }}>
                              {t.side?.toUpperCase()}
                            </span>
                            <span style={{ color: "#D4D4D4" }}>${t.entry?.toLocaleString()} → ${t.exit?.toLocaleString()}</span>
                          </div>
                          <div style={{ textAlign: "right" }}>
                            <span style={{ fontWeight: "700", color: t.win ? "#00E676" : "#FF1744" }}>{t.pnl >= 0 ? "+" : ""}${t.pnl}</span>
                            <span style={{ color: "#3a3a3a", marginLeft: "6px", fontSize: "9px" }}>{t.reason}</span>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
              {backtestResult?.error && (
                <div style={{ fontSize: "11px", color: "#FF1744", padding: "16px", textAlign: "center" }}>{backtestResult.error}</div>
              )}
              {!backtestResult && (
                <div style={{ textAlign: "center", padding: "30px", color: "#2a2a2a", fontSize: "11px" }}>
                  Configure parameters and click EVALUATE STRATEGY to test your logic against historical data
                </div>
              )}
            </div>
          )}
        </div>

        {/* Business Clarification & Legal Disclaimer */}
        <div style={{ 
          marginTop: "20px", 
          padding: "16px", 
          background: "rgba(212,175,55,0.03)", 
          border: "1px solid rgba(212,175,55,0.1)",
          borderRadius: "8px",
          fontSize: "10px",
          color: "#5C5C5C",
          lineHeight: "1.6",
          textAlign: "center",
          fontStyle: "italic",
          maxWidth: "100%",
          boxSizing: "border-box"
        }}>
          <div style={{ color: "#D4AF37", fontWeight: "700", marginBottom: "4px", letterSpacing: "1px", fontStyle: "normal" }}>LEGAL NOTICE & DISCLOSURE</div>
          "To clarify, our business is a technology provider offering research and execution software. We are not a cryptocurrency exchange, fund manager, or investment advisor. We sell monthly software subscriptions that provide users with analytical tools to manage their own independent trading accounts."
        </div>
      </div>

      {/* Loss notification toast */}
      {lossToast && (
        <div
          style={{
            position: "fixed", bottom: "60px", left: "50%", transform: "translateX(-50%)",
            background: "#1a0a0a", border: "1px solid #C0392B55", borderRadius: "8px",
            padding: "12px 20px", boxShadow: "0 4px 24px rgba(192,57,43,0.3)",
            fontSize: "13px", fontWeight: "800",
            color: "#FF1744", letterSpacing: "2px", zIndex: 9999,
            animation: "lossToastIn 0.3s ease-out",
          }}
          role="alert"
        >
          {lossToast.msg}
        </div>
      )}

      {/* ══ MOBILE NAV DRAWER (hamburger) ══ */}

      {/* ══ FOOTER — User nav + Status bar ══ */}
      <div className="status-bar" style={{
        position: "fixed", bottom: 0, left: 0, right: 0, zIndex: 9000,
        display: "flex", flexWrap: "nowrap", alignItems: "center", justifyContent: "space-between", gap: "8px",
        padding: "6px 12px",
        minHeight: "44px",
        background: "rgba(10,10,10,0.6)", borderTop: "1px solid rgba(212,175,55,0.12)",
        backdropFilter: "blur(40px) saturate(1.6)", WebkitBackdropFilter: "blur(40px) saturate(1.6)",
        boxShadow: "0 -4px 32px rgba(0,0,0,0.3), inset 0 1px 0 rgba(255,255,255,0.04)",
      }}>
        {/* Left: user identity */}
        <span className="status-bar-user" style={{ fontSize: "10px", color: "#5C5C5C", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", maxWidth: "120px", flexShrink: 0 }}>
          {profile?.display_name || user?.email?.split("@")[0] || ""}
        </span>

        {/* Center: status badges — hidden on mobile, revealed by CSS */}
        <div className="status-bar-badges" style={{ display: "flex", gap: "5px", flexWrap: "nowrap", alignItems: "center", justifyContent: "center", flex: 1, minWidth: 0, overflow: "hidden" }}>
          {[
            { label: "BACKEND", ok: connected, on: "LIVE", off: "OFFLINE", dotColor: connected ? "#00E676" : "#FF1744", textColor: connected ? "#00E676" : "#FF1744" },
            { label: "COINBASE", ok: cbLive, on: "REAL-TIME", off: "REST", dotColor: cbLive ? "#00E676" : connected ? "#ff9900" : "#FF1744", textColor: cbLive ? "#00E676" : connected ? "#ff9900" : "#FF1744" },
            { label: "BINANCE", ok: binanceEnabled, on: "SPOT+FUT", off: "OFF", dotColor: binanceEnabled ? "#00E676" : "#FF1744", textColor: binanceEnabled ? "#00E676" : "#3a3a3a" },
            {label: "KRAKEN", ok: krakenEnabled, on: "SPOT+FUT", off: "OFF", dotColor: krakenEnabled ? "#00E676" : "#FF1744", textColor: krakenEnabled ? "#00E676" : "#3a3a3a" },
            { label: "ENGINE", ok: hasEngine, on: "READY", off: "ERROR", dotColor: hasEngine ? "#00E676" : "#ff9900", textColor: hasEngine ? "#00E676" : "#ff9900" },
            { label: "MODE", ok: isLiveMode, on: "LIVE", off: "PAPER", dotColor: isLiveMode ? "#FF1744" : "#ff9900", textColor: isLiveMode ? "#FF1744" : "#ff9900" },
            { label: "AGENTKIT", ok: agentKit.agentkit_ready, on: "ON-CHAIN", off: paperMode ? "PAPER" : "OFFLINE", dotColor: agentKit.agentkit_ready ? "#00E676" : paperMode ? "#ff9900" : "#FF1744", textColor: agentKit.agentkit_ready ? "#00E676" : "#3a3a3a" },
          ].map(s => (
            <div key={s.label} style={{ display: "flex", gap: "3px", alignItems: "center", background: "#111111", border: "1px solid #1e1e1e", borderRadius: "4px", padding: "2px 6px", flexShrink: 0 }} role="status" aria-label={`${s.label}: ${s.ok ? s.on : s.off}`}>
              <span style={{ fontSize: "6px", color: "#5C5C5C", letterSpacing: "0.3px" }}>{s.label}</span>
              <span style={{ fontSize: "8px", fontWeight: "700", color: s.textColor, display: "flex", alignItems: "center", gap: "2px" }}>
                <span style={{ width: "6px", height: "6px", borderRadius: "50%", background: s.dotColor, boxShadow: `0 0 5px ${s.dotColor}88`, display: "inline-block", flexShrink: 0 }} />
                {s.ok ? s.on : s.off}
              </span>
            </div>
          ))}
          {directionBias !== "both" && (
            <div style={{ display: "flex", gap: "3px", alignItems: "center", background: "#111111", border: "1px solid #1e1e1e", borderRadius: "4px", padding: "2px 6px", flexShrink: 0 }}>
              <span style={{ fontSize: "6px", color: "#5C5C5C" }}>DIR</span>
                <span style={{ fontSize: "8px", fontWeight: "700", color: directionBias === "long" ? "#00E676" : "#FF1744", display: "flex", alignItems: "center", gap: "2px" }}>
                  {directionBias === "long" ? <ArrowUp size={8} /> : <ArrowDown size={8} />}
                  {directionBias === "long" ? "LONG" : "SHORT"}
                </span>
            </div>
          )}
          {price > 0 && <span style={{ fontSize: "8px", color: priceAge > 60 ? "#ff9900" : "#5C5C5C", flexShrink: 0 }}>price <AnimatedNumber value={priceAge} format={(v) => `${Math.round(v)}s`} duration={100} /> ago</span>}
          {wsRetrying && !connected && <span style={{ fontSize: "8px", color: "#ff9900", flexShrink: 0 }}>Reconnecting…</span>}
        </div>

        {/* Right: nav links (desktop) + hamburger (mobile) */}
        <div style={{ display: "flex", alignItems: "center", gap: "6px", flexShrink: 0 }}>
          {/* Desktop nav links — hidden on mobile by CSS */}
          <div className="status-bar-badges" style={{ display: "flex", alignItems: "center", gap: "6px" }}>
            <button onClick={() => navigate("/history")} className="btn btn-d" style={{ fontSize: "10px", padding: "3px 10px", minHeight: "24px" }}>HISTORY</button>
            <button onClick={() => navigate("/billing")} className="btn btn-d" style={{ fontSize: "10px", padding: "3px 10px", minHeight: "24px" }}>BILLING</button>
            <button onClick={() => navigate("/settings")} className="btn btn-d" style={{ fontSize: "10px", padding: "3px 10px", minHeight: "24px", color: "#D4AF37" }}>SETTINGS</button>
            {isAdminEmail(user?.email) && (
              <button onClick={() => navigate("/admin")} className="btn btn-p" style={{ fontSize: "10px", padding: "3px 10px", minHeight: "24px", color: colors.dark, background: colors.gold }}>ADMIN</button>
            )}
            <a href="mailto:feichangfuyou@doyou.trade" className="btn btn-d" style={{ fontSize: "10px", padding: "3px 10px", minHeight: "24px", textDecoration: "none" }} title="Contact feichangfuyou@doyou.trade">CONTACT</a>
            <button onClick={signOut} className="btn btn-d" style={{ fontSize: "10px", padding: "3px 10px", minHeight: "24px" }}>Sign Out</button>
          </div>
        </div>
      </div>
      {/* ── NEWS DETAIL MODAL ── */}
      {selectedNews && (
        <div className="glass-overlay fadein" style={{ position: "fixed", inset: 0, zIndex: 10000, display: "flex", alignItems: "center", justifyContent: "center", padding: "20px" }} onClick={() => setSelectedNews(null)}>
          <div className="glass-heavy" style={{ maxWidth: "600px", width: "100%", padding: "40px", position: "relative" }} onClick={e => e.stopPropagation()}>
            <button 
              onClick={() => setSelectedNews(null)}
              style={{ position: "absolute", top: "20px", right: "20px", background: "none", border: "none", color: "#5C5C5C", fontSize: "14px", cursor: "pointer" }}
            >
              &times;
            </button>
            <div className="section-label" style={{ marginBottom: "16px", color: "#D4AF37" }}>INTELLIGENCE REPORT</div>
            <h2 style={{ fontSize: "20px", fontWeight: "700", color: "#fff", lineHeight: "1.4", marginBottom: "20px", letterSpacing: "0.5px" }}>
              {selectedNews.title}
            </h2>
            <div style={{ display: "flex", gap: "10px", marginBottom: "24px" }}>
              <span className="tag" style={{ background: "#D4AF3722", color: "#D4AF37" }}>
                SENTIMENT: {selectedNews.sentiment?.toUpperCase() || "NEUTRAL"}
              </span>
              <span className="tag" style={{ background: "#111", color: "#5C5C5C" }}>
                {newsData.last_updated}
              </span>
            </div>
            <div style={{ fontSize: "14px", color: "#AAA", lineHeight: "1.8", marginBottom: "32px", maxHeight: "300px", overflowY: "auto", paddingRight: "10px" }}>
              {selectedNews.description || "No extended description available for this headline."}
            </div>
            <div style={{ display: "flex", gap: "12px" }}>
              <button className="btn btn-p" onClick={() => setSelectedNews(null)} style={{ flex: 1 }}>ACKNOWLEDGE & CLOSE</button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
