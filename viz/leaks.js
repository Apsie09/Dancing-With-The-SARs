// Leak records: parsing, privacy rules, filtering and styling.

export const LEAKS_URL = '../data/coryell/leak_survey.geojson';
export const NISAR_START = Date.UTC(2025, 9, 17); // 2025-10-17, first NISAR science data
const DROP_IDS = new Set([1611]); // test entry near Galveston, all attributes blank
// Notes of these records name people: never shown (the data file is not modified).
const HIDE_NOTES_IDS = new Set([469, 512, 535, 577, 768, 792, 1473]);

// Time axis of the slider/histogram: whole months.
export const T0 = Date.UTC(2019, 8, 1);   // 2019-09-01
export const T1 = Date.UTC(2026, 11, 1);  // 2026-12-01 (end of Nov 2026, exclusive)
export const DAY = 86400000;

export const SIZES = [0.75, 1, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10];
export const sizeLabel = (s) => (s == null ? '?' : ({ 0.75: '¾', 1.5: '1½', 2.5: '2½' }[s] ?? String(s)) + '″');

export const CAUSES = [
  { key: 'natural', label: 'Natural', raw: 'Naturally_Occurred' },
  { key: 'construction', label: 'Construction / maintenance', raw: 'Construction_Maintenance_Induce' },
  { key: 'other', label: 'Other', raw: 'Other' },
];

// Colour modes. `bins` drive both the map style and the legend (with counts).
export const COLOR_MODES = {
  size: {
    label: 'Pipe size',
    prop: 'sbin',
    bins: [
      { v: 0, label: '≤ 1″ (service)', color: '#fff3b0' },
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
      { v: 1, label: '10–24 gpm', color: '#8fdcbc' },
      { v: 2, label: '25–49 gpm', color: '#3fbfcf' },
      { v: 3, label: '50–99 gpm', color: '#2a8ad8' },
      { v: 4, label: '≥ 100 gpm', color: '#6a4cff' },
      { v: -1, label: 'Unknown', color: '#9aa3ad' },
    ],
  },
  cause: {
    label: 'Cause',
    prop: 'cbin',
    bins: [
      { v: 0, label: 'Natural', color: '#4cc9f0' },
      { v: 1, label: 'Construction / maint.', color: '#ff4f9a' },
      { v: 2, label: 'Other', color: '#d9d9d9' },
    ],
  },
  year: {
    label: 'Year',
    prop: 'ybin',
    bins: [2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026].map((y, i, a) => ({
      v: y, label: String(y), color: yearColor(i / (a.length - 1)),
    })),
  },
};

function yearColor(t) {
  // Perceptual ramp from deep blue to bright yellow (readable on dark imagery).
  const stops = [[63, 81, 181], [33, 145, 140], [94, 201, 98], [253, 231, 37]];
  const x = t * (stops.length - 1), i = Math.min(Math.floor(x), stops.length - 2), f = x - i;
  const c = stops[i].map((v, k) => Math.round(v + (stops[i + 1][k] - v) * f));
  return `rgb(${c.join(',')})`;
}

// ------------------------------------------------------------- parsing ------

/** Pipe size text ('1.5"', '.75"', '2",1.5"') -> largest diameter in inches. */
function parseSize(txt) {
  if (!txt) return null;
  const nums = (txt.match(/\d*\.?\d+/g) || []).map(Number).filter((n) => n > 0);
  return nums.length ? Math.max(...nums) : null;
}

/**
 * Water loss free text -> gallons per minute. Takes numbers that carry a unit
 * (gpm, gallons, gph); if the text says it escalated or gives "a/b", the
 * largest. Otherwise the first number. 'Unsure' -> null.
 */
export function parseGpm(txt) {
  if (!txt) return null;
  const t = txt.replace(/�/g, '"');
  const withUnit = [...t.matchAll(/(\d*\.?\d+)\s*(gpm|gpn|gallons?|gph)/gi)]
    .map((m) => Number(m[1]) / (m[2].toLowerCase() === 'gph' ? 60 : 1));
  if (withUnit.length) return Math.max(...withUnit);
  const all = (t.match(/\d*\.?\d+/g) || []).map(Number);
  if (!all.length) return null;
  return /escalat|\//i.test(t) ? Math.max(...all) : all[0];
}

/** Repair notes etc. lost their typographic quotes in the export (U+FFFD). */
function fixText(s) {
  if (!s) return s;
  return s.replace(/(\d)�/g, '$1″').replace(/([A-Za-z])�([A-Za-z])/g, '$1’$2').replace(/�/g, '"').trim();
}

const pretty = (s) => (s ? s.replace(/_+/g, ' ').trim() : null);
const zoneName = (s) => (s ? s.replace(/_Plane$/, '').replace(/_/g, ' ') : null);

/**
 * Builds the in-memory leak features. Only whitelisted, non-personal fields
 * are copied: Creator/Editor never leave this function, and the notes of
 * records naming people are dropped.
 */
