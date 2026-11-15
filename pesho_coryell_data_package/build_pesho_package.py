"""Build the Coryell NISAR train/test chip package (`pesho_coryell_data_package/`).

Positives are Coryell City WSD leak repairs, negatives are random points on the
district pipe network at the same NISAR pass. For every sample the script cuts a
20 x 20 px (200 m) chip from four passes of stack 041_D_073 (CRID P05023):
t-2, t-1, t0 (last pass at or before the repair), t+1, with six raw bands, and
computes circle and district-wide normalisation statistics.

Stages (run all, or one at a time with --stage; every stage is resumable)
    plan      positives, leakage groups, stratified 80/20 split, negatives  -> <work>/plan.json
    remote    per granule: inputDataExceptionMask over the district window and
              rtcGammaToSigmaFactor at the needed chips, read remotely     -> <work>/remote/<date>.npz
    extract   per pass: district stats, chips, circle stats                 -> <work>/extract/<date>.npz/.json
    assemble  the package: index.csv, passes.csv, <split>/<sample>/sar.npz + meta.json, summary.json

Inputs
    data/coryell/leak_survey.geojson, waterlines.geojson, pressure_zones.geojson
    data/coryell/nisar/acquisitions_041D073.json             the 24 P05023 passes (granule, time, URL)
    data/coryell/nisar/district/nisar_index.json + GeoTIFFs  district subsets (HHHH, HVHV, mask,
                                                             numberOfLooks), made by
                                                             scripts/download_nisar_coryell.py
    Passes without a local district GeoTIFF are read remotely (same four bands).
    Remote reads need an Earthdata login in ~/.netrc; signed URLs are requested per granule.

Usage
    python pesho_coryell_data_package/build_pesho_package.py                     # all stages
    python pesho_coryell_data_package/build_pesho_package.py --stage plan        # one stage
    python pesho_coryell_data_package/build_pesho_package.py --stage remote --workers 3
    Options: --seed 20261115, --work data/coryell/nisar/pesho_work, --out pesho_coryell_data_package,
             --min-free-gb 8 (stop if the disk gets fuller than that)

Needs numpy, h5py, fsspec, aiohttp, requests, pyproj, rasterio, shapely (no pandas).
"""
import argparse
import csv
import json
import math
import os
import re
import shutil
import sys
import time
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
DATA = REPO / 'data' / 'coryell'
NISAR = DATA / 'nisar'
DIST = NISAR / 'district'
DEFAULT_WORK = NISAR / 'pesho_work'
DEFAULT_OUT = REPO / 'pesho_coryell_data_package'
GRID = '/science/LSAR/GCOV/grids/frequencyA'

SEED = 20261115
NISAR_START = '2025-10-17'
DROP_IDS = {1611}                    # Galveston test entry
MAX_DAYS_TO_REPAIR = 12.0            # positive: last pass at/before repair, at most 12 days earlier
N_NEG = 10                           # negatives per positive
NEG_LEAK_DIST = 300.0                # m: negatives this far from any leak ...
NEG_LEAK_DAYS = 60.0                 # ... repaired within this many days of t0
CHIP = 20                            # px; 10 m pixels -> 200 m
PX = 10.0
HALF = CHIP // 2
RADII = (250, 500, 1000, 2000)       # m, circle statistics
TEST_FRAC = 0.2
ROLES = ('t-2', 't-1', 't0', 't+1')
ROLE_OFF = (-2, -1, 0, 1)
BANDS = ('HHHH', 'HVHV', 'mask', 'numberOfLooks', 'inputDataExceptionMask', 'rtcGammaToSigmaFactor')
DAY_MS = 86400000
CAUSE = {'Naturally_Occurred': 'natural', 'Construction_Maintenance_Induce': 'construction', 'Other': 'other'}
DISTRICT_BBOX = (-97.904, 31.337, -97.412, 31.686)


def log(msg):
    print(f'[{datetime.now().strftime("%H:%M:%S")}] {msg}', flush=True)


def free_gb(path):
    return shutil.disk_usage(path).free / 1e9


def check_disk(path, min_gb):
    f = free_gb(path)
    if f < min_gb:
        raise SystemExit(f'STOP: free disk {f:.1f} GB < {min_gb} GB')
    return f


def iso(ms):
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def r6(v, n=6):
    return None if v is None or not np.isfinite(v) else round(float(v), n)


# ------------------------------------------------------------------ inputs --

def parse_size(txt):
    if not txt:
        return None
    nums = [float(n) for n in re.findall(r'\d*\.?\d+', str(txt)) if float(n) > 0]
    return max(nums) if nums else None


def parse_gpm(txt):
    """Same rules as scripts/make_leak_chips.py and viz/leaks.js (largest of 'x/y' or 'escalated to')."""
    if not txt:
        return None
    t = str(txt).replace('�', '"')
    wu = [float(m.group(1)) / (60 if m.group(2).lower() == 'gph' else 1)
          for m in re.finditer(r'(\d*\.?\d+)\s*(gpm|gpn|gallons?|gph)', t, re.I)]
    if wu:
        return max(wu)
    allnums = [float(n) for n in re.findall(r'\d*\.?\d+', t)]
    if not allnums:
        return None
    return max(allnums) if re.search(r'escalat|/', t, re.I) else allnums[0]


def load_leaks(tr):
    """All leak records with a point (any date), ObjectId 1611 dropped. No personal or free-text fields kept."""
    fc = json.loads((DATA / 'leak_survey.geojson').read_text(encoding='utf-8'))
    out = []
    for f in fc['features']:
        p = f['properties']
        if p['ObjectId'] in DROP_IDS or not f.get('geometry'):
            continue
        lon, lat = f['geometry']['coordinates'][:2]
        x, y = tr.transform(lon, lat)
        out.append(dict(id=int(p['ObjectId']), t=p.get('datetime'), lon=lon, lat=lat, x=x, y=y,
                        cause=CAUSE.get(p.get('cause_of_leak'), 'unknown' if not p.get('cause_of_leak') else 'other'),
                        size_in=parse_size(p.get('line_size')), loss_gpm=parse_gpm(p.get('approximate_water_loss_gpm')),
                        repair_type=p.get('type_of_repair') or '',
                        zone_reported=(p.get('what_pressure_plane_did_the_lea') or '').replace('_Plane', '').replace('_', ' ')))
    return out


def load_pipes(tr):
    from shapely import STRtree
    from shapely.geometry import LineString
    fc = json.loads((DATA / 'waterlines.geojson').read_text(encoding='utf-8'))
    lines, attrs = [], []
    for f in fc['features']:
        g = f['geometry']
        if not g or g['type'] != 'LineString':
            continue
        xs, ys = tr.transform(*zip(*[c[:2] for c in g['coordinates']]))
        lines.append(LineString(list(zip(xs, ys))))
        p = f['properties']
        dia = p.get('Diameter')
        attrs.append(dict(pipe_id=p.get('OBJECTID'), pipe_size=(p.get('Size') or '').strip(),
                          pipe_diameter_in=float(dia) if dia not in (None, '') else parse_size(p.get('Size')),
                          pipe_material=(p.get('Material') or '').strip()))
    return lines, attrs, STRtree(lines)


