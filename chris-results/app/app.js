/* TerraGuard Evidence Explorer — static MapLibre app.
 *
 * One dataset contract, four sites. Everything is loaded from ./data/.
 * The app deliberately keeps three evidence types separate:
 *   observed  — repair records, pipe attributes, mapped networks
 *   modelled  — expected-condition residuals, break-risk scores
 *   inferred  — what the site team might investigate next
 */
const DATA = './data/';
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
const fmt = (v, d = 2) => (v == null || Number.isNaN(v) ? '—' : Number(v).toFixed(d));
const pct = (v, d = 0) => (v == null || Number.isNaN(v) ? '—' : `${(Number(v) * 100).toFixed(d)}%`);
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

const BASEMAPS = {
  imagery: {
    tiles: ['https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'],
    attribution: 'Imagery © Esri, Maxar, Earthstar Geographics, GIS User Community',
  },
  streets: {
    tiles: ['https://tile.openstreetmap.org/{z}/{x}/{y}.png'],
    attribution: '© OpenStreetMap contributors',
  },
  dark: {
    tiles: ['https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}'],
    attribution: '© Esri, HERE, Garmin, © OpenStreetMap contributors',
  },
};

const state = {
  sites: [],
  site: null,
  meta: null,
  data: null,
  map: null,
  cache: new Map(),
  year: 'all',
  overlay: 'leak',
  basemap: 'imagery',
  selection: null,
  show: { network: true, events: true, hotspots: true, zones: true },
};

/* ------------------------------------------------------------------ boot */
async function boot() {
  state.sites = await fetch(DATA + 'sites.json', { cache: 'no-cache' }).then((r) => r.json());
  buildNav();
  bindChrome();
  window.addEventListener('hashchange', route);
  route();
}

function buildNav() {
  const nav = $('#site-nav');
  nav.innerHTML = `
    <button data-route="overview">Overview</button>
    ${state.sites.map((s) => `<button data-route="site/${s.id}">${esc(s.name)}</button>`).join('')}
    <button data-route="compare">Compare</button>
    <button data-route="method">Method</button>`;
  nav.addEventListener('click', (e) => {
    const b = e.target.closest('button[data-route]');
    if (b) location.hash = b.dataset.route;
  });
}

function bindChrome() {
  $('#about-btn').addEventListener('click', () => $('#about').showModal());
  $('#layers-btn').addEventListener('click', () => $('#app main').classList.toggle('mobile-sidebar'));
  $('#evidence-btn').addEventListener('click', () => $('#app main').classList.toggle('show-evidence'));
}

function route() {
  const hash = (location.hash || '#overview').slice(1);
  const [view, id] = hash.split('/');
  state.selection = null;
  if (view === 'site' && state.sites.some((s) => s.id === id)) {
    openSite(id);
  } else if (view === 'compare') {
    renderCompare();
  } else if (view === 'method') {
    renderMethod();
  } else {
    renderOverview();
  }
  markNav(view, id);
}

function markNav(view, id) {
  $$('#site-nav button').forEach((b) => {
    const target = b.dataset.route;
    b.classList.toggle('active', target === (view === 'site' ? `site/${id}` : view));
  });
}

/* ------------------------------------------------------------------ overview */
function renderOverview() {
  state.site = null;
  state.meta = null;
  state.data = null;
  destroyMap();
  const main = $('#app main');
  main.className = 'overview';
  $('#doc').hidden = true;
  $('#doc').innerHTML = '';
  $('#sidebar').style.display = '';
  $('#map').style.display = '';
  $('#evidence').style.display = '';
  $('#sidebar').innerHTML = overviewSidebar();
  $('#evidence').innerHTML = '';
  $('#map').innerHTML = '<div class="loading">Loading world view…</div>';
  bindOverviewCards();
  setTimeout(() => buildOverviewMap(), 0);
}

function overviewSidebar() {
  const totalLabels = state.sites.reduce((a, s) => a + (s.labels || 0), 0);
  const totalPipes = 918 + 8134 + 5879 + 1;
  return `
    <div class="hero">
      <div class="eyebrow">NASA Space Apps 2026 · Dancing with the SARs</div>
      <h1>Four water networks.<br>One evidence-first workflow.</h1>
      <p>Separate what is <strong>observed</strong>, what is <strong>modelled</strong>, and what the data
         cannot yet support. Radar context meets weather normalisation and real repair records.</p>
      <div class="stats">
        <div><b>${state.sites.length}</b>study areas</div>
        <div><b>${totalLabels.toLocaleString()}</b>field records</div>
        <div><b>~${(totalPipes / 1000).toFixed(1)}k</b>pipe features</div>
        <div><b>3</b>evidence layers</div>
      </div>
    </div>
    <div class="site-cards">
      ${state.sites.map(siteCard).join('')}
    </div>`;
}

function siteCard(s) {
  const flag = s.labels > 0 ? 'labels' : 'demo';
  const flagText = s.labels > 0 ? `${s.labels} labels` : 'unlabelled';
  const auc = s.metrics.label_auc;
  return `
    <button class="site-card" data-site="${s.id}">
      <div class="row">
        <span class="name">${esc(s.name)}</span>
        <span class="flag ${flag}">${flagText}</span>
      </div>
      <div class="where">${esc(s.subtitle)}</div>
      <div class="desc">${esc(s.headline)}</div>
      <div class="mini">
        <span><b>${s.dates || '—'}</b> S1 dates</span>
        <span><b>${auc == null ? '—' : fmt(auc, 3)}</b> ${s.metrics.label_auc != null ? 'label AUC' : 'AUC'}</span>
        <span><b>${s.metrics.vv_r2 == null ? '—' : fmt(s.metrics.vv_r2, 2)}</b> VV R²</span>
      </div>
    </button>`;
}

function bindOverviewCards() {
  $$('.site-card').forEach((b) => b.addEventListener('click', () => { location.hash = `site/${b.dataset.site}`; }));
}

