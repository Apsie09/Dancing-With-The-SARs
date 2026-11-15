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
| no Coryell case | Coryell added as a normal fourth Sentinel-1 case: 72 summer repairs, 55 dates, same model and validation |
| no cross-site comparison | compare view separates model skill from label ranking across all four sites |
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
| Coryell, Texas | Sentinel-1/2 + Landsat, weather-normalised | 72 summer repairs | label AUC 0.548 | weak positive; mean corridor p 0.024, p95 0.24 |

### Coryell details

- **Scope:** a fixed 10 × 10 km rural AOI in UTM 14N (EPSG:32614), 184 clipped pipe segments,
  72 summer repairs (June–September 2025–2026), 7 pressure zones in the source district.
- **Sensors:** Sentinel-1 RTC ascending relative orbit 34, **55 dates** (2025-01-07 to 2026-11-05);
  76 Sentinel-2 dates; 47 Landsat LST dates; ERA5 weather.
- **Pipeline:** exactly the same modules and parameters as the other cases, selected by
  `TERRAGUARD_CASE=case_studies/coryell/case.json`.
- **Model skill:** VV MAE 1.32 dB / R² **0.426**; NDMI MAE 0.113 / R² **0.505**.
- **Label ranking:** AUC **0.548**, median percentile 59.1 on 72 repairs.
- **Corridor test:** mean placebo p **0.024**, p95 placebo p **0.244**. The mean is nominally
  small; the p95 test is not, so this is not a validated detector.
- **No NISAR:** the case has no calibrated NISAR imagery. It is a Sentinel-1/2 case like
  Aguascalientes and Calgary.

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
│       └── coryell/         meta.json, network, events, rasters, stats
├── scripts/
│   ├── fetch_coryell.py          public ArcGIS vectors (no login)
│   ├── build_platform_data.py    one exporter for all sites
│   └── check_platform.py         contract + privacy + metric checks
├── case_studies/coryell/         case.json, clipped network, labels, pipeline outputs
├── data/coryell/                 data note; raw vectors fetched and git-ignored
├── docs/PLATFORM.md              this document
└── run_dashboard.sh              serves the bundle and prints /app/
```

### Data contract

Every site directory contains:

| File | Required | Contents |
|---|---|---|
| `meta.json` | yes | id, name, centre, zoom, kind (`raster`/`vector`), layer list, timelines, sources, caveats |
| `network.geojson` | yes | mapped pipes / water main |
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

# 1. Coryell source vectors and case subset (public ArcGIS, no login)
python scripts/fetch_coryell.py
python case_studies/prepare_coryell.py

# 2. Run the same pipeline as the other cases
CASE=case_studies/coryell/case.json
TERRAGUARD_CASE=$CASE python -m pipeline.acquire --workers 16
TERRAGUARD_CASE=$CASE python -m pipeline.model
TERRAGUARD_CASE=$CASE python -m pipeline.make_map

# 3. Export every case to the app contract
python scripts/build_platform_data.py
python scripts/check_platform.py

# 4. Serve
./run_dashboard.sh          # http://127.0.0.1:8766/app/
```

`build_platform_data.py` is deterministic. It:

- reads the Bulgaria and case outputs already in the bundle;
- renders the three evidence rasters to bounded RGBA PNGs (no browser-side GeoTIFF decoding);
- stretches only the leak raster for display to the site median–p99 so the top evidence is visible;
  the absolute 0–100 score remains in the evidence panel, hotspots and validation files;
- simplifies networks in their local UTM CRS before reprojecting to WGS84;
- strips personal fields from Coryell labels (Creator, Editor, notes, globalid, raw loss text);
- writes one registry and one meta file per site from each case's `validation.json`.

Raw satellite stacks remain excluded and regenerable with the original pipeline tasks.

---

## 5. What was borrowed, and what is new

The platform is a continuation, not a replacement:

- **From the NISAR/Kitchener work:** the discipline of matched controls, temporal holdouts,
  quality masks and per-segment aggregation motivated the evidence vocabulary. The Kitchener
  processed data was not available in this bundle, so the app does not reproduce its risk model.
- **From the Coryell NISAR viewer:** the MapLibre interaction patterns, time filtering and
  before/after idea. NISAR chips are not bundled because they need an Earthdata login.
- **From the original TerraGuard pipeline:** the weather-normalised expected-condition method,
  per-land-cover robust residuals, persistence, thermal cooling and corridor placebo tests.
- **New here:** the unified contract, the four-site app, the evidence panel, the comparison view,
  the fourth Coryell case run through the same pipeline, and the reproducibility checks.

---

## 6. Verification performed

- Browser: overview, Bulgaria, Aguascalientes, Calgary, Coryell, compare and method were rendered
  with zero console errors during development.
- Overlay switching (leak / moisture / persistence) checked on Bulgaria; the same mechanism is used
  on every raster site.
- Time filtering and the NISAR-era filter checked on Coryell.
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
- **Label AUC ≈ 0.52–0.55** in the three Sentinel-1 labelled cases; confidence intervals include 0.5.
- **Coryell is a weak positive.** Mean corridor p is 0.024, but p95 is 0.24 and label AUC is 0.548;
  it does not validate a surface detector.
- **Coryell licence:** the ArcGIS layers have no stated open licence. The raw vectors are
  git-ignored and fetched by script; the privacy-trimmed app export is bundled for the hackathon
  demonstration only. Ask the district before any further redistribution.
- **NISAR:** no calibrated NISAR imagery is in this bundle. Bulgaria has a fourth, display-only
  NISAR HH browse overlay (8-bit, kilometre-scale geolocation uncertainty); the app never uses it
  quantitatively.
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
