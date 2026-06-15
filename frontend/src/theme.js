/**
 * Central design tokens — single source of truth for UI consistency.
 * True Liquid Glass: poured-resin aesthetic with Aqua specular + VisionOS depth.
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
  success: "#00E676",
  error: "#FF1744",
  warning: "#ff9900",
  dim: "#3a3a3a",
  surface: "rgba(255, 255, 255, 0.03)",
  surfaceHover: "rgba(255, 255, 255, 0.06)",
  glassBorder: "rgba(212, 175, 55, 0.10)",
  glassBorderHover: "rgba(212, 175, 55, 0.22)",
  glassBorderActive: "rgba(212, 175, 55, 0.4)",
  inputBorder: "rgba(255, 255, 255, 0.05)",
  inputBg: "rgba(6, 6, 6, 0.65)",
  inputBgFocus: "rgba(6, 6, 6, 0.8)",
};

export const radii = {
  xs: 4,
  sm: 8,
  md: 10,
  lg: 12,
  xl: 14,
  xxl: 18,
  card: 18,
  cardLg: 22,
  modal: 22,
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
  fontBody: "'Inter', sans-serif",
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

/** Canonical button dimensions — single size across all variants */
export const buttonSizes = {
  height: 30,
  paddingY: 5,
  paddingX: 12,
  fontSize: 10,
  letterSpacing: 0.6,
  radius: 7,
};

/** Spread into inline button style objects for consistency */
export const buttonBase = {
  fontSize: buttonSizes.fontSize,
  padding: `${buttonSizes.paddingY}px ${buttonSizes.paddingX}px`,
  minHeight: buttonSizes.height,
  minWidth: buttonSizes.height,
  borderRadius: buttonSizes.radius,
  letterSpacing: buttonSizes.letterSpacing,
  fontWeight: 500,
  cursor: "pointer",
  display: "inline-flex",
  alignItems: "center",
  justifyContent: "center",
  gap: 6,
  lineHeight: 1.2,
  boxSizing: "border-box",
};

/* ── True Liquid Glass inline-style system ──────────────────── */

const LG_SHADOW = [
  "0 18px 50px rgba(0,0,0,0.55)",
  "0 3px 8px rgba(0,0,0,0.38)",
  "0 28px 40px -20px rgba(212,175,55,0.04)",
  "inset 0 1.5px 0 rgba(255,255,255,0.14)",
  "inset 1px 0 0 rgba(255,255,255,0.06)",
  "inset 0 -2px 4px rgba(0,0,0,0.22)",
  "inset -1px 0 0 rgba(0,0,0,0.10)",
].join(", ");

const LG_SHADOW_ELEVATED = [
  "0 24px 70px rgba(0,0,0,0.60)",
  "0 6px 16px rgba(0,0,0,0.42)",
  "0 0 0 1px rgba(212,175,55,0.08)",
  "0 30px 50px -22px rgba(212,175,55,0.06)",
  "inset 0 1.5px 0 rgba(255,255,255,0.18)",
  "inset 1px 0 0 rgba(255,255,255,0.08)",
  "inset 0 -2px 4px rgba(0,0,0,0.26)",
  "inset -1px 0 0 rgba(0,0,0,0.12)",
].join(", ");

const LG_SHADOW_GLOW = [
  "0 0 60px rgba(212,175,55,0.10)",
  "0 18px 50px rgba(0,0,0,0.55)",
  "0 3px 8px rgba(0,0,0,0.38)",
  "0 28px 40px -20px rgba(212,175,55,0.06)",
  "inset 0 1.5px 0 rgba(255,255,255,0.14)",
  "inset 0 -2px 4px rgba(0,0,0,0.22)",
].join(", ");

const LG_EASE = "cubic-bezier(0.34, 1.56, 0.64, 1)";
const LG_EASE_OUT = "cubic-bezier(0.22, 0.68, 0, 1.02)";

