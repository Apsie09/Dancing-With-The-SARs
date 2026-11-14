# Data availability audit — Elin Pelin, Bulgaria

**Audit date:** 2026-11-14 · **Study area:** `EPSG:4326` bbox west=23.575, south=42.610,
east=23.640, north=42.665 (Elin Pelin plain, east of Sofia, Bulgaria).

All counts below were measured live against the two STAC APIs on the audit date. Nothing is
estimated or copied from documentation. Probe rasters and the machine-readable summary are in
`data/raw/probe/`.

## Bottom line

| Decision | Recommendation |
|---|---|
| **S1 orbit** | **relative orbit 7, descending** — 434 acquisition dates, 9/9 years, 100 % AOI footprint coverage on every date, 6-day median cadence, only one gap >20 days |
| S1 runner-up | relative orbit 102, ascending — 426 dates, 9/9 years, but 8 gaps >20 days |
| S1 orbit to avoid | relative orbit 29, ascending — 659 items looks best by item count, but only **179/422 dates cover the whole AOI** and there are no full-AOI dates in 2022–2024 |
| S2 collection | Earth Search `sentinel-2-l2a`, tile `34TGN` — 919 items / 679 dates; 394 items / 291 dates with `eo:cloud_cover < 30`; 537 / 398 with `< 60` |
| S2 offset | `reflectance = DN * 0.0001 + offset`, offset **−0.1** for processing baseline ≥ 04.00 (639 items), **0** for older baselines (280 items). Read the offset per item from `raster:bands`; do not assume −0.1 archive-wide |
| Landsat | 1 303 items / 845 dates total; 620 items / 423 dates with cloud < 30 %, of which **448 items / 318 dates** are Landsat 8/9 and only **216 scenes / 185 dates** fully cover this small AOI. Exclude Landsat 7 |
| Common grid | **EPSG:32634, 20 m, 277 × 314**, transform `[20, 0, 711020, 0, -20, 4727000]` — `data/raw/probe/grid.json` |
| Blocker | Earth Search Landsat pixels live in the requester-pays `s3://usgs-landsat` bucket. Metadata counts work anonymously; pixel reads fail. Probe rasters were read from the Planetary Computer `landsat-c2-l2` mirror of the same USGS scene |

### Study-area and grid geometry

The AOI is ~5.52 km × 6.27 km. Its axis-aligned envelope in `EPSG:32634` is
`x 711026.53 … 716544.48`, `y 4720721.76 … 4726993.96`. Snapping outward to a 20 m lattice gives:

```
CRS        EPSG:32634 (WGS 84 / UTM zone 34N)
transform  [20.0, 0.0, 711020.0, 0.0, -20.0, 4727000.0]
width      277
height     314
bounds     711020, 4720720, 716560, 4727000
pixels     86 978
```

The exact grid is stored in `data/raw/probe/grid.json`. The AOI is very close to the 24 °E UTM
zone boundary (zone 34 / 35), which is the source of two important traps documented below:
Sentinel-1 RTC tiles switch between EPSG:32634 and EPSG:32635 by date, and Landsat scenes from
path 183 arrive in EPSG:32635 while path 184 arrives in EPSG:32634.

---

## 1. Sentinel-1 RTC

### 1.1 Collection and assets

| Item | Value |
|---|---|
| STAC | `https://planetarycomputer.microsoft.com/api/stac/v1` |
| Collection | `sentinel-1-rtc` |
| Product | Sentinel-1 IW GRD, Radiometrically Terrain Corrected (RTC) **gamma0**, C-band |
| Native resolution | 10 m |
| Pixel values | `float32` **linear power** (not dB, not sigma0) |
| Asset keys | `vv`, `vh` (plus `tilejson`, `rendered_preview`, not used) |
| Nodata | `-32768` |
| Search window | 2018-01-01 … 2026-11-15 |
| Signing | `planetary_computer.sign_inplace` as the client modifier |

The search returns **1 520 items** but only **951 unique dates** across all orbits, because the
same AOI is crossed by several relative orbits and because some ascending frames are split into
adjacent 25-second granules.

### 1.2 Counts per orbit and per orbit state

Orbit ranking must use **full-AOI footprint coverage**, not the number of STAC items. The AOI is
small enough that a frame can intersect the search bbox while covering only a sliver of it.

| Rel. orbit | State | Items | Unique dates | Dates with 100 % AOI coverage | First | Last | Median gap | Max gap | Gaps >20 d | UTC overpass |
|---|---|---:|---:|---:|---|---|---:|---:|---:|---|
| **7** | **descending** | **434** | **434** | **434** | 2018-01-06 | 2026-11-09 | 6 d | 36 d | **1** | 04:29–04:31 |
| 102 | ascending | 426 | 426 | 426 | 2018-01-06 | 2026-11-09 | 6 d | 36 d | 8 | 16:23–16:25 |
| 29 | ascending | 659 | 422 | **179** | 2018-01-01 | 2026-11-10 | 12 d | 1 212 d | 5 | 16:15–16:17 |
| 80 | descending | 1 | 1 | 0 | 2018-01-11 | 2018-01-11 | — | — | — | 04:38 |

Orbit-state totals: **ascending 1 085 items, descending 435 items**. The descending side is
almost entirely orbit 7; the ascending side is dominated by orbits 29 and 102.

The raw ascending count is misleading. Orbit 29 has 659 items / 422 dates, but its AOI footprint
coverage has a median of only **79 %** and a minimum of 4.6 %: most acquisitions are adjacent
25-second frames that clip the AOI. Only 179 dates cover the whole AOI, and those dates have
**no coverage at all in 2022, 2023 and 2024** (the 1 212-day maximum gap runs from 2021-12-11 to
2025-04-06). It is not usable as a consistent time series for this AOI.

**Recommendation: orbit 7 descending.** It has the most full-AOI dates (434), the fewest long
gaps (one 36-day gap, 2024-01-23 → 2024-02-28), exactly one RTC frame per date (no
frame-boundary duplicates), and a 04:29–04:31 UTC morning overpass (~06:30 local time).
Platform mix: S1A 252, S1B 121, S1C 47, S1D 14 acquisitions.

Orbit 102 ascending (426 dates, 16:23–16:25 UTC, ~18:25 local) is a valid second choice, but it
has eight gaps >20 days, including a 36-day gap in late 2024. It is useful as an independent
geometry check, not as the primary series.

### 1.3 Full-AOI dates per year (S1)

| Year | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 | Total |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **orbit 7 desc** | 59 | 60 | 61 | 60 | 30 | 31 | 28 | 53 | 52 | **434** |
| orbit 102 asc | 58 | 60 | 61 | 59 | 30 | 28 | 26 | 52 | 52 | **426** |
| orbit 29 asc (full only) | 30 | 30 | 30 | 28 | 0 | 0 | 0 | 22 | 39 | **179** |

Cadence history: 6-day repeat through 2021 (S1A + S1B), 12-day from 2022 to 2024 after the S1B
failure in December 2021, and 6-day again from 2025 with S1C/S1D. This is a real change in the
sampling rate, not a STAC artefact.

### 1.4 The CRS trap: EPSG:32634 is not universal

The brief said RTC items are EPSG:32634. The actual archive is mixed:

| CRS | Items | Share |
|---|---:|---:|
| `EPSG:32635` (UTM 35N) | 1 019 | 67 % |
| `EPSG:32634` (UTM 34N) | 501 | 33 % |

For orbit 7 alone it is **360 items EPSG:32635 vs 74 items EPSG:32634**. The CRS changes by date
because the RTC tiling scheme assigns the product to the UTM zone of the tile, and this AOI sits
near the 24 °E boundary where both zone-34 and zone-35 tiles cover it. The three probe dates
demonstrate the problem directly:

