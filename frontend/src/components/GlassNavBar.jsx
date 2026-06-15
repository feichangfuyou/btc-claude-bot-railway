const NAV_ITEMS = [
  {
    id: "trade",
    label: "Market",
    icon: (
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
      </svg>
    ),
  },
  {
    id: "bot",
    label: "Agent",
    icon: (
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        <rect x="4" y="4" width="16" height="16" rx="2" />
        <path d="M9 9h6M9 13h6M9 17h4" />
        <line x1="12" y1="1" x2="12" y2="4" />
        <circle cx="12" cy="1" r="1" fill="currentColor" stroke="none" />
      </svg>
    ),
  },
  {
    id: "logs",
    label: "Activity",
    icon: (
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        <line x1="8" y1="6" x2="21" y2="6" />
        <line x1="8" y1="12" x2="21" y2="12" />
        <line x1="8" y1="18" x2="21" y2="18" />
        <line x1="3" y1="6" x2="3.01" y2="6" />
        <line x1="3" y1="12" x2="3.01" y2="12" />
        <line x1="3" y1="18" x2="3.01" y2="18" />
      </svg>
    ),
  },
];

const MoreIcon = () => (
  <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="12" cy="5" r="1.5" fill="currentColor" stroke="none" />
    <circle cx="12" cy="12" r="1.5" fill="currentColor" stroke="none" />
    <circle cx="12" cy="19" r="1.5" fill="currentColor" stroke="none" />
  </svg>
);

export function GlassNavBar({ activeTab, onTabChange, onMenuOpen }) {
  return (
    <nav className="app-tabbar" aria-label="Main navigation">
      {NAV_ITEMS.map((item) => {
        const isActive = activeTab === item.id;
        return (
          <button
            key={item.id}
            type="button"
            className={`app-tabbar__item${isActive ? " app-tabbar__item--active" : ""}`}
            onClick={() => onTabChange(item.id)}
            aria-current={isActive ? "page" : undefined}
          >
            <span className="app-tabbar__pill" aria-hidden="true" />
            <span className="app-tabbar__icon">{item.icon}</span>
            <span className="app-tabbar__label">{item.label}</span>
          </button>
        );
      })}
      <button
        type="button"
        className="app-tabbar__item app-tabbar__item--more"
        onClick={onMenuOpen}
        aria-label="Open menu"
      >
        <span className="app-tabbar__icon"><MoreIcon /></span>
        <span className="app-tabbar__label">More</span>
      </button>
    </nav>
  );
}
