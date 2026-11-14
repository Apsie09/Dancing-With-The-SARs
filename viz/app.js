// Coryell City WSD leak map: map setup, layers, UI and interaction.
import { MAP_DEFAULTS, BASEMAPS, OVERLAYS } from './config.js';
import {
  LEAKS_URL, NISAR_START, T0, T1, DAY, SIZES, CAUSES, COLOR_MODES,
  prepareLeaks, makeFilter, passesAttr, passesTime, colorExpr, radiusExpr,
  sizeLabel, fmtDateCT, fmtDay, fmtGpm,
} from './leaks.js';
import { Graticule, fmtLat, fmtLon, toUTM } from './graticule.js';

const COG_PLUGIN = 'https://unpkg.com/@geomatico/maplibre-cog-protocol@0.10.0/dist/index.js';
const $ = (sel, root = document) => root.querySelector(sel);
const el = (tag, attrs = {}, html = '') => {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === 'class') e.className = v; else if (k.startsWith('on')) e.addEventListener(k.slice(2), v); else e.setAttribute(k, v);
  }
  if (html) e.innerHTML = html;
  return e;
};
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const nf = (n) => n.toLocaleString('en-US');

// ------------------------------------------------------------------ state ---
const state = {
  basemap: MAP_DEFAULTS.basemap,
  mode: 'points',        // points | clusters | heat
  color: 'size',         // key of COLOR_MODES
  sizeBy: 'none',        // none | loss | size
  ghosts: true,
  filter: makeFilter(),
  leaks: [],
  shown: [],
  playing: null,
  overlayData: {},       // id -> FeatureCollection (for popups / counts)
  overlayOk: {},         // id -> true | false (optional layers that failed)
};

// -------------------------------------------------------------------- map ---
const hasHash = /map=/.test(location.hash);
const map = new maplibregl.Map({
  container: 'map',
  hash: 'map',
  style: {
    version: 8,
    glyphs: MAP_DEFAULTS.glyphs,
    sources: Object.fromEntries(BASEMAPS.map((b) => [`bm-${b.id}`, {
      type: 'raster', tiles: b.tiles, tileSize: 256, maxzoom: b.maxzoom, attribution: b.attribution,
    }])),
    layers: [
      { id: 'bg', type: 'background', paint: { 'background-color': '#0b1016' } },
      ...BASEMAPS.map((b) => ({
        id: `bm-${b.id}`, type: 'raster', source: `bm-${b.id}`,
        layout: { visibility: b.id === state.basemap ? 'visible' : 'none' },
        paint: { 'raster-fade-duration': 150 },
      })),
      // Empty anchor layers that fix the drawing order of overlay groups.
      { id: 'z-raster-top', type: 'background', layout: { visibility: 'none' }, paint: {} },
      { id: 'z-vector-top', type: 'background', layout: { visibility: 'none' }, paint: {} },
    ],
  },
  ...(hasHash ? {} : { bounds: MAP_DEFAULTS.bounds, fitBoundsOptions: { padding: 40 } }),
  maxZoom: 19,
  dragRotate: false,
  pitchWithRotate: false,
  touchPitch: false,
  attributionControl: false,
});
map.touchZoomRotate.disableRotation();
map.keyboard.disableRotation();

map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right');
map.addControl(new (class {
  onAdd() {
    const c = el('div', { class: 'maplibregl-ctrl maplibregl-ctrl-group' });
    c.appendChild(el('button', { type: 'button', title: 'Zoom to all leaks', 'aria-label': 'Zoom to all leaks', class: 'ctrl-home',
      onclick: () => map.fitBounds(MAP_DEFAULTS.bounds, { padding: 40 }) },
    '<svg viewBox="0 0 20 20" width="18" height="18"><path d="M3 9.5 10 4l7 5.5V16a1 1 0 0 1-1 1h-3.5v-4.5h-5V17H4a1 1 0 0 1-1-1z" fill="currentColor"/></svg>'));
    return c;
  }
  onRemove() {}
})(), 'top-right');
map.addControl(new maplibregl.ScaleControl({ maxWidth: 140, unit: 'metric' }), 'bottom-left');
map.addControl(new maplibregl.ScaleControl({ maxWidth: 140, unit: 'imperial' }), 'bottom-left');
map.addControl(new maplibregl.AttributionControl({
  compact: true,
  customAttribution: 'Leak records: Coryell City Water Supply District (Survey123), no licence stated',
}), 'bottom-right');

// ------------------------------------------------------------- bootstrap ----
map.on('load', async () => {
  if (OVERLAYS.some((o) => o.needsCog)) await loadCogPlugin();
  addOverlays();
  const grat = new Graticule(map, { beforeId: undefined });
  $('#opt-graticule').addEventListener('change', (e) => grat.setVisible(e.target.checked));

  try {
    const res = await fetch(LEAKS_URL);
    if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
    state.leaks = prepareLeaks(await res.json());
    state.byId = new Map(state.leaks.map((f) => [f.id, f]));
  } catch (err) {
    showFatal(`Could not load the leak data (${esc(err.message)}). Serve the repository root over HTTP and open <code>/viz/</code>; see viz/README.md.`);
    return;
  }
  addLeakLayers();
  buildLeakUI();
  applyFilter();
  setupInteraction();
  $('#loading').classList.add('hidden');
});

