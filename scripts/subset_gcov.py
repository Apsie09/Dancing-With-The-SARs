"""Read a lon/lat window of a remote NISAR GCOV granule (no full download) into a GeoTIFF.

The granule is opened once over HTTP range requests (h5py + fsspec); the window
is read in row strips so memory stays bounded and progress is logged. Output
bands: 1 = HHHH, 2 = HVHV (linear gamma-0, float32, NaN where the `mask` layer
is not 1..254), in the granule's UTM grid (EPSG:32614 here), 10 m.

Usage:
    python scripts/subset_gcov.py <granule .h5 URL> <out.tif> <W> <S> <E> <N>

Earthdata login through ~/.netrc. See research/NISAR coverage - Coryell.md, section 6.
Needs requests, fsspec (+aiohttp), h5py, numpy, pyproj, rasterio.
"""
import json
import sys
import time

import fsspec
import h5py
import numpy as np
import rasterio
import requests
from pyproj import Transformer
from rasterio.transform import from_origin

GRID = '/science/LSAR/GCOV/grids/frequencyA'
STRIP = 1024  # rows per read (two 512-row chunk rows)


def main():
    url, out = sys.argv[1], sys.argv[2]
    W, S, E, N = map(float, sys.argv[3:7])
    t0 = time.time()
    r = requests.get(url, headers={'Range': 'bytes=0-0'}, timeout=120)
    r.raise_for_status()
    signed = r.url  # short-lived pre-signed URL
    f = fsspec.filesystem('http').open(signed, block_size=2 ** 20, cache_type='blockcache',
                                       cache_options=dict(maxblocks=64))
    g = h5py.File(f, 'r', rdcc_nbytes=256 * 2 ** 20, rdcc_nslots=10007)[GRID]
    epsg = int(g['projection'][()])
    x, y = g['xCoordinates'][:], g['yCoordinates'][:]
    dx, dy = float(g['xCoordinateSpacing'][()]), float(g['yCoordinateSpacing'][()])
    tr = Transformer.from_crs(4326, epsg, always_xy=True)
    xs, ys = tr.transform([W, E, E, W], [S, S, N, N])
    c0, c1 = int(np.searchsorted(x, min(xs))), int(np.searchsorted(x, max(xs))) + 1
    r0, r1 = int(np.searchsorted(-y, -max(ys))), int(np.searchsorted(-y, -min(ys))) + 1
    h, w = r1 - r0, c1 - c0
    print(f'window rows {r0}:{r1} cols {c0}:{c1} = {h} x {w} px', flush=True)
    transform = from_origin(x[c0] - dx / 2, y[r0] - dy / 2, dx, -dy)
    prof = dict(driver='GTiff', height=h, width=w, count=2, dtype='float32', crs=f'EPSG:{epsg}',
                transform=transform, nodata=np.nan, compress='deflate', predictor=3, tiled=True,
                blockxsize=512, blockysize=512, BIGTIFF='IF_SAFER')
    with rasterio.open(out, 'w', **prof) as dst:
        for a in range(r0, r1, STRIP):
            b = min(a + STRIP, r1)
            m = g['mask'][a:b, c0:c1]
            bad = (m < 1) | (m > 254)
            for i, term in enumerate(('HHHH', 'HVHV'), 1):
                arr = g[term][a:b, c0:c1].astype(np.float32)
                arr[bad] = np.nan
                dst.write(arr, i, window=rasterio.windows.Window(0, a - r0, w, b - a))
            print(f'  rows {a - r0}-{b - r0} of {h}, {time.time() - t0:.0f} s, '
                  f'~{f.cache.miss_count * 2 ** 20 / 1e6:.0f} MB fetched', flush=True)
        dst.set_band_description(1, 'HHHH gamma0 linear power')
        dst.set_band_description(2, 'HVHV gamma0 linear power')
        dst.update_tags(source=url.rsplit('/', 1)[-1], units='linear power (gamma0), unitless', path=GRID)
    print(json.dumps(dict(out=out, shape=[h, w], seconds=round(time.time() - t0, 1),
                          mb_fetched=round(f.cache.miss_count * 2 ** 20 / 1e6, 1))), flush=True)


if __name__ == '__main__':
    main()
