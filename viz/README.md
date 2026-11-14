# Coryell leak map

Interactive web map of the water leak repairs logged by the Coryell City Water
Supply District (central Texas), with the district's pipe network, pressure
zones, land cover and NISAR frame footprints. It is the base for adding NISAR
radar layers.

Plain HTML/CSS/JS with [MapLibre GL JS](https://maplibre.org/) 4.7.1 from a CDN.
No build step and nothing to install.

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
- Narrow screens get a slide-out panel.

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

## Adding a NISAR layer

All overlays are entries in the `OVERLAYS` array in `config.js`, built with a
helper. The panel row, toggle, opacity slider, legend, attribution and drawing
order come for free. Rasters draw under the pipes and leaks; vector layers
draw above rasters. Within a group, earlier entries draw on top.

**1. XYZ tiles** (simplest for a demo). Reproject the GCOV band to Web
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
