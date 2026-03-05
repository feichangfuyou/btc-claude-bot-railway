/**
 * FetchingPrice — Anime.js-driven loading text that pulses and cycles dots.
 * Constantly updating and changing for an alive, active feel.
 */
import { useEffect, useRef } from "react";
import { animate } from "animejs";
import { colors } from "./theme.js";

const DOTS = ["Warming up.", "Warming up..", "Warming up..."];

export default function FetchingPrice({ style = {} }) {
  const elRef = useRef(null);
  const dotIdx = useRef(0);

  useEffect(() => {
    const el = elRef.current;
    if (!el) return;

    // 1. Infinite pulse: opacity 0.55 ↔ 1.0, subtle scale 0.97 ↔ 1.03
    const pulse = animate(el, {
      opacity: [0.55, 1],
      scale: [0.97, 1.03],
      duration: 800,
      ease: "in-out",
      alternate: true,
      loop: true,
    });

    // 2. Cycle dots every 400ms for "constantly updating" feel
    const dotInterval = setInterval(() => {
      if (!el) return;
      dotIdx.current = (dotIdx.current + 1) % DOTS.length;
      el.textContent = DOTS[dotIdx.current];
    }, 400);

    return () => {
      pulse.cancel?.();
      clearInterval(dotInterval);
    };
  }, []);

  return (
    <div
      ref={elRef}
      style={{
        fontFamily: "'Bebas Neue', sans-serif",
        fontSize: "24px",
        color: `${colors.gold}66`,
        letterSpacing: "3px",
        transformOrigin: "center",
        ...style,
      }}
    >
      {DOTS[0]}
    </div>
  );
}
