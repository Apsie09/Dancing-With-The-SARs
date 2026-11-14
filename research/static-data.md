# Static & Meteorological Layers — Elin Pelin AOI

Acquired **2026-11-14 (UTC)** for the NASA Space Apps "Dancing With The SARs" study area east of Sofia, Bulgaria. Every layer below is real downloaded data (no synthetic values); processing/resampling steps and the only gap-fill are documented explicitly.

## Study area and common grid

| Item | Value |
|---|---|
| AOI bbox (EPSG:4326) | west **23.575**, south **42.610**, east **23.640**, north **42.665** |
| Centre | 23.6075 E, 42.6375 N |
| AOI bbox in EPSG:32634 | 711026.5, 4720721.8 → 716544.5, 4726994.0 |
| Analysis grid | **EPSG:32634 (UTM 34N), 10 m**, 553 × 628 px |
| Grid origin / extent | (711020, 4727000); x 711020–716550, y 4720720–4727000 |
| Grid area | 34.7284 km² (5.53 km × 6.28 km) |
| Affine transform | `10, 0, 711020, 0, -10, 4727000` |

All GeoTIFFs are single-band, have the **same 553 × 628 grid**, DEFLATE compression, and are aligned pixel-for-pixel. No-data conventions: `NaN` for float soil/DEM/slope layers, `0` for WorldCover (class 0 = no data; none present), `-9999` for the two distance rasters, `255` for the soil mask.

## Layer summary

| File | Layer | Native source / resolution | Output CRS / res | Units | Range (mean) |
|---|---|---|---|---|---|
| `data/met/weather_hourly.csv` | hourly meteorology | Open-Meteo ERA5, ~9 km | — | see §1 | 42,696 h |
| `data/met/weather_daily.csv` | daily meteorology | derived | — | see §1 | 1,779 d |
| `data/static/soil_sand_0_5.tif` | sand 0–5 cm | SoilGrids 250 m | EPSG:32634 / 10 m | g/kg | 230.3–383.0 (293.9) |
| `data/static/soil_sand_5_15.tif` | sand 5–15 cm | SoilGrids 250 m | EPSG:32634 / 10 m | g/kg | 228.3–388.0 (295.7) |
| `data/static/soil_clay_0_5.tif` | clay 0–5 cm | SoilGrids 250 m | EPSG:32634 / 10 m | g/kg | 248.5–361.7 (308.6) |
| `data/static/soil_clay_5_15.tif` | clay 5–15 cm | SoilGrids 250 m | EPSG:32634 / 10 m | g/kg | 254.0–382.7 (318.0) |
| `data/static/soil_silt_0_5.tif` | silt 0–5 cm | SoilGrids 250 m | EPSG:32634 / 10 m | g/kg | 319.0–479.0 (397.5) |
| `data/static/soil_silt_5_15.tif` | silt 5–15 cm | SoilGrids 250 m | EPSG:32634 / 10 m | g/kg | 301.5–471.0 (386.3) |
| `data/static/soil_soc_0_5.tif` | organic carbon 0–5 cm | SoilGrids 250 m | EPSG:32634 / 10 m | g/kg | 32.8–48.8 (41.1) |
| `data/static/soil_soc_5_15.tif` | organic carbon 5–15 cm | SoilGrids 250 m | EPSG:32634 / 10 m | g/kg | 17.1–30.5 (21.2) |
| `data/static/soil_bdod_0_5.tif` | bulk density 0–5 cm | SoilGrids 250 m | EPSG:32634 / 10 m | g/cm³ | 1.290–1.390 (1.341) |
| `data/static/soil_bdod_5_15.tif` | bulk density 5–15 cm | SoilGrids 250 m | EPSG:32634 / 10 m | g/cm³ | 1.390–1.490 (1.448) |
| `data/static/soil_nodata_mask.tif` | SoilGrids no-data mask | derived | EPSG:32634 / 10 m | 0/1 | 8.87 % = 1 |
| `data/static/worldcover_aoi.tif` | land cover classes | ESA WorldCover 10 m | EPSG:32634 / 10 m | class code | 10–90 |
| `data/static/dem_aoi.tif` | elevation (DSM) | Copernicus GLO-30 | EPSG:32634 / 10 m | m (EGM2008) | 535.5–630.8 (558.6) |
| `data/static/slope_aoi.tif` | slope | derived from GLO-30 | EPSG:32634 / 10 m | degrees | 0.0005–10.24 (0.98) |
| `data/static/dist_built_aoi.tif` | distance to building | OSM / Overpass | EPSG:32634 / 10 m | m | 0–2521.7 (614.6) |
| `data/static/dist_road_aoi.tif` | distance to road | OSM / Overpass | EPSG:32634 / 10 m | m | 0–1011.1 (195.8) |

