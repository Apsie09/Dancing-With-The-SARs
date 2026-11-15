"""Cut small NISAR GCOV chips around each Coryell leak, before and after the repair.

For every leak repaired in the NISAR window (ObjectId 1611 dropped, all causes),
on stack 041_D_073 (track 41 descending, frame 73, CRID P05023):

    before   = last acquisition at or before the repair time
    baseline = the acquisition before `before`
    after    = first acquisition after the repair time

Day offsets are elapsed time, in days, between the acquisition start time (UTC,
from the granule name, about 01:18 UTC = 20:18 CDT / 19:18 CST the evening
before the UTC date) and the repair time (`datetime`, UTC). In the manifest
`days` = (acquisition - repair) / 24 h, so it is negative for baseline/before
and positive for after.

Chips are read remotely (h5py over HTTP range requests, no full download). Each
granule is opened once and every chip needed from it is read in one pass.
Leaks within ~200 m of each other share one chip footprint ("site"), centred
on the site's seed leak, so a leak's three chips are pixel-aligned.

Steps
  1. acquisitions -> data/coryell/nisar/acquisitions_041D073.json
  2. fetch        -> raw float chips (HHHH, HVHV linear gamma-0, mask) as .npz in --cache-dir
  3. render       -> data/coryell/nisar/chips/<site>_<yyyymmdd>.png and leak_chips.json

The fetch step is resumable (chips already in the cache are skipped). Render
re-runs from the cache in a few seconds, with no network.

PNG encoding (UTM 14N grid, north-up, 10 m pixels, 120 x 120 px = 1.2 km):
    R = HH dB after a 3x3 boxcar on linear power, linear over -25..0 dB -> 0..255
    G = HV dB, same filter, linear over -32..-7 dB -> 0..255
    B = 255 where the pixel is valid (mask 1..254 and finite), else 0
The browser decodes R/G back to dB and colours them (false colour, HH, HV).

Usage
    python scripts/make_leak_chips.py --cache-dir <dir> [--workers 6] [--granules-csv gcov_granules.csv]
    python scripts/make_leak_chips.py --cache-dir <dir> --render-only
    python scripts/make_leak_chips.py --cache-dir <dir> --dry-run

Needs numpy, h5py, fsspec (+aiohttp), requests, pyproj. Earthdata login via ~/.netrc.
"""
import argparse
import csv
import json
import math
import os
import re
import struct
import sys
import time
import zlib
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
DATA = REPO / 'data' / 'coryell'
OUT = DATA / 'nisar'
STACK = '041_D_073'
CRID = 'P05023'
FIRST_DATE, LAST_DATE = '2025-12-31', '2026-10-15'    # the single-CRID P05023 run
NISAR_START_MS = int(datetime(2025, 10, 17, tzinfo=timezone.utc).timestamp() * 1000)
DROP_IDS = {1611}
CHIP = 120          # px (1.2 km at 10 m)
PAD = 1             # extra px read on each side for the 3x3 boxcar
SITE_RADIUS = 200.0 # m: leaks this close to a site seed share its chip footprint
R_IN, R_ANN0, R_ANN1 = 30.0, 100.0, 300.0
HH_RANGE, HV_RANGE = (-25.0, 0.0), (-32.0, -7.0)
GRID = '/science/LSAR/GCOV/grids/frequencyA'
DAY_MS = 86400000

CAUSE = {'Naturally_Occurred': 'natural', 'Construction_Maintenance_Induce': 'construction', 'Other': 'other'}


def log(msg, fh=None):
    line = f'[{datetime.now().strftime("%H:%M:%S")}] {msg}'
    print(line, flush=True)


# ---------------------------------------------------------------- parsing --

def parse_size(txt):
    if not txt:
        return None
    nums = [float(n) for n in re.findall(r'\d*\.?\d+', txt) if float(n) > 0]
    return max(nums) if nums else None


def parse_gpm(txt):
    """Same rules as parseGpm() in viz/leaks.js."""
    if not txt:
        return None
    t = txt.replace('�', '"')
    wu = [float(m.group(1)) / (60 if m.group(2).lower() == 'gph' else 1)
          for m in re.finditer(r'(\d*\.?\d+)\s*(gpm|gpn|gallons?|gph)', t, re.I)]
    if wu:
        return max(wu)
    allnums = [float(n) for n in re.findall(r'\d*\.?\d+', t)]
    if not allnums:
        return None
    return max(allnums) if re.search(r'escalat|/', t, re.I) else allnums[0]