function buildOverviewMap() {
  const map = new maplibregl.Map({
    container: 'map',
    style: baseStyle('dark'),
    center: [10, 35],
    zoom: 1.4,
    minZoom: 1,
    attributionControl: true,
  });
  state.map = map;
  whenStyleReady(map, () => {
    $('#map .loading')?.classList.add('hide');
    const coords = state.sites.map((s) => s.center);
    const lons = coords.map((c) => c[0]), lats = coords.map((c) => c[1]);
    map.fitBounds([[Math.min(...lons) - 8, Math.min(...lats) - 6],
                   [Math.max(...lons) + 8, Math.max(...lats) + 6]], { padding: 70, maxZoom: 4.2, duration: 0 });
    state.sites.forEach((s) => {
      const el = document.createElement('button');
      el.className = 'site-marker';
      el.innerHTML = `<span class="pin"></span><span class="lbl">${esc(s.name)}</span>`;
      el.title = s.subtitle;
      el.addEventListener('click', () => { location.hash = `site/${s.id}`; });
      new maplibregl.Marker({ element: el, anchor: 'left' }).setLngLat(s.center).addTo(map);
    });
  });
  map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right');
}

/* ------------------------------------------------------------------ site */
async function openSite(id) {
  state.site = state.sites.find((s) => s.id === id);
  state.year = 'all';
  state.overlay = 'leak';
  state.basemap = 'imagery';
  state.selection = null;
  state.show = { network: true, events: true, hotspots: true, zones: true };
  destroyMap();
  const mainEl = $('#app main');
  mainEl.className = '';
  $('#doc').hidden = true;
  $('#doc').innerHTML = '';
  $('#sidebar').style.display = '';
  $('#map').style.display = '';
  $('#evidence').style.display = '';
  $('#sidebar').scrollTop = 0;
  $('#evidence').scrollTop = 0;
  $('#sidebar').innerHTML = '<div class="side-section"><p>Loading site…</p></div>';
  $('#evidence').innerHTML = '';
  $('#map').innerHTML = '<div class="loading">Loading layers…</div>';

  let payload;
  try {
    payload = await loadSite(id);
  } catch (err) {
    $('#sidebar').innerHTML = `<div class="side-section"><h2>Could not load</h2><p>${esc(err.message)}</p></div>`;
    return;
  }
  state.meta = payload.meta;
  state.data = payload;
  $('#sidebar').innerHTML = siteSidebar(state.site, payload);
  bindSiteControls();
  renderDefaultEvidence();
  setTimeout(() => buildSiteMap(payload), 0);
}

async function loadSite(id) {
  if (state.cache.has(id)) return state.cache.get(id);
  const base = `${DATA}${id}/`;
  const meta = await fetch(base + 'meta.json', { cache: 'no-cache' }).then((r) => r.json());
  const get = async (name) => {
    if (!name) return null;
    const r = await fetch(base + name, { cache: 'no-cache' });
    return r.ok ? r.json() : null;
  };
  const [network, events, hotspots, zones, stats] = await Promise.all([
    get(meta.network_file), get(meta.events_file), get(meta.hotspots_file),
    get(meta.zones_file), get(meta.stats_file),
  ]);
  const out = { meta, network, events, hotspots, zones, stats };
  state.cache.set(id, out);
  return out;
}

function siteSidebar(site, payload) {
  const { meta, stats } = payload;
  const m = site.metrics;
  const cards = [
    ['VV R²', fmt(m.vv_r2, 2), `MAE ${fmt(m.vv_mae, 2)} dB`],
    ['NDMI R²', fmt(m.ndmi_r2, 2), `MAE ${fmt(m.ndmi_mae, 3)}`],
    [m.label_auc != null ? 'Label AUC' : 'Corridor p95', m.label_auc != null ? fmt(m.label_auc, 3) : fmt(m.corridor_p95 ?? m.corridor_p, 2), m.label_auc != null ? `${m.n_labels} labels` : 'placebo test'],
    ['S1 dates', m.s1_dates ?? '—', `${m.dry_season_dates ?? '—'} dry-season`],
  ];

  const overlays = (meta.layers || []);
  const years = stats?.by_year ? Object.keys(stats.by_year).sort() : [];
  const histMax = years.length ? Math.max(...years.map((y) => stats.by_year[y])) : 1;

  return `
    <div class="side-section">
      <div class="eyebrow">${esc(site.subtitle)}</div>
      <h3>${esc(site.name)}</h3>
      <p class="strong">${esc(site.headline)}</p>
      <div class="status-row">
        <span class="chip ${site.labels > 100 ? 'green' : site.labels > 0 ? 'amber' : ''}">${esc(site.status)}</span>
        <span class="chip">Sentinel-1 grid</span>
        ${site.id === 'coryell' ? '<span class="chip red">licence: none stated</span>' : ''}
      </div>
      <div class="metric-grid">
        ${cards.map(([k, v, note]) => `
          <div class="metric">
            <div class="k">${esc(k)}</div>
            <div class="v">${esc(v)}</div>
            <div class="k" style="margin-top:2px">${esc(note)}</div>
          </div>`).join('')}
      </div>
    </div>

    <div class="side-section">
      <h2>Layers</h2>
      ${meta.network_file ? layerRow('network', 'Pipe network', 'mapped main', '#7ee0b0', state.show.network) : ''}
      ${meta.events_file ? layerRow('events', 'Ground-truth labels', `${site.labels}`, '#ffd166', state.show.events) : ''}
      ${meta.hotspots_file ? layerRow('hotspots', 'Candidate hotspots', 'ranked', '#ff5c8a', state.show.hotspots) : ''}
      ${meta.zones_file ? layerRow('zones', 'Pressure zones', '7', '#4cc9f0', state.show.zones) : ''}

      ${overlays.length ? `
        <h2 style="margin-top:14px">Evidence raster</h2>
        <div class="seg" id="overlay-seg">
          ${overlays.map((o) => `<button data-overlay="${o.kind}" class="${o.kind === state.overlay ? 'active' : ''}">${o.kind === 'leak' ? 'Leak' : o.kind === 'moisture' ? 'Moisture' : o.kind === 'persistence' ? 'Persistence' : 'NISAR'}</button>`).join('')}
        </div>
        <div class="legend" id="legend"></div>
      ` : `
        <h2 style="margin-top:14px">Pipe risk</h2>
        <div class="legend">
          <div class="legend-bar" style="background:linear-gradient(90deg,#2b5d4b,#d9a441,#ff6b4a,#ff2d55)"></div>
          <div class="legend-labels"><span>low</span><span>risk percentile</span><span>high</span></div>
        </div>
      `}

      <h2 style="margin-top:14px">Basemap</h2>
      <select id="basemap">
        <option value="imagery" ${state.basemap === 'imagery' ? 'selected' : ''}>Satellite imagery</option>
        <option value="streets" ${state.basemap === 'streets' ? 'selected' : ''}>OpenStreetMap</option>
        <option value="dark" ${state.basemap === 'dark' ? 'selected' : ''}>Dark canvas</option>
      </select>
    </div>

    <div class="side-section">
      <h2>Time</h2>
      ${years.length > 1 ? `
        <div class="timeline">
          <div class="histogram" id="histogram">
            ${years.map((y) => `<button data-year="${y}" title="${y}: ${stats.by_year[y]} records" style="height:${Math.max(3, (stats.by_year[y] / histMax) * 100)}%"><span class="tip">${y}: ${stats.by_year[y]}</span></button>`).join('')}
          </div>
          <div class="timeline-meta"><span>${stats.period?.[0] || ''}</span><span>${stats.period?.[1] || ''}</span></div>
          <div style="display:flex;gap:6px;margin-top:6px;flex-wrap:wrap">
            <button class="ghost" data-year="all" style="padding:3px 9px;font-size:11px">All years</button>
            ${site.id === 'coryell' ? '<button class="ghost" data-year="nisar" style="padding:3px 9px;font-size:11px">NISAR era</button>' : ''}
          </div>
          <p id="event-count" style="margin-top:8px"></p>
        </div>
      ` : years.length === 1 ? `
        <div class="status-row"><span class="chip amber">${years[0]} · ${stats.events ?? site.labels} records</span></div>
        <p>One dry season is bundled. The evidence raster is an aggregate for that period, not a time series.</p>
      ` : `<p>Aggregate dry-season evidence, 2022–2026. No point-level timeline is bundled for this site.</p>`}
    </div>

    <div class="side-section">
      <h2>Read this first</h2>
      ${(site.caveats || []).map((c) => `<div class="caveat">${esc(c)}</div>`).join('')}
      <div class="evidence-actions">
        ${meta.sources?.length ? `<button id="sources-btn">Sources</button>` : ''}
        ${site.kind === 'raster' ? `<a href="../${site.id === 'bulgaria' ? 'outputs' : `case_studies/${site.id}/outputs`}/validation.json" target="_blank" rel="noopener">validation.json</a>` : ''}
        ${site.kind === 'raster' ? `<a href="../${site.id === 'bulgaria' ? 'outputs' : `case_studies/${site.id}/outputs`}/terraguard_map.html" target="_blank" rel="noopener">legacy evidence map</a>` : ''}
        ${site.id === 'coryell' ? '<a href="../data/coryell/README.md" target="_blank" rel="noopener">data note</a>' : ''}
      </div>
    </div>`;
}