| Probe date | Item | Item CRS |
|---|---|---|
| 2024-01-23 | `S1A_IW_GRDH_1SDV_20240123T043104_…_rtc` | EPSG:32635 |
| 2024-04-04 | `S1A_IW_GRDH_1SDV_20240404T043105_…_rtc` | EPSG:32634 |
| 2024-08-14 | `S1A_IW_GRDH_1SDV_20240814T043102_…_rtc` | EPSG:32635 |

Hard-coding `transform_bounds(..., 'EPSG:32634')` and then reading a 32635 raster places the
window in the wrong location (or outside the raster). **Always read `item.properties["proj:code"]`
and transform the AOI to that CRS**, or simply use `src.crs` from the opened COG.

A second geometry subtlety: the analysis grid is snapped outward by up to 20 m (one 20 m cell).
When reprojecting a 32635 source into the 32634 grid, the zone rotation over the 5.5 km AOI causes
a corner overhang of ~150 m. Reading only the exact AOI envelope leaves triangular edge nodata.
The probe generator therefore pads the source window by 25 pixels (250 m) before reprojection;
the resulting 20 m products have zero nodata.

### 1.5 Value handling and measured dB ranges

DB conversion from linear power:

```python
valid = (power != -32768) & (power > 0)
db = 10.0 * np.log10(np.where(valid, power, np.nan))
```

Do not average dB values when resampling; average **linear power** first, then convert the
average to dB. Averaging dB biases the result low.

Probe results (native 10 m windows, AOI only; percentiles over all valid pixels):

| Date | Season | Item CRS | VV p5 / p50 / p95 (dB) | VH p5 / p50 / p95 (dB) | VV p1 / p99 (dB) | Nodata |
|---|---|---|---:|---:|---:|---:|
| 2024-01-23 | winter | 32635 | −14.17 / **−9.82** / −4.50 | −21.54 / **−17.87** / −13.01 | −15.97 / +0.96 | 0 % |
| 2024-04-04 | spring | 32634 | −17.31 / **−12.65** / −5.47 | −22.71 / **−18.93** / −12.30 | −19.07 / +1.11 | 0 % |
| 2024-08-14 | dry summer | 32635 | −16.05 / **−11.43** / −4.85 | −22.24 / **−17.52** / −11.85 | −17.85 / +1.35 | 0 % |

Full valid-pixel extremes across the three dates: VV **−25.35 … +25.89 dB**, VH
**−30.36 … +15.17 dB**. The high tail (positive dB) comes from buildings, metal roofs and
steep/urban scatterers in the AOI; use percentiles (p1–p99) rather than min/max for
normalisation. The seasonal medians behave as expected for C-band over cropland: winter VV is
brightest (wet soil/rough surface, −9.8 dB), spring is darkest (smooth young crops, −12.6 dB),
and summer is intermediate (−11.4 dB).

Nodata handling: source nodata `-32768`, plus `power <= 0` treated as invalid. Outputs use
`-9999` as nodata. Native 10 m probes contain **0 % nodata**; all 20 m grid products also contain
0 % nodata after the padded reprojection.

### 1.6 S1 probe files

| File | Content |
|---|---|
| `data/raw/probe/s1_20240123_vv_vh_db_10m.tif` | native 10 m, 2 bands VV/VH dB, EPSG:32635 |
| `data/raw/probe/s1_20240404_vv_vh_db_10m.tif` | native 10 m, 2 bands VV/VH dB, EPSG:32634 |
| `data/raw/probe/s1_20240814_vv_vh_db_10m.tif` | native 10 m, 2 bands VV/VH dB, EPSG:32635 |
| `data/raw/probe/s1_*_vv_vh_db_20m.tif` | 20 m analysis grid, 277 × 314, EPSG:32634, average power → dB |
| `data/raw/probe/s1_*_vv_db_10m.png` | VV quicklook, 2–98 % stretch |

---

## 2. Sentinel-2 L2A

### 2.1 Collection, assets and grids

| Item | Value |
|---|---|
| STAC | `https://earth-search.aws.element84.com/v1` |
| Collection | `sentinel-2-l2a` |
| Tile | single MGRS tile **34TGN** (all 919 items) |
| CRS | **EPSG:32634** for all items |
| Asset keys used | `nir08` (B8A, 20 m), `swir16` (B11, 20 m), `scl` (20 m), `red`, `green`, `blue`, `nir` (B08, 10 m), `swir22` (B12, 20 m), `visual` |
| Other assets | `coastal`, `rededge1/2/3`, `aot`, `wvp`, `nir09`, `cloud`, `snow`, plus `-jp2` variants and metadata |
| SWIR resolution | **20 m**, not 10 m |
| Nodata | `0` in all reflectance and SCL assets |

All 919 items are in the same tile and the same 20 m UTM lattice. For the probe date the native
20 m window was **exactly** the analysis grid — same transform `[20, 0, 711020, 0, -20, 4727000]`
and same 277 × 314 shape — so NDMI needs no resampling at all. This holds for the whole tile.

Practical API note: `limit=1000` caused an HTTP 500 on Earth Search during the audit; `limit=100`
(or paging via the default) works. Counts were collected with `limit=100`.

### 2.2 Counts, 2018-01-01 … 2026-11-15

Items are STAC items; dates are unique acquisition dates. There are more items than dates because
the same satellite sometimes has two datatakes over the tile on one date (item IDs ending `_0_`
and `_1_`, a few minutes apart), not because of different satellites.

| Year | All items | All dates | `<30 %` items | `<30 %` dates | `<60 %` items | `<60 %` dates |
|---|---:|---:|---:|---:|---:|---:|
| 2018 | 79 | 56 | 34 | 25 | 49 | 35 |
| 2019 | 130 | 73 | 61 | 34 | 83 | 45 |
| 2020 | 146 | 72 | 70 | 36 | 84 | 42 |
| 2021 | 154 | 73 | 62 | 32 | 81 | 40 |
| 2022 | 73 | 72 | 25 | 25 | 44 | 44 |
| 2023 | 73 | 73 | 29 | 29 | 44 | 44 |
| 2024 | 75 | 72 | 32 | 30 | 49 | 46 |
| 2025 | 99 | 99 | 37 | 37 | 51 | 51 |
| 2026 | 90 | 89 | 44 | 43 | 52 | 51 |
| **Total** | **919** | **679** | **394** | **291** | **537** | **398** |

### 2.3 Ten clearest dry-season dates per year (June–September)

Selected from all scenes with `eo:cloud_cover < 60`, deduplicated by date (the lowest-cloud item
is kept when two datatakes share a date), sorted by cloud cover. Values are `eo:cloud_cover` in
percent. These are **tile-level** cloud percentages; the AOI must still be masked with SCL.