def load_leaks():
    fc = json.loads((DATA / 'leak_survey.geojson').read_text(encoding='utf-8'))
    leaks = []
    for f in fc['features']:
        p = f['properties']
        if p['ObjectId'] in DROP_IDS or not f.get('geometry') or p.get('datetime') is None:
            continue
        if p['datetime'] < NISAR_START_MS:
            continue
        lon, lat = f['geometry']['coordinates'][:2]
        leaks.append(dict(id=p['ObjectId'], t=p['datetime'], lon=lon, lat=lat,
                          cause=CAUSE.get(p.get('cause_of_leak'), 'other'),
                          size=parse_size(p.get('line_size')), gpm=parse_gpm(p.get('approximate_water_loss_gpm'))))
    leaks.sort(key=lambda l: l['t'])
    return leaks


# ----------------------------------------------------------- acquisitions --

def acquisitions_from_csv(path):
    rows = [r for r in csv.DictReader(open(path, encoding='utf-8'))
            if r['stack'] == STACK and r['crid'] == CRID and FIRST_DATE <= r['date_utc'] <= LAST_DATE]
    best = {}
    for r in rows:  # where _001 and _002 exist, keep the highest counter
        if r['date_utc'] not in best or int(r['counter']) > int(best[r['date_utc']]['counter']):
            best[r['date_utc']] = r
    acqs = []
    for d in sorted(best):
        r = best[d]
        st = datetime.fromisoformat(r['start_utc'])
        acqs.append(dict(date=d, start_utc=st.strftime('%Y-%m-%dT%H:%M:%SZ'), t=int(st.timestamp() * 1000),
                         granule=r['name'], crid=r['crid'], maturity=r['maturity'], counter=int(r['counter']),
                         h5_GB=float(r['h5_GB']), url=r['url']))
    return acqs


def acquisitions_from_asf():
    """Query the ASF search API (anonymous) for the stack, if no CSV is given."""
    import requests
    q = dict(dataset='NISAR', processingLevel='GCOV', relativeOrbit=41, frame=73, flightDirection='DESCENDING',
             start=f'{FIRST_DATE}T00:00:00Z', end=f'{LAST_DATE}T23:59:59Z', output='geojson', maxResults=500)
    js = requests.get('https://api.daac.asf.alaska.edu/services/search/param', params=q, timeout=120).json()
    best = {}
    for f in js['features']:
        p = f['properties']
        name = p['sceneName'] if 'sceneName' in p else p['fileID']
        m = re.search(r'_(\d{8})T(\d{6})_\d{8}T\d{6}_(\w\d{5})_\w_\w_\w_(\d{3})', name)
        if not m or m.group(3) != CRID:
            continue
        d = f'{m.group(1)[:4]}-{m.group(1)[4:6]}-{m.group(1)[6:]}'
        cnt = int(m.group(4))
        if d not in best or cnt > best[d][0]:
            best[d] = (cnt, name, p.get('url'), m.group(2))
    acqs = []
    for d in sorted(best):
        cnt, name, url, hms = best[d]
        st = datetime.strptime(d + hms, '%Y-%m-%d%H%M%S').replace(tzinfo=timezone.utc)
        acqs.append(dict(date=d, start_utc=st.strftime('%Y-%m-%dT%H:%M:%SZ'), t=int(st.timestamp() * 1000),
                         granule=name, crid=CRID, maturity='PROVISIONAL', counter=cnt, url=url))
    return acqs


# ------------------------------------------------------------------- plan --

def make_plan(leaks, acqs):
    from pyproj import Transformer
    tr = Transformer.from_crs(4326, 32614, always_xy=True)
    for l in leaks:
        l['x'], l['y'] = tr.transform(l['lon'], l['lat'])
    # Roles
    ts = [a['t'] for a in acqs]
    for l in leaks:
        i = int(np.searchsorted(ts, l['t'], side='right')) - 1   # last acq with t <= repair
        l['roles'] = {}
        if i >= 0:
            l['roles']['before'] = i
            if i >= 1:
                l['roles']['baseline'] = i - 1
        if i + 1 < len(acqs):
            l['roles']['after'] = i + 1
    # Sites: greedy, densest leak first; the seed is the chip centre.
    xy = np.array([[l['x'], l['y']] for l in leaks])
    d = np.hypot(xy[:, None, 0] - xy[None, :, 0], xy[:, None, 1] - xy[None, :, 1])
    near = (d <= SITE_RADIUS).sum(1)
    unassigned = set(range(len(leaks)))
    sites = []
    for i in sorted(range(len(leaks)), key=lambda k: (-near[k], leaks[k]['t'])):
        if i not in unassigned:
            continue
        members = [j for j in unassigned if d[i, j] <= SITE_RADIUS]
        for j in members:
            unassigned.discard(j)
        sid = f"s{leaks[i]['id']}"
        sites.append(dict(id=sid, seed=leaks[i]['id'], x=leaks[i]['x'], y=leaks[i]['y'],
                          members=[leaks[j]['id'] for j in members]))
        for j in members:
            leaks[j]['site'] = sid
    # Chips needed: (site, acquisition index)
    site_by_id = {s['id']: s for s in sites}
    need = defaultdict(set)    # acq index -> set of site ids
    for l in leaks:
        for r, ai in l['roles'].items():
            need[ai].add(l['site'])
    return sites, site_by_id, need


