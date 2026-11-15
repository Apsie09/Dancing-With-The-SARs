"""Rebuild data/coryell/ (git-ignored) for the Coryell leak map in viz/.

Steps (run all, or pick with --steps):

  vectors     Leak repairs, pipe network and pressure zones from the district
              consultant's public ArcGIS services -> leak_survey.geojson/.csv,
              waterlines.geojson, pressure_zones.geojson. No login needed.
  footprints  NISAR GCOV frames over the district from the ASF archive, one
              polygon per stack with its dates and CRIDs
              -> nisar_gcov_footprints.geojson. No login needed.
  chips       Before/after radar chips around every leak in the NISAR window
              (runs scripts/make_leak_chips.py) -> nisar/acquisitions_041D073.json,
              nisar/leak_chips.json, nisar/chips/*.png. Needs Earthdata login.
  images      Whole-district false-colour images for 2026-08-28, 09-09, 09-21
              and the Riddle-cluster subset of 2026-09-09 (scripts/subset_gcov.py
              + scripts/render_gcov_png.py) -> nisar/*_district_rgb.webp,
              nisar/gcov_041D073_20260909_riddle*. Needs Earthdata login and the
              acquisitions file from the chips step.

The full NISAR district stack (all passes, all frames, float GeoTIFFs) is a
separate, larger download: scripts/download_nisar_coryell.py.

Usage (from the repo root):
    python scripts/fetch_coryell_data.py                      # everything
    python scripts/fetch_coryell_data.py --steps vectors,footprints
    python scripts/fetch_coryell_data.py --steps chips --workers 6

Requirements: Python 3.10+, numpy, requests, shapely, asf_search (footprints);
plus h5py, fsspec, aiohttp, pyproj, rasterio for chips/images. Earthdata login
(free, https://urs.earthdata.nasa.gov/) in ~/.netrc for chips/images:
    machine urs.earthdata.nasa.gov login <user> password <password>
Run times: vectors + footprints < 1 min; chips ~5-10 min (~1.4 GB transfer);
images ~4 min and ~180 MB transfer per district date.

Notes:
  * Source layers have no stated licence; see data/coryell/README.md.
  * waterlines.geojson drops the `Notes` field (its only values were staff
    e-mail addresses and a name); everything else is as served.
"""
import argparse
import csv
import json
import re
import subprocess
import sys
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

import requests

REPO = Path(__file__).resolve().parents[1]
DATA = REPO / 'data' / 'coryell'
NISAR = DATA / 'nisar'
SCRIPTS = REPO / 'scripts'

AGOL = 'https://services9.arcgis.com/AIKMFC1P7gpNycCX/arcgis/rest/services'
LAYERS = {
    'leak_survey': f'{AGOL}/survey123_7d36ae6d371c488ba8699e7c34bb1588/FeatureServer/0',
    'waterlines': f'{AGOL}/CCWSDWaterline2026/FeatureServer/16',
    'pressure_zones': f'{AGOL}/CCWSD_Leak_Density_WFL1/FeatureServer/19',
}
DISTRICT = (-97.904, 31.337, -97.412, 31.686)          # W, S, E, N
RIDDLE = (-97.5706, 31.431, -97.5094, 31.499)
NISAR_START = '2025-10-17'
DISTRICT_DATES = ['2026-08-28', '2026-09-09', '2026-09-21']
GRANULE_RE = re.compile(r'NISAR_L2_(\w\w)_GCOV_(\d{3})_(\d{3})_([AD])_(\d{3})_(\d{4})_(\w{4})_([AM])_'
                        r'(\d{8}T\d{6})_(\d{8}T\d{6})_(\w\d{5})_(\w)_(\w)_(\w)_(\d{3})')


def log(msg):
    print(f'[{datetime.now():%H:%M:%S}] {msg}', flush=True)


