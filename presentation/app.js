// AquaGuard · presentation dashboard
// Deck navigation, progressive reveals, speaker notes and the live Coryell map.

document.documentElement.classList.remove('no-js');

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
const pad2 = (n) => String(n).padStart(2, '0');
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const fmt = (n) => Number(n).toLocaleString('en-US');

const slides = $$('.slide');
const TOTAL = slides.length;
const deck = $('#deck');
const notesPanel = $('#notes');
const notesBody = $('#notes-body');
const notesSlide = $('#notes-slide');

let index = -1;
let direction = 1;
let notesOpen = false;
let autoPlaying = false;
let autoTimer = 0;
let toastTimer = 0;
let wheelAcc = 0;
let wheelLocked = false;
let touchStart = null;

/* --------------------------------------------------------------- chrome -- */
$('#total-num').textContent = TOTAL;

const rail = $('#rail');
slides.forEach((slide, i) => {
  const b = document.createElement('button');
  b.type = 'button';
  b.className = 'rail-dot';
  b.dataset.label = `${pad2(i + 1)} · ${slide.dataset.title}`;
  b.setAttribute('aria-label', `Go to slide ${i + 1}: ${slide.dataset.title}`);
  b.addEventListener('click', () => go(i));
  rail.appendChild(b);
});
const railDots = $$('.rail-dot', rail);

// Stagger the reveals inside each slide, capped so the last ones still arrive.
slides.forEach((slide) => {
  $$('.reveal', slide).forEach((el, i) => el.style.setProperty('--i', Math.min(i, 9)));
});

function updateChrome() {
  const slide = slides[index];
  $('#cur-num').textContent = index + 1;
  $('#chapter-num').textContent = pad2(index);
  $('#chapter-name').textContent = slide.dataset.chapter;
  $('#slide-title').textContent = slide.dataset.title;
  $('#slide-count').textContent = `${pad2(index + 1)} / ${pad2(TOTAL)}`;
  const pct = TOTAL > 1 ? (index / (TOTAL - 1)) * 100 : 0;
  $('#progress-fill').style.width = pct + '%';
  $('#progress-knob').style.left = pct + '%';
  $('#prev-btn').disabled = index === 0;
  $('#next-btn').disabled = index === TOTAL - 1;
  railDots.forEach((d, i) => d.classList.toggle('on', i === index));
  if (notesOpen) renderNotes();
  document.title = `${slide.dataset.title} · AquaGuard`;
}

function animateCounters(scope) {
  $$('[data-count]', scope).forEach((el) => {
    const target = Number(el.dataset.count);
    if (!Number.isFinite(target)) return;
    const decimals = Number(el.dataset.decimals || 0);
    const dur = 900;
    const t0 = performance.now();
    cancelAnimationFrame(el._countRaf);
    const tick = (now) => {
      const p = Math.min(1, (now - t0) / dur);
      const eased = 1 - Math.pow(1 - p, 3);
      const v = target * eased;
      el.textContent = decimals ? v.toFixed(decimals) : fmt(Math.round(v));
      if (p < 1) el._countRaf = requestAnimationFrame(tick);
    };
    el._countRaf = requestAnimationFrame(tick);
  });
}

/* ------------------------------------------------------------ navigation -- */
function readHash() {
  const m = (location.hash || '').match(/(\d+)/);
  if (!m) return 0;
  const n = Number(m[1]);
  return Number.isFinite(n) ? Math.max(0, Math.min(TOTAL - 1, n)) : 0;
}

function go(n, opts = {}) {
  const target = Math.max(0, Math.min(TOTAL - 1, n));
  if (target === index && !opts.force) return;
  const prev = index;
  direction = target >= prev ? 1 : -1;
  index = target;

  slides.forEach((slide, i) => {
    slide.classList.toggle('active', i === index);
    slide.classList.toggle('dir-back', i === index && direction < 0);
    slide.setAttribute('aria-hidden', i === index ? 'false' : 'true');
  });

  updateChrome();
  animateCounters(slides[index]);

  if (index === 5) {
    initMap().then(() => {
      if (!mapState) return;
      requestAnimationFrame(() => {
        mapState.map.resize();
        if (mapState.ready) mapState.maybeAutoPlay();
      });
    }).catch(() => {});
  } else if (mapState?.playing) {
    stopMapPlay();
  }

  if (index === 6) {
    initPasses().then(() => {
      if (index === 6) animatePasses();
    }).catch(() => {});
  }
  if (index === 7) initViewer().catch(() => {});
  else stopBlink();

  if (!opts.fromHistory) {
    history.pushState({ slide: index }, '', `#/${index}`);
  }

  if (autoPlaying) scheduleAuto();
}

function next() { go(index + 1); }
function prev() { go(index - 1); }

