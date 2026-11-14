# TerraGuard — `chris-results` bundle

This folder is a **self-contained, shareable copy** of the TerraGuard work: code, docs, the three
case maps, validation metrics, small data layers and the tabbed dashboard. It is meant to be opened
by someone who has never seen the repository.

**Start here:** run the dashboard, then read the results and caveats.

```bash
cd chris-results
./run_dashboard.sh
# open http://127.0.0.1:8766/terraguard_dashboard.html
```

No Python environment is needed just to view the maps — the HTML files are self-contained
(base64 raster overlays). The dashboard and maps load Leaflet/Esri tiles from the internet; the
data overlays themselves are embedded.

---

## 1. What TerraGuard is

A weather-normalised, multi-sensor **screening** pipeline for buried water networks:

```
Sentinel-1 RTC + Sentinel-2 NDMI + Landsat LST + ERA5 weather + soil / land cover / DEM
        ↓
LightGBM expected-condition model (what should this 20 m pixel look like?)
        ↓
residual z-scores → dry-season persistence + thermal cooling
        ↓
pipeline-network proximity weighting
        ↓
leak-likelihood map + hotspot cards + validation
```

It does **not** claim metre-level leak localisation or confirmed detection. It ranks places where
the ground stays wet (and cool) when rainfall, soil, vegetation and season say it should be dry.

The full research review is in [`research/Pipeline-Leak-Detection.md`](research/Pipeline-Leak-Detection.md).
Implementation details and metrics are in [`docs/RESULTS.md`](docs/RESULTS.md).
The challenge-facing design is in [`docs/SOLUTION.md`](docs/SOLUTION.md).

---

## 2. The three cases

| Tab | Case | Labels | S1 dates | VV R² | NDMI R² | Label AUC | Corridor p | Verdict |
|---|---|---|---:|---:|---:|---:|---:|---|
| Bulgaria | Elin Pelin rural water main | — | 194 | 0.611 | 0.471 | — | 0.89 | unlabelled demo; negative corridor test |
| Aguascalientes | 5×5 km urban utility network | 50 repairs | 28 | 0.436 | 0.294 | **0.526** | 1.00 | weak positive, not significant |
| Calgary | 10×10 km trunk water network | 48 breaks | 50 | 0.650 | 0.249 | **0.524** | 0.95 | weak positive, not significant |

**The honest headline:** the expected-condition models are skilful (VV R² 0.44–0.65, NDMI R²
0.25–0.47), but the final leak score is only weakly associated with historical repair/break
locations (AUC ≈ 0.52–0.53, close to random). The pipeline is a triage tool, not a detector.
This is consistent with the published literature and with the unlabelled Bulgarian result.

### Case details

**Bulgaria (demo)**
- Elin Pelin, Sofia Province; 5.5 × 6.3 km farmland; 3.3 km buried water main (OSM `1106343159`).
- Sentinel-1 RTC orbit 7 descending, 434 dates 2018–2026; 194 dates used 2022–2026.
- No confirmed leak. The corridor enrichment test is **not significant** (p = 0.89 at the 95th
  percentile vs 200 translated placebo corridors).
- Map: [`outputs/terraguard_map.html`](outputs/terraguard_map.html)
- Static: [`outputs/terraguard_map.png`](outputs/terraguard_map.png)

**Aguascalientes, Mexico**
- 5 × 5 km AOI, EPSG:32613; utility water network `Tuberias.shp` (8,134 segments, 575 km).
- 50 actual repair records (`SE REPARA FTC, GENERA BA`) from the cleaned 2022 dry-season labels.
- Sentinel-1 RTC ascending 151, 28 dates in 2022.
- VV MAE 2.10 dB / R² 0.436; NDMI MAE 0.076 / R² 0.294.
- Label AUC **0.526**, median percentile 56.2; corridor p 1.00 (not significant).
- Map: [`case_studies/aguascalientes/outputs/terraguard_map.html`](case_studies/aguascalientes/outputs/terraguard_map.html)