def load_zones():
    from shapely.geometry import shape
    fc = json.loads((DATA / 'pressure_zones.geojson').read_text(encoding='utf-8'))
    return [(f['properties']['Name'].replace(' Plane', ''), shape(f['geometry'])) for f in fc['features']]


def zone_of(zones, lon, lat):
    from shapely.geometry import Point
    pt = Point(lon, lat)
    for name, poly in zones:
        if poly.contains(pt):
            return name
    return ''


def load_passes():
    acq = json.loads((NISAR / 'acquisitions_041D073.json').read_text(encoding='utf-8'))['acquisitions']
    idx = json.loads((DIST / 'nisar_index.json').read_text(encoding='utf-8')) if (DIST / 'nisar_index.json').exists() else {'files': []}
    local = {f['granule']: f for f in idx['files']}
    for a in acq:
        f = local.get(a['granule'])
        a['local_tif'] = str(DIST / f['file']) if f and (DIST / f['file']).exists() else None
    return acq


def grid_of(passes, work):
    """Reference raster grid (all district GeoTIFFs of the stack share it): x0, y0 (top-left corner), w, h."""
    import rasterio
    ref = None
    for a in passes:
        if a['local_tif']:
            with rasterio.open(a['local_tif']) as src:
                g = (src.transform.c, src.transform.f, src.width, src.height, src.transform.a, src.transform.e)
            if ref is None:
                ref = g
            elif g != ref:
                raise SystemExit(f'grid mismatch {a["date"]}: {g} vs {ref}')
    if ref is None:
        raise SystemExit('no local district GeoTIFF found; run scripts/download_nisar_coryell.py first')
    assert ref[4] == PX and ref[5] == -PX, ref
    return dict(x0=ref[0], y0=ref[1], w=ref[2], h=ref[3])


def read_band(path, band):
    import rasterio
    with rasterio.open(path) as src:
        return src.read(band)


# -------------------------------------------------------------------- plan --

def chip_origin(G, x, y):
    """Chip top-left pixel (col0, row0) in the district grid: the point lies between the 4 centre pixels."""
    fc, fr = (x - G['x0']) / PX, (G['y0'] - y) / PX           # fractional pixel coords (centres at i + 0.5)
    return int(round(fc)) - HALF, int(round(fr)) - HALF, fc, fr


def chips_overlap(a, b):
    return abs(a[0] - b[0]) < CHIP and abs(a[1] - b[1]) < CHIP


def window_idx(i, n):
    return [i + o if 0 <= i + o < n else None for o in ROLE_OFF]


def split_groups(groups, pos, seed):
    """Assign whole groups to test so that test ~ 20% of positives and keeps the cause, zone, quarter and
    3x3 geographic-cell proportions. Seeded random restarts + greedy flip/swap hill climbing."""
    rng = np.random.default_rng(seed)
    keys = ('cause', 'zone_strat', 'quarter', 'geo_cell')
    cats = {k: sorted({p[k] for p in pos}) for k in keys}
    G = len(groups)
    # count matrix per group: one block per key
    cols = [(k, c) for k in keys for c in cats[k]]
    M = np.zeros((G, len(cols)))
    for gi, g in enumerate(groups):
        for m in g['members']:
            for j, (k, c) in enumerate(cols):
                if pos[m][k] == c:
                    M[gi, j] += 1
    sizes = np.array([len(g['members']) for g in groups], float)
    tot = M.sum(0)
    N = sizes.sum()
    w = np.array([2.0 if k == 'cause' else 1.0 for k, _ in cols])

    def score(sel):
        t = M[sel].sum(0)
        dev = (t - TEST_FRAC * tot) ** 2 / np.maximum(TEST_FRAC * tot, 1.0)
        return float((w * dev).sum() + 4.0 * (sizes[sel].sum() - TEST_FRAC * N) ** 2 / (TEST_FRAC * N))

    best_sel, best = None, np.inf
    for _ in range(30):
        sel = rng.random(G) < TEST_FRAC
        cur = score(sel)
        improved = True
        while improved:
            improved = False
            for gi in rng.permutation(G):
                sel[gi] = ~sel[gi]
                s = score(sel)
                if s < cur - 1e-9:
                    cur, improved = s, True
                else:
                    sel[gi] = ~sel[gi]
            ins, outs = np.flatnonzero(sel), np.flatnonzero(~sel)
            for a in rng.permutation(ins)[:25]:
                for b in rng.permutation(outs)[:25]:
                    sel[a], sel[b] = False, True
                    s = score(sel)
                    if s < cur - 1e-9:
                        cur, improved = s, True
                        break
                    sel[a], sel[b] = True, False
                if improved:
                    break
        if cur < best:
            best, best_sel = cur, sel.copy()
    return best_sel, best


