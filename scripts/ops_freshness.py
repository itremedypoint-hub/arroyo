#!/usr/bin/env python3
"""Deploy gate: fail if the dataset is training data (with --require-live)
or stale. Run before each wet-season deploy and monthly during the season."""
import json, sys, argparse
from datetime import date, datetime
ap = argparse.ArgumentParser()
ap.add_argument("dataset"); ap.add_argument("--max-days", type=int, default=120)
ap.add_argument("--require-live", action="store_true")
a = ap.parse_args()
d = json.load(open(a.dataset)); p = d.get("provenance", {})
if p.get("mode") == "training":
    print("Dataset is TRAINING data.")
    sys.exit(1 if a.require_live else 0)
age = (date.today() - datetime.fromisoformat(p["retrieved"]).date()).days
print(f"Dataset {p.get('dataset_version')} retrieved {p['retrieved']} ({age} days ago); DOI {p.get('dataset_doi')}")
if age > a.max_days:
    print(f"STALE: exceeds --max-days {a.max_days}. Re-check ScienceBase for a newer Eaton version."); sys.exit(1)
print("Fresh enough.")
