# TerraGuard: satellite leak screening for buried water pipelines

**NASA Space Apps Challenge 2026 — "Dancing with the SARs"**

**Status:** implemented 15 November 2026. The working pipeline, interactive map, metrics and caveats are in [`docs/RESULTS.md`](RESULTS.md). No TerraGuard accuracy is claimed; the AOI has no confirmed leak.

## 1. Pitch

TerraGuard is an open-source, map-first screening tool for buried water pipelines. It combines a 2018–2026 Sentinel-1 C-band time series, Sentinel-2 optical moisture, Landsat thermal data, ERA5 weather, soil/land-cover/DEM layers, NISAR L-band browse imagery and OpenStreetMap pipeline geometry. A physics-informed LightGBM model learns what each 20 m pixel should look like given rainfall, temperature, evapotranspiration, soil, vegetation and season; the residual flags ground that stays wet when the weather says it should dry. Persistence, optical moisture and a thermal-cooling check are fused into a corridor-weighted leak-likelihood map with evidence cards. The output is an **inspection-priority map**, not a verified leak detection.

## 2. Challenge alignment

The brief asks for an interactive NISAR application that visualizes surface change, explains its drivers and is open-source. TerraGuard maps persistent soil-moisture anomalies and tests one driver: leakage from a buried main.

| Challenge requirement | How TerraGuard satisfies it | Honest caveat |
|---|---|---|
| **Study area** | Elin Pelin, Sofia Province, Bulgaria; 5.5×6.3 km farmland crossed by a 3.3 km buried water transmission main (OSM 1106343159). | No confirmed leak; method demonstration. |
| **NISAR data** | Public ASF NISAR GCOV **browse** imagery for 2026-06-20 and 2026-10-06 (track 094), shown as L-band HH and HH/HV change layers. A calibrated HDF5 extraction path (`scripts/nisar_extract.py --hdf5`) is implemented and validated on ASF's public sample. | Full Bulgaria HDF5 download needs Earthdata auth and was blocked; browse is 8-bit, ~160 m, approximate georeferencing, display-only. |
| **Multi-year time series** | Sentinel-1 RTC C-band 2018–2026, one orbit/pass (descending 7), 434 dates, 100% AOI coverage. | C-band is shallower (~2–5 cm vs ~5–20 cm); NISAR archive starts Oct 2025. |
| **Interactive medium** | Self-contained Leaflet/Folium map: layer toggles, annual moisture layers, leak-likelihood layer, hotspot cards with evidence and residual time series. | Demo, not utility operations. |
| **Physical drivers** | Dielectric/moisture; ET/thermal inertia; vegetation; dry-season residual; co-pol vs cross-pol. | 20 m analysis grid; 100 m native thermal; no metre-level localisation. |
| **Open source** | Python/LightGBM/GeoPandas/rasterio/Folium, Pixi environment, open data, MIT licence. | Free Earthdata login is needed for calibrated NISAR HDF5. |
| **Storytelling** | Local farmland, non-revenue water, map-first demo, evidence cards, explicit negative validation. | No local incident confirmed. |

**NISAR and Sentinel-1 play different roles.** NISAR provides L-band context and a two-date change layer; Sentinel-1 provides the multi-year record needed to learn seasonal and weather-driven behaviour. The two are never mixed into a single uncalibrated index. Calibrated NISAR GCOV HH/HV and closure phase are the next scientific upgrade, not a claim of this build.

## 3. Study area

| Item | Value |
|---|---|
| Location | Elin Pelin municipality, Sofia Province, Bulgaria; centre 42.6375°N, 23.6075°E. |
| AOI | 5.5×6.3 km farmland on a 20 m grid (EPSG:32634, UTM 34N; 277×314 pixels). |
| Asset | OSM way 1106343159: `man_made=pipeline`, `substance=water`, `location=underground`; 3.3 km transmission main. |
| Coverage | Sentinel-1 RTC 2018–2026 (orbit 7, descending); Sentinel-2 2018–2026; Landsat 2018–2026; NISAR browse June/October 2026. |
| Ground truth | None confirmed; OSM geometry, not a utility GIS. |

