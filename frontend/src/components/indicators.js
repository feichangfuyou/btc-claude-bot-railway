export function calcEMA(prices, period) {
  if (prices.length < 2) return null;
  const n = Math.min(period, prices.length), k = 2 / (n + 1);
  let v = prices.slice(0, n).reduce((a, b) => a + b, 0) / n;
  for (let i = n; i < prices.length; i++) v = prices[i] * k + v * (1 - k);
  return +v.toFixed(2);
}

export function calcRSI(prices, period = 14) {
  if (prices.length < period + 1) return 50;
  let g = 0, l = 0;
  for (let i = prices.length - period; i < prices.length; i++) {
    const d = prices[i] - prices[i - 1];
    d > 0 ? (g += d) : (l += Math.abs(d));
  }
  return +(100 - 100 / (1 + (g / period) / (l / period + 1e-9))).toFixed(2);
}

export function calcATR(prices, period = 14) {
  if (prices.length < 2) return 0;
  const trs = prices.slice(1).map((p, i) => Math.abs(p - prices[i]));
  const r = trs.slice(-period);
  return +(r.reduce((a, b) => a + b, 0) / r.length).toFixed(2);
}

export function calcBB(prices, period = 20) {
  const r = prices.slice(-Math.min(period, prices.length));
  const mid = r.reduce((a, b) => a + b, 0) / r.length;
  const std = Math.sqrt(r.reduce((s, p) => s + (p - mid) ** 2, 0) / r.length);
  const width = mid ? +((4 * std / mid) * 100).toFixed(4) : 0;
  return { upper: +(mid + 2 * std).toFixed(2), middle: +mid.toFixed(2), lower: +(mid - 2 * std).toFixed(2), width };
}