| Year | Ten clearest dates (cloud %) | Scenes `<30` | Scenes `<60` | Unique dates `<60` |
|---|---|---|---:|---:|
| 2018 | 06-08 (1.9), 09-01 (3.4), 08-07 (7.2), 07-03 (10.9), 06-13 (13.7), 08-02 (14.9), 08-22 (14.9), 09-16 (17.1), 08-17 (18.2), 07-13 (23.7) | 21 | 31 | 18 |
| 2019 | 08-12 (0.0), 09-01 (0.0), 08-07 (0.01), 07-03 (0.1), 08-27 (0.5), 07-28 (0.7), 09-16 (1.2), 09-21 (1.5), 08-22 (3.0), 06-13 (4.4) | 35 | 47 | 24 |
| 2020 | 08-31 (0.0), 09-05 (0.1), 09-20 (1.2), 06-27 (1.8), 07-02 (5.6), 09-10 (5.9), 09-25 (9.2), 08-26 (9.5), 08-11 (11.0), 07-12 (11.5) | 31 | 39 | 20 |
| 2021 | 08-16 (0.0), 07-27 (0.1), 08-01 (1.8), 07-17 (3.2), 07-12 (4.5), 09-25 (4.7), 08-31 (5.9), 06-27 (6.1), 06-22 (9.3), 08-11 (9.9) | 31 | 37 | 19 |
| 2022 | 07-22 (0.2), 07-27 (2.1), 09-30 (2.2), 07-17 (3.5), 08-16 (9.7), 06-02 (11.3), 07-02 (12.2), 06-17 (18.4), 06-27 (31.5), 08-01 (32.3) | 8 | 21 | 21 |
| 2023 | 07-22 (0.02), 07-12 (0.1), 09-30 (4.1), 08-01 (4.5), 08-21 (7.9), 09-20 (9.3), 07-17 (11.0), 06-22 (13.4), 08-26 (15.0), 09-10 (21.9) | 11 | 18 | 18 |
| 2024 | 08-15 (0.3), 07-01 (0.5), 06-11 (1.1), 08-25 (1.5), 07-31 (2.3), 06-16 (5.1), 07-06 (5.6), 07-21 (7.4), 07-16 (9.3), 07-11 (11.5) | 16 | 22 | 22 |
| 2025 | 08-30 (0.0), 08-10 (0.0), 09-16 (0.0), 09-19 (0.0), 08-27 (0.01), 07-26 (0.04), 07-08 (0.9), 06-08 (1.0), 06-26 (1.1), 06-16 (2.8) | 22 | 30 | 30 |
| 2026 | 09-09 (0.0), 07-26 (0.03), 08-20 (0.03), 09-11 (0.1), 07-31 (0.2), 08-02 (0.3), 08-12 (0.3), 07-11 (1.4), 08-15 (2.3), 08-22 (2.5) | 25 | 31 | 30 |

2022 is the weakest dry season: only 8 scenes have tile cloud < 30 %, so the 9th and 10th entries
in that row exceed 30 %. 2018 is also comparatively weak. 2025 and 2026 are the strongest.

### 2.4 BOA offset: mandatory and per-item

Sentinel-2 L2A processing baseline 04.00 (25 January 2022) introduced a **−1000 DN offset** so
that negative surface reflectances could be encoded in unsigned 16-bit data:

```
reflectance = DN * 0.0001 + offset
offset = -0.1   # baseline >= 04.00, i.e. DN 1000 == reflectance 0.0
offset =  0.0   # baseline < 04.00
```

The archive is **not uniform**, so the offset must be read per item:

| Baselines | Items | Offset in `raster:bands` |
|---|---:|---|
| 04.00, 05.00, 05.09, 05.10, 05.11, 05.12, 05.13 | **639** | **−0.1** |
| 00.01, 02.07–02.14, 03.00, 03.01 | **280** | **0.0** |

Critical detail: `earthsearch:boa_offset_applied` **disagrees with the asset metadata for 16
modern items** (7 items with baseline 04.00 from Jan–Feb 2022, and 9 items with baseline 05.10 /
05.11 from 2025). Those items are flagged `false` but their `raster:bands` offset is still
`-0.1`. Trust the per-asset `raster:bands` offset, not the flag:

```python
rb = item.assets["nir08"].extra_fields["raster:bands"][0]
scale, offset = rb["scale"], rb["offset"]   # 0.0001, -0.1 or 0.0
```

Applying −0.1 to a pre-04.00 item lowers every reflectance by 0.1 and biases NDMI; skipping it
on a 05.x item has the opposite effect. For a multi-year NDMI series, branch per item.

### 2.5 SCL cloud mask

`SCL` is the Sen2Cor scene-classification layer at 20 m. Classes:

| Value | Class | Use for land NDMI |
|---:|---|---|
| 0 | No data | drop |
| 1 | Saturated / defective | drop |
| 2 | Dark area / cast shadow | drop |
| 3 | Cloud shadow | **drop** |
| 4 | Vegetation | **keep** |
| 5 | Not vegetated | **keep** |
| 6 | Water | drop for land NDMI (keep if water is of interest) |
| 7 | Unclassified | **keep** |
| 8 | Cloud, medium probability | **drop** |
| 9 | Cloud, high probability | **drop** |
| 10 | Thin cirrus | **drop** |
| 11 | Snow / ice | **drop** (irrelevant in summer; essential in winter) |

Recommended land mask: `np.isin(scl, [4, 5, 7])`. In the probe, the only classes present were
4, 5 and 7, and **100 % of AOI pixels were clear** even though the tile-level `eo:cloud_cover`
was 0.26 %. That is the point: tile-level cloud cover is not an AOI cloud mask.

### 2.6 NDMI probe

Probe date **2024-08-15**, item `S2B_34TGN_20240815_0_L2A`, baseline 05.11, offset −0.1,
scene cloud 0.26 %, SCL-clear AOI 100 %.

```
NDMI = (B8A − B11) / (B8A + B11)
     = (nir08 − swir16) / (nir08 + swir16)    # both 20 m, same grid
```

Validity mask used: SCL ∈ {4, 5, 6, 7}, both reflectances > 0, and `B8A + B11 > 0.05`.
The denominator guard is necessary: 8 pixels had near-zero denominators that produced
unphysical NDMI values up to 13 before masking. NDMI was clipped to [−1, 1] after masking.

Measured over 86 970 valid AOI pixels:

| Statistic | NDMI |
|---|---:|
| min (clipped) | −1.00 |
| p1 | −0.315 |
| p5 | −0.232 |
| **p50** | **−0.076** |
| p95 | +0.234 |
| p99 | +0.390 |
| max (clipped) | +1.00 |

The dry-summer median of −0.08 is plausible for harvested/dry cropland and bare soil in the
Elin Pelin plain; the positive tail is irrigated/green vegetation. NDMI over this AOI in August
is dominated by land management, not by a single physical process — do not interpret negative
NDMI as a leak signal without a seasonal baseline.

Probe files:

| File | Content |
|---|---|
| `data/raw/probe/s2_ndmi_probe.tif` | native 20 m NDMI, EPSG:32634, 277 × 314, nodata −9999 |
| `data/raw/probe/s2_ndmi_probe_20m.tif` | identical grid-aligned NDMI copy (no resampling needed) |
| `data/raw/probe/s2_scl_probe.tif` | SCL classes, uint8, 20 m |
| `data/raw/probe/s2_ndmi_probe.png` | NDMI quicklook, fixed −0.5 … +0.5 colour scale |

### 2.7 S2 notes and caveats

- Earth Search also exposes a `sentinel-2-c1-l2a` collection (566 items over this AOI,
  2018-03-20 … 2026-11-13, baseline 05.13, offset −0.1). It is a newer reprocessing and is a
  reasonable future alternative, but this audit uses the requested `sentinel-2-l2a`.
- The 20 m SWIR bands and 10 m visible/NIR bands are on different grids within the same tile.
  For NDMI use `nir08` + `swir16`, both 20 m, and stay on one grid. If you need 10 m NDMI, read
  `nir` (B08, 10 m) and resample `swir16` to 10 m — but do not mix the 10 m and 20 m grids
  implicitly.
- `eo:cloud_cover` is tile-level. Use SCL, and optionally also drop SCL 6 (water) and 11 (snow)
  depending on the target.
- Some dates have two items from the same satellite (`_0_` / `_1_` datatakes) with different tile
  cloud cover. Deduplicate by date before building a time series, keeping the lower-cloud item or,
  better, mosaicking.

---

## 3. Landsat Collection 2 Level-2

### 3.1 Collection, assets and the access blocker

