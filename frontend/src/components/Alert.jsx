import { colors, radii, liquidGlass } from "../theme.js";

export default function Alert({ children, variant = "info", style = {} }) {
  const tints = {
    error: {
      color: colors.error,
      background: "rgba(255,23,68,0.06)",
      border: "1px solid rgba(255,23,68,0.15)",
      boxShadow: [
        "0 4px 16px rgba(0,0,0,0.25)",
        "inset 0 1px 0 rgba(255,23,68,0.06)",
        "inset 0 -1px 0 rgba(0,0,0,0.10)",
        "0 0 20px rgba(255,23,68,0.04)",
      ].join(", "),
    },
    success: {
      color: colors.success,
      background: "rgba(0,230,118,0.06)",
      border: "1px solid rgba(0,230,118,0.15)",
      boxShadow: [
        "0 4px 16px rgba(0,0,0,0.25)",
        "inset 0 1px 0 rgba(0,230,118,0.06)",
        "inset 0 -1px 0 rgba(0,0,0,0.10)",
        "0 0 20px rgba(0,230,118,0.04)",
      ].join(", "),
    },
    warning: {
      color: colors.warning,
      background: "rgba(255,153,0,0.06)",
      border: "1px solid rgba(255,153,0,0.15)",
      boxShadow: [
        "0 4px 16px rgba(0,0,0,0.25)",
        "inset 0 1px 0 rgba(255,153,0,0.06)",
        "inset 0 -1px 0 rgba(0,0,0,0.10)",
        "0 0 20px rgba(255,153,0,0.04)",
      ].join(", "),
    },
    info: {
      color: colors.gold,
      background: "rgba(212,175,55,0.06)",
      border: "1px solid rgba(212,175,55,0.15)",
      boxShadow: [
        "0 4px 16px rgba(0,0,0,0.25)",
        "inset 0 1px 0 rgba(212,175,55,0.06)",
        "inset 0 -1px 0 rgba(0,0,0,0.10)",
        "0 0 20px rgba(212,175,55,0.04)",
      ].join(", "),
    },
  };

  const v = tints[variant] || tints.info;
  return (
    <div
      role="alert"
      style={{
        position: "relative",
        fontSize: 12,
        borderRadius: radii.lg,
        padding: "10px 14px",
        marginBottom: 16,
        lineHeight: 1.5,
        backdropFilter: "blur(12px) saturate(1.3)",
        WebkitBackdropFilter: "blur(12px) saturate(1.3)",
        overflow: "hidden",
        ...v,
        ...style,
      }}
    >
      <span
        aria-hidden
        style={{
          position: "absolute",
          inset: 0,
          borderRadius: "inherit",
          background: "linear-gradient(176deg, rgba(255,255,255,0.06) 0%, transparent 40%)",
          pointerEvents: "none",
          zIndex: 0,
        }}
      />
      <span style={{ position: "relative", zIndex: 1 }}>{children}</span>
    </div>
  );
}
