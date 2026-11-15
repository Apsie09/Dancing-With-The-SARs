// Leak-risk ranking per pipe piece and month (data/coryell/risk/, built by
// `pixi run coryell-risk` in asen_results/). The ranking uses leak history and
// pipe attributes only; ranks are percentiles over the hold-out
// (Nov 2025 to Oct 2026), so 1 means the riskiest 1% of pipe-months.
// Tiers are a cyan ramp, wide enough to show around the leak dots, whose own
// colour schemes are warm.
export const RISK_DIR = '../data/coryell/risk/';
export const RISK_TIERS = [
  { max: 1, color: '#8ffcff', label: 'Top 1% riskiest', w: [4.5, 11] },
  { max: 5, color: '#22c7e8', label: 'Top 5%', w: [3.2, 8] },
  { max: 20, color: '#2f86b3', label: 'Top 20%', w: [1.9, 4.5] },
  { max: 100, color: '#aab3bd', label: 'Other pipes', w: [0.9, 2.2] },
];
const keyOf = (month) => `r_${month.replace('-', '_')}`;
const pct = (key) => ['to-number', ['get', key], 100];
const step = (key, pick) => {
  const e = ['step', pct(key), pick(RISK_TIERS[0])];
  for (let i = 1; i < RISK_TIERS.length; i++) e.push(RISK_TIERS[i - 1].max + 1, pick(RISK_TIERS[i]));
  return e;
};
export const riskColor = (key) => step(key, (t) => t.color);
export const riskWidth = (key, extra = 0) => ['interpolate', ['linear'], ['zoom'],
  9, step(key, (t) => t.w[0] + extra), 15, step(key, (t) => t.w[1] + extra * 2)];
export const RISK_DEFAULT_KEY = 'r_2026_10';

const tierOf = (p) => RISK_TIERS.find((t) => p <= t.max) || RISK_TIERS[RISK_TIERS.length - 1];
const rankLabel = (p) => (p == null ? 'not ranked' : p <= 20 ? `top ${p}%` : 'lower 80%');
const monthLabel = (m) => new Date(`${m}-15T00:00:00Z`).toLocaleString('en-US', { month: 'short', year: 'numeric', timeZone: 'UTC' });
const share = (v) => `${Math.round(v * 100)}%`;

export async function initRisk({ map, setOverlayVisibleById }) {
  let sum;
  try {
    const res = await fetch(`${RISK_DIR}risk_summary.json`);
    if (!res.ok) throw new Error(res.status);
    sum = await res.json();
  } catch { return null; }
  const months = sum.months;
  let month = months[months.length - 1];
  const m = sum.metrics.model;

  const body = document.querySelector('#ov-pipe-risk .ov-body');
  const box = document.createElement('div');
  box.className = 'risk-box';
  box.innerHTML = `
    <label class="risk-month">Month
      <select>${months.map((x) => `<option value="${x}">${monthLabel(x)}</option>`).join('')}</select>
    </label>
    <p class="ov-info risk-now"></p>
    <p class="ov-info">Past leaks and pipe attributes. AUC ${m.auc.toFixed(2)} on 12 held-out months.</p>`;
  if (body) body.insertBefore(box, body.firstChild);
  const select = box.querySelector('select');

  function setMonth(x) {
    if (!months.includes(x)) return;
    month = x;
    select.value = x;
    const key = keyOf(x);
    if (map.getLayer('risk-line')) {
      map.setPaintProperty('risk-line', 'line-color', riskColor(key));
      map.setPaintProperty('risk-line', 'line-width', riskWidth(key));
      map.setPaintProperty('risk-casing', 'line-width', riskWidth(key, 1.2));
    }
    const pm = sum.per_month.find((r) => r.month === x);
    box.querySelector('.risk-now').textContent = pm
      ? `${pm.leaks} leaked · ${pm.in_top5} in top 5% · ${pm.in_top20} in top 20%` : '';
  }
  select.addEventListener('change', () => setMonth(select.value));
  setMonth(month);
  // The diameter-coloured pipe layer competes with the risk colours; it stays one click away.
  setOverlayVisibleById?.('pipes', false);

  return {
    setMonth,
    /** Follow a NISAR pass date (YYYY-MM-DD); dates outside the hold-out are ignored. */
    setMonthFromDate(d) { if (d) setMonth(d.slice(0, 7)); },
    /** Row for the leak popup: where the leaking pipe stood in the ranking that month. */
    leakRow(id) {
      const r = sum.leak_rank[id];
      if (!r) return null;
      return ['Risk rank', `<span class="lg-line" style="background:${tierOf(r.pct).color};height:3px"></span> ${rankLabel(r.pct)}
        <span class="pp-sub">its pipe, the month it leaked${r.construction ? '; construction damage is not what the ranking predicts' : ''}</span>`];
    },
    popup(p) {
      const cur = p[keyOf(month)];
      const strip = months.map((x) => {
        const v = p[keyOf(x)];
        return `<i title="${monthLabel(x)}: ${rankLabel(v)}" style="background:${tierOf(v ?? 100).color}${x === month ? ';outline:2px solid #fff' : ''}"></i>`;
      }).join('');
      const rows = [
        ['Rank', `${rankLabel(cur)} <span class="pp-sub">${monthLabel(month)}</span>`],
        ['Leaks on this piece', `${p.leaks_on_piece} <span class="pp-sub">since 2019</span>`],
        ['Leaks within 200 m', `${p.leaks_200m}`],
        ['Size', p.size ? String(p.size).replace(/"/g, '″') : (p.dia ? `${p.dia}″` : '–')],
        ['Length', `${p.len_m} m`],
        ['Pressure zone', p.zone_name || '–'],
      ];
      return `<div class="pp"><div class="pp-head"><span class="lg-line" style="background:${tierOf(cur ?? 100).color};height:3px"></span><b>Leak risk</b></div>
        <dl>${rows.map(([k, v]) => `<dt>${k}</dt><dd>${v}</dd>`).join('')}</dl>
        <div class="risk-strip">${strip}</div>
        <div class="risk-strip-lab"><span>${monthLabel(months[0])}</span><span>${monthLabel(months[months.length - 1])}</span></div>
        <div class="pp-foot">Piece ${p.piece} of water line ${p.pipe_id} · rank among all pipe-months</div></div>`;
    },
  };
}
