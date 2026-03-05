/**
 * Lightweight animation utilities using Anime.js.
 * Stagger, fade-in, number tween — keeps the UI feeling snappy.
 */
import { animate, utils } from "animejs";

/** Round to N decimals for number animations */
export const round = (decimals = 2) => utils.round(decimals);

/**
 * Animate a JS object's numeric property; call onRender to sync DOM.
 * @param {Object} obj - { value: number }
 * @param {number} target
 * @param {(v: number) => void} onRender
 * @param {number} duration
 */
export function animateNumber(obj, target, onRender, duration = 120) {
  if (obj.value === target) return;
  obj.value = obj.value ?? target;
  const decimals = target >= 100 ? 0 : target >= 1 ? 2 : 4;
  animate(obj, {
    value: target,
    duration,
    ease: "out",
    modifier: round(decimals),
    onRender,
  });
}

/**
 * Stagger-fade children when container mounts.
 * @param {HTMLElement} container
 * @param {string} selector - e.g. ".logrow" or "[data-stagger]"
 * @param {{ delay?: number, duration?: number, limit?: number, start?: number }?} opts
 *   limit: max items to animate (newest first). start: skip first N (animate only new items).
 */
export function staggerIn(container, selector, opts = {}) {
  if (!container) return;
  const nodes = Array.from(container.querySelectorAll(selector));
  if (!nodes.length) return;
  const { delay = 35, duration = 160, limit = 12, start = 0 } = opts;
  const slice = nodes.slice(start, limit ? start + limit : undefined);
  slice.forEach((el) => {
    el.style.opacity = "0";
    el.style.transform = "translateY(4px)";
  });
  animate(slice, {
    opacity: [0, 1],
    y: [4, 0],
    duration,
    delay: (_, i) => i * delay,
    ease: "out",
  });
}

/**
 * Fade-in a single element.
 */
export function fadeIn(el, duration = 200) {
  if (!el) return;
  el.style.opacity = "0";
  animate(el, { opacity: [0, 1], duration, ease: "out" });
}