function loadCogPlugin() {
  return new Promise((resolve) => {
    const s = el('script', { src: COG_PLUGIN });
    s.onload = () => { maplibregl.addProtocol('cog', window.MaplibreCOGProtocol.cogProtocol); resolve(); };
    s.onerror = () => { console.warn('COG plugin failed to load'); resolve(); };
    document.head.appendChild(s);
  });
}

function showFatal(html) {
  $('#loading').classList.add('hidden');
  const b = $('#fatal');
  b.innerHTML = html;
  b.classList.remove('hidden');
}

// --------------------------------------------------------------- overlays ---
const overlayOpacityProps = { raster: ['raster-opacity'], fill: ['fill-opacity'], line: ['line-opacity'], circle: ['circle-opacity', 'circle-stroke-opacity'], symbol: ['text-opacity', 'icon-opacity'], heatmap: ['heatmap-opacity'] };
const baseOpacity = {}; // layerId -> {prop: value}

function addOverlays() {
  // Reverse so that the first entry in OVERLAYS ends up on top of its group.
  for (const o of [...OVERLAYS].reverse()) {
    for (const [sid, src] of Object.entries(o.sources)) {
      const s = { ...src };
      if (s.type === 'geojson') s.data = { type: 'FeatureCollection', features: [] };
      if (o.attribution && !s.attribution) s.attribution = o.attribution;
      map.addSource(sid, s);
    }
    for (const l of o.layers) {
      const layer = structuredClone(l);
      layer.layout = { ...(layer.layout || {}), visibility: o.visible ? 'visible' : 'none' };
      map.addLayer(layer, o.z === 'raster' ? 'z-raster-top' : 'z-vector-top');
      baseOpacity[layer.id] = {};
      for (const p of overlayOpacityProps[layer.type] || []) {
        const v = layer.paint?.[p];
        baseOpacity[layer.id][p] = typeof v === 'number' ? v : 1;
      }
    }
    setOverlayOpacity(o, o.opacity ?? 1);
    if (o.z === 'vector' && o.url) loadOverlayData(o);
  }
  buildOverlayUI();
}

async function loadOverlayData(o) {
  try {
    const res = await fetch(o.url);
    if (!res.ok) throw new Error(res.status);
    let fc = await res.json();
    if (!fc || !Array.isArray(fc.features)) throw new Error('not GeoJSON');
    if (o.transform) fc = o.transform(fc);
    state.overlayData[o.id] = fc;
    state.overlayOk[o.id] = true;
    map.getSource(Object.keys(o.sources)[0]).setData(fc);
  } catch (err) {
    state.overlayOk[o.id] = false;
    if (!o.optional) console.error(`Overlay ${o.id} failed to load`, err);
  }
  updateOverlayRow(o);
}

function setOverlayVisible(o, v) {
  o.visible = v;
  for (const l of o.layers) map.setLayoutProperty(l.id, 'visibility', v ? 'visible' : 'none');
}

function setOverlayOpacity(o, k) {
  o.opacity = k;
  for (const l of o.layers) {
    for (const [p, base] of Object.entries(baseOpacity[l.id] || {})) map.setPaintProperty(l.id, p, base * k);
  }
}

// ------------------------------------------------------------------ leaks ---
function addLeakLayers() {
  const empty = { type: 'FeatureCollection', features: [] };
  map.addSource('leaks', { type: 'geojson', data: empty });
  map.addSource('leaks-out', { type: 'geojson', data: empty });
  map.addSource('leaks-cl', { type: 'geojson', data: empty, cluster: true, clusterRadius: 42, clusterMaxZoom: 14 });

  map.addLayer({ id: 'leaks-ghost', type: 'circle', source: 'leaks-out',
    paint: {
      'circle-color': '#dfe5ea', 'circle-opacity': 0.45,
      'circle-stroke-color': 'rgba(10,14,20,0.6)', 'circle-stroke-width': 0.5,
      'circle-radius': ['interpolate', ['linear'], ['zoom'], 8, 1.8, 11, 2.6, 14, 4.5],
    } });

  map.addLayer({ id: 'leaks-heat', type: 'heatmap', source: 'leaks', maxzoom: 16,
    layout: { visibility: 'none' },
    paint: {
      'heatmap-weight': 1,
      'heatmap-intensity': ['interpolate', ['linear'], ['zoom'], 8, 0.25, 11, 0.45, 14, 1],
      'heatmap-radius': ['interpolate', ['linear'], ['zoom'], 8, 8, 11, 14, 14, 26, 16, 36],
      'heatmap-color': ['interpolate', ['linear'], ['heatmap-density'],
        0, 'rgba(0,0,0,0)', 0.1, 'rgba(42,138,216,0.45)', 0.3, 'rgba(76,201,240,0.75)', 0.5, '#fdc94f', 0.75, '#fb8c3c', 0.9, '#ef3b2c', 1, '#c51b7d'],
      'heatmap-opacity': ['interpolate', ['linear'], ['zoom'], 13, 0.9, 16, 0.25],
    } });

  map.addLayer({ id: 'leaks-circle', type: 'circle', source: 'leaks',
    paint: {
      'circle-color': colorExpr(state.color),
      'circle-radius': radiusExpr(state.sizeBy),
      'circle-stroke-color': ['case', ['boolean', ['feature-state', 'hover'], false], '#ffffff', '#0b0f14'],
      'circle-stroke-width': ['case', ['boolean', ['feature-state', 'hover'], false], 2.5, 0.9],
      'circle-opacity': 0.95,
    } });

  map.addLayer({ id: 'cl-circle', type: 'circle', source: 'leaks-cl', filter: ['has', 'point_count'],
    layout: { visibility: 'none' },
    paint: {
      'circle-color': ['step', ['get', 'point_count'], '#fdc94f', 10, '#fb8c3c', 50, '#ef3b2c', 150, '#c51b7d'],
      'circle-radius': ['step', ['get', 'point_count'], 13, 10, 17, 50, 22, 150, 28],
      'circle-stroke-color': 'rgba(11,15,20,0.85)', 'circle-stroke-width': 2, 'circle-opacity': 0.92,
    } });
  map.addLayer({ id: 'cl-count', type: 'symbol', source: 'leaks-cl', filter: ['has', 'point_count'],
    layout: { visibility: 'none', 'text-field': ['get', 'point_count_abbreviated'], 'text-font': MAP_DEFAULTS.font, 'text-size': 12, 'text-allow-overlap': true },
    paint: { 'text-color': ['step', ['get', 'point_count'], '#1a1a1a', 50, '#ffffff'] } });
  map.addLayer({ id: 'cl-point', type: 'circle', source: 'leaks-cl', filter: ['!', ['has', 'point_count']],
    layout: { visibility: 'none' },
    paint: {
      'circle-color': colorExpr(state.color), 'circle-radius': radiusExpr(state.sizeBy),
      'circle-stroke-color': '#0b0f14', 'circle-stroke-width': 0.9,
    } });
}

