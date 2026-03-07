# Responsiveness Audit — DoYou.trade Frontend

## Overall Score: **72/100** (Good, but needs polish for 280px)

---

## What’s Working Well

### 1. **Base System (global.css)** — 9/10
- Breakpoints: 600px, 400px, 375px, 320px, **280px**
- Font scaling: 16→14→13→12→10→9px
- Button/select touch targets scale: 44→38→34→32→30→28px
- Safe-area insets for notched devices
- Card padding and border-radius scale down
- `chart-card` height scales: 65vh→60vh→55vh→50vh→45vh

### 2. **Dashboard (App.jsx)** — 8/10
- Breakpoints: 1024px, 600px, 400px, **280px**
- Grid collapses: 3-col → 2-col → 1-col
- Mobile bottom nav with safe-area
- Hamburger nav drawer
- Control panel, brand row, ticker tape all have narrow rules

### 3. **Auth Pages (auth.css)** — 7/10
- Breakpoints: 600px, 375px, 320px
- Card padding and typography scale
- **Missing: 280px breakpoint**

### 4. **Landing (auth.css)** — 7/10
- Breakpoints: 1024px, 768px, 480px, **280px**
- Hero, stats, features scale
- Some 280px rules exist but are incomplete

---

## What Needs Fixing (Down to 280px)

### Critical (Breaks or Poor UX at 280px)

| Component | Issue | Fix |
|-----------|-------|-----|
| **auth.css** | No 280px breakpoint for Login/Signup | Add `@media (max-width: 280px)` for auth-card, auth-brand, auth-input, etc. |
| **Billing.jsx** | No 280px; tier grid can overflow | Add 280px media query; stack tier cards; shrink typography |
| **History.jsx** | No 280px; table overflows | Add 280px; reduce font/padding; consider horizontal scroll wrapper |
| **Admin.jsx** | Only 640px; no 320/280px | Add 375px, 320px, 280px breakpoints |
| **ChartSection.jsx** | Ticker search input `width: 140px` fixed | Use `min(140px, calc(100vw - 48px))` or `max(80px, 50%)` |
| **ControlPanel** | Goal picker row (100, 500, 1k, 2.5k, 4k + custom) | At 280px: wrap to 2 rows or hide some buttons; shrink custom input |
| **TickerItem** | `minWidth: 52px` on chg24h; fixed padding | At 280px: reduce minWidth; smaller font; tighter padding |
| **TickerTape** | `gap: 24px` (inline), `.ticker-track` gap: 32px | Add 280px rule: reduce gap to 12–16px |

### Medium (Visual/UX polish)

| Component | Issue | Fix |
|-----------|-------|-----|
| **StrategyDropdown** | Dropdown width may exceed 280px | Add `max-width: min(300px, calc(100vw - 24px))` |
| **PositionsPanel** | pos-grid at 280px is 1fr (good) | Verify entry/TP/SL don’t overflow |
| **TradeQuote** | May have fixed widths | Audit and use relative units |
| **Confirm overlay** | confirm-box padding | Already has generic padding override; verify 280px |
| **Landing nav** | `padding: 0 10px` at 280px | Consider 6px for extra narrow |
| **Landing hero** | `font-size: 32px` at 280px | Consider 28px for very narrow |

### Minor (Edge cases)

| Component | Issue | Fix |
|-----------|-------|-----|
| **Login.jsx LandingTicker** | `gap: 40px` between items | Reduce at 280px via CSS or inline style |
| **Error boundary** | Fixed `fontSize: 48px` icon | Scale down at 280px |
| **Modals (TradeDetail, etc.)** | Fixed widths | Ensure `max-width: calc(100vw - 24px)` |

---

## Breakpoint Coverage Summary

| Breakpoint | global.css | App.jsx | auth.css | History | Billing | Admin |
|------------|------------|---------|----------|---------|---------|-------|
| 1024px | ✓ | ✓ | ✓ | — | — | — |
| 768px | — | — | — | ✓ | ✓ | — |
| 640px | — | — | — | — | — | ✓ |
| 600px | ✓ | ✓ | ✓ | ✓ | ✓ | — |
| 480px | — | — | ✓ | — | — | — |
| 400px | ✓ | ✓ | — | — | — | — |
| 375px | ✓ | — | ✓ | ✓ | ✓ | — |
| 320px | ✓ | — | ✓ | ✓ | ✓ | — |
| **280px** | ✓ | ✓ | **✗** | **✗** | **✗** | **✗** |

---

## Recommended Fix Order

1. **auth.css** — Add 280px breakpoint for auth pages
2. **Billing.jsx** — Add 280px; ensure tier grid stacks
3. **History.jsx** — Add 280px; table scroll/padding
4. **Admin.jsx** — Add 375px, 320px, 280px
5. **ChartSection.jsx** — Responsive ticker search width
6. **ControlPanel** — Goal picker wrap/shrink at 280px
7. **TickerItem** — Smaller sizing at 280px
8. **App.jsx** — Ticker track gap at 280px (add to existing block)
9. **StrategyDropdown** — Max-width constraint

---

## Device Reference (Widths)

- **iPhone SE (1st gen)**: 320px
- **iPhone 12/13 mini**: 375px
- **Galaxy Z Flip cover**: 260px (folds to ~280px usable)
- **Galaxy Fold inner**: 512px
- **Smallest common**: 280px (Galaxy Fold outer, very old devices)