| Item | Value |
|---|---|
| STAC metadata | `https://earth-search.aws.element84.com/v1` |
| Collection | `landsat-c2-l2` |
| Pixel mirror used | `https://planetarycomputer.microsoft.com/api/stac/v1`, collection `landsat-c2-l2` |
| Sensors in window | Landsat 8 OLI/TIRS, Landsat 9 OLI-2/TIRS-2, Landsat 7 ETM+ |
| Asset keys | `lwir11` (ST_B10), `qa_pixel`, `emis` (ST_EMIS), `red` (SR_B4), `nir08` (SR_B5), `swir16` (SR_B6), `swir22` (SR_B7), `trad`, `qa_radsat`, `qa_aerosol`, `ang` |
| Thermal resolution | **100 m native, resampled to 30 m** in the C2 L2 product |
| Reflective resolution | 30 m |
| Nodata | ST_B10 `0`; QA_PIXEL `1`; ST_EMIS `-9999` |

**Asset-name correction:** Landsat C2 L2 uses `nir08` for band 5 (SR_B5), not `nir`; there is no
`nir` asset in this collection. The task brief listed `nir`; the actual key is `nir08`.

**Access blocker (measured):** Earth Search Landsat asset hrefs point at
`s3://usgs-landsat/collection02/...`. That bucket is **requester pays**. Anonymous reads fail:

```
CPLE_AWSInvalidCredentialsError: InvalidCredentials: No valid AWS credentials found
# with AWS_NO_SIGN_REQUEST=YES:
CPLE_AWSAccessDeniedError: AccessDenied: Anonymous users cannot invoke requests against
Requester Pays buckets. Please authenticate.
```

Setting `AWS_NO_SIGN_REQUEST=YES` is not enough. Metadata search and counting work anonymously;
pixel reads require AWS credentials and `--request-payer requester`. For the probe, the **same
USGS scene** was read from the Planetary Computer mirror
(`LC09_L2SP_184030_20240801_02_T1`), whose SAS-signed COGs are public. The scene ID, asset names,
scales and QA bits are identical.

### 3.2 Counts, 2018-01-01 … 2026-11-15

| Set | Items | Unique dates | Scenes with 100 % AOI coverage | Unique full-AOI dates |
|---|---:|---:|---:|---:|
| All Landsat C2 L2 | 1 303 | 845 | 840 | 624 |
| `eo:cloud_cover < 30` | 620 | 423 | 385 | 295 |
| `eo:cloud_cover < 30`, Landsat 8/9 only | **448** | **318** | **216** | **185** |
| `eo:cloud_cover < 30`, Landsat 7 only | 172 | 118 | 169 | 117 |

Platform split at cloud <30 %: Landsat 8 **286**, Landsat 9 **162**, Landsat 7 **172**.
Landsat 7 is excluded from the recommendation: it has scan-line gaps and a 60 m native thermal
band, and its archive ends in 2023.

Landsat 8/9, cloud <30 %, per year:

| Year | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Items | 33 | 33 | 34 | 33 | 72 | 41 | 65 | 77 | 60 |
| Unique dates | 22 | 23 | 25 | 25 | 51 | 31 | 45 | 54 | 42 |
| Full-AOI scenes | 14 | 10 | 10 | 15 | 34 | 22 | 42 | 38 | 31 |
| Full-AOI unique dates | 12 | 10 | 10 | 14 | 29 | 19 | 32 | 33 | 26 |

The 2022 jump is Landsat 9 becoming operational. The small AOI straddles WRS-2 path/row
boundaries: only 216 of 448 clear L8/9 scenes cover 100 % of it. Two scenes from adjacent rows
are often needed on the same date if mosaicking the full AOI. This is why the **unique full-AOI
date count (185)** is much lower than the raw item count.

Scene projections at cloud <30 %:

| WRS-2 path/row | Projection | Items |
|---|---|---:|
| 183 / 031 | EPSG:32635 | 220 |
| 183 / 030 | EPSG:32635 | 206 |
| 184 / 030 | EPSG:32634 | 194 |

So Landsat has the same zone-boundary issue as S1: path 184 arrives in EPSG:32634, path 183 in
EPSG:32635. Reproject to the common 32634 grid, or read each scene in its own CRS.

### 3.3 QA_PIXEL bits and cloud/shadow mask

`QA_PIXEL` is a uint16 bit index. Bits used here:

| Bit(s) | Meaning | Recommended action |
|---:|---|---|
| 0 | Fill | drop |
| 1 | Dilated cloud | drop |
| 2 | Cirrus | drop |
| 3 | Cloud | **drop** |
| 4 | Cloud shadow | **drop** |
| 5 | Snow | drop |
| 6 | Clear | **require = 1** |
| 7 | Water | optional (keep for land LST, drop for water targets) |
| 8–9 | Cloud confidence (0 not determined, 1 low, 2 medium, 3 high) | drop high confidence |
| 10–11 | Cloud-shadow confidence | drop high confidence |
| 12–13 | Snow confidence | — |
| 14–15 | Cirrus confidence | — |

Recommended mask:

```python
fill    = (qa >> 0) & 1
dilated = (qa >> 1) & 1
cirrus  = (qa >> 2) & 1
cloud   = (qa >> 3) & 1
shadow  = (qa >> 4) & 1
snow    = (qa >> 5) & 1
clear   = (qa >> 6) & 1

good = (clear == 1) & ((qa & 0b111111) == 0)   # bits 0-5 all zero, bit 6 set
```

In the probe the entire AOI had `QA_PIXEL = 21824` (bit 6 set; low confidence in bits 8/10/12/14),
i.e. 100 % clear, and cloud/shadow/snow fractions were all 0 %. The scene-level cloud cover was
0.02 %, so scene metadata and AOI QA agree here — but they will not always.

### 3.4 ST_B10 → Kelvin / Celsius

```
LST_K = DN * 0.00341802 + 149.0
LST_C = LST_K - 273.15
```

These are the exact USGS C2 L2 coefficients (`scale = 0.00341802`, `offset = 149.0`), also present
in `raster:bands`.

**Emissivity:** `ST_B10` is already a **surface-temperature** product; the per-pixel emissivity
from `ST_EMIS` is already incorporated in the retrieval. In the probe, `ST_EMIS` had median
**0.9807** (range 0.9384–0.9971, scale 0.0001). Do **not** apply a second constant-ε = 0.97
correction to `ST_B10`; that would double-count emissivity and introduce a warm bias. For
reference, forcing a uniform ε = 0.97 via the Stefan–Boltzmann ratio
`T97 = Tp * (εp / 0.97)^(1/4)` would raise the median by only ~**0.9 K**, which is smaller than
the 100 m thermal resampling error. If you instead derive temperature from the TOA thermal
radiance asset `trad` (ST_TRAD), then you do need the standard brightness-temperature +
emissivity formula (λ ≈ 10.9 µm, ε ≈ 0.97, K1 = 774.8853, K2 = 1321.0789 for L8/L9 band 10).
For this pipeline, use `ST_B10` directly.

### 3.5 LST probe

Probe date **2024-08-01**, scene `LC09_L2SP_184030_20240801_02_T1`, Landsat 9, WRS-2 184/030,
EPSG:32634, scene cloud 0.02 %, QA-clear 100 % of the AOI.

| Statistic | LST (K) | LST (°C) |
|---|---:|---:|
| min | 305.82 | 32.67 |
| p1 | 308.28 | 35.13 |
| p5 | 309.81 | 36.66 |
| **p50** | **314.24** | **41.09** |
| p95 | 319.74 | 46.59 |
| p99 | 321.53 | 48.38 |
| max | 323.68 | 50.53 |

The median 41 °C and the 35–48 °C central range are typical for a clear early-August late-morning
overpass (09:04 UTC, sun elevation 36°) over dry cropland and bare soil in the Sofia plain.
The 30 m product is a resampling of the 100 m native thermal band, so small fields are smoothed;
do not treat 30 m LST as independent 30 m measurements.

