// Layer configuration for the Coryell leak map.
//
// Everything that is "a layer on the map" (except the leaks themselves, which
// have their own filters and styling in leaks.js) is declared here. To add a
// layer, append an entry to OVERLAYS using one of the helpers below:
//
//   xyz({...})      raster XYZ / TMS tiles  ({z}/{x}/{y} URL template)
//   wms({...})      a WMS GetMap layer, requested as 256 px Web Mercator tiles
//   cog({...})      a Cloud-Optimized GeoTIFF (must be EPSG:3857), read in the
//                   browser with HTTP range requests (maplibre-cog-protocol)
//   geojson({...})  a GeoJSON file (points, lines or polygons)
//
// See README.md, "Adding a NISAR layer", for worked examples.

// Paths are relative to viz/index.html; serve the repo root (see README.md).
const DATA = '../data/coryell/';

export const MAP_DEFAULTS = {
  // Leak extent (ObjectId 1611 near Galveston excluded), used for the first view.
  bounds: [[-97.8906, 31.3479], [-97.4227, 31.7064]],
  basemap: 'usgs-imagery',
  glyphs: 'https://demotiles.maplibre.org/font/{fontstack}/{range}.pbf',
  font: ['Open Sans Semibold'],
};

// ---------------------------------------------------------------- basemaps --
// One is visible at a time. `maxzoom` is the deepest native zoom of the tile
// service; MapLibre over-zooms beyond it.
export const BASEMAPS = [
  {
    id: 'usgs-imagery',
    title: 'USGS imagery',
    note: 'USDA NAIP aerial photos, ~1 m. Public domain.',
    group: 'Imagery',
    tiles: ['https://basemap.nationalmap.gov/arcgis/rest/services/USGSImageryOnly/MapServer/tile/{z}/{y}/{x}'],
    maxzoom: 16,
    attribution: 'Imagery: <a href="https://www.usgs.gov/programs/national-geospatial-program/national-map" target="_blank" rel="noopener">USGS The National Map</a> (USDA NAIP), public domain',
  },
  {
    id: 'esri-imagery',
    title: 'Esri World Imagery',
    note: 'Sharpest at street level (to ~0.3 m). Esri terms of use.',
    group: 'Imagery',
    tiles: ['https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'],
    maxzoom: 19,
    attribution: 'Imagery: <a href="https://www.esri.com/" target="_blank" rel="noopener">Esri</a>, Maxar, Earthstar Geographics, and the GIS User Community',
  },
  {
    id: 'eox-s2',
    title: 'Sentinel-2 cloudless 2024',
    note: '10 m mosaic, same scale as radar. CC BY-NC-SA 4.0.',
    group: 'Imagery',
    tiles: ['https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless-2024_3857/default/g/{z}/{y}/{x}.jpg'],
    maxzoom: 15,
    attribution: '<a href="https://s2maps.eu" target="_blank" rel="noopener">Sentinel-2 cloudless 2024</a> by EOX IT Services GmbH (contains modified Copernicus Sentinel data 2024), CC BY-NC-SA 4.0',
  },
  {
    id: 'usgs-topo',
    title: 'USGS Topo',
    note: 'US topographic map with contours. Public domain.',
    group: 'Maps',
    tiles: ['https://basemap.nationalmap.gov/arcgis/rest/services/USGSTopo/MapServer/tile/{z}/{y}/{x}'],
    maxzoom: 16,
    attribution: 'Map: <a href="https://www.usgs.gov/programs/national-geospatial-program/national-map" target="_blank" rel="noopener">USGS The National Map</a>, public domain',
  },
  {
    id: 'opentopomap',
    title: 'OpenTopoMap',
    note: 'OSM-based topographic map. CC BY-SA.',
    group: 'Maps',
    tiles: ['https://a.tile.opentopomap.org/{z}/{x}/{y}.png', 'https://b.tile.opentopomap.org/{z}/{x}/{y}.png', 'https://c.tile.opentopomap.org/{z}/{x}/{y}.png'],
    maxzoom: 17,
    attribution: 'Map data &copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a> contributors, SRTM | Style &copy; <a href="https://opentopomap.org" target="_blank" rel="noopener">OpenTopoMap</a> (CC BY-SA)',
  },
  {
    id: 'osm',
    title: 'OpenStreetMap',
    note: 'Standard street map. ODbL.',
    group: 'Maps',
    tiles: ['https://tile.openstreetmap.org/{z}/{x}/{y}.png'],
    maxzoom: 19,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a> contributors',
  },
  {
    id: 'esri-dark',
    title: 'Dark gray',
    note: 'Muted canvas that lets the data stand out. Esri terms of use.',
    group: 'Maps',
    tiles: ['https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}'],
    maxzoom: 16,
    attribution: 'Base map: <a href="https://www.esri.com/" target="_blank" rel="noopener">Esri</a>, HERE, Garmin, &copy; OpenStreetMap contributors, and the GIS user community',
  },
];

