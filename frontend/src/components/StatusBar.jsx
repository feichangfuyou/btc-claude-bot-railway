import AnimatedNumber from "../AnimatedNumber.jsx";

export function StatusBar({
  user,
  profile,
  connected,
  cbLive,
  krakenEnabled,
  binanceEnabled,
  isLiveMode,
  price,
  priceAge,
}) {
  const badges = [
    { label: "BACKEND", ok: connected, on: "LIVE", off: "OFF", dotColor: connected ? "#00E676" : "#FF1744", textColor: connected ? "#00E676" : "#FF1744" },
    { label: "COINBASE", ok: cbLive, on: "RT", off: "REST", dotColor: cbLive ? "#00E676" : connected ? "#ff9900" : "#FF1744", textColor: cbLive ? "#00E676" : connected ? "#ff9900" : "#FF1744" },
    { label: "BINANCE", ok: binanceEnabled, on: "ON", off: "OFF", dotColor: binanceEnabled ? "#00E676" : "#FF1744", textColor: binanceEnabled ? "#00E676" : "#3a3a3a" },
    { label: "KRAKEN", ok: krakenEnabled, on: "ON", off: "OFF", dotColor: krakenEnabled ? "#00E676" : "#FF1744", textColor: krakenEnabled ? "#00E676" : "#3a3a3a" },
    { label: "MODE", ok: isLiveMode, on: "LIVE", off: "PAPER", dotColor: isLiveMode ? "#FF1744" : "#ff9900", textColor: isLiveMode ? "#FF1744" : "#ff9900" },
  ];

  return (
    <div className="app-status-bar" role="status" aria-label="System status">
      <span className="app-status-bar__user">
        {profile?.display_name || user?.email?.split("@")[0] || ""}
      </span>
      <div className="app-status-bar__badges">
        {badges.map((s) => (
          <div key={s.label} className="app-status-bar__badge" aria-label={`${s.label}: ${s.ok ? s.on : s.off}`}>
            <span className="app-status-bar__dot" style={{ background: s.dotColor, boxShadow: `0 0 4px ${s.dotColor}88` }} />
            <span style={{ color: s.textColor }}>{s.ok ? s.on : s.off}</span>
          </div>
        ))}
        {price > 0 && (
          <span className="app-status-bar__price-age" style={{ color: priceAge > 60 ? "#ff9900" : "#5C5C5C" }}>
            <AnimatedNumber value={priceAge} format={(v) => `${Math.round(v)}s`} duration={100} />
          </span>
        )}
      </div>
    </div>
  );
}