Probe files:

| File | Content |
|---|---|
| `data/raw/probe/landsat_lst_probe.tif` | native 30 m, band 1 LST K, band 2 LST °C, EPSG:32634, nodata −9999 |
| `data/raw/probe/landsat_lst_probe_20m.tif` | LST °C bilinearly resampled to the 20 m analysis grid |
| `data/raw/probe/landsat_qa_probe.tif` | native 30 m `QA_PIXEL`, uint16 |
| `data/raw/probe/landsat_lst_probe.png` | LST °C quicklook, 2–98 % stretch |

---

## 4. Common 20 m analysis grid — cross-check

| Source | Native CRS | Native res | Native grid vs 20 m grid | Resampling to analysis grid | 20 m nodata |
|---|---|---|---:|---|---:|
| Sentinel-1 RTC | EPSG:32634 **or** EPSG:32635 per item | 10 m | different CRS and origin | average **linear power**, then dB; 25 px source padding for zone rotation | 0 % |
| Sentinel-2 L2A | EPSG:32634 | 20 m (nir08/swir16/scl) | **identical** transform and 277 × 314 shape | none for NDMI; bilinear if a different band grid is used | 0 % |
| Landsat C2 L2 | EPSG:32634 (path 184) or EPSG:32635 (path 183) | 30 m (thermal native 100 m) | different CRS/origin | bilinear for LST, nearest for QA | 0 % |

All three 20 m products in `data/raw/probe/` were written on exactly
`[20, 0, 711020, 0, -20, 4727000]`, 277 × 314, EPSG:32634, and were verified to contain **zero
nodata pixels**. The S2 native 20 m grid coinciding exactly with the analysis grid is a useful
simplification: NDMI can be computed directly on the analysis grid with an integer window offset
and no resampling.

Recommended resampling rules for the pipeline:

- **S1:** resample gamma0 **linear power** with `Resampling.average`, then convert to dB. Never
  average dB. For a 10 m → 20 m reduction, average is also a mild speckle filter.
- **S2:** NDMI is a ratio; compute it at native 20 m first, then resample the index bilinearly
  only if a different grid is required. SCL must use `Resampling.nearest`.
- **Landsat:** LST is a physical quantity; bilinear is acceptable for a continuous field. QA
  must use nearest. The native thermal support is 100 m, so 20 m is oversampling, not new
  information.

---

## 5. Reproducible code

### 5.1 Analysis grid

```python
import math
import rasterio
from rasterio.transform import from_origin
from rasterio.warp import transform_bounds

W, S, E, N = 23.575, 42.610, 23.640, 42.665

xmin, ymin, xmax, ymax = transform_bounds("EPSG:4326", "EPSG:32634", W, S, E, N)
gx  = 20 * math.floor(xmin / 20)
gy  = 20 * math.floor(ymin / 20)
gx2 = 20 * math.ceil(xmax / 20)
gy2 = 20 * math.ceil(ymax / 20)
transform = from_origin(gx, gy2, 20, 20)
width  = int((gx2 - gx) // 20)   # 277
height = int((gy2 - gy) // 20)   # 314
# transform = [20, 0, 711020, 0, -20, 4727000], CRS EPSG:32634
```

### 5.2 Sentinel-1 RTC search and per-item-CRS read

```python
import math
import numpy as np
import planetary_computer as pc
import rasterio
from pystac_client import Client
from rasterio.windows import Window, from_bounds
from rasterio.warp import transform_bounds

catalog = Client.open(
    "https://planetarycomputer.microsoft.com/api/stac/v1",
    modifier=pc.sign_inplace,
)
items = list(catalog.search(
    collections=["sentinel-1-rtc"],
    bbox=[23.575, 42.610, 23.640, 42.665],
    datetime="2018-01-01/2026-11-15",
    limit=1000,
).items())

# orbit 7 = best; 102 = runner-up
items = [i for i in items if i.properties["sat:relative_orbit"] == 7]
item = items[0]

def aoi_window(src, pad=0):
    b = transform_bounds("EPSG:4326", src.crs, 23.575, 42.610, 23.640, 42.665)
    w = from_bounds(*b, transform=src.transform)
    c0, r0 = math.floor(w.col_off) - pad, math.floor(w.row_off) - pad
    c1 = math.ceil(w.col_off + w.width) + pad
    r1 = math.ceil(w.row_off + w.height) + pad
    c0, r0 = max(c0, 0), max(r0, 0)
    c1, r1 = min(c1, src.width), min(r1, src.height)
    return Window(c0, r0, c1 - c0, r1 - r0)

with rasterio.open(item.assets["vv"].href) as src:
    # NEVER hard-code 32634: use the item's own CRS
    win = aoi_window(src)
    power = src.read(1, window=win).astype("float64")
    valid = (power != src.nodata) & (power > 0)
    db = 10.0 * np.log10(np.where(valid, power, np.nan))
```

For the 20 m grid, read with `pad=25`, average linear power with
`rasterio.warp.reproject(..., resampling=Resampling.average)`, then take `10*log10`.

### 5.3 Sentinel-2 search, offset, SCL mask, NDMI

```python
import numpy as np
import rasterio
from pystac_client import Client

catalog = Client.open("https://earth-search.aws.element84.com/v1")
items = list(catalog.search(
    collections=["sentinel-2-l2a"],
    bbox=[23.575, 42.610, 23.640, 42.665],
    datetime="2018-01-01/2026-11-15",
    query={"eo:cloud_cover": {"lt": 30}},
    limit=100,            # limit=1000 returned HTTP 500 during the audit
).items())

item = items[0]
rb = item.assets["nir08"].extra_fields["raster:bands"][0]
scale, offset = rb["scale"], rb["offset"]     # 0.0001, -0.1 or 0.0

# read windows on the common 20 m grid, then:
b8a  = nir_dn  * scale + offset
b11  = swir_dn * scale + offset
den  = b8a + b11
ndmi = (b8a - b11) / den
valid = np.isin(scl, [4, 5, 7]) & (nir_dn > 0) & (swir_dn > 0) & (den > 0.05)
ndmi = np.where(valid, np.clip(ndmi, -1, 1), np.nan)
```

### 5.4 Landsat search (Earth Search) and pixel read (Planetary Computer)

```python
import numpy as np
import planetary_computer as pc
import rasterio
from pystac_client import Client

# counts / metadata: Earth Search (anonymous search is fine)
es = Client.open("https://earth-search.aws.element84.com/v1")
meta = list(es.search(
    collections=["landsat-c2-l2"],
    bbox=[23.575, 42.610, 23.640, 42.665],
    datetime="2018-01-01/2026-11-15",
    query={"eo:cloud_cover": {"lt": 30}},
    limit=100,
).items())

# pixel reads: Planetary Computer mirror of the same USGS scene
pcc = Client.open(
    "https://planetarycomputer.microsoft.com/api/stac/v1",
    modifier=pc.sign_inplace,
)
item = [i for i in pcc.search(
    collections=["landsat-c2-l2"],
    bbox=[23.575, 42.610, 23.640, 42.665],
    datetime="2024-08-01/2024-08-02",
    limit=20,
).items() if i.id.startswith("LC09_L2SP_184030_20240801")][0]

with rasterio.open(item.assets["lwir11"].href) as src:
    # reuse aoi_window() from 5.2 for exact coverage; ST_B10 and QA_PIXEL share this 30 m grid
    win = aoi_window(src)
    dn = src.read(1, window=win)
    lst_k = dn * 0.00341802 + 149.0
    lst_c = lst_k - 273.15

with rasterio.open(item.assets["qa_pixel"].href) as src:
    qa = src.read(1, window=win)

good = (((qa >> 6) & 1) == 1) & ((qa & 0b111111) == 0)
lst_c = np.where(good, lst_c, np.nan)
```