// ------------------------------------------------------------ helpers ------

/** Raster XYZ tiles. */
export function xyz({ id, title, tiles, attribution, maxzoom = 22, opacity = 1, tileSize = 256, ...rest }) {
  return {
    id, title, opacity, z: 'raster', ...rest,
    sources: { [id]: { type: 'raster', tiles, tileSize, maxzoom, attribution } },
    layers: [{ id, type: 'raster', source: id, paint: { 'raster-opacity': 1 } }],
  };
}

/** WMS layer, fetched as 256 px tiles in EPSG:3857. */
export function wms({ id, title, url, layer, styles = '', version = '1.1.1', format = 'image/png', ...rest }) {
  const crsKey = version === '1.3.0' ? 'CRS' : 'SRS';
  const q = `SERVICE=WMS&VERSION=${version}&REQUEST=GetMap&LAYERS=${encodeURIComponent(layer)}&STYLES=${styles}` +
    `&${crsKey}=EPSG:3857&BBOX={bbox-epsg-3857}&WIDTH=256&HEIGHT=256&FORMAT=${encodeURIComponent(format)}&TRANSPARENT=true`;
  return xyz({ id, title, tiles: [`${url}${url.includes('?') ? '&' : '?'}${q}`], ...rest });
}

/**
 * Cloud-Optimized GeoTIFF read in the browser. The file must be in EPSG:3857
 * and served by a host that supports HTTP range requests (and CORS if it is
 * on another origin). Python's http.server does NOT do range requests; use
 * `npx http-server` locally, or object storage (S3, GitHub release, ...).
 * `colorRamp` is the maplibre-cog-protocol "#color:" spec for single-band
 * data, e.g. 'BrewerGreys9,-25,0,c' for backscatter in dB.
 */
export function cog({ id, title, url, colorRamp, ...rest }) {
  const hash = colorRamp ? `#color:${colorRamp}` : '';
  return {
    id, title, z: 'raster', needsCog: true, opacity: 1, ...rest,
    sources: { [id]: { type: 'raster', url: `cog://${url}${hash}`, tileSize: 256 } },
    layers: [{ id, type: 'raster', source: id, paint: { 'raster-opacity': 1 } }],
  };
}

/**
 * A single georeferenced image (PNG/JPG) stretched over four lon/lat corners
 * [top-left, top-right, bottom-right, bottom-left]. The image must already be
 * in Web Mercator (EPSG:3857) so it lines up. Works with python http.server.
 * scripts/render_gcov_png.py writes such PNGs plus a JSON with the corners.
 */
export function image({ id, title, url, coordinates, ...rest }) {
  return {
    id, title, z: 'raster', opacity: 1, ...rest,
    sources: { [id]: { type: 'image', url: new URL(url, window.location.href).href, coordinates } },
    layers: [{ id, type: 'raster', source: id, paint: { 'raster-opacity': 1, 'raster-fade-duration': 0, 'raster-resampling': 'nearest' } }],
  };
}

/**
 * GeoJSON overlay. `layers` are MapLibre style layers without `source`
 * (filled in automatically). `optional: true` means the file may not exist
 * yet: the layer is then listed as "not available" instead of failing.
 */
export function geojson({ id, title, url, layers, optional = false, promoteId, ...rest }) {
  return {
    id, title, z: 'vector', optional, url, opacity: 1, ...rest,
    // `data` is fetched by app.js (so that missing optional files and `transform` work).
    sources: { [id]: { type: 'geojson', data: url, ...(promoteId ? { promoteId } : {}) } },
    layers: layers.map((l, i) => ({ id: l.id || `${id}-${i}`, source: id, ...l })),
  };
}

