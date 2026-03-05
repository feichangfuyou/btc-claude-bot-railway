import { colors, radii } from "../theme.js";

/** Shared alert — variants: error | success | warning | info */
export default function Alert({ children, variant = "info", style = {} }) {
  const variants = {
    error: {
      color: colors.error,
      background: "rgba(255,23,68,0.08)",
      border: "1px solid rgba(255,23,68,0.2)",
    },
    success: {
      color: colors.success,
      background: "rgba(0,230,118,0.08)",
      border: "1px solid rgba(0,230,118,0.2)",
    },
    warning: {
      color: colors.warning,
      background: "rgba(255,153,0,0.08)",
      border: "1px solid rgba(255,153,0,0.2)",
    },
    info: {
      color: colors.gold,
      background: "rgba(212,175,55,0.08)",
      border: "1px solid rgba(212,175,55,0.2)",
    },
  };

  const v = variants[variant] || variants.info;
  return (
    <div
      role="alert"
      style={{
        fontSize: 12,
        borderRadius: radii.lg,
        padding: "10px 14px",
        marginBottom: 16,
        lineHeight: 1.5,
        backdropFilter: "blur(8px)",
        WebkitBackdropFilter: "blur(8px)",
        ...v,
        ...style,
      }}
    >
      {children}
    </div>
  );
}
