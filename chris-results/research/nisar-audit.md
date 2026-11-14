# NISAR L-band GCOV audit — Elin Pelin, Bulgaria

**Status:** public browse quicklooks delivered for the AOI; calibrated GCOV HDF5
access is blocked by NASA Earthdata Login. The HDF5 extraction path is implemented
and was validated on the public 2008 NISAR-format sample granule.

**Study area (EPSG:4326):** `west=23.575, south=42.610, east=23.640, north=42.665`
(farmland and villages near Elin Pelin, Sofia Province, Bulgaria).

**Delivered grid:** EPSG:32634 (UTM 34N), 20 m, **277 x 314** pixels,
transform `[20, 0, 711020, 0, -20, 4727000]`
(west 711020 m, north 4727000 m; east 716560 m, south 4720720 m).
This covers the AOI with a 0–16 m margin.

---

## 1. Scene selection

Both scenes are the same relative orbit/track and frame, 3.5 months apart:

| | Early | Late |
|---|---|---|
| Acquisition (UTC) | 2026-06-20 17:28:59 | 2026-10-06 17:28:56 |
| Granule | `NISAR_L2_PR_GCOV_023_094_D_067_2005_DHDH_A_20260620T172859_20260620T172934_P05023_N_F_J_001` | `NISAR_L2_PR_GCOV_032_094_D_067_2005_DHDH_A_20261006T172856_20261006T172931_P05023_N_F_J_001` |
| Cycle | 023 | 032 |
| Track / direction | 094 / DESCENDING | 094 / DESCENDING |
| Frame | 067 | 067 |
| Absolute orbit | 4691 | 6248 |
| Product | L2 GCOV, PROVISIONAL V1 | L2 GCOV, PROVISIONAL V1 |
| Polarisation token | `DHDH` (dual-pol HH + HV) | `DHDH` (dual-pol HH + HV) |
| HDF5 size (HEAD) | 2,034,237,440 B | 2,034,237,440 B |

Other candidates from the same track (e.g. 2026-07-02, 2026-09-24) exist, but
June/October gives the largest seasonal contrast for farmland.

The ASF SearchAPI query used (no authentication):

```
https://api.daac.asf.alaska.edu/services/search/param
  ?platform=NISAR
  &processingLevel=GCOV
  &intersectsWith=POLYGON((23.575 42.610,23.640 42.610,23.640 42.665,23.575 42.665,23.575 42.610))
  &start=2026-06-01T00:00:00Z
  &output=json
```

## 2. Access audit — why the HDF5 route stopped

### 2.1 ASF HDF5 URL returns a login redirect on GET

For both granules:

- `HEAD` on the `downloadUrl` returns **HTTP 303** to a CloudFront
  `.../head-<hash>/sds-n-cumulus-prod-nisar-products.s3.us-west-2.amazonaws.com/...`
  URL. Following that HEAD returns **HTTP 200**, `content-length: 2034237440`,
  `accept-ranges: bytes`. This is why a HEAD-only check looks public.
- `GET` (with or without a `Range` header) returns **HTTP 302** to
  `https://urs.earthdata.nasa.gov/oauth/authorize?...&app_type=401`.
  The body is `HTTP Basic: Access denied.` The CloudFront signed `head-` URL is
  not valid for GET (403).
- `https://nisar.asf.earthdatacloud.nasa.gov/s3credentials` also redirects to
  Earthdata OAuth. The S3 object endpoint returns 403 without temporary
  credentials.

Conclusion: **calibrated NISAR GCOV HDF5 download requires an Earthdata Login
account and a `~/.netrc` (or equivalent) session.** No credentials were present
in this environment, so the 2 GB files were not downloaded and the attempt was
not retried.

### 2.2 What *is* public

- ASF search API metadata: works without auth.
- Browse quicklooks under `/BROWSE/...`: **HTTP 200**, no auth.
- NASA's public NISAR-format sample granule (2008): **HTTP 200**,
  171,966,464 B. Downloaded to `/tmp/opencode/nisar/sample_gcov_2008.h5`.
  It is a PALSAR-based NISAR sample over California (UTM 11N), **not Bulgaria**;
  it is used only to validate the HDF5 reader and document the structure.

Browse files used:

| File | Bytes |
|---|---:|
| `20260620_LATLON.png` (1968 x 1945 RGB) | 4,282,211 |
| `20260620_NATIVE_A_HHHH.png` (1968 x 1944, 8-bit) | 1,649,312 |
| `20260620_NATIVE_A_HVHV.png` (1968 x 1944, 8-bit) | 1,635,123 |
| `20261006_LATLON.png` (1968 x 1945 RGB) | 4,290,096 |
| `20261006_NATIVE_A_HHHH.png` (1968 x 1944, 8-bit) | 1,649,500 |
| `20261006_NATIVE_A_HVHV.png` (1968 x 1944, 8-bit) | 1,638,130 |

The full browse URL pattern is:

```
https://nisar.asf.earthdatacloud.nasa.gov/BROWSE/NISAR_L2_GCOV_PROVISIONAL_V1/
  <granule>/<granule>_LATLON.png
  <granule>/<granule>_NATIVE_A_HHHH.png
  <granule>/<granule>_NATIVE_A_HVHV.png
```

The verbatim URLs for both scenes are recorded in
`data/raw/nisar/nisar_browse_metadata.json` under `scenes[].browse_urls`.

The `browse` list in the ASF search JSON also contains `_NATIVE.png` (RGB) and
frequency-B layers. The AOI scenes are `DHDH` (dual-pol on both frequencies);
the frequency-A layers were used because A is the primary, higher-resolution
L-band. Frequency-B quicklooks exist but were not used.

## 3. Real GCOV HDF5 structure (from the public sample)

Paths and attributes below are the actual structure of
`/tmp/opencode/nisar/sample_gcov_2008.h5` (NISAR L2 GCOV format). The sample is
single-pol (`SHNA`), so it contains `HHHH` but no `HVHV`; a `DHDH` AOI granule
will contain both `HHHH` and `HVHV`.

```
/science/LSAR/GCOV/grids/frequencyA/
  HHHH                       float32  (6220, 4545)  chunks (512, 512)
  mask                       uint8    (6220, 4545)  chunks (512, 512)
  numberOfLooks              float32  (6220, 4545)  chunks (512, 512)
  numberOfSubSwaths          uint8    scalar
  projection                 uint32   scalar          EPSG code
  rtcGammaToSigmaFactor      float32  (6220, 4545)  chunks (512, 512)
  xCoordinateSpacing         float64  scalar          20.0 m
  xCoordinates               float64  (4545,)         metres
  yCoordinateSpacing         float64  scalar          -20.0 m
  yCoordinates               float64  (6220,)         metres, descending
  listOfCovarianceTerms      |S4      (1,)
  listOfPolarizations        |S2      (1,)
/science/LSAR/GCOV/metadata/...   (attitude, calibration, orbit,
                                   processingInformation, radarGrid, sourceData)
```

Key dataset attributes:

| Dataset | Attribute | Value |
|---|---|---|
| `HHHH` | `description` | `Covariance between HH and HH` |
| `HHHH` | `_FillValue` | `nan` |
| `HHHH` | `valid_min` | `0.0` |
| `HHHH` | `units` | `1` (linear power, gamma0) |
| `HHHH` | `grid_mapping` | `projection` |
| `mask` | `_FillValue` | `255` |
| `mask` | `valid_min` | `0` |
| `numberOfLooks` | `_FillValue` | `nan`; range 0.0019–40.25, mean 7.90 |
| `rtcGammaToSigmaFactor` | `_FillValue` | `nan`; range 0.00130–0.02137, mean 0.01735 |
| `projection` | `epsg_code` | `32611` (sample) |
| `projection` | `utm_zone_number` | `11` |
| `projection` | `grid_mapping_name` | `transverse_mercator` |
| `xCoordinates` | `standard_name`, `units` | `projection_x_coordinate`, `meters` |
| `yCoordinates` | `standard_name`, `units` | `projection_y_coordinate`, `meters` |

Sample grid: EPSG:32611, x = 365490 … 456370 m, y = 3913610 … 3789230 m,
20 m posting; `HHHH` is linear gamma0 power, not dB. For the Bulgarian AOI the
expected projection is **EPSG:32634** (UTM 34N), with `HHHH` and `HVHV` both
present.

The calibrated conversion used by `scripts/nisar_extract.py`:

```python
valid = np.isfinite(power) & (power > 0) & (mask != 255)
db = 10.0 * np.log10(power)
db[~valid] = np.nan
# optional sigma0: power *= rtcGammaToSigmaFactor before the log
```

Root attributes of the sample include `Conventions=CF-1.7`,
`mission_name=NISAR`, `institution=NASA JPL`, and
`reference_document=D-102274 ... L2 GCOV`.