### 5.5 Reproducing the counts

The counts in this report were produced with `pystac_client` searches identical to the snippets
above, iterating all returned items (automatic paging) and grouping by
`datetime.year`, `sat:relative_orbit`, `sat:orbit_state`, `eo:cloud_cover`, and by the AOI
footprint intersection:

```python
from shapely.geometry import shape, box
aoi = box(23.575, 42.610, 23.640, 42.665)
full = shape(item.geometry).intersection(aoi).area / aoi.area >= 0.999
```

The S1 orbit ranking in this report uses `full`, not the STAC bbox hit. That distinction is what
disqualifies relative orbit 29.

---

## 6. Caveats and recommended settings

### 6.1 Sentinel-1 RTC

- **C-band gamma0**, not NISAR L-band. The NISAR mission is young; this audit uses S1 RTC as the
  available proxy. Do not describe C-band results as NISAR results.
- RTC is terrain-corrected but still affected by **speckle**, incidence-angle variation across
  the swath, and layover/shadow in steep terrain. There is no local-incidence-angle asset in the
  PC RTC item; the incidence angle varies between tracks and dates. For a leak-detection model,
  normalise by a temporal baseline or by VV/VH ratio rather than raw dB.
- The AOI has no large water body, so the 0 % nodata result is expected. Do not assume 0 %
  nodata for larger AOIs; always mask `-32768` and `<= 0`.
- **Item CRS varies by date** (32634 vs 32635). This is the single most likely source of silent
  wrong-window bugs. Read `proj:code` / `src.crs` per item.
- **Orbit 29 is a trap**: it has the most items but only 179 full-AOI dates and a three-year hole
  in full-AOI coverage (2022–2024). Orbit 7 is the consistent record.
- Temporal sampling is not uniform: 6-day (2018–2021), 12-day (2022–2024), 6-day (2025–2026).
  A model trained across 2022–2024 sees half the sampling rate of 2018–2021.
- The 36-day gap 2024-01-23 → 2024-02-28 is the longest gap in orbit 7; account for it in
  lag/seasonal features.

### 6.2 Sentinel-2 L2A

- **BOA offset is per item.** 639 items need −0.1; 280 items need 0.0. The
  `earthsearch:boa_offset_applied` flag is wrong for 16 modern items; use `raster:bands`.
- **Use SCL, not `eo:cloud_cover`**, for AOI masking. Tile cloud cover can be 0.3 % while the AOI
  is 100 % clear, or vice versa.
- SWIR is 20 m; visible/NIR are 10 m. Keep each index on one grid.
- The archive has duplicate dates (S2A + S2B). Deduplicate or mosaic before temporal analysis.
- The 2018 archive is weak (25 dates with tile cloud <30 % for the whole year, 18 dry-season
  dates with <60 %), and 2022 is the weakest dry season (8 scenes <30 % in Jun–Sep). Expect gaps
  in a 2018–2026 NDMI series.
- The `sentinel-2-c1-l2a` collection is a newer reprocessing and a reasonable future migration,
  but it was not used here.

### 6.3 Landsat C2 L2

- **Requester-pays blocker:** Earth Search metadata is free, pixels are not. Either configure AWS
  credentials + requester-pays, or read the same scenes from the Planetary Computer mirror. The
  probe used the mirror.
- **Thermal is 100 m native, resampled to 30 m.** Treat LST as a 100 m product. The 20 m grid is
  oversampling.
- **ST_B10 is already surface temperature** with per-pixel emissivity. Do not apply a second
  ε = 0.97 correction. If using `trad` (TOA radiance), then apply the brightness-temperature and
  emissivity formula.
- **Mixed projections:** path 184 → EPSG:32634, path 183 → EPSG:32635. Reproject per scene.
- **Small-AOI coverage:** only 216 of 448 clear L8/9 scenes cover 100 % of the AOI; 185 unique
  full-AOI dates. Mosaic adjacent rows or accept partial coverage.
- **Exclude Landsat 7** for thermal work: scan-line gaps and 60 m native thermal.
- Scene-level cloud cover is not an AOI mask. Always apply `QA_PIXEL` bits 0–6.

### 6.4 Nodata summary

| Source | Source nodata | Invalid values | Probe output nodata |
|---|---|---|---|
| S1 RTC | −32768 | `<= 0` power | −9999 |
| S2 L2A reflectance | 0 | `DN <= 0` | −9999 |
| S2 SCL | 0 | class 0 | 0 |
| Landsat ST_B10 | 0 | `DN == 0` | −9999 |
| Landsat QA_PIXEL | 1 | fill bit / `== 1` | 1 |
| Landsat ST_EMIS | −9999 | `== -9999` | −9999 |

### 6.5 What was not audited

- NISAR data itself (no NISAR collection was queried).
- Sentinel-1 GRD (non-RTC) or InSAR/coherence products.
- Sentinel-2 L1C.
- Landsat Collection 2 Level-1 or surface-reflectance-only products.
- Atmospheric correction / BRDF normalisation across sensors.
- A full time-series extraction and gap statistics for S2/Landsat (only availability counts and
  one probe date each).

---

## Appendix A — all Sentinel-1 acquisition dates, best two orbits

One RTC item per date; every date listed for both orbits covers 100 % of the AOI.

<details>
<summary><b>Relative orbit 7, descending (recommended) — 434 dates</b></summary>

**2018 (59)** — 2018-01-06, 2018-01-12, 2018-01-18, 2018-01-24, 2018-01-30, 2018-02-05, 2018-02-11, 2018-02-17, 2018-02-23, 2018-03-01, 2018-03-07, 2018-03-13, 2018-03-19, 2018-03-25, 2018-03-31, 2018-04-06, 2018-04-12, 2018-04-18, 2018-04-24, 2018-04-30, 2018-05-06, 2018-05-12, 2018-05-18, 2018-05-24, 2018-05-30, 2018-06-05, 2018-06-17, 2018-06-23, 2018-06-29, 2018-07-05, 2018-07-11, 2018-07-17, 2018-07-23, 2018-07-29, 2018-08-04, 2018-08-10, 2018-08-16, 2018-08-22, 2018-08-28, 2018-09-03, 2018-09-09, 2018-09-15, 2018-09-21, 2018-09-27, 2018-10-03, 2018-10-09, 2018-10-15, 2018-10-21, 2018-10-27, 2018-11-02, 2018-11-08, 2018-11-14, 2018-11-20, 2018-11-26, 2018-12-02, 2018-12-08, 2018-12-14, 2018-12-20, 2018-12-26

**2019 (60)** — 2019-01-01, 2019-01-07, 2019-01-13, 2019-01-19, 2019-01-25, 2019-01-31, 2019-02-06, 2019-02-12, 2019-02-18, 2019-02-24, 2019-03-02, 2019-03-08, 2019-03-14, 2019-03-20, 2019-03-26, 2019-04-01, 2019-04-07, 2019-04-13, 2019-04-19, 2019-04-25, 2019-05-01, 2019-05-07, 2019-05-13, 2019-05-19, 2019-05-31, 2019-06-06, 2019-06-12, 2019-06-18, 2019-06-24, 2019-06-30, 2019-07-06, 2019-07-12, 2019-07-18, 2019-07-24, 2019-07-30, 2019-08-05, 2019-08-11, 2019-08-17, 2019-08-23, 2019-08-29, 2019-09-04, 2019-09-10, 2019-09-16, 2019-09-22, 2019-09-28, 2019-10-04, 2019-10-10, 2019-10-16, 2019-10-22, 2019-10-28, 2019-11-03, 2019-11-09, 2019-11-15, 2019-11-21, 2019-11-27, 2019-12-03, 2019-12-09, 2019-12-15, 2019-12-21, 2019-12-27