**Calgary, Canada**
- 10 × 10 km AOI, EPSG:32611; public water main network (5,879 clipped segments).
- 48 water main breaks, 2025–2026.
- Sentinel-1 RTC ascending 122, 50 dates (2025–2026; the RTC archive over this AOI starts April 2025).
- VV MAE 1.85 dB / R² 0.650; NDMI MAE 0.137 / R² 0.249.
- Label AUC **0.524**, median percentile 51.7; corridor p 0.90 mean / 0.95 p95 (not significant).
- Map: [`case_studies/calgary/outputs/terraguard_map.html`](case_studies/calgary/outputs/terraguard_map.html)

Full case notes: [`case_studies/README.md`](case_studies/README.md).

---

## 3. What is in this folder

| Path | Contents |
|---|---|
| `terraguard_dashboard.html` | Tabbed dashboard: Overview / Bulgaria / Aguascalientes / Calgary / Method |
| `run_dashboard.sh` | Local HTTP server helper |
| `pipeline/` | Acquisition, feature engineering, model, map builder |
| `scripts/` | OSM pipeline extraction and NISAR browse/HDF5 extraction |
| `docs/` | `SOLUTION.md` (challenge design) and `RESULTS.md` (implementation + metrics) |
| `research/` | Literature review, data audit, static-data audit, NISAR audit |
| `data/` | Small static/vector/met layers and NISAR browse; **no large raw stacks** |
| `outputs/` | Bulgaria map, GeoTIFFs, hotspots, validation, scores, dashboard screenshots |
| `case_studies/` | Two labelled cases: `case.json`, network, labels, small layers, outputs |
| `pixi.toml` / `pixi.lock` | Pinned conda-forge environment |
| `README.md` | Original project README |
| `LICENSE` | MIT |
| `explanation.md` | This guide |

### Deliberately excluded (too large, re-downloadable)

- `data/raw/s1_stack.npz`, `s2_stack.npz`, `lst_stack.npz` (hundreds of MB).
- `case_studies/*/data/raw/` (S1/S2/LST stacks and raw network caches) and `data/interim/`.
- `.pixi/`, `__pycache__/`.

Everything else needed to inspect the results and rerun the pipeline is here.

---

## 4. Quick start

### View the dashboard (no install)

```bash
cd chris-results
./run_dashboard.sh          # or: python3 -m http.server 8766 --directory .
# open http://127.0.0.1:8766/terraguard_dashboard.html
```

You can also open `terraguard_dashboard.html` directly from disk; the case maps are relative
links. A local server is recommended because browsers restrict local iframes.

### Install the environment (for reruns)

```bash
# Pixi: https://pixi.sh
curl -fsSL https://pixi.sh/install.sh | bash
export PATH="$HOME/.pixi/bin:$PATH"
cd chris-results
pixi install
```

### Run the Bulgaria pipeline

```bash
pixi run pipelines        # OSM vectors (uses the bundled cache if present)
pixi run acquire          # Sentinel-1/2, Landsat, ERA5, static layers
pixi run model            # residuals, validation, hotspots, GeoTIFFs
pixi run map              # interactive map + static figures
```

`acquire` re-downloads the raw stacks into `data/raw/` (a few hundred MB). The bundled outputs are
already generated; you do not need to rerun to view them.

### Run a labelled case

```bash
CASE=case_studies/aguascalientes/case.json

TERRAGUARD_CASE=$CASE pixi run python -m pipeline.acquire --workers 16
TERRAGUARD_CASE=$CASE pixi run python -m pipeline.model
TERRAGUARD_CASE=$CASE pixi run python -m pipeline.make_map
```

Replace with `case_studies/calgary/case.json` for Calgary. The prepared networks, labels, small
static layers and already-generated outputs are included; only the raw satellite stacks are
missing and will be re-downloaded by `acquire`.

---

## 5. Data sources and access

| Layer | Source | Auth |
|---|---|---|
| Sentinel-1 RTC | Planetary Computer `sentinel-1-rtc` | none (SAS signing automatic) |
| Sentinel-2 L2A | AWS Earth Search `sentinel-2-l2a` | none |
| Landsat C2 L2 | Planetary Computer `landsat-c2-l2` | none |
| ERA5 weather | Open-Meteo archive | none |
| WorldCover / Copernicus DEM | ESA / AWS public buckets | none |
| OSM pipelines | Overpass API | none (user agent) |
| NISAR GCOV browse | ASF public browse | none |
| NISAR GCOV HDF5 | ASF / Earthdata | **Earthdata login**; extraction code in `scripts/nisar_extract.py --hdf5` |

