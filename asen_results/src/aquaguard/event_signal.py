"""Offline fixed-protocol repair-relative signal diagnostic; see docs/EVENT_SIGNAL_PROTOCOL.md."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import h5py
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
RADII = (10, 30, 60)
SEED = 20261115


def split_for(event_id):
    return 'validation' if int(hashlib.sha256(str(int(event_id)).encode()).hexdigest(), 16) % 10 < 3 else 'development'


def masks(size=64, spacing=10):
    yy, xx = np.indices((size, size))
    distance = np.hypot(yy - size // 2, xx - size // 2) * spacing
    return {r: distance <= r for r in RADII}, (distance >= 100) & (distance <= 300)


def contrast(raw, valid, disk, ring):
    """Difference of dB linear means, with explicit finite coverage denominators."""
    good = valid & np.isfinite(raw) & (raw > 0)
    if good.mean() < .9 or good[disk].mean() < .8 or good[ring].mean() < .8:
        return np.nan
    return float(10 * np.log10(raw[good & disk].mean()) - 10 * np.log10(raw[good & ring].mean()))


def window(delta):
    if -30 <= delta < 0:
        return 'pre'
    if 30 <= delta <= 90:
        return 'post'
    return 'other'


def extract():
    disks, ring = masks()
    tables, audit = [], []
    for dirname in ('coryell', 'coryell_confirm'):
        d = ROOT / 'data/sar' / dirname
        idx = pd.read_parquet(d / 'sar_patches.parquet')
        events = pd.read_parquet(d / 'leaks.parquet').set_index('leak_id')
        before = len(idx)
        idx = idx[(idx.maturity != 'beta') & idx.incident_id.isin(events.index[events.cause != 'Construction_Maintenance_Induce'])].copy()
        idx['gpm'] = idx.incident_id.map(events.gpm)
        idx['split'] = idx.incident_id.map(split_for)
        idx['stack'] = idx.comparison_group
        cols = ['incident_id', 'site_id', 'site_type', 'pass_id', 'stack', 'delta_days', 'gpm', 'split']
        vals = {f'{pol}_{r}': [] for pol in ('hh', 'hv') for r in RADII}
        with h5py.File(d / 'patches.h5') as h:
            for count, row in enumerate(idx.itertuples()):
                raw, valid = h['gamma0'][row.patch_index], h['valid'][row.patch_index]
                for band, pol in enumerate(('hh', 'hv')):
                    for r in RADII:
                        vals[f'{pol}_{r}'].append(contrast(raw[band], valid, disks[r], ring))
                if count % 5000 == 0:
                    print(dirname, count, '/', len(idx), flush=True)
        table = idx[cols].reset_index(drop=True)
        for name, values in vals.items():
            table[name] = values
        tables.append(table)
        audit.append({'cache': dirname, 'patch_rows': before, 'non_beta_natural_rows': len(idx), 'events': idx.incident_id.nunique()})
    return pd.concat(tables, ignore_index=True), audit


def matched_passes(table):
    """Use fixed first control as placebo, never all control-minus-other averages."""
    controls = table[table.site_type == 'control']
    chosen = controls.groupby('incident_id').site_id.min().to_dict()
    out = []
    for keys, group in table.groupby(['incident_id', 'stack', 'pass_id'], sort=True):
        event, stack, pass_id = keys
        incident = group[group.site_type == 'incident']
        ctl = group[group.site_type == 'control'].drop_duplicates('site_id')
        if len(incident) != 1:
            raise ValueError(f'Expected one incident patch for {keys}')
        row = incident.iloc[0]
        for pol in ('hh', 'hv'):
            for r in RADII:
                feature = f'{pol}_{r}'
                good = ctl[np.isfinite(ctl[feature])]
                if not np.isfinite(row[feature]) or len(good) < 2:
                    continue
                pseudo = good[good.site_id == chosen.get(event)]
                others = good[good.site_id != chosen.get(event)]
                placebo = float(pseudo[feature].iloc[0] - others[feature].mean()) if len(pseudo) == 1 and len(others) else np.nan
                out.append(dict(incident_id=event, stack=stack, pass_id=pass_id, delta_days=row.delta_days,
                                split=row.split, gpm=row.gpm, polarization=pol, radius_m=r, controls=len(good),
                                matched=float(row[feature] - good[feature].mean()), placebo=placebo,
                                window=window(row.delta_days)))
    return pd.DataFrame(out)


def effects(passes, minimum=2, value='matched'):
    rows = []
    for keys, group in passes.groupby(['incident_id', 'stack', 'polarization', 'radius_m']):
        pre = group.loc[group.window == 'pre', value].dropna()
        post = group.loc[group.window == 'post', value].dropna()
        if len(pre) < minimum or len(post) < minimum:
            continue
        row = group.iloc[0]
        rows.append(dict(incident_id=keys[0], stack=keys[1], polarization=keys[2], radius_m=keys[3],
                         split=row.split, gpm=row.gpm, n_pre=len(pre), n_post=len(post), effect_db=pre.mean()-post.mean()))
    return pd.DataFrame(rows, columns=['incident_id','stack','polarization','radius_m','split','gpm','n_pre','n_post','effect_db'])


def event_effects(stack_effects):
    return stack_effects.groupby(['incident_id','polarization','radius_m','split'], as_index=False).agg(
        effect_db=('effect_db','mean'), gpm=('gpm','first'), n_stacks=('stack','nunique'))


def estimate(values):
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]
    if not len(values):
        return dict(n_events=0, mean_db=np.nan, ci_low=np.nan, ci_high=np.nan, median_db=np.nan)
    rng = np.random.default_rng(SEED)
    draws = rng.choice(values, (2000,len(values)), replace=True).mean(axis=1)
    return dict(n_events=len(values), mean_db=float(values.mean()), ci_low=float(np.quantile(draws,.025)),
                ci_high=float(np.quantile(draws,.975)), median_db=float(np.median(values)))


def summaries(events, minimum, metric):
    rows=[]
    for (split,pol,r), group in events.groupby(['split','polarization','radius_m']):
        for subgroup in ('all','gpm_ge_50'):
            g=group if subgroup == 'all' else group[group.gpm >= 50]
            rows.append(dict(split=split,polarization=pol,radius_m=r,minimum_passes=minimum,metric=metric,
                             subgroup=subgroup,**estimate(g.effect_db)))
    return rows


def plot(passes, destination):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(2,3,figsize=(13,7),sharex=True,sharey=True)
    selected=passes[passes.delta_days.between(-90,120)].copy()
    selected['bin']=np.floor(selected.delta_days/15)*15+7.5
    # Equal event weighting, first equal means across observations within event/bin.
    means=selected.groupby(['incident_id','split','polarization','radius_m','bin'],as_index=False)[['matched','placebo']].mean()
    trajectories=[]
    for (split,pol,r,b), group in means.groupby(['split','polarization','radius_m','bin']):
        trajectories.append(dict(split=split,polarization=pol,radius_m=r,day=b,**estimate(group.matched)))
    traj=pd.DataFrame(trajectories)
    traj.to_csv(destination.with_name('event_signal_trajectories.csv'),index=False)
    for i,pol in enumerate(('hh','hv')):
        for j,r in enumerate(RADII):
            ax=axes[i,j]
            for split,color in [('development','tab:blue'),('validation','tab:orange')]:
                g=traj[(traj.split==split)&(traj.polarization==pol)&(traj.radius_m==r)].sort_values('day')
                ax.plot(g.day,g.mean_db,label=split,color=color)
                ax.fill_between(g.day,g.ci_low,g.ci_high,alpha=.15,color=color)
            ax.axvline(0,color='black',ls=':'); ax.axhline(0,color='grey',lw=.7)
            ax.axvspan(-30,0,color='green',alpha=.07);ax.axvspan(30,90,color='purple',alpha=.07)
            ax.set_title(f'{pol.upper()} radius {r} m');ax.set_xlabel('Days relative to recorded repair')
            if j==0: ax.set_ylabel('Site minus matched controls (dB)')
    axes[0,0].legend();fig.suptitle('Repair-relative proxy trajectories; shading: event-bootstrap 95% CI')
    fig.tight_layout();fig.savefig(destination,dpi=160);plt.close(fig)


def main():
    out=ROOT/'data/reports';out.mkdir(parents=True,exist_ok=True)
    table,audit=extract()
    table.drop(columns=[],errors='ignore').to_parquet(out/'event_signal_patch_features.parquet',index=False)
    passes=matched_passes(table);passes.to_csv(out/'event_signal_passes.csv',index=False)
    summary=[]; event_tables=[];stack_tables=[]
    for minimum in (2,1):
        for metric in ('matched','placebo'):
            stacks=effects(passes,minimum,metric)
            events=event_effects(stacks)
            summary.extend(summaries(events,minimum,metric))
            event_tables.append(events.assign(minimum_passes=minimum,metric=metric))
            stack_tables.append(stacks.assign(minimum_passes=minimum,metric=metric))
    result=pd.DataFrame(summary)
    result.to_csv(out/'event_signal_summary.csv',index=False)
    pd.concat(event_tables).to_csv(out/'event_signal_events.csv',index=False)
    pd.concat(stack_tables).to_csv(out/'event_signal_stack_effects.csv',index=False)
    event_meta=table[['incident_id','split','gpm']].drop_duplicates('incident_id')
    eligibility=event_meta.copy()
    primary=event_tables[0].query("polarization == 'hh' and radius_m == 30")
    eligibility['primary_eligible']=eligibility.incident_id.isin(primary.incident_id)
    eligibility['reason']=np.where(eligibility.primary_eligible,'eligible','insufficient same-stack quality-controlled pre/post passes with controls')
    eligibility.to_csv(out/'event_signal_eligibility.csv',index=False)
    plot(passes,out/'event_signal_trajectories.png')
    selected=result.query("metric == 'matched' and minimum_passes == 2 and polarization == 'hh' and radius_m == 30 and subgroup == 'all'")
    report=['# Coryell repair-relative multiscale diagnostic','',
      'This experiment tests a repair-associated SAR change, not known active leakage, classifier performance, or moisture specificity.',
      'Protocol: `docs/EVENT_SIGNAL_PROTOCOL.md`. No data download or original report modification.', '',
      '## Primary result: HH, 30 m radius, >=2 pre and >=2 post passes per stack','',selected.to_markdown(index=False),'',
      'Positive values mean greater matched site brightness before repair than after. Each event contributes once after equal averaging of eligible stacks.',
      'Internal validation is a deterministic event split of previously explored data, not independent confirmation. Event bootstrap does not account fully for shared scenes/nearby sites.',
      '', '## Coverage','',pd.DataFrame(audit).to_markdown(index=False),'',
      eligibility.groupby(['split','primary_eligible']).size().rename('events').reset_index().to_markdown(index=False),'',
      'Dropout means insufficient observations after all fixed quality/window/control requirements; excluded events are listed in event_signal_eligibility.csv.',
      '', '## All predefined effects','',result.to_markdown(index=False),'',
      '## Limits and artifacts','',
      '- Repair timestamps do not establish onset or actual completion; pre [-30,0) is a proxy. Post [30,90] is not verified dry.',
      '- Controls are unverified non-leaks; they are nearby network locations, not proven matched land cover/weather.',
      '- Cache masks enforce validity but grid spacing is assumed from the documented 10 m extraction; original caches omit per-granule spacing metadata.',
      '- 10 m radius statistics involve very few pixels and are especially sensitive to speckle and positional uncertainty.',
      '- Secondary scales, HV, large leaks and one-pass sensitivity are descriptive; no selection or multiple-comparison significance claim.',
      '- Bootstrap intervals assume independent events; nearby sites/shared acquisition noise can violate this.',
      '- event_signal_events.csv: one effect per event; event_signal_stack_effects.csv: within-stack effects.',
      '- event_signal_passes.csv and event_signal_patch_features.parquet: auditable extraction and matching.',
      '- event_signal_trajectories.png/.csv: all-event trajectories, not outcome-selected examples.',
      '- Placebo uses one fixed control against the remaining controls; it is not the algebraically cancelling pooled leave-one-out average.',
      '']
    (out/'event_signal_report.md').write_text('\n'.join(report))
    (out/'event_signal_audit.json').write_text(json.dumps(audit,indent=2))
    print(selected.to_string(index=False),flush=True)

if __name__ == '__main__':
    main()
