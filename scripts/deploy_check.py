#!/usr/bin/env python3
"""Audit a DEPLOYED Arroyo site from the outside. Run locally (not in CI):

    python3 scripts/deploy_check.py https://youruser.github.io/arroyo/

Checks what a visitor actually receives: the page, the data slots, staleness
of both live snapshots, security headers, and the rails/attribution text.
Exit 0 = all pass, 1 = at least one FAIL. WARNs never fail the run."""
import json, sys, urllib.request, urllib.error
from datetime import datetime, timezone

UA = {"User-Agent": "arroyo-deploy-check"}
P = F = W = 0

def ok(m):   globals().__setitem__('P', P+1); print(f"  PASS  {m}")
def bad(m):  globals().__setitem__('F', F+1); print(f"  FAIL  {m}")
def warn(m): globals().__setitem__('W', W+1); print(f"  WARN  {m}")

def fetch(url):
    r = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=20)
    return r.status, dict(r.headers), r.read().decode("utf-8", "replace")

def age_min(iso):
    t = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    return (datetime.now(timezone.utc) - t).total_seconds() / 60

def main():
    if len(sys.argv) < 2:
        sys.exit("usage: deploy_check.py https://host/path/")
    base = sys.argv[1].rstrip("/") + "/"
    print(f"\nArroyo deploy check — {base}\n")

    print("PAGE")
    try:
        st, hdr, body = fetch(base)
    except Exception as e:
        sys.exit(f"  FAIL  cannot load the site: {e}")
    ok(f"HTTP {st}, {len(body)//1024} KB") if st == 200 else bad(f"HTTP {st}")
    for needle, label in [
        ("supplements official alerts", "top rail present"),
        ("Content-Security-Policy", "CSP meta tag present"),
        ("<noscript>", "noscript fallback present"),
        ("AI assistance (Claude, Anthropic)", "AI attribution present"),
        ("alert.lacounty.gov", "Alert LA County link present"),
        ("protect.genasys.com", "Genasys link present"),
        ("ARROYO_ENGINE_START", "engine block shipped"),
        ("id=\"live\"", "live-observations section shipped")]:
        ok(label) if needle in body else bad(label + " — MISSING")
    if "rotate(225" in body: bad("season ring still hardcoded to a fixed date")
    else: ok("season ring is runtime-dated")

    print("\nHEADERS")
    csp = hdr.get("Content-Security-Policy")
    ok("CSP header set by host") if csp else warn("no CSP response header (GitHub Pages ignores _headers; meta CSP still applies)")
    ok("frame-ancestors set") if csp and "frame-ancestors" in csp else warn("no frame-ancestors — the page can be framed by others (host limitation)")
    ok("nosniff set") if hdr.get("X-Content-Type-Options") else warn("no X-Content-Type-Options")

    print("\nTHRESHOLD DATA")
    try:
        _, _, raw = fetch(base + "data/basins_eaton.json")
        d = json.loads(raw)
        p = d.get("provenance", {})
        if p.get("mode") == "training": warn("dataset present but labeled training")
        else:
            ok(f"live dataset: {p.get('dataset_version')} · DOI {p.get('dataset_doi')} · {len(d['basins'])} basins")
            if not str(p.get("dataset_doi", "")).startswith("10.5066/"): bad("dataset_doi is not a USGS 10.5066 DOI")
            if p.get("units", {}).get("i15") != "mm/h": bad("units.i15 is not mm/h")
    except urllib.error.HTTPError as e:
        warn(f"no data/basins_eaton.json ({e.code}) — site runs in labeled TRAINING mode") if e.code == 404 else bad(str(e))
    except Exception as e:
        bad(f"basins_eaton.json unreadable: {e}")

    print("\nLIVE SNAPSHOTS")
    for name, key in [("rain_latest.json", "stations"), ("alerts_latest.json", "alerts")]:
        try:
            _, _, raw = fetch(base + "data/" + name)
            d = json.loads(raw)
            a = age_min(d["provenance"]["fetched_at"])
            n = len(d.get(key, []))
            state = "fresh" if a <= 45 else "stale" if a <= 360 else "EXPIRED"
            msg = f"{name}: {n} {key}, {a:.0f} min old ({state}), source {d['provenance']['source']}"
            ok(msg) if a <= 45 else (warn(msg) if a <= 360 else bad(msg + " — the scheduled job is not running"))
        except urllib.error.HTTPError as e:
            warn(f"{name} absent ({e.code}) — live panel shows its 'feeds off' state") if e.code == 404 else bad(str(e))
        except Exception as e:
            bad(f"{name}: {e}")

    print(f"\n{P} passed · {W} warnings · {F} failed\n")
    return 1 if F else 0

if __name__ == "__main__":
    sys.exit(main())
