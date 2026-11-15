# AquaGuard — implementation and results

**Study area:** Elin Pelin, Sofia Province, Bulgaria — a 5.5 × 6.3 km farmland AOI crossed by a 3.3 km buried water transmission main (OSM way `1106343159`).

**Question:** can a weather-normalised multi-sensor model find ground that stays wet (and cool) when rainfall, soil, vegetation and season say it should be dry — and does that anomaly cluster on the pipeline?

**Answer:** the pipeline works end-to-end and produces a defensible screening map. The model predicts SAR backscatter and optical moisture well. **The corridor-wide pipeline enrichment test is not statistically significant in this AOI** (p = 0.57 for the mean, p = 0.89 for the 95th percentile against 200 translated placebo corridors). The map therefore shows *inspection candidates*, not confirmed leaks. This is the honest result, and it is consistent with the research: a 20 m C-band pixel over a 3.3 km main with no known leak is a hard target.

---

## 1. What was built

```
OSM pipeline geometry ─┐
Sentinel-1 RTC  ───────┤
Sentinel-2 L2A  ───────┼──► common 20 m grid (EPSG:32634) ──► feature table
Landsat C2 LST  ───────┤                                      │
ERA5 weather    ───────┤                                      ▼
SoilGrids / DEM / LC ──┘                         LightGBM expected-condition model
                                                              │
                                          residual z-scores per pixel/date
                                                              │
                            dry-season mean + persistence + thermal cooling
                                                              │
                                     pipeline proximity weighting (Gaussian)
                                                              │
                              leak likelihood 0–100 + hotspot cards
                                                              │
                                    interactive Leaflet map + GeoTIFFs
```

The code is in `pipeline/`:

| Module | Role |
|---|---|
| `pipeline/config.py` | AOI, 20 m analysis grid, date range, STAC endpoints, paths |
| `pipeline/acquire.py` | S1 RTC mosaicking/resampling, S2 NDMI/NDVI, Landsat LST, ERA5 fallback, static fallback, pipeline distance rasters |
| `pipeline/features.py` | static-layer alignment, weather lags/anomalies, S1/S2/LST temporal features |
| `pipeline/model.py` | LightGBM models, residuals, dry-season aggregation, fusion, validation, hotspots, GeoTIFFs |
| `pipeline/make_map.py` | self-contained Leaflet HTML, static two-panel map, corridor profile |
| `scripts/extract_pipelines.py` | OSM pipeline extraction (Overpass) |
| `scripts/nisar_extract.py` | NISAR browse extraction now; HDF5 extraction path for authenticated runs |

`pixi.toml` pins the environment; `pixi.lock` records the exact solve.

---

## 2. Data actually used

### Sentinel-1 RTC (the quantitative backbone)

- Source: Planetary Computer STAC `sentinel-1-rtc`, 10 m gamma0, C-band.
- Orbit: **relative orbit 7, descending**. This was chosen after the audit showed that orbit 29 (which looks best by raw item count) only covers 100% of the AOI on 179 dates, with **no full-AOI dates in 2022–2024**. Orbit 7 covers 100% of the AOI on all 434 dates.
- Stack: **434 dates, 2018-01-06 → 2026-11-09**, median valid fraction 0.972.
- Used in the model: **194 dates from 2022-01-09 → 2026-11-09**, including **69 dry-season (June–September) scenes**.
- Read pattern: per-item CRS (some RTC tiles are EPSG:32635, not 32634), AOI transformed to the item CRS, adjacent tiles mosaicked per date, then reprojected to the 20 m grid.

### Sentinel-2 L2A

- Source: AWS Earth Search `sentinel-2-l2a`, public COGs.
- **195 cloud-screened dates**, 2018–2026.
- NDMI = `(B8A − B11) / (B8A + B11)`, NDVI = `(B8 − B4) / (B8 + B4)`.
- SCL classes 3, 8, 9, 10, 11 masked; scenes with >65% AOI cloud rejected; nearest date within ±10 days matched to each S1 acquisition.
- BOA offset applied (modern L2A: −0.1; older items may be 0.0).