## 4. Browse fallback method (what was actually delivered)

The browse PNG has **no embedded geotransform**, and its KML sidecar
(`_NATIVE.kml`, `_LATLON.kml`) is login-protected (401). The fallback therefore
uses a deliberately simple linear mapping. The `_LATLON.png` is used for the
valid-area mask; the single-pol `_NATIVE_A_HHHH.png` / `_NATIVE_A_HVHV.png`
quicklooks supply the raw DN.

1. Read the scene's four-corner `stringFootprint` from the ASF search JSON.
   For both dates the bbox is approximately
   `21.03692, 41.14741, 24.87676, 43.96711` (lon/lat).
2. For every 20 m output pixel centre in EPSG:32634, transform to lon/lat.
3. Normalise into the footprint bbox and sample the 8-bit browse PNG:
   `px = (lon-lon_min)/(lon_max-lon_min)*(W-1)`,
   `py = (lat_max-lat)/(lat_max-lat_min)*(H-1)`.
4. Nearest-neighbour sample (`order=0`) to preserve the raw 8-bit values.
   `DN=0` is treated as nodata; the `_LATLON.png` valid-area mask is applied.
5. Write GeoTIFFs on the fixed 277 x 314 grid, EPSG:32634.

This assumes the browse image spans exactly the footprint bbox and is north-up.
It is **approximate**: the browse quicklook is a resampled rendering in the
product's native grid, the footprint is a rotated quadrilateral, and the KML
that would give the true raster extent is not public. Expect geolocation errors
of **kilometres**, not metres. The layer is for visualization and storytelling,
not for the quantitative leak model.

The AOI is ~5.5–6.1 km across; at ~160 m browse pixel size it is only ~35–40
source pixels per side. The 20 m GeoTIFF is therefore an upsampled display
product, not new 20 m information.

## 5. Files produced

All in `data/raw/nisar/`:

| File | Type | Bytes | Value range | Median |
|---|---|---:|---|---:|
| `nisar_hh_20260620.tif` | uint8, EPSG:32634 | 7,073 | 1–255 DN | 182 |
| `nisar_hh_20261006.tif` | uint8, EPSG:32634 | 7,083 | 1–255 DN | 166 |
| `nisar_hh_latest.tif` | uint8, copy of 2026-10-06 | 7,083 | 1–255 DN | 166 |
| `nisar_hv_20260620.tif` | uint8, EPSG:32634 | 7,133 | 19–255 DN | 175 |
| `nisar_hv_20261006.tif` | uint8, EPSG:32634 | 7,163 | 33–255 DN | 164 |
| `nisar_change_HH.tif` | int16, nodata −9999 | 8,045 | −94 … +67 DN | −11 |
| `nisar_change_HV.tif` | int16, nodata −9999 | 7,927 | −58 … +29 DN | −6 |
| `nisar_preview.png` | 4-panel preview | 142,127 | — | — |
| `nisar_browse_metadata.json` | scene/grid/method metadata | 6,176 | — | — |

Change is **later minus earlier** (2026-10-06 − 2026-06-20), computed from the
raw 8-bit browse values. `nisar_hh_latest.tif` is a byte-identical copy of
`nisar_hh_20261006.tif` (same SHA-256).

All GeoTIFFs have:

```
width=277, height=314
crs=EPSG:32634
transform=(20.0, 0.0, 711020.0, 0.0, -20.0, 4727000.0)
```

## 6. What the change image shows

- HH browse DN median falls from **182 (June)** to **166 (October)**, a shift of
  −16 DN; the pixel-wise change median is **−11 DN** (range −94…+67).
- HV falls from **175** to **164**; change median **−6 DN** (range −58…+29).
- The change is spatially coherent: most of the central/northern fields are
  darker in October (blue), with scattered brighter patches (red) in the south
  and east. Dark forest patches at the top/bottom of the AOI remain dark in both
  dates.
- A plausible physical driver is seasonal crop phenology (green, moist June
  fields vs. harvested/bare October fields), possibly plus soil-moisture and
  incidence/geometry differences. This is a **hypothesis for the story**, not a
  calibrated retrieval.

**Important:** the June and October browse quicklooks are stretched
independently (each is a 5–95 % percentile, gamma-0.5 display stretch of linear
power). A DN difference therefore mixes real backscatter change with a change in
the display stretch. The change GeoTIFF is a **display-only visual index**, not
a calibrated dB change and not evidence of a water leak.

## 7. Reproduction

Use the pixi environment:

```bash
cd "/home/user/Engineering/Hackathons/NASA Space App/Project/Dancing-With-The-SARs"

# 1. Search (no auth)
~/.pixi/bin/pixi run python scripts/nisar_extract.py search

# 2. Public browse fallback -> data/raw/nisar/ (works now)
~/.pixi/bin/pixi run python scripts/nisar_extract.py --browse \
    --scene-json /tmp/opencode/nisar/search.json \
    --dates 2026-06-20 2026-10-06

# 3. Inspect the public 2008 sample HDF5 (real GCOV structure)
~/.pixi/bin/pixi run python scripts/nisar_extract.py inspect \
    /tmp/opencode/nisar/sample_gcov_2008.h5

# 4. Calibrated HDF5 extraction (future, after Earthdata Login)
~/.pixi/bin/pixi run python scripts/nisar_extract.py --hdf5 \
    /path/to/NISAR_L2_PR_GCOV_..._20260620....h5 \
    --bbox 23.575 42.610 23.640 42.665 \
    --pols HHHH HVHV
```

Browse downloads are cached in `/tmp/opencode/nisar/`; no large files are
committed. The default grid can be overridden with
`--grid WEST NORTH WIDTH HEIGHT RES` and `--epsg`.

### Enabling the calibrated HDF5 run

1. Create a free Earthdata Login account: <https://urs.earthdata.nasa.gov/>.
2. Put credentials in `~/.netrc` (never commit this file):

```
machine urs.earthdata.nasa.gov
    login <username>
    password <password>
```

3. Download the granule to `/tmp/opencode/nisar/` (for example with
   `curl -n -L -c ~/.urs_cookies -b ~/.urs_cookies -o /tmp/opencode/nisar/granule.h5 "<downloadUrl>"`,
   or with `asf_search`). Then run the `--hdf5` command on the local file. The
   script reads only the AOI window with h5py, applies the `mask`, converts
   gamma0 linear power to dB, and writes float32 GeoTIFFs.

Expected calibrated output names from the HDF5 path are `<date>_HH.tif` and
`<date>_HV.tif` (plus `nisar_change_HH.tif` / `nisar_change_HV.tif` with
`--change`), not the `nisar_`-prefixed browse filenames. The HDF5 path was
validated on the sample: a 467 x 563 px subset produced
`20081012_HH.tif` with dB −29.3…+11.8 (median −17.7), EPSG:32611, 20 m.

## 8. Limitations / next steps

1. **No calibrated NISAR radiometry over the AOI.** The delivered GeoTIFFs are
   8-bit browse DN, not gamma0/sigma0. They must not be used as quantitative
   backscatter or for leak detection.
2. **Approximate georeferencing.** The linear footprint-bbox mapping is not the
   product grid. Obtaining the login-protected KML sidecar, or reading the HDF5
   `xCoordinates`/`yCoordinates`, is required for an exact AOI subset. The
   current alignment is suitable for a visual story only.
3. **No mask / number-of-looks / RTC metadata** in the browse fallback. These
   layers exist in the HDF5; the `--hdf5` path reads `mask` and can be extended
   to export looks and the gamma-to-sigma factor.
4. **The public sample is not Bulgaria.** It is a 2008 PALSAR-based NISAR-format
   sample over California, used only to verify group paths, dtypes, attributes,
   CRS handling and the dB conversion.
5. **Next step for the quantitative model:** get one Earthdata Login, run the
   `--hdf5` path for the two track-094 granules (or a single granule first),
   and replace the browse GeoTIFFs with calibrated gamma0 dB rasters on the
   same 277 x 314 grid. The script already reads `numberOfLooks` and
   `rtcGammaToSigmaFactor`; exporting them as separate GeoTIFFs is a small
   extension.

## 9. References

- ASF SearchAPI: <https://api.daac.asf.alaska.edu/services/search/param>
- NISAR GCOV product guide: <https://nisar-docs.asf.alaska.edu/gcov>
- NISAR GCOV product specification D-102274 Rev F:
  <https://cumulus.asf.earthdatacloud.nasa.gov/PUBLIC/DATA/NISAR/NISAR_D-102274_RevF_NASA_SDS_Product_Specification_L2_GCOV_w-esigs.pdf>
- NISAR sample data: <https://science.nasa.gov/mission/nisar/sample-data/>
- `nisarqa` browse/QA software: <https://github.com/isce-framework/nisarqa>
- Earthdata Login: <https://urs.earthdata.nasa.gov/>