function layerRow(key, label, note, color, checked) {
  return `
    <label class="layer-row">
      <input type="checkbox" data-layer="${key}" ${checked ? 'checked' : ''}>
      <span class="swatch" style="background:${color}"></span>
      <span>${esc(label)}</span>
      <span class="note">${esc(note)}</span>
    </label>`;
}

function bindSiteControls() {
  $$('#sidebar input[data-layer]').forEach((el) => {
    el.addEventListener('change', () => {
      state.show[el.dataset.layer] = el.checked;
      applyVisibility();
    });
  });
  $$('#overlay-seg button').forEach((b) => {
    b.addEventListener('click', () => {
      state.overlay = b.dataset.overlay;
      $$('#overlay-seg button').forEach((x) => x.classList.toggle('active', x === b));
      setOverlay(state.overlay);
    });
  });
  $('#basemap')?.addEventListener('change', (e) => {
    state.basemap = e.target.value;
    setBasemap(state.basemap);
  });
  $$('#histogram button').forEach((b) => {
    b.addEventListener('click', () => setYear(b.dataset.year));
  });
  $$('#sidebar button[data-year]').forEach((b) => {
    if (b.closest('#histogram')) return;
    b.addEventListener('click', () => setYear(b.dataset.year));
  });
  $('#sources-btn')?.addEventListener('click', showSources);
}

/* ------------------------------------------------------------------ map */

/* MapLibre defers the style.load/load events in hidden tabs. Poll the style
 * state so the app initialises reliably in background tabs and headless tests. */
function whenStyleReady(map, fn) {
  let done = false;
  const run = () => {
    if (done) return;
    if (map.isStyleLoaded()) { done = true; fn(); }
    else setTimeout(run, 120);
  };
  map.on('style.load', () => { if (!done) { done = true; fn(); } });
  setTimeout(run, 0);
}

function baseStyle(mode = 'imagery') {
  const sources = {};
  const layers = [];
  for (const [key, b] of Object.entries(BASEMAPS)) {
    sources[`bm-${key}`] = { type: 'raster', tiles: b.tiles, tileSize: 256, attribution: b.attribution };
    layers.push({
      id: `bm-${key}`, type: 'raster', source: `bm-${key}`,
      layout: { visibility: key === mode ? 'visible' : 'none' },
      paint: { 'raster-opacity': 1 },
    });
  }
  return { version: 8, sources, layers };
}

function destroyMap() {
  if (state.map) {
    state.map.remove();
    state.map = null;
  }
}

function buildSiteMap(payload) {
  const { meta, network, events, hotspots, zones } = payload;
  const map = new maplibregl.Map({
    container: 'map',
    style: baseStyle(state.basemap),
    center: meta.center,
    zoom: meta.zoom,
    attributionControl: true,
  });
  state.map = map;
  map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right');
  map.addControl(new maplibregl.ScaleControl({ maxWidth: 120, unit: 'metric' }), 'bottom-right');

  whenStyleReady(map, () => {
    $('#map .loading')?.classList.add('hide');
    addOverlay(map, meta, state.overlay);
    if (zones && state.show.zones) addZones(map, zones);
    if (network) addNetwork(map, network);
    if (events) addEvents(map, events, state.site.id);
    if (hotspots) addHotspots(map, hotspots);
    addSelectionLayer(map);
    applyVisibility();
    applyYearFilter();
    bindMapInteractions(map);
    updateLegend();
    updateEventCount();
  });

  const note = document.createElement('div');
  note.className = 'map-note';
  note.innerHTML = siteMapNote(state.site);
  $('#map').appendChild(note);
}

function siteMapNote(site) {
  if (site.id === 'bulgaria') return '<b>Screening demo.</b> Raster = weather-normalised evidence. Points = ranked candidates, not confirmed leaks.';
  return '<b>Validation case.</b> Colour raster = leak-likelihood score; yellow points = repair/break records.';
}