/* ------------------------------------------------------------- autoplay -- */
const autoBtn = $('#deck-play');
function setAuto(on) {
  autoPlaying = on;
  autoBtn.classList.toggle('playing', on);
  clearTimeout(autoTimer);
  if (on) {
    scheduleAuto();
    toast('Autoplay on · 11 s per slide. Press P to pause.');
  } else {
    toast('Autoplay paused.');
  }
}
function scheduleAuto() {
  clearTimeout(autoTimer);
  if (!autoPlaying) return;
  autoTimer = window.setTimeout(() => {
    if (index >= TOTAL - 1) { setAuto(false); return; }
    go(index + 1);
  }, 11000);
}

/* ---------------------------------------------------------------- events -- */
$('#prev-btn').addEventListener('click', prev);
$('#next-btn').addEventListener('click', next);
autoBtn.addEventListener('click', () => setAuto(!autoPlaying));
$$('[data-next]').forEach((b) => b.addEventListener('click', next));
$$('[data-restart]').forEach((b) => b.addEventListener('click', () => go(0)));

$('#notes-btn').addEventListener('click', toggleNotes);
$('#notes-btn-2').addEventListener('click', toggleNotes);
$('#notes-close').addEventListener('click', () => setNotes(false));

$('#fs-btn').addEventListener('click', toggleFullscreen);
document.addEventListener('fullscreenchange', () => {
  $('#fs-label').textContent = document.fullscreenElement ? 'Exit' : 'Fullscreen';
});
$('#help-btn').addEventListener('click', () => {
  toast('← → navigate · Space next · F fullscreen · N notes · P autoplay · Home / End jump');
});

function toggleNotes() { setNotes(!notesOpen); }
function setNotes(on) {
  notesOpen = on;
  notesPanel.hidden = !on;
  if (on) renderNotes();
}
function renderNotes() {
  const slide = slides[index];
  notesSlide.textContent = `${pad2(index + 1)} / ${pad2(TOTAL)}`;
  const text = slide.dataset.notes || 'No notes for this slide.';
  notesBody.innerHTML = '';
  text.split('\n').filter(Boolean).forEach((para) => {
    const p = document.createElement('p');
    p.textContent = para;
    notesBody.appendChild(p);
  });
}

function toggleFullscreen() {
  if (!document.fullscreenElement) {
    document.documentElement.requestFullscreen?.().catch(() => toast('Fullscreen was blocked by the browser.'));
  } else {
    document.exitFullscreen?.();
  }
}

function toast(msg, ms = 3600) {
  const el = $('#toast');
  el.textContent = msg;
  el.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = window.setTimeout(() => el.classList.remove('show'), ms);
}

/* Keyboard */
window.addEventListener('keydown', (e) => {
  if (e.target.closest('input, select, textarea, [contenteditable], #map')) return;
  const inButton = e.target.closest('button');
  const k = e.key;

  if (k === ' ' && inButton) return;
  if (k === 'ArrowRight' || k === 'ArrowDown' || k === 'PageDown' || k === ' ') {
    e.preventDefault(); next(); return;
  }
  if (k === 'ArrowLeft' || k === 'ArrowUp' || k === 'PageUp') {
    e.preventDefault(); prev(); return;
  }
  if (k === 'Home') { e.preventDefault(); go(0); return; }
  if (k === 'End') { e.preventDefault(); go(TOTAL - 1); return; }
  if (k === 'f' || k === 'F') { e.preventDefault(); toggleFullscreen(); return; }
  if (k === 'n' || k === 'N') { e.preventDefault(); toggleNotes(); return; }
  if (k === 'p' || k === 'P') { e.preventDefault(); setAuto(!autoPlaying); return; }
  if (k === '?' || k === '/') { e.preventDefault(); toast('← → navigate · Space next · F fullscreen · N notes · P autoplay · Home / End jump'); return; }
  if (k === 'Escape') { setNotes(false); }
});

/* Wheel */
window.addEventListener('wheel', (e) => {
  if (e.target.closest('#map, .map-panel, .notes, input, select, textarea')) return;
  if (wheelLocked) return;
  if (Math.abs(e.deltaY) < Math.abs(e.deltaX)) return;
  wheelAcc += e.deltaY;
  if (Math.abs(wheelAcc) < 55) return;
  const dir = wheelAcc > 0 ? 1 : -1;
  wheelAcc = 0;
  wheelLocked = true;
  window.setTimeout(() => { wheelLocked = false; }, 720);
  if (dir > 0) next(); else prev();
}, { passive: true });

/* Touch */
deck.addEventListener('touchstart', (e) => {
  if (e.target.closest('#map, .map-panel, input, select, .notes')) return;
  const t = e.touches[0];
  touchStart = { x: t.clientX, y: t.clientY };
}, { passive: true });
deck.addEventListener('touchend', (e) => {
  if (!touchStart) return;
  const t = e.changedTouches[0];
  const dx = t.clientX - touchStart.x;
  const dy = t.clientY - touchStart.y;
  touchStart = null;
  if (Math.abs(dx) < 48 || Math.abs(dx) < Math.abs(dy)) return;
  if (dx < 0) next(); else prev();
}, { passive: true });

