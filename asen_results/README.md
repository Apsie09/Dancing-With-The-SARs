# TerraGuard: Kitchener water-main breaks × NISAR GCOV

Data pipeline for the task in [`dataset/Data_Engineering_Task.md`](dataset/Data_Engineering_Task.md).
All six stages are implemented. The final summary is in `data/reports/data_feasibility_report.md`
(regenerate with `pixi run report`).

All commands run from this folder (`cd asen_results`).

```bash
pixi install          # conda-forge env (Python 3.12, geopandas, earthaccess, h5py, rasterio, ...)
pixi run pipeline     # stages 1-3 + reports, ~10 s
pixi run -e dev test  # unit tests
```

Individual stages: `pixi run incidents | catalog | match | report`.

Stages 4–6 (need an Earthdata login in `~/.netrc` for `sar` only):
```bash
pixi run probe                    # stream-test one granule: layout, pixel size, bytes per crop
pixi run sar --all --workers 6    # Stage 4: stream city crops (~190 MB each, ~13 GB total), cut patches
pixi run features                 # Stage 5: radar_features.parquet
pixi run signal                   # exploratory localized-change check -> data/reports/signal_check.md
pixi run mains                    # Kitchener water-main network (for control sites)
pixi run controls                 # Stage 6a: 5 control sites per incident on mains + their patches/features
pixi run dataset                  # Stage 6b: labels, DiD features, grouped splits -> ml_dataset.parquet
pixi run signal-controls          # incident sites vs controls: AUC + difference-in-differences
pixi run report                   # final feasibility report
pixi run aux --workers 6          # Stage 7a: GUNW (ground movement) + SME2 (soil moisture) city crops, ~1.8 GB streamed
pixi run segments                 # Stage 7b: sample NISAR layers along all 16k water-main segments
pixi run risk                     # Stage 7c: segment x month break-risk model, baseline vs + NISAR
pixi run risk-v2                  # Stage 7c v2: normalised NISAR, L1 + nested CV, monotonic baseline
pixi run coryell --workers 6      # Coryell (TX) rural leak test: stream site windows (~6 GB), then --analyse
pixi run coryell --confirm ...    # pre-registered confirmation on a held-out track (docs/CORYELL_CONFIRMATION_PREREG.md)
```

What was done, why, and the results: [`docs/DATA_PIPELINE_REPORT.md`](docs/DATA_PIPELINE_REPORT.md).

All parameters (AOI, collections, temporal windows, patch size, controls, splits) are in
[`config/pipeline.toml`](config/pipeline.toml).

| Stage | Module | Output |
|---|---|---|
| 1. Incidents (ArcGIS, paginated) | `src/terraguard/incidents.py` | `kitchener_incidents.parquet` |
| 2. NISAR catalogue (CMR via earthaccess) | `src/terraguard/catalog.py` | `nisar_acquisitions.parquet` |
| 3. Spatiotemporal matching | `src/terraguard/matching.py` | `incident_nisar_matches.parquet`, `incident_coverage_summary.parquet` |
| 4. Streamed SAR crops + patches | `src/terraguard/sar.py` | `data/sar/crops/`, `patches.h5`, `sar_patches.parquet` |
| 5. Features | `src/terraguard/features.py` | `radar_features.parquet` |
| 6. Controls + labelled dataset | `src/terraguard/controls.py`, `dataset.py` | `control_*`, `ml_dataset.parquet` |
| Signal checks | `src/terraguard/signal_check.py` | `data/reports/signal_check*.md` |
| Reports | `src/terraguard/report.py` | `data/reports/data_feasibility_report.md`, `incidents_summary.md`, charts, map |

`data/` is git-ignored and fully regenerable. Raw ArcGIS snapshots are kept in `data/raw/`.

## Conventions
- Column roles are stored in the incidents parquet metadata (`terraguard` key). Only `pre_incident`
  columns may be used as predictive features. `post_incident` fields (repair type, cause, status…) are
  for labelling and analysis only.
- Nothing is silently dropped. Duplicates, suspect dates and suspect locations are **flagged**
  (`is_primary_record`, `date_suspect`, `location_suspect`), and match confidence records the reasons.
- `potential_event_window` is a matching hypothesis around the *reported* date, not observed leakage.
- `comparison_group` = track + direction + bandwidth + polarisations. Only compare acquisitions within
  one group. CRID (processing version) changes are flagged.

## Data volume
Remote GCOV over the AOI is ~626 GB; the 70 granules used total 408 GB. **Nothing is downloaded in full.** Stage 4 streams
one 27 x 22 km city crop per pass (~190 MB transferred, ~13 GB total) and keeps 3.2 GB of crops. All of `data/` is ~4.3 GB.
