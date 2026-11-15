# Coryell NISAR leak chips: train/test package

Small NISAR L-band SAR image chips around **water leak repairs** in the Coryell
City Water Supply District (rural central Texas), with **matched negatives**
on the same pipe network and the same satellite pass, split 80/20 into train
and test. It is meant for training and evaluating leak detectors and for
exploring the signal, at the NASA Space Apps hackathon.

Built 2026-11-15 by `pesho_coryell_data_package/build_pesho_package.py` (seed 20261115).

## Contents

1. [Quick facts](#1-quick-facts)
2. [Quick start](#2-quick-start)
3. [Layout](#3-layout)
4. [Sources](#4-sources)
5. [How the samples were chosen](#5-how-the-samples-were-chosen)
6. [Train/test split and leakage guard](#6-traintest-split-and-leakage-guard)
7. [Counts](#7-counts)
8. [SAR data per sample](#8-sar-data-per-sample)
9. [Normalisation statistics](#9-normalisation-statistics)
10. [Field reference](#10-field-reference)
11. [Exception mask (sample slip) check](#11-exception-mask-sample-slip-check)
12. [Caveats](#12-caveats)
13. [Rebuilding](#13-rebuilding)
14. [Credit and licence](#14-credit-and-licence)

## 1. Quick facts

| | |
|---|---|
| Samples | **3,014**: 274 positives (leak repairs) + 2,740 negatives (10 per positive) |
| Split | train 2,420 (220 positives), test 594 (54 positives), by leak groups |
| Satellite data | NISAR L2 GCOV, stack **041_D_073** (track 41 descending, frame 73), CRID **P05023** (PROVISIONAL), 24 passes 2025-12-31 to 2026-10-15, every 12 days, about 20:18 local time |
| Chip | 20 x 20 px, 10 m pixels (200 m x 200 m), native UTM 14N grid (EPSG:32614), no resampling |
| Passes per sample | `t-2`, `t-1`, `t0` (last pass at or before the repair), `t+1` |
| Bands | HHHH, HVHV (linear gamma-0), mask, numberOfLooks, inputDataExceptionMask, rtcGammaToSigmaFactor |
| Stats | per pass: mean / median / std / valid fraction of HH and HV (linear and dB) in circles of 250 m, 500 m, 1 km, 2 km around the point, and over the whole district |
| Size | 92 MB in 6,034 files |

## 2. Quick start

```bash
python load_example.py                      # loads the index and the first train positive
python load_example.py --sample N1692_03    # any sample
python load_example.py --png sample.png     # also draws HH dB, HV dB, normalised HH (needs matplotlib)
```

Minimal loading code (numpy only):

```python
import csv, json, numpy as np
idx = list(csv.DictReader(open("train/index.csv")))           # or pandas.read_csv("train/index.csv")
s = idx[0]["sample_id"]
z = np.load(f"train/{s}/sar.npz")
sar = z["sar"]                     # (4, 6, 20, 20) float32: passes x bands x rows x cols
passes, bands = list(z["pass_names"]), list(z["band_names"])   # ['t-2','t-1','t0','t+1'], ['HHHH',...]
meta = json.load(open(f"train/{s}/meta.json"))

t0 = passes.index("t0")
hh, mask = sar[t0, 0], sar[t0, 2]
valid = (mask >= 1) & (mask <= 254) & (hh > 0)
hh_db = np.where(valid, 10 * np.log10(hh), np.nan)
d = meta["passes"][t0]["district"]                 # whole-district stats of the same pass
hh_norm = (hh_db - d["hh_db_median"]) / d["hh_db_std"]
```

## 3. Layout

```
pesho_coryell_data_package/
  README.md          this file
  passes.csv         one row per pass (24): time, granule, CRID, district-wide stats, exception-mask fractions
  summary.json       counts per split x cause / zone / quarter / cell, excluded leaks, negative-sampling log
  load_example.py    loading example
  risk_context.csv   one row per sample (3,014): leak-risk score of the nearest pipe piece for the month of `t0`
                     (added by `cd asen_results && pixi run coryell-risk`; join on `sample_id`)
  train/index.csv    one row per sample (2,420)
  train/<sample_id>/sar.npz     chips: passes x bands x 20 x 20
  train/<sample_id>/meta.json   sample metadata, chip geotransform, point position, per-pass stats
  test/...           same (594 samples)
```

Sample IDs: positives `P<ObjectId>` (the leak record ID), negatives
`N<ObjectId>_<01..10>` (the positive they were drawn for).

## 4. Sources

- **Leaks:** "Coryell City Leak Survey" (Survey123 layer of the Coryell City
  WSD, via its GIS consultant's ArcGIS Online), all 1,692 records, downloaded
  2026-11-14; see `data/coryell/README.md` in the repo. ObjectId 1611 (a test
  entry near Galveston) is dropped. The leak date is `datetime`, when the
  repair was logged on site (UTC).
- **Pipes:** `waterlines.geojson`, 918 lines, 624 km (size, diameter,
  material). **Pressure zones:** `pressure_zones.geojson`, 7 polygons.
- **NISAR:** L2 GCOV frequency A (10 m), HH and HV, from ASF. HHHH, HVHV,
  mask and numberOfLooks come from district subsets of each granule made by
  `scripts/download_nisar_coryell.py` (`data/coryell/nisar/district/`);
  inputDataExceptionMask and rtcGammaToSigmaFactor were read straight from the
  remote `.h5` files (HTTP range requests). Same grid in both: pixel edges on
  multiples of 10 m in UTM 14N; the district raster is 4,721 x 3,928 px with
  its top-left corner at (603,870 E, 3,506,740 N).

No personal data: crew account names (`Creator`, `Editor`), `notes` and other
free text are not included. Pipe size and water loss are parsed numbers.

## 5. How the samples were chosen

### Positives (label 1)

Every leak repair on or after 2025-10-17 (the NISAR window; 322 records)
**that has a P05023 pass of stack 041_D_073 at or before the repair, at most
12 days earlier**, all causes. Its time point **`t0` = the last pass at or
before the repair time** (comparing the pass start time and the repair time,
both UTC). `days_pass_to_repair` is the elapsed time from that pass to the
repair, in days (0.04 to 11.9, median 6.0).

Excluded (48), listed in `summary.json`:

| Reason | Leaks |
|---|---|
| Repaired before the first P05023 pass (2025-10-17 to 2025-12-30) | 27 |
| Repaired after 2026-10-27, more than 12 days after the last P05023 pass (2026-10-15) | 11 |
| Repaired 2026-08-04 to 08-16: the last pass before is 2026-07-23, 24 days earlier (instrument data gap) | 10 |

No leak was lost to invalid SAR pixels: the 4 centre pixels are valid on `t0`
for all 274.

### Negatives (label 0)

**10 per positive, on the same pass `t0`**, at random points **on the pipe
network**, drawn along `waterlines.geojson` with probability proportional to
line length (random generator seeded). A candidate is kept only if:

- the whole chip lies inside the district raster and its 4 centre pixels are
  valid (mask 1..254) on `t0`;
- **no recorded leak of any cause lies within 300 m whose repair date is within
  60 days of `t0`** (all 1,691 leak records are used, also those before the
  NISAR window; the one record without a date counts as always conflicting);
- **its chip shares no pixel with any other sample on the same pass `t0`**
  (positives or negatives). Chips are 200 m squares, so the centres are at least
  200 m apart in x or y (which also means at least 200 m apart);
- its chip shares no pixel with any sample **of the other split** whose four
  passes overlap its four passes (see section 6).

Each negative records the nearest pipe's attributes, the distance to the
nearest recorded leak at **any** time (`nearest_leak_m`, can be small: a pipe
that leaked years ago is a valid negative) and to the nearest leak within 60
days (`nearest_leak_pm60d_m`, always at least 300 m). Candidates rejected while
sampling: 601 < 300 m from a leak within 60 days, 502 chip overlaps a sample on the same t0, 514 chip overlaps an other-split sample on a shared pass, 22 outside raster.

## 6. Train/test split and leakage guard

- **Unit:** groups of positives. Two positives are in the same group if their
  chips overlap (closer than 200 m in both x and y, which covers everything
  within 200 m) **and** their four passes share at least one acquisition (so
  overlapping chips on the same pass, or a repeat repair at the same spot within
  about a month). 274 positives form 202 groups (157 single, 34 of 2, 5 of 3,
  3 of 5, 2 of 6, 1 of 7). Every negative takes its positive's split and
  `group_id`.
- **Stratification:** whole groups were assigned to test so that test holds
  about 20% of the positives and keeps the proportions of cause
  (natural / construction / other), pressure zone, calendar quarter of `t0`
  and a 3 x 3 geographic cell of the district (`geo_cell`, N/C/S x W/C/E).
  Method: seeded random starts plus greedy group flips and swaps, minimising
  the squared deviations from 20% in every category.
- **Guarantee (checked):** no train chip and test chip share any pixel on any
  acquisition. Positives: by grouping. Negatives: by the sampling rules above
  (and a negative is always at least 300 m from any leak within 60 days, so from
  any positive whose passes overlap).
- Not guarded: the same place can appear in train and test on passes that
  don't overlap (more than about 36 days apart), for example a pipe that leaked
  in March (train) and again in September (test). Use `group_id` plus
  `utm_x/utm_y` if you want a stricter spatial split.

## 7. Counts

Positives / negatives per split and cause (negatives counted by their
positive's cause, `stratum_cause`):

| Cause | Train pos | Train neg | Test pos | Test neg | Total pos |
|---|---|---|---|---|---|
| Naturally occurred | 205 | 2,050 | 50 | 500 | 255 |
| Construction / maintenance | 12 | 120 | 3 | 30 | 15 |
| Other | 3 | 30 | 1 | 10 | 4 |
| **Total** | **220** | **2,200** | **54** | **540** | **274** |

Per pressure zone (polygon containing the point; `none` = outside all 7 polygons). Positives were stratified on the polygon zone, or the reported zone where the point is outside all polygons, so the positive counts here can differ slightly from the strata:

| Zone | Train pos | Train neg | Test pos | Test neg | Test share of pos |
|---|---|---|---|---|---|
| Coryell City | 32 | 328 | 8 | 94 | 20% |
| Crawford | 45 | 288 | 11 | 72 | 20% |
| Levita | 2 | 29 | 0 | 5 | 0% |
| Mound | 4 | 100 | 1 | 23 | 20% |
| Pancake | 96 | 1110 | 24 | 277 | 20% |
| Ranch Addition | 0 | 6 | 0 | 0 | - |
| Riddle | 40 | 325 | 10 | 67 | 20% |
| none | 1 | 14 | 0 | 2 | 0% |

Per calendar quarter of `t0`:

| Quarter | Train pos | Train neg | Test pos | Test neg | Test share of pos |
|---|---|---|---|---|---|
| 2025Q4 | 6 | 60 | 1 | 10 | 14% |
| 2026Q1 | 35 | 350 | 9 | 90 | 20% |
| 2026Q2 | 45 | 450 | 11 | 110 | 20% |
| 2026Q3 | 100 | 1000 | 25 | 250 | 20% |
| 2026Q4 | 34 | 340 | 8 | 80 | 19% |

Per 3 x 3 geographic cell (`geo_cell`):

| Cell | Train pos | Train neg | Test pos | Test neg | Test share of pos |
|---|---|---|---|---|---|
| CC | 21 | 210 | 5 | 50 | 19% |
| CE | 89 | 890 | 22 | 220 | 20% |
| CW | 42 | 420 | 10 | 100 | 19% |
| NC | 21 | 210 | 5 | 50 | 19% |
| NE | 1 | 10 | 0 | 0 | 0% |
| NW | 22 | 220 | 6 | 60 | 21% |
| SC | 5 | 50 | 1 | 10 | 17% |
| SE | 19 | 190 | 5 | 50 | 21% |

## 8. SAR data per sample

### Chip geometry

- 20 x 20 px at 10 m, on the native NISAR grid (UTM 14N, EPSG:32614), north up.
- The chip is placed so the point lies **between its 4 centre pixels**:
  `point_col` and `point_row` are fractional pixel positions measured from the
  chip's top-left corner (pixel centres at `c + 0.5`, `r + 0.5`), always in
  9.5..10.5.
- Geotransform (GDAL order) in `meta.json`: `[x0, 10, 0, y0, 0, -10]`, with
  `x0, y0` the UTM coordinates of the chip's top-left **corner**. Pixel
  `(r, c)` covers `x0 + 10c .. x0 + 10(c+1)` and `y0 - 10r .. y0 - 10(r+1)`.
  The point is at `utm_x = x0 + 10 * point_col`, `utm_y = y0 - 10 * point_row`.

### Passes

`t0` is the last P05023 pass at or before the repair (positives) or the same
pass as its positive (negatives). `t-1`, `t-2` are the two previous P05023
passes (a reference for change detection) and `t+1` the next one. The spacing
is 12 days, except 24 days across the 2026-07-23 to 08-16 data gap
(`dt_*_days` gives the exact offsets). Passes before 2025-12-31 or after
2026-10-15 do not exist in this run: their slot is **all NaN** and
`available` / `avail_*` is 0 (2025-12-31 has no `t-1`, `t-2`; 2026-01-12 no
`t-2`; 2026-10-15 no `t+1`).

> **`t+1` is after the repair for positives.** The leak was fixed before that
> pass, so a wet patch may be drying out or gone, and repair work (digging,
> vehicles) may show. That is useful for analysis (before/after), but **a
> detection model must not use `t+1`**: it would not exist at detection time
> and it differs systematically between positives and negatives.

### Bands (`band_names`, in this order)

| # | Band | Unit / codes | Notes |
|---|---|---|---|
| 0 | `HHHH` | gamma-0, **linear power** (dB = 10 log10) | Raw, unfiltered (no speckle filter). NaN where mask is not 1..254. |
| 1 | `HVHV` | gamma-0, linear power | Same. |
| 2 | `mask` | 0 invalid (partly focused), 1..254 valid (subswath number), 255 outside the acquisition | |
| 3 | `numberOfLooks` | looks (float) | Stored at float16 precision by the district download. |
| 4 | `inputDataExceptionMask` | bit flags, 0 = no anomaly, 2 = "qFSP-H1 sample slip" | See section 11. |
| 5 | `rtcGammaToSigmaFactor` | factor (about 0.6-0.9 here) | sigma-0 = gamma-0 x factor. Terrain/geometry only. |

All bands are stored in one float32 array; mask and exception codes are exact
small integers in float32 (original types uint8). A missing pass is NaN in
every band.

## 9. Normalisation statistics

Per sample and per available pass (`meta.json` -> `passes[i]`):

- `circles["250" | "500" | "1000" | "2000"]`: statistics over all pixels whose
  centre is within that radius (m) of the point;
- `district`: the same statistics over the **whole district** (lon -97.904 to
  -97.412, lat 31.337 to 31.686) for that pass, identical for every sample on
  the pass and also in `passes.csv`;
- `chip`: valid and exception fractions inside the 20 x 20 chip.

Each block holds, for `hh` and `hv`: `*_lin_mean`, `*_lin_median`,
`*_lin_std` (linear gamma-0) and `*_db_mean`, `*_db_median`, `*_db_std`
(computed on the dB values of the pixels, so `db_mean` is not the dB of
`lin_mean`); plus `n_pixels` (pixels in the area), `valid_frac` (valid pixels
/ `n_pixels`), `exc_frac` (share of the valid pixels with a non-zero
exception code). Valid = mask 1..254 and HH, HV finite and > 0. Exception
pixels are **not** removed from the statistics (use `exc_frac` to decide).
Standard deviations are population (ddof = 0). Circles that reach past the
district raster (only 2 km circles near the edge) count the outside part as
not valid.

District HH medians (`passes.csv`) range from -13.8 dB (2026-03-25) to -9.0 dB (2026-10-03, a wet scene,
probably rain); the dry August-September passes are about -13.1 to -13.3 dB (HV about -19.5 to -19.7 dB).
District medians come from a 0.001 dB histogram built in row blocks (means and std are exact); circle
medians are exact.

Suggested use: normalise each pass by its own district median and std in dB
(removes pass-wide changes such as rain or calibration), or by a local circle
(removes the land cover around the point), then compare `t0` with `t-1`, `t-2`.

## 10. Field reference

### `train/index.csv`, `test/index.csv`

One row per sample. Empty = not applicable / unknown.

| Field | Meaning |
|---|---|
| `sample_id` | `P<ObjectId>` or `N<ObjectId>_<k>` |
| `label` | 1 leak repair, 0 random pipe point |
| `split` | `train` / `test` |
| `group_id` | leakage group (`G<smallest ObjectId in the group>`); negatives carry their positive's |
| `positive_id` | the positive this sample belongs to (itself for positives) |
| `cause` | positives: `natural`, `construction`, `other`; empty for negatives |
| `stratum_cause` | the positive's cause, for both labels (used for stratification) |
| `leak_objectid` | leak record ObjectId (positives) |
| `repair_utc` | repair logged on site, UTC (positives) |
| `days_pass_to_repair` | days from the `t0` pass start to the repair (positives), 0-12 |
| `leak_pipe_size_in` | pipe size from the leak record, parsed to inches (largest number in `line_size`) |
| `loss_gpm` | estimated water loss parsed to US gal/min (largest value for entries like "15/300gpm" or "escalated to") |
| `repair_type` | coded choice from the form: `line_`, `fitting_`, `valve`, combinations |
| `zone` | pressure zone polygon containing the point (empty if none) |
| `zone_reported` | pressure zone entered on the leak form (positives) |
| `geo_cell` | 3 x 3 cell of the district bbox: row N/C/S, column W/C/E |
| `quarter` | calendar quarter of `t0` |
| `lon`, `lat` | WGS 84 |
| `utm_x`, `utm_y` | UTM 14N (EPSG:32614), m |
| `nearest_pipe_id`, `pipe_size`, `pipe_diameter_in`, `pipe_material` | nearest line of `waterlines.geojson` (`OBJECTID`, `Size` text, `Diameter` in inches, `Material`) |
| `dist_to_pipe_m` | distance to that line (negatives: about 0) |
| `nearest_leak_m`, `nearest_leak_id`, `nearest_leak_days` | nearest other leak record at any time: distance, ObjectId, its repair time minus `t0` in days |
| `nearest_leak_pm60d_m` | nearest other leak repaired within 60 days of `t0` |
| `t0_date`, `t0_utc` | the sample's pass (granule date, start time UTC) |
| `tm2_date`, `tm1_date`, `tp1_date` | dates of `t-2`, `t-1`, `t+1` (empty if missing) |
| `avail_tm2`, `avail_tm1`, `avail_t0`, `avail_tp1` | 1 if the pass exists |
| `dt_tm2_days`, `dt_tm1_days`, `dt_tp1_days` | pass time minus `t0`, days |
| `chip_x0`, `chip_y0` | chip top-left corner, UTM m |
| `point_col`, `point_row` | point position in the chip, fractional pixels |
| `t0_chip_valid_frac`, `t0_chip_exc_frac` | valid share of the chip on `t0`; exception share of its valid pixels |
| `t0_hh_db_median_500m`, `t0_hv_db_median_500m` | quick look: median dB within 500 m on `t0` |

### `<sample_id>/sar.npz`

| Array | Shape, type | |
|---|---|---|
| `sar` | (4, 6, 20, 20) float32 | passes x bands x rows x cols |
| `available` | (4,) bool | pass exists |
| `pass_names` | (4,) str | `t-2`, `t-1`, `t0`, `t+1` |
| `pass_dates` | (4,) str | granule dates (empty if missing) |
| `band_names` | (6,) str | see section 8 |

### `<sample_id>/meta.json`

- `sample`: the index row.
- `chip`: `crs`, `x0`, `y0`, `pixel_size`, `width`, `height`, `geotransform`,
  `point_col`, `point_row`.
- `passes`: four entries (`t-2` .. `t+1`) with `available`, and if available
  `pass_idx`, `date`, `start_utc`, `granule`, `crid`, `days_from_t0`, `chip`,
  `circles`, `district` (section 9).
- `bands`, `pass_roles`.

### `passes.csv`

| Field | Meaning |
|---|---|
| `pass_idx`, `date`, `start_utc`, `local_time_cdt_cst` | pass (granule date is UTC; local time is the evening before) |
| `granule`, `crid`, `maturity`, `counter` | NISAR product (`_002` used for 2026-06-17) |
| `n_chips` | sample chips cut from this pass (all roles) |
| `n_pixels`, `valid_frac` | district pixels and valid share |
| `exc_frac`, `exc_code2_frac` | share of valid district pixels with any exception code / with code 2 (sample slip) |
| `looks_median`, `rtc_chip_median` | median looks over the district; median RTC factor over the chips |
| `hh_*`, `hv_*` | district stats as in section 9 |

## 11. Exception mask (sample slip) check

The `inputDataExceptionMask` was read for all 24 passes over the whole district.
**Only one pass carries any exception code: 2026-04-18**, with code 2 ("NISAR LSAR qFSP-H1 sample slip")
on **51.8% of the valid district pixels**: one contiguous block covering every
column east of about lon -97.78 (all rows), i.e. the eastern half of the district (Crawford, Riddle, Coryell
City and the east of Pancake). The other 23 passes are clean (exception mask 0 everywhere).

Effect (scratch check, not in the package): relative to the mean of the neighbouring passes 2026-04-06 and
2026-04-30, flagged pixels changed by **about 0.35 dB less in HH** (and 0.10 dB less in HV) than unflagged
pixels of the same rows. That is darker, as in the teammate pipeline (which found 1-1.5 dB in Kitchener), but
much smaller here, and partly confounded because flagged and clean pixels are in different parts of the
district.

Impact on this package: 110 samples have `t0` = 2026-04-18 (median chip exception fraction
0.00), and 297 samples use that pass in some slot
(`t-2` .. `t+1`). Every chip carries the mask (band 4) and every stats block its `exc_frac`. Options: drop the
flagged pixels, add about +0.35 dB to flagged HH, or simply normalise per pass (the district statistics mix
flagged and clean pixels on that date).

## 12. Caveats

- **Leak start is unknown.** The record is the repair. A leak may have run for
  hours or for weeks, so a positive's `t0` may or may not show it; `t-1`/`t-2`
  may already show it too. `days_pass_to_repair` is an upper bound on how long
  it had to be running at `t0` only if it started before `t0`.
- **Weak labels.** Most repairs are small pipes (1-3") with 5-50 gpm losses;
  many will leave no wet patch visible at 10 m. Big mains and high losses are
  rare (see `leak_pipe_size_in`, `loss_gpm`).
- **Negatives are not certified dry.** They are pipe points with no recorded
  leak within 300 m and 60 days; unreported leaks, irrigation, ponds and rain
  are not excluded.
- **Positions:** leak points are where the crew stood (metres to tens of
  metres). Median distance from a positive to the mapped pipe is 2 m, 90% are
  within 15 m, a few are far off (max 715 m: a pipe missing from the map or a
  mistyped point). Negatives are exactly on mapped pipes, so `dist_to_pipe_m`
  separates the classes: **don't use it as a feature**.
- **`t+1` is after the repair** (section 8). Also avoid `days_pass_to_repair`,
  `repair_*`, `loss_gpm`, `nearest_leak_*` as model inputs: they exist only
  for positives or encode how negatives were chosen.
- **PROVISIONAL products** (P05023); 2027 reprocessing will supersede them.
- **HH/HV were set to NaN where the mask is not 1..254** by the district
  download, so the raw values of invalid pixels are not kept. Values of valid
  pixels are untouched.
- **Speckle:** single pixels vary by several dB (about 5 looks). Average over
  windows before comparing passes.
- **Descending pass at about 20:18 local time** (evening): dew is unlikely, but
  rain the day before will raise HH district-wide (watch the district median).

## 13. Rebuilding

From the repository root, with Python 3.12 and numpy, h5py, fsspec, aiohttp,
requests, pyproj, rasterio, shapely; an Earthdata login in `~/.netrc` (NISAR
access approved):

```bash
python scripts/fetch_coryell_data.py                         # leak, pipe, zone layers -> data/coryell/
python scripts/download_nisar_coryell.py --stacks 041_D_073  # district GeoTIFFs (or let the build read them remotely)
python pesho_coryell_data_package/build_pesho_package.py                        # plan -> remote -> extract -> assemble
```

The build is seeded (`--seed 20261115`) and resumable: intermediate files go
to `data/coryell/nisar/pesho_work/` (plan, remote reads, per-pass extracts),
and each stage skips work already done. `--stage plan|remote|extract|assemble`
runs one stage; `--min-free-gb 8` stops when the disk gets full. The leak
layer is live, so a rebuild after new records are added gives different
samples.

## 14. Credit and licence

Leak, pipe and zone data: Coryell City Water Supply District and its GIS
consultant; no licence stated, publicly queryable. **Ask them before any use
beyond the hackathon.** NISAR data: NASA/JPL and ISRO, distributed by the
Alaska Satellite Facility DAAC. Aerial imagery used only for the geolocation
check (not included): Esri World Imagery.

## 15. Leak-risk score per sample (`risk_context.csv`)

Added 2026-11-15 by `asen_results/src/aquaguard/coryell_risk.py` (`pixi run coryell-risk`
in `asen_results/`). It is a tabular baseline to compare any SAR model against, and a
candidate extra input.

The pipe network is cut into 3,007 pieces of at most 250 m. A gradient-boosting model
ranks every piece for every month from leak history and pipe attributes only (no SAR):
leaks on the piece and within 200 m / 500 m, months since the last one, length, diameter,
galvanised flag, pressure zone, month of year. Features use only leaks repaired **before
the month starts**. It is trained on 2020-10 to 2025-10 and scored on 2025-11 to 2026-10,
so every sample's score (all `t0` dates fall in that period) is out of sample.

| Column | Meaning |
|---|---|
| `sample_id`, `split`, `label` | as in `index.csv` |
| `risk_month` | month of `t0` (YYYY-MM) |
| `piece`, `piece_dist_m` | nearest pipe piece and the distance to it |
| `risk_score` | model probability that the piece leaks in `risk_month` |
| `risk_pct` | percentile rank among all piece-months of the hold-out (1 = riskiest 1%) |
| `own_all`, `own_24`, `own_12` | leaks on the piece: ever, last 24 months, last 12 months |
| `n200_all`, `n200_24`, `n500_all`, `n500_24` | leaks within 200 m / 500 m of the piece |
| `mo_since_own`, `mo_since_200` | months since the last leak on the piece / within 200 m (999 = never) |

Results (full table in `asen_results/data/reports/coryell_risk.md`): on all piece-months
of the hold-out the ranking reaches AUC 0.79 [0.76, 0.82], and the top 5% of piece-months
hold 32% of the leaks. On this package's test split `risk_score` alone gives AUC 0.79
(594 samples, 54 leaks).

Caveat: negatives in this package are drawn in proportion to pipe length, while leaks
cluster where there are customers and service lines. Part of the package AUC therefore
reflects where leaks concentrate; the piece-month evaluation does not have this problem,
because it scores every piece.
