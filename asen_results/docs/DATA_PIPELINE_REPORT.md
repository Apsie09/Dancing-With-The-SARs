# TerraGuard: data pipeline, decisions and results

_Status as of 2026-11-15 (updated 11:00 EET). NASA Space Apps Challenge 2026, "Dancing with the SARs"._

This document records what was built for the data task in
[`dataset/Data_Engineering_Task.md`](../dataset/Data_Engineering_Task.md), why each decision was made, and what
the data showed. Every number below comes from the pipeline and can be regenerated (see [Reproducing](#reproducing)).

---

## 1. Summary

| Question | Answer |
|---|---|
| Can Kitchener water-main breaks be joined to NISAR observations? | **Yes.** All 105 usable breaks in the NISAR period fall inside NISAR coverage. 60 have before, near-date and after images on the same track. |
| Can NISAR data be used without downloading full files? | **Yes.** City crops are streamed over HTTPS: about 13 GB of GCOV and 1.8 GB of GUNW/SME2 were transferred, instead of ~570 GB of full files. |
| Is a leak visible as a backscatter change at the break site (GCOV, 10 m)? | **No.** Break sites can't be told apart from matched control sites: AUC 0.48-0.52, every CI includes 0.5. No localized change is detected down to ~0.1-0.2 dB. |
| Can breaks be **predicted** per pipe segment and month? | **Yes.** The baseline (infrastructure, break history, season, weather) reaches **AUC 0.91** on 11 unseen months, and the riskiest 5% of segment-months contain 56% of breaks. |
| Does NISAR (soil moisture, ground movement, backscatter) improve that prediction? | **No, not with the data so far.** v1: ΔAUC between -0.02 and 0. v2 (per-pass normalisation, L1 with nested CV, monotonic baseline): **L1 switches off every NISAR column in every fold**. The early soil-moisture hint was noise. There are only 11 months of NISAR data (96 break-months). |
| Are large **rural** leaks visible (Coryell, Texas, NISAR L-band)? | **No (not confirmed).** An exploratory analysis on 2 tracks found +0.25 dB HH at leak sites while leaking (p = 0.0003). A **pre-registered** test on a held-out third track did not replicate it: -0.03 dB [-0.24, +0.19], p = 0.76. |

**Bottom line:** the pipeline that joins tabular infrastructure data to NISAR is complete and reproducible. The infrastructure
risk model is strong (AUC 0.90-0.91). In three settings (Kitchener urban, Coryell rural, plus the team's Sentinel-based
cases) no leak signature could be detected, and NISAR features don't improve break prediction with the ~1 year of data
that exists. Everything is set up to re-test as more months arrive.

---

## 2. Data sources (verified, not assumed)

| Source | What | Access |
|---|---|---|
| Kitchener `Water_Main_Breaks` (ArcGIS FeatureServer) | 3,026 break records, 1985 - 2026-10-31 (only 9 before 1997) | open, paginated |
| Kitchener `Water_Mains` (ArcGIS FeatureServer) | 16,214 pipe segments, 939 km: material, diameter, install date | open |
| NISAR L2 **GCOV** (backscatter, 10 m, HH+HV) | 143 granules over the city (137 after de-duplication); beta from 2025-10-28, provisional from 2026-01-03, validated from 2026-10-23 | Earthdata login; streamed |
| NISAR L2 **GUNW** (unwrapped interferograms, 80 m) | 71 12-day pairs, 2025-11 to 2026-10 | streamed |
| NISAR L3 **SME2** (soil moisture, 200 m EASE grid) | 77 dates, 2025-10 to 2026-10 | streamed |
| ERA5 via Open-Meteo | hourly and daily weather and soil state for one Kitchener point | open, no key |

Facts we checked against the brief, and corrections:
- **Provisional GCOV over Kitchener starts 2026-01-03, not 2026-06-17** as the task text says.
- GCOV here is **dual-pol HH + HV only** (no VV/VH), with 10 m posting (40 MHz). The pixel size was confirmed from the HDF5 grid, EPSG:32617.
- All tracks share one pixel lattice (pixel centres at 5 m mod 10 m), so crops from different dates align **without resampling**.
- Three tracks see the city: 090A frame 023, 162A frame 024, and 127D frames 066/067. The city straddles the boundary between frames 066 and 067.

---

## 3. What was built (stages)

All code is in `src/terraguard/`. All parameters are in `config/pipeline.toml`. Everything runs through `pixi run <task>`.

| Stage | Task | Output | Size |
|---|---|---|---|
| 1. Incidents | `incidents` | `kitchener_incidents.parquet` | 0.3 MB |
| 2. NISAR catalogue | `catalog` | `nisar_acquisitions.parquet` | 65 KB |
| 3. Spatiotemporal matching | `match` | `incident_nisar_matches.parquet`, `incident_coverage_summary.parquet` | 0.2 MB |
| (probe) | `probe` | measures HDF5 layout and the bytes needed per crop | - |
| 4. Streamed SAR crops + patches | `sar --all` | 70 city crops (3.2 GB); `patches.h5` (3,096 patches, 165 MB) | ~13 GB transferred |
| 5. Patch features | `features` | `radar_features.parquet` (80 feature columns) | 1.2 MB |
| 6a. Control sites | `mains`, `controls` | 550 controls on mains; `control_patches.h5` (15,480 patches) | 0.8 GB |
| 6b. Labelled dataset | `dataset` | `ml_dataset.parquet` (18,576 rows) | 8 MB |
| Signal checks | `signal`, `signal-controls` | `data/reports/signal_check*.md` | - |
| 7a. GUNW + SME2 crops | `aux` | 71 GUNW + 77 SME2 crops | 1.84 GB transferred, 69 MB disk |
| 7b. Pipe-segment sampling | `segments` | `seg_gcov` / `seg_gunw` / `seg_sme2` parquet | 40 MB |
| 7c. Break-risk model | `risk` | `risk_panel_eval.parquet`, `data/reports/risk_model_report.md` | 27 MB |
| Report | `report` | `data/reports/data_feasibility_report.md`, charts, map | - |

`data/` (about 4.4 GB) is git-ignored and fully regenerable.

---

## 4. Decisions and their reasons

### Environment and access
- **pixi** (conda-forge) is the package manager, as the team chose. The environment is locked in `pixi.lock`.
- **Never download full NISAR granules.** HDF5 files are opened over HTTPS with `earthaccess` + `fsspec` + `h5py`, and only the
  city window is read. Measured: GCOV stores data in 512x512 gzip chunks, so a 64 px patch still costs a whole chunk. The
  efficient unit is therefore **one whole-city crop per pass** (~190 MB transferred, ~50 MB on disk), with all patches cut locally.
- Hugging Face hosting was considered and dropped. Everything stays local.
- HTTP requests have connect and read timeouts plus retries, after one request hung for 13 minutes. All writes are atomic
  (temporary file, then rename), so interrupted runs resume safely.

### Incident cleaning (Stage 1)
- **Nothing is silently deleted.** Problems are *flagged*:
  - `date_suspect`: dates before 1997, including 1985-01-01 placeholders.
  - `is_primary_record` / `duplicate_group`: same asset, or same location within 25 m, on the same day.
  - `location_suspect`: no street and no asset; for example 3 records at identical coordinates 12 km from the city cluster.
  - `is_cancelled`.
- Placeholders become missing values: material `XXX`, size `0`, asset id `0`.
- Date-only records (82%) are referenced to **local noon with ±0.5 day uncertainty**. One clock time that repeats 49 times
  (15:38) was treated as a bulk-load artefact.
- **Column roles** are stored in the parquet metadata:
  - `pre_incident` (allowed as model inputs): material, size, age, depth, prior breaks.
  - `at_report` and `post_incident` (labels and analysis only): status, repair, cause, closure, frost depth.

### Matching (Stage 3)
- Windows are configurable (days relative to the reported date): pre [-120, -21], event [-14, +3], post [+10, +120].
  Gaps between windows, and intervals that straddle a window edge, become `timing_uncertain`.
- `potential_event_window` is a **matching hypothesis**, not observed leakage.
- `comparison_group` = track + direction + bandwidth + polarisation. Only acquisitions within one group are compared.
  Processing-version (CRID) mixes are flagged.
- One observation per incident per pass. Adjacent frames of the same pass are the same measurement.
- **Beta products are low confidence** (pre-calibration). The cost is that Dec-2025 incidents lose their pre-event references.

### SAR preprocessing (Stage 4)
- The original γ⁰ (linear) is kept untouched in the crops. The analysis layer is a dB image with a **Lee filter whose speckle level
  comes from the product's own `numberOfLooks`** (CV² = 1/ENL).
- The valid mask combines `mask` (0 = invalid, 255 = fill, 1..n = sub-swath) and **`inputDataExceptionMask == 0`**.
- **Found and measured:** 6 granules carry exception code 2 ("qFSP-H1 sample slip") over ~73% of the city, *including all
  three validated granules*. Those pixels read ~1-1.5 dB too dark in HH, so they are excluded.
- No dataset-wide normalisation is applied before the train/test split, to avoid leakage.

### Features, controls, labels (Stages 5-6)
- **Localized change** is the core feature: (break-site disk minus background ring) of (dB minus a pre-event reference on the
  same track). Pre-event rows use a leave-one-out reference.
- Infrastructure features use only `pre_incident` columns. Weather and soil state come from ERA5 at acquisition time.
- **Controls are not negatives.** There are 5 per incident, placed on the water-main network, 0.5-3 km away, matched on material
  and size (495/550 matched on both), with no recorded break within 300 m / ±365 days. They are labelled `unknown`, and they
  serve as a difference-in-differences baseline, an anomaly-detection background, and an evaluation reference.
- Labels: `confirmed_break_event` (inside the documented break interval), `candidate_satellite_match` (event window),
  `unknown` (everything else). **`verified_non_leak` is never assigned**, because no evidence of absence exists.
- Splits: each incident stays together with its controls. There are 5 folds of 2 km spatial blocks (balanced to 21-23 incidents
  each) and a temporal hold-out from 2026-08-01.

### The pivot to break-risk prediction (Stage 7)
- Detecting an active leak directly in GCOV showed no signal (section 5). The goal was reframed as **predicting break
  risk per pipe segment and month, with NISAR as additional features**. This is the "augment with NISAR" use case.
- At the segment-month level, "no recorded break this month" is a legitimate negative, because the target is *reported breaks*,
  not "leaking right now".
- **Forecast design:** every feature uses only data from before the month (break history strictly before; weather and
  NISAR from the previous 30 days).
- NISAR features per segment: GCOV HH/HV dB and its change vs. the previous pass on the same track; GUNW local LOS movement
  (high-passed against ~2 km to remove atmosphere and orbit effects) and coherence; SME2 soil moisture (recommended retrievals;
  3x3 neighbourhood fill flagged), its value relative to the city median, and its change.
- **Models** (scikit-learn):
  - Baseline: gradient-boosted trees (`HistGradientBoostingClassifier`, depth 4, ≥200 samples per leaf) trained on
    2005-2025 with weighted negative sampling, then scored on Dec 2025 - Oct 2026.
  - The added value of NISAR is measured by stacking: baseline score alone (A) vs. baseline score + NISAR (B). Both a regularised
    logistic regression and boosted trees are used, with the same 5 spatial-block folds and a paired block-bootstrap CI for B - A.
- Breaks are linked to segments by asset id (81%) or by nearest segment within 30 m (2,976 of 2,980 linked).

---

## 5. Results

### Leak visibility at break sites (GCOV backscatter)
- 72 subset tests: unfrozen conditions, large mains, road closed / long impact, tight window, and site radius 20/30/70 m.
  Nothing is significant after Benjamini-Hochberg (min q = 0.27). The minimum detectable effect is ~0.11-0.14 dB at 70 m.
- **Sites vs. matched controls:** the AUC of naive change scores is 0.48-0.52, and every 95% CI includes 0.5.
  Difference-in-differences gives p ≥ 0.29.
- A weak "site darker" trend (-0.1 to -0.4 dB) that appeared without controls **disappears against controls**, so it was a
  city-wide or seasonal effect.

### Break-risk prediction
| | AUC | Average precision | Top-5% capture |
|---|---|---|---|
| Baseline (temporal hold-out, 178k segment-months, 96 with a break; base rate 0.05%) | **0.907** | 0.011 | **56%** |

Added value of NISAR (paired block bootstrap, B - A):

| Added to baseline | ΔAUC [95% CI] (logistic) | ΔAP [95% CI] (logistic) |
|---|---|---|
| All NISAR | -0.019 [-0.039, -0.002] | +0.000 [-0.004, +0.016] |
| GCOV only | -0.003 [-0.013, +0.012] | -0.001 [-0.002, +0.005] |
| GUNW only | -0.003 [-0.007, +0.002] | -0.001 [-0.002, +0.001] |
| SME2 only | -0.008 [-0.018, +0.001] | **+0.009 [-0.001, +0.032]** |

The boosted-tree second stage gives the same picture. The full tables are in `data/reports/risk_model_report.md`.

NISAR coverage of the evaluation rows: GCOV 82%, GUNW 99%, **SME2 35%**. Soil moisture is missing over the dense urban core and
in frozen months, where the retrieval is not produced.

### Break-risk v2: normalisation + regularization (`pixi run risk-v2`, `data/reports/risk_model_report_v2.md`)
These changes were fixed before running:
- per-pass radiometric normalisation of GCOV (each pass's city median dB removed),
- signed log1p for skewed inputs,
- an **L1** logistic second stage with the penalty chosen by **nested** spatially blocked CV (test folds never used for tuning),
- **monotonic constraints** on the boosted baseline (older pipe, more past breaks, more frost → risk can't decrease).

| | AUC | Average precision | Top-5% capture |
|---|---|---|---|
| Baseline v1 (boosting) | 0.907 | 0.011 | 56% |
| Baseline v2 (boosting + monotonic) | 0.904 | 0.012 | 56% |

- L1 + NISAR: the inner CV chose the strongest penalty in all 5 folds, and **no NISAR column survived** in any fold. The small
  +0.002 AUC of variant B comes from how the baseline score is penalised, not from NISAR.
- Boosting + normalised NISAR: ΔAUC -0.014 to -0.021 (overfitting).

### Coryell, Texas: rural leak visibility (`pixi run coryell`, reports `data/reports/coryell_*.md`)
Coryell is the most favourable setting available: Peter's data, Coryell City WSD, with 1,692 GPS-located repairs, 303 natural
leaks in the NISAR window (median ~20 gpm, 90th percentile 100 gpm), and pipes under pasture rather than pavement. Calibrated
GCOV windows were streamed around each leak and 3 controls per leak on the district's own pipes (0.4-1.5 km away, no other
leak within 300 m / ±365 d). This transferred **6.0 GB instead of 338 GB**.

- **Discovery** (stacks 041D_073 + 062A_017; 29k patches):
  - single-feature site-vs-control AUCs are ≈ 0.5 for all leaks. The ≥ 100 gpm leaks reach 0.60-0.64, but already **before** the repair.
  - A time-course plot (`coryell_event_study.png`) suggested sites are brighter while leaking and normal after repair.
  - The per-leak HH "brightness drop" from leaking (-60..+14 d) to after (+30..+120 d) was **+0.25 dB [+0.11, +0.40], p = 0.0003**
    (n = 201). The placebo on controls gave +0.00 dB. The drop did **not** scale with leak size (Spearman ≈ 0).
  - The windows were chosen after seeing the plot, so this was treated as exploratory.
- **Pre-registered confirmation** (`docs/CORYELL_CONFIRMATION_PREREG.md`, written before download; held-out stack 163A_017;
  2.1 GB): **NOT CONFIRMED**. Leak drop **-0.03 dB [-0.24, +0.19], p = 0.76**, n = 37 leaks. The placebo was 0.00. The interval
  excludes the +0.25 dB found in discovery.
  - Only 37 of 122 leaks were testable:
    - 50 lie in a strip this track's `mask` marks as invalid;
    - ~30 were repaired in Sep-Oct 2026 and have no "after" passes yet;
    - the last two passes carry the sample-slip exception.
  - Re-running in early 2027 with the same rules would roughly double n.

### Physical sanity checks
- GUNW local movement: ~1.5 mm median and ~5 mm p95 in summer at coherence ~0.7. In winter coherence is ~0.5 and the spread is
  2-3x larger (snow and frozen ground decorrelate the signal).
- SME2: 0.11-0.22 m³/m³, with no retrievals in Dec-Jan (frozen soil), as expected.

---

## 6. Limitations
- NISAR has existed for only ~1 year: there are 96 break-months in the evaluation window, so small gains can't be detected.
- Break dates are *report* dates. Leak start, duration and volume are unknown (`return_to_normal` is missing for 96% of records).
- 57% of NISAR-era breaks happen in Dec-Feb, when frozen ground and snow dominate L-band changes.
- GUNW is 80 m, coarser than single-pipe sinkholes. SME2 is 200 m and missing in the urban core.
- The current mains snapshot is used for historical years, so old breaks on replaced pipes are linked to their replacements.
- The GUNW sign convention (`-(phase - ionosphere) * λ/4π`) has not been validated against ground truth. Features rely only on
  magnitudes and on consistency within a segment.

## 7. Next steps
1. **Re-run the pre-registered Coryell confirmation** in early 2027, once the Sep-Oct 2026 leaks have "after" passes (same rules, more leaks).
2. **Re-run monthly** as NISAR and break data accumulate (`pixi run aux`, `segments`, `risk-v2`).
3. A **demo map** of predicted risk per pipe and month, with breaks overlaid (the challenge asks for an interactive app).
4. Possibly form 10 m interferograms from GSLC crops (same grid as GCOV) for finer ground movement. Add NISAR STATIC layers
   (layover/shadow) for urban masking.
5. Evaluate Bulgaria's transmission mains separately: larger flows and rural corridors favour SAR.

---

## Reproducing

From the `asen_results/` folder:

```bash
pixi install
pixi run pipeline                  # stages 1-3 + report (no login needed)
# Earthdata login once: pixi run python -c "import earthaccess; earthaccess.login(strategy='interactive', persist=True)"
pixi run sar --all --workers 6     # stage 4  (~13 GB streamed, ~3.4 GB disk)
pixi run features
pixi run mains && pixi run controls && pixi run dataset
pixi run signal && pixi run signal-controls
pixi run aux --workers 6           # stage 7a (~1.8 GB streamed)
pixi run segments && pixi run risk && pixi run risk-v2
# Coryell (rural leaks; data via: python ../scripts/fetch_coryell_data.py --steps vectors)
pixi run coryell --workers 6 && pixi run coryell --analyse                       # discovery (~6 GB streamed)
pixi run coryell --confirm --workers 6 && pixi run coryell --confirm --analyse   # pre-registered confirmation (~2 GB)
pixi run report
pixi run -e dev test
```
