#!/usr/bin/env python3
"""Fetch observed rain near the Eaton scar and write the static snapshot the
site reads (site/data/rain_latest.json). Runs in CI on a schedule — never in
the visitor's browser (audit F6: tokens and third-party calls stay
server-side; the client only ever fetches same-origin files).

Providers:
  synoptic  15-minute precipitation intervals → basis "i15" (the real thing).
            Requires SYNOPTIC_TOKEN in the environment (GitHub secret).
  nws       Keyless api.weather.gov station observations →
            precipitationLastHour → basis "1h". Honest but coarser: hourly
            rates smooth the bursts that trigger debris flows, so the site
            labels them as a floor. Used automatically when no token is set.

Stations come from docs/stations.json:
  { "nws": ["STATION_ID", ...], "synoptic": ["STID", ...],
    "names": {"STATION_ID": "Human name", ...} }
Pick real gauges once (NWS station pages / county ALERT list / Synoptic
metadata) — this repo ships only docs/stations.example.json so nobody
mistakes placeholders for instruments.

Sanity rails: rates are clamped to [0, 200] mm/h — anything outside drops the
station with a warning; if nothing usable remains the run fails and the
previous snapshot stays deployed (the site then ages it to STALE → EXPIRED,
which is the correct public behavior for a dead feed).
"""
import argparse, json, os, sys, urllib.request
from datetime import datetime, timezone

UA = {"User-Agent": "arroyo-community (maintainer contact in repo)", "Accept": "application/json"}
MAX_RATE = 200.0
SCAR = (34.19, -118.10)          # Eaton burn scar centroid, for distance labeling


def haversine_km(a, b):
    import math
    R, r = 6371.0088, math.pi / 180
    dlat, dlon = (b[0] - a[0]) * r, (b[1] - a[1]) * r
    x = math.sin(dlat / 2) ** 2 + math.cos(a[0] * r) * math.cos(b[0] * r) * math.sin(dlon / 2) ** 2
    return 2 * R * math.asin(math.sqrt(x))


def now_iso():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=20) as r:
        return json.load(r)


def mm_from(value, unit_code):
    if value is None:
        return None
    u = (unit_code or "").lower()
    if u.endswith(":mm") or u == "mm":
        return float(value)
    if u.endswith(":m") or u == "m":
        return float(value) * 1000.0
    if u.endswith(":in") or u == "in":
        return float(value) * 25.4
    raise ValueError(f"unrecognized precipitation unit {unit_code!r} — refusing to guess")


def parse_nws_observation(payload, sid, name):
    p = payload.get("properties", {})
    pr = p.get("precipitationLastHour") or {}
    mm = mm_from(pr.get("value"), pr.get("unitCode"))
    if mm is None:
        return None
    return {"id": sid, "name": name, "basis": "1h", "rate_mmh": round(mm, 2),
            "accum_mm": round(mm, 2), "obs_time": p.get("timestamp")}


def parse_synoptic(payload, names):
    out = []
    for st in payload.get("STATION", []):
        sid = st.get("STID", "?")
        obs = st.get("OBSERVATIONS", {})
        times = obs.get("date_time", [])
        series_key = next((k for k in obs if k.startswith("precip_intervals")), None)
        vals = obs.get(series_key, []) if series_key else []
        series = [{"t": t, "mm": (float(v) if v is not None else None)}
                  for t, v in zip(times, vals)]
        latest = None
        for e in reversed(series):
            if e["mm"] is not None and e["mm"] >= 0:
                latest = e
                break
        if latest is None:
            continue
        out.append({"id": sid, "name": names.get(sid, sid), "basis": "i15",
                    "rate_mmh": round(latest["mm"] * 4, 2), "accum_mm": round(latest["mm"], 2),
                    "obs_time": latest["t"],
                    "lat": float(st["LATITUDE"]) if st.get("LATITUDE") else None,
                    "lon": float(st["LONGITUDE"]) if st.get("LONGITUDE") else None})
    return out