function addOverlay(map, meta, kind) {
  const layer = (meta.layers || []).find((l) => l.kind === kind) || (meta.layers || [])[0];
  if (!layer) return;
  const [w, s, e, n] = layer.bounds;
  if (map.getLayer('overlay')) map.removeLayer('overlay');
  if (map.getSource('overlay')) map.removeSource('overlay');
  map.addSource('overlay', {
    type: 'image',
    url: `./data/${meta.id}/${layer.file}`,
    coordinates: [[w, n], [e, n], [e, s], [w, s]],
  });
  map.addLayer({
    id: 'overlay', type: 'raster', source: 'overlay',
    paint: { 'raster-opacity': 0.72, 'raster-fade-duration': 0 },
  });
}

function setOverlay(kind) {
  if (!state.map || !state.meta) return;
  state.overlay = kind;
  addOverlay(state.map, state.meta, kind);
  // Keep network/events above the raster.
  for (const id of ['network-line', 'network-hit', 'events-circle', 'hotspots-circle', 'zones-line', 'zones-fill', 'selection-point', 'selection-line']) {
    if (state.map.getLayer(id)) state.map.moveLayer(id);
  }
  updateLegend();
}

function addNetwork(map, fc) {
  map.addSource('network', { type: 'geojson', data: fc, generateId: true });
  map.addLayer({
    id: 'network-line', type: 'line', source: 'network',
    paint: { 'line-color': '#7ee0b0', 'line-width': ['interpolate', ['linear'], ['zoom'], 8, 1, 13, 2.2], 'line-opacity': 0.62 },
  });
  map.addLayer({
    id: 'network-hit', type: 'line', source: 'network',
    paint: { 'line-color': '#000', 'line-width': 9, 'line-opacity': 0 },
  });
}

function addEvents(map, fc, siteId) {
  map.addSource('events', { type: 'geojson', data: fc });
  map.addLayer({
    id: 'events-circle', type: 'circle', source: 'events',
    paint: {
      'circle-color': '#ffd166',
      'circle-radius': ['interpolate', ['linear'], ['zoom'], 8, 2.2, 13, 4.4, 16, 7],
      'circle-stroke-color': '#06100c',
      'circle-stroke-width': 1.1,
      'circle-opacity': 0.92,
    },
  });
}

function addHotspots(map, fc) {
  map.addSource('hotspots', { type: 'geojson', data: fc });
  map.addLayer({
    id: 'hotspots-circle', type: 'circle', source: 'hotspots',
    paint: {
      'circle-color': '#ff5c8a',
      'circle-radius': ['interpolate', ['linear'], ['zoom'], 8, 2.4, 13, 5, 16, 8],
      'circle-stroke-color': '#2a0714',
      'circle-stroke-width': 1.2,
      'circle-opacity': 0.85,
    },
  });
}

function addZones(map, fc) {
  map.addSource('zones', { type: 'geojson', data: fc });
  map.addLayer({
    id: 'zones-fill', type: 'fill', source: 'zones',
    paint: { 'fill-color': '#4cc9f0', 'fill-opacity': 0.035 },
  });
  map.addLayer({
    id: 'zones-line', type: 'line', source: 'zones',
    paint: { 'line-color': '#4cc9f0', 'line-width': 1.1, 'line-opacity': 0.55, 'line-dasharray': [4, 4] },
  });
}

function addSelectionLayer(map) {
  map.addSource('selection', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });
  map.addLayer({
    id: 'selection-point', type: 'circle', source: 'selection',
    filter: ['==', ['geometry-type'], 'Point'],
    paint: { 'circle-radius': 9, 'circle-color': 'rgba(0,0,0,0)', 'circle-stroke-color': '#ffffff', 'circle-stroke-width': 2 },
  });
  map.addLayer({
    id: 'selection-line', type: 'line', source: 'selection',
    filter: ['==', ['geometry-type'], 'LineString'],
    paint: { 'line-color': '#ffffff', 'line-width': 4, 'line-opacity': 0.9 },
  });
}

function applyVisibility() {
  if (!state.map) return;
  const map = state.map;
  const set = (id, on) => { if (map.getLayer(id)) map.setLayoutProperty(id, 'visibility', on ? 'visible' : 'none'); };
  set('network-line', state.show.network);
  set('network-hit', state.show.network);
  set('events-circle', state.show.events);
  set('hotspots-circle', state.show.hotspots);
  set('zones-fill', state.show.zones);
  set('zones-line', state.show.zones);
}

function setBasemap(mode) {
  if (!state.map) return;
  for (const key of Object.keys(BASEMAPS)) {
    if (state.map.getLayer(`bm-${key}`)) {
      state.map.setLayoutProperty(`bm-${key}`, 'visibility', key === mode ? 'visible' : 'none');
    }
  }
}

function setYear(year) {
  state.year = year;
  $$('#histogram button').forEach((b) => b.classList.toggle('active', b.dataset.year === String(year)));
  applyYearFilter();
  updateEventCount();
}

function applyYearFilter() {
  if (!state.map || !state.map.getLayer('events-circle')) return;
  if (state.year === 'all') state.map.setFilter('events-circle', null);
  else if (state.year === 'nisar') state.map.setFilter('events-circle', ['>=', ['get', 'date'], '2025-10-17']);
  else state.map.setFilter('events-circle', ['==', ['to-number', ['get', 'year']], Number(state.year)]);
}

function updateEventCount() {
  const el = $('#event-count');
  if (!el || !state.data?.events) return;
  const n = state.data.events.features.length;
  const shown = state.year === 'all'
    ? n
    : state.year === 'nisar'
      ? state.data.events.features.filter((f) => (f.properties.date || '') >= '2025-10-17').length
      : state.data.events.features.filter((f) => String(f.properties.year) === String(state.year)).length;
  el.textContent = state.year === 'all'
    ? `${n.toLocaleString()} records shown.`
    : state.year === 'nisar'
      ? `${shown.toLocaleString()} of ${n.toLocaleString()} records on/after 2025-10-17.`
      : `${shown.toLocaleString()} of ${n.toLocaleString()} records in ${state.year}.`;
}

