/**
 * Central design tokens — single source of truth for UI consistency.
 * Use these everywhere; never hardcode colors, radii, or spacing.
 */
export const colors = {
  gold: "#D4AF37",
  goldDim: "rgba(212, 175, 55, 0.5)",
  goldDark: "#B8860B",
  dark: "#0A0A0A",
  card: "#111111",
  border: "#1A1A1A",
  muted: "#5C5C5C",
  text: "#D4D4D4",
  /** Semantic: success / up / buy — use consistently */
  success: "#00E676",
  /** Semantic: error / down / sell — use consistently */
  error: "#FF1744",
  /** Warning / caution */
  warning: "#ff9900",
  /** Dim / disabled */
  dim: "#3a3a3a",
  surface: "rgba(255, 255, 255, 0.03)",
  surfaceHover: "rgba(255, 255, 255, 0.06)",
  glassBorder: "rgba(212, 175, 55, 0.12)",
  glassBorderHover: "rgba(212, 175, 55, 0.25)",
  glassBorderActive: "rgba(212, 175, 55, 0.4)",
  inputBorder: "rgba(255, 255, 255, 0.06)",
  inputBg: "rgba(10, 10, 10, 0.6)",
  inputBgFocus: "rgba(10, 10, 10, 0.8)",
};

export const radii = {
  xs: 4,
  sm: 6,
  md: 8,
  lg: 10,
  xl: 12,
  xxl: 16,
  card: 16,
  cardLg: 20,
  modal: 20,
};

export const spacing = {
  xs: 4,
  sm: 6,
  md: 8,
  lg: 12,
  xl: 16,
  xxl: 20,
  section: 24,
};

export const typography = {
  fontMono: "'Space Mono', monospace",
  fontDisplay: "'Montserrat', sans-serif",
  fontButton: "'Montserrat', sans-serif",
  sizeXs: 9,
  sizeSm: 10,
  sizeMd: 11,
  sizeBase: 12,
  sizeLg: 13,
  sizeXl: 14,
  size2xl: 16,
  size3xl: 20,
  size4xl: 24,
  size5xl: 28,
  size6xl: 36,
};

export const breakpoints = {
  xs: 320,
  sm: 375,
  md: 600,
  lg: 768,
};
