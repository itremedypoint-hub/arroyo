#!/usr/bin/env python3
"""Fixture test for the real-data ingestion path: a synthetic PWFDF-shaped
GeoJSON goes in; a valid basins_eaton.json must come out, with correct unit
scaling, provenance, traceability, and refusal behavior. Plain asserts."""
import json, subprocess, sys, tempfile, os
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SCRIPT = os.path.join(ROOT, "scripts", "build_basins.py")
N = 0
def check(cond, msg):
    global N
    assert cond, msg
    N += 1

fixture = {"type": "FeatureCollection", "features": [
    {"type": "Feature",
     "properties": {"Segment_ID": "EAT_001", "BasinName": "Fixture Canyon A",
                    "I15_P50": 0.7087, "I15_P75": None, "PDF_Lik": 0.81, "VolCls": 3,
                    "Towns": "Altadena, Pasadena"},
     "geometry": {"type": "Polygon", "coordinates": [[[-118.10, 34.19], [-118.09, 34.19], [-118.09, 34.20], [-118.10, 34.20], [-118.10, 34.19]]]}},
    {"type": "Feature",
     "properties": {"Segment_ID": "EAT_002", "BasinName": "Fixture Canyon B",
                    "I15_P50": 1.0236, "I15_P75": 1.4, "PDF_Lik": 0.55, "VolCls": 2,
                    "Towns": "Sierra Madre"},
     "geometry": {"type": "Point", "coordinates": [-118.05, 34.18]}}]}
mapping = {"id": "Segment_ID", "name": "BasinName", "i15_p50": "I15_P50",
           "i15_p75": "I15_P75", "likelihood": "PDF_Lik", "volume_class": "VolCls",
           "communities": "Towns"}

with tempfile.TemporaryDirectory() as td:
    gj = os.path.join(td, "f.geojson"); mp = os.path.join(td, "m.json"); out = os.path.join(td, "out.json")
    json.dump(fixture, open(gj, "w")); json.dump(mapping, open(mp, "w"))

    # --list-fields introspection
    r = subprocess.run([sys.executable, SCRIPT, "--geojson", gj, "--list-fields"],
                       capture_output=True, text=True)
    check(r.returncode == 0 and "Segment_ID" in r.stdout, "--list-fields lists attributes")

    # inches/hour source → mm/h output (0.7087 in/h ≈ 18.0 mm/h)
    r = subprocess.run([sys.executable, SCRIPT, "--geojson", gj, "--mapping", mp,
                        "--dataset-doi", "10.5066/P14EWYME", "--dataset-version", "fixture v1",
                        "--source-url", "https://doi.org/10.5066/P14EWYME",
                        "--units", "inh", "--min-basins", "1", "--out", out],
                       capture_output=True, text=True)
    check(r.returncode == 0, f"build succeeds: {r.stderr}")
    d = json.load(open(out))
    check(d["provenance"]["spec_doi"] == "10.5066/P13KUWCO", "spec DOI stamped")
    check(d["provenance"]["dataset_doi"].startswith("10.5066/"), "dataset DOI stamped")
    check(d["provenance"]["units"]["i15"] == "mm/h", "units normalized to mm/h")
    b = {x["id"]: x for x in d["basins"]}
    check(abs(b["eat_001"]["i15_mmh"]["p50"] - 18.0) < 0.01, "0.7087 in/h → 18.0 mm/h")
    check(abs(b["eat_002"]["i15_mmh"]["p75"] - 35.56) < 0.01, "p75 scaled too")
    check(b["eat_001"]["communities"] == ["Altadena", "Pasadena"], "communities split from CSV field")
    check(b["eat_001"]["usgs_fields"]["segment_or_basin_id"] == "EAT_001", "traceability id")
    check(b["eat_001"]["usgs_fields"]["threshold_field_name"] == "I15_P50", "traceability field")
    check(34.0 <= b["eat_001"]["lat"] <= 34.4 and -118.3 <= b["eat_001"]["lon"] <= -117.9, "polygon centroid in range")
    check(d["basins"][0]["i15_mmh"]["p50"] <= d["basins"][1]["i15_mmh"]["p50"], "sorted by p50")

    # refusal: values that look like 15-min accumulations must hard-stop (audit F2)
    r = subprocess.run([sys.executable, SCRIPT, "--geojson", gj, "--mapping", mp,
                        "--dataset-doi", "10.5066/P14EWYME", "--dataset-version", "fixture",
                        "--source-url", "x", "--units", "mmh", "--min-basins", "1", "--out", out + "2"],
                       capture_output=True, text=True)
    check(r.returncode != 0 and "ACCUMULATION" in (r.stderr + r.stdout).upper(),
          "refuses accumulation-looking values instead of guessing ×4")
    check(not os.path.exists(out + "2"), "invalid build writes nothing")

    # refusal: below --min-basins
    one = dict(fixture); one["features"] = fixture["features"][:1]
    json.dump(one, open(gj, "w"))
    r = subprocess.run([sys.executable, SCRIPT, "--geojson", gj, "--mapping", mp,
                        "--dataset-doi", "10.5066/P14EWYME", "--dataset-version", "f",
                        "--source-url", "x", "--units", "inh", "--out", out + "3"],
                       capture_output=True, text=True)
    check(r.returncode != 0 and "min-basins" in r.stderr + r.stdout, "count floor enforced by default")

print(f"BUILD_BASINS_CHECKS={N}")
print("test_build_basins: PASS")