/* ------------------------------------------------------------------ interaction */
function bindMapInteractions(map) {
  let tooltip = $('#tooltip');
  if (!tooltip) {
    tooltip = document.createElement('div');
    tooltip.id = 'tooltip';
    $('#map').appendChild(tooltip);
  }
  const showTip = (e, html) => {
    tooltip.innerHTML = html;
    tooltip.style.display = 'block';
    tooltip.style.left = `${e.point.x + 14}px`;
    tooltip.style.top = `${e.point.y + 14}px`;
  };
  const hideTip = () => { tooltip.style.display = 'none'; };

  const layers = ['events-circle', 'hotspots-circle', 'network-hit'].filter((id) => map.getLayer(id));
  for (const layer of layers) {
    map.on('mousemove', layer, (e) => {
      map.getCanvas().style.cursor = 'pointer';
      const p = e.features[0].properties;
      if (layer === 'events-circle') {
        showTip(e, `<b>${esc(p.date || 'record')}</b>${p.cause ? ` · ${esc(p.cause)}` : ''}${p.size ? ` · ${esc(p.size)}` : ''}`);
      } else if (layer === 'hotspots-circle') {
        showTip(e, `<b>Candidate ${esc(fmt(p.score, 1))}/100</b><br>moisture z ${esc(fmt(p.moisture, 2))}`);
      } else {
        showTip(e, '<b>Mapped water main</b>');
      }
    });
    map.on('mouseleave', layer, () => { map.getCanvas().style.cursor = ''; hideTip(); });
    map.on('click', layer, (e) => {
      hideTip();
      // A point click must win over the wide invisible pipe hit layer.
      if (layer === 'network-hit') {
        const points = ['events-circle', 'hotspots-circle'].filter((id) => map.getLayer(id));
        if (points.length && map.queryRenderedFeatures(e.point, { layers: points }).length) return;
      }
      const f = e.features[0];
      if (layer === 'events-circle') selectFeature('event', f);
      else if (layer === 'hotspots-circle') selectFeature('hotspot', f);
      else selectFeature('network', f);
    });
  }
  map.on('click', (e) => {
    if (e.defaultPrevented) return;
    const hits = map.queryRenderedFeatures(e.point, { layers: layers });
    if (!hits.length) clearSelection();
  });
}

function selectFeature(kind, feature) {
  setSelectionHighlight(feature);
  state.selection = { kind, props: feature.properties, geometry: feature.geometry };
  renderEvidence();
  $('#app main').classList.add('show-evidence');
}

function setSelectionHighlight(feature) {
  if (!state.map) return;
  const src = state.map.getSource('selection');
  if (!src) return;
  src.setData({ type: 'FeatureCollection', features: [{ type: 'Feature', geometry: feature.geometry, properties: {} }] });
  if (feature.geometry.type === 'Point') {
    state.map.flyTo({ center: feature.geometry.coordinates, zoom: Math.max(state.map.getZoom(), 14), duration: 500 });
  }
}

function clearSelection() {
  state.selection = null;
  state.map?.getSource('selection')?.setData({ type: 'FeatureCollection', features: [] });
  renderDefaultEvidence();
  $('#app main').classList.remove('show-evidence');
}

/* ------------------------------------------------------------------ evidence */
function renderDefaultEvidence() {
  if (!state.site) return;
  const s = state.site;
  const m = s.metrics;
  const isCoryell = s.id === 'coryell';
  const corridor = m.corridor_p == null ? '—' : `${fmt(m.corridor_p, 2)}${m.corridor_p95 != null ? ` · p95 ${fmt(m.corridor_p95, 2)}` : ''}`;
  $('#evidence').innerHTML = `
    <div class="side-section">
      <div class="evidence-head">
        <div>
          <div class="eyebrow">Evidence panel</div>
          <h3>What this site can support</h3>
        </div>
      </div>
      <p>Click a point, pipe or candidate hotspot on the map. The panel keeps the three evidence
         types separate so a modelled score is never presented as an observation.</p>
      <div class="kv">
        <span class="k"><span class="tag obs">observed</span></span><span class="v">${m.n_labels || s.labels || 0} ground-truth labels; mapped network</span>
        <span class="k"><span class="tag mod">modelled</span></span><span class="v">Expected-condition residuals; leak score${m.vv_r2 != null ? `; VV R² ${fmt(m.vv_r2, 2)}` : ''}</span>
        <span class="k"><span class="tag inf">inferred</span></span><span class="v">A place to investigate, never a confirmed leak</span>
      </div>
      <h2 style="margin-top:16px">Validation</h2>
      <div class="kv">
        <span class="k">VV model</span><span class="v">R² ${fmt(m.vv_r2, 2)} · MAE ${fmt(m.vv_mae, 2)} dB</span>
        <span class="k">NDMI model</span><span class="v">R² ${fmt(m.ndmi_r2, 2)} · MAE ${fmt(m.ndmi_mae, 3)}</span>
        ${m.label_auc != null ? `<span class="k">Label ranking</span><span class="v">AUC ${fmt(m.label_auc, 3)} · median percentile ${fmt(m.label_percentile, 1)}</span>` : ''}
        <span class="k">Corridor test</span><span class="v">p = ${corridor}</span>
      </div>
      <div class="caveat">${m.label_auc != null
        ? `Label AUC is close to random. ${isCoryell ? 'Coryell’s mean corridor p is nominally small, but the p95 test is 0.24; treat it as exploratory, not detection.' : 'Treat this as a screening demonstration, not a detector.'}`
        : 'No confirmed leak labels. The corridor enrichment test is not significant; the map is a hypothesis generator.'}</div>
      <div class="evidence-actions">
        <button id="jump-results">Open results</button>
        <button id="jump-method">How it works</button>
      </div>
    </div>`;
  $('#jump-results')?.addEventListener('click', () => { location.hash = 'compare'; });
  $('#jump-method')?.addEventListener('click', () => { location.hash = 'method'; });
}

function renderEvidence() {
  if (!state.selection) return renderDefaultEvidence();
  const { kind, props } = state.selection;
  const head = kind === 'event' ? 'Repair / label' : kind === 'hotspot' ? 'Candidate hotspot' : 'Pipe segment';
  $('#evidence').innerHTML = `
    <div class="side-section">
      <div class="evidence-head">
        <div>
          <div class="eyebrow">${esc(head)}</div>
          <h3>${esc(kind === 'event' ? (props.date || 'record') : kind === 'hotspot' ? `Score ${fmt(props.score, 1)} / 100` : (props.size_label || 'Mapped main'))}</h3>
        </div>
        <button class="close" id="close-evidence" aria-label="Close">×</button>
      </div>
      ${kind === 'event' ? eventEvidence(props) : kind === 'hotspot' ? hotspotEvidence(props) : networkEvidence(props)}
      <div class="evidence-actions">
        <button id="back-to-site">Site summary</button>
      </div>
    </div>`;
  $('#close-evidence').addEventListener('click', clearSelection);
  $('#back-to-site').addEventListener('click', clearSelection);
}

