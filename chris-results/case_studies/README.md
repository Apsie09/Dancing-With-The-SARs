# TerraGuard ground-truth case studies

Three independent tests of the **same pipeline**, each in its own folder, using real water-utility
labels rather than the unlabelled Bulgarian demo. Run with a single environment variable; the code
is identical, only `case.json` changes.

> In the original repository these folders are local experiments. **This `chris-results` bundle
> includes their prepared vectors, small layers and generated outputs** so the platform can be
> opened without rerunning acquisition. The raw satellite stacks are still excluded.

## Case 1 — Aguascalientes, Mexico

| Item | Value |
|---|---|
| Source | [`erickfama/rs_leaks`](https://github.com/erickfama/rs_leaks) |
| Network | Utility GIS `Tuberias.shp`: 8,134 pipe segments in the AOI (575 km), EPSG:32613 |
| Labels | `leaks_clean_download.csv`: 50 actual repairs (`SE REPARA FTC, GENERA BA`) in the AOI, Jan–May and Nov–Dec 2022 |
| AOI | 5 × 5 km, EPSG:32613, 20 m grid (260 × 260) |
| Period | 2022-01-01 → 2023-01-01 |
| Sentinel-1 | ascending 151, **28 dates**, 99% valid |
| Sentinel-2 / Landsat | 111 / 51 dates |
| Dry months | Jan–May + Nov–Dec 2022 |
| Train / test | Jan–Aug 2022 / Nov–Dec 2022 |

**Results**

- VV expected-condition model: MAE **2.10 dB**, R² **0.436** (321k test rows).
- NDMI expected-condition model: MAE **0.076**, R² **0.294** (321k test rows).
- Label evaluation: **AUC 0.526**, median percentile **56.2**, labelled mean leak score 29.2 vs
  background 28.8.
- Pipeline enrichment vs 40 translated network placebos: p = **1.00** (not significant).

The Aguascalientes network is extremely dense (23 km of pipe per km²), so the corridor prior covers
most of the AOI. The map displays only primary + transmission mains.

## Case 2 — Calgary, Canada

| Item | Value |
|---|---|
| Source | City of Calgary Open Data: [`w6h9-w33i`](https://data.calgary.ca/d/w6h9-w33i) (water mains) and [`dpcu-jr23`](https://data.calgary.ca/d/dpcu-jr23) (water main breaks) |
| Network | Public water main GeoJSON, clipped to the AOI (5,879 segments), EPSG:32611 |
| Labels | 48 water main breaks in the AOI, 2025–2026 |
| AOI | 10 × 10 km, EPSG:32611, 20 m grid (571 × 375) |
| Period | 2025-01-01 → 2026-11-15 |
| Sentinel-1 | ascending 122, **50 dates**, 95–100% valid |
| Sentinel-2 / Landsat | 91 / 76 dates |
| Season | all months 2025–2026 |
| Train / test | Apr–Sep 2025 / 2026 |

**Results**

- VV expected-condition model: MAE **1.85 dB**, R² **0.650** (3.89M test rows).
- NDMI expected-condition model: MAE **0.137**, R² **0.249** (2.82M test rows).
- Label evaluation: **AUC 0.524**, median percentile **51.7**, labelled mean leak score 24.7 vs
  background 24.0.
- Pipeline enrichment vs 40 translated network placebos: p = **0.90** mean, **0.95** p95 (not significant).

**Important data limitation:** the Planetary Computer Sentinel-1 RTC archive over this Calgary AOI
only starts in **April 2025** for the available orbits. The earlier 2022–2024 period is not
available, so this test uses 2025–2026 only. It is a short-record, all-season test, not a multi-year
dry-season baseline.

## Side-by-side

| | Aguascalientes | Calgary |
|---|---|---|
| Labels | 50 repairs | 48 breaks |
| Network | 575 km in 25 km² (trunk shown) | 100 km² (mains ≥600 mm shown) |
| S1 dates | 28 | 50 |
| VV R² | 0.436 | 0.650 |
| NDMI R² | 0.294 | 0.249 |
| **Label AUC** | **0.526** | **0.524** |
| Median percentile of labels | 56.2 | 51.7 |
| Corridor enrichment p | 1.00 | 0.90 / 0.95 |
| Verdict | weak positive, not significant | weak positive, not significant |

## What this means

The **expected-condition models are skilful** — they predict C-band backscatter with R² 0.44–0.65
and optical moisture with R² 0.25–0.29 on held-out dates. But the **final leak score is only weakly
associated with the historical repair/break locations**: AUC ≈ 0.52–0.53, i.e. barely better than
random ranking.

That is a real and useful result, not a bug:

1. A repair record marks where a pipe failed, not necessarily where a detectable moisture plume
   existed for weeks. Small or quickly repaired leaks leave little surface expression.
2. The score is a multi-month mean, while a repair is a point-in-time event. A visible anomaly may
   have lasted only days around the repair date.
3. Urban surfaces, roads, irrigation and snow confound the moisture signal; the 20 m pixel mixes
   pipe-scale effects with block-scale land cover.
4. The label sets are unbalanced (50 vs 56k background pixels); AUC is the right metric, but the
   effect size is small.
5. The dense Aguascalientes network makes proximity a weak discriminator; the Calgary record is
   short and spans winter snow.

The honest conclusion is that **the current weather-normalised moisture/thermal residual is a weak
screening signal for historical repair points**. It is consistent with the published Austin open
dataset (F1 0.68 vs 0.58 dummy) and with the research document's warning that satellite leak
screening is condition-dependent. To become a useful detector, the next iteration needs
event-window residuals around known leaks, leak-duration/rate labels, calibrated NISAR L-band and
hydraulic data — not a bigger model on the same labels.

## Run a case

```bash
CASE=case_studies/aguascalientes/case.json

TERRAGUARD_CASE=$CASE ~/.pixi/bin/pixi run python -m pipeline.acquire --workers 16
TERRAGUARD_CASE=$CASE ~/.pixi/bin/pixi run python -m pipeline.model
TERRAGUARD_CASE=$CASE ~/.pixi/bin/pixi run python -m pipeline.make_map

# open $CASE's outputs/terraguard_map.html
```

Calgary:

```bash
CASE=case_studies/calgary/case.json
# same three commands
```

The case folders contain:

```
case_studies/
  prepare.py                 # build Aguascalientes and Calgary from source repos
  prepare_coryell.py         # subset the Coryell district data into a 10 x 10 km case
  aguascalientes/
    case.json                # AOI, grid, dates, orbit, network, labels, season
    data/vectors/            # water_main.geojson, labels.csv
    data/{raw,static,met,interim}/
    outputs/                 # map, GeoTIFFs, hotspots, validation.json
  calgary/
    ...
  coryell/
    case.json                # fixed 10 x 10 km AOI, 55 S1 dates, 72 summer labels
    data/vectors/            # clipped water_main.geojson, labels.csv
    data/{raw,static,met,interim}/
    outputs/                 # same map, GeoTIFFs, hotspots, validation.json
  README.md
```

`prepare.py` expects the cloned source repo at `/tmp/opencode/cases/aguas` and the Calgary breaks
CSV at `/tmp/opencode/cases/calgary/breaks.csv`; the case outputs are already generated here.
`prepare_coryell.py` expects `data/coryell/` from `scripts/fetch_coryell.py`.

Maps: `case_studies/aguascalientes/outputs/terraguard_map.html`,
`case_studies/calgary/outputs/terraguard_map.html` and
`case_studies/coryell/outputs/terraguard_map.html`. Static previews are the matching
`terraguard_map.png` files.

## Case 3 — Coryell City WSD, Texas

Coryell is a **normal Sentinel-1 case**, built with the same `case.json` contract and the same
pipeline modules as the other two. It is a fixed 10 × 10 km rural AOI chosen from the densest
2025–26 summer repair cell.

| Item | Value |
|---|---|
| Source | Coryell City WSD public ArcGIS layers (no stated licence) |
| Network | 184 clipped pipe segments in the AOI, EPSG:32614 |
| Labels | 72 summer repairs (June–September 2025–2026) |
| Period | 2025-01-01 → 2026-11-15 |
| Sentinel-1 | ascending 34, **55 dates** (2025-01-07 → 2026-11-05) |
| Sentinel-2 / Landsat | 76 / 47 dates |
| VV model | MAE 1.32 dB / R² **0.426** |
| NDMI model | MAE 0.113 / R² **0.505** |
| Label ranking | AUC **0.548**, median percentile 59.1 |
| Corridor test | mean p **0.024**, p95 **0.244** |

The mean corridor result is nominally small, but the p95 test is not, and the label AUC is still
weak. No NISAR imagery is used. Licence: **none stated**; see `data/coryell/README.md`.

Run it with the same commands as the other cases:

```bash
CASE=case_studies/coryell/case.json
TERRAGUARD_CASE=$CASE pixi run python -m pipeline.acquire --workers 16
TERRAGUARD_CASE=$CASE pixi run python -m pipeline.model
TERRAGUARD_CASE=$CASE pixi run python -m pipeline.make_map
```

## Caveats

- The pipeline's core is designed for **persistent** dry-season leakage, not acute repairs; the
  case labels are repair events. This mismatch is part of why the AUC is low.
- No NISAR layer is used in the cases (the browse extraction was done only for Bulgaria).
- SoilGrids / terrain / road layers are absent in the case folders; the models use land cover, SAR,
  optical and weather, so the feature set is slightly smaller than the Bulgarian run.
- The label AUC is a ranking metric over repair locations; it is not precision/recall against
  confirmed visible leaks, and it does not prove the absence of a leak at any other pixel.
- Coryell’s mean corridor p = 0.024 is nominal; its p95 is 0.244 and its label AUC is 0.548.
  Do not describe that as leak detection.
