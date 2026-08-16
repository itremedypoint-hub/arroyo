#!/usr/bin/env python3
"""Build site/data/basins_eaton.json from a GeoJSON export of the USGS
post-fire debris-flow assessment for the Eaton Fire.

Typical path from the official release (DOI 10.5066/P14EWYME):
  1. Download the assessment zip from ScienceBase and unzip it.
  2. Export the basin/segment layer to GeoJSON, e.g.:
       ogr2ogr -f GeoJSON basins.geojson <file.gdb|shapefile> <layer>
  3. Introspect the attribute names once:
       python3 scripts/build_basins.py --geojson basins.geojson --list-fields
  4. Write mapping.json pointing at the real field names, then:
       python3 scripts/build_basins.py --geojson basins.geojson \
         --mapping mapping.json --dataset-doi 10.5066/P14EWYME \
         --dataset-version "Eaton 2025-01-08 v1.0" \
         --source-url "https://doi.org/10.5066/P14EWYME" \
         --out site/data/basins_eaton.json

mapping.json example (keys on the left are Arroyo's; values are the
attribute names found in step 3):
  { "id": "Segment_ID", "name": "Basin_Name",
    "i15_p50": "RainAtP50_i15_mmh", "i15_p75": null,
    "likelihood": "PDFLikelihood", "volume_class": "VolClass",
    "communities": null }
If "communities" is null, provide --communities-json id_to_communities.json
(hand-maintained: {"<basin id>": ["Altadena", ...], ...}).

Design rules enforced here (they mirror the in-app validator and the JSON
schema in verify/):
  * i15 values are 15-minute INTENSITIES in mm/h. If the source column is
    inches/hour pass --units inh. If the numbers look like 15-minute
    accumulations (suspiciously small), the build refuses: re-read the spec
    field description rather than overriding (audit F2).
  * Every basin carries a usgs_fields traceability block naming the source
    row id and threshold column.
  * Output is validated before it is written; an invalid build writes nothing.
Stdlib only.
"""
import argparse, json, statistics, sys
from datetime import date

SPEC_DOI = "10.5066/P13KUWCO"
ADVISORY_FLOOR = 2.0
Y2 = 1.302648013407  # 1 + ln 3 / 3.63


def centroid(geom):
    t = geom.get("type"); c = geom.get("coordinates")
    if t == "Point":
        return c[1], c[0]
    if t == "Polygon":
        ring = c[0]
    elif t == "MultiPolygon":
        ring = max((poly[0] for poly in c), key=len)
    elif t == "LineString":
        ring = c
    else:
        raise ValueError(f"unsupported geometry type {t}")
    lats = [p[1] for p in ring]; lons = [p[0] for p in ring]
    return sum(lats) / len(lats), sum(lons) / len(lons)


