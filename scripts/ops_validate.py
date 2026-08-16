#!/usr/bin/env python3
"""Validate a basins dataset. Training datasets (provenance.mode=="training")
are checked structurally; live datasets are additionally checked against the
JSON schema in verify/basins_eaton.schema.json when jsonschema is installed,
and MUST carry a real DOI. Exit 0 = valid, 1 = invalid, 2 = valid with
warnings (--strict turns warnings into failures)."""
import json, sys, argparse, importlib.util
sys.path.insert(0, __file__.rsplit("/", 1)[0])
from build_basins import validate as live_validate, ADVISORY_FLOOR, Y2

def training_validate(d):
    errs, warn = [], []
    p = d.get("provenance", {})
    for f in ("dataset_version", "source_url", "retrieved", "units"):
        if not p.get(f): errs.append(f"provenance.{f} missing")
    if p.get("units", {}).get("i15") != "mm/h": errs.append('units.i15 must be "mm/h"')
    for i, b in enumerate(d.get("basins", [])):
        at = f"basins[{i}] "
        p50 = b.get("i15_mmh", {}).get("p50")
        if p50 is None or p50 <= ADVISORY_FLOOR: errs.append(at + "p50 missing or ≤ floor")
        if not b.get("communities"): errs.append(at + "communities missing")
        if not (34.0 <= b.get("lat", 0) <= 34.4 and -118.3 <= b.get("lon", 0) <= -117.9):
            errs.append(at + "coordinates outside Eaton range")
    if not d.get("basins"): errs.append("no basins")
    return errs, warn

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dataset"); ap.add_argument("--strict", action="store_true")
    a = ap.parse_args()
    d = json.load(open(a.dataset))
    training = d.get("provenance", {}).get("mode") == "training"
    errs, warn = (training_validate if training else live_validate)(d)
    if not training and importlib.util.find_spec("jsonschema"):
        import jsonschema
        schema = json.load(open(__file__.rsplit("/scripts/", 1)[0] + "/verify/basins_eaton.schema.json"))
        try: jsonschema.validate(d, schema)
        except jsonschema.ValidationError as e: errs.append("jsonschema: " + e.message)
    for w in warn: print("WARN:", w)
    for e in errs: print("ERROR:", e)
    mode = "training" if training else "live"
    if errs: print(f"INVALID ({mode})"); return 1
    print(f"VALID ({mode}, {len(d['basins'])} basins)" + (" — warnings above" if warn else ""))
    return 2 if (warn and a.strict) else 0

if __name__ == "__main__": sys.exit(main())