/* History */
window.addEventListener('popstate', () => go(readHash(), { fromHistory: true }));
window.addEventListener('hashchange', () => {
  if (window.__ignoreHash) return;
  const n = readHash();
  if (n !== index) go(n, { fromHistory: true });
});

/* ------------------------------------------------------------------------
   Live map
   ------------------------------------------------------------------------ */
const CORYELL_BOUNDS = [[-97.8906, 31.3479], [-97.4227, 31.7064]];
const TIME_START = Date.UTC(2019, 8, 1);
const TIME_END = Date.UTC(2026, 11, 1);
const DROP_IDS = new Set([1611]);

let mapState = null;
let mapPromise = null;

function startMapPlay() {
  const state = mapState;
  if (!state || !state.ready || state.playing) return;
  if (state.p >= .999) state.p = 0;
  state.playing = true;
  state.last = 0;
  const btn = $('#map-play');
  btn.classList.add('playing');
  btn.querySelector('span').textContent = 'Pause';
  state.applyCursor();

  const tick = (now) => {
    if (!state.playing) return;
    if (!state.last) state.last = now;
    const dt = Math.min(80, now - state.last);
    state.last = now;
    state.p = Math.min(1, state.p + dt / 18000);
    state.applyCursor();
    if (state.p >= 1) {
      stopMapPlay();
      state.applyCursor();
      return;
    }
    state.raf = requestAnimationFrame(tick);
  };
  state.raf = requestAnimationFrame(tick);
}

function stopMapPlay() {
  const state = mapState;
  if (!state) return;
  state.playing = false;
  cancelAnimationFrame(state.raf);
  const btn = $('#map-play');
  if (btn) {
    btn.classList.remove('playing');
    btn.querySelector('span').textContent = 'Play';
  }
}

const COLORS = {
  size: {
    label: 'Pipe size',
    prop: 'sbin',
    bins: [
      { v: 0, label: '≤ 1″', color: '#fff3b0' },
      { v: 1, label: '1½–2″', color: '#fdc94f' },
      { v: 2, label: '2½–3″', color: '#fb8c3c' },
      { v: 3, label: '4–6″', color: '#ef3b2c' },
      { v: 4, label: '8–10″', color: '#c51b7d' },
      { v: -1, label: 'Unknown', color: '#9aa3ad' },
    ],
  },
  loss: {
    label: 'Water loss',
    prop: 'gbin',
    bins: [
      { v: 0, label: '< 10 gpm', color: '#d5f2c4' },
      { v: 1, label: '10–24', color: '#8fdcbc' },
      { v: 2, label: '25–49', color: '#3fbfcf' },
      { v: 3, label: '50–99', color: '#2a8ad8' },
      { v: 4, label: '≥ 100', color: '#6a4cff' },
      { v: -1, label: 'Unknown', color: '#9aa3ad' },
    ],
  },
  cause: {
    label: 'Cause',
    prop: 'cbin',
    bins: [
      { v: 0, label: 'Natural', color: '#4cc9f0' },
      { v: 1, label: 'Construction', color: '#ff4f9a' },
      { v: 2, label: 'Other', color: '#d9d9d9' },
    ],
  },
  year: {
    label: 'Year',
    prop: 'year',
    bins: [
      { v: 2019, label: '2019', color: '#3f51b5' },
      { v: 2020, label: '2020', color: '#2a7f8a' },
      { v: 2021, label: '2021', color: '#2a9d6f' },
      { v: 2022, label: '2022', color: '#5ec962' },
      { v: 2023, label: '2023', color: '#a8d84a' },
      { v: 2024, label: '2024', color: '#e0d63a' },
      { v: 2025, label: '2025', color: '#f7c331' },
      { v: 2026, label: '2026', color: '#fde725' },
      { v: -1, label: 'Unknown', color: '#9aa3ad' },
    ],
  },
};

function parseSize(txt) {
  if (!txt) return null;
  const nums = (String(txt).match(/\d*\.?\d+/g) || []).map(Number).filter((n) => n > 0);
  return nums.length ? Math.max(...nums) : null;
}
function parseGpm(txt) {
  if (!txt) return null;
  const t = String(txt).replace(/,/g, '').replace(/�/g, '"');
  const withUnit = [...t.matchAll(/(\d*\.?\d+)\s*(gpm|gpn|gallons?|gph)/gi)]
    .map((m) => Number(m[1]) / (m[2].toLowerCase() === 'gph' ? 60 : 1));
  if (withUnit.length) return Math.max(...withUnit);
  const all = (t.match(/\d*\.?\d+/g) || []).map(Number);
  return all.length ? all[0] : null;
}
function pretty(s) {
  return s ? String(s).replace(/_+/g, ' ').trim() : null;
}