---

## 1. Meteorology — Open-Meteo ERA5 archive

**Endpoint (no authentication):**

```text
https://archive-api.open-meteo.com/v1/archive?latitude=42.6375&longitude=23.6075
  &start_date=2022-01-01&end_date=2026-11-14
  &hourly=temperature_2m,precipitation,relative_humidity_2m,shortwave_radiation,
          et0_fao_evapotranspiration,soil_moisture_0_to_7cm,soil_moisture_7_to_28cm,
          soil_moisture_28_to_100cm,vapor_pressure_deficit,wind_speed_10m
  &timezone=UTC
```

**Acquired period:** 2022-01-01 00:00 → 2026-11-14 23:00 UTC — **42,696 hourly records, zero nulls, all days have 24 hours**. The response snaps the request to the nearest ERA5 grid cell: **42.636204 N, 23.628319 E, grid elevation 548 m** (~2.2 km east of the requested centre; ERA5 native grid ≈ 9 km). Recent days come from the archive's latest ERA5T/analysis stream and may be revised upstream.

### Hourly file — `data/met/weather_hourly.csv`

42,696 rows × 11 columns. `time_utc` is ISO-8601 with `Z`.

| Column | Units | Notes |
|---|---|---|
| `time_utc` | UTC timestamp | hourly, no gaps |
| `temperature_2m` | °C | 2 m air temperature |
| `precipitation` | mm | hourly total |
| `relative_humidity_2m` | % | |
| `shortwave_radiation` | W/m² | hourly mean |
| `et0_fao_evapotranspiration` | mm | FAO-56 reference ET, hourly total |
| `soil_moisture_0_to_7cm` | m³/m³ | volumetric |
| `soil_moisture_7_to_28cm` | m³/m³ | volumetric |
| `soil_moisture_28_to_100cm` | m³/m³ | volumetric |
| `vapor_pressure_deficit` | kPa | |
| `wind_speed_10m` | km/h | 10 m wind |

### Daily file — `data/met/weather_daily.csv`

1,779 rows × 15 columns, one row per **date** (UTC day).

| Column | Units | Aggregation |
|---|---|---|
| `date` | YYYY-MM-DD | UTC calendar day |
| `precip_sum` | mm/day | Σ hourly precipitation |
| `temp_mean` / `temp_min` / `temp_max` | °C | daily mean / min / max |
| `rh_mean` | % | mean of hourly RH |
| `radiation_sum` | W·h/m²/day | Σ hourly W/m² |
| `radiation_mj_m2` | MJ/m²/day | `radiation_sum × 0.0036` |
| `et0_sum` | mm/day | Σ hourly ET₀ |
| `sm0_7`, `sm7_28`, `sm28_100` | m³/m³ | daily mean of hourly soil moisture |
| `vpd_mean` | kPa | daily mean VPD |
| `wind_mean` | km/h | daily mean 10 m wind |
| `n_hours` | count | 24 for every day (QA) |

### Climatology of the acquired record

Overall mean temperature **11.97 °C**; total precipitation **2,784 mm**; total ET₀ **5,195 mm**. Annual totals (2026 is incomplete, through 14 Nov):

| Year | Days | Precip (mm) | Tmean (°C) | Tmin (°C) | Tmax (°C) | ET₀ (mm) |
|---|---|---|---|---|---|---|
| 2022 | 365 | 537.1 | 11.2 | −15.3 | 33.9 | 1,024 |
| 2023 | 365 | 719.9 | 12.1 | −7.6 | 38.0 | 1,014 |
| 2024 | 366 | 452.3 | 12.4 | −9.8 | 36.5 | 1,099 |
| 2025 | 365 | 603.4 | 11.6 | −14.3 | 38.6 | 1,057 |
| 2026 | 318 | 471.7 | 12.5 | −9.5 | 35.8 | 1,001 |

Metadata (request URL, returned coordinates/elevation, variable units) is in `data/met/metadata.json`.

---

## 2. Soil properties — ISRIC SoilGrids v2.0

### Primary source: WCS GetCoverage (250 m)

Map endpoints:

```text
https://maps.isric.org/mapserv?map=/map/sand.map
https://maps.isric.org/mapserv?map=/map/clay.map
https://maps.isric.org/mapserv?map=/map/silt.map
https://maps.isric.org/mapserv?map=/map/soc.map
https://maps.isric.org/mapserv?map=/map/bdod.map
```

Example request (sand, 0–5 cm, AOI padded by 0.01° to avoid edge no-data):

```text
SERVICE=WCS&VERSION=2.0.1&REQUEST=GetCoverage
&COVERAGEID=sand_0-5cm_mean
&FORMAT=image/tiff
&SUBSET=long(23.565,23.650)
&SUBSET=lat(42.600,42.675)
&SUBSETTINGCRS=http://www.opengis.net/def/crs/EPSG/0/4326
&OUTPUTCRS=http://www.opengis.net/def/crs/EPSG/0/4326
```

Coverage IDs used: `{sand|clay|silt|soc|bdod}_{0-5cm|5-15cm}_mean` (10 layers). Native product is **250 m**, global; the server returned ~250 m subsets (38 × 31 px), which were bilinearly resampled to the 10 m UTM grid. Values are SoilGrids predicted means.

### QC sample: point API (6 × 8 grid)

```text
https://rest.isric.org/soilgrids/v2.0/properties/query?lon=23.6075&lat=42.6375
  &property=sand&property=clay&property=silt&property=soc&property=bdod
  &depth=0-5cm&depth=5-15cm&value=mean
```

- 48 points: 6 longitudes (23.575 → 23.640) × 8 latitudes (42.610 → 42.665), inclusive of the bbox edges.
- `data/static/soil_samples_6x8.csv`: **480 rows** (48 points × 5 properties × 2 depths), long format: `sample_id, lon, lat, property, depth, value, unit`. Values/units are **as returned by the point API** (sand/clay/silt `g/kg`, SOC `dg/kg`, bulk density `cg/cm³`).
- All 48 point requests succeeded (no failures). The API was slow at times (~10 s/request; 448 s total with 4 workers). **40 of the 480 values are `null`** (read as `NaN` by pandas), from 4 points that fall in SoilGrids no-data areas — 3 on the AOI bbox edge and 1 in a built-up/water patch near 23.588 E, 42.626 N.

**Agreement between the WCS rasters and the independent point samples** (48 points, output units): sand/clay/silt MAE ≈ **3.6–4.2 g/kg**, SOC MAE ≈ **0.6–0.9 g/kg**, bulk density MAE ≈ **0.003 g/cm³**; mean biases < 1.4 g/kg (SOC < 0.21 g/kg). This confirms the WCS values and the unit conversions below.

### Units written to the GeoTIFFs

| Property | WCS/API source unit | Conversion applied | Output unit | Output mean (0–5 cm) |
|---|---|---|---|---|
| sand, clay, silt | g/kg | none | **g/kg** | 294 / 309 / 398 |
| organic carbon (SOC) | dg/kg | ÷ 10 | **g/kg** | 41.1 g/kg (= 4.11 %) |
| bulk density (BDOD) | cg/cm³ | ÷ 100 | **g/cm³** | 1.341 g/cm³ |

The three texture fractions sum to **999–1001 g/kg** (mean 1000), consistent with the SoilGrids texture model. Mean texture is 29.4 % sand / 30.9 % clay / 39.8 % silt → indicative **clay loam** (USDA); use the per-pixel rasters rather than the mean for classification.

### No-data and gap fill

WCS output contains **30,789 no-data pixels (8.87 % of the AOI)**, mainly server-side warp/mask streaks that partly coincide with built-up areas (57 % of WorldCover class 50 is no-data) and mask edges. These were filled with the **nearest valid SoilGrids 250 m cell** so that all 10 soil rasters are continuous. The original mask is preserved in `soil_nodata_mask.tif` (1 = filled). Where the point API also returns `null` (urban/water), the fill carries the nearest soil value — treat those pixels as inferred, not measured. No other soil values were altered besides unit scaling.

---

## 3. Land cover — ESA WorldCover 2021 v200, 10 m

**Tile note:** the task-specified `N42E023` tile **does not exist** in the public bucket (HTTP 404). WorldCover map tiles are **3° × 3°**, not 1° × 1°. The AOI (23.575–23.640 E) lies inside **`N42E021`**, which covers 21–24 E, 42–45 N:

```text
https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map/ESA_WorldCover_10m_2021_v200_N42E021_Map.tif
```

