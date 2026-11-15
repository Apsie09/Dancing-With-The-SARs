"""Load the index and one sample of the Coryell NISAR chip package, build dB and normalised images.

    python load_example.py                       # first positive in train/
    python load_example.py --sample N1692_03     # a given sample (train or test)
    python load_example.py --png out.png         # also save a picture (needs matplotlib)

Needs only numpy (pandas and matplotlib are optional).
"""
import argparse
import csv
import json
from pathlib import Path

import numpy as np

PKG = Path(__file__).resolve().parent


def read_index(split):
    """index.csv as a list of dicts (strings). With pandas: pd.read_csv(PKG / split / 'index.csv')."""
    with open(PKG / split / 'index.csv', newline='', encoding='utf-8') as fh:
        return list(csv.DictReader(fh))


def load_sample(split, sample_id):
    z = np.load(PKG / split / sample_id / 'sar.npz')
    meta = json.loads((PKG / split / sample_id / 'meta.json').read_text(encoding='utf-8'))
    return z, meta


def to_db(lin):
    with np.errstate(divide='ignore', invalid='ignore'):
        return 10 * np.log10(lin)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--sample')
    ap.add_argument('--png')
    args = ap.parse_args()

    train, test = read_index('train'), read_index('test')
    print(f'train: {len(train)} samples ({sum(r["label"] == "1" for r in train)} positives), '
          f'test: {len(test)} samples ({sum(r["label"] == "1" for r in test)} positives)')
    if args.sample:
        split = 'train' if any(r['sample_id'] == args.sample for r in train) else 'test'
        sid = args.sample
    else:
        split, sid = 'train', next(r['sample_id'] for r in train if r['label'] == '1')
    row = next(r for r in (train if split == 'train' else test) if r['sample_id'] == sid)
    z, meta = load_sample(split, sid)

    sar = z['sar']                                   # (4 passes, 6 bands, 20, 20) float32
    passes = list(z['pass_names'])                   # ['t-2', 't-1', 't0', 't+1']
    bands = list(z['band_names'])                    # ['HHHH', 'HVHV', 'mask', 'numberOfLooks', ...]
    avail = z['available']                           # (4,) bool; missing passes are all-NaN
    print(f'\n{sid} ({split}) label={row["label"]} cause={row["cause"] or "-"} t0={row["t0_date"]} '
          f'days pass->repair={row["days_pass_to_repair"] or "-"} zone={row["zone"]}')
    print('passes:', dict(zip(passes, z['pass_dates'])), 'available:', avail.tolist())
    print('array:', sar.shape, sar.dtype, '| bands:', bands)

    t0 = passes.index('t0')
    hh = sar[t0, bands.index('HHHH')]
    hv = sar[t0, bands.index('HVHV')]
    mask = sar[t0, bands.index('mask')]
    exc = sar[t0, bands.index('inputDataExceptionMask')]
    valid = (mask >= 1) & (mask <= 254) & np.isfinite(hh) & (hh > 0)
    hh_db = np.where(valid, to_db(hh), np.nan)
    hv_db = np.where(valid, to_db(hv), np.nan)
    print(f't0 HH dB: median {np.nanmedian(hh_db):.2f}, valid px {valid.sum()}/400, exception px {int((exc != 0).sum())}')

    # Normalisation 1: whole-district stats of the same pass (dB), stored per pass in meta.json and passes.csv
    d = meta['passes'][t0]['district']
    hh_norm_district = (hh_db - d['hh_db_median']) / d['hh_db_std']
    # Normalisation 2: local background, the 1 km circle around the point on the same pass
    c = meta['passes'][t0]['circles']['1000']
    hh_norm_local = (hh_db - c['hh_db_median']) / c['hh_db_std']
    print(f'district HH median {d["hh_db_median"]} dB (std {d["hh_db_std"]}), 1 km circle median {c["hh_db_median"]} dB')
    print(f'normalised HH (district): mean {np.nanmean(hh_norm_district):+.2f}; (local 1 km): mean {np.nanmean(hh_norm_local):+.2f}')

    # Change vs the previous pass, each pass normalised by its own district median
    t1 = passes.index('t-1')
    if avail[t1]:
        hh1 = sar[t1, 0]
        v1 = (sar[t1, 2] >= 1) & (sar[t1, 2] <= 254) & np.isfinite(hh1) & (hh1 > 0)
        d1 = meta['passes'][t1]['district']
        change = (hh_db - d['hh_db_median']) - (np.where(v1, to_db(hh1), np.nan) - d1['hh_db_median'])
        print(f'HH change t0 - t-1 (district-median corrected): mean {np.nanmean(change):+.2f} dB')

    # Where is the point? Fractional pixel position (pixel centres at i + 0.5) and chip geotransform
    ch = meta['chip']
    print(f'point at col {ch["point_col"]}, row {ch["point_row"]}; chip top-left UTM 14N ({ch["x0"]}, {ch["y0"]}), '
          f'{ch["pixel_size"]} m pixels')

    if args.png:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(1, 3, figsize=(10, 3.4))
        for a, img, title, kw in ((ax[0], hh_db, 'HH dB (t0)', dict(vmin=-25, vmax=0, cmap='magma')),
                                  (ax[1], hv_db, 'HV dB (t0)', dict(vmin=-32, vmax=-7, cmap='viridis')),
                                  (ax[2], hh_norm_district, 'HH normalised (district)', dict(vmin=-3, vmax=3, cmap='RdBu_r'))):
            im = a.imshow(img, extent=(0, 20, 20, 0), **kw)
            a.plot(ch['point_col'], ch['point_row'], 'c+', ms=12, mew=2)
            a.set_title(title, fontsize=9); fig.colorbar(im, ax=a, fraction=0.046)
        fig.suptitle(f'{sid}  label={row["label"]}  t0={row["t0_date"]}', fontsize=10)
        fig.tight_layout(); fig.savefig(args.png, dpi=110)
        print('saved', args.png)


if __name__ == '__main__':
    main()
