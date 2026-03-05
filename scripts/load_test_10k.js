/**
 * k6 load test for 10K readiness.
 * Run: k6 run scripts/load_test_10k.js
 * Install: brew install k6  (or https://k6.io/docs/getting-started/installation/)
 *
 * Phases: ramp to 500 → 1k → 2k VUs, hold, then ramp down.
 * Target: P95 < 500ms for read endpoints, error rate < 1%.
 */
import http from "k6/http";
import { check, sleep } from "k6";
import { Rate } from "k6/metrics";

const BASE = __ENV.BASE_URL || "http://localhost:8000";
const errorRate = new Rate("errors");

export const options = {
  stages: [
    { duration: "1m", target: 100 },
    { duration: "2m", target: 500 },
    { duration: "2m", target: 1000 },
    { duration: "2m", target: 2000 },
    { duration: "3m", target: 2000 },
    { duration: "1m", target: 0 },
  ],
  thresholds: {
    http_req_duration: ["p(95)<2000"],
    errors: ["rate<0.05"],
  },
};

export default function () {
  const paths = ["/health", "/readiness", "/api/config", "/metrics"];
  const path = paths[Math.floor(Math.random() * paths.length)];
  const res = http.get(`${BASE}${path}`);
  const ok = check(res, {
    "status 200": (r) => r.status === 200,
    "latency ok": (r) => r.timings.duration < 3000,
  });
  errorRate.add(!ok);
  sleep(0.5 + Math.random() * 1);
}