### Landsat C2 L2 thermal

- Source: Planetary Computer `landsat-c2-l2` (Earth Search points at a requester-pays bucket, so PC was used).
- **75 dates** with cloud <40% and AOI cloud <65%.
- `ST_B10` → °C: `DN × 0.00341802 + 149.0 − 273.15`. No extra emissivity correction (ST_B10 already includes it).
- 100 m native thermal, resampled to 30 m by USGS and to 20 m here. Used as a **direct local anomaly** (cooler than the scene median), not as a calibrated physical temperature.

### Weather

- Open-Meteo ERA5 archive, **1,779 days, 2022-01-01 → 2026-11-14**, at 42.6362 N, 23.6283 E (548 m).
- Daily aggregates: precipitation, mean/min/max temperature, RH, radiation, ET₀, soil moisture (0–7, 7–28, 28–100 cm), VPD, wind.
- Engineered: 1/3/7/14/30/60-day precipitation sums, 3/7-day temperature, 7/30-day ET₀, 7-day VPD, consecutive dry days, 31-day soil-moisture anomaly, monthly precipitation/temperature anomaly, day-of-year sin/cos.

### Static layers

- ESA WorldCover 2021 v200, 10 m (tile N42E021 — the N42E023 URL in the original brief is a 404).
- Copernicus DEM GLO-30 + Horn slope.
- SoilGrids 250 m: sand, clay, silt, SOC, bulk density (0–5 cm), with 8.9% no-data filled from the nearest valid cell (mask preserved).
- OSM: 1,341 buildings, 478 road ways (157 km), water main and gas transmission line.

### NISAR

- ASF search returned 32+ GCOV scenes over the AOI from 2026-06 onward.
- **Full HDF5 download is blocked** without Earthdata authentication: `HEAD` returns a signed CloudFront URL, but `GET` redirects to OAuth and returns `HTTP Basic: Access denied`. The extraction path is implemented and validated on ASF's public 2008 sample (California, not Bulgaria), but the Bulgaria HDF5s were not downloaded.
- **What is used:** public ASF GCOV **browse imagery** for **2026-06-20** and **2026-10-06**, track 094 descending, frame 067. These are 8-bit, independently stretched, ~160 m browse pixels, georeferenced approximately (km-level). They are shown as L-band context and a relative change layer, **not** in the quantitative score.
- This limitation is stated in the map and in `research/nisar-audit.md`.

---

## 3. Model

### Target and features

Three expected-condition models were tested. The final quantitative score uses two:

| Target | Features | Test MAE | Test R² | Test n |
|---|---|---:|---:|---:|
| Sentinel-1 VV (dB) | static + weather + season + NDVI + SAR texture | **1.77 dB** | **0.611** | 867,272 |
| Sentinel-2 NDMI | static + weather + season + NDVI + SAR texture | **0.178** | **0.471** | 734,421 |

A Landsat LST model was also trained in an earlier iteration (MAE 8.8 °C, R² −0.41) and **discarded**. The negative R² showed that a weather-only regression could not explain Landsat LST at this scale. The thermal layer now uses a direct per-scene anomaly: `− (LST − scene median)`, i.e. local evaporative cooling relative to the surrounding land, which is the physically relevant quantity and avoids a bad model.

- Algorithm: LightGBM, `objective="regression_l1"` (MAE), 450 trees, learning rate 0.045, 63 leaves, subsample 0.8, column sample 0.85.
- Table: 3.31 M rows × 48 columns; 17,054 sampled pixels (3,054 corridor + 14,000 background); 1.88 M training rows for VV.
- Split: train < 2025-07-01; validation 2025-07-01 → 2025-12-31; **test = 2026**.
- Residual z-scores use the training residual median/MAD, not per-pixel centering, so a persistent wet anomaly is not removed.

