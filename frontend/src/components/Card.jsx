import { colors, radii } from "../theme.js";

/** Shared glass card — use for sections, modals, content blocks */
export default function Card({ children, className = "", style = {}, variant = "default" }) {
  const base = {
    background: "rgba(17,17,17,0.55)",
    backdropFilter: "blur(20px) saturate(1.4)",
    WebkitBackdropFilter: "blur(20px) saturate(1.4)",
    border: `1px solid ${colors.glassBorder}`,
    borderRadius: radii.xxl,
    boxShadow: "0 8px 32px rgba(0,0,0,0.4), inset 0 1px 0 rgba(255,255,255,0.04)",
    transition: "border-color 0.3s ease, box-shadow 0.3s ease",
  };

  const variants = {
    default: {},
    heavy: {
      background: "rgba(17,17,17,0.72)",
      backdropFilter: "blur(40px) saturate(1.6)",
      WebkitBackdropFilter: "blur(40px) saturate(1.6)",
      boxShadow: "0 24px 64px rgba(0,0,0,0.5), inset 0 1px 0 rgba(255,255,255,0.06)",
    },
    light: {
      background: "rgba(17,17,17,0.35)",
      backdropFilter: "blur(12px) saturate(1.2)",
      WebkitBackdropFilter: "blur(12px) saturate(1.2)",
      borderRadius: radii.xl,
    },
  };

  return (
    <div className={className} style={{ ...base, ...variants[variant], ...style }}>
      {children}
    </div>
  );
}
