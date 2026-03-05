export function StrategyDropdown({ tradingPreset, presets, presetCategories, onPresetChange }) {
  const currentPreset = presets.find(p => p.id === tradingPreset);
  const grouped = presetCategories.length > 0;
  const sections = grouped
    ? presetCategories.map(cat => ({ cat, items: presets.filter(p => p.category === cat) })).filter(s => s.items.length > 0)
    : [{ cat: null, items: presets.length ? presets : [{ id: tradingPreset, name: tradingPreset, trader: "" }] }];

  return (
    <div style={{ display: "flex", alignItems: "center", gap: "4px" }}>
      <span style={{ fontSize: "7px", color: "#5C5C5C", letterSpacing: "1px", fontFamily: "'Space Mono',monospace" }}>STRAT</span>
      <select
        value={tradingPreset}
        onChange={e => onPresetChange(e.target.value)}
        title={currentPreset?.description}
        style={{
          fontFamily: "'Space Mono',monospace",
          fontSize: "9px",
          padding: "3px 20px 3px 6px",
          borderRadius: "4px",
          backgroundColor: "rgba(0,0,0,0.4)",
          backgroundImage: "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='6' height='4' viewBox='0 0 10 6'%3E%3Cpath fill='%23D4AF37' d='M0 0l5 6 5-6z'/%3E%3C/svg%3E\")",
          backgroundRepeat: "no-repeat",
          backgroundPosition: "right 6px center",
          color: "#D4AF37",
          border: "1px solid #D4AF3722",
          cursor: "pointer",
          outline: "none",
          appearance: "none",
          minWidth: "120px",
          maxWidth: "180px",
        }}
        aria-label="Select strategy preset"
      >
        {sections.map((sec) =>
          sec.cat ? (
            <optgroup key={sec.cat} label={sec.cat}>
              {sec.items.map(p => (
                <option key={p.id} value={p.id}>{p.name}</option>
              ))}
            </optgroup>
          ) : (
            sec.items.map(p => <option key={p.id} value={p.id}>{p.name}</option>)
          )
        )}
      </select>
    </div>
  );
}