def stage_plan(args):
    from pyproj import Transformer
    from shapely.geometry import Point
    tr = Transformer.from_crs(4326, 32614, always_xy=True)
    passes = load_passes()
    n = len(passes)
    G = grid_of(passes, args.work)
    tpass = np.array([a['t'] for a in passes], dtype=np.int64)
    leaks = load_leaks(tr)
    lines, pattrs, tree = load_pipes(tr)
    zones = load_zones()
    log(f'{len(leaks)} leak records with a point (1611 dropped), {len(lines)} pipes, {n} passes, grid {G}')

    # masks at t0 (only the passes that are used as t0 are read)
    mask_cache = {}

    def mask_at(i):
        if i not in mask_cache:
            a = passes[i]
            if a['local_tif']:
                mask_cache[i] = read_band(a['local_tif'], 3).astype(np.uint8)
            else:
                mask_cache[i] = np.load(Path(args.work) / 'remote_bands' / f'{a["date"]}.npz')['mask']
        return mask_cache[i]

    def centre_valid(i, col0, row0):
        m = mask_at(i)
        r, c = row0 + HALF - 1, col0 + HALF - 1
        if r < 0 or c < 0 or r + 2 > m.shape[0] or c + 2 > m.shape[1]:
            return False
        blk = m[r:r + 2, c:c + 2]
        return bool(((blk >= 1) & (blk <= 254)).all())

    def inside(col0, row0):
        return col0 >= 0 and row0 >= 0 and col0 + CHIP <= G['w'] and row0 + CHIP <= G['h']

    lx = np.array([l['x'] for l in leaks]); ly = np.array([l['y'] for l in leaks])
    lt = np.array([l['t'] if l['t'] is not None else -1 for l in leaks], dtype=np.int64)
    lt_known = np.array([l['t'] is not None for l in leaks])
    lid = np.array([l['id'] for l in leaks])

    # ---- positives
    start_ms = int(datetime.fromisoformat(NISAR_START).replace(tzinfo=timezone.utc).timestamp() * 1000)
    excluded = []
    pos = []
    for l in sorted(leaks, key=lambda l: (l['t'] or 0, l['id'])):
        if l['t'] is None or l['t'] < start_ms:
            continue
        i = int(np.searchsorted(tpass, l['t'], side='right')) - 1
        if i < 0:
            excluded.append(dict(objectid=l['id'], repair_utc=iso(l['t']), reason='before the first P05023 pass (2025-12-31)'))
            continue
        days = (l['t'] - tpass[i]) / DAY_MS
        if days > MAX_DAYS_TO_REPAIR:
            why = ('data gap 2026-07-23 to 08-16 (last pass > 12 days before repair)' if passes[i]['date'] == '2026-07-23'
                   else 'after the last P05023 pass + 12 days (2026-10-27)' if i == n - 1
                   else f'last pass {days:.1f} days before repair')
            excluded.append(dict(objectid=l['id'], repair_utc=iso(l['t']), reason=why, days=round(days, 2)))
            continue
        col0, row0, fc, fr = chip_origin(G, l['x'], l['y'])
        if not inside(col0, row0):
            excluded.append(dict(objectid=l['id'], repair_utc=iso(l['t']), reason='chip outside the district raster'))
            continue
        if not centre_valid(i, col0, row0):
            excluded.append(dict(objectid=l['id'], repair_utc=iso(l['t']), reason=f'centre pixels not valid in mask on t0 {passes[i]["date"]}'))
            continue
        d = np.hypot(lx - l['x'], ly - l['y'])
        d[lid == l['id']] = np.inf
        j = int(np.argmin(d))
        near60 = lt_known & (np.abs(lt - tpass[i]) <= NEG_LEAK_DAYS * DAY_MS)
        d60 = np.where(near60, d, np.inf)
        q = (int(passes[i]['date'][5:7]) - 1) // 3 + 1
        pos.append(dict(sample_id=f'P{l["id"]}', label=1, leak=l, pass_idx=i, col0=col0, row0=row0, fc=fc, fr=fr,
                        x=l['x'], y=l['y'], lon=l['lon'], lat=l['lat'], cause=l['cause'],
                        days_pass_to_repair=round(days, 3),
                        nearest_leak_m=round(float(d[j]), 1), nearest_leak_id=int(lid[j]),
                        nearest_leak_days=round((lt[j] - tpass[i]) / DAY_MS, 1) if lt_known[j] else None,
                        nearest_leak_pm60d_m=round(float(d60.min()), 1) if np.isfinite(d60.min()) else None,
                        quarter=f'{passes[i]["date"][:4]}Q{q}'))
    log(f'positives {len(pos)}, excluded {len(excluded)}: {Counter(e["reason"].split(" (")[0] for e in excluded)}')

    # geography strata for positives
    xs = np.array([p['x'] for p in pos]); ys = np.array([p['y'] for p in pos])
    gx0, gx1, gy0, gy1 = G['x0'], G['x0'] + G['w'] * PX, G['y0'] - G['h'] * PX, G['y0']
    for p in pos:
        p['zone'] = zone_of(zones, p['lon'], p['lat'])
        p['zone_strat'] = p['zone'] or p['leak']['zone_reported'] or 'none'
        cx = min(2, int(3 * (p['x'] - gx0) / (gx1 - gx0))); cy = min(2, int(3 * (gy1 - p['y']) / (gy1 - gy0)))
        p['geo_cell'] = f'{"NCS"[cy]}{"WCE"[cx]}'   # N/C/S row, W/C/E column of the district bbox

    # ---- leakage groups: positives whose chips overlap and whose 4-pass windows share a pass
    win = [set(k for k in window_idx(p['pass_idx'], n) if k is not None) for p in pos]
    parent = list(range(len(pos)))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a
    for a in range(len(pos)):
        for b in range(a + 1, len(pos)):
            if win[a] & win[b] and chips_overlap((pos[a]['col0'], pos[a]['row0']), (pos[b]['col0'], pos[b]['row0'])):
                parent[find(a)] = find(b)
    gmembers = defaultdict(list)
    for a in range(len(pos)):
        gmembers[find(a)].append(a)
    groups = []
    for root, mem in gmembers.items():
        gid = 'G' + str(min(pos[m]['leak']['id'] for m in mem))
        for m in mem:
            pos[m]['group_id'] = gid
        groups.append(dict(group_id=gid, members=sorted(mem)))
    groups.sort(key=lambda g: g['group_id'])
    log(f'{len(groups)} groups; sizes {Counter(len(g["members"]) for g in groups)}')

    sel, sc = split_groups(groups, pos, args.seed)
    for gi, g in enumerate(groups):
        for m in g['members']:
            pos[m]['split'] = 'test' if sel[gi] else 'train'
    log(f'split score {sc:.2f}; test positives {sum(p["split"] == "test" for p in pos)} of {len(pos)}')

    # ---- negatives
    segs = []
    for li, ln in enumerate(lines):
        c = np.asarray(ln.coords)
        for k in range(len(c) - 1):
            segs.append((c[k, 0], c[k, 1], c[k + 1, 0], c[k + 1, 1], li))
    segs = np.array(segs)
    seglen = np.hypot(segs[:, 2] - segs[:, 0], segs[:, 3] - segs[:, 1])
    cum = np.cumsum(seglen)
    L = cum[-1]
    rng = np.random.default_rng(args.seed + 1)
    placed = [dict(col0=p['col0'], row0=p['row0'], win=win[k], t0=p['pass_idx'], split=p['split']) for k, p in enumerate(pos)]
    P_col = np.array([p['col0'] for p in placed]); P_row = np.array([p['row0'] for p in placed])
    P_t0 = np.array([p['t0'] for p in placed]); P_split = np.array([p['split'] for p in placed])
    P_win = np.zeros((len(placed), n), bool)
    for k, p in enumerate(placed):
        P_win[k, list(p['win'])] = True
    negs = []
    rej = Counter()
    for p in sorted(pos, key=lambda p: (p['pass_idx'], p['leak']['id'])):
        i = p['pass_idx']
        wset = [k for k in window_idx(i, n) if k is not None]
        tconf = (~lt_known) | (np.abs(lt - tpass[i]) <= NEG_LEAK_DAYS * DAY_MS)
        cx_, cy_ = lx[tconf], ly[tconf]
        k_got, tries = 0, 0
        while k_got < N_NEG and tries < 50000:
            tries += 1
            u = rng.uniform(0, L)
            s = int(np.searchsorted(cum, u))
            f = (u - (cum[s] - seglen[s])) / max(seglen[s], 1e-9)
            x = segs[s, 0] + f * (segs[s, 2] - segs[s, 0]); y = segs[s, 1] + f * (segs[s, 3] - segs[s, 1])
            col0, row0, fc, fr = chip_origin(G, x, y)
            if not inside(col0, row0):
                rej['outside raster'] += 1; continue
            if len(cx_) and np.hypot(cx_ - x, cy_ - y).min() < NEG_LEAK_DIST:
                rej['< 300 m from a leak within 60 days'] += 1; continue
            ov = (np.abs(P_col - col0) < CHIP) & (np.abs(P_row - row0) < CHIP)
            if ov.any():
                same = ov & (P_t0 == i)
                cross = ov & P_win[:, wset].any(1) & (P_split != p['split'])
                if same.any():
                    rej['chip overlaps a sample on the same t0'] += 1; continue
                if cross.any():
                    rej['chip overlaps an other-split sample on a shared pass'] += 1; continue
            if not centre_valid(i, col0, row0):
                rej['centre pixels not valid on t0'] += 1; continue
            k_got += 1
            pipe = pattrs[int(segs[s, 4])]
            negs.append(dict(sample_id=f'N{p["leak"]["id"]}_{k_got:02d}', label=0, pos_id=p['sample_id'], pass_idx=i,
                             col0=col0, row0=row0, fc=fc, fr=fr, x=float(x), y=float(y), split=p['split'],
                             group_id=p['group_id'], sampled_pipe_id=pipe['pipe_id']))
            P_col = np.append(P_col, col0); P_row = np.append(P_row, row0); P_t0 = np.append(P_t0, i)
            P_split = np.append(P_split, p['split'])
            row = np.zeros((1, n), bool); row[0, wset] = True
            P_win = np.vstack([P_win, row])
        if k_got < N_NEG:
            log(f'  WARNING {p["sample_id"]}: only {k_got} negatives after {tries} tries')
    log(f'negatives {len(negs)}; rejections {dict(rej)}')

    # ---- attributes for every sample
    inv = Transformer.from_crs(32614, 4326, always_xy=True)
    allsamp = pos + negs
    pos_by_id = {p['sample_id']: p for p in pos}
    for s in allsamp:
        if s['label'] == 0:
            s['lon'], s['lat'] = inv.transform(s['x'], s['y'])
            s['zone'] = zone_of(zones, s['lon'], s['lat'])
            d = np.hypot(lx - s['x'], ly - s['y'])
            j = int(np.argmin(d))
            s['nearest_leak_m'] = round(float(d[j]), 1); s['nearest_leak_id'] = int(lid[j])
            s['nearest_leak_days'] = round((lt[j] - tpass[s['pass_idx']]) / DAY_MS, 1) if lt_known[j] else None
            near60 = lt_known & (np.abs(lt - tpass[s['pass_idx']]) <= NEG_LEAK_DAYS * DAY_MS)
            d60 = np.where(near60, d, np.inf)
            s['nearest_leak_pm60d_m'] = round(float(d60.min()), 1) if np.isfinite(d60.min()) else None
            pp = pos_by_id[s['pos_id']]
            s['stratum_cause'] = pp['cause']; s['quarter'] = pp['quarter']; s['geo_cell'] = pp['geo_cell']
        else:
            s['pos_id'] = s['sample_id']; s['stratum_cause'] = s['cause']
        pt = Point(s['x'], s['y'])
        k = int(tree.query_nearest(pt)[0])
        s.update({kk: vv for kk, vv in pattrs[k].items()})
        s['nearest_pipe_id'] = s.pop('pipe_id')
        s['dist_to_pipe_m'] = round(float(lines[k].distance(pt)), 2)

    def clean(s):
        o = {k: v for k, v in s.items() if k not in ('leak',)}
        if s['label'] == 1:
            l = s['leak']
            o.update(leak_objectid=l['id'], repair_utc=iso(l['t']), leak_pipe_size_in=l['size_in'],
                     loss_gpm=l['loss_gpm'], repair_type=l['repair_type'], zone_reported=l['zone_reported'])
        return o
    plan = dict(seed=args.seed, grid=G, passes=passes, samples=[clean(s) for s in allsamp],
                groups=[dict(group_id=g['group_id'], members=[pos[m]['sample_id'] for m in g['members']]) for g in groups],
                excluded=excluded, neg_rejections=dict(rej), split_score=sc)
    Path(args.work).mkdir(parents=True, exist_ok=True)
    (Path(args.work) / 'plan.json').write_text(json.dumps(plan, indent=1, default=float), encoding='utf-8')
    log(f'wrote plan: {len(pos)} positives, {len(negs)} negatives')


