# Coryell leak map

Interactive web map of the water leak repairs logged by the Coryell City Water
Supply District (central Texas), with the district's pipe network, pressure
zones, land cover and NISAR frame footprints. It is the base for adding NISAR
radar layers.

Plain HTML/CSS/JS with [MapLibre GL JS](https://maplibre.org/) 4.7.1 from a CDN.
No build step and nothing to install.

## Get the data first

`data/coryell/` is **git-ignored** (only its `README.md`, which documents the
sources, fields and licence, is tracked). After cloning, rebuild it with:

```sh
# from the repo root
python scripts/fetch_coryell_data.py                         # everything
python scripts/fetch_coryell_data.py --steps vectors,footprints   # no login, < 1 min
```

| Step | Makes | Needs | Time |
|---|---|---|---|
| `vectors` | `leak_survey.geojson`/`.csv`, `waterlines.geojson`, `pressure_zones.geojson` (district consultant's public ArcGIS layers) | nothing | seconds |
| `footprints` | `nisar_gcov_footprints.geojson` (NISAR GCOV frames over the district, from the ASF archive) | `asf_search`, `shapely` | seconds |
| `risk` (separate: `cd asen_results && pixi run coryell-risk`) | `risk/pipe_risk.geojson`, `risk/risk_summary.json`, and `pesho_coryell_data_package/risk_context.csv` | the `vectors` step first | ~15 s, no download |
| `chips` | `nisar/acquisitions_041D073.json`, `nisar/leak_chips.json`, `nisar/chips/*.png` (runs `scripts/make_leak_chips.py`) | Earthdata login | ~5-10 min, ~1.4 GB transfer |
| `images` | district images for 08-28 / 09-09 / 09-21 and the Riddle subset (runs `subset_gcov.py` + `render_gcov_png.py`) | Earthdata login, `chips` step first | ~4 min and ~180 MB per date |

Python packages: `numpy requests shapely asf_search` for the first two steps,
plus `h5py fsspec aiohttp pyproj rasterio` for the NISAR steps. The NISAR
steps read only the needed pieces of each 7 GB granule remotely; they need a
free Earthdata login (<https://urs.earthdata.nasa.gov/>) in `~/.netrc`
(`C:/Users/<you>/.netrc` on Windows):

```
machine urs.earthdata.nasa.gov login <username> password <password>
```

Without the NISAR steps the map still works: leaks, pipes, zones and frame
footprints show; the NISAR passes tab and radar layers say what is missing.

## Run it

Browsers block `fetch()` of local files, so opening `index.html` by
double-clicking (`file://`) does not work; the page then shows these
instructions. Serve the **repository root** instead:

```sh
cd dancing-with-the-sars        # the repo root, not viz/
python -m http.server 8000
```

Then open <http://localhost:8000/viz/>.

The data is read from `../data/coryell/`, so the server must be started from
the repo root. An internet connection is needed for the basemaps, the WMS
layers and the MapLibre library.

## What you can do

- **Pan, zoom, home button** (zoom to all leaks). The map stays north-up.
  The view is kept in the URL (`#map=zoom/lat/lon`), so links reopen the same view.
- **Live cursor coordinates** (lat/lon and UTM, bottom right), metric and
  imperial **scale bars**, and a **coordinate grid** whose spacing adapts to
  the zoom, with labels on the top and left edges.
- **Leaks**: one dot per repair. Hover shows the details, click pins them.
  Colour by pipe size, water loss, cause or year; size by water loss or pipe
  size; switch between points, clusters and heatmap.
- **Leak risk by pipe** (top of the Layers list, on by default when its data
  exists): the pipe network cut into pieces of at most 250 m and coloured by
  where each piece ranks for the chosen month (top 1%, 5%, 20% of all
  pipe-months from Nov 2025 to Oct 2026). Pick the month in the layer row; in
  the NISAR passes tab it follows the selected pass. Click a piece for its
  rank, leak history and a 12-month strip. Leak popups in that period show
  where the leaking pipe stood in the ranking. The ranking uses past leaks and
  pipe attributes only, no radar: trained on Oct 2020 to Oct 2025, it reaches
  AUC 0.79 on the 12 held-out months, and the top 5% of pipe-months hold 32%
  of the leaks (report: `asen_results/data/reports/coryell_risk.md`). The
  diameter-coloured pipe layer is switched off while the risk layer loads;
  tick "Pipe network" to bring it back.
- **Time filter**: histogram of leaks per month for the current filters,
  a two-handle date slider (Sep 2019 to Nov 2026), presets (All,
  **NISAR window** from 2025-10-17, 2026, last 12 months), click a month bar to
  select that month, and **play** (or press space) to step a window through time.
- **Filters** for pipe size (with a "≥ 4″ only" shortcut) and cause. The count,
  summary tiles, legend counts and histogram follow the filters. Filtered-out
  leaks can stay visible as faint grey dots.
- **Basemaps and overlays** with legends and opacity sliders.
- **NISAR frames**: click a frame to see its track, direction, polarization
  and acquisition dates; the dates are also marked on the time histogram.
- **NISAR passes** tab (slice mode) and the **before/after radar viewer**:
  see the next section.
- Narrow screens get a slide-out panel.

## NISAR passes (slice mode) and the before/after viewer

The **NISAR passes** tab steps through the 24 passes of stack `041_D_073`
(track 41 descending, frame 73, CRID P05023, 2025-12-31 to 2026-10-15) and
shows which leaks were repaired shortly after each one.

- **Prev / Next** buttons, the **←/→ keys**, or a click on a date in the
  strip. Each date shows how many leaks fall in the current window (a dotted
  mark flags the 2026-07-27 to 08-10 data gap). On entering, the most recent
  pass with natural leaks in the window is selected.
- **Days after the pass**: a two-handle slider from 0 to 12 days (default
  0-6). Day *n* means repaired between *n* x 24 h and (*n*+1) x 24 h after
  the acquisition start time (about 01:18 UTC, which is 20:18 CDT / 19:18 CST
  the evening before the UTC date in the file name).
- **Also show leaks repaired up to N days before the pass**: hollow dots (on
  by default, N = 3). Their "after" chip is the current pass.
- **Natural leaks only** (default) and **pipes ≥ 4″ only**. All other leaks
  are grey dots (hide them with the "grey dots" option in the Leaks section).
- **District radar image of this pass**: if a district-wide image exists for
  the pass date (2026-08-28, 09-09, 09-21) it is switched on; for other dates
  nothing is shown and the chips are the radar view.
- The **list** under the controls has every leak in the window, sorted by
  time after the pass: offset, repair time (Central), pipe size, parsed loss,
  and how many of its 3 chips exist. Click a row (or a dot on the map) to
  select the leak, fly to it and open the viewer.

**Before/after viewer** (also from the "Radar before / after" button in any
leak popup of the NISAR window):

- Three 1.2 km chips at 10 m, side by side: **baseline** (the pass before
  "before"), **before** (last pass at or before the repair time) and
  **after** (first pass after it), each with its date and its time relative
  to the repair. The leak is marked with a 30 m ring (the stats disc), plus
  dashed 100 m and 300 m rings (the background annulus). Chips are north-up
  in the UTM grid.
- **False colour / HH / HV** toggle with a fixed, shared stretch (HH -22 to
  -3 dB, HV -28 to -11 dB, HH/HV 3 to 12 dB; the same as the district images
  and `scripts/render_gcov_png.py`).
- **On map: Off / Baseline / Before / After** puts that chip on the map at
  its true location (dashed square = chip footprint), with an opacity slider
  and **Blink**, which alternates before and after.
- **Stats (exploratory)**: mean gamma-0 within 30 m of the leak and in a
  100-300 m annulus, their difference (contrast), and the before − baseline
  and after − before changes. Speckle on a 30 m disc is about ±1 dB; regional
  wetting moves the disc and the annulus together (09-21 → 10-03: background
  HH +2.5 dB median), so prefer the contrast change.
- `–` minimises the viewer; `×` or Esc closes it.
- The popup's privacy rules still apply: the viewer shows only the ObjectId,
  repair time, cause, pipe size, parsed loss and zone.

Leaks within 200 m of each other share one chip footprint (a "site"), so
their marker is not always exactly in the centre.

### Regenerating the chips and district images

```sh
# chips + manifest (resumable: raw chips are cached as .npz in --cache-dir)
python scripts/make_leak_chips.py --cache-dir <scratch dir> --granules-csv <gcov_granules.csv> --workers 6
python scripts/make_leak_chips.py --cache-dir <scratch dir> --render-only     # re-render, no network
python scripts/make_leak_chips.py --cache-dir <scratch dir> --dates 2026-10-03   # refetch one pass
# district image for one pass: subset (about 180 MB transfer, 4 min), then render
python scripts/subset_gcov.py <granule .h5 URL> district.tif -97.900 31.342 -97.418 31.681
python scripts/render_gcov_png.py district.tif --out-dir data/coryell/nisar --boxcar 3 \
  --downsample 2 --products rgb --format webp --quality 85
```

Without `--granules-csv`, `make_leak_chips.py` reuses
`data/coryell/nisar/acquisitions_041D073.json` (or queries the ASF search
API). Earthdata login comes from `~/.netrc`. A full run reads 24 granules
(703 chips) in about 6 minutes with 6 workers and transfers about 1.4 GB.
To show a district image for another pass, render it and add its date to
`DISTRICT_DATES` in `config.js`.

## Privacy rules (built in)

- `Creator` and `Editor` (staff account names) are never read into the page.
- The notes of ObjectIds 469, 512, 535, 577, 768, 792 and 1473 name people;
  they are replaced by "withheld" at display time (the data file is unchanged).
  The list is `HIDE_NOTES_IDS` in `leaks.js`.
- The water-loss field is free text and a few entries name people ("… Bobby
  hit it"). The popup shows only the parsed number (for example "≈ 100 gpm",
  marked "parsed from crew text") and never the raw text.
- ObjectId 1611 (a test entry near Galveston) is dropped. ObjectId 564 has no
  date, so it only appears when the full time range is selected.
- The meter and parcel layers of the consultant's service (customer and owner
  names) are not used.

## Layers and sources

### Basemaps (one at a time)

| Basemap | Source | Licence / attribution |
|---|---|---|
| USGS imagery (default) | USGS The National Map, `USGSImageryOnly` (USDA NAIP aerial photos, ~0.6–1 m, refreshed 2024), native to z16 | Public domain. "USGS The National Map" |
| Esri World Imagery | `server.arcgisonline.com` World_Imagery, to z19 | Esri terms of use. "Esri, Maxar, Earthstar Geographics, and the GIS User Community" |
| Sentinel-2 cloudless 2024 | EOX `s2cloudless-2024_3857` (10 m, the scale of NISAR GCOV pixels) | CC BY-NC-SA 4.0. "Sentinel-2 cloudless 2024 by EOX IT Services GmbH (contains modified Copernicus Sentinel data 2024)" |
| USGS Topo | USGS The National Map, `USGSTopo` | Public domain |
| OpenTopoMap | `tile.opentopomap.org` | © OpenStreetMap contributors, SRTM; style © OpenTopoMap (CC BY-SA) |
| OpenStreetMap | `tile.openstreetmap.org` | © OpenStreetMap contributors (ODbL); follow the OSM tile usage policy (fine for a demo) |
| Dark gray | Esri Canvas `World_Dark_Gray_Base`, to z16 | Esri terms of use. "Esri, HERE, Garmin, © OpenStreetMap contributors, and the GIS user community" |

CARTO's dark basemap was tried first, but it now needs an API key.

### Overlays

| Layer | Source | Licence / attribution |
|---|---|---|
| Leaks | `data/coryell/leak_survey.geojson`, CCWSD Survey123 layer (see `data/coryell/README.md`) | No licence stated; credit the district |
| Pipe network | `data/coryell/waterlines.geojson`, 918 lines from the consultant layer `CCWSDWaterline2026` (Sept 2026, the newest and most complete copy). Width and colour by diameter; click for size, material, class, depth, install year, length | As above (district / OEI GIS) |
| Pressure zones | `data/coryell/pressure_zones.geojson`, 7 polygons (`CCWSD_Leak_Density_WFL1` layer 19). Click for area and leak count / density under the current filters | As above |
| NISAR district images | `data/coryell/nisar/gcov_041D073_{20260828,20260909,20260921}_district_rgb.webp`: whole district (about 46 x 39 km), 20 m, false colour (HH, HV, HH/HV). Off in Explore; slice mode shows the one matching the pass | NASA/JPL-Caltech, ISRO (ASF DAAC), CRID P05023 |
| NISAR Riddle subset | `data/coryell/nisar/gcov_041D073_20260909_riddle_*.png`, 10 m, off by default | As above |
| NISAR leak chips | `data/coryell/nisar/chips/*.png` + `leak_chips.json`, shown by the viewer | As above |
| NISAR GCOV frames | `data/coryell/nisar_gcov_footprints.geojson` (6 frames, made by another script in this repo). Orange = ascending, pink = descending | NASA/JPL-Caltech, ISRO; footprints from CMR / ASF DAAC |
| Hillshade | USGS The National Map `USGSShadedReliefOnly` (3DEP) | Public domain |
| Land cover, NLCD 2021 (30 m) | USGS/MRLC WMS `NLCD_2021_Land_Cover_L48` (`www.mrlc.gov/geoserver`). Separates pasture/hay, grassland, crops, shrub and forest | Public domain |
| Land cover, ESA WorldCover 2021 (10 m) | VITO Terrascope WMS `WORLDCOVER_2021_MAP` (`services.terrascope.be/wms/v2`) | CC BY 4.0, "© ESA WorldCover project 2021 / Contains modified Copernicus Sentinel data (2021) processed by the ESA WorldCover consortium" |
| Roads & places | Esri `Reference/World_Transportation` | Esri terms of use |

**WorldCover caveat:** `services.terrascope.be` resets the connection on the
network this was built on, so this layer could not be checked. If its tiles fail, the
layer row says "tiles failing"; use NLCD, which covers the same question
(grass vs crops vs trees vs built-up) for the US. The ESA WorldCover COGs on
AWS have no CORS headers, so the browser cannot read them directly.

Attribution for the visible layers is shown in the map's bottom-right corner
(the (i) button on small screens).

## Files

| File | Contents |
|---|---|
| `index.html` | Page layout and panel |
| `style.css` | Dark theme |
| `config.js` | **Basemaps and overlays.** Add layers here |
| `leaks.js` | Leak parsing (sizes, free-text water loss), privacy rules, filters, colour schemes |
| `graticule.js` | Adaptive lat/lon grid and the UTM conversion for the cursor readout |
| `app.js` | Map, UI and interaction |
| `slice.js` | NISAR passes (slice mode) and the before/after chip viewer |
| `risk.js` | Leak-risk layer: tier colours, month control, popups (data from `asen_results/src/terraguard/coryell_risk.py`) |

## Adding a NISAR layer

All overlays are entries in the `OVERLAYS` array in `config.js`, built with a
helper. The panel row, toggle, opacity slider, legend, attribution and drawing
order come for free. Rasters draw under the pipes and leaks; vector layers
draw above rasters. Within a group, earlier entries draw on top.

**0. A single false-colour image (what the map uses now).** A pre-rendered
image stretched over its corners is the simplest option and works with
`python -m http.server`. The `image()` helper does this. The district images
(`nisar-district-YYYYMMDD`, 20 m WebP, see "Regenerating" above) are made
this way. The older Riddle-only layers (`nisar-rgb`, `nisar-hh`, `nisar-hv`:
track 41 descending frame 73, 2026-09-09, 10 m, now off by default) were
made with:

```sh
python scripts/render_gcov_png.py data/coryell/nisar/gcov_041D073_20260909_riddle.tif \
  --out-dir data/coryell/nisar --boxcar 3
```

The script boxcar-filters the linear power, converts to dB, reprojects to
EPSG:3857, and writes `<stem>_rgb.png` (R = HH, G = HV, B = HH/HV ratio),
`<stem>_hh.png` (magma), `<stem>_hv.png` (viridis) and `<stem>.json`, which
holds the corner coordinates to paste into `config.js`. Display ranges are
fixed (HH -22..-3 dB, HV -28..-11 dB, ratio 3..12 dB), so images from
different dates render with comparable colours. To add another date, subset
it the same way, run the script, and copy one of the `image({...})` entries.

**1. XYZ tiles** (better for large areas). Reproject the GCOV band to Web
Mercator, scale it to 8-bit, and cut tiles:

```sh
# HH backscatter (linear power) -> dB, Web Mercator, 8-bit (-25..0 dB)
gdalwarp -t_srs EPSG:3857 -r average HDF5:"GCOV.h5"://science/LSAR/GCOV/grids/frequencyA/HHHH hh_3857.tif
gdal_calc.py -A hh_3857.tif --calc="10*log10(A)" --outfile hh_db.tif --NoDataValue=-9999
gdal_translate -scale -25 0 1 255 -ot Byte -a_nodata 0 hh_db.tif hh_byte.tif
gdal2tiles.py --xyz -z 9-15 hh_byte.tif data/coryell/tiles/gcov_hh_20260915
```

```js
xyz({
  id: 'nisar-hh-20260915', title: 'NISAR HH, 15 Sep 2026', group: 'NISAR', visible: true, opacity: 0.8,
  tiles: ['../data/coryell/tiles/gcov_hh_20260915/{z}/{x}/{y}.png'], maxzoom: 15,
  attribution: 'NISAR data: NASA/JPL-Caltech, ISRO (ASF DAAC)',
  legend: { type: 'ramp', colors: ['#000', '#fff'], labels: ['-25 dB', '0 dB'] },
}),
```

Use `--xyz`: without it gdal2tiles writes TMS (flipped y) tiles.

**2. Cloud-Optimized GeoTIFF** read in the browser, no tiling step. The file
must be in **EPSG:3857** (the plugin does not reproject):

```sh
gdalwarp -t_srs EPSG:3857 -of COG -co BLOCKSIZE=256 -co COMPRESS=DEFLATE hh_db.tif hh_db_3857_cog.tif
```

```js
cog({
  id: 'nisar-hh-cog', title: 'NISAR HH (COG)', group: 'NISAR', visible: true, opacity: 0.8,
  url: 'http://localhost:8000/data/coryell/hh_db_3857_cog.tif',
  colorRamp: 'BrewerGreys9,-25,0,c',   // "#color:" spec of maplibre-cog-protocol, min/max in data units
  attribution: 'NISAR data: NASA/JPL-Caltech, ISRO (ASF DAAC)',
  legend: { type: 'ramp', colors: ['#000', '#fff'], labels: ['-25 dB', '0 dB'] },
}),
```

The [maplibre-cog-protocol](https://github.com/geomatico/maplibre-cog-protocol)
plugin (0.10.0, MIT) is loaded only when a `cog()` layer is configured; it was
tested with this MapLibre version on the plugin's demo COG. COGs need HTTP
range requests, which Python's `http.server` does **not** support. Serve
with `npx http-server -p 8000 --cors` from the repo root, or host the file
anywhere that supports ranges and CORS (S3, a GitHub release, ...).

**3. GeoJSON** (footprints, change polygons, detections):

```js
geojson({
  id: 'nisar-detections', title: 'Wet-soil detections', group: 'NISAR', visible: true,
  url: '../data/coryell/detections.geojson',
  optional: true,                       // "not available yet" instead of an error if missing
  popup: 'generic',                     // click shows the feature's properties
  legend: { type: 'fills', items: [['#00e5ff', 'Detection']] },
  layers: [
    { type: 'fill', paint: { 'fill-color': '#00e5ff', 'fill-opacity': 0.35 } },
    { type: 'line', paint: { 'line-color': '#00e5ff', 'line-width': 1.5 } },
  ],
}),
```

**4. WMS** (e.g. a GeoServer or ASF/NASA GIBS endpoint): `wms({ id, title, url, layer, ... })`.

Two commented examples (`nisar-hh`, `nisar-hh-cog`) are already in
`config.js`; uncomment one and change the path. Keep large rasters and tile
folders out of git (add them to `.gitignore`, or host them elsewhere).

### NISAR footprints

`nisar_gcov_footprints.geojson` is listed as an optional layer. If the file is
missing, the row reads "not available yet" and nothing breaks. When the file
is present it loads automatically, off by default. The frame popup reads
`stack`, `track`, `direction`, `frame`, `polarization`, `pixel_spacing_m`,
`n_dates`, `first_date`, `last_date`, `dates`, `leaks_inside` and
`leak_bbox_fraction_covered`; with other fields it falls back to a generic
property table.

## Known limits

- Times are converted from UTC to US Central (CST/CDT) in the browser.
- Water loss is the crew's estimate, parsed from free text (`5gpm`, `5 gpm`,
  `40 gallons a minute`, `30gpm/escalated to 800gpm` → 800). "Unsure" is
  shown as unknown.
- The NISAR window preset starts on 2025-10-17, the first NISAR science data.
- WorldCover could not be checked from this network (see above).