function prepareLeaks(fc) {
  const out = [];
  for (const f of fc.features || []) {
    const p = f.properties || {};
    if (DROP_IDS.has(p.ObjectId) || !f.geometry) continue;
    const size = parseSize(p.line_size);
    const gpm = parseGpm(p.approximate_water_loss_gpm);
    const rawCause = p.cause_of_leak || '';
    const cbin = rawCause === 'Naturally_Occurred' ? 0 : rawCause === 'Construction_Maintenance_Induce' ? 1 : 2;
    const cause = cbin === 0 ? 'Natural' : cbin === 1 ? 'Construction / maintenance' : 'Other';
    const t = Number(p.datetime);
    const year = Number.isFinite(t) && t > 0 ? new Date(t).getUTCFullYear() : -1;
    out.push({
      type: 'Feature',
      geometry: f.geometry,
      properties: {
        id: p.ObjectId,
        t: Number.isFinite(t) && t > 0 ? t : -1,
        year,
        size: size ?? -1,
        sbin: size == null ? -1 : size <= 1 ? 0 : size <= 2 ? 1 : size <= 3 ? 2 : size <= 6 ? 3 : 4,
        gpm: gpm ?? -1,
        gbin: gpm == null ? -1 : gpm < 10 ? 0 : gpm < 25 ? 1 : gpm < 50 ? 2 : gpm < 100 ? 3 : 4,
        cbin,
        cause,
        zone: p.what_pressure_plane_did_the_lea
          ? pretty(p.what_pressure_plane_did_the_lea.replace(/_Plane$/, ''))
          : 'Unknown zone',
        repair: pretty(p.type_of_repair) || 'Not recorded',
      },
    });
  }
  return { type: 'FeatureCollection', features: out };
}

function dataUrl(name) {
  return new URL(`../data/coryell/${name}`, import.meta.url).href;
}

async function fetchJSON(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
  return r.json();
}

function initMap() {
  if (mapPromise) return mapPromise;
  mapPromise = buildMap();
  return mapPromise;
}

function showMapFallback(message) {
  const el = $('#map-fallback');
  if (!el) return;
  el.hidden = false;
  if (message) {
    const p = el.querySelector('p');
    if (p) p.textContent = message;
  }
}