function eventEvidence(p) {
  const rows = [
    ['date', p.date],
    ['cause', p.cause || p.activity],
    ['break type', p.break_type],
    ['pipe size', p.size || p.line_size],
    ['water loss', p.loss != null ? `${p.loss} gpm` : null],
    ['repair', p.repair],
    ['zone', p.zone],
  ].filter(([, v]) => v != null && v !== '');
  return `
    <div class="kv">
      ${rows.map(([k, v]) => `<span class="k">${esc(k)}</span><span class="v">${esc(v)}</span>`).join('')}
    </div>
    <div class="caveat" style="margin-top:12px">
      <span class="tag obs">observed</span> Field record. The date is when the repair was logged,
      not when leakage began. It is a weak label for a persistent leak.
    </div>
    ${p.zone ? `<p style="margin-top:10px">Pressure zone: <strong>${esc(p.zone)}</strong>. Zone context is descriptive, not causal.</p>` : ''}`;
}

function hotspotEvidence(p) {
  return `
    <div class="kv">
      <span class="k"><span class="tag mod">modelled</span>score</span><span class="v">${fmt(p.score, 1)} / 100</span>
      <span class="k">moisture z</span><span class="v">${fmt(p.moisture, 2)}</span>
      <span class="k">persistence</span><span class="v">${fmt(p.persistence, 2)}</span>
      <span class="k">thermal z</span><span class="v">${fmt(p.thermal, 2)}</span>
      <span class="k">confidence</span><span class="v">${fmt(p.confidence, 0)} / 100</span>
      <span class="k">distance to main</span><span class="v">${fmt(p.dist_water, 0)} m</span>
      <span class="k">top dates</span><span class="v">${esc((p.dates || '').replace(/[\[\]']/g, '')) || '—'}</span>
    </div>
    <div class="caveat" style="margin-top:12px">
      <span class="tag inf">inferred</span> A place where the surface stayed wetter than weather and
      land cover predict. It is not a confirmed leak. Field inspection is required.
    </div>`;
}

function networkEvidence() {
  return `<p>This is the mapped water main used as the proximity prior. The case does not include
      per-segment attributes, so only the geometry and its distance context are available.</p>
      <div class="caveat"><span class="tag obs">observed</span> Network geometry from the utility.
      <span class="tag mod">modelled</span> Proximity weighting in the leak score.</div>`;
}

/* ------------------------------------------------------------------ compare */
function renderCompare() {
  state.site = null; state.meta = null; state.data = null;
  destroyMap();
  $('#app main').className = 'doc-view';
  $('#doc').hidden = false;
  $('#sidebar').innerHTML = '';
  $('#evidence').innerHTML = '';
  $('#map').innerHTML = '';
  const sites = state.sites;
  const row = (s) => {
    const m = s.metrics;
    const auc = m.label_auc;
    const verdict = auc == null
      ? ['bad', 'unlabelled']
      : auc > 0.6 ? ['ok', 'useful'] : auc > 0.5 ? ['warn', 'weak'] : ['bad', 'not better'];
    const v = verdict;
    return `<tr>
      <td><strong>${esc(s.name)}</strong><br><span style="color:var(--muted);font-size:11px">${esc(s.subtitle)}</span></td>
      <td>Sentinel-1 expected condition</td>
      <td class="num">${s.labels ? s.labels.toLocaleString() : '—'}</td>
      <td class="num">${s.dates || '—'}</td>
      <td class="num">${fmt(m.vv_r2, 2)}</td>
      <td class="num">${fmt(m.ndmi_r2, 2)}</td>
      <td class="num">${auc == null ? '—' : `${fmt(auc, 3)} <span style="color:var(--muted);font-size:10px">label AUC</span>`}</td>
      <td class="num">${m.corridor_p95 == null ? '—' : fmt(m.corridor_p95, 2)}</td>
      <td><span class="pill ${v[0]}">${v[1]}</span></td>
    </tr>`;
  };
  $('#sidebar').innerHTML = '';
  $('#evidence').innerHTML = '';
  $('#map').innerHTML = '';
  $('#map').style.display = 'none';
  $('#sidebar').style.display = 'none';
  $('#evidence').style.display = 'none';
  const main = $('#doc');
  main.innerHTML = `
    <div class="doc">
      <div class="doc-inner">
        <div class="eyebrow">Cross-site comparison</div>
        <h1>What is actually validated?</h1>
        <p class="lead">Four studies, one pipeline. The table separates model skill (predicting a surface
          state) from label ranking (does the final score find repairs?). Every case uses the same
          20 m grid, the same weather-normalised expected-condition model and the same validation code.</p>

        <div class="cards3">
          <div class="card"><h3>Surface models are skilful</h3><div class="big">0.25–0.65</div><p>VV and NDMI R² across the three Sentinel-1 cases. Weather, soil and season explain most of the variance.</p></div>
          <div class="card"><h3>The leak score is weak</h3><div class="big">≈ 0.53</div><p>Label AUC is 0.526, 0.524 and 0.548 in the three labelled cities. The honest result is a screening tool, not a detector.</p></div>
          <div class="card"><h3>One corridor test is nominally small</h3><div class="big">0.024</div><p>Coryell’s mean corridor placebo p is 0.024, but the p95 test is 0.24 and its label AUC is 0.548. One nominal result in four sites is not a validated detector.</p></div>
        </div>

        <h2>The comparison</h2>
        <div style="overflow-x:auto">
          <table class="compare">
            <thead><tr>
              <th>Site</th><th>Model</th><th>Labels</th><th>S1 dates</th><th>VV R²</th><th>NDMI R²</th><th>Final AUC</th><th>Corridor p95</th><th>Verdict</th>
            </tr></thead>
            <tbody>${sites.map(row).join('')}</tbody>
          </table>
        </div>

        <h2>Model skill, side by side</h2>
        <div class="metric-bars">
          ${sites.filter((s) => s.metrics.vv_r2 != null).map((s) => `
            <div class="metric-bar-row"><span>${esc(s.name)} · VV</span>
              <div class="track"><div class="fill" style="width:${Math.max(2, s.metrics.vv_r2 * 100)}%"></div></div>
              <span class="val">${fmt(s.metrics.vv_r2, 2)}</span></div>`).join('')}
          ${sites.filter((s) => s.metrics.ndmi_r2 != null).map((s) => `
            <div class="metric-bar-row"><span>${esc(s.name)} · NDMI</span>
              <div class="track"><div class="fill" style="width:${Math.max(2, s.metrics.ndmi_r2 * 100)}%;background:linear-gradient(90deg,#2e6f8f,#4cc9f0)"></div></div>
              <span class="val">${fmt(s.metrics.ndmi_r2, 2)}</span></div>`).join('')}
        </div>

        <h2>What the final score adds</h2>
        <p>For the Sentinel-1 cases the final score combines moisture residual, persistence, thermal cooling and
          pipe proximity. Against historical repair coordinates its AUC is <strong>0.526</strong> (Aguascalientes),
          <strong>0.524</strong> (Calgary) and <strong>0.548</strong> (Coryell). All are weak positives, and the
          corridor p95 tests are non-significant (1.00, 0.95 and 0.24). Coryell’s mean corridor p is 0.024, but a
          single nominal mean result does not overturn the label ranking. Do not present this as leak detection.</p>

        <h2>Why keep all four?</h2>
        <p>They are the same method in different environments: a dry Bulgarian corridor with no labels, a dense
          Mexican urban network, a Canadian trunk network, and a rural Texas district. Running Coryell through the
          identical pipeline shows that the result is not an artefact of one city — and that the weak label signal
          repeats. A single platform makes that comparison visible instead of collapsing everything into one
          “leak probability”.</p>

        <h2>Read the evidence files</h2>
        <p><a href="../outputs/validation.json" target="_blank" rel="noopener">Bulgaria validation</a> ·
           <a href="../case_studies/aguascalientes/outputs/validation.json" target="_blank" rel="noopener">Aguascalientes validation</a> ·
           <a href="../case_studies/calgary/outputs/validation.json" target="_blank" rel="noopener">Calgary validation</a> ·
           <a href="../case_studies/coryell/outputs/validation.json" target="_blank" rel="noopener">Coryell validation</a></p>
      </div>
    </div>`;
}

