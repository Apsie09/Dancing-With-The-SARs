r"""Render a NISAR GCOV subset as false-colour PNG overlays for the web map.

Input: a GeoTIFF subset of a GCOV granule with bands
    1 = HHHH gamma-0 (linear power), 2 = HVHV gamma-0 (linear power)
(as written by the subset recipe in research/NISAR coverage - Coryell.md).

Output (in --out-dir, named after the input file):
    <stem>_rgb.png   dual-pol composite: R = HH dB, G = HV dB, B = HH/HV ratio dB
    <stem>_hh.png    HH dB with the magma colour ramp
    <stem>_hv.png    HV dB with the viridis colour ramp
    <stem>.json      corner coordinates (lon/lat) and stretch ranges, for viz/config.js

Steps: boxcar-average the linear power (speckle reduction), convert to dB,
reproject to Web Mercator (EPSG:3857, what MapLibre image sources expect),
stretch to fixed dB ranges (fixed, not percentiles, so dates stay comparable),
and write RGBA PNGs with transparent nodata.

Usage:
    python scripts/render_gcov_png.py <subset.tif> --out-dir data/coryell/nisar [--boxcar 3]
    # large areas: average 2x2 (20 m), write only the false-colour image, as lossy WebP
    python scripts/render_gcov_png.py <district.tif> --out-dir data/coryell/nisar --boxcar 3 \
        --downsample 2 --products rgb --format webp --quality 82

--downsample N averages N x N blocks of linear power (after the boxcar, before
dB). --format webp writes lossy WebP with alpha (much smaller than PNG for
noisy radar images; supported by all current browsers and MapLibre).

Needs: numpy, rasterio.
"""
import argparse
import json
from pathlib import Path

import numpy as np
import rasterio
from rasterio.warp import Resampling, calculate_default_transform, reproject, transform_bounds

# Fixed display ranges in dB (from the 2026-09-09 Riddle subset: HH 2-98 % = -20.7..-4.5,
# HV 2-98 % = -26.3..-12.8). Keep them fixed across dates so colours are comparable.
RANGES = {"hh": (-22.0, -3.0), "hv": (-28.0, -11.0), "ratio": (3.0, 12.0)}

# Colour ramps: anchor colours sampled from matplotlib's magma and viridis (BSD-licensed).
MAGMA = ["#000004", "#1c1044", "#4f127b", "#812581", "#b5367a", "#e55064", "#fb8761", "#fec287", "#fcfdbf"]
VIRIDIS = ["#440154", "#472d7b", "#3b528b", "#2c728e", "#21918c", "#28ae80", "#5ec962", "#addc30", "#fde725"]


def boxcar(a, k):
    """Mean over a k x k window, ignoring NaN (edges use the available pixels)."""
    if k <= 1:
        return a
    valid = np.isfinite(a)
    v = np.where(valid, a, 0.0).astype(np.float64)
    n = valid.astype(np.float64)
    pad = k // 2
    v = np.pad(v, pad)
    n = np.pad(n, pad)

    def win_sum(x):
        c = x.cumsum(0).cumsum(1)
        c = np.pad(c, ((1, 0), (1, 0)))
        return c[k:, k:] - c[:-k, k:] - c[k:, :-k] + c[:-k, :-k]

    s, cnt = win_sum(v), win_sum(n)
    out = np.where(cnt > 0, s / np.maximum(cnt, 1), np.nan)
    out[~valid] = np.nan
    return out.astype(np.float32)


def to_db(p):
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(p > 0, 10.0 * np.log10(p), np.nan).astype(np.float32)


def stretch(a, lo, hi):
    return np.clip((a - lo) / (hi - lo), 0.0, 1.0)


def ramp(t, anchors):
    """Map t in [0, 1] to RGB uint8 through evenly spaced anchor colours."""
    cols = np.array([[int(h[i:i + 2], 16) for i in (1, 3, 5)] for h in anchors], dtype=np.float32)
    x = np.linspace(0.0, 1.0, len(anchors))
    t = np.nan_to_num(t, nan=0.0)
    return np.stack([np.interp(t, x, cols[:, i]) for i in range(3)]).round().astype(np.uint8)


def write_png(path, rgb, alpha, fmt="png", quality=82):
    h, w = alpha.shape
    opts = {"QUALITY": quality} if fmt == "webp" else {}
    with rasterio.Env(GDAL_PAM_ENABLED="NO"):
        with rasterio.open(path, "w", driver=fmt.upper(), width=w, height=h, count=4, dtype="uint8", **opts) as dst:
            dst.write(np.concatenate([rgb, alpha[None]], axis=0))


