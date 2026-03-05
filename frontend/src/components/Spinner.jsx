import { colors } from "../theme.js";

/** Shared loading spinner — use everywhere for consistency */
export default function Spinner({ dark = false, size = 16, style = {} }) {
  const borderColor = dark ? `rgba(10,10,10,0.2)` : "rgba(255,255,255,0.2)";
  const topColor = dark ? colors.dark : "#fff";
  return (
    <span
      role="status"
      aria-label="Loading"
      style={{
        display: "inline-block",
        width: size,
        height: size,
        border: `2px solid ${borderColor}`,
        borderTopColor: topColor,
        borderRadius: "50%",
        animation: "theme-spin 0.6s linear infinite",
        flexShrink: 0,
        ...style,
      }}
    />
  );
}
