import { colors } from "../theme.js";

export default function Spinner({ dark = false, size = 16, style = {} }) {
  return (
    <span
      role="status"
      aria-label="Loading"
      style={{
        display: "inline-block",
        width: size,
        height: size,
        border: `2px solid ${dark ? "rgba(10,10,10,0.15)" : "rgba(255,255,255,0.10)"}`,
        borderTopColor: dark ? colors.dark : colors.gold,
        borderRadius: "50%",
        animation: "theme-spin 0.6s linear infinite",
        flexShrink: 0,
        boxShadow: dark
          ? "none"
          : "0 0 8px rgba(212,175,55,0.12), inset 0 0 4px rgba(212,175,55,0.06)",
        ...style,
      }}
    />
  );
}