// --------------------------------------------------------------- styling ----

// Pipe diameter (inches) bins, shared by the legend and the line style.
export const PIPE_BINS = [
  { max: 1,   label: '≤ 1″',     color: '#d4f3ff', width: 1.0 },
  { max: 2,   label: '1½–2″',    color: '#8ee0ff', width: 1.6 },
  { max: 3,   label: '2½–3″',    color: '#45c3f2', width: 2.3 },
  { max: 6,   label: '4–6″',     color: '#2f8bff', width: 3.2 },
  { max: 99,  label: '8–10″',    color: '#7b6bff', width: 4.4 },
];
// `dia` is added by the pipes `transform` below (Diameter, or parsed from Size).
const pipeDiameter = ['coalesce', ['get', 'dia'], 0];
const pipeStep = (key) => ['step', pipeDiameter, PIPE_BINS[0][key], 1.01, PIPE_BINS[1][key], 2.01, PIPE_BINS[2][key], 3.01, PIPE_BINS[3][key], 6.01, PIPE_BINS[4][key]];

export const ZONE_COLORS = {
  'Pancake Plane': '#f2b134', 'Riddle Plane': '#5ad1a4', 'Crawford Plane': '#e86f8a',
  'Coryell City Plane': '#8f9cff', 'Mound Plane': '#d48cf0', 'Levita Plane': '#7fd6ff',
  'Ranch Addition Plane': '#f5e663',
};
const zoneColor = ['match', ['get', 'Name'], ...Object.entries(ZONE_COLORS).flat(), '#cccccc'];

const NISAR_DIR = ['match', ['get', 'direction'], 'ASCENDING', '#ff9f1c', 'DESCENDING', '#f15bb5', '#ff9f1c'];

// NLCD 2021 classes present around Gatesville (official NLCD colours).
const NLCD_LEGEND = [
  ['#466b9f', 'Open water'], ['#dec5c5', 'Developed, open space'], ['#d99282', 'Developed, low'],
  ['#eb0000', 'Developed, medium'], ['#ab0000', 'Developed, high'], ['#b3ac9f', 'Barren'],
  ['#68ab5f', 'Deciduous forest'], ['#1c5f2c', 'Evergreen forest'], ['#b5c58f', 'Mixed forest'],
  ['#ccb879', 'Shrub / scrub'], ['#dfdfc2', 'Grassland'], ['#dcd939', 'Pasture / hay'],
  ['#ab6c28', 'Cultivated crops'], ['#b8d9eb', 'Woody wetlands'], ['#6c9fb8', 'Herbaceous wetlands'],
];
const WORLDCOVER_LEGEND = [
  ['#006400', 'Tree cover'], ['#ffbb22', 'Shrubland'], ['#ffff4c', 'Grassland'], ['#f096ff', 'Cropland'],
  ['#fa0000', 'Built-up'], ['#b4b4b4', 'Bare / sparse'], ['#0064c8', 'Water'], ['#0096a0', 'Herbaceous wetland'],
];

// District-wide NISAR images (scripts/render_gcov_png.py --downsample 2 --format webp).
// All three share one grid, so one set of corners (from gcov_041D073_<date>_district.json).
const DISTRICT_DATES = ['2026-08-28', '2026-09-09', '2026-09-21'];
const DISTRICT_CORNERS = [[-97.90398322757241, 31.68611024477773], [-97.41230638527239, 31.68611024477773],
  [-97.41230638527239, 31.33692130847318], [-97.90398322757241, 31.33692130847318]];
/** Pass date (UTC) -> overlay id; slice mode shows the matching image. */
export const PASS_OVERLAYS = Object.fromEntries(DISTRICT_DATES.map((d) => [d, `nisar-district-${d.replace(/-/g, '')}`]));

