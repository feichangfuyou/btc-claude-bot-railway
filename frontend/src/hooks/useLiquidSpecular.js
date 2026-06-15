import { useCallback, useRef } from "react";

/**
 * Cursor-reactive specular glare for True Liquid Glass surfaces.
 *
 * Renders a soft radial-gradient spotlight that dynamically tracks the
 * user's mouse (X/Y) via requestAnimationFrame, applied as an overlay
 * with mix-blend-mode so it interacts with the underlying surface like
 * real light hitting wet resin.
 *
 * Usage:
 *   const { glareRef, specularRef, onMouseMove, onMouseLeave } = useLiquidSpecular();
 *   // glareRef   → interactive glare overlay (mix-blend-mode: overlay)
 *   // specularRef → static specular highlight (top-half shine)
 */
export function useLiquidSpecular() {
  const glareRef = useRef(null);
  const specularRef = useRef(null);
  const rafRef = useRef(null);

  const onMouseMove = useCallback((e) => {
    if (rafRef.current) return;
    rafRef.current = requestAnimationFrame(() => {
      rafRef.current = null;
      const glare = glareRef.current;
      if (!glare) return;

      const container = glare.parentElement;
      if (!container) return;
      const rect = container.getBoundingClientRect();
      const x = ((e.clientX - rect.left) / rect.width) * 100;
      const y = ((e.clientY - rect.top) / rect.height) * 100;

      glare.style.background =
        `radial-gradient(ellipse 60% 50% at ${x}% ${y}%, ` +
        `rgba(255,255,255,0.14) 0%, ` +
        `rgba(255,255,255,0.06) 25%, ` +
        `rgba(255,255,255,0.02) 50%, ` +
        `transparent 70%)`;
      glare.style.opacity = "1";
    });
  }, []);

  const onMouseLeave = useCallback(() => {
    const glare = glareRef.current;
    if (!glare) return;
    if (rafRef.current) {
      cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
    }
    glare.style.opacity = "0";
  }, []);

  const glareStyle = {
    position: "absolute",
    inset: 0,
    borderRadius: "inherit",
    background: "transparent",
    mixBlendMode: "overlay",
    pointerEvents: "none",
    zIndex: 2,
    opacity: 0,
    transition: "opacity 0.35s ease",
  };

  const specularStyle = {
    position: "absolute",
    inset: 0,
    borderRadius: "inherit",
    background:
      "linear-gradient(174deg, " +
      "rgba(255,255,255,0.22) 0%, " +
      "rgba(255,255,255,0.12) 12%, " +
      "rgba(255,255,255,0.04) 30%, " +
      "rgba(255,255,255,0.008) 48%, " +
      "transparent 56%)",
    maskImage: "linear-gradient(to bottom, black 50%, transparent 70%)",
    WebkitMaskImage: "linear-gradient(to bottom, black 50%, transparent 70%)",
    pointerEvents: "none",
    zIndex: 1,
  };

  return {
    glareRef,
    specularRef,
    glareStyle,
    specularStyle,
    onMouseMove,
    onMouseLeave,
    overlayRef: glareRef,
  };
}