## 4. What was actually built

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

**Ingest.** Sentinel-1 RTC comes from Planetary Computer (per-item CRS; adjacent tiles mosaicked per date). Sentinel-2 L2A comes from AWS Earth Search (NDMI, NDVI, SCL cloud mask; BOA offset applied). Landsat C2 L2 thermal comes from Planetary Computer (`ST_B10`, QA cloud mask). ERA5 weather comes from Open-Meteo. SoilGrids, WorldCover, Copernicus DEM and OSM provide static context. NISAR browse imagery comes from the public ASF browse endpoints.

**Expected-condition model.** Two LightGBM regressors (`objective=regression_l1`, 450 trees) predict:
- Sentinel-1 VV backscatter in dB;
- Sentinel-2 NDMI.

Features: soil texture/SOC/bulk density, land cover, elevation, slope, distance to built-up/roads, rainfall lags (1/3/7/14/30/60 days), temperature, ET₀, ERA5 soil moisture, VPD, dry-spell length, season, NDVI and SAR texture. The model is trained on all conditions, not leak labels, and tested on the **2026 temporal holdout**.

A Landsat LST model was tried and discarded (R² < 0). Thermal evidence uses the direct per-scene anomaly `−(LST − scene median)`, which removes weather and captures local evaporative cooling without a bad regression.

**Residual and fusion.** For each pixel/date:

```
z_moist   = mean(z_VV, z_NDMI)          # positive = wetter than expected
z_thermal = −z_LST_local               # positive = cooler than the scene
persistence = fraction of dry dates with z_moist > 0.5
moist_dry = mean(z_moist) over June–September, 2022–2026
thermal   = mean(z_thermal) over the same dates
```

The evidence is smoothed to 3×3 (60 m), the scale of a shallow leakage plume:

```
leak_raw = 0.55·clip(moist_dry/2.5) + 0.25·persistence + 0.20·clip(thermal/2.5)
pipe_w   = max(exp(−(d_water/60)²), 0.8·exp(−(d_gas/60)²))
leak     = 100 · clip(leak_raw/0.45, 0, 1) · (0.05 + 0.95·pipe_w)
```

The score is relative and evidence-based; it is not a calibrated probability. The 60 m smoothing reflects the physical plume scale, not a fitted tuning parameter.

**Map and cards.** The interactive map has a Sentinel-2 true-colour basemap, Esri reference imagery, leak likelihood, soil-moisture anomaly, thermal cooling, persistence, confidence, annual moisture layers, the water main, a 60 m inspection corridor, the gas line, NISAR browse/change layers and hotspot markers. Each hotspot popup shows moisture residual, persistence, thermal evidence, distance to the pipe, confidence, land cover, strongest dry-season dates and a residual time-series chart.

## 5. The physics

```
leak → soil pore pressure and saturation rise
     → dielectric constant rises (water εr ≈ 80; dry soil ≈ 3–5)
     → co-pol backscatter rises on bare or short vegetation
     → evaporation and thermal inertia change surface temperature
     → vegetation stays green in drought, or dies from waterlogging
```

A buried pipe is not imaged directly. Mains sit 0.9–1.5 m down; L-band senses the top ~5–20 cm of dry soil, C-band ~2–5 cm, and wet soil attenuates both. The satellite sees the moisture halo. Wet soil usually raises co-pol backscatter, but standing water can lower it and dense vegetation masks the soil, so the model learns expected behaviour and uses two-sided residuals.

Wet soil has higher heat capacity and thermal inertia: cooler by day, warmer at night; evapotranspiration adds daytime cooling. But 100 m Landsat thermal cannot resolve a pipe-scale halo: a 5 K source needs a ~40 m patch for a 2 K pixel anomaly. Thermal is a low-weight confirmation of large wet patches, not a primary detector.