const MODE_LAYERS = {
  points: ['leaks-circle'],
  clusters: ['cl-circle', 'cl-count', 'cl-point'],
  heat: ['leaks-heat', 'leaks-circle'],
};

function applyMode() {
  const all = new Set(Object.values(MODE_LAYERS).flat());
  for (const id of all) map.setLayoutProperty(id, 'visibility', MODE_LAYERS[state.mode].includes(id) ? 'visible' : 'none');
  // In heatmap mode the individual dots only appear once zoomed in.
  map.setLayerZoomRange('leaks-circle', state.mode === 'heat' ? 13 : 0, 24);
  map.setLayoutProperty('leaks-ghost', 'visibility', state.ghosts && state.mode !== 'heat' ? 'visible' : 'none');
}

function applyStyle() {
  for (const id of ['leaks-circle', 'cl-point']) {
    map.setPaintProperty(id, 'circle-color', colorExpr(state.color));
    map.setPaintProperty(id, 'circle-radius', radiusExpr(state.sizeBy));
  }
  map.setPaintProperty('leaks-heat', 'heatmap-weight', state.sizeBy === 'loss'
    ? ['case', ['<', ['get', 'gpm'], 0], 0.5, ['min', 3, ['/', ['ln', ['+', 1, ['get', 'gpm']]], 2.5]]]
    : 1);
  renderLegend();
}

function applyFilter() {
  const f = state.filter;
  const shown = [], out = [], attrOnly = [];
  for (const ft of state.leaks) {
    const a = passesAttr(ft.properties, f);
    if (a) attrOnly.push(ft);
    if (a && passesTime(ft.properties, f)) shown.push(ft); else out.push(ft);
  }
  state.shown = shown;
  const fc = (features) => ({ type: 'FeatureCollection', features });
  map.getSource('leaks').setData(fc(shown));
  map.getSource('leaks-cl').setData(fc(shown));
  map.getSource('leaks-out').setData(fc(out));
  renderStats(shown);
  renderHistogram(attrOnly);
  renderLegend();
}

// ---------------------------------------------------------------- leak UI ---
const sliderMax = Math.round((T1 - T0) / DAY);
const dayToT = (d) => T0 + d * DAY;
const tToDay = (t) => Math.round((t - T0) / DAY);