The NISAR HDF5 path is implemented and validated on ASF's public sample, but the Bulgaria HDF5
downloads were blocked without credentials. The bundled NISAR layers are public 8-bit browse
imagery, display-only, not calibrated gamma0.

---

## 6. How the pipeline works

1. **Grid.** One 20 m UTM grid per case (EPSG:32634 Bulgaria, 32613 Aguascalientes, 32611 Calgary).
2. **Ingest.** S1 RTC per-item CRS handling and adjacent-tile mosaicking; S2 BOA offset, NDMI/NDVI
   and SCL cloud mask; Landsat `ST_B10` to °C and QA mask; ERA5 lags; static layers.
3. **Expected condition.** LightGBM (`regression_l1`) predicts VV backscatter and NDMI from weather,
   soil, land cover, vegetation, season and SAR texture. Trained on ordinary dates, no leak labels.
4. **Residual.** Observed − expected; robust z-scores; dry-season mean, persistence and thermal
   cooling. Residuals are not centred per pixel, so a persistent anomaly survives.
5. **Fusion.** `0.55·moisture + 0.25·persistence + 0.20·thermal`, smoothed to the 60 m plume scale,
   weighted by distance to the mapped network. Dense networks use a softer proximity prior.
6. **Validation.** Temporal holdout (2026 for Bulgaria, 2023 for Aguascalientes, 2026 for Calgary),
   40–200 translated-network placebo corridors, and label AUC where ground truth exists.

---

## 7. Caveats for anyone using this

- **No confirmed leak in Bulgaria.** The map is a screening priority, not a detection.
- **Label AUC ≈ 0.52–0.53** in both labelled cities. Do not present this as a leak detector.
- Repair records are not persistent leaks; the score is a multi-month residual, so the temporal
  match is weak. Event-window residuals around known leaks are the next step.
- 20 m pixels and 100 m native thermal cannot localise a metre-scale pipe failure.
- Urban land cover, irrigation, snow, roads and construction produce the same surface signatures.
- Calgary's S1 RTC record starts April 2025; the Bulgarian record starts in 2018 but the weather
  covariates start in 2022.
- The case maps use the same pipeline but a slightly smaller feature set (no SoilGrids/terrain/roads
  in the case folders).
- The dashboard and maps load Leaflet/Esri tiles from the internet; raster overlays are embedded.

---

## 8. Results files

| File | Meaning |
|---|---|
| `outputs/validation.json` | Bulgaria S1 counts, model metrics, corridor placebo test |
| `outputs/model_metrics.json` | VV/NDMI metrics |
| `outputs/hotspots.csv` / `.json` | Ranked candidates with evidence |
| `outputs/*.tif` | Soil-moisture anomaly, leak likelihood, persistence, thermal, confidence |
| `case_studies/*/outputs/validation.json` | Case model metrics + label AUC + placebo test |
| `case_studies/*/outputs/hotspots.csv` | Case hotspots |
| `case_studies/*/outputs/terraguard_map.html` | Case interactive map |

---

## 9. Credits and licence

- Code and text: MIT (`LICENSE`).
- Sentinel data: Copernicus / ESA; Landsat: USGS/NASA; NISAR: NASA/ISRO/ASF; SoilGrids: ISRIC;
  WorldCover: ESA; weather: Open-Meteo/ERA5; OSM: OpenStreetMap contributors (ODbL).
- Aguascalientes case data: [`erickfama/rs_leaks`](https://github.com/erickfama/rs_leaks).
- Calgary case data: City of Calgary Open Data (`w6h9-w33i`, `dpcu-jr23`).
- Research review and implementation: TerraGuard / “Dancing with the SARs”.

Prepared as a portable hand-off bundle. The main repository remains at
`Apsie09/Dancing-With-The-SARs`; this folder is the self-contained copy.