def load_plan(args):
    return json.loads((Path(args.work) / 'plan.json').read_text(encoding='utf-8'))


def needs_by_pass(plan):
    """pass index -> list of (sample_id, role, col0, row0, fc, fr)."""
    n = len(plan['passes'])
    need = defaultdict(list)
    for s in plan['samples']:
        for role, k in zip(ROLES, window_idx(s['pass_idx'], n)):
            if k is not None:
                need[k].append((s['sample_id'], role, s['col0'], s['row0'], s['fc'], s['fr']))
    return need


# ------------------------------------------------------------------ remote --

def remote_granule(acq, G, chips, out_path, want_bands, threads, log_path):
    """Worker: read inputDataExceptionMask (district window) and rtcGammaToSigmaFactor (chips) from one granule.
    want_bands: also read HHHH/HVHV/mask/numberOfLooks over the window (pass without a local GeoTIFF)."""
    import fsspec
    import h5py
    sys.path.insert(0, str(REPO / 'scripts'))
    from download_nisar_coryell import read_window, sign

    def wlog(msg):
        with open(log_path, 'a', encoding='utf-8') as fh:
            fh.write(f'[{datetime.now().strftime("%H:%M:%S")}] [{acq["date"]}] {msg}\n')
    t0 = time.time()
    last = None
    for attempt in range(3):
        try:
            signed = sign(acq['url'])
            fs = fsspec.filesystem('http', skip_instance_cache=True)
            f = fs.open(signed, block_size=2 ** 20, cache_type='blockcache', cache_options=dict(maxblocks=32))
            h = h5py.File(f, 'r')
            g = h[GRID]
            x = g['xCoordinates'][:]; y = g['yCoordinates'][:]
            assert int(g['projection'][()]) == 32614
            c0 = int(round((G['x0'] + PX / 2 - x[0]) / PX)); r0 = int(round((y[0] - (G['y0'] - PX / 2)) / PX))
            assert abs(x[c0] - (G['x0'] + 5)) < 1e-6 and abs(y[r0] - (G['y0'] - 5)) < 1e-6
            stats = dict(bytes=0)
            sl = (r0, r0 + G['h'], c0, c0 + G['w'])
            exc = read_window(g['inputDataExceptionMask'], signed, *sl, 0, threads, stats)
            # rtc: only the 512 x 512 chunks that hold chips -> read the bounding rows/cols in blocks of chunks
            rtc_full = np.full((G['h'], G['w']), np.nan, np.float32)
            need = set()
            for (_, _, col0, row0) in chips:
                for rr in (row0, row0 + CHIP - 1):
                    for cc in (col0, col0 + CHIP - 1):
                        need.add(((r0 + rr) // 512, (c0 + cc) // 512))
            from concurrent.futures import ThreadPoolExecutor

            def read_chunk(bc_):          # one 512 x 512 chunk, fetched in parallel below
                br, bc = bc_
                ra, rb = max(br * 512, r0), min(br * 512 + 512, r0 + G['h'])
                ca, cb = max(bc * 512, c0), min(bc * 512 + 512, c0 + G['w'])
                st = dict(bytes=0)
                a = read_window(g['rtcGammaToSigmaFactor'], signed, ra, rb, ca, cb, np.nan, 1, st)
                return ra, rb, ca, cb, a, st['bytes']
            # h5py serialises its own calls (global lock), so only the HTTP range fetches overlap
            with ThreadPoolExecutor(threads) as tpx:
                for ra, rb, ca, cb, a, nb in tpx.map(read_chunk, sorted(need)):
                    rtc_full[ra - r0:rb - r0, ca - c0:cb - c0] = a
                    stats['bytes'] += nb
            keys = [f'{sid}|{role}' for sid, role, _, _ in chips]
            rtc = np.stack([rtc_full[r:r + CHIP, c:c + CHIP] for _, _, c, r in chips]) if chips else np.zeros((0, CHIP, CHIP), np.float32)
            extra = {}
            if want_bands:
                mk = read_window(g['mask'], signed, *sl, 255, threads, stats)
                extra['mask'] = mk
                for b in ('HHHH', 'HVHV', 'numberOfLooks'):
                    a = read_window(g[b], signed, *sl, np.nan, threads, stats)
                    if b != 'numberOfLooks':
                        a[(mk < 1) | (mk > 254)] = np.nan
                    extra[b] = a
            meta = dict(granule=acq['granule'], h5_row0=r0, h5_col0=c0,
                        exc_description=g['inputDataExceptionMask'].attrs.get('description', b'').decode())
            h.close(); f.close()
            tmp = out_path.with_suffix('.tmp.npz')
            np.savez_compressed(tmp, exc=exc, rtc=rtc.astype(np.float32), keys=np.array(keys), meta=json.dumps(meta), **extra)
            os.replace(tmp, out_path)
            msg = f'ok: {len(chips)} rtc chips from {len(need)} chunks, {stats["bytes"] / 1e6:.1f} MB, {time.time() - t0:.0f} s, exc codes {np.unique(exc).tolist()}'
            wlog(msg)
            return dict(date=acq['date'], ok=True, msg=msg)
        except Exception as e:  # noqa: BLE001
            last = repr(e)[:300]
            wlog(f'attempt {attempt + 1} failed: {last}')
            time.sleep(5 * (attempt + 1))
    return dict(date=acq['date'], ok=False, msg=last)


def stage_remote(args):
    plan = load_plan(args)
    G = plan['grid']
    need = needs_by_pass(plan)
    rdir = Path(args.work) / 'remote'; rdir.mkdir(parents=True, exist_ok=True)
    log_path = Path(args.work) / 'remote.log'
    jobs = []
    for k, a in enumerate(plan['passes']):
        out = rdir / f'{a["date"]}.npz'
        chips = [(sid, role, c, r) for sid, role, c, r, _, _ in need.get(k, [])]
        if out.exists():
            have = set(np.load(out)['keys'].tolist())
            if all(f'{s}|{r}' in have for s, r, _, _ in chips):
                continue
        jobs.append((a, chips, out, a['local_tif'] is None))
    log(f'remote: {len(jobs)} granules to read (workers {args.workers})')
    with ProcessPoolExecutor(args.workers) as ex:
        futs = {}
        for a, chips, out, wb in jobs:
            check_disk(REPO, args.min_free_gb)
            futs[ex.submit(remote_granule, a, G, chips, out, wb, 6, log_path)] = a['date']
        for fu in as_completed(futs):
            r = fu.result()
            log(f'  {r["date"]}: {"ok" if r["ok"] else "FAILED"} {r["msg"]}')
    missing = [a['date'] for a in plan['passes'] if not (rdir / f'{a["date"]}.npz').exists()]
    if missing:
        raise SystemExit(f'remote stage incomplete: {missing}')


# ----------------------------------------------------------------- extract --

def basic_stats(v):
    """mean, median, std (population) of a 1-D array; None if empty."""
    if v.size == 0:
        return None, None, None
    return float(v.mean()), float(np.median(v)), float(v.std())


def stats_block(hh, hv, valid, exc, n_total):
    """Stats for HH and HV (linear and dB) over valid pixels; n_total = pixels in the area (for valid_frac).
    exc may be None (exception mask not available for the pass)."""
    out = {}
    nv = int(valid.sum())
    out['n_pixels'] = int(n_total)
    out['valid_frac'] = r6(nv / n_total if n_total else np.nan, 4)
    out['exc_frac'] = r6(float((exc[valid] != 0).mean()) if nv and exc is not None else np.nan, 4)
    for name, a in (('hh', hh), ('hv', hv)):
        v = a[valid].astype(np.float64)
        m, md, sd = basic_stats(v)
        out[f'{name}_lin_mean'], out[f'{name}_lin_median'], out[f'{name}_lin_std'] = r6(m, 7), r6(md, 7), r6(sd, 7)
        m, md, sd = basic_stats(10 * np.log10(v)) if v.size else (None, None, None)
        out[f'{name}_db_mean'], out[f'{name}_db_median'], out[f'{name}_db_std'] = r6(m, 3), r6(md, 3), r6(sd, 3)
    return out


def padded(a, r0, r1, c0, c1, fill):
    H, W = a.shape
    out = np.full((r1 - r0, c1 - c0), fill, dtype=a.dtype)
    ra, rb, ca, cb = max(r0, 0), min(r1, H), max(c0, 0), min(c1, W)
    if ra < rb and ca < cb:
        out[ra - r0:rb - r0, ca - c0:cb - c0] = a[ra:rb, ca:cb]
    return out


HIST_LO, HIST_HI, HIST_STEP = -80.0, 60.0, 0.001     # dB histogram for the district medians


def hist_median(h):
    c = np.cumsum(h)
    if c[-1] == 0:
        return np.nan
    i = int(np.searchsorted(c, c[-1] / 2.0))
    return HIST_LO + (i + 0.5) * HIST_STEP


def inbox_rows(G, r0, h, inv, cache_dir):
    """Pixels of rows r0..r0+h whose centre is inside the lon/lat district bbox; cached as packed bits."""
    f = Path(cache_dir) / f'inbox_{r0}_{h}.npy'
    if f.exists():
        return np.unpackbits(np.load(f), axis=1, count=G['w']).astype(bool)
    W_, S_, E_, N_ = DISTRICT_BBOX
    cc = np.arange(G['w']); rr = np.arange(r0, r0 + h)
    X, Y = np.meshgrid(G['x0'] + (cc + 0.5) * PX, G['y0'] - (rr + 0.5) * PX)
    lo, la = inv.transform(X, Y)
    m = (lo >= W_) & (lo <= E_) & (la >= S_) & (la <= N_)
    f.parent.mkdir(parents=True, exist_ok=True)
    np.save(f, np.packbits(m, axis=1))
    return m


def district_stats(src, G, exc, block=512, cache_dir=None):
    """Whole-district stats for one pass, read in row blocks (low memory). Means and std are exact (float64
    sums); medians come from a 0.001 dB histogram (linear median = 10^(dB median / 10))."""
    from pyproj import Transformer
    from rasterio.windows import Window
    inv = Transformer.from_crs(32614, 4326, always_xy=True)
    W_, S_, E_, N_ = DISTRICT_BBOX
    nb = int(round((HIST_HI - HIST_LO) / HIST_STEP))
    acc = {p: dict(h=np.zeros(nb, np.int64), s=0.0, s2=0.0, d=0.0, d2=0.0) for p in ('hh', 'hv')}
    nl_h = np.zeros(10001, np.int64)                 # looks histogram, 0.01 steps
    n_in = n_valid = n_exc = n_exc2 = 0
    for r0 in range(0, G['h'], block):
        h = min(block, G['h'] - r0)
        hh, hv, mk, nl = src.read((1, 2, 3, 4), window=Window(0, r0, G['w'], h))
        inbox = inbox_rows(G, r0, h, inv, cache_dir)
        v = inbox & (mk >= 1) & (mk <= 254) & np.isfinite(hh) & np.isfinite(hv) & (hh > 0) & (hv > 0)
        n_in += int(inbox.sum()); n_valid += int(v.sum())
        if exc is not None:
            e = exc[r0:r0 + h][v]
            n_exc += int((e != 0).sum()); n_exc2 += int(((e & 2) != 0).sum())
        for p, a in (('hh', hh), ('hv', hv)):
            x = a[v].astype(np.float64)
            db = 10 * np.log10(x)
            A = acc[p]
            A['s'] += x.sum(); A['s2'] += (x * x).sum(); A['d'] += db.sum(); A['d2'] += (db * db).sum()
            idx = np.clip(((db - HIST_LO) / HIST_STEP).astype(np.int64), 0, nb - 1)
            A['h'] += np.bincount(idx, minlength=nb)
        nl_h += np.bincount(np.clip((nl[v] * 100).astype(np.int64), 0, 10000), minlength=10001)
    out = dict(n_pixels=n_in, valid_frac=r6(n_valid / n_in, 4),
               exc_frac=r6(n_exc / n_valid, 4) if exc is not None and n_valid else None)
    for p in ('hh', 'hv'):
        A = acc[p]; n = n_valid
        m = A['s'] / n; md = hist_median(A['h'])
        out[f'{p}_lin_mean'] = r6(m, 7); out[f'{p}_lin_median'] = r6(10 ** (md / 10), 7)
        out[f'{p}_lin_std'] = r6(math.sqrt(max(A['s2'] / n - m * m, 0)), 7)
        dm = A['d'] / n
        out[f'{p}_db_mean'] = r6(dm, 3); out[f'{p}_db_median'] = r6(md, 3)
        out[f'{p}_db_std'] = r6(math.sqrt(max(A['d2'] / n - dm * dm, 0)), 3)
    out['exc_code2_frac'] = r6(n_exc2 / n_valid, 4) if exc is not None and n_valid else None
    c = np.cumsum(nl_h)
    out['looks_median'] = r6(int(np.searchsorted(c, c[-1] / 2.0)) / 100.0, 3)
    return out


def extract_pass(k, acq, G, items, work):
    """One pass: district stats (row blocks) + per-sample chips and circle stats (windowed reads)."""
    import rasterio
    from rasterio.windows import Window
    rp = Path(work) / 'remote' / f'{acq["date"]}.npz'
    has_remote = rp.exists()
    if has_remote:
        rem = np.load(rp)
        exc = rem['exc']
        rtc = dict(zip(rem['keys'].tolist(), rem['rtc']))
    else:                                            # exception mask / RTC not read for this pass
        exc, rtc = None, {}
    if not acq['local_tif']:
        raise SystemExit(f'{acq["date"]}: no local district GeoTIFF')
    with rasterio.Env(GDAL_CACHEMAX=128 * 2 ** 20), rasterio.open(acq['local_tif']) as src:
        district = district_stats(src, G, exc, cache_dir=Path(work) / 'inbox')
        district['mask_valid_frac'] = district['valid_frac']
        district['rtc_chip_median'] = r6(float(np.nanmedian(np.stack(list(rtc.values())))), 4) if rtc else None
        district['exc_available'] = has_remote
        R = int(max(RADII) / PX) + 2
        n = 2 * R + 1
        off = np.arange(n)
        chips, keys, cstats = [], [], {}
        for sid, role, col0, row0, fc, fr in sorted(items, key=lambda t: (t[3] // 512, t[2] // 512, t[3], t[2])):
            rc, cc0 = int(fr), int(fc)
            a0, b0 = rc - R, cc0 - R
            w = src.read((1, 2, 3, 4), window=Window(b0, a0, n, n), boundless=True, fill_value=np.nan)
            whh, whv, wmk, wnl = w
            wva = (wmk >= 1) & (wmk <= 254) & np.isfinite(whh) & np.isfinite(whv) & (whh > 0) & (whv > 0)
            wex = padded(exc, a0, a0 + n, b0, b0 + n, 0) if exc is not None else None
            ch = np.full((len(BANDS), CHIP, CHIP), np.nan, np.float32)
            sr, sc = row0 - a0, col0 - b0           # chip inside the window
            sl = (slice(sr, sr + CHIP), slice(sc, sc + CHIP))
            ch[0], ch[1], ch[2], ch[3] = whh[sl], whv[sl], wmk[sl], wnl[sl]
            if exc is not None:
                ch[4] = wex[sl]
            if f'{sid}|{role}' in rtc:
                ch[5] = rtc[f'{sid}|{role}']
            chips.append(ch); keys.append(f'{sid}|{role}')
            d = np.hypot((b0 + off + 0.5 - fc)[None, :], (a0 + off + 0.5 - fr)[:, None]) * PX
            st = {}
            for r in RADII:
                sel = d <= r
                st[str(r)] = stats_block(whh[sel], whv[sel], wva[sel], wex[sel] if wex is not None else None, int(sel.sum()))
            cv = wva[sl]
            st['chip'] = dict(valid_frac=r6(float(cv.mean()), 4),
                              exc_frac=r6(float((wex[sl][cv] != 0).mean()), 4) if exc is not None and cv.any() else None)
            cstats[f'{sid}|{role}'] = st
    np.savez_compressed(Path(work) / 'extract' / f'{acq["date"]}.npz',
                        chips=np.stack(chips) if chips else np.zeros((0, len(BANDS), CHIP, CHIP), np.float32), keys=np.array(keys))
    (Path(work) / 'extract' / f'{acq["date"]}.json').write_text(
        json.dumps(dict(district=district, circles=cstats, has_remote=has_remote)), encoding='utf-8')
    return acq['date'], len(items), district


def stage_extract(args):
    plan = load_plan(args)
    need = needs_by_pass(plan)
    edir = Path(args.work) / 'extract'; edir.mkdir(parents=True, exist_ok=True)
    jobs = []
    for k, a in enumerate(plan['passes']):
        items = need.get(k, [])
        j = edir / f'{a["date"]}.json'
        if j.exists() and (edir / f'{a["date"]}.npz').exists():
            have = set(np.load(edir / f'{a["date"]}.npz')['keys'].tolist())
            stale = (not json.loads(j.read_text(encoding='utf-8')).get('has_remote', False)
                     and (Path(args.work) / 'remote' / f'{a["date"]}.npz').exists())
            if all(f'{s}|{r}' in have for s, r, *_ in items) and not stale:
                continue
        jobs.append((k, a, items))
    log(f'extract: {len(jobs)} passes (workers {args.extract_workers})')
    with ProcessPoolExecutor(args.extract_workers) as ex:
        futs = {}
        for k, a, items in jobs:
            check_disk(REPO, args.min_free_gb)
            futs[ex.submit(extract_pass, k, a, plan['grid'], items, args.work)] = a['date']
        for fu in as_completed(futs):
            date, nitems, d = fu.result()
            log(f'  {date}: {nitems} chips; district HH median {d["hh_db_median"]} dB, HV {d["hv_db_median"]} dB, '
                f'valid {d["valid_frac"]}, exc {d["exc_frac"]} (code 2 {d["exc_code2_frac"]})'
                + ('' if d['exc_available'] else ' [exception mask / RTC not available]'))


# ---------------------------------------------------------------- assemble --

INDEX_COLS = ['sample_id', 'label', 'split', 'group_id', 'positive_id', 'cause', 'stratum_cause', 'leak_objectid',
              'repair_utc', 'days_pass_to_repair', 'leak_pipe_size_in', 'loss_gpm', 'repair_type', 'zone', 'zone_reported',
              'geo_cell', 'quarter', 'lon', 'lat', 'utm_x', 'utm_y', 'nearest_pipe_id', 'pipe_size', 'pipe_diameter_in',
              'pipe_material', 'dist_to_pipe_m', 'nearest_leak_m', 'nearest_leak_id', 'nearest_leak_days',
              'nearest_leak_pm60d_m', 't0_date', 't0_utc', 'tm2_date', 'tm1_date', 'tp1_date', 'avail_tm2', 'avail_tm1',
              'avail_t0', 'avail_tp1', 'dt_tm2_days', 'dt_tm1_days', 'dt_tp1_days', 'chip_x0', 'chip_y0', 'point_col',
              'point_row', 't0_chip_valid_frac', 't0_chip_exc_frac', 't0_hh_db_median_500m', 't0_hv_db_median_500m']

PASS_COLS = ['pass_idx', 'date', 'start_utc', 'local_time_cdt_cst', 'granule', 'crid', 'maturity', 'counter', 'n_chips',
             'n_pixels', 'valid_frac', 'exc_frac', 'exc_code2_frac', 'looks_median', 'rtc_chip_median',
             'hh_lin_mean', 'hh_lin_median', 'hh_lin_std', 'hh_db_mean', 'hh_db_median', 'hh_db_std',
             'hv_lin_mean', 'hv_lin_median', 'hv_lin_std', 'hv_db_mean', 'hv_db_median', 'hv_db_std']


def fmt(v):
    if v is None:
        return ''
    if isinstance(v, float):
        return '' if not np.isfinite(v) else repr(round(v, 6))
    return str(v)


def stage_assemble(args):
    from zoneinfo import ZoneInfo
    plan = load_plan(args)
    passes = plan['passes']
    n = len(passes)
    G = plan['grid']
    out = Path(args.out)
    check_disk(REPO, args.min_free_gb)
    ex = {}
    for a in passes:
        d = np.load(Path(args.work) / 'extract' / f'{a["date"]}.npz')
        js = json.loads((Path(args.work) / 'extract' / f'{a["date"]}.json').read_text(encoding='utf-8'))
        ex[a['date']] = (dict(zip(d['keys'].tolist(), d['chips'])), js)
    # passes.csv
    out.mkdir(parents=True, exist_ok=True)
    need = needs_by_pass(plan)
    with open(out / 'passes.csv', 'w', newline='', encoding='utf-8') as fh:
        w = csv.writer(fh); w.writerow(PASS_COLS)
        for k, a in enumerate(passes):
            d = ex[a['date']][1]['district']
            loc = datetime.fromisoformat(a['start_utc'].replace('Z', '+00:00')).astimezone(ZoneInfo('America/Chicago'))
            row = dict(pass_idx=k, date=a['date'], start_utc=a['start_utc'], local_time_cdt_cst=loc.strftime('%Y-%m-%d %H:%M %Z'),
                       granule=a['granule'], crid=a['crid'], maturity=a['maturity'], counter=a['counter'],
                       n_chips=len(need.get(k, [])), **d)
            w.writerow([fmt(row.get(c)) for c in PASS_COLS])
    rows = {'train': [], 'test': []}
    for s in plan['samples']:
        i = s['pass_idx']
        widx = window_idx(i, n)
        sar = np.full((len(ROLES), len(BANDS), CHIP, CHIP), np.nan, np.float32)
        avail = np.zeros(len(ROLES), bool)
        pmeta = []
        for j, (role, k) in enumerate(zip(ROLES, widx)):
            if k is None:
                pmeta.append(dict(role=role, available=False))
                continue
            a = passes[k]
            chips, js = ex[a['date']]
            sar[j] = chips[f'{s["sample_id"]}|{role}']
            avail[j] = True
            pmeta.append(dict(role=role, available=True, pass_idx=k, date=a['date'], start_utc=a['start_utc'],
                              granule=a['granule'], crid=a['crid'],
                              days_from_t0=round((a['t'] - passes[i]['t']) / DAY_MS, 3),
                              chip=js['circles'][f'{s["sample_id"]}|{role}']['chip'],
                              circles={r: js['circles'][f'{s["sample_id"]}|{role}'][r] for r in map(str, RADII)},
                              district=js['district']))
        x0 = G['x0'] + s['col0'] * PX; y0 = G['y0'] - s['row0'] * PX
        pcol, prow = s['fc'] - s['col0'], s['fr'] - s['row0']
        sdir = out / s['split'] / s['sample_id']
        sdir.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(sdir / 'sar.npz', sar=sar, available=avail, pass_names=np.array(ROLES), band_names=np.array(BANDS),
                            pass_dates=np.array([p.get('date', '') for p in pmeta]))
        t0p = pmeta[2]
        idx = dict(sample_id=s['sample_id'], label=s['label'], split=s['split'], group_id=s['group_id'], positive_id=s['pos_id'],
                   cause=s.get('cause', '') if s['label'] == 1 else '', stratum_cause=s['stratum_cause'],
                   leak_objectid=s.get('leak_objectid'), repair_utc=s.get('repair_utc'),
                   days_pass_to_repair=s.get('days_pass_to_repair'), leak_pipe_size_in=s.get('leak_pipe_size_in'),
                   loss_gpm=s.get('loss_gpm'), repair_type=s.get('repair_type'), zone=s['zone'], zone_reported=s.get('zone_reported'),
                   geo_cell=s['geo_cell'], quarter=s['quarter'], lon=round(s['lon'], 6), lat=round(s['lat'], 6),
                   utm_x=round(s['x'], 2), utm_y=round(s['y'], 2), nearest_pipe_id=s['nearest_pipe_id'], pipe_size=s['pipe_size'],
                   pipe_diameter_in=s['pipe_diameter_in'], pipe_material=s['pipe_material'], dist_to_pipe_m=s['dist_to_pipe_m'],
                   nearest_leak_m=s['nearest_leak_m'], nearest_leak_id=s['nearest_leak_id'], nearest_leak_days=s['nearest_leak_days'],
                   nearest_leak_pm60d_m=s['nearest_leak_pm60d_m'], t0_date=passes[i]['date'], t0_utc=passes[i]['start_utc'],
                   tm2_date=pmeta[0].get('date', ''), tm1_date=pmeta[1].get('date', ''), tp1_date=pmeta[3].get('date', ''),
                   avail_tm2=int(avail[0]), avail_tm1=int(avail[1]), avail_t0=int(avail[2]), avail_tp1=int(avail[3]),
                   dt_tm2_days=pmeta[0].get('days_from_t0'), dt_tm1_days=pmeta[1].get('days_from_t0'),
                   dt_tp1_days=pmeta[3].get('days_from_t0'), chip_x0=x0, chip_y0=y0, point_col=round(pcol, 3),
                   point_row=round(prow, 3), t0_chip_valid_frac=t0p['chip']['valid_frac'], t0_chip_exc_frac=t0p['chip']['exc_frac'],
                   t0_hh_db_median_500m=t0p['circles']['500']['hh_db_median'], t0_hv_db_median_500m=t0p['circles']['500']['hv_db_median'])
        meta = dict(sample=idx,
                    chip=dict(crs='EPSG:32614', x0=x0, y0=y0, pixel_size=PX, width=CHIP, height=CHIP,
                              geotransform=[x0, PX, 0.0, y0, 0.0, -PX],
                              point_col=round(pcol, 4), point_row=round(prow, 4),
                              note='pixel (row r, col c) covers x0+10c..x0+10(c+1), y0-10r..y0-10(r+1); '
                                   'point_col/row are fractional, pixel centres at c+0.5 / r+0.5'),
                    passes=pmeta, bands=list(BANDS), pass_roles=list(ROLES))
        (sdir / 'meta.json').write_text(json.dumps(meta, indent=1), encoding='utf-8')
        rows[s['split']].append(idx)
    for sp, rr in rows.items():
        rr.sort(key=lambda r: (r['positive_id'], -r['label'], r['sample_id']))
        with open(out / sp / 'index.csv', 'w', newline='', encoding='utf-8') as fh:
            w = csv.writer(fh); w.writerow(INDEX_COLS)
            for r in rr:
                w.writerow([fmt(r.get(c)) for c in INDEX_COLS])
    # summary
    allr = rows['train'] + rows['test']
    summ = dict(seed=plan['seed'], built_utc=datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
                counts={}, excluded=plan['excluded'], neg_rejections=plan['neg_rejections'], split_score=plan['split_score'])
    for key in ('stratum_cause', 'zone', 'quarter', 'geo_cell'):
        c = defaultdict(lambda: defaultdict(int))
        for r in allr:
            c[f'{r["split"]}_{"pos" if r["label"] == 1 else "neg"}'][r[key] or 'none'] += 1
        summ['counts'][key] = {k: dict(sorted(v.items())) for k, v in sorted(c.items())}
    summ['groups'] = dict(n=len(plan['groups']), size_hist=dict(Counter(len(g['members']) for g in plan['groups'])))
    (out / 'summary.json').write_text(json.dumps(summ, indent=1), encoding='utf-8')
    log(f'assembled {len(allr)} samples: train {len(rows["train"])}, test {len(rows["test"])}')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--stage', default='all', choices=['all', 'plan', 'remote', 'extract', 'assemble'])
    ap.add_argument('--seed', type=int, default=SEED)
    ap.add_argument('--work', default=str(DEFAULT_WORK))
    ap.add_argument('--out', default=str(DEFAULT_OUT))
    ap.add_argument('--workers', type=int, default=3, help='parallel granules in the remote stage')
    ap.add_argument('--extract-workers', type=int, default=1)
    ap.add_argument('--min-free-gb', type=float, default=8.0)
    ap.add_argument('--replan', action='store_true', help='rebuild plan.json even if it exists')
    args = ap.parse_args()
    check_disk(REPO, args.min_free_gb)
    t = time.time()
    if args.stage in ('all', 'plan'):
        if args.replan or args.stage == 'plan' or not (Path(args.work) / 'plan.json').exists():
            stage_plan(args)
    if args.stage in ('all', 'remote'):
        stage_remote(args)
    if args.stage in ('all', 'extract'):
        stage_extract(args)
    if args.stage in ('all', 'assemble'):
        stage_assemble(args)
    log(f'done in {(time.time() - t) / 60:.1f} min')


if __name__ == '__main__':
    main()