### Fusion

For every pixel and dry-season date:

```
z_moist  = mean(z_VV, z_NDMI)          # positive = wetter than expected
z_thermal = -z_LST_local               # positive = cooler than the scene
persistence = fraction of dry dates with z_moist > 0.5
moist_dry = mean(z_moist) over June–September, 2022–2026
thermal   = mean(z_thermal) over the same dates
```

The evidence layers are smoothed to a 3×3 (60 m) scale, the scale of a shallow leakage plume:

```
leak_raw  = 0.55·clip(moist_dry/2.5) + 0.25·persistence + 0.20·clip(thermal/2.5)
pipe_w    = max(exp(−(d_water/60)²), 0.8·exp(−(d_gas/60)²))
leak      = 100 · clip(leak_raw/0.45, 0, 1) · (0.05 + 0.95·pipe_w)
```

`d_water` is the distance to the 3.3 km water main; `d_gas` is the distance to the gas transmission line. The product is a **screening priority**, not a probability.

The soil-moisture map is `50 + 25·clip(moist_dry, −2, 2)`: 50 = expected, <50 = drier than expected, >50 = wetter.

---

## 4. Results

### 4.1 Model skill

- VV: MAE 1.77 dB on a target with std 3.75 dB; R² 0.611 on 2026 holdout. This is a meaningful expected-condition model for C-band backscatter.
- NDMI: MAE 0.178 on a target with std 0.393; R² 0.471. Optical moisture is noisier because of cloud gaps and vegetation structure.
- The residuals are close to zero-mean by construction; the question is whether their spatial pattern is informative.

### 4.2 Pipeline enrichment test (the key validation)

The water main was compared with **200 translated placebo corridors** of the same length and orientation, inside the AOI, using the same 30 m buffer:

| Statistic | Real corridor | Placebo mean | Placebo 95th pct | Ratio | p-value |
|---|---:|---:|---:|---:|---:|
| Mean moisture z | 0.019 | 0.028 | 0.127 | 0.66 | **0.567** |
| 95th percentile moisture z | 0.324 | 0.886 | — | 0.62 | **0.891** |

**Interpretation:** the corridor is not enriched in dry-season moisture anomalies relative to random lines. In fact, the real corridor's extremes are slightly *lower* than typical placebo lines. This is a negative result for the hypothesis that this particular main is leaking in a way Sentinel-1 can see. It does not prove there is no leak; it says the data do not support a corridor-scale detection at this AOI.

Why might this be?

1. **No known leak.** The OSM main is a real buried water line, but there is no confirmed failure during 2022–2026. A non-leaking pipe should not produce an anomaly.
2. **Irrigation and land cover dominate.** The AOI is 73% cropland; irrigation, crop rotation and harvest change the SAR/NDMI signal more than a small leak would.
3. **C-band penetration and resolution.** A 20 m pixel integrates a 400 m² area; a small leak's moisture plume may fill only a fraction of it. C-band also senses the top ~2–5 cm, which dries quickly.
4. **The model removes too much.** Static soil/landcover features may absorb the corridor's baseline wetness, leaving little residual.
5. **The main may be below the detection threshold** (deep burial, low leakage rate, free-draining soil).

This is exactly the kind of result the research document warned about: satellite leak screening is feasible in some environments, but reliability depends on soil, land cover, pipe depth, leak duration and ground validation.

### 4.3 Hotspots (candidates for field checking)

The top candidates from the current run are below. Scores are relative (0–100); a score of 60 is the strongest evidence in this AOI, not “60% probability of a leak”.