function buildLeakUI() {
  // Display mode (segmented control)
  for (const b of document.querySelectorAll('#seg-mode button')) {
    b.addEventListener('click', () => {
      state.mode = b.dataset.v;
      document.querySelectorAll('#seg-mode button').forEach((x) => x.classList.toggle('on', x === b));
      applyMode();
    });
  }
  const colorSel = $('#sel-color');
  colorSel.innerHTML = Object.entries(COLOR_MODES).map(([k, m]) => `<option value="${k}">${m.label}</option>`).join('');
  colorSel.value = state.color;
  colorSel.addEventListener('change', () => { state.color = colorSel.value; applyStyle(); });
  $('#sel-size').addEventListener('change', (e) => { state.sizeBy = e.target.value; applyStyle(); });
  $('#opt-ghosts').addEventListener('change', (e) => { state.ghosts = e.target.checked; applyMode(); });

  // Pipe size chips
  const sizeBox = $('#chips-size');
  for (const s of [...SIZES, null]) {
    const n = state.leaks.filter((f) => f.properties.size === s).length;
    if (!n) continue;
    const c = el('button', { type: 'button', class: 'chip on', title: `${n} leaks` }, esc(sizeLabel(s)));
    c.addEventListener('click', () => {
      const on = !c.classList.contains('on');
      c.classList.toggle('on', on);
      on ? state.filter.sizes.add(s) : state.filter.sizes.delete(s);
      applyFilter();
    });
    sizeBox.appendChild(c);
  }
  const sizePreset = (pred) => {
    state.filter.sizes = new Set([...SIZES, null].filter(pred));
    [...sizeBox.children].forEach((c, i) => {
      const s = [...SIZES, null].filter((x) => state.leaks.some((f) => f.properties.size === x))[i];
      c.classList.toggle('on', state.filter.sizes.has(s));
    });
    applyFilter();
  };
  $('#size-all').addEventListener('click', () => sizePreset(() => true));
  $('#size-big').addEventListener('click', () => sizePreset((s) => s != null && s >= 4));

  // Cause chips
  const causeBox = $('#chips-cause');
  CAUSES.forEach((c, i) => {
    const b = el('button', { type: 'button', class: 'chip on' }, esc(c.label));
    b.addEventListener('click', () => {
      const on = !b.classList.contains('on');
      b.classList.toggle('on', on);
      on ? state.filter.causes.add(i) : state.filter.causes.delete(i);
      applyFilter();
    });
    causeBox.appendChild(b);
  });

  // Time range slider
  const a = $('#t-from'), b = $('#t-to');
  for (const r of [a, b]) { r.min = 0; r.max = sliderMax; r.step = 1; }
  a.value = 0; b.value = sliderMax;
  const onSlide = (e) => {
    let lo = +a.value, hi = +b.value;
    if (lo > hi - 1) { if (e?.target === a) lo = hi - 1; else hi = lo + 1; a.value = lo; b.value = hi; }
    setRange(dayToT(lo), dayToT(hi), false);
  };
  a.addEventListener('input', onSlide);
  b.addEventListener('input', onSlide);

  document.querySelectorAll('[data-preset]').forEach((btn) => btn.addEventListener('click', () => {
    stopPlay();
    const p = btn.dataset.preset;
    const last = Date.UTC(2026, 10, 12); // day after the newest record
    if (p === 'all') setRange(T0, T1);
    if (p === 'nisar') setRange(NISAR_START, T1);
    if (p === '12m') setRange(last - 365 * DAY, T1);
    if (p === '2026') setRange(Date.UTC(2026, 0, 1), T1);
  }));
  $('#btn-play').addEventListener('click', () => (state.playing ? stopPlay() : startPlay()));
  const SPEEDS = [['0.5×', 900], ['1×', 450], ['2×', 200], ['4×', 90]];
  $('#btn-speed').addEventListener('click', (e) => {
    const b = e.currentTarget;
    const i = (SPEEDS.findIndex(([, ms]) => ms === +b.dataset.ms) + 1) % SPEEDS.length;
    b.textContent = SPEEDS[i][0];
    b.dataset.ms = SPEEDS[i][1];
    if (state.playing) { stopPlay(); startPlay(); }
  });

  applyMode();
  updateRangeLabels();
}

function setRange(t0, t1, moveSliders = true) {
  state.filter.t0 = Math.max(T0, t0);
  state.filter.t1 = Math.min(T1, t1);
  if (moveSliders) { $('#t-from').value = tToDay(state.filter.t0); $('#t-to').value = tToDay(state.filter.t1); }
  updateRangeLabels();
  applyFilter();
}

function updateRangeLabels() {
  const { t0, t1 } = state.filter;
  $('#t-label-from').textContent = fmtDay(t0);
  $('#t-label-to').textContent = fmtDay(t1 - DAY);
  const days = Math.round((t1 - t0) / DAY);
  $('#t-span').textContent = days >= 730 ? `${(days / 365.25).toFixed(1)} years` : days >= 60 ? `${Math.round(days / 30.44)} months` : `${days} days`;
  document.querySelectorAll('[data-preset]').forEach((btn) => {
    const p = btn.dataset.preset;
    btn.classList.toggle('on', (p === 'all' && t0 === T0 && t1 === T1) || (p === 'nisar' && t0 === NISAR_START && t1 === T1));
  });
  // Track fill between the two thumbs
  const lo = tToDay(t0) / sliderMax * 100, hi = tToDay(t1) / sliderMax * 100;
  $('#t-track-fill').style.left = `${lo}%`;
  $('#t-track-fill').style.width = `${hi - lo}%`;
}

// Play: slide the current window forward (or a 60-day window if the whole range is selected).
function startPlay() {
  let { t0, t1 } = state.filter;
  let win = t1 - t0;
  if (win > 400 * DAY) win = 60 * DAY;
  if (t0 + win >= T1 || t1 >= T1) t0 = T0;
  t1 = t0 + win;
  const btn = $('#btn-play');
  btn.classList.add('on');
  btn.innerHTML = ICON_PAUSE;
  btn.setAttribute('aria-label', 'Pause');
  const stepDays = Math.max(3, Math.round(win / DAY / 8));
  const tick = () => {
    setRange(t0, t1);
    if (t1 >= T1) { stopPlay(); return; }
    t0 += stepDays * DAY; t1 += stepDays * DAY;
    if (t1 > T1) { t0 -= t1 - T1; t1 = T1; }
  };
  tick();
  state.playing = setInterval(tick, +$('#btn-speed').dataset.ms);
}
function stopPlay() {
  if (!state.playing) return;
  clearInterval(state.playing);
  state.playing = null;
  const btn = $('#btn-play');
  btn.classList.remove('on');
  btn.innerHTML = ICON_PLAY;
  btn.setAttribute('aria-label', 'Play');
}
const ICON_PLAY = '<svg viewBox="0 0 20 20" width="16" height="16"><path d="M6 4.5v11l9-5.5z" fill="currentColor"/></svg>';
const ICON_PAUSE = '<svg viewBox="0 0 20 20" width="16" height="16"><path d="M5.5 4.5h3v11h-3zm6 0h3v11h-3z" fill="currentColor"/></svg>';

