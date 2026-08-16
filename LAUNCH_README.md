# Arroyo v2.0-community — launch guide

A trilingual (EN/ES/简体中文) literacy tool for post-fire debris-flow rainfall
thresholds on the Eaton burn scar. Static, single file, no backend, no user
data. **This build's interface and engine were generated with AI assistance
(Claude, Anthropic) at the maintainer's direction, August 2026** — that
attribution is stamped in the page footer and this repo, and stays. Engine
correctness is defined by an independent oracle (`verify/golden_vectors.json`),
not by the engine's own opinion of itself.

**Safety rails (also maintenance policy — never remove):** Arroyo never
issues or clears a warning; nothing on the page ever says "you are safe."
Tiers are computed from rainfall numbers against published thresholds only.
Every tier links out to Alert LA County, NWS Los Angeles/Oxnard, and Genasys
Protect. Ships in labeled TRAINING mode until a real USGS dataset is loaded.

## Repo map
```
site/index.html          the entire app (CSP meta, engine, i18n, admin console)
site/data/               live-data slot (README inside; empty until ingestion)
site/_headers            production headers for Cloudflare Pages
scripts/build_basins.py  USGS GeoJSON → basins_eaton.json (the only threshold path)
scripts/fetch_rain.py    CI: gauge snapshot (Synoptic 15-min / NWS hourly fallback)
scripts/fetch_alerts.py  CI: active NWS flood/debris products, LA County filter
scripts/ops_*.py         validate / freshness gate / link check
verify/                  golden_vectors.json (oracle) + JSON schema
tests/                   341+29 oracle checks · 329 DOM · 15 ingestion · 14 fetcher · 63 structural
.github/workflows/       verify-gated GitHub Pages deploy
Makefile                 make verify | serve | freshness | links
```

## Run it
Open `site/index.html` in a browser — it works from a plain file. For a
local server: `make serve` → http://localhost:8000. Requirements for
development: Node ≥ 20 (`npm install jsdom` once) and Python 3.10+.

## Verify it (do this after every edit)
```
make verify
```
Green means: the shipped engine block matches all 341 oracle values
(M1 coefficients, the 1.302648 year-2 factor, curve points, unit invariance,
all 90 tier rows, the low-threshold guard pathology, SHA-256 against Python
hashlib); the page drives correctly in a real DOM (272 checks — basin
switching, year toggle, published-P75 vs derived triggers, escalation-only
session display, **simulator sandbox isolation**, the admin gate, full
three-language string parity); the ingestion script scales units, stamps
traceability, and refuses accumulation-looking values; and the HTML is
structurally sound with no inline handlers and the CSP present. Visitors get
a 12-value canary self-check on every page load (Status section).

## Live feeds (CI snapshots — the only live-data architecture allowed here)
The browser never calls a third-party API and never sees a token: a scheduled
workflow (`.github/workflows/live-data.yml`, every 15 min Oct–Apr) runs the
two fetchers server-side and redeploys the site with fresh same-origin JSON.
The page stamps every snapshot with its age and enforces the policy the
oracle pins: **fresh ≤ 45 min** (full function), **stale ≤ 6 h** (values
shown, "Read this rate" disabled), **expired** beyond that (values hidden,
explicit "not an all-clear"). A dead feed therefore degrades the site to
honesty, not to silence or stale confidence — that failure mode is the tested
default, so leaving the workflow disabled is always safe.