| # | Lat | Lon | Score | Moisture z | Persistence | Thermal z | Distance to water main | Confidence | Land cover |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 1 | 42.64752 | 23.61555 | 59.8 | 0.52 | 0.48 | 0.51 | 0 m | 100 | crop |
| 2 | 42.63126 | 23.60194 | 57.1 | 1.12 | 0.72 | −0.06 | 28 m | 80 | crop |
| 3 | 42.64609 | 23.61500 | 49.8 | 0.55 | 0.45 | 1.03 | 20 m | 100 | crop |
| 4 | 42.64486 | 23.61349 | 43.6 | 0.19 | 0.33 | 0.97 | 0 m | 80 | crop |
| 5 | 42.64238 | 23.61168 | 40.7 | −0.05 | 0.20 | 1.02 | 0 m | 60 | crop |
| 6 | 42.63919 | 23.60935 | 37.8 | 0.35 | 0.33 | 0.39 | 20 m | 100 | grass |
| 7 | 42.66013 | 23.63877 | 34.8 | 0.74 | 0.41 | −0.22 | 2,042 m (28 m to gas) | 80 | crop |
| 8 | 42.64910 | 23.61708 | 34.0 | 0.17 | 0.42 | −0.01 | 0 m | 60 | crop |
| 9 | 42.66435 | 23.63529 | 30.9 | 0.29 | 0.38 | 0.09 | 2,128 m (0 m to gas) | 60 | crop |

Hotspot #2 is the most interesting: 28 m from the main, moisture z = 1.12, persistence 72%, and its strongest dates are in the 2022 and 2025 dry seasons. Hotspots #7 and #9 are on the gas line, not the water main; a gas leak does not normally wet soil, so treat them as land-surface anomalies, not water-leak candidates.

The full list is in `outputs/hotspots.csv` and `outputs/hotspots.json`.

### 4.4 Data quality notes

- 69 dry-season scenes over 5 years is enough for a stable mean but not for a daily time series; 2022–2024 have only 10–11 scenes per dry season (single-satellite era), 2025–2026 have 19.
- S2 cloud cover reduces usable NDMI dates; nearest-date matching within ±10 days can mix pre/post-rain conditions.
- Landsat thermal is 100 m native; the 20 m grid is interpolation, not new information.
- The soil-moisture map is a **relative anomaly**, not volumetric water content (m³/m³). ERA5 gives the coarse absolute background (~0.24 m³/m³ in the top 7 cm).

---

## 5. The interactive map

Open `outputs/aquaguard_map.html` directly in a browser (it is self-contained, ~3 MB, no server or API key needed). Layers:

- **Leak likelihood (2022–2026)** — corridor-weighted evidence score, 0–20+.
- **Soil-moisture anomaly (z)** — dry-season residual, dry (red) ↔ wet (blue).
- **Thermal cooling anomaly** — positive = cooler than the scene median.
- **Persistence** — fraction of dry-season dates with wet residual.
- **Confidence** — data density × evidence agreement.
- **Moisture anomaly 2022–2026** — annual layers for storytelling.
- **Buried water main** (cyan), **60 m inspection corridor**, **gas transmission line** (orange dashed).
- **NISAR L-band HH latest** and **HH/HV change (Jun→Oct 2026)** — public browse, approximate georeferencing, display-only.

The left panel reports the number of S1 dates, dry-season scenes, the top score and the pipeline-enrichment p-value. Hotspot popups include a dry-season residual time-series chart and the evidence table.

Static outputs:

- `outputs/aquaguard_map.png` — two-panel map (soil moisture and leak likelihood) over a Sentinel-2 true-colour basemap.
- `outputs/corridor_profile.png` — moisture residual and leak score along the 3.3 km main.
- `outputs/soil_moisture_anomaly.tif`, `outputs/leak_likelihood.tif`, `outputs/persistence.tif`, `outputs/thermal_anomaly.tif`, `outputs/confidence.tif`, `outputs/moisture_raw_z.tif`, `outputs/moisture_smooth_z.tif`.

---

## 6. How to run

