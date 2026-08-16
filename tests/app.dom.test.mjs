// Full-page integration in jsdom: the shipped index.html is loaded with
// scripts enabled and driven the way a visitor (and a maintainer) would.
import test from "node:test";
import assert from "node:assert/strict";
import { JSDOM } from "jsdom";
import { html, HTML_PATH } from "./extract.mjs";
import { pathToFileURL } from "node:url";

let DOMCHECKS = 0;
const ok = (v, msg) => { assert.ok(v, msg); DOMCHECKS++; };
const eq = (a, b, msg) => { assert.equal(a, b, msg); DOMCHECKS++; };

function boot() {
  const dom = new JSDOM(html, {
    url: pathToFileURL(HTML_PATH).href,
    runScripts: "dangerously",
    pretendToBeVisual: true,
    beforeParse(window) {
      // jsdom lacks TextEncoder on window; the sha256 gate needs it.
      window.TextEncoder = TextEncoder;
    }
  });
  return dom;
}

test("visitor flow, sandbox isolation, admin gate, i18n", async () => {
  const dom = boot();
  const { window } = dom;
  const doc = window.document;
  await new Promise(r => setTimeout(r, 30)); // let DOMContentLoaded handlers run
  const A = window.__arroyo;
  ok(A && A.state && A.ARROYO, "test handle exposed");

  // -- initial state: training banner, 8 basins, default year 2 --
  const banner = doc.getElementById("modeBanner");
  ok(!banner.hidden && /TRAINING/i.test(banner.textContent), "training banner visible and labeled");
  const chips = doc.querySelectorAll("#basinChips .chip");
  eq(chips.length, 8, "eight training basins");
  eq(A.state.year, 2, "defaults to the season ahead (year 2)");
  ok(/12/.test(doc.getElementById("intensity").value), "default intensity 12");
  ok(doc.getElementById("selfCheckLine").textContent.includes("14/14"), "canary self-check 14/14 at load");
  ok(doc.getElementById("page").contains(doc.querySelector("main")) && doc.getElementById("page").contains(doc.querySelector("footer")), "#page owns the visible canvas");

  // -- sandbox proof FIRST, while live high-water is still low (audit F4) --
  // At load: basin 0 (Eaton Canyon, p50 18 → y2 trigger 23.45), I=12 → advisory.
  eq(A.ARROYO.TIER_ORDER[A.state.live.hw], "advisory", "live high-water starts at advisory");
  const hwBefore = A.state.live.hw;
  doc.getElementById("preset").value = "burst";
  doc.getElementById("simStart").click();
  for (let i = 0; i < 8; i++) doc.getElementById("simStep").click();
  ok(A.state.sim && A.state.sim.hw === 3, "burst preset reaches warning inside the sandbox");
  ok(doc.getElementById("simOut").textContent.length > 0, "sim table rendered");
  doc.getElementById("simExit").click();
  eq(A.state.sim, null, "sandbox destroyed on exit");
  eq(A.state.live.hw, hwBefore, "live session high-water untouched by training run");

  // -- reader interactions --
  chips[3].click();
  eq(doc.getElementById("bName").textContent, "Pasadena Glen", "basin switch");
  const setI = v => {
    const inp = doc.getElementById("intensity");
    inp.value = String(v);
    inp.dispatchEvent(new window.Event("input", { bubbles: true }));
  };
  setI(24);
  // Pasadena Glen publishes p75 = 28.6 → year-2: 24/28.6 = 83.9% → watch
  ok(doc.getElementById("readout").textContent.includes("84%"), "readout fraction vs published p75");
  eq(doc.querySelector(".rung.active").dataset.tier, "watch", "watch rung active at 84%");
  // year 1: 24/22 = 109% → warning
  doc.querySelector('input[name="year"][value="1"]').click();
  eq(doc.querySelector(".rung.active").dataset.tier, "warning", "year-1 flips the same rain to warning");
  ok(doc.getElementById("readout").textContent.includes("109%"), "year-1 fraction");
  doc.querySelector('input[name="year"][value="2"]').click();

  // -- escalation-only display: dropping the rain does not drop the high-water --
  const hwAtPeak = A.state.live.hw;
  setI(3);
  eq(A.state.live.hw, hwAtPeak, "session high-water never de-escalates");
  ok(doc.getElementById("hwLine").textContent.length > 0, "high-water line rendered");

  // -- i18n: Spanish, then Chinese, then parity --
  const lang = doc.getElementById("lang");
  lang.value = "es"; lang.dispatchEvent(new window.Event("change", { bubbles: true }));
  eq(doc.documentElement.lang, "es", "html lang follows selection");
  eq(doc.querySelector("h1").textContent, "Lee la montaña.", "Spanish hero");
  ok(!doc.getElementById("fnLangNote").hidden, "field-notes language note shown in Spanish");
  ok(doc.getElementById("fieldnotes").getAttribute("lang") === "en", "English notes carry lang=en for screen readers");
  lang.value = "zh"; lang.dispatchEvent(new window.Event("change", { bubbles: true }));
  eq(doc.documentElement.lang, "zh-Hans", "Chinese html lang");
  ok(doc.querySelector("h1").textContent.includes("读懂"), "Chinese hero");
  lang.value = "en"; lang.dispatchEvent(new window.Event("change", { bubbles: true }));
  for (const l of ["es", "zh"]) {
    for (const k of Object.keys(A.STRINGS.en)) {
      const v = A.STRINGS[l][k];
      ok(v !== undefined && (Array.isArray(v) ? v.length === A.STRINGS.en[k].length : String(v).length > 0),
        `i18n parity ${l}:${k}`);
    }
  }

  // -- admin gate --
  eq(A.admTryPass("wrong-pass"), false, "wrong passphrase rejected");
  ok(doc.getElementById("admMsg").textContent.includes("Not the passphrase"), "rejection message");
  eq(A.admTryPass("poppy-ink-2026"), true, "correct passphrase unlocks");
  ok(!doc.getElementById("admPanel").hidden, "panel visible after unlock");
  doc.getElementById("admSelftest").click();
  ok(doc.getElementById("admOut").textContent.includes("14/14"), "in-app self-test 14/14");
  doc.getElementById("admInspect").click();
  ok(doc.getElementById("admOut").textContent.includes("VALID"), "training dataset passes structural inspection");

  // -- candidate loader: reject bad, accept good (session-only) --
  const bad = JSON.stringify({ provenance: { mode: "training" }, basins: [{ id: "x", name: "X", lat: 34.1, lon: -118.1, i15_mmh: { p50: 1.0 }, likelihood: 0.5, volume_class: 2, communities: ["Y"] }] });
  doc.getElementById("admJson").value = bad;
  doc.getElementById("admValidate").click();
  ok(doc.getElementById("admOut").textContent.includes("REJECTED"), "candidate below advisory floor rejected");
  const good = JSON.stringify({
    provenance: { mode: "training", dataset_version: "TRAINING-cand", source_url: "test", retrieved: "2026-08-15", units: { i15: "mm/h" } },
    basins: [{ id: "cand", name: "Candidate Canyon", lat: 34.2, lon: -118.1, i15_mmh: { p50: 21.0 }, likelihood: 0.5, volume_class: 2, communities: ["Test"] }]
  });
  doc.getElementById("admJson").value = good;
  doc.getElementById("admValidate").click();
  ok(doc.getElementById("admOut").textContent.includes("ACCEPTED"), "valid candidate accepted for session preview");
  eq(doc.getElementById("bName").textContent, "Candidate Canyon", "preview swaps the reader");
  ok(/CANDIDATE|CONJUNTO|候选/.test(doc.getElementById("modeBanner").textContent), "candidate banner shown");
  doc.getElementById("admLock").click();
  ok(doc.getElementById("admPanel").hidden, "console locks");

  // -- live feeds: off by default, then every staleness state via fixtures --
  ok(doc.getElementById("rainBody").textContent.includes("aren't configured") &&
     doc.getElementById("alertsBody").textContent.includes("aren't configured"), "feeds off by default (honest empty state)");
  const NOW = "2026-08-15T20:00:00Z";
  const rainSnap = age => ({
    provenance: { source: "fixture", fetched_at: new Date(Date.parse(NOW) - age * 60000).toISOString(), units: { rate: "mm/h" } },
    stations: [
      { id: "g1", name: "Eaton Wash Gauge", lat: 34.19, lon: -118.1, basis: "i15", rate_mmh: 26.0, obs_time: NOW },
      { id: "g2", name: "Santa Anita Dam", lat: 34.18, lon: -118.02, basis: "1h", rate_mmh: 9.0, obs_time: NOW }
    ]
  });
  // invalid snapshot: rejected, nothing rendered
  const badSnap = rainSnap(5); badSnap.stations[0].rate_mmh = 999;
  eq(A.applyRain(badSnap, NOW).ok, false, "999 mm/h snapshot rejected by validator");
  ok(doc.getElementById("rainBody").textContent.includes("aren't configured"), "rejected snapshot leaves the panel untouched");
  // fresh: rows render, read-rate feeds the reader
  eq(A.applyRain(rainSnap(10), NOW).ok, true, "fresh snapshot accepted");
  ok(doc.getElementById("rainBody").textContent.includes("Eaton Wash Gauge"), "gauge row rendered");
  ok(doc.getElementById("rainBody").textContent.includes("Updated 10 min ago"), "fresh age stamp");
  const useBtns = doc.querySelectorAll("#rainBody button");
  eq(useBtns.length, 2, "one read-rate button per gauge");
  ok(!useBtns[0].disabled, "fresh → button enabled");
  useBtns[0].click();
  eq(A.state.intensity, 26, "read-rate feeds the reader input");
  ok(doc.getElementById("intensity").value === "26", "input reflects the observed rate");
  ok(doc.getElementById("rainBody").textContent.includes("1-hour rate"), "coarser basis labeled honestly");
  // stale: values visible, action disabled
  A.applyRain(rainSnap(120), NOW);
  ok(doc.getElementById("rainBody").textContent.includes("STALE"), "stale stamp shown");
  ok(doc.querySelector("#rainBody button").disabled, "stale → read-rate disabled");
  // expired: values hidden, explicit not-an-all-clear
  A.applyRain(rainSnap(400), NOW);
  ok(!doc.getElementById("rainBody").textContent.includes("Eaton Wash Gauge"), "expired hides values");
  ok(doc.getElementById("rainBody").textContent.includes("not an all-clear"), "expired states the non-promise");
  // alerts: none-active phrasing, then an active FFW row
  const alertsSnap = (list, age) => ({
    provenance: { source: "api.weather.gov (fixture)", fetched_at: new Date(Date.parse(NOW) - age * 60000).toISOString() },
    alerts: list
  });
  eq(A.applyAlerts(alertsSnap([], 5), NOW).ok, true, "empty alerts snapshot valid");
  ok(doc.getElementById("alertsBody").textContent.includes("No flash-flood"), "quiet state phrased with lag caveat");
  ok(doc.getElementById("alertsBody").textContent.includes("confirm at the official source") ||
     doc.getElementById("alertsBody").textContent.includes("Confirm at the official source") ||
     doc.getElementById("alertsBody").textContent.includes("confirm"), "quiet state points at the source");
  A.applyAlerts(alertsSnap([{ id: "x1", event: "Flash Flood Warning", headline: "FFW for the Eaton burn scar until 4:15 PM", ends: NOW, link: "https://www.weather.gov/lox/" }], 5), NOW);
  ok(doc.getElementById("alertsBody").textContent.includes("Flash Flood Warning"), "active product rendered by its official name");
  ok(doc.querySelector("#alertsBody a").href.startsWith("https://www.weather.gov"), "product links to the office");

  // -- rails in copy: no push, no all-clear promises; official links present --
  const railText = doc.querySelector(".rail").textContent;
  ok(railText.includes("never replaces"), "rail states the boundary");
  for (const host of ["alert.lacounty.gov", "weather.gov/lox", "protect.genasys.com"]) {
    ok(html.includes(host), `official link ${host} present`);
  }

  console.log(`DOM_CHECKS=${DOMCHECKS}`);
});