**2020 (61)** — 2020-01-02, 2020-01-08, 2020-01-14, 2020-01-20, 2020-01-26, 2020-02-01, 2020-02-07, 2020-02-13, 2020-02-19, 2020-02-25, 2020-03-02, 2020-03-08, 2020-03-14, 2020-03-20, 2020-03-26, 2020-04-01, 2020-04-07, 2020-04-13, 2020-04-19, 2020-04-25, 2020-05-01, 2020-05-07, 2020-05-13, 2020-05-19, 2020-05-25, 2020-05-31, 2020-06-06, 2020-06-12, 2020-06-18, 2020-06-24, 2020-06-30, 2020-07-06, 2020-07-12, 2020-07-18, 2020-07-24, 2020-07-30, 2020-08-05, 2020-08-11, 2020-08-17, 2020-08-23, 2020-08-29, 2020-09-04, 2020-09-10, 2020-09-16, 2020-09-22, 2020-09-28, 2020-10-04, 2020-10-10, 2020-10-16, 2020-10-22, 2020-10-28, 2020-11-03, 2020-11-09, 2020-11-15, 2020-11-21, 2020-11-27, 2020-12-03, 2020-12-09, 2020-12-15, 2020-12-21, 2020-12-27

**2021 (60)** — 2021-01-02, 2021-01-08, 2021-01-14, 2021-01-20, 2021-01-26, 2021-02-01, 2021-02-07, 2021-02-13, 2021-02-19, 2021-02-25, 2021-03-03, 2021-03-09, 2021-03-15, 2021-03-21, 2021-03-27, 2021-04-02, 2021-04-08, 2021-04-14, 2021-04-20, 2021-04-26, 2021-05-02, 2021-05-08, 2021-05-14, 2021-05-20, 2021-05-26, 2021-06-01, 2021-06-07, 2021-06-13, 2021-06-25, 2021-07-01, 2021-07-07, 2021-07-13, 2021-07-19, 2021-07-25, 2021-07-31, 2021-08-06, 2021-08-12, 2021-08-18, 2021-08-24, 2021-08-30, 2021-09-05, 2021-09-11, 2021-09-17, 2021-09-23, 2021-09-29, 2021-10-05, 2021-10-11, 2021-10-17, 2021-10-23, 2021-10-29, 2021-11-04, 2021-11-10, 2021-11-16, 2021-11-22, 2021-11-28, 2021-12-04, 2021-12-10, 2021-12-16, 2021-12-22, 2021-12-28

**2022 (30)** — 2022-01-09, 2022-01-21, 2022-02-02, 2022-02-14, 2022-02-26, 2022-03-10, 2022-03-22, 2022-04-03, 2022-04-15, 2022-04-27, 2022-05-09, 2022-05-21, 2022-06-02, 2022-06-14, 2022-06-26, 2022-07-08, 2022-07-20, 2022-08-01, 2022-08-13, 2022-08-25, 2022-09-06, 2022-09-18, 2022-09-30, 2022-10-12, 2022-10-24, 2022-11-05, 2022-11-17, 2022-11-29, 2022-12-11, 2022-12-23

**2023 (31)** — 2023-01-04, 2023-01-16, 2023-01-28, 2023-02-09, 2023-02-21, 2023-03-05, 2023-03-17, 2023-03-29, 2023-04-10, 2023-04-22, 2023-05-04, 2023-05-16, 2023-05-28, 2023-06-09, 2023-06-21, 2023-07-03, 2023-07-15, 2023-07-27, 2023-08-08, 2023-08-20, 2023-09-01, 2023-09-13, 2023-09-25, 2023-10-07, 2023-10-19, 2023-10-31, 2023-11-12, 2023-11-24, 2023-12-06, 2023-12-18, 2023-12-30

**2024 (28)** — 2024-01-11, 2024-01-23, 2024-02-28, 2024-03-11, 2024-03-23, 2024-04-04, 2024-04-16, 2024-04-28, 2024-05-10, 2024-05-22, 2024-06-03, 2024-06-15, 2024-06-27, 2024-07-09, 2024-07-21, 2024-08-02, 2024-08-14, 2024-08-26, 2024-09-07, 2024-09-19, 2024-10-01, 2024-10-13, 2024-10-25, 2024-11-06, 2024-11-18, 2024-11-30, 2024-12-12, 2024-12-24

**2025 (53)** — 2025-01-05, 2025-01-17, 2025-01-29, 2025-02-10, 2025-02-22, 2025-03-06, 2025-03-18, 2025-03-30, 2025-04-05, 2025-04-11, 2025-04-17, 2025-04-23, 2025-04-29, 2025-05-05, 2025-05-11, 2025-05-17, 2025-05-23, 2025-05-29, 2025-06-04, 2025-06-10, 2025-06-16, 2025-06-22, 2025-06-28, 2025-07-04, 2025-07-16, 2025-07-22, 2025-07-28, 2025-08-03, 2025-08-09, 2025-08-15, 2025-08-21, 2025-08-27, 2025-09-02, 2025-09-08, 2025-09-14, 2025-09-20, 2025-09-26, 2025-10-02, 2025-10-08, 2025-10-14, 2025-10-20, 2025-10-26, 2025-11-01, 2025-11-07, 2025-11-13, 2025-11-19, 2025-11-25, 2025-12-01, 2025-12-07, 2025-12-13, 2025-12-19, 2025-12-25, 2025-12-31

**2026 (52)** — 2026-01-06, 2026-01-12, 2026-01-18, 2026-01-24, 2026-01-30, 2026-02-05, 2026-02-11, 2026-02-23, 2026-03-01, 2026-03-07, 2026-03-13, 2026-03-19, 2026-03-25, 2026-03-31, 2026-04-06, 2026-04-12, 2026-04-18, 2026-04-24, 2026-04-30, 2026-05-06, 2026-05-12, 2026-05-18, 2026-05-19, 2026-05-24, 2026-05-30, 2026-05-31, 2026-06-17, 2026-06-24, 2026-06-29, 2026-06-30, 2026-07-06, 2026-07-12, 2026-07-18, 2026-07-24, 2026-07-30, 2026-08-05, 2026-08-11, 2026-08-17, 2026-08-23, 2026-08-29, 2026-09-04, 2026-09-10, 2026-09-16, 2026-09-22, 2026-09-28, 2026-10-04, 2026-10-10, 2026-10-16, 2026-10-22, 2026-10-28, 2026-11-03, 2026-11-09

</details>

<details>
<summary><b>Relative orbit 102, ascending (runner-up) — 426 dates</b></summary>

**2018 (58)** — 2018-01-06, 2018-01-12, 2018-01-18, 2018-01-24, 2018-01-30, 2018-02-05, 2018-02-11, 2018-02-17, 2018-02-23, 2018-03-01, 2018-03-07, 2018-03-13, 2018-03-19, 2018-03-25, 2018-03-31, 2018-04-06, 2018-04-12, 2018-04-18, 2018-04-24, 2018-04-30, 2018-05-06, 2018-05-12, 2018-05-18, 2018-05-24, 2018-05-30, 2018-06-05, 2018-06-17, 2018-06-23, 2018-07-05, 2018-07-11, 2018-07-17, 2018-07-23, 2018-07-29, 2018-08-04, 2018-08-10, 2018-08-16, 2018-08-22, 2018-08-28, 2018-09-03, 2018-09-09, 2018-09-15, 2018-09-21, 2018-09-27, 2018-10-03, 2018-10-09, 2018-10-15, 2018-10-21, 2018-10-27, 2018-11-02, 2018-11-08, 2018-11-14, 2018-11-20, 2018-11-26, 2018-12-02, 2018-12-08, 2018-12-14, 2018-12-20, 2018-12-26

