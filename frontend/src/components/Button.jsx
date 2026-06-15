import { colors, radii, typography, liquidGlass, buttonSizes } from "../theme.js";

export default function Button({
  children,
  variant = "primary",
  disabled = false,
  loading = false,
  className = "",
  style = {},
  ...props
}) {
  const base = {
    fontFamily: typography.fontButton,
    fontSize: buttonSizes.fontSize,
    fontWeight: 500,
    letterSpacing: buttonSizes.letterSpacing,
    textTransform: "uppercase",
    padding: `${buttonSizes.paddingY}px ${buttonSizes.paddingX}px`,
    border: "none",
    borderRadius: buttonSizes.radius,
    cursor: disabled ? "not-allowed" : "pointer",
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "center",
    gap: 5,
    position: "relative",
    overflow: "hidden",
    minHeight: buttonSizes.height,
    lineHeight: 1.2,
    boxSizing: "border-box",
    ...liquidGlass.button,
    ...style,
  };

  const variants = {
    primary: {
      background: `linear-gradient(180deg, ${colors.gold}, ${colors.goldDark})`,
      color: colors.dark,
      boxShadow: [
        "0 3px 12px rgba(212,175,55,0.16)",
        "0 1px 3px rgba(0,0,0,0.18)",
        "inset 0 1px 0 rgba(255,255,255,0.20)",
      ].join(", "),
    },
    success: {
      background: `linear-gradient(180deg, ${colors.success}, #00C853)`,
      color: "#fff",
      boxShadow: [
        "0 3px 12px rgba(0,230,118,0.14)",
        "0 1px 3px rgba(0,0,0,0.18)",
        "inset 0 1px 0 rgba(255,255,255,0.16)",
      ].join(", "),
    },
    secondary: {
      background: "rgba(255,255,255,0.03)",
      ...liquidGlass.button,
      border: `1px solid ${colors.inputBorder}`,
      color: colors.muted,
    },
    danger: {
      background: "rgba(255,23,68,0.85)",
      ...liquidGlass.button,
      color: "#fff",
      boxShadow: [
        "0 3px 12px rgba(255,23,68,0.14)",
        "0 1px 3px rgba(0,0,0,0.18)",
        "inset 0 1px 0 rgba(255,255,255,0.12)",
      ].join(", "),
    },
    ghost: {
      background: "rgba(255,255,255,0.03)",
      ...liquidGlass.button,
      border: `1px solid ${colors.inputBorder}`,
      color: colors.muted,
    },
  };

  const v = variants[variant] || variants.primary;
  const merged = { ...base, ...v };

  if (disabled) merged.opacity = 0.6;
  if (loading) merged.opacity = 0.8;

  return (
    <button
      type="button"
      className={className}
      style={merged}
      disabled={disabled || loading}
      {...props}
    >
      <span
        aria-hidden
        style={{
          position: "absolute",
          inset: 0,
          borderRadius: "inherit",
          background: "linear-gradient(176deg, rgba(255,255,255,0.18) 0%, rgba(255,255,255,0.04) 42%, transparent 54%)",
          pointerEvents: "none",
          zIndex: 1,
        }}
      />
      <span style={{ position: "relative", zIndex: 2, display: "inline-flex", alignItems: "center", gap: 8 }}>
        {loading ? (
          <>
            <span
              style={{
                width: 16,
                height: 16,
                border: "2px solid rgba(255,255,255,0.2)",
                borderTopColor: variant === "primary" || variant === "success" ? colors.dark : "#fff",
                borderRadius: "50%",
                animation: "theme-spin 0.6s linear infinite",
              }}
            />
            {children}
          </>
        ) : (
          children
        )}
      </span>
    </button>
  );
}
