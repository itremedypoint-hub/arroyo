#!/usr/bin/env python3
"""Find REAL observation stations near the Eaton burn scar and write
docs/stations.json. Run this once from a machine with internet — it replaces
guessing station ids with asking the source.

    python3 scripts/discover_stations.py --write

What it does:
  1. Asks api.weather.gov for the observation stations serving the scar
     centroid (34.19, -118.10), nearest first.
  2. Pulls each station's latest observation and keeps only those actually
     reporting precipitationLastHour — a station that never reports rain is
     useless here no matter how close it is.
  3. Records the great-circle distance from the scar so the site can label
     valley stations honestly ("not on the burn scar" beyond 8 km).
  4. Prints a table for you to eyeball, and with --write saves the config.

Every id it writes came from the API in this run, so nothing here is a
placeholder. Still open one station page by hand the first time and confirm
the numbers look like the same weather you see outside.

Synoptic upgrade (better data — true 15-minute intervals from the LA County
ALERT gauges rather than hourly airport observations): get a token at
synopticdata.com, then run with --synoptic to list nearby precipitation
stations and their STIDs, and paste those into the "synoptic" array.
"""
import argparse, json, math, os, sys, urllib.request, urllib.parse

UA = {"User-Agent": "arroyo-community (maintainer contact in repo)", "Accept": "application/geo+json"}
SCAR = (34.19, -118.10)          # Eaton burn scar centroid
OFFSCAR_KM = 8.0


def get(url, hdrs=UA):
    with urllib.request.urlopen(urllib.request.Request(url, headers=hdrs), timeout=25) as r:
        return json.load(r)


def haversine_km(a, b):
    R, r = 6371.0088, math.pi / 180
    dlat, dlon = (b[0] - a[0]) * r, (b[1] - a[1]) * r
    x = math.sin(dlat / 2) ** 2 + math.cos(a[0] * r) * math.cos(b[0] * r) * math.sin(dlon / 2) ** 2
    return 2 * R * math.asin(math.sqrt(x))


def discover_nws(limit):
    pt = get(f"https://api.weather.gov/points/{SCAR[0]},{SCAR[1]}")
    stations_url = pt["properties"]["observationStations"]
    feats = get(stations_url)["features"]
    rows = []
    for f in feats[:limit * 3]:
        p, g = f["properties"], f["geometry"]["coordinates"]
        sid, name = p.get("stationIdentifier"), p.get("name")
        if not sid:
            continue
        lat, lon = g[1], g[0]
        try:
            obs = get(f"https://api.weather.gov/stations/{sid}/observations/latest")["properties"]
        except Exception as e:
            print(f"  skip {sid}: {e}", file=sys.stderr)
            continue
        pr = obs.get("precipitationLastHour") or {}
        reports = "precipitationLastHour" in obs and pr.get("unitCode") is not None
        rows.append({"id": sid, "name": name, "lat": lat, "lon": lon,
                     "km": round(haversine_km(SCAR, (lat, lon)), 1),
                     "reports_precip": bool(reports),
                     "last_obs": obs.get("timestamp")})
        if len([r for r in rows if r["reports_precip"]]) >= limit:
            break
    rows.sort(key=lambda r: r["km"])
    return rows


def discover_synoptic(token, radius_km, limit):
    q = urllib.parse.urlencode({"radius": f"{SCAR[0]},{SCAR[1]},{int(radius_km * 0.621371)}",
                                "vars": "precip_accum_15_minute,precip_accum_one_hour",
                                "status": "active", "limit": limit, "token": token})
    data = get(f"https://api.synopticdata.com/v2/stations/metadata?{q}", {"User-Agent": UA["User-Agent"]})
    rows = []
    for st in data.get("STATION", []):
        lat, lon = float(st["LATITUDE"]), float(st["LONGITUDE"])
        rows.append({"stid": st["STID"], "name": st.get("NAME"), "network": st.get("MNET_ID"),
                     "km": round(haversine_km(SCAR, (lat, lon)), 1)})
    rows.sort(key=lambda r: r["km"])
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=6)
    ap.add_argument("--radius-km", type=float, default=25)
    ap.add_argument("--synoptic", action="store_true", help="also list Synoptic STIDs (needs SYNOPTIC_TOKEN)")
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--out", default="docs/stations.json")
    a = ap.parse_args()

    print(f"Searching for stations near the Eaton scar ({SCAR[0]}, {SCAR[1]})…\n")
    nws = discover_nws(a.limit)
    print(f"{'ID':10s} {'km':>6s}  {'precip?':8s} name")
    for r in nws:
        print(f"{r['id']:10s} {r['km']:6.1f}  {'yes' if r['reports_precip'] else 'no ':8s} {r['name']}")
    usable = [r for r in nws if r["reports_precip"]][:a.limit]
    if not usable:
        sys.exit("\nNo nearby station reports hourly precipitation. Widen --limit, or use --synoptic.")
    far = [r for r in usable if r["km"] > OFFSCAR_KM]
    print(f"\n{len(usable)} usable station(s). "
          f"{len(far)} of them sit more than {OFFSCAR_KM:.0f} km from the scar and the site will label "
          f"them 'valley station — not on the burn scar'.")

    syn = []
    if a.synoptic:
        token = os.environ.get("SYNOPTIC_TOKEN", "")
        if not token:
            print("\nSYNOPTIC_TOKEN not set — skipping the Synoptic lookup.", file=sys.stderr)
        else:
            syn = discover_synoptic(token, a.radius_km, a.limit)
            print(f"\nSynoptic stations within {a.radius_km:.0f} km reporting precipitation:")
            for r in syn:
                print(f"  {r['stid']:10s} {r['km']:6.1f} km  {r['name']}")

    cfg = {"_generated_by": "scripts/discover_stations.py",
           "_scar_centroid": {"lat": SCAR[0], "lon": SCAR[1]},
           "_note": "ids returned by the NWS/Synoptic APIs at generation time — verify one by hand before trusting the feed",
           "nws": [r["id"] for r in usable],
           "synoptic": [r["stid"] for r in syn],
           "names": {r["id"]: r["name"] for r in usable} | {r["stid"]: r["name"] for r in syn},
           "coords": {r["id"]: [r["lat"], r["lon"]] for r in usable}}
    if a.write:
        with open(a.out, "w") as fh:
            json.dump(cfg, fh, indent=2)
        print(f"\nWrote {a.out}. Next: python3 scripts/fetch_rain.py --out - | head -40")
    else:
        print("\n(dry run — re-run with --write to save docs/stations.json)")


if __name__ == "__main__":
    main()