- Product: ESA WorldCover 2021 **v200**, 10 m, epoch 2021.
- Native CRS/resolution: **EPSG:4326**, 1/12000° (≈ 9.3 m); 36,000 × 36,000 px tile.
- Read strategy: GDAL `/vsicurl` window read (padded 0.02°) from the 84 MB COG, no full download.
- Output: cropped to the AOI and reprojected to **EPSG:32634 / 10 m with nearest neighbour**, so **class codes are unchanged**.
- No class-0 (no-data) pixels remain after the padded read; 347,284/347,284 pixels are valid.

| Code | Class | Pixels | Area (km²) | Share |
|---:|---|---:|---:|---:|
| 10 | Tree cover | 19,630 | 1.963 | 5.65 % |
| 20 | Shrubland | 36 | 0.0036 | 0.01 % |
| 30 | Grassland | 44,684 | 4.468 | 12.87 % |
| 40 | Cropland | 252,632 | 25.263 | 72.75 % |
| 50 | Built-up | 28,394 | 2.839 | 8.18 % |
| 60 | Bare / sparse vegetation | 1,820 | 0.182 | 0.52 % |
| 80 | Permanent water bodies | 81 | 0.0081 | 0.02 % |
| 90 | Herbaceous wetland | 7 | 0.0007 | 0.002 % |

Classes absent in the AOI: 70 (snow/ice), 95 (mangroves), 100 (moss/lichen).

---

## 4. Terrain — Copernicus DEM GLO-30

```text
https://copernicus-dem-30m.s3.amazonaws.com/Copernicus_DSM_COG_10_N42_00_E023_00_DEM/
  Copernicus_DSM_COG_10_N42_00_E023_00_DEM.tif
```

- Product: Copernicus DEM **GLO-30** (COG), tile `N42_00_E023_00`, 3600 × 3600 px, 1 arc-second (~30 m), **EPSG:4326**, vertical datum **EGM2008**, units **metres**.
- This is a **DSM** (surface model: canopy/buildings included), not a bare-earth DTM.
- Read via `/vsicurl` window (padded 0.01°) then bilinearly resampled to the 10 m UTM grid → `dem_aoi.tif`.
- **Slope:** computed on a 30 m UTM 34N grid with the **Horn 3 × 3 kernel**, then bilinearly resampled to 10 m → `slope_aoi.tif` (degrees). A 120 m buffer around the AOI avoids edge effects.

| Layer | Min | Max | Mean | Median | P05–P95 |
|---|---:|---:|---:|---:|---:|
| Elevation (m) | 535.45 | 630.76 | 558.55 | 549.55 | 539.2–601.2 |
| Slope (°) | 0.0005 | 10.24 | 0.98 | 0.70 | 0.15–2.63 |

The AOI is a low-relief farmland basin (~535–560 m) with a hilly/wooded margin rising to ~630 m in the south/southeast; slopes are mostly < 3°.

---

## 5. Built environment — OpenStreetMap / Overpass (optional layer, produced)

**Overpass query** (`https://overpass-api.de/api/interpreter`, GET, 2026-11-14; OSM base timestamp 2026-11-14T20:56:21Z):

```text
[out:json][timeout:180];
(way["building"](42.610,23.575,42.665,23.640);
 way["highway"](42.610,23.575,42.665,23.640););
out geom;
```

- **1,341 building ways**, **478 highway ways**, total road length **157.4 km**.
- `osm_buildings.geojson` / `osm_roads.geojson`: EPSG:4326, OSM ids and basic tags (`building`, `highway`, `name`).
- `dist_built_aoi.tif`: buildings rasterized at 10 m (`all_touched=True`), Euclidean distance transform in metres (0 on a footprint; max 2,522 m; mean 615 m).
- `dist_road_aoi.tif`: same method for roads (max 1,011 m; mean 196 m).
- Caveats: OSM completeness is uneven in rural Bulgaria — some farm buildings/tracks may be missing. Distance is to mapped features only, not a cadastral built-up boundary.

---

## 6. File inventory

