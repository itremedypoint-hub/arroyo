# Arroyo — deploy audit fixes & go-live guide
**Audited:** https://itremedypoint-hub.github.io/arroyo/ · 2026-08-15
**Verdict:** deployment healthy; four fixes applied; live panel needs one config step you must do.

---

## Part 1 — What the audit found

**Healthy.** The site serves the newest build (live-observations section present), returns HTTP 200 with correct title and meta, and every safety rail survived deployment: the "supplements official alerts" bar with all three official links, the TRAINING banner, trilingual controls, literacy core, field notes, and citations. All outbound links are https. Because it's a project page served with a trailing slash, the relative `data/` fetches resolve correctly to `/arroyo/data/…` — the failure that most often breaks project-page deploys silently.

| # | Finding | Severity | Status |
|---|---------|----------|--------|
| 1 | Season ring's "today" marker hardcoded to Aug 15 | Medium — visibly wrong by November, on a seasonal graphic | **Fixed** |
| 2 | No `<noscript>` fallback; reader renders empty without JS | Medium — hazard page should degrade gracefully | **Fixed** |
| 3 | `site/_headers` is inert on GitHub Pages (no `frame-ancestors`, `nosniff`, referrer policy) | Low — no secrets, no user data; meta CSP still applies | **Documented**, see Part 3 |
| 4 | Live panel empty; still TRAINING data | Expected, not a deploy fault | **Part 2 unblocks it** |

---

## Part 2 — What changed in this build

**1. The season ring is now runtime-dated.** Marker angle, post-fire year, wet-season phrasing, and the SVG screen-reader description are all computed from the current date against the Eaton ignition date (2025-01-07). Two new pure functions, `postFireYear()` and `ringAngleDeg()`, are pinned by 31 new oracle cases including leap day and both season boundaries. A post-fire year counts *wet seasons*, not calendar years, so the 2026–27 season is year 2.

**2. The reader's default season follows the calendar**, clamped to the year-2 ceiling. Past year 2 a note appears saying the convention has run out and an updated USGS assessment is needed — the app declines to extrapolate rather than quietly guessing.

**3. `<noscript>` fallback** placed above the fold: names what won't work, links to the literacy core, field notes, and resources (all of which render as static HTML), and points at the USGS dashboard for thresholds.

**4. Gauge distance honesty.** Every station now carries its distance from the scar centroid, shown as a badge; anything beyond 8 km is labeled **"valley station — not on the burn scar"** in all three languages. This matters because the keyless NWS route only reaches airport stations 10–15 km away in the valley, and "Observed rain near the scar" would otherwise overclaim.

**5. Two new tools.** `scripts/discover_stations.py` finds real station IDs from the NWS API; `scripts/deploy_check.py` audits a deployed site from the outside.

Verification now stands at **840 checks, all green** (`make verify`).

---

## Part 3 — Getting the live panel populated

Do these in order. Steps 1 and 2 are the ones that actually unblock it.

### Step 1 — Set the Pages source to GitHub Actions ← *most important*
**Settings → Pages → Build and deployment → Source: GitHub Actions.**

If this currently says "Deploy from a branch," then two things are true right now: your test suite is *not* gating deploys, and `live-data.yml` can never publish, because `actions/deploy-pages` requires the Actions source. Nothing else in this guide works until this is changed.

### Step 2 — Get real station IDs
```
python3 scripts/discover_stations.py --limit 6          # look at the table
python3 scripts/discover_stations.py --limit 6 --write  # save docs/stations.json
```
It asks api.weather.gov which stations serve the scar centroid, keeps only those actually reporting `precipitationLastHour`, and records each one's distance. Nothing placeholder ever reaches the config. **Open one station's page by hand afterward** and confirm the number matches the weather outside — do this once, on a dry day.

Then confirm the fetchers produce sane output before trusting any schedule:
```
python3 scripts/fetch_rain.py --out -   | head -40
python3 scripts/fetch_alerts.py --out - | head -20
```

### Step 3 — First publish, by hand
Don't wait for the cron; prove the whole path works once:
```
python3 scripts/fetch_rain.py   --out site/data/rain_latest.json
python3 scripts/fetch_alerts.py --out site/data/alerts_latest.json
make verify
git add site/data && git commit -m "live: first snapshots" && git push
```
Within a minute the bottom panel should show gauge rows and either active NWS products or the honest "none listed" line, each stamped with its age.

### Step 4 — Turn on the schedule
`.github/workflows/live-data.yml` runs every 15 minutes during Oct–Apr. It's already committed; enable it under the Actions tab (`Run workflow` once to confirm it publishes). Ageing out is the tested default, so a failed run is safe: the site marks the snapshot STALE, then EXPIRED, and hides values rather than showing stale confidence.

### Step 5 — Verify from outside
```
make deploy-check URL=https://itremedypoint-hub.github.io/arroyo/
```
Checks the live page, both snapshot files and their ages, the threshold dataset's DOI and units, headers, and that the rails and AI attribution are present. Run it after every push.

### Optional — better rain data
The NWS route is keyless and honest but hourly and off-scar. A free Synoptic token reaches the LA County ALERT gauges with true 15-minute intervals — the actual instruments this hazard is monitored with:
1. Get a token at synopticdata.com.
2. `SYNOPTIC_TOKEN=… python3 scripts/discover_stations.py --synoptic --write`
3. Add `SYNOPTIC_TOKEN` as a repo secret (Settings → Secrets → Actions). The workflow already passes it; the fetcher auto-prefers Synoptic when it's set. The token never reaches the browser.

### Optional — real headers
GitHub Pages ignores `_headers`. To get `frame-ancestors`, `nosniff`, and a referrer policy, point Cloudflare Pages at the same repo with build output `site/` — the file already there does the rest. Worth doing before you publicize the URL, so nobody can iframe the hazard page and present it as their own.

---

## Part 4 — Before the wet season (by early November)

1. **Load the real USGS thresholds.** This is the one that turns off the TRAINING banner and makes the site genuinely useful — full procedure in `LAUNCH_README.md` → "Going live with real numbers." Everything else here is plumbing; this is the payload.
2. `make links` — verify every official destination still resolves.
3. `make deploy-check URL=…` — confirm both feeds are fresh, not merely present.
4. Freeze content changes once storms start. Fix typos on sunny days.