// ------------------------------------------------------- histogram & stats --
const MONTHS = [];
for (let d = new Date(T0); d.getTime() < T1; d.setUTCMonth(d.getUTCMonth() + 1)) MONTHS.push(d.getTime());
const monthIndex = (t) => { const d = new Date(t); return (d.getUTCFullYear() - 2019) * 12 + d.getUTCMonth() - 8; };
const fmtMonth = new Intl.DateTimeFormat('en-US', { timeZone: 'UTC', month: 'short', year: 'numeric' });

function renderHistogram(features) {
  const counts = new Array(MONTHS.length).fill(0);
  for (const f of features) if (f.properties.t >= 0) counts[monthIndex(f.properties.t)]++;
  const max = Math.max(5, ...counts);
  const W = 1000, H = 100;
  const x = (t) => ((t - T0) / (T1 - T0)) * W;
  const { t0, t1 } = state.filter;
  let svg = `<rect class="h-nisar" x="${x(NISAR_START)}" y="0" width="${W - x(NISAR_START)}" height="${H}"/>`;
  MONTHS.forEach((m, i) => {
    const m1 = MONTHS[i + 1] ?? T1;
    const bx = x(m), bw = x(m1) - bx;
    const h = (counts[i] / max) * (H - 18);
    const sel = m1 > t0 && m < t1;
    svg += `<rect class="h-bar${sel ? ' sel' : ''}" x="${(bx + 0.6).toFixed(1)}" y="${(H - h).toFixed(1)}" width="${Math.max(0.5, bw - 1.2).toFixed(1)}" height="${h.toFixed(1)}"/>`;
    svg += `<rect class="h-hit" data-i="${i}" x="${bx.toFixed(1)}" y="0" width="${bw.toFixed(1)}" height="${H}"><title>${fmtMonth.format(new Date(m))}: ${counts[i]} leak${counts[i] === 1 ? '' : 's'}</title></rect>`;
  });
  if (state.acq) {
    for (const t of state.acq.dates) {
      svg += `<rect class="h-acq-line" x="${(x(t) - 0.6).toFixed(1)}" y="16" width="1.2" height="${H - 16}"/>`;
      svg += `<rect class="h-acq" x="${(x(t) - 1.5).toFixed(1)}" y="16" width="3" height="7"/>`;
    }
  }
  const hist = $('#hist');
  hist.innerHTML = `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none">${svg}</svg>` +
    `<span class="h-nisar-label" style="left:${(x(NISAR_START) / W * 100).toFixed(2)}%">NISAR</span>` +
    (state.acq ? `<span class="h-acq-label">${esc(state.acq.stack)} acquisitions</span>` : '');
  hist.querySelectorAll('.h-hit').forEach((r) => r.addEventListener('click', () => {
    stopPlay();
    const i = +r.dataset.i;
    setRange(MONTHS[i], MONTHS[i + 1] ?? T1);
  }));
  $('#hist-max').textContent = `${max}/mo`;
  // Year ticks
  let ticks = '';
  for (let y = 2020; y <= 2026; y++) ticks += `<span style="left:${(x(Date.UTC(y, 0, 1)) / W * 100).toFixed(2)}%">${y}</span>`;
  $('#hist-axis').innerHTML = ticks;
}

function renderStats(shown) {
  const total = state.leaks.length;
  $('#count').textContent = nf(shown.length);
  $('#count-of').textContent = `of ${nf(total)} leaks`;
  const g = shown.map((f) => f.properties.gpm).filter((v) => v >= 0).sort((a, b) => a - b);
  const med = g.length ? g[Math.floor((g.length - 1) / 2)] : null;
  const big = shown.filter((f) => f.properties.size >= 4).length;
  const nisar = shown.filter((f) => f.properties.t >= NISAR_START).length;
  $('#st-med').textContent = med == null ? '–' : fmtGpm(med);
  $('#st-big').textContent = shown.length ? `${nf(big)} (${Math.round((big / shown.length) * 100)}%)` : '–';
  $('#st-nisar').textContent = nf(nisar);
}

function renderLegend() {
  const m = COLOR_MODES[state.color];
  const counts = new Map();
  for (const f of state.shown) counts.set(f.properties[m.prop], (counts.get(f.properties[m.prop]) || 0) + 1);
  $('#legend-leaks').innerHTML = m.bins
    .filter((b) => b.v !== -1 || counts.get(-1))
    .map((b) => `<div class="lg-row"><span class="lg-dot" style="background:${b.color}"></span><span class="lg-label">${esc(b.label)}</span><span class="lg-n">${nf(counts.get(b.v) || 0)}</span></div>`)
    .join('');
  const sizeNote = { none: '', loss: 'Dot size: estimated water loss.', size: 'Dot size: pipe diameter.' }[state.sizeBy];
  $('#legend-note').textContent = sizeNote;
}

