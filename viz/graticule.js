// Graticule (lat/lon grid with edge labels, spacing adapts to zoom) and
// coordinate helpers. The map is kept north-up, so meridians are vertical and
// parallels horizontal on screen, which keeps the edge labels simple.

const STEPS = [30, 20, 10, 5, 2, 1, 0.5, 0.25, 0.2, 0.1, 0.05, 0.025, 0.02, 0.01, 0.005, 0.0025, 0.002, 0.001, 0.0005, 0.00025];

function pickStep(spanDeg, targetLines) {
  for (const s of STEPS) if (spanDeg / s >= targetLines) return s;
  return STEPS[STEPS.length - 1];
}

const decimals = (step) => Math.max(0, Math.min(5, Math.ceil(-Math.log10(step) - 1e-9) + (String(step).includes('25') ? 1 : 0)));

export function fmtLon(lon, d = 4) {
  const v = Math.abs(lon).toFixed(d);
  return `${v}°${lon < 0 ? 'W' : lon > 0 ? 'E' : ''}`;
}
export function fmtLat(lat, d = 4) {
  const v = Math.abs(lat).toFixed(d);
  return `${v}°${lat < 0 ? 'S' : lat > 0 ? 'N' : ''}`;
}

export class Graticule {
  constructor(map, { color = 'rgba(255,255,255,0.35)', beforeId } = {}) {
    this.map = map;
    this.visible = true;
    this.labels = document.createElement('div');
    this.labels.className = 'graticule-labels';
    map.getContainer().appendChild(this.labels);
    map.addSource('graticule', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });
    map.addLayer({
      id: 'graticule', type: 'line', source: 'graticule',
      paint: { 'line-color': color, 'line-width': 0.8, 'line-dasharray': [4, 3] },
    }, beforeId);
    this._raf = null;
    const schedule = () => {
      if (this._raf) return;
      this._raf = requestAnimationFrame(() => { this._raf = null; this.update(); });
    };
    map.on('move', schedule);
    map.on('resize', schedule);
    this.update();
  }

  setVisible(v) {
    this.visible = v;
    this.map.setLayoutProperty('graticule', 'visibility', v ? 'visible' : 'none');
    this.labels.style.display = v ? '' : 'none';
    if (v) this.update();
  }

  update() {
    if (!this.visible) return;
    const map = this.map;
    const b = map.getBounds();
    const w = map.getContainer().clientWidth;
    const h = map.getContainer().clientHeight;
    const west = b.getWest(), east = b.getEast(), south = b.getSouth(), north = b.getNorth();
    // Same step for both axes; aim for roughly one line per ~140 px of width.
    const step = pickStep(east - west, Math.max(3, Math.round(w / 160)));
    const d = decimals(step);
    const features = [];
    let html = '';
    const lon0 = Math.ceil(west / step) * step;
    for (let lon = lon0; lon <= east; lon += step) {
      const L = +lon.toFixed(8);
      features.push({ type: 'Feature', geometry: { type: 'LineString', coordinates: [[L, Math.max(south - 1, -85)], [L, Math.min(north + 1, 85)]] } });
      const x = map.project([L, (north + south) / 2]).x;
      if (x > 34 && x < w - 34) html += `<span class="gl gl-top" style="left:${x.toFixed(1)}px">${fmtLon(L, d)}</span>`;
    }
    const lat0 = Math.ceil(south / step) * step;
    for (let lat = lat0; lat <= north; lat += step) {
      const L = +lat.toFixed(8);
      // Densify so the line follows the projection when panning far.
      features.push({ type: 'Feature', geometry: { type: 'LineString', coordinates: [[west - 1, L], [(west + east) / 2, L], [east + 1, L]] } });
      const y = map.project([(west + east) / 2, L]).y;
      if (y > 24 && y < h - 64) html += `<span class="gl gl-left" style="top:${y.toFixed(1)}px">${fmtLat(L, d)}</span>`;
    }
    map.getSource('graticule').setData({ type: 'FeatureCollection', features });
    this.labels.innerHTML = html;
  }
}

/** WGS 84 lat/lon -> UTM (zone, easting, northing). Standard Snyder series. */
export function toUTM(lat, lon) {
  const a = 6378137, f = 1 / 298.257223563, k0 = 0.9996;
  const e2 = f * (2 - f), ep2 = e2 / (1 - e2);
  const zone = Math.floor((lon + 180) / 6) + 1;
  const lon0 = ((zone - 1) * 6 - 180 + 3) * Math.PI / 180;
  const phi = lat * Math.PI / 180, lam = lon * Math.PI / 180;
  const N = a / Math.sqrt(1 - e2 * Math.sin(phi) ** 2);
  const T = Math.tan(phi) ** 2, C = ep2 * Math.cos(phi) ** 2, A = Math.cos(phi) * (lam - lon0);
  const M = a * ((1 - e2 / 4 - 3 * e2 ** 2 / 64 - 5 * e2 ** 3 / 256) * phi
    - (3 * e2 / 8 + 3 * e2 ** 2 / 32 + 45 * e2 ** 3 / 1024) * Math.sin(2 * phi)
    + (15 * e2 ** 2 / 256 + 45 * e2 ** 3 / 1024) * Math.sin(4 * phi)
    - (35 * e2 ** 3 / 3072) * Math.sin(6 * phi));
  const E = k0 * N * (A + (1 - T + C) * A ** 3 / 6 + (5 - 18 * T + T ** 2 + 72 * C - 58 * ep2) * A ** 5 / 120) + 500000;
  let Nn = k0 * (M + N * Math.tan(phi) * (A ** 2 / 2 + (5 - T + 9 * C + 4 * C ** 2) * A ** 4 / 24
    + (61 - 58 * T + T ** 2 + 600 * C - 330 * ep2) * A ** 6 / 720));
  if (lat < 0) Nn += 10000000;
  return { zone, hemi: lat >= 0 ? 'N' : 'S', E, N: Nn };
}
