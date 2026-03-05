import { colors, radii } from "./theme.js";

/**
 * Skeleton — minimal shimmer placeholder for loading states.
 * Uses theme tokens; animation defined in global.css.
 */
export default function Skeleton({ width = "100%", height = 16, style = {}, className = "" }) {
  return (
    <div
      className={className}
      role="progressbar"
      aria-busy="true"
      style={{
        width,
        height,
        background: `linear-gradient(90deg, ${colors.border} 25%, #2a2a2a 50%, ${colors.border} 75%)`,
        backgroundSize: "200% 100%",
        animation: "skeleton-shimmer 1.2s ease-in-out infinite",
        borderRadius: radii.xs,
        ...style,
      }}
    />
  );
}
