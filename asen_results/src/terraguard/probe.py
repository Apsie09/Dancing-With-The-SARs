"""Streaming probe: open one GCOV granule remotely and measure layout, bytes transferred and time.

Answers, with measurements instead of estimates:
  - dataset names, shapes, dtypes, HDF5 chunking and compression of the frequency-A grids
  - real pixel spacing and CRS
  - network bytes needed for (a) opening the file, (b) a whole-AOI crop, (c) one incident patch
"""
from __future__ import annotations

import time

import earthaccess
import geopandas as gpd
import h5py
import numpy as np
from pyproj import Transformer

from .config import Config, human_size

GRID = "/science/LSAR/GCOV/grids/frequencyA"


def run(cfg: Config, granule: str | None = None, block_size: int = 1 << 20) -> None:
    earthaccess.login(strategy="netrc")
    acq = gpd.read_parquet(cfg.acquisitions_parquet)
    inc = gpd.read_parquet(cfg.incidents_parquet)
    if granule:
        row = acq[acq["granule_ur"] == granule].iloc[0]
    else:
        row = acq[acq["is_preferred"] & (acq["maturity"] == "validated") & (acq["n_incidents_inside"] > 0)].iloc[0]
    print(f"Probe: {row['granule_ur']}\n  remote size {human_size(row['size_bytes'])}, block_size {human_size(block_size)}")

    fs = earthaccess.get_fsspec_https_session()
    remote = fs.open(row["h5_https"], "rb", block_size=block_size, cache_type="blockcache",
                     cache_options={"maxblocks": 1024})
    remote.cache.total_requested_bytes = 0
    _count_fetches(remote)

    t = time.time()
    h5 = h5py.File(remote, "r")
    g = h5[GRID]
    print("\n  frequencyA datasets:")
    for name, obj in g.items():
        if isinstance(obj, h5py.Dataset):
            print(f"    {name:28s} shape={obj.shape!s:16s} dtype={obj.dtype!s:9s} chunks={obj.chunks} "
                  f"compression={obj.compression}({obj.compression_opts}) shuffle={obj.shuffle}")
    x, y = g["xCoordinates"][:], g["yCoordinates"][:]
    proj = g["projection"]
    epsg = int(proj.attrs["epsg_code"]) if "epsg_code" in proj.attrs else int(proj[()])
    dx, dy = float(np.median(np.diff(x))), float(np.median(np.diff(y)))
    print(f"\n  CRS EPSG:{epsg}, pixel spacing dx={dx:.2f} m dy={dy:.2f} m, grid {len(y)} x {len(x)} px")
    print(f"  top-level groups: {list(h5['/science/LSAR/GCOV'].keys())}, metadata: "
          f"{list(h5['/science/LSAR/GCOV/metadata'].keys()) if 'metadata' in h5['/science/LSAR/GCOV'] else '-'}")
    open_bytes, open_t = remote.cache.total_requested_bytes, time.time() - t
    print(f"\n  [open + coords]  {human_size(open_bytes):>10s} transferred, {open_t:5.1f} s")

    tr = Transformer.from_crs(4326, epsg, always_xy=True)

    def window(xmin, ymin, xmax, ymax):
        ci = np.where((x >= xmin) & (x <= xmax))[0]
        ri = np.where((y >= ymin) & (y <= ymax))[0]
        return slice(ri.min(), ri.max() + 1), slice(ci.min(), ci.max() + 1)

    pols = [p for p in ("HHHH", "HVHV", "VVVV", "VHVH") if p in g]

    def measure(label, sl):
        before, t0 = remote.cache.total_requested_bytes, time.time()
        arrs = {p: g[p][sl] for p in pols}
        nbytes = sum(a.nbytes for a in arrs.values())
        got = remote.cache.total_requested_bytes - before
        a = arrs[pols[0]]
        valid = np.isfinite(a) & (a > 0)
        print(f"  [{label}] {a.shape} px x {len(pols)} pols = {human_size(nbytes)} in memory; "
              f"{human_size(got)} transferred ({got / max(nbytes, 1):.1f}x), {time.time() - t0:5.1f} s; "
              f"valid {100 * valid.mean():.0f}%, {pols[0]} median {10 * np.log10(np.nanmedian(a[valid])):.1f} dB"
              if valid.any() else f"  [{label}] no valid pixels")
        return arrs

    half = cfg.section("sar")["patch_size_px"] * dx / 2
    pts = inc[inc["incident_date_local"] >= "2026-01-01"].iloc[[0, 20, 40]]  # spread out: no shared chunks
    for _, r in pts.iterrows():
        px, py = tr.transform(r["lon"], r["lat"])
        measure(f"patch #{r['incident_id']}", window(px - half, py - half, px + half, py + half))

    # Crop last: patches above are measured cold (nothing cached yet).
    x0, y0, x1, y1 = cfg.section("nisar")["aoi_bbox"]
    xs, ys = tr.transform([x0, x1, x0, x1], [y0, y0, y1, y1])
    measure("whole-AOI crop", window(min(xs), min(ys), max(xs), max(ys)))

    total = remote.cache.total_requested_bytes
    print(f"\n  TOTAL transferred this probe: {human_size(total)} of {human_size(row['size_bytes'])} "
          f"({100 * total / row['size_bytes']:.2f}% of the file)")


def _count_fetches(remote):
    """Track bytes fetched by the fsspec block cache (each miss fetches one block)."""
    cache = remote.cache
    orig = cache.fetcher

    def fetcher(start, end):
        cache.total_requested_bytes += end - start
        return orig(start, end)

    cache.fetcher = fetcher
