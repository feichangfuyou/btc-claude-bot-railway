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

/**
 * Slide-up and fade-in for section/container mounting.
 */
export function slideUp(els, duration = 400, delay = 0) {
  if (!els) return;
  const arr = els instanceof NodeList || Array.isArray(els) ? Array.from(els) : [els];
  if (!arr.length) return;

  arr.forEach(el => {
    if (el && el.style) {
      el.style.opacity = "0";
      el.style.transform = "translateY(12px)";
    }
  });

  animate(arr, {
    opacity: [0, 1],
    y: [12, 0],
    duration,
    delay,
    ease: "outElastic(1, 1.2)",
  });
}

/**
 * Pop-in effect for modals or impactful cards.
 */
export function popIn(els, duration = 500, delay = 0) {
  if (!els) return;
  const arr = els instanceof NodeList || Array.isArray(els) ? Array.from(els) : [els];
  if (!arr.length) return;

  arr.forEach(el => {
    if (el && el.style) {
      el.style.opacity = "0";
      el.style.transform = "scale(0.92)";
    }
  });

  animate(arr, {
    opacity: [0, 1],
    scale: [0.92, 1],
    duration,
    delay,
    ease: "outElastic(1, 0.8)",
  });
}

/**
 * Gentle infinite pulse for indicators (like live dots).
 */
export function pulseInfinite(els, duration = 2000) {
  if (!els) return;
  const arr = els instanceof NodeList || Array.isArray(els) ? Array.from(els) : [els];
  if (!arr.length) return;

  return animate(arr, {
    opacity: [0.3, 1],
    duration,
    direction: "alternate",
    loop: true,
    ease: "inOutSine"
  });
}