def validate(snap):
    errs = []
    p = snap.get("provenance", {})
    if not p.get("source"): errs.append("provenance.source missing")
    try: datetime.fromisoformat(p.get("fetched_at", "").replace("Z", "+00:00"))
    except Exception: errs.append("provenance.fetched_at not ISO")
    if p.get("units", {}).get("rate") != "mm/h": errs.append("units.rate must be mm/h")
    if not snap.get("stations"): errs.append("no usable stations")
    for i, st in enumerate(snap.get("stations", [])):
        if st.get("basis") not in ("i15", "1h"): errs.append(f"stations[{i}] bad basis")
        r = st.get("rate_mmh")
        if not isinstance(r, (int, float)) or not (0 <= r <= MAX_RATE):
            errs.append(f"stations[{i}] rate {r} outside 0–{MAX_RATE}")
        if not st.get("obs_time"): errs.append(f"stations[{i}] obs_time missing")
    return errs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", choices=["auto", "synoptic", "nws"], default="auto")
    ap.add_argument("--stations", default="docs/stations.json")
    ap.add_argument("--fixture", help="parse a canned payload instead of the network (tests)")
    ap.add_argument("--fixture-provider", choices=["synoptic", "nws"])
    ap.add_argument("--out", default="site/data/rain_latest.json")
    a = ap.parse_args()

    token = os.environ.get("SYNOPTIC_TOKEN", "")
    provider = a.provider
    if provider == "auto":
        provider = "synoptic" if token else "nws"

    stations = []
    if a.fixture:
        payload = json.load(open(a.fixture))
        fp = a.fixture_provider or provider
        if fp == "synoptic":
            names = payload.pop("_names", {})
            stations = parse_synoptic(payload, names)
            source = "synoptic (fixture)"
        else:
            for entry in payload["observations"]:
                st = parse_nws_observation(entry["payload"], entry["id"], entry["name"])
                if st: stations.append(st)
            source = "api.weather.gov (fixture)"
    else:
        cfg = json.load(open(a.stations))
        names = cfg.get("names", {})
        if provider == "synoptic":
            if not token:
                sys.exit("SYNOPTIC_TOKEN not set; use --provider nws or set the secret.")
            stids = ",".join(cfg["synoptic"])
            url = ("https://api.synopticdata.com/v2/stations/precip"
                   f"?stid={stids}&pmode=intervals&interval=15&recent=90&units=metric&token={token}")
            stations = parse_synoptic(get(url), names)
            source = "synopticdata.com (15-min intervals)"
        else:
            for sid in cfg["nws"]:
                try:
                    st = parse_nws_observation(get(f"https://api.weather.gov/stations/{sid}/observations/latest"),
                                               sid, names.get(sid, sid))
                    if st: stations.append(st)
                except Exception as e:
                    print(f"WARN: {sid}: {e}", file=sys.stderr)
            source = "api.weather.gov (hourly observations)"

    coords = {}
    if not a.fixture:
        try:
            coords = json.load(open(a.stations)).get("coords", {})
        except Exception:
            coords = {}
    for st in stations:
        c = coords.get(st["id"]) or ([st.get("lat"), st.get("lon")] if st.get("lat") is not None else None)
        if c and c[0] is not None:
            st["dist_km"] = round(haversine_km(SCAR, (float(c[0]), float(c[1]))), 1)

    kept = []
    for st in stations:
        if 0 <= st["rate_mmh"] <= MAX_RATE:
            kept.append(st)
        else:
            print(f"WARN: dropping {st['id']} — rate {st['rate_mmh']} outside sanity bounds", file=sys.stderr)

    snap = {"provenance": {"source": source, "fetched_at": now_iso(),
                           "station_count": len(kept), "units": {"rate": "mm/h", "accum": "mm"},
                           "built_by": "scripts/fetch_rain.py"},
            "stations": kept}
    errs = validate(snap)
    if errs:
        for e in errs: print("ERROR:", e, file=sys.stderr)
        sys.exit("INVALID snapshot — nothing written; previous snapshot remains deployed.")
    out = sys.stdout if a.out == "-" else open(a.out, "w")
    json.dump(snap, out, indent=1)
    if a.out != "-":
        out.close()
        print(f"Wrote {a.out}: {len(kept)} stations via {source}")


if __name__ == "__main__":
    main()