# ------------------------------------------------------------------ vectors --
def query_layer(url):
    """All features of an ArcGIS feature layer as a GeoJSON FeatureCollection (WGS 84)."""
    feats, offset = [], 0
    while True:
        r = requests.get(f'{url}/query', timeout=120, params=dict(
            where='1=1', outFields='*', outSR=4326, f='geojson',
            resultOffset=offset, resultRecordCount=1000))
        r.raise_for_status()
        batch = r.json().get('features', [])
        feats += batch
        offset += len(batch)
        if len(batch) < 1000:
            return {'type': 'FeatureCollection', 'features': feats}


def leaks_to_csv(fc, path):
    keys = list(fc['features'][0]['properties'])
    dates = {'CreationDate', 'EditDate', 'datetime'}
    with open(path, 'w', newline='', encoding='utf-8') as fh:
        w = csv.writer(fh)
        w.writerow(keys + ['longitude', 'latitude'])
        for f in fc['features']:
            p = f['properties']
            xy = (f.get('geometry') or {}).get('coordinates', [None, None])[:2]
            w.writerow([datetime.fromtimestamp(p[k] / 1000, timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
                        if k in dates and p.get(k) else p.get(k) for k in keys] + xy)


def step_vectors(args):
    DATA.mkdir(parents=True, exist_ok=True)
    for name, url in LAYERS.items():
        fc = query_layer(url)
        if name == 'waterlines':
            for f in fc['features']:
                f['properties'].pop('Notes', None)
        (DATA / f'{name}.geojson').write_text(json.dumps(fc), encoding='utf-8')
        log(f'{name}.geojson: {len(fc["features"])} features')
        if name == 'leak_survey':
            leaks_to_csv(fc, DATA / 'leak_survey.csv')


# --------------------------------------------------------------- footprints --
def window_leaks():
    """(lon, lat) of leaks in the NISAR window, test point 1611 dropped."""
    fc = json.loads((DATA / 'leak_survey.geojson').read_text(encoding='utf-8'))
    t0 = datetime.fromisoformat(NISAR_START).replace(tzinfo=timezone.utc).timestamp() * 1000
    return [tuple(f['geometry']['coordinates'][:2]) for f in fc['features']
            if f['properties'].get('ObjectId') != 1611 and (f['properties'].get('datetime') or 0) >= t0]


def step_footprints(args):
    import asf_search as asf
    from shapely.geometry import Point, box, shape

    W, S, E, N = DISTRICT
    pad = 0.02
    aoi = box(W - pad, S - pad, E + pad, N + pad)
    results = asf.search(dataset='NISAR', processingLevel='GCOV', intersectsWith=aoi.wkt,
                         start='2025-10-01', end=date.today().isoformat())
    log(f'ASF: {len(results)} GCOV granules over the district')

    stacks = defaultdict(dict)   # stack -> date -> (counter, granule, geometry, crid, full, bw)
    for r in results:
        name = r.properties.get('fileID') or r.properties.get('sceneName') or ''
        m = GRANULE_RE.search(name)
        if not m:
            continue
        _, _, track, d, frame, bw, pol, _, t_start, _, crid, _, full, _, counter = m.groups()
        stack = f'{track}_{d}_{frame}'
        day = f'{t_start[:4]}-{t_start[4:6]}-{t_start[6:8]}'
        rec = (int(counter), m.group(0), r.geometry, crid, full == 'F', bw, pol)
        if day not in stacks[stack] or rec[0] > stacks[stack][day][0]:
            stacks[stack][day] = rec

    leaks = window_leaks()
    lon = [p[0] for p in leaks]
    lat = [p[1] for p in leaks]
    leak_box = box(min(lon), min(lat), max(lon), max(lat))
    feats = []
    for stack, by_day in sorted(stacks.items()):
        days = sorted(by_day)
        full40 = [by_day[d] for d in days if by_day[d][4] and by_day[d][5].startswith('40')]
        ref = (full40 or [by_day[d] for d in days])[-1]
        poly = shape(ref[2])
        track, d, frame = stack.split('_')
        feats.append({'type': 'Feature', 'geometry': ref[2], 'properties': {
            'stack': stack, 'track': int(track), 'direction': 'ASCENDING' if d == 'A' else 'DESCENDING',
            'frame': int(frame), 'polarization': ref[6],
            'pixel_spacing_m': sorted({10 if by_day[x][5].startswith('40') else 20 for x in days}),
            'n_dates': len(days), 'first_date': days[0], 'last_date': days[-1], 'dates': days,
            'crid_per_date': [by_day[x][3] for x in days],
            'leak_bbox_fraction_covered': round(poly.intersection(leak_box).area / leak_box.area, 3),
            'leaks_inside': sum(poly.contains(Point(p)) for p in leaks),
            'footprint_from': ref[1],
            'note': 'Footprint = 4-corner polygon of the latest full-frame 40 MHz granule; per-date '
                    'footprints shift slightly and partial frames cover less.',
        }})
        log(f'{stack}: {len(days)} dates, {feats[-1]["properties"]["leaks_inside"]} leaks inside')
    out = {'type': 'FeatureCollection', 'name': 'nisar_gcov_footprints', 'features': feats}
    (DATA / 'nisar_gcov_footprints.geojson').write_text(json.dumps(out, indent=1), encoding='utf-8')


# ------------------------------------------------------------- chips/images --
def run(cmd):
    log('$ ' + ' '.join(str(c) for c in cmd))
    subprocess.run([str(c) for c in cmd], check=True)


def step_chips(args):
    cache = args.cache_dir or NISAR / '_chip_cache'
    run([sys.executable, SCRIPTS / 'make_leak_chips.py', '--cache-dir', cache, '--workers', args.workers])


def granule_url(day):
    acq = NISAR / 'acquisitions_041D073.json'
    if not acq.exists():
        sys.exit('nisar/acquisitions_041D073.json missing: run the chips step first.')
    for a in json.loads(acq.read_text(encoding='utf-8'))['acquisitions']:
        if a['date'] == day:
            return a['url']
    sys.exit(f'No 041_D_073 acquisition on {day} in acquisitions_041D073.json')


def step_images(args):
    tmp = NISAR / '_subsets'
    tmp.mkdir(parents=True, exist_ok=True)
    jobs = [(d, f'gcov_041D073_{d.replace("-", "")}_district', DISTRICT,
             ['--downsample', 2, '--format', 'webp', '--products', 'rgb']) for d in DISTRICT_DATES]
    jobs.append(('2026-09-09', 'gcov_041D073_20260909_riddle', RIDDLE, []))
    for day, stem, bbox, render_opts in jobs:
        tif = tmp / f'{stem}.tif'
        if not tif.exists():
            run([sys.executable, SCRIPTS / 'subset_gcov.py', granule_url(day), tif, *bbox])
        run([sys.executable, SCRIPTS / 'render_gcov_png.py', tif, '--out-dir', NISAR, *render_opts])
    # The map's Riddle layers also expect the float subset next to the PNGs.
    (NISAR / 'gcov_041D073_20260909_riddle.tif').write_bytes((tmp / 'gcov_041D073_20260909_riddle.tif').read_bytes())


STEPS = {'vectors': step_vectors, 'footprints': step_footprints, 'chips': step_chips, 'images': step_images}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--steps', default=','.join(STEPS), help=f'comma list of {", ".join(STEPS)}')
    ap.add_argument('--workers', type=int, default=6, help='parallel granule readers for chips')
    ap.add_argument('--cache-dir', type=Path, help='raw chip cache (default data/coryell/nisar/_chip_cache)')
    ap.add_argument('--data-dir', type=Path, help='output folder (default data/coryell)')
    args = ap.parse_args()
    if args.data_dir:
        global DATA, NISAR
        DATA, NISAR = args.data_dir, args.data_dir / 'nisar'
    for s in args.steps.split(','):
        log(f'--- {s}')
        STEPS[s.strip()](args)
    log('done')


if __name__ == '__main__':
    main()
