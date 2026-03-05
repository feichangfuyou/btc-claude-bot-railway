/**
 * AnimatedNumber — smooth value transitions via Anime.js.
 * Keeps the UI feeling snappy; 120ms duration.
 */
import { useEffect, useRef } from "react";
import { animate, utils } from "animejs";

export default function AnimatedNumber({
  value,
  format = (v) => String(v),
  duration = 120,
  style = {},
  ...rest
}) {
  const elRef = useRef(null);
  const objRef = useRef({ v: typeof value === "number" ? value : parseFloat(value) || 0 });

  useEffect(() => {
    const target = typeof value === "number" ? value : parseFloat(value) || 0;
    if (Number.isNaN(target) || objRef.current.v === target) return;
    const decimals = target >= 100 ? 0 : target >= 1 ? 2 : 4;
    animate(objRef.current, {
      v: target,
      duration,
      ease: "out",
      modifier: utils.round(decimals),
      onRender: () => {
        if (elRef.current) elRef.current.textContent = format(objRef.current.v);
      },
    });
  }, [value, duration, format]);

  const display = typeof value === "number" ? value : parseFloat(value) || 0;
  return (
    <span ref={elRef} style={style} {...rest}>
      {format(display)}
    </span>
  );
}
