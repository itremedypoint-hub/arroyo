// Live-feed math ↔ independent oracle (verify/live_vectors.json).
import test from "node:test";
import assert from "node:assert/strict";
import { loadCore } from "./extract.mjs";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const { ARROYO } = loadCore();
const V = JSON.parse(readFileSync(join(dirname(fileURLToPath(import.meta.url)), "..", "verify", "live_vectors.json"), "utf8"));
let N = 0;
const near = (a, b, eps = 1e-9) => { assert.ok(Math.abs(a - b) <= eps, `${a} !≈ ${b}`); N++; };
const same = (a, b) => { assert.equal(a, b); N++; };

test("staleness policy matches the oracle at every boundary", () => {
  same(ARROYO.LIVE.FRESH_MAX_MIN, V.meta.policy.fresh_max_min);
  same(ARROYO.LIVE.STALE_MAX_MIN, V.meta.policy.stale_max_min);
  for (const c of V.status_cases) same(ARROYO.snapshotStatus(Number(c.minutes)), c.status);
});
test("ISO age arithmetic (incl. timezone offsets)", () => {
  for (const c of V.age_minutes_cases) near(ARROYO.ageMinutes(c.fetched, c.now), c.minutes, 1e-6);
});
test("i15 from a 15-minute series: gaps, garbage, zeros, emptiness", () => {
  for (const c of V.i15_series_cases) {
    const series = c.series.map(e => ({ t: e.t, mm: e.mm === null ? null : e.mm }));
    const got = ARROYO.i15FromSeries(series);
    if (c.expect === null) same(got, null);
    else { near(got.mmh, c.expect.mmh); same(got.at, c.expect.at); }
  }
});
test("count", () => { console.log(`LIVE_VECTOR_CHECKS=${N}`); assert.ok(N >= 25); });
