import { colors, radii, typography } from "../theme.js";

/** Shared button — variants: primary | secondary | danger | ghost */
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
    fontSize: variant === "ghost" ? typography.sizeBase : typography.sizeLg,
    fontWeight: 600,
    letterSpacing: 2,
    textTransform: "uppercase",
    padding: "10px 24px",
    border: "none",
    borderRadius: radii.lg,
    cursor: disabled ? "not-allowed" : "pointer",
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "center",
    gap: 8,
    transition: "all 0.25s cubic-bezier(0.4, 0, 0.2, 1)",
    minHeight: 44,
    ...style,
  };

  const variants = {
    primary: {
      background: `linear-gradient(180deg, ${colors.gold}, ${colors.goldDark})`,
      color: colors.dark,
      boxShadow: "0 4px 20px rgba(212,175,55,0.2)",
    },
    success: {
      background: `linear-gradient(180deg, ${colors.success}, #00C853)`,
      color: "#fff",
      boxShadow: "0 4px 20px rgba(0,230,118,0.2)",
    },
    secondary: {
      background: "rgba(255,255,255,0.03)",
      backdropFilter: "blur(8px)",
      WebkitBackdropFilter: "blur(8px)",
      border: `1px solid ${colors.inputBorder}`,
      color: colors.muted,
    },
    danger: {
      background: "rgba(255,23,68,0.85)",
      backdropFilter: "blur(8px)",
      WebkitBackdropFilter: "blur(8px)",
      color: "#fff",
      boxShadow: "0 4px 16px rgba(255,23,68,0.15)",
    },
    ghost: {
      background: "rgba(255,255,255,0.03)",
      backdropFilter: "blur(8px)",
      WebkitBackdropFilter: "blur(8px)",
      border: `1px solid ${colors.inputBorder}`,
      color: colors.muted,
      fontSize: typography.sizeBase,
      padding: "6px 12px",
      minHeight: 36,
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
    </button>
  );
}
