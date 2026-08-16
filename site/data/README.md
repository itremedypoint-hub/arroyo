# The live-data slot

Place the real USGS-derived dataset here as `basins_eaton.json` and the app
leaves training mode automatically (the page validates it at load; an invalid
or training-labeled file is ignored and the TRAINING banner stays up).

Build it with `scripts/build_basins.py` — full procedure in LAUNCH_README.md.
Never hand-edit numbers into this file; the build script exists so every
value traces to a named field in the USGS release.

Two more files land here at runtime, written only by CI (`live-data.yml`):
`rain_latest.json` (observed gauge rates; Synoptic 15-min intervals when the
token secret is set, keyless NWS hourly otherwise) and `alerts_latest.json`
(active NWS flood/debris/evacuation products for LA County). The page ages
both by their `fetched_at` stamp: fresh ≤45 min, stale ≤6 h (values shown,
actions disabled), expired beyond that (values hidden — never an all-clear).
Absent files simply leave the panel in its labeled "feeds off" state.
