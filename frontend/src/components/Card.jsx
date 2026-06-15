import { liquidGlass } from "../theme.js";
import { useLiquidSpecular } from "../hooks/useLiquidSpecular.js";

export default function Card({ children, className = "", style = {}, variant = "default", reactive = false }) {
  const variants = {
    default: liquidGlass.surface,
    heavy: liquidGlass.heavy,
    light: liquidGlass.light,
  };

  const base = variants[variant] || variants.default;
  const { glareRef, specularRef, glareStyle, specularStyle, onMouseMove, onMouseLeave } = useLiquidSpecular();

  return (
    <div
      className={`${className}`}
      style={{ position: "relative", ...base, ...style }}
      onMouseMove={reactive ? onMouseMove : undefined}
      onMouseLeave={reactive ? onMouseLeave : undefined}
    >
      {/* Static specular highlight — curved convex resin shine on top half */}
      <div
        ref={reactive ? specularRef : undefined}
        aria-hidden
        style={specularStyle}
      />
      {/* Interactive glare — mouse-tracking spotlight with overlay blend */}
      {reactive && (
        <div
          ref={glareRef}
          aria-hidden
          style={glareStyle}
        />
      )}
      {/* Gold caustic refraction */}
      <div
        aria-hidden
        style={{
          position: "absolute",
          inset: 0,
          borderRadius: "inherit",
          background: "radial-gradient(ellipse at 20% 10%, rgba(212,175,55,0.08) 0%, rgba(212,175,55,0.025) 35%, transparent 60%)",
          pointerEvents: "none",
          zIndex: 1,
          opacity: 0.55,
        }}
      />
      <div style={{ position: "relative", zIndex: 3 }}>
        {children}
      </div>
    </div>
  );
}