/* ------------------------------------------------------------------ method */
function renderMethod() {
  state.site = null; state.meta = null; state.data = null;
  destroyMap();
  $('#app main').className = 'doc-view';
  $('#doc').hidden = false;
  $('#sidebar').innerHTML = '';
  $('#evidence').innerHTML = '';
  $('#map').innerHTML = '';
  $('#map').style.display = 'none';
  $('#sidebar').style.display = 'none';
  $('#evidence').style.display = 'none';
  const main = $('#doc');
  main.innerHTML = `
    <div class="doc">
      <div class="doc-inner">
        <div class="eyebrow">Method & limits</div>
        <h1>One workflow, four evidence checks</h1>
        <p class="lead">TerraGuard asks a narrower question than “where is the leak?”: where does the surface
          stay wetter (or cooler) than weather, soil, land cover and season predict — and does that anomaly
          line up with a pipe, a repair record, or a radar change?</p>

        <h2>1. The pipeline</h2>
        <pre class="code">Sentinel-1 RTC ─┐
Sentinel-2 NDMI ├─→ align to one 20 m UTM grid ─→ expected-condition model
Landsat LST     │                                  (LightGBM, ordinary dates only)
ERA5 weather    │                                            │
soil / terrain ─┘                                            ▼
                                              residual = observed − expected
                                                         │
                                     dry-season mean + persistence + thermal
                                                         │
                                          pipe proximity weighting
                                                         ▼
                                     leak-likelihood raster + hotspot cards
                                                         │
                                          validation: placebo corridors,
                                          label ranking, temporal holdout</pre>

        <h2>2. Features</h2>
        <table class="compare">
          <thead><tr><th>Block</th><th>Features</th><th>Why</th></tr></thead>
          <tbody>
            <tr><td>Static (21)</td><td>DEM, slope, sand/clay/silt, SOC, bulk density, distance to buildings/roads, 10 land-cover one-hots</td><td>Absorbs what does not change: soil, terrain, land use</td></tr>
            <tr><td>Observation (7)</td><td>VV, VH, local VV texture, NDMI, NDVI, LST, scene-relative LST</td><td>What the pixel looks like at acquisition</td></tr>
            <tr><td>Weather (22)</td><td>Rain 1/3/7/14/30/60 d, temperature means and maxima, ET₀, soil moisture at three depths, VPD, dry days, anomalies, season</td><td>Removes the weather explanation before calling an anomaly</td></tr>
            <tr><td>Targets</td><td>VV backscatter and NDMI</td><td>Two independent expected-condition models; the targets are removed from their own feature set</td></tr>
          </tbody>
        </table>

        <h2>3. Normalisation, in order</h2>
        <ol>
          <li><strong>Radiometric.</strong> dB, valid-mask and exception-mask filtering, same track/polarisation comparison group, fixed display stretch. No per-image histogram equalisation.</li>
          <li><strong>Input scaling.</strong> None for trees; <code>StandardScaler</code> only for the logistic comparisons, fitted inside each training fold.</li>
          <li><strong>Weather normalisation.</strong> <code>expected = f(weather, soil, terrain, land cover, season)</code>; residual <code>r = observed − expected</code>. This is the core step: weather is the normaliser, not another hopeful covariate.</li>
          <li><strong>Residual scaling.</strong> Robust z-score <code>(r − median) / (1.4826 · MAD)</code>, fitted on training dates only and per land-cover class. The leak raster is display-stretched to the site median–p99; the absolute score stays in the evidence panel.</li>
          <li><strong>Cross-site.</strong> Local contrast (pipe minus a 100–300 m annulus), within-city percentile, matched controls, translated placebo corridors.</li>
        </ol>
        <div class="caveat red">Never standardise a pixel against its own time series: that removes the persistent anomaly a leak produces.
          Never fit a scaler, median or weather baseline on data that includes the evaluation period.</div>

        <h2>4. What each site adds</h2>
        <div class="cards3">
          <div class="card"><h3>Elin Pelin</h3><p><strong>Method demo.</strong> Weather-normalised VV/NDMI, thermal cooling, persistence, a 3.3 km OSM main, and a 200-corridor placebo test. No labels.</p></div>
          <div class="card"><h3>Aguascalientes</h3><p><strong>Urban label test.</strong> 50 dry-season repairs on 8,134 segments; 28 S1 dates. Final score AUC 0.526.</p></div>
          <div class="card"><h3>Calgary</h3><p><strong>Trunk-network test.</strong> 48 breaks on 5,879 segments; 50 dates across 2025–26. Final score AUC 0.524.</p></div>
          <div class="card"><h3>Coryell</h3><p><strong>Rural label test.</strong> 72 summer repairs on 184 segments; 55 S1 dates. VV R² 0.43, NDMI R² 0.50, label AUC 0.548; mean corridor p 0.024, p95 0.24.</p></div>
        </div>

        <h2>5. What is new in this platform</h2>
        <ul>
          <li><strong>One contract.</strong> Every site exports the same meta, network, events and overlay schema, so a new area is a data task, not a UI rewrite.</li>
          <li><strong>One map.</strong> MapLibre replaces the per-case Leaflet pages; raster overlays, pipes, repairs and candidates share a view.</li>
          <li><strong>Coryell.</strong> The fourth case is now a normal pipeline run: 72 summer repairs, 55 Sentinel-1 dates, the same 20 m expected-condition model and the same placebo/label tests.</li>
          <li><strong>Evidence separation.</strong> Observed, modelled and inferred are labelled separately; no composite “leak probability”.</li>
          <li><strong>Honest comparison.</strong> Model skill and label ranking are reported separately; no score is presented as a leak probability.</li>
        </ul>

        <h2>6. Limits</h2>
        <ul>
          <li>The Sentinel-1 cases have <strong>no confirmed leak</strong>: repairs are bursts, not persistent leakage, and dates are report dates.</li>
          <li>Label AUC ≈ 0.52–0.55 is close to random. The corridor p95 tests are not significant; Coryell’s mean p is nominally 0.024 but its p95 is 0.24.</li>
          <li>20 m pixels and ~100 m thermal cannot localise a metre-scale pipe failure.</li>
          <li>Urban land cover, irrigation, snow, roads and construction produce the same surface signatures.</li>
          <li>Coryell has <strong>no stated open licence</strong>; the layers are bundled for the hackathon only.</li>
          <li>NISAR chips are not bundled: they need an Earthdata login. The Bulgarian NISAR layers are 8-bit browse, display-only.</li>
          <li>Calgary’s RTC archive starts April 2025; the Bulgarian weather covariates start in 2022.</li>
        </ul>

        <h2>7. Rebuild the platform data</h2>
        <pre class="code">cd chris-results
pixi install                       # or use the parent .pixi environment
python scripts/fetch_coryell.py    # public ArcGIS vectors, no login
CASE=case_studies/coryell/case.json
TERRAGUARD_CASE=$CASE python -m pipeline.acquire --workers 16
TERRAGUARD_CASE=$CASE python -m pipeline.model
TERRAGUARD_CASE=$CASE python -m pipeline.make_map
python scripts/build_platform_data.py
./run_dashboard.sh                 # http://127.0.0.1:8766/app/</pre>
        <p>Full method notes: <a href="../docs/RESULTS.md">docs/RESULTS.md</a> ·
           research: <a href="../research/Pipeline-Leak-Detection.md">Pipeline-Leak-Detection.md</a> ·
           case notes: <a href="../case_studies/README.md">case_studies/README.md</a>.</p>
      </div>
    </div>`;
}