export function prepareLeaks(fc) {
  const out = [];
  for (const f of fc.features) {
    const p = f.properties;
    if (DROP_IDS.has(p.ObjectId) || !f.geometry) continue;
    const size = parseSize(p.line_size);
    const gpm = parseGpm(p.approximate_water_loss_gpm);
    const cause = CAUSES.findIndex((c) => c.raw === p.cause_of_leak);
    const t = p.datetime ?? null;
    out.push({
      type: 'Feature',
      id: p.ObjectId,
      geometry: f.geometry,
      properties: {
        id: p.ObjectId,
        t: t ?? -1,
        year: t ? new Date(t).getUTCFullYear() : -1,
        size, // inches or null
        sbin: size == null ? -1 : size <= 1 ? 0 : size <= 2 ? 1 : size <= 3 ? 2 : size <= 6 ? 3 : 4,
        gpm: gpm ?? -1,
        gbin: gpm == null ? -1 : gpm < 10 ? 0 : gpm < 25 ? 1 : gpm < 50 ? 2 : gpm < 100 ? 3 : 4,
        cbin: cause < 0 ? 2 : cause,
        ybin: t ? new Date(t).getUTCFullYear() : -1,
        repair: p.type_of_repair ? p.type_of_repair.split(',').map((x) => pretty(x)).filter(Boolean)
          .map((x) => x[0].toUpperCase() + x.slice(1)).join(', ') : null,
        zone: zoneName(p.what_pressure_plane_did_the_lea),
        zoneRaw: p.what_pressure_plane_did_the_lea || null,
        duration: fixText(p.length_of_time_it_took_to_compl),
        notes: HIDE_NOTES_IDS.has(p.ObjectId) ? null : fixText(p.notes),
        notesHidden: HIDE_NOTES_IDS.has(p.ObjectId) && !!p.notes,
        // Raw loss text can name people; keep only whether it was a plain number.
        lossPlain: isPlainLoss(p.approximate_water_loss_gpm),
      },
    });
  }
  return out;
}

// ------------------------------------------------------------- filtering ----

export function makeFilter() {
  return {
    t0: T0, t1: T1,
    sizes: new Set([...SIZES, null]),
    causes: new Set([0, 1, 2]),
  };
}

/** Attribute filter (everything except time). */
export function passesAttr(p, f) {
  return f.sizes.has(p.size) && f.causes.has(p.cbin);
}

/** Time filter. Undated records only appear when the full range is selected. */
export function passesTime(p, f) {
  if (p.t < 0) return f.t0 <= T0 && f.t1 >= T1;
  return p.t >= f.t0 && p.t < f.t1;
}

// --------------------------------------------------------------- styling ----

export function colorExpr(mode) {
  const m = COLOR_MODES[mode];
  const fallback = m.bins.find((b) => b.v === -1)?.color ?? '#9aa3ad';
  return ['match', ['get', m.prop], ...m.bins.filter((b) => b.v !== -1).flatMap((b) => [b.v, b.color]), fallback];
}

/** Radius factor for "size by" modes. */
export function sizeFactorExpr(mode) {
  if (mode === 'loss') {
    // sqrt scale on gpm, clamped: 1 gpm -> 0.75, 25 gpm -> 1.25, 400 gpm -> 2.6
    return ['case', ['<', ['get', 'gpm'], 0], 0.8,
      ['min', 2.8, ['max', 0.7, ['+', 0.6, ['*', 0.1, ['sqrt', ['get', 'gpm']]]]]]];
  }
  if (mode === 'size') {
    return ['case', ['==', ['get', 'sbin'], -1], 0.8, ['+', 0.75, ['*', 0.35, ['get', 'sbin']]]];
  }
  return 1;
}

export function radiusExpr(mode) {
  const f = sizeFactorExpr(mode);
  const s = (r) => (f === 1 ? r : ['*', r, f]);
  return ['interpolate', ['linear'], ['zoom'], 8, s(2.6), 11, s(4.2), 14, s(7), 17, s(10)];
}

// ------------------------------------------------------------- formatting ---

const fmtCT = new Intl.DateTimeFormat('en-US', {
  timeZone: 'America/Chicago', weekday: 'short', year: 'numeric', month: 'short', day: 'numeric',
  hour: 'numeric', minute: '2-digit', timeZoneName: 'short',
});
export const fmtDateCT = (t) => (t < 0 ? 'No date recorded' : fmtCT.format(new Date(t)));
const fmtUTCDay = new Intl.DateTimeFormat('en-GB', { timeZone: 'UTC', year: 'numeric', month: 'short', day: 'numeric' });
export const fmtDay = (t) => fmtUTCDay.format(new Date(t));
export const fmtISO = (t) => new Date(t).toISOString().slice(0, 10);

export function fmtGpm(g) {
  if (g == null || g < 0) return null;
  if (g < 1) return `${+g.toFixed(2)} gpm`;
  return `${Math.round(g).toLocaleString('en-US')} gpm`;
}

/** True when the free text is just a number with an optional unit (safe to show verbatim). */
export function isPlainLoss(txt) {
  return !!txt && /^\s*\d*\.?\d+\s*(gpm|gallons?( a| per)? minute)?\s*$/i.test(txt);
}
