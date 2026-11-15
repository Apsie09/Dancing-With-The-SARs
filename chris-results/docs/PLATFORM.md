# TerraGuard Evidence Explorer — platform notes

This document describes the platform added inside `chris-results/` on the `test` branch:
the single data contract, the MapLibre application, the Coryell case, and the checks that
keep the bundle reproducible.

**Open it:** `./run_dashboard.sh` then <http://127.0.0.1:8766/app/>.

---

## 1. What changed in this branch

The previous bundle had one tabbed dashboard and a separate Leaflet map per case. The new
platform replaces that as the main entry point:

| Before | After |
|---|---|
| `terraguard_dashboard.html` with case tabs | `app/` — one MapLibre explorer with four sites, compare and method views |
| each case map built by `pipeline/make_map.py` | one export contract (`app/data/`) consumed by one app |
| no Coryell case | Coryell added: 1,690 repairs, 918 pipes, seven-year repair history |
| no cross-site risk comparison | compare view separates model skill, label ranking and repair-history risk |
| no evidence vocabulary | observed / modelled / inferred labels on every panel |
| hardcoded per-case HTML | site registry + `meta.json`; a new site is a data task |

The old dashboard and per-case Leaflet maps are kept as a **legacy appendix**; they still work.

---

## 2. Results in the platform

| Site | Evidence | Labels | Final test | Honest verdict |
|---|---|---|---:|---|
| Elin Pelin, Bulgaria | Sentinel-1/2 + Landsat, weather-normalised | none | corridor p95 = 0.89 | method demo; no confirmed leak |
| Aguascalientes, Mexico | Sentinel-1, weather-normalised | 50 repairs | label AUC 0.526 | weak, not significant |
| Calgary, Canada | Sentinel-1, weather-normalised | 48 breaks | label AUC 0.524 | weak, not significant |
| Coryell, Texas | repair history + pipe network | 1,690 repairs | temporal risk AUC 0.787 | useful ranking of infrastructure risk, not radar detection |

### Coryell details

- **Scope:** 1,690 usable point repairs (2 records dropped: one outlier near Galveston and one
  without a date), 2019-09-30 to 2026-11-11; 918 pipe features; 7 pressure zones.
- **Model:** `HistGradientBoostingClassifier`, features only from before each cutoff:
  length, diameter, install year (mostly missing), PVC indicator, prior repairs, prior repairs
  in the last two years, months since last repair, repairs within 500 m of the pipe midpoint.
- **Train:** features before 2023-01-01 → target any repair in 2023–2024.
- **Test:** features before 2025-01-01 → target any repair in 2025-01-01..2026-11-11.
- **Results:** AUC **0.787**, average precision **0.511**, top-10 % capture **28.1 %** of repairs,
  base rate **22.1 %** of pipes, transparent recurrence baseline AUC **0.719**.
- **Map score:** model trained on 2023–24, applied to pre-2025 features; displayed as a percentile.
- **Why it is different:** this is *infrastructure risk*, not a radar observation. The target is
  "a repair was recorded on this pipe in the next two years", not "a leak is visible now".

---

## 3. Architecture

```text
chris-results/
├── app/
│   ├── index.html          MapLibre shell
│   ├── app.js              routing, maps, layers, evidence, compare/method views
│   ├── style.css           dark UI, responsive layout
│   └── data/
│       ├── sites.json      site registry + headline metrics + caveats
│       ├── bulgaria/       meta.json, network, hotspots, overlay_*.png, stats
│       ├── aguascalientes/  same contract
│       ├── calgary/         same contract
│       └── coryell/         meta.json, network, events, zones, stats, risk.csv
├── scripts/
│   ├── fetch_coryell.py          public ArcGIS vectors (no login)
│   ├── build_platform_data.py    one exporter for all sites
│   └── check_platform.py         contract + privacy + metric checks
├── data/coryell/                 data note; raw vectors fetched and git-ignored
├── docs/PLATFORM.md              this document
└── run_dashboard.sh              serves the bundle and prints /app/
```

### Data contract

Every site directory contains:

| File | Required | Contents |
|---|---|---|
| `meta.json` | yes | id, name, centre, zoom, kind (`raster`/`vector`), layer list, timelines, sources, caveats |
| `network.geojson` | vector sites | pipes; Coryell adds size, material, risk, repair history |
| `events.geojson` | labelled sites | repairs/breaks; privacy-safe fields only |
| `hotspots.geojson` | raster sites | ranked candidates with score and evidence components |
| `zones.geojson` | optional | pressure zones |
| `overlay_<kind>.png` | raster sites | leak / moisture / persistence, RGBA, with bounds in `meta.json` |
| `stats.json` | yes | counts, by-year series, metrics, validation details |

