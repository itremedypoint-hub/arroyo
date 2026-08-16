#!/usr/bin/env python3
"""Monthly link check for every official destination the site points to.
A hazard-literacy page with a dead official link is worse than none."""
import json, sys, urllib.request
links = json.load(open(__file__.rsplit("/scripts/", 1)[0] + "/docs/links.json"))
if "--skip-network" in sys.argv:
    print(f"{len(links)} links registered (network check skipped here)."); sys.exit(0)
bad = 0
for u in links:
    req = urllib.request.Request(u, method="HEAD", headers={"User-Agent": "arroyo-linkcheck"})
    try:
        with urllib.request.urlopen(req, timeout=12) as r: print(f"  {r.status}  {u}")
    except Exception as e:
        try:
            req = urllib.request.Request(u, headers={"User-Agent": "arroyo-linkcheck"})
            with urllib.request.urlopen(req, timeout=12) as r: print(f"  {r.status}  {u} (GET)")
        except Exception as e2:
            print(f"  FAIL {u}  {e2}"); bad += 1
sys.exit(1 if bad else 0)