function showSources() {
  const meta = state.meta;
  if (!meta) return;
  $('#about-title').textContent = `${meta.name} — sources`;
  $('#about-body').innerHTML = `
    <ul>${(meta.sources || []).map((s) => `<li>${esc(s)}</li>`).join('')}</ul>
    ${meta.caveats?.length ? `<h3>Caveats</h3><ul>${meta.caveats.map((c) => `<li>${esc(c)}</li>`).join('')}</ul>` : ''}
    <p>Raster overlays are pre-rendered from the bundled GeoTIFFs. Basemaps are loaded from Esri, OpenStreetMap
       and CARTO and require an internet connection.</p>`;
  $('#about').showModal();
}

/* ------------------------------------------------------------------ legend */
function updateLegend() {
  const el = $('#legend');
  if (!el || !state.meta) return;
  const layer = (state.meta.layers || []).find((l) => l.kind === state.overlay);
  if (!layer) return;
  const cmap = state.overlay === 'leak'
    ? 'linear-gradient(90deg,#1b0c2e,#6a1c66,#c43c4b,#fe9f6d,#fcfdbf)'
    : state.overlay === 'moisture'
      ? 'linear-gradient(90deg,#2166ac,#92c5de,#f7f7f7,#f4a582,#b2182b)'
      : state.overlay === 'nisar'
        ? 'linear-gradient(90deg,#000,#888,#fff)'
        : 'linear-gradient(90deg,#440154,#3b528b,#21918c,#5ec962,#fde725)';
  const vmin = layer.vmin != null ? Number(layer.vmin) : state.overlay === 'leak' ? 0 : state.overlay === 'moisture' ? -2.5 : state.overlay === 'nisar' ? 0 : 0;
  const vmax = layer.vmax != null ? Number(layer.vmax) : state.overlay === 'leak' ? 100 : state.overlay === 'moisture' ? 2.5 : state.overlay === 'nisar' ? 255 : 1;
  const mid = (vmin + vmax) / 2;
  const nf = (v) => Number.isInteger(v) ? String(v) : v.toFixed(2);
  const labels = [nf(vmin), nf(mid), nf(vmax)];
  const title = state.overlay === 'leak'
    ? `${layer.label} · display ${nf(vmin)}–${nf(vmax)} of 0–100`
    : `${layer.label} (${layer.unit})`;
  el.innerHTML = `
    <div class="legend-title">${esc(title)}</div>
    <div class="legend-bar" style="background:${cmap}"></div>
    <div class="legend-labels">${labels.map((l) => `<span>${l}</span>`).join('')}</div>`;
}

/* ------------------------------------------------------------------ css for markers */
const style = document.createElement('style');
style.textContent = `
.site-marker {
  display: flex; align-items: center; gap: 7px;
  background: rgba(6,16,12,.9); border: 1px solid #2c4a3d; border-radius: 999px;
  color: #e6f1ec; padding: 4px 9px 4px 5px; cursor: pointer; font: inherit; font-size: 11px;
  box-shadow: 0 6px 20px rgba(0,0,0,.35); white-space: nowrap;
}
.site-marker:hover { border-color: #7ee0b0; }
.site-marker .pin { width: 8px; height: 8px; border-radius: 50%; background: #7ee0b0; box-shadow: 0 0 10px #7ee0b0; }
.site-marker .lbl { font-weight: 600; }
`;
document.head.appendChild(style);

boot().catch((err) => {
  console.error(err);
  document.body.innerHTML = `<pre style="padding:24px;color:#ffb4a8">TerraGuard failed to start:\n${esc(err.stack || err)}</pre>`;
});

// Exposed for browser smoke tests; harmless in production.
window.__tg = { state, selectFeature, clearSelection };