// ------------------------------------------------------------ overlay UI ----
function legendHTML(lg) {
  if (!lg) return '';
  if (lg.type === 'ramp') {
    return `<div class="lg-ramp" style="background:linear-gradient(90deg,${lg.colors.join(',')})"></div><div class="lg-ramp-l"><span>${esc(lg.labels[0])}</span><span>${esc(lg.labels[1])}</span></div>`;
  }
  return lg.items.map(([c, label, w]) => {
    const sw = lg.type === 'lines'
      ? `<span class="lg-line" style="background:${c};height:${Math.max(1.5, w * 1.1)}px"></span>`
      : `<span class="lg-fill" style="background:${c}"></span>`;
    return `<div class="lg-row">${sw}<span class="lg-label">${esc(label)}</span></div>`;
  }).join('');
}

function buildOverlayUI() {
  const box = $('#overlays');
  let group = null;
  for (const o of OVERLAYS) {
    if (o.group !== group) { group = o.group; box.appendChild(el('div', { class: 'ov-group' }, esc(group))); }
    const row = el('div', { class: `ov${o.visible ? ' open' : ''}`, id: `ov-${o.id}` });
    row.innerHTML = `
      <label class="ov-head">
        <input type="checkbox" ${o.visible ? 'checked' : ''}>
        <span class="ov-title">${esc(o.title)}</span>
        <span class="ov-status"></span>
      </label>
      <div class="ov-body">
        ${o.info ? `<p class="ov-info">${esc(o.info)}</p>` : ''}
        <div class="ov-opacity"><span>Opacity</span><input type="range" min="0" max="100" value="${Math.round((o.opacity ?? 1) * 100)}"><output>${Math.round((o.opacity ?? 1) * 100)}%</output></div>
        <div class="ov-legend">${legendHTML(o.legend)}</div>
      </div>`;
    const cb = $('input[type=checkbox]', row);
    cb.addEventListener('change', () => { setOverlayVisible(o, cb.checked); row.classList.toggle('open', cb.checked); });
    const op = $('.ov-opacity input', row);
    op.addEventListener('input', () => { setOverlayOpacity(o, op.value / 100); $('output', row).textContent = `${op.value}%`; });
    box.appendChild(row);
    updateOverlayRow(o);
  }
}

function updateOverlayRow(o) {
  const row = document.getElementById(`ov-${o.id}`);
  if (!row) return;
  const st = $('.ov-status', row);
  if (state.overlayOk[o.id] === false) {
    row.classList.add('missing');
    row.classList.remove('open');
    $('input[type=checkbox]', row).disabled = true;
    $('input[type=checkbox]', row).checked = false;
    setOverlayVisible(o, false);
    st.textContent = o.optional ? 'not available yet' : 'failed to load';
    st.title = `Could not load ${o.url}`;
  } else if (state.overlayOk[o.id] === true && state.overlayData[o.id]) {
    st.textContent = nf(state.overlayData[o.id].features.length);
    st.title = 'features';
  }
}

// Tile errors on overlays (e.g. a WMS host blocked by the network) are flagged on the row.
map.on('error', (e) => {
  const o = OVERLAYS.find((x) => e.sourceId && x.sources[e.sourceId]);
  if (o && o.z === 'raster') {
    const row = document.getElementById(`ov-${o.id}`);
    if (row && !row.classList.contains('tile-error')) {
      row.classList.add('tile-error');
      $('.ov-status', row).textContent = 'tiles failing';
    }
  } else if (e.sourceId && e.sourceId.startsWith('bm-')) {
    // basemap tile hiccups: ignore quietly
  } else {
    console.warn(e.error || e);
  }
});

// ----------------------------------------------------------- basemap UI -----
function buildBasemapUI() {
  const box = $('#basemaps');
  for (const b of BASEMAPS) {
    const thumb = b.tiles[0].replace('{z}', 11).replace('{x}', 468).replace('{y}', 835);
    const card = el('button', { type: 'button', class: `bm${b.id === state.basemap ? ' on' : ''}`, title: b.note },
      `<img src="${thumb}" alt="" loading="lazy"><span>${esc(b.title)}</span>`);
    card.addEventListener('click', () => {
      for (const x of BASEMAPS) map.setLayoutProperty(`bm-${x.id}`, 'visibility', x.id === b.id ? 'visible' : 'none');
      state.basemap = b.id;
      box.querySelectorAll('.bm').forEach((c) => c.classList.toggle('on', c === card));
      $('#bm-note').textContent = b.note;
    });
    box.appendChild(card);
  }
  $('#bm-note').textContent = BASEMAPS.find((b) => b.id === state.basemap).note;
}
buildBasemapUI();

// ------------------------------------------------------------ interaction ---
const popupHover = new maplibregl.Popup({ closeButton: false, closeOnClick: false, maxWidth: '320px', offset: 10, className: 'pp-hover' });
// closeOnClick is handled in the click handler, so one click can move the popup to another feature.
const popupClick = new maplibregl.Popup({ closeButton: true, closeOnClick: false, maxWidth: '340px', offset: 10 });
popupClick.on('close', () => { if (state.acq) { state.acq = null; applyFilter(); } });

function leakColor(p) {
  const m = COLOR_MODES[state.color];
  return (m.bins.find((b) => b.v === p[m.prop]) || m.bins.find((b) => b.v === -1) || { color: '#9aa3ad' }).color;
}