def validate(dataset):
    errs, warn = [], []
    p = dataset["provenance"]
    if not str(p.get("dataset_doi", "")).startswith("10.5066/"):
        errs.append("provenance.dataset_doi must be a 10.5066/… DOI")
    if p.get("spec_doi") != SPEC_DOI:
        errs.append(f"provenance.spec_doi must be {SPEC_DOI}")
    if p.get("units", {}).get("i15") != "mm/h":
        errs.append('provenance.units.i15 must be "mm/h"')
    seen = set()
    for i, b in enumerate(dataset["basins"]):
        at = f"basins[{i}] "
        if not b.get("id") or b["id"] in seen:
            errs.append(at + "id missing or duplicate")
        seen.add(b.get("id"))
        if not (34.0 <= b.get("lat", 0) <= 34.4):
            errs.append(at + f"lat {b.get('lat')} outside Eaton range 34.0–34.4")
        if not (-118.3 <= b.get("lon", 0) <= -117.9):
            errs.append(at + f"lon {b.get('lon')} outside Eaton range −118.3…−117.9")
        p50 = b.get("i15_mmh", {}).get("p50")
        if p50 is None:
            errs.append(at + "i15_mmh.p50 missing")
        else:
            if p50 <= ADVISORY_FLOOR:
                errs.append(at + f"p50 {p50} ≤ advisory floor {ADVISORY_FLOOR}")
            if p50 > 80:
                errs.append(at + f"p50 {p50} implausibly high — check units")
            p75 = b.get("i15_mmh", {}).get("p75")
            if p75 is not None:
                if p75 <= p50:
                    errs.append(at + "p75 must exceed p50")
                elif abs(p75 - p50 * Y2) / (p50 * Y2) > 0.25:
                    warn.append(at + "p75 differs >25% from p50×1.3026 — fine if published; verify mapping")
        if not (0 <= b.get("likelihood", -1) <= 1):
            errs.append(at + "likelihood must be 0–1")
        if b.get("volume_class") not in (1, 2, 3, 4):
            errs.append(at + "volume_class must be integer 1–4")
        if not b.get("communities"):
            errs.append(at + "communities: at least one required")
        uf = b.get("usgs_fields", {})
        if not uf.get("segment_or_basin_id") or not uf.get("threshold_field_name"):
            errs.append(at + "usgs_fields traceability block incomplete")
    return errs, warn


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--geojson", required=True)
    ap.add_argument("--mapping")
    ap.add_argument("--communities-json")
    ap.add_argument("--dataset-doi")
    ap.add_argument("--dataset-version")
    ap.add_argument("--source-url")
    ap.add_argument("--retrieved", default=date.today().isoformat())
    ap.add_argument("--units", choices=["mmh", "inh"], default="mmh")
    ap.add_argument("--min-basins", type=int, default=8,
                    help="safety floor; lower only for test fixtures")
    ap.add_argument("--out")
    ap.add_argument("--list-fields", action="store_true")
    a = ap.parse_args()

    gj = json.load(open(a.geojson))
    feats = gj["features"]
    if a.list_fields:
        keys = sorted({k for f in feats for k in f.get("properties", {})})
        print(f"{len(feats)} features. Attribute fields:")
        for k in keys:
            sample = next((f["properties"][k] for f in feats if f["properties"].get(k) is not None), None)
            print(f"  {k:32s} e.g. {sample!r}")
        return 0

    for flag in ("mapping", "dataset_doi", "dataset_version", "source_url", "out"):
        if not getattr(a, flag):
            ap.error(f"--{flag.replace('_','-')} is required unless --list-fields")
    m = json.load(open(a.mapping))
    comm = json.load(open(a.communities_json)) if a.communities_json else {}
    scale = 25.4 if a.units == "inh" else 1.0

    basins = []
    for f in feats:
        pr = f["properties"]
        bid = str(pr[m["id"]]).strip().lower().replace(" ", "_")
        lat, lon = centroid(f["geometry"])
        p50 = float(pr[m["i15_p50"]]) * scale
        entry = {
            "id": bid,
            "name": str(pr[m["name"]]) if m.get("name") else bid,
            "lat": round(lat, 4), "lon": round(lon, 4),
            "i15_mmh": {"p50": round(p50, 2)},
            "likelihood": round(float(pr[m["likelihood"]]), 3),
            "volume_class": int(pr[m["volume_class"]]),
            "communities": comm.get(bid) or (pr.get(m["communities"]) if m.get("communities") else None),
            "usgs_fields": {"segment_or_basin_id": str(pr[m["id"]]),
                            "threshold_field_name": m["i15_p50"]},
        }
        if isinstance(entry["communities"], str):
            entry["communities"] = [s.strip() for s in entry["communities"].split(",") if s.strip()]
        if m.get("i15_p75") and pr.get(m["i15_p75"]) is not None:
            entry["i15_mmh"]["p75"] = round(float(pr[m["i15_p75"]]) * scale, 2)
        basins.append(entry)

    med = statistics.median(b["i15_mmh"]["p50"] for b in basins)
    if med < ADVISORY_FLOOR:
        sys.exit(f"REFUSING: median p50 {med} mm/h is below the advisory floor — these look like "
                 "15-minute ACCUMULATIONS, not intensities. Re-read the spec field description "
                 "(audit F2); do not multiply by 4 unless the spec says the field is accumulation.")
    if med < 8:
        print(f"WARNING: median p50 {med} mm/h is unusually low for i15 — verify the field mapping.", file=sys.stderr)
    if len(basins) < a.min_basins:
        sys.exit(f"REFUSING: only {len(basins)} basins (< --min-basins {a.min_basins}).")

    basins.sort(key=lambda b: b["i15_mmh"]["p50"])
    dataset = {
        "provenance": {
            "dataset_doi": a.dataset_doi,
            "dataset_version": a.dataset_version,
            "spec_doi": SPEC_DOI,
            "source_url": a.source_url,
            "retrieved": a.retrieved,
            "units": {"i15": "mm/h"},
            "built_by": "scripts/build_basins.py",
        },
        "basins": basins,
    }
    errs, warn = validate(dataset)
    for w in warn:
        print("WARN:", w, file=sys.stderr)
    if errs:
        for e in errs:
            print("ERROR:", e, file=sys.stderr)
        sys.exit("INVALID — nothing written.")
    with open(a.out, "w") as fh:
        json.dump(dataset, fh, indent=2, ensure_ascii=False)
    print(f"Wrote {a.out}: {len(basins)} basins, "
          f"p50 range {basins[0]['i15_mmh']['p50']}–{basins[-1]['i15_mmh']['p50']} mm/h "
          f"(after sort), DOI {a.dataset_doi}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