| Path | Size |
|---|---:|
| `data/met/weather_hourly.csv` | 2.95 MB |
| `data/met/weather_daily.csv` | 319 KB |
| `data/met/metadata.json` | 1.5 KB |
| `data/static/soil_*_0_5.tif`, `soil_*_5_15.tif` (10 files) | 0.32–0.57 MB each |
| `data/static/soil_nodata_mask.tif` | 2.8 KB |
| `data/static/soil_samples_6x8.csv` | 20 KB |
| `data/static/worldcover_aoi.tif` | 28 KB |
| `data/static/dem_aoi.tif` | 791 KB |
| `data/static/slope_aoi.tif` | 806 KB |
| `data/static/dist_built_aoi.tif` | 607 KB |
| `data/static/dist_road_aoi.tif` | 340 KB |
| `data/static/osm_buildings.geojson` | 336 KB |
| `data/static/osm_roads.geojson` | 164 KB |
| `data/static/layers_metadata.json` | 11 KB |
| `data/static/scripts/fetch_met.py` | acquisition script |
| `data/static/scripts/fetch_static.py` | acquisition script |

`data/static/layers_metadata.json` mirrors the table above with per-layer source URLs, coverage IDs, units, transforms and value statistics. (`data/static/dem.tif` pre-existed this task and was left untouched; the documented DEM is `dem_aoi.tif`.)

---

## 7. Run instructions

From the repository root, using the pixi environment:

```bash
# meteorology (seconds)
~/.pixi/bin/pixi run python data/static/scripts/fetch_met.py

# soil, land cover, DEM/slope, OSM (first run ~10-12 min; ~2-3 min with cached soil samples)
~/.pixi/bin/pixi run python data/static/scripts/fetch_static.py

# force a fresh 48-point SoilGrids sample (otherwise soil_samples_6x8.csv is reused)
FORCE_SOIL=1 ~/.pixi/bin/pixi run python data/static/scripts/fetch_static.py
```

Requirements (already in `pixi.toml`): `numpy`, `pandas`, `scipy`, `rasterio`, `requests`, `geopandas`, `shapely`, `pyproj`. Network access is required for every run; outputs are overwritten in place. The scripts only write to `data/met/` and `data/static/`; `research/static-data.md` is maintained manually.

Error handling in the scripts: Open-Meteo variables are dropped from the request if the API omits them; SoilGrids WCS/point calls and Overpass are retried (4× / 4× / 3× with backoff). Any remaining failure is logged in `layers_metadata.json` (`failures` list) and does not abort the other layers.

---

## 8. Known issues, fallbacks and caveats

1. **WorldCover tile mismatch (resolved):** `N42E023` is not a valid tile in the v200 bucket. Tiles are 3° × 3°; the AOI is in **`N42E021`**. No substitute/fallback product was needed.
2. **SoilGrids WCS no-data (documented gap fill):** 8.87 % of the AOI was no-data in the WCS output. Filled with the nearest valid 250 m cell; original mask in `soil_nodata_mask.tif`. The point API independently returns `null` at some of these pixels (urban/water/edges), so filled values there are inferred.
3. **SoilGrids point API latency:** individual requests occasionally take 20–60 s. The 48-point sample took 448 s with 4 workers; results are cached in `soil_samples_6x8.csv` so re-runs are fast.
4. **Overpass availability:** one transient HTTP 502 occurred and was retried successfully; if Overpass is down the two distance rasters and GeoJSONs are skipped and recorded under `failures`.
5. **ERA5 spatial support:** meteorology is a single ~9 km grid cell (42.6362 N, 23.6283 E), not a spatial field; it does not resolve the AOI's ~100 m relief. Applicable for regional weather/soil-moisture context, not pixel-level water balance.
6. **Recent meteorology:** values near the end date (Nov 2026) are the archive's latest/ERA5T stream and may be revised by ECMWF.
7. **DEM is a DSM:** Copernicus GLO-30 includes vegetation and buildings; slope is therefore surface slope, not bare-earth slope. Vertical datum EGM2008 (no ellipsoid conversion applied).
8. **Resampling:** only categorical land cover uses nearest neighbour; soil/DEM/slope use bilinear. Soil effective resolution remains **250 m** even though stored at 10 m; do not interpret 10 m soil texture variation as real.
9. **OSM completeness:** rural building/road mapping is incomplete; distances are to mapped features and should be treated as a proxy.

## 9. Attribution / licences

- **Open-Meteo** archive API (ERA5/ERA5T © ECMWF/Copernicus Climate Change Service) — free non-commercial API; see Open-Meteo terms.
- **SoilGrids v2.0** © ISRIC — CC BY 4.0.
- **ESA WorldCover 2021 v200** © ESA — CC BY 4.0.
- **Copernicus DEM GLO-30** © ESA — free and open, attribution required.
- **OpenStreetMap** © OpenStreetMap contributors — ODbL 1.0.
