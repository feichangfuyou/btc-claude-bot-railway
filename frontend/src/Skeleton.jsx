/**
 * Skeleton — minimal shimmer placeholder for loading states.
 * Pure CSS, no JS. Feels instant.
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
        background: "linear-gradient(90deg, #1a1a1a 25%, #2a2a2a 50%, #1a1a1a 75%)",
        backgroundSize: "200% 100%",
        animation: "skeleton-shimmer 1.2s ease-in-out infinite",
        borderRadius: 4,
        ...style,
      }}
    />
  );
}