def chip_name(site_id, date):
    return f"{site_id}_{date.replace('-', '')}"


# ------------------------------------------------------------------ fetch --

def fetch_granule(acq, chips, cache_dir, log_path):
    """Open one granule remotely and read every chip window it needs. Runs in a worker process."""
    import aiohttp
    import fsspec
    import h5py
    import requests

    def wlog(msg):
        with open(log_path, 'a', encoding='utf-8') as fh:
            fh.write(f'[{datetime.now().strftime("%H:%M:%S")}] [{acq["date"]}] {msg}\n')

    t0 = time.time()
    last_err = None
    for attempt in range(3):
        try:
            done = 0
            sess = requests.Session()
            r = sess.get(acq['url'], headers={'Range': 'bytes=0-0'}, timeout=120)
            r.raise_for_status()
            signed = r.url
            r.close()
            # Without a timeout a stalled range request can hang for ~30 min.
            fs = fsspec.filesystem('http', skip_instance_cache=True,
                                   client_kwargs=dict(timeout=aiohttp.ClientTimeout(total=180, sock_read=90)))
            f = fs.open(signed, block_size=2 ** 20, cache_type='blockcache', cache_options=dict(maxblocks=128))
            h = h5py.File(f, 'r', rdcc_nbytes=768 * 2 ** 20, rdcc_nslots=20011)
            g = h[GRID]
            x = g['xCoordinates'][:]
            y = g['yCoordinates'][:]
            dx = float(g['xCoordinateSpacing'][()]); dy = float(g['yCoordinateSpacing'][()])
            epsg = int(g['projection'][()])
            assert epsg == 32614, epsg
            HH, HV, MK = g['HHHH'], g['HVHV'], g['mask']
            # Sort windows by chunk position so neighbouring chips reuse cached chunks.
            todo = []
            for name, cx, cy in chips:
                ic = int(round((cx - x[0]) / dx)); ir = int(round((cy - y[0]) / dy))
                c0, r0 = ic - CHIP // 2, ir - CHIP // 2
                todo.append((r0 // 512, c0 // 512, name, r0, c0))
            todo.sort()
            for _, _, name, r0, c0 in todo:
                out = cache_dir / f'{name}.npz'
                if out.exists():
                    continue
                sl = (slice(r0 - PAD, r0 + CHIP + PAD), slice(c0 - PAD, c0 + CHIP + PAD))
                hh = HH[sl]; hv = HV[sl]; mk = MK[sl]
                tmp = cache_dir / f'{name}.tmp.npz'
                np.savez_compressed(tmp, hh=hh.astype(np.float32), hv=hv.astype(np.float32), mask=mk,
                                    x_left=x[c0] - dx / 2, y_top=y[r0] - dy / 2, dx=dx, dy=dy,
                                    r0=r0, c0=c0, granule=acq['granule'])
                os.replace(tmp, out)
                done += 1
            c = f.cache
            stats = dict(date=acq['date'], chips=len(chips), new=done, seconds=round(time.time() - t0, 1),
                         blocks_fetched=getattr(c, 'miss_count', None),
                         mb_fetched=round(getattr(c, 'miss_count', 0) * 2 ** 20 / 1e6, 1),
                         x0=float(x[0]), y0=float(y[0]), attempt=attempt + 1)
            h.close(); f.close()
            wlog(f'done {done} new chips of {len(chips)} in {stats["seconds"]} s, ~{stats["mb_fetched"]} MB fetched, grid origin {x[0]:.1f},{y[0]:.1f}')
            return stats
        except Exception as e:  # noqa: BLE001 - retry with a fresh signed URL
            last_err = repr(e)
            wlog(f'attempt {attempt + 1} failed: {last_err[:300]}')
            time.sleep(5 * (attempt + 1))
    return dict(date=acq['date'], error=last_err, seconds=round(time.time() - t0, 1))


# ----------------------------------------------------------------- render --

def boxcar3(a):
    valid = np.isfinite(a)
    v = np.where(valid, a, 0.0).astype(np.float64)
    n = valid.astype(np.float64)

    def s3(z):
        c = np.pad(z, 1).cumsum(0).cumsum(1)
        c = np.pad(c, ((1, 0), (1, 0)))
        return c[3:, 3:] - c[:-3, 3:] - c[3:, :-3] + c[:-3, :-3]

    s, cnt = s3(v), s3(n)
    out = np.where(cnt > 0, s / np.maximum(cnt, 1), np.nan)
    out[~valid] = np.nan
    return out


def write_png(path, rgb):
    """Minimal RGB PNG writer with per-row adaptive filtering (no Pillow needed)."""
    h, w, _ = rgb.shape
    a = rgb.astype(np.int16)
    left = np.zeros_like(a); left[:, 1:] = a[:, :-1]
    up = np.zeros_like(a); up[1:] = a[:-1]
    ul = np.zeros_like(a); ul[1:, 1:] = a[:-1, :-1]
    p = left + up - ul
    pa, pb, pc = np.abs(p - left), np.abs(p - up), np.abs(p - ul)
    paeth = np.where((pa <= pb) & (pa <= pc), left, np.where(pb <= pc, up, ul))
    cands = [a, a - left, a - up, a - ((left + up) // 2), a - paeth]
    cands = [(c % 256).astype(np.uint8) for c in cands]
    cost = np.stack([np.abs(c.astype(np.int8).astype(np.int16)).reshape(h, -1).sum(1) for c in cands])
    best = cost.argmin(0)
    raw = b''.join(bytes([int(best[i])]) + cands[best[i]][i].tobytes() for i in range(h))

    def chunk(t, d):
        return struct.pack('>I', len(d)) + t + d + struct.pack('>I', zlib.crc32(t + d) & 0xffffffff)

    png = b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0)) + \
        chunk(b'IDAT', zlib.compress(raw, 9)) + chunk(b'IEND', b'')
    path.write_bytes(png)


def to_db(a):
    with np.errstate(divide='ignore', invalid='ignore'):
        return 10 * np.log10(a)


def quant(db, lo, hi):
    q = np.round((db - lo) / (hi - lo) * 255)
    return np.where(np.isfinite(q), np.clip(q, 0, 255), 0).astype(np.uint8)


def chip_stats(hh, hv, valid, col, row):
    """Mean linear power in a 30 m disc vs a 100-300 m annulus around (col,row) (fractional px from top-left)."""
    yy, xx = np.mgrid[0:CHIP, 0:CHIP]
    r = np.hypot(xx + 0.5 - col, yy + 0.5 - row) * 10.0
    out = {}
    for key, a in (('hh', hh), ('hv', hv)):
        for part, sel in (('in', r <= R_IN), ('out', (r >= R_ANN0) & (r <= R_ANN1))):
            m = sel & valid & np.isfinite(a) & (a > 0)
            out[f'{key}_{part}'] = round(float(10 * np.log10(a[m].mean())), 2) if m.sum() >= 5 else None
            out[f'n_{part}'] = int(m.sum())
    for key in ('hh', 'hv'):
        i, o = out[f'{key}_in'], out[f'{key}_out']
        out[f'{key}_contrast'] = round(i - o, 2) if i is not None and o is not None else None
    return out


def render(leaks, sites, site_by_id, need, acqs, cache_dir):
    from pyproj import Transformer
    inv = Transformer.from_crs(32614, 4326, always_xy=True)
    chip_dir = OUT / 'chips'
    chip_dir.mkdir(parents=True, exist_ok=True)
    chips = {}
    cache = {}
    for ai, sids in sorted(need.items()):
        for sid in sorted(sids):
            name = chip_name(sid, acqs[ai]['date'])
            npz = cache_dir / f'{name}.npz'
            if not npz.exists():
                continue
            z = np.load(npz)
            hh = z['hh'].astype(np.float64); hv = z['hv'].astype(np.float64); mk = z['mask']
            valid_full = (mk >= 1) & (mk <= 254)
            hh[~valid_full | ~np.isfinite(hh) | (hh <= 0)] = np.nan
            hv[~valid_full | ~np.isfinite(hv) | (hv <= 0)] = np.nan
            hhb = boxcar3(hh)[PAD:-PAD, PAD:-PAD]; hvb = boxcar3(hv)[PAD:-PAD, PAD:-PAD]
            hh_c, hv_c = hh[PAD:-PAD, PAD:-PAD], hv[PAD:-PAD, PAD:-PAD]
            valid = valid_full[PAD:-PAD, PAD:-PAD] & np.isfinite(hhb) & np.isfinite(hvb)
            rgb = np.dstack([quant(to_db(hhb), *HH_RANGE), quant(to_db(hvb), *HV_RANGE),
                             np.where(valid, 255, 0).astype(np.uint8)])
            rgb[~valid, 0] = 0; rgb[~valid, 1] = 0
            write_png(chip_dir / f'{name}.png', rgb)
            xl, yt, dx, dy = float(z['x_left']), float(z['y_top']), float(z['dx']), float(z['dy'])
            xr, yb = xl + dx * CHIP, yt + dy * CHIP
            corners = [inv.transform(px, py) for px, py in ((xl, yt), (xr, yt), (xr, yb), (xl, yb))]
            chips[name] = dict(file=f'chips/{name}.png', date=acqs[ai]['date'], site=sid,
                               corners=[[round(a, 6), round(b, 6)] for a, b in corners],
                               utm=[round(xl, 1), round(yt, 1)], valid=round(float(valid.mean()), 3))
            cache[name] = (hh_c, hv_c, valid, xl, yt, dx, dy)
    out_leaks, missing = [], defaultdict(list)
    for l in leaks:
        e = dict(id=l['id'], t=l['t'], cause=l['cause'], size=l['size'], gpm=l['gpm'],
                 lon=round(l['lon'], 6), lat=round(l['lat'], 6), site=l['site'], roles={})
        for role in ('baseline', 'before', 'after'):
            ai = l['roles'].get(role)
            if ai is None:
                missing[role].append(l['id'])
                continue
            name = chip_name(l['site'], acqs[ai]['date'])
            rr = dict(date=acqs[ai]['date'], acq=ai, days=round((acqs[ai]['t'] - l['t']) / DAY_MS, 2))
            if name in cache:
                hh_c, hv_c, valid, xl, yt, dx, dy = cache[name]
                col, row = (l['x'] - xl) / dx, (l['y'] - yt) / dy
                rr.update(chip=name, px=[round(col, 2), round(row, 2)], stats=chip_stats(hh_c, hv_c, valid, col, row))
            else:
                rr['chip'] = None
                missing[role + '_chip_not_fetched'].append(l['id'])
            e['roles'][role] = rr
        # Exploratory changes
        ch = {}
        R = e['roles']
        for a, b, key in (('before', 'baseline', 'before_minus_baseline'), ('after', 'before', 'after_minus_before')):
            if R.get(a, {}).get('stats') and R.get(b, {}).get('stats'):
                sa, sb = R[a]['stats'], R[b]['stats']
                ch[key] = {k: (round(sa[k] - sb[k], 2) if sa.get(k) is not None and sb.get(k) is not None else None)
                           for k in ('hh_in', 'hv_in', 'hh_contrast', 'hv_contrast')}
        e['change'] = ch
        out_leaks.append(e)
    manifest = dict(
        description='NISAR GCOV chips around Coryell leak repairs, before and after each repair. Exploratory.',
        stack=STACK, crid=CRID, frequency='A', pixel_m=10, chip_px=CHIP, crs='EPSG:32614',
        convention=('days = (acquisition start UTC - repair datetime UTC) / 24 h; negative = pass before the repair. '
                    'before = last pass at or before the repair, baseline = the pass before that, after = first pass after.'),
        encoding=dict(r=dict(band='HH', unit='dB', range=list(HH_RANGE)), g=dict(band='HV', unit='dB', range=list(HV_RANGE)),
                      b='255 = valid pixel, 0 = invalid/outside', filter='3x3 boxcar on linear gamma-0, then 10*log10',
                      orientation='UTM 14N grid, north-up, row 0 = north edge; corners = [TL, TR, BR, BL] lon/lat'),
        stats=dict(note='EXPLORATORY. Mean linear gamma-0 (no filter) converted to dB: in = within 30 m of the leak, '
                        'out = annulus 100-300 m; contrast = in - out. change = later minus earlier pass.',
                   r_in_m=R_IN, annulus_m=[R_ANN0, R_ANN1]),
        acquisitions=[dict(date=a['date'], start_utc=a['start_utc'], t=a['t']) for a in acqs],
        chips=chips, leaks=out_leaks,
        missing={k: v for k, v in missing.items()},
        generated=datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
    )
    (OUT / 'leak_chips.json').write_text(json.dumps(manifest, separators=(',', ':')), encoding='utf-8')
    return manifest


# ------------------------------------------------------------------- main --

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--cache-dir', required=True, type=Path, help='where raw float chips (.npz) are kept')
    ap.add_argument('--granules-csv', type=Path, help='gcov_granules.csv from the coverage search (else ASF API)')
    ap.add_argument('--workers', type=int, default=6)
    ap.add_argument('--log', type=Path, help='progress log for the worker processes')
    ap.add_argument('--dates', help='comma list of acquisition dates to fetch (default: all with missing chips)')
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--render-only', action='store_true')
    a = ap.parse_args()
    a.cache_dir.mkdir(parents=True, exist_ok=True)
    log_path = a.log or (a.cache_dir / 'fetch.log')
    t0 = time.time()

    acq_path = OUT / 'acquisitions_041D073.json'
    if a.granules_csv:
        acqs = acquisitions_from_csv(a.granules_csv)
    elif acq_path.exists():
        acqs = json.loads(acq_path.read_text(encoding='utf-8'))['acquisitions']
    else:
        acqs = acquisitions_from_asf()
    OUT.mkdir(parents=True, exist_ok=True)
    acq_path.write_text(json.dumps(dict(
        stack=STACK, crid=CRID, maturity='PROVISIONAL', note=(
            'Track 41 descending, frame 73, NISAR L2 GCOV, P05023 run 2025-12-31 to 2026-10-15 (_002 used where _001/_002 exist). '
            'BETA dates (2025-11-01..12-19) and the VALIDATED 2026-10-27 date (P05036) are excluded. No data 2026-07-27..08-10. '
            'start_utc is the acquisition start; about 01:18 UTC = 20:18 CDT (19:18 CST) the evening before the UTC date.'),
        acquisitions=acqs), indent=1), encoding='utf-8')
    log(f'{len(acqs)} acquisitions {acqs[0]["date"]} .. {acqs[-1]["date"]}')

    leaks = load_leaks()
    sites, site_by_id, need = make_plan(leaks, acqs)
    n_pairs = sum(len(l['roles']) for l in leaks)
    n_chips = sum(len(v) for v in need.values())
    log(f'{len(leaks)} leaks, {len(sites)} sites, {n_pairs} leak-role pairs -> {n_chips} chips over {len(need)} granules')
    if a.dry_run:
        for ai in sorted(need):
            print(acqs[ai]['date'], len(need[ai]))
        return

    if not a.render_only:
        jobs = []
        for ai, sids in sorted(need.items()):
            chips = [(chip_name(s, acqs[ai]['date']), site_by_id[s]['x'], site_by_id[s]['y']) for s in sorted(sids)]
            if all((a.cache_dir / f'{c[0]}.npz').exists() for c in chips):
                continue
            if a.dates and acqs[ai]['date'] not in a.dates.split(','):
                continue
            jobs.append((acqs[ai], chips))
        log(f'{len(jobs)} granules to read, {a.workers} workers; log: {log_path}')
        results = []
        with ProcessPoolExecutor(max_workers=a.workers) as ex:
            futs = {ex.submit(fetch_granule, acq, chips, a.cache_dir, str(log_path)): acq['date'] for acq, chips in jobs}
            for fu in as_completed(futs):
                res = fu.result()
                results.append(res)
                log(f'{futs[fu]}: {res}')
        mb = sum(r.get('mb_fetched', 0) or 0 for r in results)
        errs = [r for r in results if 'error' in r]
        log(f'fetch done in {time.time() - t0:.0f} s, ~{mb:.0f} MB fetched, {len(errs)} granule errors')
        (a.cache_dir / 'fetch_summary.json').write_text(json.dumps(dict(results=results, mb=mb, seconds=time.time() - t0), indent=1))

    m = render(leaks, sites, site_by_id, need, acqs, a.cache_dir)
    size = sum(p.stat().st_size for p in (OUT / 'chips').glob('*.png'))
    log(f'rendered {len(m["chips"])} chips ({size / 1e6:.1f} MB), manifest {(OUT / "leak_chips.json").stat().st_size / 1e3:.0f} kB; '
        f'missing: { {k: len(v) for k, v in m["missing"].items()} }; total {time.time() - t0:.0f} s')


if __name__ == '__main__':
    main()
