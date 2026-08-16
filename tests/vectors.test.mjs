// Engine ↔ oracle parity. The oracle (verify/golden_vectors.json) was
// computed independently; every check here compares the shipped JS engine
// block (sliced from site/index.html) against it. Tolerance 1e-9.
import test from "node:test";
import assert from "node:assert/strict";
import { loadCore, loadVectors } from "./extract.mjs";

const { ARROYO, sha256Hex } = loadCore();
const V = loadVectors();
let CHECKS = 0;
const near = (a, b, eps = 1e-9) => {
  assert.ok(Math.abs(a - b) <= eps, `${a} !≈ ${b} (Δ=${Math.abs(a - b)})`); CHECKS++;
};
const same = (a, b) => { assert.equal(a, b); CHECKS++; };

test("constants and the year-2 factor", () => {
  const co = V.constants["M1_coefficients_by_duration_[B,Ct,Cf,Cs]"]["15min"];
  near(ARROYO.B, co[0]); near(ARROYO.CT, co[1]); near(ARROYO.CF, co[2]); near(ARROYO.CS, co[3]);
  near(ARROYO.LN3, V.constants.ln3);
  near(ARROYO.logit(0.75), V.constants["logit_0.75"]);
  near(ARROYO.y2factor(), V.constants.year2_factor_1_plus_ln3_over_absB);
  // identity: shifting any trigger by the factor lands the curve at exactly 0.75
  near(ARROYO.sigmoid(ARROYO.B + (-ARROYO.B) * ARROYO.y2factor()), 0.75);
});

test("M1 raw-covariate route — R is 15-min ACCUMULATION in mm (audit F2)", () => {
  const cases = V.m1_pure_function_R_is_accumulation_mm;
  assert.equal(cases.length, 3); CHECKS++;
  for (const c of cases) {
    const kSum = ARROYO.CT * c.T + ARROYO.CF * c.F + ARROYO.CS * c.S;
    near(kSum, c.k_per_mm_accum);
    near(ARROYO.m1R(c.T, c.F, c.S, 0.5), c.R50_mm_accum_15min);
    near(ARROYO.m1R(c.T, c.F, c.S, 0.75), c.R75_mm_accum_15min);
    near(ARROYO.accum15ToMmh(c.R50_mm_accum_15min), c.R50_as_intensity_mmh);
    near(ARROYO.accum15ToMmh(c.R75_mm_accum_15min), c.R75_as_intensity_mmh);
    near(c.ratio_R75_over_R50, ARROYO.y2factor());
    near(ARROYO.m1P(c.T, c.F, c.S, c.R50_mm_accum_15min), c.identity_p_at_R50);
    near(ARROYO.m1P(c.T, c.F, c.S, c.R75_mm_accum_15min), c.identity_p_at_R75);
    near(ARROYO.m1P(c.T, c.F, c.S, 6), c.p_at_6mm_accum);
    near(ARROYO.B + kSum * 6, c.X_at_6mm_accum);
  }
});

test("curve back-solved from a published threshold (the app's route)", () => {
  const c = V.curve_from_published_threshold;
  const k = ARROYO.kFromThreshold(c.published_i15_mmh_at_p50, 0.5);
  near(k, c.k_intensity_per_mmh);
  near(ARROYO.kFromThreshold(c.published_i15_mmh_at_p50 / 4, 0.5), c.k_accumulation_per_mm);
  for (const [I, p] of Object.entries(c.P_at_intensity_mmh)) near(ARROYO.pCurve(Number(I), k), p);
  near(ARROYO.pCurve(24, k), c.unit_invariance_proof.intensity_route_P_at_24mmh);
  near(ARROYO.pCurve(6, c.k_accumulation_per_mm), c.unit_invariance_proof.accumulation_route_P_at_6mm);
  near(ARROYO.pCurve(c.published_i15_mmh_at_p50 * ARROYO.y2factor(), k), c["P_at_year2_trigger_must_equal_0.75"]);
});

test("conversions", () => {
  near(ARROYO.inchesToMm(1), V.conversions.inch_to_mm_exact);
  near(ARROYO.inchesToMm(0.25), V.conversions["0.25in_per_15min"].mm_accum);
  near(ARROYO.accum15ToMmh(ARROYO.inchesToMm(0.25)), V.conversions["0.25in_per_15min"].intensity_mmh);
  near(ARROYO.inchesToMm(1.25), V.conversions["1.25in_per_hour_to_mmh"]);
  near(ARROYO.accum15ToMmh(6), V.conversions["6mm_per_15min_to_mmh"]);
});

test("all 90 guarded tier rows — tier, trigger, fraction", () => {
  const rows = V.tier_classification_guarded;
  assert.equal(rows.length, 90); CHECKS++;
  for (const row of rows) {
    const r = ARROYO.classify(row.i15_y1_mmh, row.year, row.I_mmh);
    same(r.tier, row.tier);
    near(r.trigger, row.trigger_mmh);
    near(r.fraction, row.fraction_of_trigger);
  }
});

test("pathological low trigger (3 mm/h): guard holds where naive inverts", () => {
  const rows = V.tier_monotonicity_pathology_i15_3mmh;
  let divergences = 0;
  for (const row of rows) {
    const r = ARROYO.classify(row.i15_y1_mmh, 1, row.I_mmh);
    same(r.tier, row.guarded);
    if (row.naive !== row.guarded) { divergences++; assert.notEqual(r.tier, row.naive); CHECKS++; }
  }
  assert.ok(divergences >= 2, "oracle should exercise real naive/guarded divergence"); CHECKS++;
  const t = ARROYO.thresholds(3, 1);
  assert.ok(t.adv <= t.watch && t.watch <= t.warn); CHECKS++;
});

test("haversine reference", () => {
  const h = V.haversine_example;
  near(ARROYO.haversineKm(h.A[0], h.A[1], h.B[0], h.B[1]), h.distance_km, 1e-6);
});

test("sha256 matches Python hashlib (cross-language check)", () => {
  same(sha256Hex("abc"), "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad");
  same(sha256Hex(""), "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855");
  same(sha256Hex("poppy-ink-2026"), "595348e857a691a5bc9140c08fb29627c1a8b200636a9d98d79a1de9781b48a0");
});

test("check-count floor", () => {
  console.log(`VECTOR_CHECKS=${CHECKS}`);
  assert.ok(CHECKS >= 300, `expected ≥300 comparisons, got ${CHECKS}`);
});