Setup, once:
1. `cp docs/stations.example.json docs/stations.json` and put REAL gauge ids
   in it — verify each one by hand the first time. With no Synoptic token the
   fetcher uses keyless NWS hourly observations, which the UI labels
   "1-hour rate — smooths bursts; treat as a floor" (that honesty ships in
   three languages; don't remove it).
2. Optional but better: add a `SYNOPTIC_TOKEN` repo secret for true 15-minute
   interval rates from the county ALERT network via Synoptic. The token lives
   only in Actions.
3. Enable the workflow. First run: `python3 scripts/fetch_rain.py --out -`
   locally and eyeball the numbers against the gauge's own page before
   trusting the schedule.

Separation rule, stated once and enforced by design: observed rain and
official alerts are **display-only**. Tiers come from the reader, where the
person presses the rate against a labeled threshold. Nothing in the live
panel is colored, tiered, or auto-applied.

## The admin story, honestly
A static site has no server, so there is no server-side auth and nothing
secret to protect — the **real control plane is this repository** (branch
protection + the verify-gated deploy workflow). What the in-page "QA console"
provides is maintainer tooling behind a client-side SHA-256 passphrase gate
(5 tries, 30 s lockout): the engine self-test, a dataset inspector, a
session-only candidate-dataset preview (paste JSON → validated → previewed,
never saved), an exporter, and diagnostics. The page says exactly this to
anyone who opens the panel. Treat the passphrase as a courtesy lock, not a
vault.

**Default passphrase:** `poppy-ink-2026` — change it before deploying:
```
python3 -c "import hashlib;print(hashlib.sha256(b'YOUR-NEW-PHRASE').hexdigest())"
```
Paste the result into `ADMIN_PASS_HASH` in `site/index.html`, run
`make verify`, commit.

## Going live with real numbers (the only way the banner comes down)
The app refuses to present unlabeled numbers: it ships with synthetic
TRAINING data (clearly bannered) and leaves that mode only when a valid,
live-labeled `site/data/basins_eaton.json` exists. Build one like this:

1. **Check for the newest assessment.** ScienceBase, Eaton Fire — v1.0 is
   DOI `10.5066/P14EWYME` (King et al., 2025). If a v2 exists, use it and
   note the DOI.
2. **Export the basin layer to GeoJSON** from the release zip:
   `ogr2ogr -f GeoJSON basins.geojson <file.gdb or .shp> <layer>`
3. **Introspect the real field names** (they vary by release):
   `python3 scripts/build_basins.py --geojson basins.geojson --list-fields`
4. **Write `mapping.json`** pointing Arroyo's keys at those fields (example
   in the script's docstring). If the release has no community names,
   maintain `communities.json` by hand and pass `--communities-json`.
5. **Build.** If the threshold column is inches/hour, add `--units inh`.
   ```
   python3 scripts/build_basins.py --geojson basins.geojson \
     --mapping mapping.json --dataset-doi 10.5066/P14EWYME \
     --dataset-version "Eaton 2025-01-08 v1.0" \
     --source-url "https://doi.org/10.5066/P14EWYME" \
     --out site/data/basins_eaton.json
   ```
   The script hard-refuses values that look like 15-minute accumulations
   instead of intensities (the factor-of-4 landmine) — if it refuses,
   re-read the spec field description; don't override.
6. **Gate and ship.**
   ```
   python3 scripts/ops_validate.py site/data/basins_eaton.json
   python3 scripts/ops_freshness.py site/data/basins_eaton.json --require-live
   make verify && git commit -am "data: Eaton v1.0" && git push
   ```
   The TRAINING banner disappears on its own; provenance badges switch to
   the USGS version + DOI. Total time once you've done it: ~10 minutes.

Verify a few displayed numbers against the USGS interactive map by hand
before announcing the site. Spot-checking is a rail, not an insult.

## Deploy
**GitHub Pages (included):** push to `main`; `.github/workflows/deploy.yml`
runs the full verify suite and the freshness gate before anything ships.
Enable Pages → "GitHub Actions" in repo settings.
**Cloudflare Pages:** point it at the repo, build output `site/`;
`site/_headers` applies the CSP (including `frame-ancestors`, which a meta
tag cannot carry), nosniff, no-referrer, and a no-cache policy so threshold
updates propagate immediately.

Single-file tradeoff, stated plainly: inline script/style means the CSP
allows `'unsafe-inline'`. That is an acceptable posture for a no-input,
no-secrets static page whose DOM writes are all `textContent`. If you later
split `index.html` into `app.js` + `app.css`, tighten to
`script-src 'self'; style-src 'self'` and drop `'unsafe-inline'`.

## Operating cadence (wet season)
- **Monthly (Oct–Apr):** `make links` — a literacy page with a dead official
  link is worse than none. `python3 scripts/ops_freshness.py … --max-days 120`.
- **Live feeds:** enable `live-data.yml` in October, disable it in May; widen the cron to `*/30` if CI minutes matter. If a gauge goes bad, remove it from `docs/stations.json` — the sanity clamp already drops absurd rates automatically.
- **Before each forecast storm:** nothing. The site is deliberately static
  during events; do not push content changes while a Flash Flood Watch or
  Warning is active for the scar. Fix typos on sunny days.
- **After a USGS re-assessment:** repeat the ingestion procedure; the DOI and
  version badges tell readers which release they're seeing.
- **Never add:** push notifications, an "all clear" state, crowd reports as
  tier inputs, analytics, or accounts. If a future maintainer wants any of
  these, they are building a different tool and should rename it.