async function buildMap() {
  if (!window.maplibregl) {
    $('#map-loading')?.classList.add('done');
    showMapFallback('MapLibre could not load. Check the internet connection and reload the page.');
    throw new Error('MapLibre unavailable');
  }

  let leaks = { type: 'FeatureCollection', features: [] };
  let pipes = { type: 'FeatureCollection', features: [] };
  let dataError = null;

  try {
    const [leakRaw, pipeRaw] = await Promise.all([
      fetchJSON(dataUrl('leak_survey.geojson')),
      fetchJSON(dataUrl('waterlines.geojson')),
    ]);
    leaks = prepareLeaks(leakRaw);
    pipes = {
      type: 'FeatureCollection',
      features: (pipeRaw.features || []).map((f) => {
        const p = f.properties || {};
        const dia = Number.isFinite(p.Diameter) ? p.Diameter : parseSize(p.Size) || 1;
        return { ...f, properties: { ...p, dia } };
      }),
    };
  } catch (err) {
    dataError = err;
  }

  const map = new maplibregl.Map({
    container: 'map',
    style: {
      version: 8,
      sources: {
        'base-dark': {
          type: 'raster',
          tiles: ['https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}'],
          tileSize: 256,
          maxzoom: 16,
          attribution: 'Basemap: Esri, HERE, Garmin, © OpenStreetMap contributors',
        },
        'base-img': {
          type: 'raster',
          tiles: ['https://basemap.nationalmap.gov/arcgis/rest/services/USGSImageryOnly/MapServer/tile/{z}/{y}/{x}'],
          tileSize: 256,
          maxzoom: 16,
          attribution: 'Imagery: USGS The National Map (USDA NAIP), public domain',
        },
        pipes: { type: 'geojson', data: pipes },
        leaks: { type: 'geojson', data: leaks },
      },
      layers: [
        { id: 'bg', type: 'background', paint: { 'background-color': '#0a0f15' } },
        {
          id: 'base-dark', type: 'raster', source: 'base-dark',
          paint: { 'raster-fade-duration': 200, 'raster-opacity': .94, 'raster-brightness-max': .82 },
        },
        {
          id: 'base-img', type: 'raster', source: 'base-img', layout: { visibility: 'none' },
          paint: { 'raster-fade-duration': 200, 'raster-opacity': .74, 'raster-saturation': -.3, 'raster-brightness-max': .78 },
        },
        {
          id: 'pipes-casing', type: 'line', source: 'pipes',
          layout: { 'line-cap': 'round', 'line-join': 'round' },
          paint: {
            'line-color': '#04121c', 'line-opacity': .8,
            'line-width': ['interpolate', ['linear'], ['zoom'], 9, 1.3, 15, 5],
          },
        },
        {
          id: 'pipes', type: 'line', source: 'pipes',
          layout: { 'line-cap': 'round', 'line-join': 'round' },
          paint: {
            'line-color': ['interpolate', ['linear'], ['coalesce', ['get', 'dia'], 1],
              1, '#2a8ad8', 4, '#4cc9f0', 8, '#8fe7ff', 12, '#fff3b0'],
            'line-opacity': .75,
            'line-width': ['interpolate', ['linear'], ['zoom'], 9, .5, 15, 2.6],
          },
        },
        {
          id: 'leaks-glow', type: 'circle', source: 'leaks',
          paint: {
            'circle-radius': ['*', ['interpolate', ['linear'], ['coalesce', ['get', 'size'], 1], 1, 4, 4, 6, 10, 9], 2.2],
            'circle-color': '#4cc9f0', 'circle-opacity': .12, 'circle-blur': 1,
          },
        },
        {
          id: 'leaks', type: 'circle', source: 'leaks',
          paint: {
            'circle-radius': ['interpolate', ['linear'], ['coalesce', ['get', 'size'], 1], 1, 3.2, 4, 5.2, 10, 8],
            'circle-color': '#4cc9f0',
            'circle-opacity': .92,
            'circle-stroke-width': .8,
            'circle-stroke-color': 'rgba(5,10,15,.85)',
          },
        },
      ],
    },
    center: [-97.72, 31.5],
    zoom: 8.6,
    minZoom: 7,
    maxZoom: 16,
    dragRotate: false,
    pitchWithRotate: false,
    touchPitch: false,
    attributionControl: false,
  });

  map.touchZoomRotate.disableRotation();
  map.keyboard.disableRotation();
  map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'bottom-right');
  map.addControl(new maplibregl.AttributionControl({ compact: true }), 'bottom-right');

  await new Promise((resolve) => map.on('load', resolve));
  $('#map-loading')?.classList.add('done');

  map.fitBounds(CORYELL_BOUNDS, {
    padding: mapPadding(),
    duration: 1500,
    essential: true,
  });

  const popup = new maplibregl.Popup({
    closeButton: false,
    closeOnClick: false,
    offset: 9,
    maxWidth: '270px',
    className: 'aguard-popup',
  });

  function popupHtml(p) {
    const dt = p.t > 0
      ? new Date(p.t).toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' })
      : 'Date not recorded';
    const size = p.size > 0 ? `${p.size}″ pipe` : 'Pipe size unknown';
    const loss = p.gpm >= 0 ? `${fmt(p.gpm)} gpm` : 'Loss not recorded';
    return `<div class="mono">${esc(dt)}</div><b>${esc(size)}</b>
      <dl>
        <dt>Est. loss</dt><dd>${esc(loss)}</dd>
        <dt>Cause</dt><dd>${esc(p.cause)}</dd>
        <dt>Zone</dt><dd>${esc(p.zone)}</dd>
        <dt>Repair</dt><dd>${esc(p.repair)}</dd>
      </dl>`;
  }

  map.on('mousemove', 'leaks', (e) => {
    const f = e.features?.[0];
    if (!f) return;
    map.getCanvas().style.cursor = 'pointer';
    popup.setLngLat(e.lngLat).setHTML(popupHtml(f.properties)).addTo(map);
  });
  map.on('mouseleave', 'leaks', () => {
    map.getCanvas().style.cursor = '';
    popup.remove();
  });
  map.on('click', 'leaks', (e) => {
    const f = e.features?.[0];
    if (!f) return;
    popup.setLngLat(e.lngLat).setHTML(popupHtml(f.properties)).addTo(map);
  });

  const state = {
    map,
    leaks: leaks.features,
    pipes: pipes.features,
    ready: true,
    color: 'size',
    p: 1,
    playing: false,
    raf: 0,
    last: 0,
    autoStarted: false,
    maybeAutoPlay() {
      if (this.autoStarted || this.playing) return;
      this.autoStarted = true;
      this.p = 0;
      this.applyCursor();
      window.setTimeout(() => {
        if (index === 5 && !mapState.playing) startMapPlay();
      }, 900);
    },
  };
  mapState = state;

  if (dataError) {
    showMapFallback('Could not load the Coryell layers. Build them once, then reload:');
  }

  state.applyCursor = () => {
    const p = state.p;
    const t = TIME_START + (TIME_END - TIME_START) * p;
    const all = p >= .999;
    const filter = ['<=', ['get', 't'], all ? TIME_END + 1 : t];
    try {
      map.setFilter('leaks', filter);
      map.setFilter('leaks-glow', filter);
    } catch { /* map can be mid-render */ }

    const shown = all ? state.leaks : state.leaks.filter((f) => f.properties.t <= t);
    const losses = shown.map((f) => f.properties.gpm).filter((v) => v >= 0).sort((a, b) => a - b);
    const median = losses.length
      ? losses.length % 2
        ? losses[(losses.length - 1) / 2]
        : (losses[losses.length / 2 - 1] + losses[losses.length / 2]) / 2
      : null;
    const big = shown.filter((f) => f.properties.size >= 4).length;

    $('#map-count').textContent = fmt(shown.length);
    $('#map-median').textContent = median == null ? '—' : `${Math.round(median)}`;
    $('#map-big').textContent = fmt(big);
    $('#map-date').textContent = all
      ? 'ALL TIME'
      : new Date(t).toLocaleDateString('en-US', { month: 'short', year: 'numeric' }).toUpperCase();
    $('#map-window').textContent = `${fmt(shown.length)} REPAIRS`;
    const range = $('#map-range');
    if (document.activeElement !== range) range.value = String(Math.round(p * 1000));
  };

  state.applyColor = () => {
    const mode = COLORS[state.color];
    const expr = ['match', ['get', mode.prop]];
    mode.bins.forEach((b) => expr.push(b.v, b.color));
    expr.push('#9aa3ad');
    map.setPaintProperty('leaks', 'circle-color', expr);
    map.setPaintProperty('leaks-glow', 'circle-color', expr);
    const counts = {};
    for (const f of state.leaks) {
      const v = f.properties[mode.prop];
      counts[v] = (counts[v] || 0) + 1;
    }
    $('#map-legend').innerHTML = mode.bins.map((b) =>
      `<span><i style="background:${b.color}"></i>${esc(b.label)}<b>${fmt(counts[b.v] || 0)}</b></span>`).join('');
  };

  $('#map-play').addEventListener('click', () => {
    if (state.playing) stopMapPlay(); else startMapPlay();
  });
  $('#map-all').addEventListener('click', () => {
    stopMapPlay();
    state.p = 1;
    state.applyCursor();
  });
  $('#map-range').addEventListener('input', (e) => {
    stopMapPlay();
    state.p = Number(e.target.value) / 1000;
    state.applyCursor();
  });
  $('#map-color').addEventListener('change', (e) => {
    state.color = e.target.value;
    state.applyColor();
  });
  $('#map-base').addEventListener('change', (e) => {
    const img = e.target.value === 'imagery';
    map.setLayoutProperty('base-dark', 'visibility', img ? 'none' : 'visible');
    map.setLayoutProperty('base-img', 'visibility', img ? 'visible' : 'none');
  });
  window.addEventListener('resize', () => map.resize());

  state.applyColor();
  state.applyCursor();

  // Pause map animation when the slide leaves.
  return state;
}