**2019 (60)** — 2019-01-01, 2019-01-07, 2019-01-13, 2019-01-19, 2019-01-25, 2019-01-31, 2019-02-06, 2019-02-12, 2019-02-18, 2019-02-24, 2019-03-02, 2019-03-08, 2019-03-14, 2019-03-20, 2019-03-26, 2019-04-01, 2019-04-07, 2019-04-13, 2019-04-19, 2019-04-25, 2019-05-07, 2019-05-13, 2019-05-19, 2019-05-25, 2019-05-31, 2019-06-06, 2019-06-12, 2019-06-18, 2019-06-24, 2019-06-30, 2019-07-06, 2019-07-12, 2019-07-18, 2019-07-24, 2019-07-30, 2019-08-05, 2019-08-11, 2019-08-17, 2019-08-23, 2019-08-29, 2019-09-04, 2019-09-10, 2019-09-16, 2019-09-22, 2019-09-28, 2019-10-04, 2019-10-10, 2019-10-16, 2019-10-22, 2019-10-28, 2019-11-03, 2019-11-09, 2019-11-15, 2019-11-21, 2019-11-27, 2019-12-03, 2019-12-09, 2019-12-15, 2019-12-21, 2019-12-27

**2020 (61)** — 2020-01-02, 2020-01-08, 2020-01-14, 2020-01-20, 2020-01-26, 2020-02-01, 2020-02-07, 2020-02-13, 2020-02-19, 2020-02-25, 2020-03-02, 2020-03-08, 2020-03-14, 2020-03-20, 2020-03-26, 2020-04-01, 2020-04-07, 2020-04-13, 2020-04-19, 2020-04-25, 2020-05-01, 2020-05-07, 2020-05-13, 2020-05-19, 2020-05-25, 2020-05-31, 2020-06-06, 2020-06-12, 2020-06-18, 2020-06-24, 2020-06-30, 2020-07-06, 2020-07-12, 2020-07-18, 2020-07-24, 2020-07-30, 2020-08-05, 2020-08-11, 2020-08-17, 2020-08-23, 2020-08-29, 2020-09-04, 2020-09-10, 2020-09-16, 2020-09-22, 2020-09-28, 2020-10-04, 2020-10-10, 2020-10-16, 2020-10-22, 2020-10-28, 2020-11-03, 2020-11-09, 2020-11-15, 2020-11-21, 2020-11-27, 2020-12-03, 2020-12-09, 2020-12-15, 2020-12-21, 2020-12-27

**2021 (59)** — 2021-01-02, 2021-01-08, 2021-01-14, 2021-01-20, 2021-01-26, 2021-02-01, 2021-02-07, 2021-02-13, 2021-02-19, 2021-02-25, 2021-03-03, 2021-03-09, 2021-03-15, 2021-03-21, 2021-03-27, 2021-04-02, 2021-04-08, 2021-04-14, 2021-04-20, 2021-04-26, 2021-05-02, 2021-05-08, 2021-05-14, 2021-05-20, 2021-05-26, 2021-06-01, 2021-06-07, 2021-06-13, 2021-06-19, 2021-06-25, 2021-07-01, 2021-07-07, 2021-07-13, 2021-07-19, 2021-07-25, 2021-07-31, 2021-08-06, 2021-08-12, 2021-08-18, 2021-08-24, 2021-08-30, 2021-09-05, 2021-09-11, 2021-09-17, 2021-09-23, 2021-09-29, 2021-10-05, 2021-10-11, 2021-10-17, 2021-10-23, 2021-10-29, 2021-11-04, 2021-11-10, 2021-11-22, 2021-11-28, 2021-12-04, 2021-12-10, 2021-12-16, 2021-12-22

**2022 (30)** — 2022-01-03, 2022-01-15, 2022-01-27, 2022-02-08, 2022-02-20, 2022-03-04, 2022-03-16, 2022-03-28, 2022-04-09, 2022-04-21, 2022-05-03, 2022-05-15, 2022-05-27, 2022-06-08, 2022-06-20, 2022-07-02, 2022-07-14, 2022-07-26, 2022-08-07, 2022-08-19, 2022-08-31, 2022-09-12, 2022-09-24, 2022-10-06, 2022-10-18, 2022-10-30, 2022-11-11, 2022-12-05, 2022-12-17, 2022-12-29

**2023 (28)** — 2023-01-10, 2023-01-22, 2023-02-03, 2023-02-15, 2023-02-27, 2023-03-11, 2023-03-23, 2023-04-04, 2023-04-16, 2023-04-28, 2023-05-10, 2023-05-22, 2023-06-03, 2023-06-15, 2023-06-27, 2023-07-09, 2023-07-21, 2023-08-02, 2023-08-14, 2023-08-26, 2023-09-07, 2023-09-19, 2023-10-13, 2023-10-25, 2023-11-06, 2023-11-18, 2023-12-12, 2023-12-24

**2024 (26)** — 2024-01-17, 2024-01-29, 2024-02-22, 2024-03-05, 2024-03-17, 2024-03-29, 2024-04-10, 2024-04-22, 2024-05-04, 2024-05-16, 2024-05-28, 2024-06-09, 2024-06-21, 2024-07-03, 2024-07-15, 2024-07-27, 2024-08-08, 2024-08-20, 2024-09-01, 2024-09-13, 2024-09-25, 2024-10-19, 2024-11-24, 2024-12-06, 2024-12-18, 2024-12-30

**2025 (52)** — 2025-01-11, 2025-01-23, 2025-02-04, 2025-02-16, 2025-03-12, 2025-03-24, 2025-03-30, 2025-04-05, 2025-04-11, 2025-04-17, 2025-04-29, 2025-05-05, 2025-05-11, 2025-05-17, 2025-05-23, 2025-05-29, 2025-06-04, 2025-06-10, 2025-06-16, 2025-06-22, 2025-06-28, 2025-07-04, 2025-07-10, 2025-07-16, 2025-07-22, 2025-07-28, 2025-08-03, 2025-08-09, 2025-08-15, 2025-08-21, 2025-08-27, 2025-09-02, 2025-09-08, 2025-09-14, 2025-09-20, 2025-09-26, 2025-10-02, 2025-10-08, 2025-10-14, 2025-10-20, 2025-10-26, 2025-11-01, 2025-11-07, 2025-11-13, 2025-11-19, 2025-11-25, 2025-12-01, 2025-12-07, 2025-12-13, 2025-12-19, 2025-12-25, 2025-12-31

**2026 (52)** — 2026-01-06, 2026-01-12, 2026-01-18, 2026-01-24, 2026-01-30, 2026-02-05, 2026-02-11, 2026-02-17, 2026-02-23, 2026-03-01, 2026-03-07, 2026-03-13, 2026-03-19, 2026-03-25, 2026-03-31, 2026-04-06, 2026-04-12, 2026-04-18, 2026-04-24, 2026-04-30, 2026-05-06, 2026-05-12, 2026-05-13, 2026-05-18, 2026-05-24, 2026-05-25, 2026-05-30, 2026-06-05, 2026-06-18, 2026-06-23, 2026-06-30, 2026-07-06, 2026-07-12, 2026-07-18, 2026-07-24, 2026-07-30, 2026-08-11, 2026-08-17, 2026-08-23, 2026-08-29, 2026-09-04, 2026-09-10, 2026-09-16, 2026-09-22, 2026-09-28, 2026-10-04, 2026-10-10, 2026-10-16, 2026-10-22, 2026-10-28, 2026-11-03, 2026-11-09

</details>