The key signal is **dry-season unexplained wetness**. After rain everything is wet; during a dry spell the background dries while a leak keeps its patch wet. Persistence through that dry-down, on a mapped pipe, is far more diagnostic than one wet date.

A 20 m pixel is 400 m²; a 0.1–0.6 m pipe occupies a tiny fraction of it. A 1 m³/h leak wets ~80 m²/day; a 0.1 m³/h weep wets ~8 m², below reliable detection; 10 m³/h wets ~800 m². No published minimum detectable leak rate exists. Speckle reinforces this: a 10 m Sentinel-1 GRD product (about 5 looks) has a 3σ floor near 5.8 dB. Averaging in time and space is mandatory. A 20 m pixel cannot localise a leak to a metre; it can prioritise a corridor.

## 6. Novelty versus existing work

| Prior work | What it establishes | Gap TerraGuard addresses |
|---|---|---|
| **ASTERRA/SUEZ, Affinity Water (2025)** | L-band screening of 9,045 km; 902 leaks; 59% non-surfacing; vendor-reported, acoustically confirmed. | Proprietary; no open, weather-normalised method. |
| **MDFLD-Net, Li et al. (2025)** | L + C + polarimetry + closure phase; 1,545 leaks; 86.3% accuracy. | Supervised, selected dates, quad-pol/labels, no weather normalisation. |
| **Yan et al. (2024)** | PCA + SVM; 1,222 leaks/1,206 non-leaks; 91.86% in Beijing. | Labelled, site-specific, not transferable. |
| **ESA SECO, WATERLENS, ZOE** | Funded SAR/optical/InSAR route screening. | Combination is not novel; the method must be. |
| **Cyprus, Theocharidis et al. (2025)** | Dry-season optical; NMDI/NDWI beat NDVI; acoustic/GPR; one valve false positive. | Optical only; design evidence. |

TerraGuard's testable claim is the combination: weather-normalised residual, multi-sensor evidence, pipeline-constrained scoring and NISAR L-band context in an open implementation. The research review found no published study combining all four with an open codebase. We do not claim first use of SAR for leaks or metre-level localisation.

## 7. Validation and results

There is **no confirmed leak ground truth in the AOI** — no repair records, acoustic surveys or excavations. The output is a screening prioritisation, not a verified detection; TerraGuard does not report precision, recall or accuracy against leaks it cannot confirm.

| Test | Design | Result |
|---|---|---|
| **Temporal holdout** | Train 2022 → 2025-06; test 2026. | VV: MAE **1.77 dB**, R² **0.611**, n = 867,272. NDMI: MAE **0.178**, R² **0.471**, n = 734,421. |
| **Pipeline vs placebo** | True 3.3 km corridor vs 200 translated placebo corridors, 30 m buffer. | Mean moisture z: 0.019 vs 0.028, ratio 0.66, **p = 0.567**. 95th percentile: 0.324 vs 0.886, **p = 0.891**. **Not significant.** |
| **Spatial holdout** | Whole-field / 1 km blocks. | Not run in this build; next step. |
| **Buffer sensitivity** | 30/50/100 m buffers. | Not run in this build; next step. |
| **NISAR agreement** | Match S1 hotspots to calibrated NISAR dates. | Not quantitative: NISAR browse is display-only and approximately georeferenced. |
| **Ablation** | S1 only; + weather; + optical; + thermal. | Not run in this build; next step. |

The strongest evidence is specificity: does the true corridor outrank placebo corridors, stably across buffers and sensors? Here it does not. That is a negative result for this AOI, and it is reported as such. It does not prove there is no leak; it says the available data do not support a corridor-scale detection.

The top candidates are in `outputs/hotspots.csv`. The strongest is 28 m from the main, with moisture z = 1.12 and persistence 0.72; the highest score is 59.8/100 at the main. These are field-check candidates, not detections.

