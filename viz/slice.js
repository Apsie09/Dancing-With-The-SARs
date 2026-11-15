// NISAR pass ("slice") mode and the before/after radar chip viewer.
//
// Slice mode steps through the passes of stack 041_D_073 and shows the leaks
// repaired in a window of days after the current pass (and optionally those
// repaired just before it). The viewer shows the baseline / before / after
// chips of a selected leak (made by scripts/make_leak_chips.py) and can put
// one of them on the map at its true location.
import { DAY, CAUSES, sizeLabel, fmtDateCT, fmtGpm } from './leaks.js';

const NISAR_DIR = '../data/coryell/nisar/';
const ACQ_URL = NISAR_DIR + 'acquisitions_041D073.json';
const CHIPS_URL = NISAR_DIR + 'leak_chips.json';

// Display stretch in dB: identical to scripts/render_gcov_png.py and the map's NISAR layers.
export const RANGES = { hh: [-22, -3], hv: [-28, -11], ratio: [3, 12] };
const MAGMA = ['#000004', '#1c1044', '#4f127b', '#812581', '#b5367a', '#e55064', '#fb8761', '#fec287', '#fcfdbf'];
const VIRIDIS = ['#440154', '#472d7b', '#3b528b', '#2c728e', '#21918c', '#28ae80', '#5ec962', '#addc30', '#fde725'];
const ROLES = [['baseline', 'Baseline'], ['before', 'Before'], ['after', 'After']];
const CAUSE_COLORS = ['#4cc9f0', '#ff4f9a', '#d9d9d9'];

