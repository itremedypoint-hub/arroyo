#!/usr/bin/env python3
"""Fixture tests for the two CI fetchers: unit handling, series extraction,
sanity clamps, county+event filtering, and snapshot validity."""
import json, subprocess, sys, os, tempfile
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
N = 0
def check(c, m):
    global N; assert c, m; N += 1
def run(script, *args):
    return subprocess.run([sys.executable, os.path.join(ROOT, "scripts", script), *args],
                          capture_output=True, text=True)

with tempfile.TemporaryDirectory() as td:
    # rain via NWS fixture: mm passthrough, meters→mm, null dropped
    out = os.path.join(td, "rain_nws.json")
    r = run("fetch_rain.py", "--fixture", os.path.join(HERE, "fixtures", "nws_obs.json"),
            "--fixture-provider", "nws", "--out", out)
    check(r.returncode == 0, f"nws fixture: {r.stderr}")
    d = json.load(open(out))
    by = {s["id"]: s for s in d["stations"]}
    check(len(d["stations"]) == 2 and "FIX3" not in by, "null-precip station dropped")
    check(by["FIX1"]["rate_mmh"] == 6.0 and by["FIX1"]["basis"] == "1h", "mm unit passthrough, 1h basis")
    check(abs(by["FIX2"]["rate_mmh"] - 9.0) < 1e-9, "wmoUnit:m converted (0.009 m → 9 mm/h)")
    check(d["provenance"]["units"]["rate"] == "mm/h", "units stamped")

    # rain via Synoptic fixture: trailing null skipped, 2.5 mm/15min → 10 mm/h, dead gauge dropped
    out2 = os.path.join(td, "rain_syn.json")
    r = run("fetch_rain.py", "--fixture", os.path.join(HERE, "fixtures", "synoptic.json"),
            "--fixture-provider", "synoptic", "--out", out2)
    check(r.returncode == 0, f"synoptic fixture: {r.stderr}")
    d2 = json.load(open(out2))
    check(len(d2["stations"]) == 1, "all-null gauge dropped")
    st = d2["stations"][0]
    check(st["basis"] == "i15" and abs(st["rate_mmh"] - 10.0) < 1e-9, "latest finite 15-min ×4")
    check(st["obs_time"] == "2026-08-15T19:30:00Z", "timestamp follows the used interval, not the null")
    check(st["name"] == "Eaton Wash (fixture)", "names map applied")

    # alerts: LA flood products kept, other-county and non-flood filtered, links https
    out3 = os.path.join(td, "alerts.json")
    r = run("fetch_alerts.py", "--fixture", os.path.join(HERE, "fixtures", "nws_alerts.json"), "--out", out3)
    check(r.returncode == 0, f"alerts fixture: {r.stderr}")
    d3 = json.load(open(out3))
    check(len(d3["alerts"]) == 1, "county+event filter keeps exactly the LA FFW")
    a = d3["alerts"][0]
    check(a["event"] == "Flash Flood Warning" and a["link"].startswith("https://www.weather.gov"),
          "kept row is the FFW, linked to the office")
    check(d3["provenance"]["filter"].startswith("Los Angeles"), "filter recorded in provenance")

print(f"FETCHER_CHECKS={N}")
print("test_fetchers: PASS")