function mapPadding() {
  const w = window.innerWidth;
  if (w < 760) return 22;
  if (w < 1100) return { top: 34, right: 30, bottom: 34, left: 340 };
  return { top: 46, right: 46, bottom: 46, left: 410 };
}



/* ------------------------------------------------------------------------
   NISAR passes and the before/after viewer
   ------------------------------------------------------------------------ */
const DAY_MS = 86400000;
const NISAR = { promise: null, data: null };
let passesPromise = null;
let viewerPromise = null;
let passesReady = false;
let viewerReady = false;
const PASS_STATE = { window: 6, cause: 'natural', selected: -1, acqs: [], counts: [] };
let blinkTimer = 0;
let blinkOn = false;

function loadNisar() {
  if (NISAR.promise) return NISAR.promise;
  NISAR.promise = (async () => {
    const [leakRaw, acqRaw, chips] = await Promise.all([
      fetchJSON(dataUrl('leak_survey.geojson')),
      fetchJSON(dataUrl('nisar/acquisitions_041D073.json')),
      fetchJSON(dataUrl('nisar/leak_chips.json')),
    ]);
    const data = {
      leaks: prepareLeaks(leakRaw).features,
      acqs: acqRaw.acquisitions || [],
      chips,
    };
    NISAR.data = data;
    return data;
  })();
  return NISAR.promise;
}

function passCount(acq, win, cause) {
  const data = NISAR.data;
  if (!data) return 0;
  const tp = Number.isFinite(acq.t) ? acq.t : Date.parse(acq.start_utc);
  return data.leaks.reduce((n, f) => {
    const p = f.properties;
    if (p.t < 0) return n;
    if (cause === 'natural' && p.cbin !== 0) return n;
    const d = (p.t - tp) / DAY_MS;
    return d >= 0 && d < win + 1 ? n + 1 : n;
  }, 0);
}

function initPasses() {
  if (passesPromise) return passesPromise;
  passesPromise = (async () => {
    try {
      const data = await loadNisar();
      PASS_STATE.acqs = data.acqs;
      passesReady = true;
      wirePassControls();
      renderPasses();
      animatePasses();
    } catch (err) {
      $('#pass-fallback')?.removeAttribute('hidden');
      throw err;
    }
  })();
  return passesPromise;
}