const $ = (sel, root = document) => root.querySelector(sel);
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const fmtCTshort = new Intl.DateTimeFormat('en-US', { timeZone: 'America/Chicago', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' });
const fmtPassLocal = new Intl.DateTimeFormat('en-US', { timeZone: 'America/Chicago', weekday: 'short', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit', timeZoneName: 'short' });
const fmtStripDay = (t) => new Date(t).toISOString().slice(5, 10); // MM-DD (UTC date of the pass)
// Elapsed time: hours under a day, else days with one decimal.
const span = (days) => { const a = Math.abs(days); return a < 1 ? `${Math.round(a * 24)} h` : `${a.toFixed(1)} d`; };
const signed = (v, d = 1) => (v == null ? '–' : `${v > 0 ? '+' : v < 0 ? '−' : '±'}${Math.abs(v).toFixed(d)}`);

function lut(anchors) {
  const cols = anchors.map((h) => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16)));
  const out = new Uint8ClampedArray(256 * 3);
  for (let k = 0; k < 256; k++) {
    const x = (k / 255) * (cols.length - 1), i = Math.min(Math.floor(x), cols.length - 2), f = x - i;
    for (let c = 0; c < 3; c++) out[k * 3 + c] = cols[i][c] + (cols[i + 1][c] - cols[i][c]) * f;
  }
  return out;
}
const LUT = { hh: lut(MAGMA), hv: lut(VIRIDIS) };
export const LEGENDS = {
  rgb: { label: 'False colour', html: '<span class="vw-sw" style="background:#ff3b3b"></span>R = HH −22…−3 dB <span class="vw-sw" style="background:#3bff6a"></span>G = HV −28…−11 dB <span class="vw-sw" style="background:#3b8bff"></span>B = HH/HV 3…12 dB' },
  hh: { label: 'HH', html: `<div class="vw-ramp" style="background:linear-gradient(90deg,${MAGMA.join(',')})"></div><div class="vw-ramp-l"><span>−22 dB</span><span>HH (co-pol, soil moisture / roughness)</span><span>−3 dB</span></div>` },
  hv: { label: 'HV', html: `<div class="vw-ramp" style="background:linear-gradient(90deg,${VIRIDIS.join(',')})"></div><div class="vw-ramp-l"><span>−28 dB</span><span>HV (cross-pol, vegetation)</span><span>−11 dB</span></div>` },
};

export function initSlice(ctx) {
  const { map, state } = ctx;
  const S = state.slice = {
    on: false, ready: false, acqs: [], i: -1, lo: 0, hi: 6, beforeOn: true, beforeN: 3,
    natural: true, big: false, district: true, sel: null, manifest: null, leakChips: new Map(),
    mode: 'rgb', overlayRole: 'off', blink: null, opacity: 0.9, rings: true,
  };
  const chipCache = new Map(); // file -> Promise<ImageData (encoded)>

  // ------------------------------------------------------------ data ------
  const ready = (async () => {
    try {
      const [a, m] = await Promise.all([
        fetch(ACQ_URL).then((r) => (r.ok ? r.json() : null)).catch(() => null),
        fetch(CHIPS_URL).then((r) => (r.ok ? r.json() : null)).catch(() => null),
      ]);
      const acqs = a?.acquisitions || m?.acquisitions || [];
      S.acqs = acqs.map((x) => ({ ...x, t: x.t ?? Date.parse(x.start_utc) }));
      S.manifest = m;
      if (m) for (const l of m.leaks) S.leakChips.set(l.id, l);
      S.ready = S.acqs.length > 0;
    } catch (err) {
      console.warn('NISAR pass data failed to load', err);
    }
    buildPanel();
    return S.ready;
  })();

  // ---------------------------------------------------------- filtering ---
  const passT = (i) => S.acqs[i].t;
  const attrOK = (p) => (!S.natural || p.cbin === 0) && (!S.big || (p.size != null && p.size >= 4));
  function classify(i) {
    const tp = passT(i);
    const win = [], before = [];
    for (const f of state.leaks) {
      const p = f.properties;
      if (p.t < 0 || !attrOK(p)) continue;
      const d = (p.t - tp) / DAY;
      if (d >= S.lo && d < S.hi + 1) win.push([f, d]);
      else if (S.beforeOn && d < 0 && d >= -S.beforeN) before.push([f, d]);
    }
    win.sort((a, b) => a[1] - b[1]);
    before.sort((a, b) => b[1] - a[1]);
    return { win, before };
  }

  function defaultPass() {
    for (let i = S.acqs.length - 1; i >= 0; i--) {
      const tp = passT(i);
      if (state.leaks.some((f) => f.properties.cbin === 0 && (f.properties.t - tp) / DAY >= S.lo && (f.properties.t - tp) / DAY < S.hi + 1)) return i;
    }
    return S.acqs.length - 1;
  }

  function apply() {
    if (!S.on || !S.ready) return;
    const { win, before } = classify(S.i);
    const inSet = new Set([...win, ...before].map(([f]) => f.id));
    const fc = (features) => ({ type: 'FeatureCollection', features });
    const shown = win.map(([f]) => f);
    state.shown = shown;
    map.getSource('leaks').setData(fc(shown));
    map.getSource('leaks-cl').setData(fc(shown));
    map.getSource('slice-before').setData(fc(before.map(([f]) => f)));
    map.getSource('leaks-out').setData(fc(state.leaks.filter((f) => !inSet.has(f.id))));
    ctx.renderStats(shown);
    $('#count-of').textContent = `leaks ${S.lo}–${S.hi} d after this pass`;
    ctx.renderLegend();
    renderHeader();
    ctx.onPass?.(S.acqs[S.i]?.date);
    renderStrip();
    renderList(win, before);
    updateDistrict();
  }

  // -------------------------------------------------------------- panel ---
  function buildPanel() {
    const sec = $('#sec-slice');
    if (!S.ready) {
      $('#sl-body').innerHTML = '<p class="note">The pass list (data/coryell/nisar/acquisitions_041D073.json) could not be loaded.</p>';
      return;
    }
    $('#sl-prev').addEventListener('click', () => step(-1));
    $('#sl-next').addEventListener('click', () => step(1));
    // Days-after-pass dual slider
    const a = $('#sl-lo'), b = $('#sl-hi');
    a.value = S.lo; b.value = S.hi;
    const onSlide = (e) => {
      let lo = +a.value, hi = +b.value;
      if (lo > hi) { if (e.target === a) hi = lo; else lo = hi; a.value = lo; b.value = hi; }
      S.lo = lo; S.hi = hi;
      updateWinLabel();
      apply();
    };
    a.addEventListener('input', onSlide);
    b.addEventListener('input', onSlide);
    $('#sl-ticks').innerHTML = Array.from({ length: 13 }, (_, k) => `<span style="left:${(k / 12) * 100}%">${k}</span>`).join('');
    updateWinLabel();
    const bind = (id, fn) => $(id).addEventListener('change', (e) => { fn(e.target); apply(); });
    bind('#sl-before-on', (t) => { S.beforeOn = t.checked; });
    bind('#sl-before-n', (t) => { S.beforeN = Math.max(1, Math.min(12, Math.round(+t.value || 3))); t.value = S.beforeN; });
    bind('#sl-natural', (t) => { S.natural = t.checked; });
    bind('#sl-big', (t) => { S.big = t.checked; });
    bind('#sl-district', (t) => { S.district = t.checked; });
    $('#sl-zoom').addEventListener('click', () => {
      const { win, before } = classify(S.i);
      const pts = [...win, ...before].map(([f]) => f.geometry.coordinates);
      if (!pts.length) return;
      const lons = pts.map((p) => p[0]), lats = pts.map((p) => p[1]);
      map.fitBounds([[Math.min(...lons), Math.min(...lats)], [Math.max(...lons), Math.max(...lats)]], { padding: 80, maxZoom: 15 });
    });
    sec.classList.add('ready');
  }

  function updateWinLabel() {
    $('#sl-win').textContent = S.lo === S.hi ? `day ${S.lo}` : `days ${S.lo}–${S.hi}`;
    const lo = (S.lo / 12) * 100, hi = (S.hi / 12) * 100;
    $('#sl-fill').style.left = `${lo}%`;
    $('#sl-fill').style.width = `${Math.max(hi - lo, 0)}%`;
  }

  function renderHeader() {
    const a = S.acqs[S.i];
    $('#sl-date').textContent = a.date;
    $('#sl-sub').textContent = `acquired ${fmtPassLocal.format(new Date(a.t))} (${a.start_utc.slice(11, 16)} UTC) · ${a.crid || 'P05023'}`;
    $('#sl-prev').disabled = S.i <= 0;
    $('#sl-next').disabled = S.i >= S.acqs.length - 1;
    $('#sl-pos').textContent = `${S.i + 1} / ${S.acqs.length}`;
  }

  function renderStrip() {
    const box = $('#sl-strip');
    let html = '';
    S.acqs.forEach((a, i) => {
      const n = classify(i).win.length;
      const gap = i > 0 && a.t - S.acqs[i - 1].t > 13 * DAY;
      html += `<button type="button" class="sl-d${i === S.i ? ' on' : ''}${n ? '' : ' empty'}${gap ? ' gap' : ''}" data-i="${i}" title="${a.date}: ${n} leak${n === 1 ? '' : 's'} in the window${gap ? ' (after the 2026-07-27…08-10 data gap)' : ''}">` +
        `<span class="sl-d-date">${fmtStripDay(a.t)}</span><span class="sl-d-n">${n || '·'}</span></button>`;
    });
    box.innerHTML = html;
    box.querySelectorAll('.sl-d').forEach((b) => b.addEventListener('click', () => go(+b.dataset.i)));
  }

  function leakRow(f, d, before) {
    const p = f.properties;
    const has = S.leakChips.get(p.id)?.roles;
    const nChips = has ? ROLES.filter(([r]) => has[r]?.chip).length : 0;
    const gpm = fmtGpm(p.gpm);
    return `<button type="button" class="sl-item${before ? ' before' : ''}${S.sel === p.id ? ' on' : ''}" data-id="${p.id}">
      <span class="sl-dot${before ? ' hollow' : ''}" style="--c:${CAUSE_COLORS[p.cbin] || '#ccc'}"></span>
      <span class="sl-days">${d >= 0 ? '+' : '−'}${span(d)}</span>
      <span class="sl-when">${esc(fmtCTshort.format(new Date(p.t)))}</span>
      <span class="sl-size">${p.size != null ? esc(sizeLabel(p.size)) : '?'}</span>
      <span class="sl-gpm">${gpm ? esc(gpm) : '–'}</span>
      <span class="sl-chips" title="${nChips} of 3 radar chips">${'■'.repeat(nChips)}${'□'.repeat(3 - nChips)}</span>
    </button>`;
  }

  function renderList(win, before) {
    const box = $('#sl-list');
    const cause = S.natural ? 'natural ' : '';
    let html = `<div class="sl-list-h"><span>${win.length} ${cause}leak${win.length === 1 ? '' : 's'} repaired ${S.lo}–${S.hi} d after the pass</span></div>`;
    html += win.length ? win.map(([f, d]) => leakRow(f, d, false)).join('') : '<div class="sl-empty">None in this window. Widen the window or step to another pass.</div>';
    if (S.beforeOn) {
      html += `<div class="sl-list-h before"><span>${before.length} repaired up to ${S.beforeN} d <b>before</b> the pass (hollow dots)</span></div>`;
      html += before.map(([f, d]) => leakRow(f, d, true)).join('');
    }
    box.innerHTML = html;
    box.querySelectorAll('.sl-item').forEach((b) => b.addEventListener('click', () => select(+b.dataset.id, { fly: true })));
  }

  function updateDistrict() {
    const date = S.acqs[S.i]?.date;
    const po = ctx.passOverlays || {};
    const avail = Object.keys(po).sort();
    const id = po[date];
    const st = $('#sl-district-st');
    st.textContent = id ? 'shown for this pass' : `none for this pass (only ${avail.map((d) => d.slice(5)).join(', ') || '–'})`;
    st.classList.toggle('ok', !!id);
    if (!S.on) return;
    for (const [d, oid] of Object.entries(po)) ctx.setOverlayVisibleById(oid, S.district && d === date);
  }

  // ------------------------------------------------------- navigation -----
  function go(i) {
    if (!S.ready) return;
    S.i = Math.max(0, Math.min(S.acqs.length - 1, i));
    apply();
  }
  function step(k) { go(S.i + k); }

  async function enter() {
    await ready;
    S.on = true;
    if (!S.ready) return;
    if (S.i < 0) S.i = defaultPass();
    apply();
  }
  function exit() {
    S.on = false;
    map.getSource('slice-before')?.setData({ type: 'FeatureCollection', features: [] });
  }

  // ---------------------------------------------------------- selection ---
  function select(id, { fly = false } = {}) {
    S.sel = id;
    const f = state.byId.get(id);
    if (!f) return;
    map.getSource('leak-sel').setData({ type: 'FeatureCollection', features: [f] });
    document.querySelectorAll('.sl-item').forEach((b) => b.classList.toggle('on', +b.dataset.id === id));
    openViewer(id);
    if (fly) {
      // Keep the leak clear of the viewer (top-left) on wide screens.
      const wide = window.innerWidth > 820 && !vw.classList.contains('min');
      const ox = wide ? Math.min(vw.offsetWidth / 2 + 20, map.getCanvas().clientWidth / 4) : 0;
      const oy = window.innerWidth <= 820 ? -map.getCanvas().clientHeight / 5 : 0;
      map.flyTo({ center: f.geometry.coordinates, zoom: Math.max(map.getZoom(), 14.5), speed: 1.6, offset: [ox, oy] });
    }
  }

  // ------------------------------------------------------------- chips ----
  function loadChip(file) {
    if (!chipCache.has(file)) {
      chipCache.set(file, new Promise((resolve, reject) => {
        const im = new Image();
        im.onload = () => {
          const c = document.createElement('canvas');
          c.width = im.width; c.height = im.height;
          const g = c.getContext('2d', { willReadFrequently: true });
          g.drawImage(im, 0, 0);
          resolve(g.getImageData(0, 0, c.width, c.height));
        };
        im.onerror = () => reject(new Error(`chip ${file} failed to load`));
        im.src = NISAR_DIR + file;
      }));
    }
    return chipCache.get(file);
  }

  /** Encoded chip (R = HH dB, G = HV dB, B = valid) -> displayable RGBA canvas. */
  function colorize(enc, mode) {
    const enc8 = S.manifest.encoding;
    const [hl, hh_] = enc8.r.range, [vl, vh] = enc8.g.range;
    const out = new ImageData(enc.width, enc.height);
    const s = enc.data, o = out.data;
    const st = (v, [lo, hi]) => Math.max(0, Math.min(1, (v - lo) / (hi - lo)));
    for (let k = 0; k < s.length; k += 4) {
      if (s[k + 2] < 128) { o[k + 3] = 0; continue; }
      const hhdb = hl + (s[k] / 255) * (hh_ - hl), hvdb = vl + (s[k + 1] / 255) * (vh - vl);
      if (mode === 'rgb') {
        o[k] = 255 * st(hhdb, RANGES.hh); o[k + 1] = 255 * st(hvdb, RANGES.hv); o[k + 2] = 255 * st(hhdb - hvdb, RANGES.ratio);
      } else {
        const t = Math.round(255 * st(mode === 'hh' ? hhdb : hvdb, RANGES[mode])), L = LUT[mode];
        o[k] = L[t * 3]; o[k + 1] = L[t * 3 + 1]; o[k + 2] = L[t * 3 + 2];
      }
      o[k + 3] = 255;
    }
    const c = document.createElement('canvas');
    c.width = enc.width; c.height = enc.height;
    c.getContext('2d').putImageData(out, 0, 0);
    return c;
  }

  // ------------------------------------------------------------ viewer ----
  const vw = document.createElement('div');
  vw.id = 'viewer';
  vw.className = 'viewer hidden';
  vw.setAttribute('role', 'dialog');
  vw.setAttribute('aria-label', 'Radar chips before and after the repair');
  $('#map-wrap').appendChild(vw);

  function chipMeta(role) {
    const l = S.leakChips.get(S.sel);
    const r = l?.roles?.[role];
    if (!r || !r.chip) return null;
    return { ...r, ...S.manifest.chips[r.chip] };
  }

  function dayText(days) {
    if (days == null) return '';
    return days <= 0 ? `pass ${span(days)} before repair` : `pass ${span(days)} after repair`;
  }

  function openViewer(id) {
    S.sel = id;
    const f = state.byId.get(id);
    const p = f.properties;
    const l = S.leakChips.get(id);
    const gpm = fmtGpm(p.gpm);
    const head = `<div class="vw-head">
        <div class="vw-title"><span class="lg-dot" style="background:${CAUSE_COLORS[p.cbin] || '#ccc'}"></span>
          <b>Leak ${p.id}</b><span class="vw-meta">${esc(CAUSES[p.cbin]?.label || 'Other')} · ${p.size != null ? esc(sizeLabel(p.size)) : 'size ?'} · ${gpm ? `≈ ${esc(gpm)}` : 'loss unknown'}${p.zone ? ` · ${esc(p.zone)}` : ''}</span></div>
        <div class="vw-time">Repaired ${esc(fmtDateCT(p.t))}</div>
        <button type="button" class="vw-min" aria-label="Minimise viewer" title="Minimise / expand">–</button>
        <button type="button" class="vw-close" aria-label="Close viewer" title="Close (Esc)">×</button>
      </div>`;
    if (!S.manifest || !l) {
      vw.innerHTML = head + `<p class="note vw-none">${S.manifest ? 'No radar chips for this leak: it is outside the NISAR window (repaired before 2025-10-17).' : 'Chip manifest (data/coryell/nisar/leak_chips.json) not available. Run scripts/make_leak_chips.py.'}</p>`;
      vw.classList.remove('hidden');
      $('.vw-close', vw).addEventListener('click', closeViewer);
      return;
    }
    vw.innerHTML = head + `
      <div class="vw-bar">
        <div class="seg vw-mode" role="group" aria-label="Display">
          ${Object.entries(LEGENDS).map(([k, v]) => `<button type="button" data-m="${k}" class="${S.mode === k ? 'on' : ''}">${v.label}</button>`).join('')}
        </div>
        <label class="check vw-rings"><input type="checkbox" ${S.rings ? 'checked' : ''}> rings</label>
      </div>
      <div class="vw-chips">${ROLES.map(([r, label]) => `
        <figure class="vw-fig" data-role="${r}">
          <div class="vw-canvas-wrap"><canvas width="240" height="240"></canvas><div class="vw-missing hidden"></div></div>
          <figcaption><b>${label}</b> <span class="vw-date"></span><br><span class="vw-days"></span></figcaption>
        </figure>`).join('')}
      </div>
      <div class="vw-legend"></div>
      <div class="vw-map">
        <span class="vw-map-l">On map</span>
        <div class="seg vw-ov" role="group" aria-label="Chip on map">
          ${[['off', 'Off'], ...ROLES].map(([k, v]) => `<button type="button" data-r="${k}" class="${S.overlayRole === k ? 'on' : ''}">${v}</button>`).join('')}
        </div>
        <button type="button" class="pill vw-blink${S.blink ? ' on' : ''}" title="Alternate before and after on the map">Blink</button>
        <input type="range" class="vw-op" min="20" max="100" value="${Math.round(S.opacity * 100)}" aria-label="Chip opacity" title="Chip opacity">
      </div>
      <details class="vw-stats" open><summary>Stats <span class="pp-sub">exploratory</span></summary><div class="vw-stats-body"></div></details>
      <div class="vw-foot">Track 41 descending, frame 73 (041_D_073), NISAR L2 GCOV P05023, 10 m, 1.2 km chips, 3×3 boxcar. Rings: 30 m (stats disc), 100 and 300 m (background annulus). Data: NASA/JPL-Caltech, ISRO (ASF DAAC).</div>`;
    vw.classList.remove('hidden');
    $('.vw-close', vw).addEventListener('click', closeViewer);
    $('.vw-min', vw).addEventListener('click', () => vw.classList.toggle('min'));
    vw.querySelectorAll('.vw-mode button').forEach((b) => b.addEventListener('click', () => {
      S.mode = b.dataset.m;
      vw.querySelectorAll('.vw-mode button').forEach((x) => x.classList.toggle('on', x === b));
      drawChips(); updateOverlay();
    }));
    $('.vw-rings input', vw).addEventListener('change', (e) => { S.rings = e.target.checked; drawChips(); });
    vw.querySelectorAll('.vw-ov button').forEach((b) => b.addEventListener('click', () => { stopBlink(); setOverlayRole(b.dataset.r); }));
    $('.vw-blink', vw).addEventListener('click', () => (S.blink ? stopBlink() : startBlink()));
    $('.vw-op', vw).addEventListener('input', (e) => {
      S.opacity = e.target.value / 100;
      if (map.getLayer('chip-overlay')) map.setPaintProperty('chip-overlay', 'raster-opacity', S.opacity);
    });
    renderStats();
    drawChips();
    showFootprint();
    if (S.overlayRole !== 'off') updateOverlay();
  }

  function closeViewer() {
    vw.classList.add('hidden');
    stopBlink();
    setOverlayRole('off');
    S.sel = null;
    map.getSource('leak-sel')?.setData({ type: 'FeatureCollection', features: [] });
    map.getSource('chip-foot')?.setData({ type: 'FeatureCollection', features: [] });
    document.querySelectorAll('.sl-item.on').forEach((b) => b.classList.remove('on'));
  }

  async function drawChips() {
    const sel = S.sel;
    $('.vw-legend', vw).innerHTML = LEGENDS[S.mode].html;
    for (const [role] of ROLES) {
      const fig = $(`.vw-fig[data-role="${role}"]`, vw);
      if (!fig) continue;
      const l = S.leakChips.get(sel);
      const r = l.roles[role];
      const m = chipMeta(role);
      const cv = $('canvas', fig), g = cv.getContext('2d');
      const miss = $('.vw-missing', fig);
      $('.vw-date', fig).textContent = r ? r.date : '';
      $('.vw-days', fig).textContent = r ? dayText(r.days) : '';
      g.clearRect(0, 0, cv.width, cv.height);
      if (!m) {
        miss.classList.remove('hidden');
        miss.textContent = !r ? (role === 'after' ? 'No pass after this repair in the P05023 run (ends 2026-10-15).' : 'No earlier pass in the P05023 run (starts 2025-12-31).') : 'Chip not made.';
        continue;
      }
      miss.classList.add('hidden');
      try {
        const enc = await loadChip(m.file);
        if (S.sel !== sel) return;
        const c = colorize(enc, S.mode);
        g.imageSmoothingEnabled = false;
        g.drawImage(c, 0, 0, cv.width, cv.height);
        const k = cv.width / enc.width; // canvas px per chip px (10 m)
        const [cx, cy] = [m.px[0] * k, m.px[1] * k];
        if (S.rings) {
          g.save();
          g.setLineDash([4, 4]);
          g.strokeStyle = 'rgba(255,255,255,.55)'; g.lineWidth = 1;
          for (const rm of [100, 300]) { g.beginPath(); g.arc(cx, cy, (rm / 10) * k, 0, 2 * Math.PI); g.stroke(); }
          g.restore();
        }
        g.lineWidth = 3; g.strokeStyle = 'rgba(0,0,0,.8)';
        g.beginPath(); g.arc(cx, cy, 3 * k, 0, 2 * Math.PI); g.stroke();
        g.lineWidth = 1.6; g.strokeStyle = '#fff';
        g.beginPath(); g.arc(cx, cy, 3 * k, 0, 2 * Math.PI); g.stroke();
        // ticks
        g.beginPath();
        for (const [dx, dy] of [[1, 0], [-1, 0], [0, 1], [0, -1]]) { g.moveTo(cx + dx * 4.5 * k, cy + dy * 4.5 * k); g.lineTo(cx + dx * 8 * k, cy + dy * 8 * k); }
        g.stroke();
        cv.title = `${role} ${m.date}: chip ${m.file}`;
      } catch (err) {
        miss.classList.remove('hidden');
        miss.textContent = err.message;
      }
    }
  }

  function renderStats() {
    const l = S.leakChips.get(S.sel);
    const R = l.roles;
    const v = (role, key) => R[role]?.stats?.[key];
    const cell = (x, d = 1) => (x == null ? '–' : x.toFixed(d));
    const rows = [
      ['HH ≤ 30 m', 'hh_in'], ['HH 100–300 m', 'hh_out'], ['HH contrast', 'hh_contrast'],
      ['HV ≤ 30 m', 'hv_in'], ['HV 100–300 m', 'hv_out'], ['HV contrast', 'hv_contrast'],
    ];
    const ch = l.change || {};
    const chRow = (key, label) => {
      const c = ch[key];
      if (!c) return `<tr><th>${label}</th><td colspan="4">–</td></tr>`;
      const cls = (x) => (x == null ? '' : x >= 1 ? ' class="up"' : x <= -1 ? ' class="down"' : '');
      return `<tr><th>${label}</th><td${cls(c.hh_in)}>${signed(c.hh_in)}</td><td${cls(c.hh_contrast)}>${signed(c.hh_contrast)}</td><td${cls(c.hv_in)}>${signed(c.hv_in)}</td><td${cls(c.hv_contrast)}>${signed(c.hv_contrast)}</td></tr>`;
    };
    $('.vw-stats-body', vw).innerHTML = `
      <table class="vw-t"><thead><tr><th>dB</th>${ROLES.map(([r, lab]) => `<th>${lab}<br><span class="pp-sub">${R[r]?.date?.slice(5) ?? '–'}</span></th>`).join('')}</tr></thead>
      <tbody>${rows.map(([lab, key]) => `<tr${key.endsWith('contrast') ? ' class="ct"' : ''}><th>${lab}</th>${ROLES.map(([r]) => `<td>${cell(v(r, key))}</td>`).join('')}</tr>`).join('')}</tbody></table>
      <table class="vw-t vw-ch"><thead><tr><th>Change (dB)</th><th>HH disc</th><th>HH contr.</th><th>HV disc</th><th>HV contr.</th></tr></thead>
      <tbody>${chRow('before_minus_baseline', 'Before − baseline')}${chRow('after_minus_before', 'After − before')}</tbody></table>
      <p class="note">Exploratory: mean γ⁰ (linear, unfiltered) within 30 m of the leak point vs a 100–300 m annulus, in dB; contrast = disc − annulus. Single-pass speckle is about ±1 dB on a 30 m disc, so treat changes under ~1.5 dB as noise. A wet patch should raise HH (and the contrast) on the before pass and drop after the repair. Regional wetting moves the disc and the annulus together (e.g. 09-21 → 10-03: background HH +2.5 dB median), so prefer the contrast change.</p>`;
  }

  function showFootprint() {
    const m = chipMeta('before') || chipMeta('after') || chipMeta('baseline');
    const src = map.getSource('chip-foot');
    if (!src) return;
    if (!m) { src.setData({ type: 'FeatureCollection', features: [] }); return; }
    src.setData({ type: 'Feature', properties: {}, geometry: { type: 'Polygon', coordinates: [[...m.corners, m.corners[0]]] } });
  }

  // ------------------------------------------------------ map overlay -----
  function setOverlayRole(role) {
    S.overlayRole = role;
    vw.querySelectorAll('.vw-ov button').forEach((x) => x.classList.toggle('on', x.dataset.r === role));
    updateOverlay();
  }

  async function updateOverlay() {
    const role = S.overlayRole;
    const m = role !== 'off' && S.sel != null ? chipMeta(role) : null;
    if (!m) {
      if (map.getLayer('chip-overlay')) map.setLayoutProperty('chip-overlay', 'visibility', 'none');
      return;
    }
    const enc = await loadChip(m.file);
    const url = colorize(enc, S.mode).toDataURL('image/png');
    const src = map.getSource('chip-overlay');
    if (src) src.updateImage({ url, coordinates: m.corners });
    else {
      map.addSource('chip-overlay', { type: 'image', url, coordinates: m.corners });
      map.addLayer({ id: 'chip-overlay', type: 'raster', source: 'chip-overlay',
        paint: { 'raster-opacity': S.opacity, 'raster-fade-duration': 0, 'raster-resampling': 'nearest' } }, 'z-raster-top');
    }
    map.setLayoutProperty('chip-overlay', 'visibility', 'visible');
  }

  function startBlink() {
    stopBlink();
    let k = 0;
    const roles = ['before', 'after'].filter((r) => chipMeta(r));
    if (roles.length < 2) return;
    S.blink = setInterval(() => { setOverlayRole(roles[k++ % 2]); }, 900);
    setOverlayRole(roles[k++ % 2]);
    $('.vw-blink', vw)?.classList.add('on');
  }
  function stopBlink() {
    if (S.blink) clearInterval(S.blink);
    S.blink = null;
    $('.vw-blink', vw)?.classList.remove('on');
  }

  return { ready, apply, enter, exit, step, go, select, openViewer, closeViewer, hasChips: (id) => S.leakChips.has(id) };
}