export const liquidGlass = {
  surface: {
    background: "rgba(14, 14, 14, 0.55)",
    backdropFilter: "blur(50px) saturate(2.0)",
    WebkitBackdropFilter: "blur(50px) saturate(2.0)",
    border: `1px solid ${colors.glassBorder}`,
    borderRadius: radii.xxl,
    boxShadow: LG_SHADOW,
    transition: "border-color 0.3s ease, box-shadow 0.35s ease, background 0.3s ease",
  },

  surfaceHover: {
    borderColor: colors.glassBorderHover,
    boxShadow: LG_SHADOW_ELEVATED,
  },

  heavy: {
    background: "rgba(10, 10, 10, 0.72)",
    backdropFilter: "blur(64px) saturate(2.2)",
    WebkitBackdropFilter: "blur(64px) saturate(2.2)",
    border: `1px solid ${colors.glassBorder}`,
    borderRadius: radii.xxl,
    boxShadow: LG_SHADOW_ELEVATED,
  },

  light: {
    background: "rgba(18, 18, 18, 0.32)",
    backdropFilter: "blur(28px) saturate(1.8)",
    WebkitBackdropFilter: "blur(28px) saturate(1.8)",
    border: "1px solid rgba(255, 255, 255, 0.06)",
    borderRadius: radii.lg,
    boxShadow: [
      "0 10px 30px rgba(0,0,0,0.40)",
      "0 2px 6px rgba(0,0,0,0.28)",
      "0 20px 30px -16px rgba(212,175,55,0.03)",
      "inset 0 1.5px 0 rgba(255,255,255,0.10)",
      "inset 0 -1.5px 3px rgba(0,0,0,0.16)",
    ].join(", "),
  },

  input: {
    background: "rgba(6, 6, 6, 0.60)",
    backdropFilter: "blur(20px) saturate(1.6)",
    WebkitBackdropFilter: "blur(20px) saturate(1.6)",
    border: `1px solid ${colors.inputBorder}`,
    borderRadius: radii.sm,
    boxShadow: [
      "inset 0 3px 6px rgba(0,0,0,0.45)",
      "inset 0 1px 0 rgba(0,0,0,0.25)",
      "0 1px 0 rgba(255,255,255,0.05)",
    ].join(", "),
    transition: "border-color 0.25s ease, box-shadow 0.25s ease, background 0.25s ease",
  },

  inputFocus: {
    borderColor: colors.glassBorderActive,
    background: "rgba(6, 6, 6, 0.78)",
    boxShadow: [
      "0 0 0 3px rgba(212,175,55,0.08)",
      "inset 0 3px 6px rgba(0,0,0,0.38)",
      "inset 0 1px 0 rgba(0,0,0,0.18)",
      "0 1px 0 rgba(255,255,255,0.07)",
    ].join(", "),
  },

  button: {
    backdropFilter: "blur(16px) saturate(1.6)",
    WebkitBackdropFilter: "blur(16px) saturate(1.6)",
    boxShadow: [
      "0 2px 8px rgba(0,0,0,0.22)",
      "0 1px 2px rgba(0,0,0,0.14)",
      "inset 0 1px 0 rgba(255,255,255,0.10)",
    ].join(", "),
    transition: `all 0.2s ${LG_EASE}`,
  },

  buttonHover: {
    boxShadow: [
      "0 10px 36px rgba(0,0,0,0.45)",
      "0 3px 8px rgba(0,0,0,0.30)",
      "0 22px 30px -16px rgba(212,175,55,0.06)",
      "inset 0 1.5px 0 rgba(255,255,255,0.20)",
      "inset 0 -1.5px 3px rgba(0,0,0,0.22)",
    ].join(", "),
  },

  buttonActive: {
    transform: "scale(0.97)",
    boxShadow: [
      "0 2px 8px rgba(0,0,0,0.3)",
      "inset 0 3px 6px rgba(0,0,0,0.35)",
      "inset 0 -1px 0 rgba(255,255,255,0.06)",
    ].join(", "),
  },

  overlay: {
    background: "rgba(0, 0, 0, 0.60)",
    backdropFilter: "blur(50px) saturate(2.0)",
    WebkitBackdropFilter: "blur(50px) saturate(2.0)",
  },

  shadow: LG_SHADOW,
  shadowElevated: LG_SHADOW_ELEVATED,
  shadowGlow: LG_SHADOW_GLOW,
  ease: LG_EASE,
  easeOut: LG_EASE_OUT,
};
