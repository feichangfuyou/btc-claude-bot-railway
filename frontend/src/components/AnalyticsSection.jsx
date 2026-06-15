import { useState, useEffect, useCallback } from "react";
import Skeleton from "../Skeleton.jsx";
import { useAuthHeaders } from "../hooks/useAuthHeaders.js";
import { colors } from "../theme.js";
import { RefreshCcw } from "lucide-react";

const REGIME_COLORS = {
  trending_up: colors.success,
  trending_down: colors.error,
  ranging: colors.gold,
  chaotic: colors.warning,
};

export function AnalyticsSection({ connected, log, lossToast, news, send }) {
  const getAuthHeaders = useAuthHeaders();
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
        const type = resp.headers.get("content-type") || "";
        if (!type.includes("application/json")) {
          throw new Error(
            resp.ok
              ? `Expected JSON from ${url} but got ${type || "no content-type"} (status ${resp.status}). Backend may be returning the SPA fallback.`
              : `Backend unreachable or returned non-JSON (status ${resp.status}, type ${type || "none"}). Is the server running on port 8000?`
          );
        }
        if (!resp.ok) {
          const body = await resp.json().catch(() => ({}));
          throw new Error(body.error || `HTTP ${resp.status}`);
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

  const activeTabLabel = tabs.find((t) => t.id === activeTab)?.label || "ANALYTICS";

  return (
    <>
      <div className="tab-logs analytics-section section-gap">
        <div className="dash-panel analytics-panel">
          <div className="dash-panel__header">
            <span className="section-label" style={{ marginBottom: 0 }}>{activeTabLabel}</span>
            <div className="dash-panel__header-actions">
              <button
                type="button"
                className="btn btn-d btn-icon analytics-tab-bar__refresh"
                onClick={() => fetchData(activeTab)}
                aria-label="Refresh analytics data"
              >
                <RefreshCcw size={12} />
              </button>
            </div>
          </div>

          <div className="analytics-tab-bar" role="tablist" aria-label="Analytics views">
            {tabs.map((t) => (
              <button
                key={t.id}
                type="button"
                role="tab"
                aria-selected={activeTab === t.id}
                onClick={() => setActiveTab(t.id)}
                className={`btn btn-d analytics-tab-bar__btn${activeTab === t.id ? " analytics-tab-bar__btn--active" : ""}`}
              >
                {t.label}
              </button>
            ))}
          </div>

          <div className="analytics-panel__body">
          {loading && (
            <div className="stack stack--sm" style={{ padding: "8px 0" }}>
              <Skeleton width="40%" height={14} />
              <Skeleton width="100%" height={80} />
              <Skeleton width="60%" height={14} />
              <Skeleton width="100%" height={60} />
            </div>
          )}

          {/* ── EQUITY CURVE ── */}
          {activeTab === "equity" && !loading && equityData && (
            <div>
              {equityData.curve?.length > 0 ? (
                <div>
                  <div className="session-row">
                    {equityData.sessions?.slice(0, 7).map((s) => (
                      <div key={s.date} className="session-chip">
                        <div className="session-chip__date">{s.date}</div>
                        <div className="session-chip__pnl" style={{ color: s.total_pnl >= 0 ? colors.success : colors.error }}>
                          {s.total_pnl >= 0 ? "+" : ""}${s.total_pnl?.toFixed(2)}
                        </div>
                        <div className="session-chip__meta">{s.trades_taken} trades | {s.wins}W/{s.losses}L</div>
                      </div>
                    ))}
                  </div>
                  <div className="equity-chart">
                    {(() => {
                      const pts = equityData.curve;
                      const balances = pts.map((p) => p.balance);
                      const mn = Math.min(...balances);
                      const mx = Math.max(...balances);
                      const range = mx - mn || 1;
                      const step = Math.max(1, Math.floor(pts.length / 80));
                      const sampled = pts.filter((_, i) => i % step === 0 || i === pts.length - 1);
                      return sampled.map((p, i) => {
                        const h = Math.max(2, ((p.balance - mn) / range) * 110);
                        const isUp = i > 0 ? p.balance >= sampled[i - 1].balance : true;
                        return (
                          <div
                            key={i}
                            title={`${p.ts}: $${p.balance.toFixed(2)}`}
                            className="equity-chart__bar"
                            style={{ height: `${h}px`, background: isUp ? "#00E67688" : "#FF174488" }}
                          />
                        );
                      });
                    })()}
                  </div>
                  <div className="equity-chart__axis">
                    <span>{equityData.curve[0]?.ts?.split(" ")[0]}</span>
                    <span>{equityData.curve[equityData.curve.length - 1]?.ts?.split(" ")[0]}</span>
                  </div>
                </div>
              ) : (
                <div className="dash-panel__empty">
                  No snapshots yet — run the bot for a few hours to build the equity curve
                </div>
              )}
            </div>
          )}

          {/* ── TRADE ANALYTICS ── */}
          {activeTab === "analytics" && !loading && analyticsData && (
            <div className="analytics-grid">
              <div>
                <div className="analytics-block__title">BY REGIME</div>
                {Object.entries(analyticsData.regime || {}).map(([regime, data]) => (
                  <div key={regime} className="row" style={{ fontSize: "10px" }}>
                    <span style={{ color: REGIME_COLORS[regime] || colors.muted, fontWeight: "700", textTransform: "uppercase" }}>{regime}</span>
                    <span>
                      <span style={{ color: data.win_rate >= 50 ? colors.success : colors.error, fontWeight: "700" }}>{data.win_rate}% ACCURACY</span>
                      <span style={{ color: colors.dim, marginLeft: "6px" }}>{data.total} SAMPLES</span>
                      <span style={{ color: data.total_pnl >= 0 ? colors.success : colors.error, marginLeft: "6px" }}>{data.total_pnl >= 0 ? "+" : ""}${data.total_pnl}</span>
                    </span>
                  </div>
                ))}
              </div>
              <div>
                <div className="analytics-block__title">BEST HOURS (UTC)</div>
                {(analyticsData.hourly || []).slice(0, 6).map((h) => (
                  <div key={h.hour_of_day} className="row" style={{ fontSize: "10px" }}>
                    <span style={{ color: colors.text }}>{String(h.hour_of_day).padStart(2, "0")}:00</span>
                    <span>
                      <span style={{ color: h.win_rate >= 50 ? colors.success : colors.error, fontWeight: "700" }}>{h.win_rate}% ACC</span>
                      <span style={{ color: colors.dim, marginLeft: "6px" }}>avg ${h.avg_pnl}</span>
                    </span>
                  </div>
                ))}
              </div>
              <div>
                <div className="analytics-block__title">BY SIZE</div>
                {(analyticsData.sizing || []).map((s) => (
                  <div key={s.size_band} className="row" style={{ fontSize: "10px" }}>
                    <span style={{ color: colors.text }}>{s.size_band.replace("_", " ")}</span>
                    <span>
                      <span style={{ color: s.win_rate >= 50 ? colors.success : colors.error, fontWeight: "700" }}>{s.win_rate}% ACC</span>
                      <span style={{ color: colors.dim, marginLeft: "6px" }}>{s.total} SAMPLES</span>
                    </span>
                  </div>
                ))}
              </div>
              <div>
                <div className="analytics-block__title">BY CONFIDENCE</div>
                {(analyticsData.confidence || []).map((c) => (
                  <div key={c.confidence_band} className="row" style={{ fontSize: "10px" }}>
                    <span style={{ color: colors.gold }}>{c.confidence_band.replace("_", " ")}</span>
                    <span>
                      <span style={{ color: c.win_rate >= 50 ? colors.success : colors.error, fontWeight: "700" }}>{c.win_rate}% ACC</span>
                      <span style={{ color: colors.dim, marginLeft: "6px" }}>avg ${c.avg_pnl}</span>
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* ── DECISION ENGINE ── */}
          {activeTab === "memory" && !loading && memoryData && (
            <div className="analytics-grid">
              <div>
                <div className="analytics-block__title">
                  ACTIVE HEURISTICS ({memoryData.total_rules || 0})
                </div>
                {(memoryData.rules || []).length === 0 ? (
                  <div className="dash-panel__empty" style={{ padding: "12px 0" }}>No rules learned yet — need 5+ trades</div>
                ) : (
                  (memoryData.rules || []).slice(0, 10).map((rule) => (
                    <div key={rule.rule_key} className="memory-rule">
                      <div className="memory-rule__head">
                        <span className="tag" style={{ background: rule.rule_type === "avoid" ? "#FF174418" : "#00E67618", color: rule.rule_type === "avoid" ? colors.error : colors.success, fontSize: "8px" }}>
                          {rule.rule_type?.toUpperCase()}
                        </span>
                        <span style={{ fontSize: "8px", color: colors.dim }}>
                          {rule.sample_size} samples | {rule.win_rate}% ACC
                        </span>
                      </div>
                      <div className="memory-rule__desc">{rule.description}</div>
                    </div>
                  ))
                )}
              </div>
              <div>
                <div className="analytics-block__title">
                  PATTERN PERFORMANCE ({memoryData.total_trades || 0} SAMPLES analyzed)
                </div>
                {(memoryData.patterns || []).length === 0 ? (
                  <div className="dash-panel__empty" style={{ padding: "12px 0" }}>No pattern data yet</div>
                ) : (
                  (memoryData.patterns || []).slice(0, 12).map((p, i) => (
                    <div key={i} className="row" style={{ fontSize: "10px" }}>
                      <div>
                        <span style={{ color: colors.text }}>{p.pattern}</span>
                        <span style={{ color: colors.dim, fontSize: "8px", marginLeft: "4px" }}>{p.symbol} {p.side} ({p.regime})</span>
                      </div>
                      <span>
                        <span style={{ color: p.win_rate >= 50 ? colors.success : colors.error, fontWeight: "700" }}>{p.win_rate}%</span>
                        <span style={{ color: colors.dim, marginLeft: "4px" }}>{p.total}x</span>
                      </span>
                    </div>
                  ))
                )}
              </div>
            </div>
          )}

          {/* ── CONFIDENCE CALIBRATION ── */}
          {activeTab === "calibration" && !loading && calibrationData && (
            <div>
              <p className="analytics-subhead">
                Does signal confidence actually predict outcome efficiency? Perfect calibration = predicted matches actual.
              </p>
              {(calibrationData.calibration || []).length === 0 ? (
                <div className="dash-panel__empty">Need more trades with confidence data</div>
              ) : (
                <div className="calibration-grid">
                  {(calibrationData.calibration || []).map((c) => {
                    const predicted = c.avg_predicted;
                    const actual = c.actual_win_rate;
                    const gap = Math.abs(predicted - actual);
                    const calibrated = gap < 10;
                    return (
                      <div key={c.predicted_band} className={`calibration-tile${calibrated ? " calibration-tile--ok" : " calibration-tile--off"}`}>
                        <div className="calibration-tile__band">PREDICTED {c.predicted_band}</div>
                        <div className="calibration-tile__value calibration-tile__value--predicted">{predicted}%</div>
                        <div className="calibration-tile__vs">vs actual</div>
                        <div className="calibration-tile__value" style={{ color: actual >= 50 ? colors.success : colors.error }}>{actual}%</div>
                        <div className="calibration-tile__status" style={{ color: calibrated ? colors.success : colors.warning }}>
                          {calibrated ? "CALIBRATED" : `${gap.toFixed(0)}% OFF`}
                        </div>
                        <div className="calibration-tile__meta">{c.total} trades | ${c.total_pnl}</div>
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
              <div className="dash-panel__header" style={{ marginBottom: "12px" }}>
                <p className="analytics-subhead" style={{ marginBottom: 0, maxWidth: "80%" }}>
                  Real-time sentiment and headlines from our proprietary intelligence stream. Processed by institutional models for trade screening.
                </p>
                {connected && (
                  <button type="button" onClick={() => send("refresh_news")} className="btn btn-p">
                    REFRESH PULSE
                  </button>
                )}
              </div>

              {newsData.error ? (
                <div className="dash-panel__empty" style={{ color: colors.error }}>{newsData.error}</div>
              ) : (
                <div className="stack stack--sm">
                  <div className="news-metrics">
                    <div className="news-metric news-metric--accent">
                      <div className="news-metric__label">COMPOSITE SCORE</div>
                      <div className="news-metric__value" style={{ color: newsData.sentiment_score >= 0 ? colors.success : colors.error }}>
                        {newsData.sentiment_score > 0 ? "+" : ""}{newsData.sentiment_score}
                      </div>
                      <div className="news-metric__sub">{newsData.sentiment?.replace("_", " ").toUpperCase()}</div>
                    </div>
                    <div className="news-metric">
                      <div className="news-metric__label">FEAR & GREED</div>
                      <div className="news-metric__value" style={{ color: colors.gold }}>
                        {newsData.fear_greed?.value}
                      </div>
                      <div className="news-metric__sub">{newsData.fear_greed?.classification?.toUpperCase()}</div>
                    </div>
                    {newsData.social_pulse && (
                      <div className="news-metric">
                        <div className="news-metric__label">SOCIAL PULSE</div>
                        <div className="news-metric__value" style={{ color: "#60A5FA" }}>
                          {newsData.social_pulse.galaxy_score}
                        </div>
                        <div className="news-metric__sub">{newsData.social_pulse.sentiment?.toUpperCase()}</div>
                      </div>
                    )}
                    {newsData.macro_event && newsData.macro_event !== "none" && (
                      <div className="news-metric news-metric--alert">
                        <div className="news-metric__label" style={{ color: colors.error }}>MACRO ALERT</div>
                        <div className="news-metric__value" style={{ color: colors.error, fontSize: "11px" }}>
                          {newsData.macro_event}
                        </div>
                        <div className="news-metric__sub" style={{ color: "rgba(255, 23, 68, 0.55)" }}>DANGER ZONE</div>
                      </div>
                    )}
                  </div>

                  {adversaryStats && (adversaryStats.total_vetoes > 0 || adversaryStats.total_reduces > 0) && (
                    <div className="adversary-panel">
                      <div className="adversary-panel__head">
                        <div className="adversary-panel__title">ADVERSARY SECURITY MITIGATION</div>
                        <span className="tag" style={{ background: "#FF174415", color: colors.error, fontSize: "8px", border: "1px solid #FF174433" }}>PROTECTION ACTIVE</span>
                      </div>
                      <div className="stat-grid">
                        <div className="stat-tile">
                          <div className="stat-tile__label">SIGNALS SUPPRESSED</div>
                          <div className="stat-tile__value" style={{ color: colors.error }}>{adversaryStats.total_vetoes}</div>
                        </div>
                        <div className="stat-tile">
                          <div className="stat-tile__label">SIZE REDUCTIONS</div>
                          <div className="stat-tile__value" style={{ color: colors.gold }}>{adversaryStats.total_reduces}</div>
                        </div>
                      </div>
                      {adversaryStats.latest_vetoes?.length > 0 && (
                        <div>
                          <div className="analytics-block__title">LATEST SUPPRESSED SIGNALS</div>
                          <div className="stack stack--sm">
                            {adversaryStats.latest_vetoes.map((v, idx) => (
                              <div key={idx} className="row" style={{ fontSize: "10px", alignItems: "flex-start" }}>
                                <div>
                                  <span style={{ color: colors.text, fontWeight: "700" }}>{v.symbol}</span>
                                  <div style={{ color: colors.muted, fontSize: "9px", marginTop: "2px" }}>{v.reasoning?.substring(0, 100)}...</div>
                                </div>
                                <span style={{ color: colors.dim, fontSize: "8px" }}>{v.ts?.split(" ")[1]}</span>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  )}

                  {(newsData.headlines || []).length === 0 ? (
                    <div className="dash-panel__empty">No headlines found</div>
                  ) : (
                    (newsData.headlines || []).map((h, i) => (
                      <button
                        key={i}
                        type="button"
                        onClick={() => setSelectedNews(h)}
                        className="news-headline"
                      >
                        <div className="news-headline__head">
                          <span className="news-headline__title">{h.title}</span>
                          <span className="news-headline__time">{newsData.last_updated}</span>
                        </div>
                        {h.description && (
                          <div className="news-headline__desc">{h.description}</div>
                        )}
                        <div className="news-headline__foot">
                          <span className="tag" style={{ background: "#D4AF3715", color: colors.gold, fontSize: "9px", border: "1px solid #D4AF3733" }}>
                            SENTIMENT: {h.sentiment?.toUpperCase() || "NEUTRAL"}
                          </span>
                          <span style={{ fontSize: "9px", color: colors.muted, fontWeight: "600", letterSpacing: "1px" }}>VIEW DETAILS →</span>
                        </div>
                      </button>
                    ))
                  )}
                </div>
              )}
            </div>
          )}

          {/* ── BACKTEST ── */}
          {activeTab === "backtest" && !loading && (
            <div>
              <div className="backtest-form">
                {[
                  { label: "COIN", key: "symbol", type: "select", options: ["BTC", "ETH", "SOL", "LINK", "DOGE", "AVAX"] },
                  { label: "DAYS", key: "days", type: "number", min: 7, max: 365 },
                  { label: "TP (ATR x)", key: "tp", type: "number", step: 0.5, min: 1 },
                  { label: "SL (ATR x)", key: "sl", type: "number", step: 0.25, min: 0.5 },
                  { label: "MIN CONFLUENCE", key: "confluence", type: "number", min: 1, max: 20 },
                  { label: "MIN R:R", key: "rr", type: "number", step: 0.2, min: 1 },
                ].map((f) => (
                  <div key={f.key}>
                    <div className="backtest-field__label">{f.label}</div>
                    {f.type === "select" ? (
                      <select
                        value={btParams[f.key]}
                        onChange={(e) => setBtParams((p) => ({ ...p, [f.key]: e.target.value }))}
                        className="mono-text backtest-input"
                      >
                        {f.options.map((o) => <option key={o} value={o}>{o}</option>)}
                      </select>
                    ) : (
                      <input
                        type="number"
                        value={btParams[f.key]}
                        onChange={(e) => setBtParams((p) => ({ ...p, [f.key]: +e.target.value }))}
                        className="mono-text backtest-input"
                        min={f.min}
                        max={f.max}
                        step={f.step || 1}
                        style={{ width: "70px" }}
                      />
                    )}
                  </div>
                ))}
                <button type="button" className="btn btn-p" onClick={runBacktest} disabled={backtestLoading}>
                  {backtestLoading ? <span className="blink">PROCESSING...</span> : "EVALUATE STRATEGY"}
                </button>
              </div>

              {backtestResult && !backtestResult.error && (
                <div>
                  <div className="backtest-stats">
                    {[
                      { label: "RETURN", val: `${backtestResult.return_pct >= 0 ? "+" : ""}${backtestResult.return_pct}%`, color: backtestResult.return_pct >= 0 ? colors.success : colors.error },
                      { label: "TOTAL P&L", val: `${backtestResult.total_pnl >= 0 ? "+" : ""}$${backtestResult.total_pnl}`, color: backtestResult.total_pnl >= 0 ? colors.success : colors.error },
                      { label: "SAMPLES", val: backtestResult.total_trades, color: colors.text },
                      { label: "ACCURACY", val: `${backtestResult.win_rate}%`, color: backtestResult.win_rate >= 50 ? colors.success : colors.error },
                      { label: "AVG WIN", val: `+$${backtestResult.avg_win}`, color: colors.success },
                      { label: "AVG LOSS", val: `$${backtestResult.avg_loss}`, color: colors.error },
                      { label: "MAX DD", val: `${backtestResult.max_drawdown_pct}%`, color: backtestResult.max_drawdown_pct > 15 ? colors.error : colors.warning },
                      { label: "PROFIT FACTOR", val: backtestResult.profit_factor, color: backtestResult.profit_factor >= 1.5 ? colors.success : colors.warning },
                    ].map((s) => (
                      <div key={s.label} className="stat-tile" style={{ textAlign: "center" }}>
                        <div className="stat-tile__label">{s.label}</div>
                        <div className="stat-tile__value" style={{ color: s.color }}>{s.val}</div>
                      </div>
                    ))}
                  </div>
                  {backtestResult.trades?.length > 0 && (
                    <div className="backtest-trades">
                      {backtestResult.trades.map((t, i) => (
                        <div key={i} className="trow" style={{ fontSize: "10px" }}>
                          <div>
                            <span className="tag" style={{ background: t.side === "buy" ? "#00E67618" : "#FF174418", color: t.side === "buy" ? colors.success : colors.error, marginRight: "4px" }}>
                              {t.side?.toUpperCase()}
                            </span>
                            <span style={{ color: colors.text }}>${t.entry?.toLocaleString()} → ${t.exit?.toLocaleString()}</span>
                          </div>
                          <div style={{ textAlign: "right" }}>
                            <span style={{ fontWeight: "700", color: t.win ? colors.success : colors.error }}>{t.pnl >= 0 ? "+" : ""}${t.pnl}</span>
                            <span style={{ color: colors.dim, marginLeft: "6px", fontSize: "9px" }}>{t.reason}</span>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
              {backtestResult?.error && (
                <div className="dash-panel__empty" style={{ color: colors.error }}>{backtestResult.error}</div>
              )}
              {!backtestResult && (
                <div className="dash-panel__empty">
                  Configure parameters and click EVALUATE STRATEGY to test your logic against historical data
                </div>
              )}
            </div>
          )}
          </div>

          <div className="analytics-disclaimer">
            <div className="analytics-disclaimer__title">LEGAL NOTICE & DISCLOSURE</div>
            &ldquo;To clarify, our business is a technology provider offering research and execution software. We are not a cryptocurrency exchange, fund manager, or investment advisor. We sell monthly software subscriptions that provide users with analytical tools to manage their own independent trading accounts.&rdquo;
          </div>
        </div>
      </div>

      {/* Loss notification toast */}
      {lossToast && (
        <div
          style={{
            position: "fixed", bottom: "calc(var(--app-tabbar-height, 56px) + env(safe-area-inset-bottom) + 12px)", left: "50%", transform: "translateX(-50%)",
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
