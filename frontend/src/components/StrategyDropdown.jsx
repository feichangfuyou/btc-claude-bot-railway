export function StrategyDropdown({ tradingPreset, presets, presetCategories, onPresetChange }) {
  const currentPreset = presets.find(p => p.id === tradingPreset);
  const grouped = presetCategories.length > 0;
  const sections = grouped
    ? presetCategories.map(cat => ({ cat, items: presets.filter(p => p.category === cat) })).filter(s => s.items.length > 0)
    : [{ cat: null, items: presets.length ? presets : [{ id: tradingPreset, name: tradingPreset, trader: "" }] }];

  return (
    <div className="cp-field">
      <span className="cp-field-label">STRAT</span>
      <select
        className="cp-select cp-select--strat"
        value={tradingPreset}
        onChange={e => onPresetChange(e.target.value)}
        title={currentPreset?.description}
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