function leakPopup(p, lngLat) {
  const gpm = fmtGpm(p.gpm);
  let loss = gpm ? `≈ ${gpm}` : 'Unknown';
  if (gpm && !p.lossPlain) loss += ' <span class="pp-sub">parsed from crew text</span>';
  const rows = [
    ['Pipe size', p.size != null ? sizeLabel(p.size) : 'Unknown'],
    ['Water loss', loss, true],
    ['Repair', p.repair || '–'],
    ['Cause', CAUSES[p.cbin]?.label || '–'],
    ['Pressure zone', p.zone || '–'],
    ['Repair time', p.duration || '–'],
    ['Notes', p.notesHidden ? '<span class="pp-sub">withheld (names a person)</span>' : (p.notes ? esc(p.notes) : '–'), true],
    ['Location', `${fmtLat(lngLat[1], 5)}, ${fmtLon(lngLat[0], 5)}`],
  ];
  return `<div class="pp">
    <div class="pp-head"><span class="lg-dot" style="background:${leakColor(p)}"></span><b>Leak repair</b>${p.t >= NISAR_START ? '<span class="badge">NISAR window</span>' : ''}</div>
    <div class="pp-time">${esc(fmtDateCT(p.t))}</div>
    <dl>${rows.map(([k, v, raw]) => `<dt>${k}</dt><dd>${raw ? v : esc(v)}</dd>`).join('')}</dl>
    <div class="pp-foot">ObjectId ${p.id} · local time (US Central)</div>
  </div>`;
}