// -------------------------------------------------------------- overlays ----
// Listed top to bottom as they appear in the panel. Raster overlays draw under
// vector overlays, which draw under the leaks.
export const OVERLAYS = [
  geojson({
    id: 'pipes',
    title: 'Pipe network',
    group: 'District',
    visible: true,
    url: DATA + 'waterlines.geojson',
    info: 'CCWSD water lines, 918 segments (consultant layer "CCWSDWaterline2026", Sept 2026). Click a line for its attributes.',
    attribution: 'Pipes &amp; zones: Coryell City WSD / OEI GIS',
    legend: { type: 'lines', items: PIPE_BINS.map((b) => [b.color, b.label, b.width]) },
    popup: 'pipe',
    // Diameter is numeric in the 2026 layer but blank on some lines; fall back to Size ('1.5"').
    transform: (fc) => {
      for (const f of fc.features) {
        const p = f.properties;
        p.dia = Number.isFinite(p.Diameter) ? p.Diameter : (parseFloat(p.Size) || null);
      }
      return fc;
    },
    layers: [
      { id: 'pipes-casing', type: 'line', layout: { 'line-cap': 'round', 'line-join': 'round' },
        paint: { 'line-color': '#04121c', 'line-opacity': 0.55,
          'line-width': ['interpolate', ['linear'], ['zoom'], 9, ['+', 1.2, ['*', 0.5, pipeStep('width')]], 15, ['+', 2.5, ['*', 1.6, pipeStep('width')]]] } },
      { id: 'pipes-line', type: 'line', layout: { 'line-cap': 'round', 'line-join': 'round' },
        paint: { 'line-color': pipeStep('color'),
          'line-width': ['interpolate', ['linear'], ['zoom'], 9, ['*', 0.5, pipeStep('width')], 15, ['*', 1.6, pipeStep('width')]] } },
    ],
  }),
  geojson({
    id: 'zones',
    title: 'Pressure zones',
    group: 'District',
    visible: false,
    url: DATA + 'pressure_zones.geojson',
    info: 'The 7 pressure planes of the district (consultant layer "Coryell Pressure Planes"). Click a zone for leak counts.',
    attribution: 'Pipes &amp; zones: Coryell City WSD / OEI GIS',
    legend: { type: 'fills', items: Object.entries(ZONE_COLORS).map(([k, c]) => [c, k.replace(' Plane', '')]) },
    popup: 'zone',
    layers: [
      { id: 'zones-fill', type: 'fill', paint: { 'fill-color': zoneColor, 'fill-opacity': 0.16 } },
      { id: 'zones-line', type: 'line', paint: { 'line-color': zoneColor, 'line-width': 1.6, 'line-opacity': 0.95 } },
      { id: 'zones-label', type: 'symbol',
        layout: { 'text-field': ['get', 'Name'], 'text-font': MAP_DEFAULTS.font, 'text-size': 12, 'text-transform': 'uppercase', 'text-letter-spacing': 0.08 },
        paint: { 'text-color': zoneColor, 'text-halo-color': 'rgba(8,12,18,0.9)', 'text-halo-width': 1.4 } },
    ],
  }),
  geojson({
    id: 'nisar-footprints',
    title: 'NISAR GCOV frames',
    group: 'NISAR',
    visible: false,
    optional: true, // listed as "not available yet" if the file is missing
    url: DATA + 'nisar_gcov_footprints.geojson',
    info: 'Footprints of the NISAR L2 GCOV frames (track_direction_frame) over the district. Click a frame: its acquisition dates are marked on the time histogram.',
    attribution: 'NISAR footprints: NASA/JPL-Caltech, ISRO (ASF DAAC, CMR)',
    legend: { type: 'lines', items: [['#ff9f1c', 'Ascending', 2], ['#f15bb5', 'Descending', 2]] },
    popup: 'nisar',
    layers: [
      { id: 'nisar-fp-fill', type: 'fill', paint: { 'fill-color': NISAR_DIR, 'fill-opacity': 0.04 } },
      { id: 'nisar-fp-line', type: 'line', paint: { 'line-color': NISAR_DIR, 'line-width': 1.6, 'line-dasharray': [4, 2] } },
      { id: 'nisar-fp-label', type: 'symbol',
        layout: { 'symbol-placement': 'line', 'text-field': ['coalesce', ['get', 'stack'], ''], 'text-font': MAP_DEFAULTS.font, 'text-size': 11, 'symbol-spacing': 400, 'text-offset': [0, -0.7] },
        paint: { 'text-color': NISAR_DIR, 'text-halo-color': 'rgba(8,12,18,0.9)', 'text-halo-width': 1.3 } },
    ],
  }),
  // --- NISAR GCOV, whole district, track 41 descending frame 73 ------------
  // 20 m (3x3 boxcar at 10 m, then 2x2 average of linear power), false colour,
  // made with scripts/subset_gcov.py + scripts/render_gcov_png.py (see README).
  // Slice mode ("NISAR passes") switches these on for the matching pass date.
  ...DISTRICT_DATES.map((d) => image({
    id: `nisar-district-${d.replace(/-/g, '')}`,
    title: `NISAR district ${d} (false colour, 20 m)`,
    group: 'NISAR', visible: false, opacity: 0.85,
    url: DATA + `nisar/gcov_041D073_${d.replace(/-/g, '')}_district_rgb.webp`,
    coordinates: DISTRICT_CORNERS,
    attribution: 'NISAR GCOV: NASA/JPL-Caltech, ISRO (ASF DAAC), P05023',
    info: `NISAR GCOV ${d} (evening pass the day before, about 20:18 CDT), track 41 descending, frame 73, CRID P05023, whole district ` +
      '(about 46 x 39 km) at 20 m. Red = HH (-22 to -3 dB), green = HV (-28 to -11 dB), blue = HH/HV ratio (3 to 12 dB); same stretch as the chips. ' +
      'Data: NASA/JPL-Caltech, ISRO (ASF DAAC).',
    legend: { type: 'fills', items: [['#ff3b3b', 'R: HH (surface)'], ['#3bff6a', 'G: HV (vegetation volume)'], ['#3b8bff', 'B: HH/HV ratio']] },
  })),
  // --- NISAR GCOV backscatter, track 41 descending frame 73, 2026-09-09 -----
  // Riddle cluster subset only (10 m). Off by default: the district images
  // above cover it (at 20 m) and the leak chips cover each leak at 10 m. Rendered by scripts/render_gcov_png.py from
  // data/coryell/nisar/gcov_041D073_20260909_riddle.tif (3x3 boxcar, then dB).
  // Corners and stretch ranges: data/coryell/nisar/gcov_041D073_20260909_riddle.json
  ...(() => {
    const corners = [[-97.5716333474374, 31.499715596324812], [-97.50818752163184, 31.499715596324812],
      [-97.50818752163184, 31.430201276538096], [-97.5716333474374, 31.430201276538096]];
    const base = DATA + 'nisar/gcov_041D073_20260909_riddle';
    const attribution = 'NISAR GCOV: NASA/JPL-Caltech, ISRO (ASF DAAC), P05023';
    const when = 'NISAR GCOV, 2026-09-09 (evening pass 2026-09-08 20:18 CDT), track 41 descending, frame 73, 10 m, Riddle cluster subset. Data: NASA/JPL-Caltech, ISRO (ASF DAAC), CRID P05023.';
    return [
      image({
        id: 'nisar-rgb', title: 'NISAR Riddle 2026-09-09, 10 m (false colour)', group: 'NISAR', visible: false, opacity: 0.85,
        url: base + '_rgb.png', coordinates: corners, attribution,
        info: `${when} Red = HH (-22 to -3 dB), green = HV (-28 to -11 dB), blue = HH/HV ratio (3 to 12 dB). ` +
          'Purple/blue: smooth or bare ground (strong HH, weak HV). Green/yellow: trees and shrubs (volume scattering lifts HV). ' +
          'Bright pink/white: buildings, fences and other hard edges. Wetter soil raises HH more than HV.',
        legend: { type: 'fills', items: [['#ff3b3b', 'R: HH (surface)'], ['#3bff6a', 'G: HV (vegetation volume)'], ['#3b8bff', 'B: HH/HV ratio']] },
      }),
      image({
        id: 'nisar-hh', title: 'NISAR Riddle 2026-09-09, 10 m (HH, magma)', group: 'NISAR', visible: false, opacity: 0.85,
        url: base + '_hh.png', coordinates: corners, attribution,
        info: `${when} Co-polarized backscatter; most sensitive to soil moisture and surface roughness.`,
        legend: { type: 'ramp', colors: ['#000004', '#4f127b', '#b5367a', '#fb8761', '#fcfdbf'], labels: ['-22 dB', '-3 dB'] },
      }),
      image({
        id: 'nisar-hv', title: 'NISAR Riddle 2026-09-09, 10 m (HV, viridis)', group: 'NISAR', visible: false, opacity: 0.85,
        url: base + '_hv.png', coordinates: corners, attribution,
        info: `${when} Cross-polarized backscatter; mostly vegetation volume.`,
        legend: { type: 'ramp', colors: ['#440154', '#3b528b', '#21918c', '#5ec962', '#fde725'], labels: ['-28 dB', '-11 dB'] },
      }),
    ];
  })(),
  // --- Example NISAR raster layers. Uncomment and point at your file. -------
  // xyz({
  //   id: 'nisar-hh', title: 'NISAR GCOV HH (dB)', group: 'NISAR', visible: true, opacity: 0.8,
  //   tiles: ['../data/coryell/tiles/gcov_hh_20260915/{z}/{x}/{y}.png'], maxzoom: 15,
  //   attribution: 'NISAR data: NASA/JPL-Caltech, ISRO (ASF DAAC)',
  //   legend: { type: 'ramp', colors: ['#000000', '#ffffff'], labels: ['-25 dB', '0 dB'] },
  // }),
  // cog({
  //   id: 'nisar-hh-cog', title: 'NISAR GCOV HH (COG)', group: 'NISAR', visible: true, opacity: 0.8,
  //   url: 'http://localhost:8000/data/coryell/gcov_hh_20260915_3857.tif', colorRamp: 'BrewerGreys9,-25,0,c',
  //   attribution: 'NISAR data: NASA/JPL-Caltech, ISRO (ASF DAAC)',
  //   legend: { type: 'ramp', colors: ['#000000', '#ffffff'], labels: ['-25 dB', '0 dB'] },
  // }),
  xyz({
    id: 'hillshade',
    title: 'Hillshade (USGS 3DEP)',
    group: 'Context',
    visible: false,
    opacity: 0.45,
    tiles: ['https://basemap.nationalmap.gov/arcgis/rest/services/USGSShadedReliefOnly/MapServer/tile/{z}/{y}/{x}'],
    maxzoom: 16,
    info: 'Shaded relief from the 3D Elevation Program, drawn over land cover. Shows the creek valleys where water collects.',
    attribution: 'Relief: USGS The National Map 3DEP, public domain',
    legend: { type: 'ramp', colors: ['#222', '#eee'], labels: ['shadow', 'lit'] },
  }),
  wms({
    id: 'nlcd',
    title: 'Land cover (NLCD 2021, 30 m)',
    group: 'Context',
    visible: false,
    opacity: 0.7,
    url: 'https://www.mrlc.gov/geoserver/mrlc_display/NLCD_2021_Land_Cover_L48/wms',
    layer: 'NLCD_2021_Land_Cover_L48',
    info: 'USGS / MRLC National Land Cover Database 2021. Separates pasture/hay from grassland and crops, which matters for radar soil-moisture signals.',
    attribution: 'Land cover: <a href="https://www.mrlc.gov/" target="_blank" rel="noopener">USGS / MRLC NLCD 2021</a>, public domain',
    legend: { type: 'fills', items: NLCD_LEGEND },
  }),
  wms({
    id: 'worldcover',
    title: 'Land cover (ESA WorldCover 2021, 10 m)',
    group: 'Context',
    visible: false,
    opacity: 0.7,
    url: 'https://services.terrascope.be/wms/v2',
    layer: 'WORLDCOVER_2021_MAP',
    info: 'ESA WorldCover 10 m, via VITO Terrascope WMS. Some networks block this host; if tiles stay blank, use NLCD.',
    attribution: 'Land cover: &copy; ESA WorldCover project 2021 / Contains modified Copernicus Sentinel data (2021) processed by the ESA WorldCover consortium, CC BY 4.0',
    legend: { type: 'fills', items: WORLDCOVER_LEGEND },
  }),
  xyz({
    id: 'labels',
    title: 'Roads & places',
    group: 'Context',
    visible: false,
    tiles: ['https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Transportation/MapServer/tile/{z}/{y}/{x}'],
    maxzoom: 19,
    z: 'vector', // draws above polygons so roads stay readable on imagery
    info: 'Esri transportation reference overlay, useful on top of imagery.',
    attribution: 'Roads: Esri, HERE, Garmin, &copy; OpenStreetMap contributors',
  }),
];