function wirePassControls() {
  $('#pass-window')?.addEventListener('click', (e) => {
    const b = e.target.closest('button[data-window]');
    if (!b) return;
    PASS_STATE.window = Number(b.dataset.window);
    $$('#pass-window button').forEach((x) => x.classList.toggle('on', x === b));
    renderPasses();
    animatePasses();
  });
  $('#pass-cause')?.addEventListener('click', (e) => {
    const b = e.target.closest('button[data-cause]');
    if (!b) return;
    PASS_STATE.cause = b.dataset.cause;
    $$('#pass-cause button').forEach((x) => x.classList.toggle('on', x === b));
    renderPasses();
    animatePasses();
  });
  $('#pass-chart')?.addEventListener('click', (e) => {
    const b = e.target.closest('.pass-bar');
    if (b) setPass(Number(b.dataset.i));
  });
}

function renderPasses() {
  if (!passesReady) return;
  const acqs = PASS_STATE.acqs;
  PASS_STATE.counts = acqs.map((a) => passCount(a, PASS_STATE.window, PASS_STATE.cause));
  const max = Math.max(1, ...PASS_STATE.counts);
  if (PASS_STATE.selected < 0 || PASS_STATE.selected >= acqs.length) {
    let best = 0;
    PASS_STATE.counts.forEach((n, i) => { if (n > PASS_STATE.counts[best]) best = i; });
    PASS_STATE.selected = best;
  }
  const chart = $('#pass-chart');
  chart.innerHTML = acqs.map((a, i) => {
    const n = PASS_STATE.counts[i];
    const h = Math.max(n > 0 ? 4 : 1.5, (n / max) * 100);
    return `<button class="pass-bar${i === PASS_STATE.selected ? ' on' : ''}" type="button" data-i="${i}" style="--v:${h.toFixed(1)}" title="${esc(a.date)} · ${n} repair${n === 1 ? '' : 's'}" aria-label="${esc(a.date)}: ${n} repairs"><span class="pb-cnt">${n || ''}</span><span class="pb-fill"></span></button>`;
  }).join('');

  // Month labels, one per month.
  let lastMonth = '';
  $('#pass-axis').innerHTML = acqs.map((a) => {
    const month = a.date.slice(5, 7);
    const names = { '01': 'JAN', '02': 'FEB', '03': 'MAR', '04': 'APR', '05': 'MAY', '06': 'JUN', '07': 'JUL', '08': 'AUG', '09': 'SEP', '10': 'OCT', '11': 'NOV', '12': 'DEC' };
    const label = month !== lastMonth ? names[month] : '';
    lastMonth = month;
    return `<span>${label}</span>`;
  }).join('');

  // Mark the 2026-07-27 → 08-10 gap after the 2026-07-23 pass.
  const gapIdx = acqs.findIndex((a) => a.date === '2026-07-23');
  const gap = $('#pass-gap-note');
  if (gap && gapIdx >= 0) gap.style.left = `${((gapIdx + 1) / acqs.length) * 100}%`;

  $('#pass-caption').textContent = `${PASS_STATE.cause === 'natural' ? 'Natural leaks' : 'All causes'} · 0–${PASS_STATE.window} days`;
  $('#pass-total').textContent = fmt(PASS_STATE.counts.reduce((a, b) => a + b, 0));
  setPass(PASS_STATE.selected);
}

function setPass(i) {
  const acqs = PASS_STATE.acqs;
  if (!acqs.length) return;
  PASS_STATE.selected = Math.max(0, Math.min(acqs.length - 1, i));
  $$('.pass-bar', $('#pass-chart')).forEach((b) => b.classList.toggle('on', Number(b.dataset.i) === PASS_STATE.selected));
  const n = PASS_STATE.counts[PASS_STATE.selected] || 0;
  const a = acqs[PASS_STATE.selected];
  $('#pass-detail-num').textContent = n;
  $('#pass-detail-date').textContent = a.date;
  $('#pass-detail-text').textContent = `${PASS_STATE.cause === 'natural' ? 'natural ' : ''}repairs logged 0–${PASS_STATE.window} days after the pass`;
  $('#pass-detail-side').textContent = `PASS ${pad2(PASS_STATE.selected + 1)} / ${acqs.length}`;
}

function animatePasses() {
  const chart = $('#pass-chart');
  if (!chart) return;
  chart.classList.remove('animate');
  void chart.offsetWidth;
  requestAnimationFrame(() => chart.classList.add('animate'));
}

function chipUrl(chip) {
  return new URL(`../data/coryell/nisar/chips/${chip}.png`, import.meta.url).href;
}