function pipePopup(p) {
  const blank = (v) => (v == null || String(v).trim() === '' ? null : String(v).trim());
  const rows = [
    ['Size', blank(p.Size)?.replace(/"/g, '″') || (p.dia ? `${p.dia}″` : null)],
    ['Material', blank(p.Material)],
    ['Class', blank(p.Class)],
    ['Depth', blank(p.Depth)],
    ['Installed', blank(p.Year)],
    ['Length', p.LengthMile ? `${(+p.LengthMile).toFixed(2)} mi (${Math.round(+p.LengthMile * 1609.34)} m)` : null],
    ['Remarks', blank(p.MapSource)],
  ].filter(([, v]) => v);
  return `<div class="pp"><div class="pp-head"><span class="lg-line" style="background:#45c3f2;height:3px"></span><b>Water line</b></div>
    <dl>${rows.map(([k, v]) => `<dt>${k}</dt><dd>${esc(v)}</dd>`).join('')}</dl>
    <div class="pp-foot">OBJECTID ${esc(p.OBJECTID)} · FtrID ${esc(p.FtrID)}</div></div>`;
}

function zonePopup(p) {
  const key = String(p.Name || '').replace(/ /g, '_');
  const n = state.shown.filter((f) => f.properties.zoneRaw === key).length;
  const nAll = state.leaks.filter((f) => f.properties.zoneRaw === key).length;
  return `<div class="pp"><div class="pp-head"><b>${esc(p.Name)}</b></div>
    <dl><dt>Area</dt><dd>${(+p.SquareMiles).toFixed(1)} sq mi (${(p.SquareMiles * 2.58999).toFixed(1)} km²)</dd>
    <dt>Leaks (filter)</dt><dd>${nf(n)} <span class="pp-sub">of ${nf(nAll)} total</span></dd>
    <dt>Density</dt><dd>${(n / p.SquareMiles).toFixed(1)} per sq mi</dd></dl>
    <div class="pp-foot">Pressure zone · counts follow the leak filters</div></div>`;
}

// NISAR frame: MapLibre stringifies array properties, so read the original feature.
function nisarPopup(p, o) {
  const src = state.overlayData[o.id]?.features.find((f) => f.properties.stack === p.stack)?.properties;
  if (!src || !src.stack) return genericPopup(p, o.title);
  const dates = Array.isArray(src.dates) ? src.dates : [];
  state.acq = { stack: src.stack, dates: dates.map((d) => Date.parse(`${d}T12:00:00Z`)) };
  applyFilter();
  const { t0, t1 } = state.filter;
  const chips = dates.map((d) => {
    const t = Date.parse(`${d}T12:00:00Z`);
    return `<span class="acq${t >= t0 && t < t1 ? ' in' : ''}">${d.slice(2)}</span>`;
  }).join('');
  const spacing = Array.isArray(src.pixel_spacing_m) ? src.pixel_spacing_m.join(' / ') + ' m' : src.pixel_spacing_m;
  const rows = [
    ['Track', `${src.track} · ${String(src.direction || '').toLowerCase()}`],
    ['Frame', src.frame],
    ['Polarization', src.polarization],
    ['Pixel spacing', spacing],
    ['Leaks inside', src.leaks_inside != null ? `${src.leaks_inside} (NISAR window)` : null],
    ['Covers leak area', src.leak_bbox_fraction_covered != null ? `${Math.round(src.leak_bbox_fraction_covered * 100)}%` : null],
    ['Acquisitions', `${src.n_dates ?? dates.length}${src.first_date ? ` · ${src.first_date} → ${src.last_date}` : ''}`],
  ].filter(([, v]) => v != null && v !== '');
  return `<div class="pp"><div class="pp-head"><span class="lg-line" style="background:${src.direction === 'DESCENDING' ? '#f15bb5' : '#ff9f1c'};height:3px"></span><b>NISAR GCOV ${esc(src.stack)}</b></div>
    <dl>${rows.map(([k, v]) => `<dt>${k}</dt><dd>${esc(v)}</dd>`).join('')}</dl>
    ${chips ? `<div class="acq-list">${chips}</div>` : ''}
    <div class="pp-foot">Dates are marked on the time histogram; highlighted ones fall in the current time filter.</div></div>`;
}

function genericPopup(p, title) {
  const rows = Object.entries(p).filter(([, v]) => v != null && typeof v !== 'object' && String(v).trim() !== '').slice(0, 16);
  return `<div class="pp"><div class="pp-head"><b>${esc(title)}</b></div>
    <dl>${rows.map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join('')}</dl></div>`;
}

function setupInteraction() {
  // Click priority: leaks, clusters, then overlays in panel order.
  const overlayClick = OVERLAYS.filter((o) => o.popup).map((o) => ({
    o, layers: o.layers.filter((l) => l.type !== 'symbol').map((l) => l.id),
  }));
  const leakLayers = ['leaks-circle', 'cl-point'];
  const visibleLayers = (ids) => ids.filter((id) => map.getLayer(id) && map.getLayoutProperty(id, 'visibility') !== 'none');

  let hoverId = null;
  const setHover = (id) => {
    if (hoverId === id) return;
    if (hoverId != null) map.setFeatureState({ source: 'leaks', id: hoverId }, { hover: false });
    hoverId = id;
    if (id != null) map.setFeatureState({ source: 'leaks', id }, { hover: true });
  };

  map.on('mousemove', (e) => {
    const box = [[e.point.x - 3, e.point.y - 3], [e.point.x + 3, e.point.y + 3]];
    const leak = map.queryRenderedFeatures(box, { layers: visibleLayers(leakLayers) })[0];
    if (leak) {
      setHover(leak.layer.id === 'leaks-circle' ? leak.id : null);
      if (!popupClick.isOpen()) {
        const src = state.byId.get(leak.properties.id);
        popupHover.setLngLat(src.geometry.coordinates).setHTML(leakPopup(src.properties, src.geometry.coordinates)).addTo(map);
      }
      map.getCanvas().style.cursor = 'pointer';
      return;
    }
    setHover(null);
    popupHover.remove();
    const other = map.queryRenderedFeatures(box, { layers: visibleLayers(['cl-circle', ...overlayClick.flatMap((x) => x.layers)]) });
    map.getCanvas().style.cursor = other.length ? 'pointer' : '';
  });
  map.getCanvas().addEventListener('mouseleave', () => { setHover(null); popupHover.remove(); });

  map.on('click', async (e) => {
    const hadAcq = !!state.acq;
    state.acq = null;
    await handleClick(e);
    if (hadAcq && !state.acq) applyFilter();
  });

  async function handleClick(e) {
    const box = [[e.point.x - 4, e.point.y - 4], [e.point.x + 4, e.point.y + 4]];
    const leak = map.queryRenderedFeatures(box, { layers: visibleLayers(leakLayers) })[0];
    if (leak) {
      popupHover.remove();
      const src = state.byId.get(leak.properties.id);
      popupClick.setLngLat(src.geometry.coordinates).setHTML(leakPopup(src.properties, src.geometry.coordinates)).addTo(map);
      return;
    }
    const cl = map.queryRenderedFeatures(box, { layers: visibleLayers(['cl-circle']) })[0];
    if (cl) {
      const zoom = await map.getSource('leaks-cl').getClusterExpansionZoom(cl.properties.cluster_id);
      map.easeTo({ center: cl.geometry.coordinates, zoom: Math.min(zoom + 0.3, 16) });
      return;
    }
    for (const { o, layers } of overlayClick) {
      const f = map.queryRenderedFeatures(box, { layers: visibleLayers(layers) })[0];
      if (!f) continue;
      const html = o.popup === 'pipe' ? pipePopup(f.properties)
        : o.popup === 'zone' ? zonePopup(f.properties)
        : o.popup === 'nisar' ? nisarPopup(f.properties, o)
        : genericPopup(f.properties, o.title);
      popupClick.setLngLat(e.lngLat).setHTML(html).addTo(map);
      return;
    }
    popupClick.remove();
  }
}

// ------------------------------------------------------- cursor readout -----
function showCoords(ll) {
  const u = toUTM(ll.lat, ll.lng);
  $('#coords').innerHTML =
    `<span class="c-ll">${fmtLat(ll.lat, 5)}&ensp;${fmtLon(ll.lng, 5)}</span>` +
    `<span class="c-utm">UTM ${u.zone}${u.hemi}&ensp;${Math.round(u.E).toLocaleString('en-US')} E&ensp;${Math.round(u.N).toLocaleString('en-US')} N</span>` +
    `<span class="c-z">z ${map.getZoom().toFixed(1)}</span>`;
}
map.on('mousemove', (e) => showCoords(e.lngLat));
map.on('moveend', () => showCoords(map.getCenter()));
map.once('idle', () => {
  showCoords(map.getCenter());
  // Collapse the attribution on small screens (the (i) button expands it).
  if (window.innerWidth < 820) document.querySelector('.maplibregl-ctrl-attrib')?.classList.remove('maplibregl-compact-show');
});

// ------------------------------------------------------------- panel UI -----
$('#panel-toggle').addEventListener('click', () => document.body.classList.toggle('panel-open'));
$('#panel-close').addEventListener('click', () => document.body.classList.remove('panel-open'));
document.querySelectorAll('.sec > h2').forEach((h) => h.addEventListener('click', () => h.parentElement.classList.toggle('collapsed')));
window.addEventListener('keydown', (e) => {
  if (e.key === ' ' && e.target === document.body) { e.preventDefault(); $('#btn-play').click(); }
});

// For debugging in the console.
window.leakMap = { map, state, applyFilter, setRange };
