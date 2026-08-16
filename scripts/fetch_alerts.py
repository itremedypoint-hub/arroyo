#!/usr/bin/env python3
"""Fetch active NWS products relevant to the Eaton scar and write
site/data/alerts_latest.json. Keyless (api.weather.gov), CI-only.

Filter: statewide active alerts → Los Angeles County areas → flood/debris/
evacuation-relevant events. Every row links to the issuing office page
(weather.gov/lox) rather than a raw API URL, because the office page is the
thing a resident should learn to read. An empty list is a normal, honest
output — the site pairs it with a lag caveat, never an all-clear."""
import argparse, json, sys, urllib.request
from datetime import datetime, timezone

UA = {"User-Agent": "arroyo-community (maintainer contact in repo)", "Accept": "application/geo+json"}
KEEP = ("flash flood", "flood", "debris", "evacuation", "hydrologic")
OFFICE = "https://www.weather.gov/lox/"

def now_iso():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

def relevant(props):
    area = (props.get("areaDesc") or "").lower()
    if "los angeles" not in area:
        return False
    text = " ".join(str(props.get(k) or "") for k in ("event", "headline", "description")).lower()
    return any(k in text for k in KEEP)

def build(features):
    rows = []
    for f in features:
        p = f.get("properties", {})
        if not relevant(p):
            continue
        rows.append({"id": p.get("id") or f.get("id") or "?",
                     "event": p.get("event", "?"),
                     "headline": p.get("headline") or p.get("event", ""),
                     "onset": p.get("onset"), "ends": p.get("ends") or p.get("expires"),
                     "link": OFFICE})
    return rows

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fixture"); ap.add_argument("--out", default="site/data/alerts_latest.json")
    a = ap.parse_args()
    if a.fixture:
        payload = json.load(open(a.fixture)); source = "api.weather.gov (fixture)"
    else:
        req = urllib.request.Request("https://api.weather.gov/alerts/active?area=CA", headers=UA)
        with urllib.request.urlopen(req, timeout=20) as r:
            payload = json.load(r)
        source = "api.weather.gov/alerts/active?area=CA"
    snap = {"provenance": {"source": source, "fetched_at": now_iso(),
                           "filter": "Los Angeles County · flood/debris/evacuation",
                           "built_by": "scripts/fetch_alerts.py"},
            "alerts": build(payload.get("features", []))}
    for i, al in enumerate(snap["alerts"]):
        if not al["link"].startswith("https://"):
            sys.exit(f"alerts[{i}] non-https link — refusing")
    out = sys.stdout if a.out == "-" else open(a.out, "w")
    json.dump(snap, out, indent=1)
    if a.out != "-":
        out.close()
        print(f"Wrote {a.out}: {len(snap['alerts'])} relevant alert(s)")

if __name__ == "__main__":
    main()