## 8. Demo script for judges (3 minutes)

| Time | What judges see and hear |
|---|---|
| 0:00 | **Title and pipe diagram.** "20–30% of distributed water is lost before it reaches customers. Satellites cannot see pipes, but they see wet soil." |
| 0:20 | **Map zooms to the AOI.** "This 5.5×6.3 km farmland AOI in Sofia Province is crossed by a 3.3 km buried main. Sentinel-1 gives us 194 dates since 2022; NISAR covers it since October 2025." |
| 0:40 | **NISAR toggle.** "This is the public NISAR L-band browse layer and the June→October change. L-band sees deeper than C-band; the calibrated HDF5 path is ready for an Earthdata login. We keep it as context, not as a quantitative input in this build." |
| 1:05 | **Soil-moisture anomaly.** "The model predicts what each 20 m pixel should look like given rainfall, soil and vegetation. Blue is wetter than expected in the dry season; red is drier." |
| 1:35 | **Leak likelihood and hotspot cards.** "The fusion ranks hotspots along the pipe. This card shows 28 m from the main, moisture z 1.12, persistence 72%, and the dry-season dates that drive it." |
| 2:05 | **Validation.** "We tested the real corridor against 200 placebo corridors. The enrichment is not significant — p = 0.89 — so these are inspection candidates, not detections. That honesty is the point: the tool tells you where to look and how strong the evidence is." |
| 2:35 | **Limits and next steps.** "No metre-level localisation, no confirmed leak, 20 m pixels and 100 m thermal. Calibrated NISAR HDF5, repair records and hydraulic data are the next step. Code and data are open." |

If the demo is capped at 30 seconds: map → NISAR toggle → likelihood + top hotspot → "p = 0.89, so this is triage, not detection".

## 9. Limitations and responsible use

- **No ground truth.** The AOI has no confirmed leak; the pipeline association is not statistically significant. Do not present the map as a leak detection.
- **Resolution.** 20 m analysis grid; 100 m native thermal; NISAR browse ~160 m. A leak cannot be localised to a metre.
- **NISAR.** Calibrated GCOV HDF5 requires Earthdata authentication; the public browse is approximate and display-only. The quantitative score uses Sentinel-1/2 and Landsat.
- **Confounders.** Irrigation, crop rotation, harvest, soil texture, drainage, roads and construction produce the same surface signatures.
- **Weather.** ERA5 is a reanalysis at one grid cell, not local rain-gauge data.
- **Temporal sampling.** 2022–2024 have only 10–11 dry-season scenes per year (single-satellite era); 2025–2026 have 19.
- **Responsible use.** Field verification (acoustic, GPR, ERT, visual) is required before any repair decision. The tool should reduce the search area, not replace the crew.

## 10. Judging criteria mapping

| Criterion | TerraGuard evidence |
|---|---|
| **Impact** | Non-revenue water is a global utility problem; the tool ranks a 3.3 km corridor instead of sending crews blindly. |
| **Creativity** | Weather-normalised expected-condition residual + multi-sensor evidence + pipeline-constrained scoring + NISAR L-band context, in one open pipeline. |
| **Validity** | Temporal holdout, 200-corridor placebo test, explicit negative result, documented data audit and CRS/offset traps. |
| **Challenge fit** | NISAR L-band surface-change layer, interactive map, physical drivers, open source, local Bulgarian study area. |
| **Presentation** | Self-contained HTML map, two-panel static map, corridor profile, hotspot cards, three-minute demo script. |

## References

The full literature review, with 34 references and DOIs, is in [`research/Pipeline-Leak-Detection.md`](../research/Pipeline-Leak-Detection.md). Data audits are in [`research/data-audit.md`](../research/data-audit.md), [`research/static-data.md`](../research/static-data.md) and [`research/nisar-audit.md`](../research/nisar-audit.md). Implementation details and metrics are in [`docs/RESULTS.md`](RESULTS.md).