`sites.json` is the registry: the app renders the overview cards and header from it, then lazily
loads only the selected site.

### Adding a site

1. Create `app/data/<id>/meta.json` with the fields above and place the layers next to it.
2. Add the site object to `app/data/sites.json` (or generate it in the exporter).
3. Rebuild and run `python scripts/check_platform.py`.
4. No app code change is required for a raster or vector site that follows the contract.

---

## 4. The export process

```bash
cd chris-results

# 1. Coryell vectors (public ArcGIS, no login; no stated licence)
python scripts/fetch_coryell.py

# 2. Render rasters + normalise vectors + compute Coryell validation
python scripts/build_platform_data.py

# 3. Contract, privacy and metric checks
python scripts/check_platform.py

# 4. Serve
./run_dashboard.sh          # http://127.0.0.1:8766/app/
```

`build_platform_data.py` is deterministic. It:

- reads the Bulgaria and case outputs already in the bundle;
- renders the three evidence rasters to bounded RGBA PNGs (no browser-side GeoTIFF decoding);
- simplifies networks in their local UTM CRS before reprojecting to WGS84;
- strips personal fields from Coryell events (Creator, Editor, notes, globalid, raw loss text);
- computes the Coryell temporal validation and writes `risk.csv`;
- writes one registry and one meta file per site.

Raw satellite stacks remain excluded and regenerable with the original pipeline tasks.

---

## 5. What was borrowed, and what is new

The platform is a continuation, not a replacement:

- **From the NISAR/Kitchener work:** the discipline of matched controls, temporal holdouts,
  quality masks and per-segment aggregation motivated the Coryell temporal test and the
  evidence vocabulary. The Kitchener processed data was not available in this bundle, so the
  app does not claim to reproduce its risk model.
- **From the Coryell NISAR viewer:** the MapLibre interaction patterns, time filtering and
  before/after idea. NISAR chips are not bundled because they need an Earthdata login.
- **From the original TerraGuard pipeline:** the weather-normalised expected-condition method,
  per-land-cover robust residuals, persistence, thermal cooling and corridor placebo tests.
- **New here:** the unified contract, the four-site app, the evidence panel, the comparison view,
  Coryell's seven-year temporal validation, and the reproducibility checks.

---

## 6. Verification performed

- Browser: overview, Bulgaria, Aguascalientes, Calgary, Coryell, compare and method were rendered
  with zero console errors during development.
- Overlay switching (leak / moisture / persistence) checked on Bulgaria; the same mechanism is used
  on every raster site.
- Time filtering and the NISAR-era filter checked on Coryell (322 records on/after 2025-10-17).
- Evidence panel checked for repairs and pipe risk; point clicks take priority over the transparent
  pipe hit layer.
- Mobile layout rules are present (sidebar and evidence drawers); they were not separately captured
  in the saved screenshots.
- `scripts/check_platform.py` validates every referenced file, the site schema, metric ranges,
  PNG headers and the absence of personal fields; all checks pass.
- `app.js` parses without syntax errors under tree-sitter-javascript.

---

## 7. Limits

- **No confirmed leak anywhere.** Repairs are bursts; dates are report dates.
- **Label AUC ≈ 0.52–0.53** in the two Sentinel-1 labelled cases; confidence intervals include 0.5.
- **Coryell is not radar.** Its AUC is infrastructure risk; it does not validate a surface anomaly.
- **Coryell licence:** the ArcGIS layers have no stated open licence. The raw vectors are
  git-ignored and fetched by script; the privacy-trimmed app export is bundled for the hackathon
  demonstration only. Ask the district before any further redistribution.
- **NISAR:** no calibrated NISAR imagery is in this bundle. Bulgarian NISAR layers are 8-bit
  browse, display-only; the app does not use them quantitatively.
- **Basemaps:** Esri / OpenStreetMap tiles require internet; the data overlays are local.
- **Scale:** 20 m pixels and ~100 m thermal cannot localise a metre-scale failure.

---

## 8. Deployment

The app is static. Serve the bundle root (not `app/`) so that `../outputs`, `../case_studies`
and `./data` links resolve. For GitHub Pages, publish the `chris-results/` directory as the
site root and keep the relative layout. A small server is enough:

```bash
python3 -m http.server 8766 --directory .
# http://127.0.0.1:8766/app/
```