def block_mean(a, n):
    """NaN-aware mean over n x n blocks (edges trimmed to a multiple of n)."""
    if n <= 1:
        return a
    h, w = (a.shape[0] // n) * n, (a.shape[1] // n) * n
    b = a[:h, :w].reshape(h // n, n, w // n, n)
    with np.errstate(invalid="ignore"):
        return np.nanmean(b, axis=(1, 3)).astype(np.float32)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("subset", type=Path)
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--boxcar", type=int, default=3, help="speckle filter window in pixels (odd; 1 = off)")
    ap.add_argument("--downsample", type=int, default=1, help="average N x N blocks of linear power (2: 10 m -> 20 m)")
    ap.add_argument("--products", default="rgb,hh,hv", help="comma list of rgb, hh, hv")
    ap.add_argument("--format", choices=["png", "webp"], default="png")
    ap.add_argument("--quality", type=int, default=82, help="WebP quality (lossy)")
    args = ap.parse_args()
    products = set(args.products.split(","))
    args.out_dir.mkdir(parents=True, exist_ok=True)
    stem = args.subset.stem

    with rasterio.open(args.subset) as src:
        hh_lin, hv_lin = src.read(1).astype(np.float32), src.read(2).astype(np.float32)
        src_crs, src_tf = src.crs, src.transform

    n = args.downsample
    hh = to_db(block_mean(boxcar(hh_lin, args.boxcar), n))
    hv = to_db(block_mean(boxcar(hv_lin, args.boxcar), n))
    del hh_lin, hv_lin
    if n > 1:
        src_tf = src_tf * rasterio.Affine.scale(n)
    h, w = hh.shape
    bounds = rasterio.transform.array_bounds(h, w, src_tf)
    bounds = (bounds[0], bounds[1], bounds[2], bounds[3])
    bands = np.stack([hh, hv, hh - hv])  # ratio HH/HV in dB = difference of dB values

    dst_crs = "EPSG:3857"
    dst_tf, dw, dh = calculate_default_transform(src_crs, dst_crs, w, h, *bounds)
    out = np.full((3, dh, dw), np.nan, dtype=np.float32)
    for i in range(3):
        reproject(bands[i], out[i], src_transform=src_tf, src_crs=src_crs, dst_transform=dst_tf,
                  dst_crs=dst_crs, resampling=Resampling.bilinear, src_nodata=np.nan, dst_nodata=np.nan)
    hh, hv, ratio = out
    alpha = np.where(np.isfinite(hh) & np.isfinite(hv), 255, 0).astype(np.uint8)

    ext = args.format
    if "rgb" in products:
        rgb = np.stack([stretch(hh, *RANGES["hh"]), stretch(hv, *RANGES["hv"]), stretch(ratio, *RANGES["ratio"])])
        write_png(args.out_dir / f"{stem}_rgb.{ext}", (np.nan_to_num(rgb) * 255).round().astype(np.uint8), alpha, ext, args.quality)
    if "hh" in products:
        write_png(args.out_dir / f"{stem}_hh.{ext}", ramp(stretch(hh, *RANGES["hh"]), MAGMA), alpha, ext, args.quality)
    if "hv" in products:
        write_png(args.out_dir / f"{stem}_hv.{ext}", ramp(stretch(hv, *RANGES["hv"]), VIRIDIS), alpha, ext, args.quality)

    # MapLibre image source corners: top-left, top-right, bottom-right, bottom-left (lon, lat).
    left, top = dst_tf * (0, 0)
    right, bottom = dst_tf * (dw, dh)
    w_, s_, e_, n_ = transform_bounds(dst_crs, "EPSG:4326", left, bottom, right, top)
    meta = {
        "source": args.subset.name,
        "coordinates": [[w_, n_], [e_, n_], [e_, s_], [w_, s_]],
        "size_px": [dw, dh],
        "boxcar_px": args.boxcar,
        "downsample": n,
        "pixel_m": abs(src_tf.a),
        "products": sorted(products),
        "format": args.format,
        "ranges_db": RANGES,
        "stats_db": {k: [round(float(np.nanpercentile(v, q)), 2) for q in (2, 50, 98)]
                     for k, v in (("hh", hh), ("hv", hv), ("ratio", ratio))},
    }
    (args.out_dir / f"{stem}.json").write_text(json.dumps(meta, indent=2))
    print(json.dumps(meta, indent=2))


if __name__ == "__main__":
    main()