```bash
# 1. install the pinned environment
~/.pixi/bin/pixi install

# 2. OSM pipeline vectors (Overpass; needs internet)
~/.pixi/bin/pixi run python -m scripts.extract_pipelines

# 3. acquire all sensors (S1 orbit 7, S2, Landsat, ERA5, static fallbacks)
~/.pixi/bin/pixi run python -m pipeline.acquire

# 4. train, validate, fuse, write GeoTIFFs and hotspots
~/.pixi/bin/pixi run python -m pipeline.model

# 5. build the HTML map and static figures
~/.pixi/bin/pixi run python -m pipeline.make_map

# 6. serve it (optional; the HTML also opens from disk)
python3 -m http.server 8765 --directory outputs
# http://127.0.0.1:8765/aquaguard_map.html
```

Runtime on this machine: acquisition ~10–20 min (S1 is the long pole), model ~5 min, map <1 min. Disk: raw stacks ~190 MB; outputs ~17 MB.

NISAR browse layers are already in `data/raw/nisar/`. To regenerate:

```bash
~/.pixi/bin/pixi run python scripts/nisar_extract.py --browse \
  --scene-json /tmp/opencode/nisar/search.json \
  --dates 2026-06-20 2026-10-06
```

For the authenticated HDF5 path, put Earthdata credentials in `~/.netrc` and use `scripts/nisar_extract.py --hdf5 ...`. The code is implemented but was not run on the Bulgaria scenes.

---

## 7. What would make this a real leak detector

1. **Ground truth.** Obtain utility repair/leak records (date, location, pipe material, diameter, leak rate) for the AOI or a nearby network. Without labels, the model can only learn “normal”, not “leak”.
2. **NISAR HDF5.** Download calibrated GCOV HH/HV for 2026, compute L-band change and coherence, and compare with C-band. This is the challenge's central sensor and the strongest scientific upgrade.
3. **Multiple orbits / look directions.** Use descending 7 and ascending 102/29 to separate moisture from viewing geometry.
4. **Sub-pixel / field-scale aggregation.** Score 100 m pipe reaches, not 20 m pixels; a leak is a point source with a plume, not a pixel.
5. **Hydraulic fusion.** Pressure/flow anomalies from SCADA would break the ambiguity between irrigation, soil and leakage.
6. **In-situ validation.** Soil-moisture probes, drone thermal, GPR/ERT at the top hotspots.
7. **A controlled testbed.** A buried pipe with known leak rates, soil probes and drone/thermal measurements — the only way to establish detection limits.

---

## 8. Files

| Path | Contents |
|---|---|
| `pipeline/` | acquisition, features, model, map |
| `scripts/extract_pipelines.py` | OSM pipeline vectors |
| `scripts/nisar_extract.py` | NISAR browse/HDF5 extraction |
| `data/raw/` | S1/S2/LST stacks, NISAR browse, manifests (git-ignored) |
| `data/static/` | WorldCover, DEM, slope, SoilGrids, distances |
| `data/met/` | ERA5 daily/hourly weather |
| `data/vectors/` | water main, gas line, AOI pipelines |
| `outputs/` | map, GeoTIFFs, hotspots, validation, model metrics |
| `research/` | broad research, data audit, static data, NISAR audit |
| `docs/SOLUTION.md` | challenge-aligned solution design |
| `docs/RESULTS.md` | this document |

---

## 9. One-paragraph conclusion

AquaGuard is a working, open-source, end-to-end satellite leak-screening pipeline: it ingests five sensors, learns the weather- and land-cover-expected behaviour of every 20 m pixel, extracts persistent dry-season moisture and thermal residuals, fuses them with pipeline geometry, validates against placebo corridors, and presents an interactive map with evidence cards. On the Elin Pelin water main the pipeline association is **not statistically significant**, so the correct conclusion is a ranked list of inspection candidates — not a leak detection. That negative result is itself useful: it defines the conditions (known leak, calibrated NISAR L-band, ground truth, hydraulic data) under which the next iteration can become a real detector.