function signedDb(v, digits = 1) {
  if (v == null || !Number.isFinite(v)) return '—';
  const sign = v > 0 ? '+' : v < 0 ? '−' : '±';
  return `${sign}${Math.abs(v).toFixed(digits)}`;
}

function fmtDays(days) {
  if (days == null || !Number.isFinite(days)) return '—';
  const sign = days > 0 ? '+' : days < 0 ? '−' : '±';
  return `${sign}${Math.abs(days).toFixed(1)} d`;
}

function initViewer() {
  if (viewerPromise) return viewerPromise;
  viewerPromise = (async () => {
    try {
      const data = await loadNisar();
      const leaks = data.chips?.leaks || [];
      let leak = leaks.find((l) => l.id === 1750);
      if (!leak) leak = leaks.find((l) => l.roles?.before && l.roles?.after);
      if (!leak) leak = leaks.find((l) => l.roles?.after);
      if (!leak) throw new Error('No leak chips in the manifest');

      const before = leak.roles.before;
      const after = leak.roles.after;
      if (!before || !after) throw new Error('This leak has no before/after pair');

      const beforeImg = $('#cmp-before-img');
      const afterImg = $('#cmp-after-img');
      beforeImg.src = chipUrl(before.chip);
      afterImg.src = chipUrl(after.chip);

      $('#viewer-kicker').textContent = `NISAR GCOV · P05023 · ${leak.site || 'SITE'}`;
      const size = leak.size ? `${leak.size}″ pipe` : 'pipe size unknown';
      const gpm = leak.gpm != null ? `${fmt(leak.gpm)} gpm` : 'loss unknown';
      $('#viewer-title').textContent = `ObjectId ${leak.id} · ${size} · ${gpm}`;
      $('#viewer-dates').textContent = `before ${before.date} (${fmtDays(before.days)}) → after ${after.date} (${fmtDays(after.days)})`;

      const ch = leak.change?.after_minus_before || {};
      const stats = [
        [signedDb(ch.hh_in), 'HH inside 30 m (dB)'],
        [signedDb(ch.hv_in), 'HV inside 30 m (dB)'],
        [signedDb(ch.hh_contrast), 'HH contrast (dB)'],
        [signedDb(ch.hv_contrast), 'HV contrast (dB)'],
      ];
      $('#viewer-stats').innerHTML = stats.map(([v, k]) => `<div><b>${v}</b><span>${k}</span></div>`).join('');

      const roles = [
        ['baseline', 'Baseline'],
        ['before', 'Before'],
        ['after', 'After'],
      ].filter(([k]) => leak.roles[k]);
      $('#viewer-strip').innerHTML = roles.map(([key, label]) => {
        const r = leak.roles[key];
        return `<div class="viewer-thumb"><img src="${chipUrl(r.chip)}" alt="" loading="lazy"><span class="mono">${label}</span><b>${r.date}</b><em>${fmtDays(r.days)}</em></div>`;
      }).join('');

      wireViewer();
      setCompare(50);
      $('#viewer-fallback')?.setAttribute('hidden', '');
      viewerReady = true;
    } catch (err) {
      $('#viewer-fallback')?.removeAttribute('hidden');
      throw err;
    }
  })();
  return viewerPromise;
}

function setCompare(pos) {
  const p = Math.max(0, Math.min(100, pos));
  const cmp = $('#compare');
  if (cmp) cmp.style.setProperty('--pos', `${p}%`);
  const range = $('#cmp-range');
  if (range && document.activeElement !== range) range.value = String(Math.round(p));
  const readout = $('#cmp-readout');
  if (readout) readout.textContent = `${Math.round(p)}%`;
}

function wireViewer() {
  const range = $('#cmp-range');
  const blink = $('#cmp-blink');
  if (!range || !blink || range.dataset.wired) return;
  range.dataset.wired = '1';
  range.addEventListener('input', (e) => {
    stopBlink();
    setCompare(Number(e.target.value));
  });
  blink.addEventListener('click', () => {
    if (blinkOn) { stopBlink(); return; }
    blinkOn = true;
    blink.classList.add('on');
    blink.textContent = 'Stop';
    let left = true;
    setCompare(100);
    blinkTimer = window.setInterval(() => {
      left = !left;
      setCompare(left ? 100 : 0);
    }, 950);
  });
}

function stopBlink() {
  if (!blinkOn) return;
  blinkOn = false;
  clearInterval(blinkTimer);
  const blink = $('#cmp-blink');
  if (blink) {
    blink.classList.remove('on');
    blink.textContent = 'Blink';
  }
}

/* ------------------------------------------------------------------ boot -- */
// Keep the old hash but do not create a new history entry on the first paint.
const start = readHash();
go(start, { fromHistory: true, force: true });
history.replaceState({ slide: start }, '', `#/${start}`);

// A small, one-time hint that the deck is interactive.
window.setTimeout(() => {
  if (index === 0) toast('← → or scroll to move · F fullscreen · N speaker notes');
}, 900);
