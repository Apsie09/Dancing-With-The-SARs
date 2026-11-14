"""Search, inspect and subset NISAR L-band GCOV data for the Elin Pelin AOI.

Two extraction paths are implemented:

``--hdf5`` / ``h5``
    The calibrated path.  Reads ``/science/LSAR/GCOV/grids/frequency{A,B}/``
    from a **local** NISAR GCOV HDF5 file, converts gamma0 linear power to dB
    and writes GeoTIFFs in the product's native UTM grid.  Download the file
    first with an Earthdata Login (``~/.netrc`` and ``curl -n -L`` or
    ``asf_search``); ASF PROVISIONAL granules are not anonymous.

``--browse`` / ``browse``
    The no-authentication fallback.  Downloads the public ``_LATLON.png`` and
    ``_NATIVE_A_HHHH.png`` / ``_NATIVE_A_HVHV.png`` quicklooks and maps them
    linearly from the ASF footprint bbox to the common UTM 34N grid.  Output
    is raw 8-bit browse DN (display-only), not calibrated gamma0.

Both paths write to ``data/raw/nisar`` by default.  Browse PNGs and the public
sample HDF5 are cached in ``/tmp/opencode/nisar`` and never committed.

Examples
--------
Search the AOI::

    pixi run python scripts/nisar_extract.py search

Inspect any GCOV file::

    pixi run python scripts/nisar_extract.py inspect /tmp/opencode/nisar/sample_gcov_2008.h5

Calibrated extraction from a local file::

    pixi run python scripts/nisar_extract.py --hdf5 \
        /tmp/opencode/nisar/NISAR_..._20260620....h5 \
        --bbox 23.575 42.610 23.640 42.665

Browse fallback for two dates (public PNGs only)::

    pixi run python scripts/nisar_extract.py --browse \
        --scene-json /tmp/opencode/nisar/search.json \
        --dates 2026-06-20 2026-10-06
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Iterable

import numpy as np
import requests

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "data" / "raw" / "nisar"
CACHE_DIR = Path("/tmp/opencode/nisar")

ASF_SEARCH = "https://api.daac.asf.alaska.edu/services/search/param"
DEFAULT_BBOX = (23.575, 42.610, 23.640, 42.665)

# Browse PNGs are 8-bit quicklooks produced by nisarqa from multilooked linear
# power: 5-95 % clip -> dB -> gamma 0.5 -> [0,1] -> 1..255.  The absolute dB
# range (vmin/vmax) is scene-specific and is not stored in the PNG, so these
# layers are kept as raw display DN and are NOT calibrated gamma0.
BROWSE_NODATA = 0


# ---------------------------------------------------------------------------
# generic helpers
# ---------------------------------------------------------------------------
def _bbox_tuple(values: Iterable[float]) -> tuple[float, float, float, float]:
    vals = tuple(float(v) for v in values)
    if len(vals) != 4:
        raise argparse.ArgumentTypeError("bbox needs west south east north")
    w, s, e, n = vals
    if not (w < e and s < n):
        raise ValueError(f"invalid bbox: {vals}")
    return w, s, e, n


def _bbox_wkt(bbox: tuple[float, float, float, float]) -> str:
    w, s, e, n = bbox
    return f"POLYGON(({w} {s},{e} {s},{e} {n},{w} {n},{w} {s}))"


def _safe_name(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", text)


def _date_from_name(name: str) -> str:
    m = re.search(r"_(\d{8})T\d{6}_", name)
    if not m:
        # Public sample granules often have shortened names.
        return "unknown"
    return m.group(1)


def _utm_bbox(bbox: tuple[float, float, float, float], epsg: int) -> tuple[float, float, float, float]:
    from pyproj import Transformer

    tr = Transformer.from_crs("EPSG:4326", f"EPSG:{epsg}", always_xy=True)
    xs, ys = [], []
    for lon in (bbox[0], bbox[2]):
        for lat in (bbox[1], bbox[3]):
            x, y = tr.transform(lon, lat)
            xs.append(x)
            ys.append(y)
    return min(xs), min(ys), max(xs), max(ys)


def _download(url: str, dest: Path, *, auth=None, chunk: int = 1 << 20) -> Path:
    """Stream ``url`` to ``dest`` with a simple progress line.

    Public ASF browse/sample URLs work without credentials.  Calibrated
    PROVISIONAL granules return a 302 to Earthdata Login unless the session
    carries an authenticated cookie / netrc credentials.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 0:
        print(f"  cached {dest.name} ({dest.stat().st_size / 1e6:.1f} MB)")
        return dest

    session = requests.Session()
    session.trust_env = True
    if auth is not None:
        session.auth = auth

    with session.get(url, stream=True, timeout=120, allow_redirects=True) as r:
        if r.status_code in (401, 403) or "text/html" in r.headers.get("content-type", ""):
            raise RuntimeError(
                f"HTTP {r.status_code} for {url}\n"
                "This granule requires Earthdata Login.  Put EDL credentials in "
                "~/.netrc (machine urs.earthdata.nasa.gov) and retry, or use the "
                "'browse' subcommand."
            )
        r.raise_for_status()
        total = int(r.headers.get("content-length", 0))
        done = 0
        last = -1
        with dest.open("wb") as fh:
            for block in r.iter_content(chunk_size=chunk):
                if not block:
                    continue
                fh.write(block)
                done += len(block)
                if total:
                    pct = int(done * 100 / total)
                    if pct != last and pct % 5 == 0:
                        print(f"  {dest.name}: {pct:3d}%  {done / 1e6:7.1f}/{total / 1e6:.1f} MB", flush=True)
                        last = pct
    print(f"  wrote {dest} ({dest.stat().st_size / 1e6:.1f} MB)")
    return dest


# ---------------------------------------------------------------------------
# ASF search
# ---------------------------------------------------------------------------
def search_scenes(
    bbox: tuple[float, float, float, float],
    start: str = "2026-06-01T00:00:00Z",
    end: str = "2026-12-31T23:59:59Z",
    track: int | None = None,
) -> list[dict]:
    params = {
        "platform": "NISAR",
        "processingLevel": "GCOV",
        "intersectsWith": _bbox_wkt(bbox),
        "start": start,
        "end": end,
        "output": "json",
    }
    r = requests.get(ASF_SEARCH, params=params, timeout=120)
    r.raise_for_status()
    data = r.json()
    scenes = data[0] if data and isinstance(data[0], list) else data
    if track is not None:
        scenes = [s for s in scenes if int(s.get("track") or -1) == track]
    scenes.sort(key=lambda s: s["startTime"])
    return scenes


def scene_summary(scene: dict) -> str:
    name = scene["granuleName"]
    m = re.search(r"GCOV_(\d+)_(\d+)_([AD])_", name)
    cycle, trk, direction = m.groups() if m else ("?", "?", "?")
    return (
        f"{scene['startTime'][:19]}  track {trk:>3} {direction}  cycle {cycle}  "
        f"frame {scene.get('frameNumber')}  {name}"
    )


# ---------------------------------------------------------------------------
# HDF5 inspection / extraction
# ---------------------------------------------------------------------------
def inspect_h5(path: str | Path, max_depth: int = 6) -> None:
    import h5py

    with h5py.File(path, "r") as f:
        if "science/LSAR/GCOV" not in f:
            raise SystemExit(f"{path}: no /science/LSAR/GCOV group")
        print(f"file: {path}")
        print(f"size: {Path(path).stat().st_size / 1e6:.1f} MB")
        print("root attributes:")
        for k, v in f.attrs.items():
            print(f"  @{k} = {str(v)[:160]}")

        def walk(group, prefix: str, depth: int) -> None:
            if depth > max_depth:
                return
            for key in group:
                obj = group[key]
                name = f"{prefix}/{key}"
                if isinstance(obj, h5py.Dataset):
                    attrs = []
                    for a in ("units", "description", "_FillValue", "valid_min", "max_value"):
                        if a in obj.attrs:
                            attrs.append(f"{a}={str(obj.attrs[a])[:60]}")
                    print(
                        f"{'  ' * depth}{name}  shape={obj.shape} dtype={obj.dtype} "
                        f"chunks={obj.chunks}  " + " ".join(attrs)
                    )
                else:
                    print(f"{'  ' * depth}{name}/")
                    walk(obj, name, depth + 1)

        walk(f["science/LSAR/GCOV"], "science/LSAR/GCOV", 0)


def _frequency_group(f, preferred: str = "A"):
    base = f["science/LSAR/GCOV/grids"]
    for freq in (preferred, "A", "B"):
        name = f"frequency{freq}"
        if name in base:
            return base[name], freq
    raise RuntimeError("no frequencyA/frequencyB group in GCOV grids")


def _read_coord(ds) -> np.ndarray:
    return np.asarray(ds[:], dtype="float64")


def extract_h5(
    h5_path: str | Path,
    bbox: tuple[float, float, float, float],
    out_dir: Path,
    *,
    pols: tuple[str, ...] = ("HHHH", "HVHV"),
    sigma0: bool = False,
    res: float | None = None,
    label: str | None = None,
) -> dict:
    """Subset one calibrated GCOV HDF5 granule to ``bbox`` and write GeoTIFFs."""
    import h5py
    import rasterio
    from rasterio.transform import from_origin

    with h5py.File(h5_path, "r") as f:
        grid, freq = _frequency_group(f)
        epsg = int(grid["projection"][()])
        if "epsg_code" in grid["projection"].attrs:
            epsg = int(grid["projection"].attrs["epsg_code"])
        xs = _read_coord(grid["xCoordinates"])
        ys = _read_coord(grid["yCoordinates"])
        dx = float(grid["xCoordinateSpacing"][()]) if "xCoordinateSpacing" in grid else float(xs[1] - xs[0])
        dy = float(grid["yCoordinateSpacing"][()]) if "yCoordinateSpacing" in grid else float(ys[1] - ys[0])
        if res is None:
            res = abs(dx)
        print(f"  frequency {freq}, EPSG:{epsg}, {len(xs)} x {len(ys)} grid, spacing {dx} x {dy} m")

        w, s, e, n = _utm_bbox(bbox, epsg)
        col0 = int(np.searchsorted(xs, w, side="left")) - 2
        col1 = int(np.searchsorted(xs, e, side="right")) + 2
        # yCoordinates are descending (north -> south)
        row0 = int(np.searchsorted(-ys, -n, side="left")) - 2
        row1 = int(np.searchsorted(-ys, -s, side="right")) + 2
        col0, col1 = max(0, col0), min(len(xs), col1)
        row0, row1 = max(0, row0), min(len(ys), row1)
        if col1 <= col0 or row1 <= row0:
            raise RuntimeError(f"AOI {bbox} does not overlap the granule")

        win = (slice(row0, row1), slice(col0, col1))
        print(f"  window rows {row0}:{row1}, cols {col0}:{col1} -> {row1 - row0} x {col1 - col0} px")

        mask = grid["mask"][win] if "mask" in grid else None
        looks = grid["numberOfLooks"][win] if "numberOfLooks" in grid else None
        gamma2sigma = grid["rtcGammaToSigmaFactor"][win] if "rtcGammaToSigmaFactor" in grid else None

        sub_x = xs[col0:col1]
        sub_y = ys[row0:row1]
        transform = from_origin(
            float(sub_x[0] - abs(dx) / 2),
            float(sub_y[0] + abs(dy) / 2),
            abs(dx),
            abs(dy),
        )

        out_dir.mkdir(parents=True, exist_ok=True)
        date = label or _date_from_name(Path(h5_path).name)
        meta: dict = {
            "source_h5": str(h5_path),
            "granule": Path(h5_path).name,
            "frequency": freq,
            "epsg": epsg,
            "date": date,
            "bbox_wgs84": list(bbox),
            "transform": list(transform)[:6],
            "width": int(col1 - col0),
            "height": int(row1 - row0),
            "resolution_m": float(abs(dx)),
            "sigma0": bool(sigma0),
            "layers": {},
        }

        for pol in pols:
            if pol not in grid:
                print(f"  {pol}: not present in this granule, skipping")
                continue
            power = np.asarray(grid[pol][win], dtype="float32")
            valid = np.isfinite(power) & (power > 0)
            if mask is not None:
                valid &= np.asarray(mask) != 255
            if sigma0 and gamma2sigma is not None:
                power = power * np.asarray(gamma2sigma, dtype="float32")
            with np.errstate(divide="ignore", invalid="ignore"):
                db = 10.0 * np.log10(power)
            db = np.where(valid, db, np.nan).astype("float32")

            short = pol[:2]
            if label:
                out_name = f"{label}_{short}.tif"
            else:
                out_name = f"{date}_{short}.tif"
            out_path = out_dir / out_name
            profile = {
                "driver": "GTiff",
                "height": db.shape[0],
                "width": db.shape[1],
                "count": 1,
                "dtype": "float32",
                "crs": f"EPSG:{epsg}",
                "transform": transform,
                "nodata": np.nan,
                "compress": "deflate",
                "tiled": True,
                "blockxsize": 256,
                "blockysize": 256,
            }
            with rasterio.open(out_path, "w", **profile) as ds:
                ds.write(db, 1)
                ds.set_band_description(1, f"{pol} gamma0{'-sigma0' if sigma0 else ''} (dB)")
                ds.update_tags(
                    source="NISAR L2 GCOV",
                    granule=Path(h5_path).name,
                    date=date,
                    polarization=pol,
                    units="dB",
                    radiometry="sigma0" if sigma0 else "gamma0",
                    note="10*log10(linear power); mask 255 and non-finite values set to NaN",
                )
            vals = db[np.isfinite(db)]
            meta["layers"][short] = {
                "file": out_name,
                "min_db": float(vals.min()) if vals.size else None,
                "max_db": float(vals.max()) if vals.size else None,
                "median_db": float(np.median(vals)) if vals.size else None,
                "valid_fraction": float(vals.size / db.size),
            }
            print(
                f"  {pol}: {out_name}  {db.shape[1]}x{db.shape[0]}  "
                f"dB {vals.min():.1f}..{vals.max():.1f} (median {np.median(vals):.1f})"
            )

    meta_path = out_dir / f"{label or date}_h5_metadata.json"
    meta_path.write_text(json.dumps(meta, indent=2))
    print(f"  wrote {meta_path}")
    return meta


def combine_change(out_dir: Path, date_a: str, date_b: str, pol: str = "HH") -> Path | None:
    """Write ``nisar_change_<pol>.tif`` from two per-date GeoTIFFs."""
    import rasterio

    a = out_dir / f"{date_a}_{pol}.tif"
    b = out_dir / f"{date_b}_{pol}.tif"
    if not (a.exists() and b.exists()):
        print(f"  change {pol}: missing {a.name} or {b.name}")
        return None
    with rasterio.open(a) as da, rasterio.open(b) as db:
        if (da.width, da.height, da.crs, da.transform) != (db.width, db.height, db.crs, db.transform):
            raise RuntimeError(f"grids do not align for {a.name} and {b.name}")
        arr = db.read(1) - da.read(1)
        profile = da.profile.copy()
        profile.update(dtype="float32", nodata=np.nan, compress="deflate", tiled=True)
        out = out_dir / f"nisar_change_{pol}.tif"
        with rasterio.open(out, "w", **profile) as ds:
            ds.write(arr.astype("float32"), 1)
            ds.set_band_description(1, f"{date_b} minus {date_a} {pol} (dB)")
            ds.update_tags(
                source="NISAR L2 GCOV",
                units="dB difference",
                note=f"{date_b} - {date_a}; positive means brighter on {date_b}",
            )
    vals = arr[np.isfinite(arr)]
    print(f"  change {pol}: {out.name}  {arr.shape[1]}x{arr.shape[0]}  range {vals.min():.2f}..{vals.max():.2f} dB")
    return out


# ---------------------------------------------------------------------------
# Browse fallback: public quicklook PNGs -> raw 8-bit GeoTIFFs
# ---------------------------------------------------------------------------
# Default output grid requested for the Elin Pelin AOI: 277 x 314 pixels at
# 20 m in UTM 34N.  west/north are the outer edges of the first pixel.
DEFAULT_GRID = (711020.0, 4727000.0, 277, 314, 20.0)


def _browse_urls(scene: dict) -> dict[str, str]:
    out = {}
    for url in scene.get("browse", []):
        name = url.rsplit("/", 1)[-1]
        for suffix in ("_LATLON.png", "_NATIVE_A_HHHH.png", "_NATIVE_A_HVHV.png", "_NATIVE.png"):
            if name.endswith(suffix):
                out[suffix[1:-4]] = url
    return out


def _parse_footprint(scene: dict) -> list[tuple[float, float]]:
    text = scene.get("stringFootprint") or ""
    pts = [(float(a), float(b)) for a, b in re.findall(r"([-+]?\d+\.\d+)\s+([-+]?\d+\.\d+)", text)]
    if len(pts) >= 5 and pts[0] == pts[-1]:
        pts = pts[:-1]
    if len(pts) != 4:
        raise RuntimeError(f"expected a 4-corner footprint, got {len(pts)} points")
    return pts


def _footprint_bbox(scene: dict) -> tuple[float, float, float, float]:
    pts = _parse_footprint(scene)
    lons = [p[0] for p in pts]
    lats = [p[1] for p in pts]
    return min(lons), min(lats), max(lons), max(lats)


def _grid_axes(grid: tuple[float, float, int, int, float], epsg: int):
    """Return lon/lat arrays for the pixel centres of an output UTM grid."""
    from pyproj import Transformer

    west, north, width, height, res = grid
    width, height = int(width), int(height)
    cols = np.arange(width) + 0.5
    rows = np.arange(height) + 0.5
    xx = west + cols * res
    yy = north - rows * res
    xx, yy = np.meshgrid(xx, yy)
    tr = Transformer.from_crs(f"EPSG:{epsg}", "EPSG:4326", always_xy=True)
    lon, lat = tr.transform(xx, yy)
    return lon, lat


def _sample_linear(
    png: Path,
    lon: np.ndarray,
    lat: np.ndarray,
    bbox: tuple[float, float, float, float],
) -> np.ndarray:
    """Nearest-neighbour sample of a browse PNG using a linear lon/lat mapping.

    ``bbox`` is the ASF footprint bbox (west, south, east, north).  The browse
    PNG is assumed to span that bbox.  This is deliberately simple: the browse
    image has no embedded geotransform (its KML sidecar is login-protected),
    so the result is approximate and suitable for display only.
    """
    from PIL import Image
    from scipy.ndimage import map_coordinates

    img = np.array(Image.open(png).convert("L"), dtype="float32")
    h, w = img.shape
    lon_min, lat_min, lon_max, lat_max = bbox
    px = (lon - lon_min) / (lon_max - lon_min) * (w - 1)
    py = (lat_max - lat) / (lat_max - lat_min) * (h - 1)
    dn = map_coordinates(img, [py, px], order=0, mode="constant", cval=0.0)
    return np.where(dn >= 1, dn, 0).astype("uint8")


def _sample_linear_mask(
    png: Path,
    lon: np.ndarray,
    lat: np.ndarray,
    bbox: tuple[float, float, float, float],
) -> np.ndarray:
    """Return the valid-area mask of a browse PNG on the output grid."""
    from PIL import Image
    from scipy.ndimage import map_coordinates

    img = np.array(Image.open(png).convert("L"), dtype="float32")
    h, w = img.shape
    lon_min, lat_min, lon_max, lat_max = bbox
    px = (lon - lon_min) / (lon_max - lon_min) * (w - 1)
    py = (lat_max - lat) / (lat_max - lat_min) * (h - 1)
    dn = map_coordinates(img, [py, px], order=0, mode="constant", cval=0.0)
    return dn >= 1


def _write_browse_tif(
    path: Path,
    arr: np.ndarray,
    grid: tuple[float, float, int, int, float],
    *,
    epsg: int,
    date: str,
    pol: str,
    scene: dict,
    change: bool = False,
) -> None:
    import rasterio
    from rasterio.transform import from_origin

    west, north, width, height, res = grid
    dtype = "int16" if change else "uint8"
    nodata = -9999 if change else 0
    profile = {
        "driver": "GTiff",
        "height": int(height),
        "width": int(width),
        "count": 1,
        "dtype": dtype,
        "crs": f"EPSG:{epsg}",
        "transform": from_origin(west, north, res, res),
        "nodata": nodata,
        "compress": "deflate",
        "tiled": True,
        "blockxsize": 256,
        "blockysize": 256,
    }
    with rasterio.open(path, "w", **profile) as ds:
        ds.write(arr.astype(dtype), 1)
        ds.set_band_description(
            1,
            f"{pol} browse DN change" if change else f"{pol} 8-bit browse DN",
        )
        ds.update_tags(
            source="NISAR L2 GCOV browse PNG (public quicklook fallback)",
            granule=scene.get("granuleName", ""),
            date=date,
            polarization=pol,
            units="DN change" if change else "8-bit browse DN (0-255)",
            calibration="NOT calibrated gamma0; display-only browse quicklook",
            georeferencing="linear mapping to ASF footprint bbox; approximate",
            note=(
                "Later minus earlier; positive = brighter later"
                if change
                else "Raw quicklook DN; 0 = nodata"
            ),
        )


def extract_browse(
    scene_json: Path,
    dates: tuple[str, str],
    out_dir: Path,
    *,
    grid: tuple[float, float, int, int, float] = DEFAULT_GRID,
    epsg: int = 32634,
    make_preview: bool = True,
) -> dict:
    """Download public browse PNGs for two dates and write raw 8-bit GeoTIFFs."""
    scenes = json.loads(Path(scene_json).read_text())
    if isinstance(scenes, list) and scenes and isinstance(scenes[0], list):
        scenes = scenes[0]
    by_date = {s["startTime"][:10]: s for s in scenes}
    chosen = []
    for d in dates:
        if d not in by_date:
            raise SystemExit(f"date {d} not in {scene_json}; available: {sorted(by_date)}")
        chosen.append(by_date[d])

    out_dir.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    lon, lat = _grid_axes(grid, epsg)
    west, north, width, height, res = grid
    sf = next((s for s in chosen if s.get("stringFootprint")), None)
    if sf is None:
        raise RuntimeError("no scene footprint available")
    fp_bbox = _footprint_bbox(sf)

    records = []
    dn_stack: dict[str, list[np.ndarray]] = {"HH": [], "HV": []}

    for scene in chosen:
        date = scene["startTime"][:10].replace("-", "")
        urls = _browse_urls(scene)
        if "LATLON" not in urls:
            raise RuntimeError(f"no _LATLON.png browse URL for {scene['granuleName']}")
        latlon = CACHE_DIR / f"{date}_LATLON.png"
        _download(urls["LATLON"], latlon)
        rec = {
            "granule": scene["granuleName"],
            "date": scene["startTime"],
            "track": scene.get("track"),
            "relative_orbit": scene.get("relativeOrbit"),
            "flight_direction": scene.get("flightDirection"),
            "frame": scene.get("frameNumber"),
            "browse_urls": urls,
            "url_h5": scene.get("downloadUrl"),
            "layers": {},
        }
        for pol, key in (("HH", "NATIVE_A_HHHH"), ("HV", "NATIVE_A_HVHV")):
            if key not in urls:
                print(f"  {date} {pol}: no browse layer, skipping")
                continue
            png = CACHE_DIR / f"{date}_{pol}.png"
            _download(urls[key], png)
            dn = _sample_linear(png, lon, lat, fp_bbox)
            # The LATLON quicklook is the browse product's geographic reference;
            # use its valid area so the single-pol layers cannot leak values
            # outside the imaged swath.
            dn = np.where(_sample_linear_mask(latlon, lon, lat, fp_bbox), dn, 0).astype("uint8")
            out_path = out_dir / f"nisar_{pol.lower()}_{date}.tif"
            _write_browse_tif(out_path, dn, grid, epsg=epsg, date=date, pol=pol, scene=scene)
            vals = dn[dn > 0]
            rec["layers"][pol] = {
                "file": out_path.name,
                "dn_min": int(vals.min()) if vals.size else None,
                "dn_max": int(vals.max()) if vals.size else None,
                "dn_median": float(np.median(vals)) if vals.size else None,
                "valid_fraction": float((dn > 0).mean()),
            }
            print(
                f"  {date} {pol}: {out_path.name}  {width}x{height}  "
                f"DN {vals.min() if vals.size else '-'}..{vals.max() if vals.size else '-'} "
                f"(median {np.median(vals) if vals.size else float('nan'):.0f})"
            )
            dn_stack[pol].append(dn)
        records.append(rec)

    # change = later minus earlier (raw 8-bit browse values)
    changes = {}
    for pol in ("HH", "HV"):
        if len(dn_stack[pol]) != 2:
            continue
        a, b = dn_stack[pol]
        change = np.where((a > 0) & (b > 0), b.astype("int16") - a.astype("int16"), -9999).astype("int16")
        out_path = out_dir / f"nisar_change_{pol}.tif"
        _write_browse_tif(
            out_path,
            change,
            grid,
            epsg=epsg,
            date=f"{dates[1]}_minus_{dates[0]}",
            pol=pol,
            scene=chosen[1],
            change=True,
        )
        vals = change[change != -9999]
        changes[pol] = {
            "file": out_path.name,
            "dn_min": int(vals.min()) if vals.size else None,
            "dn_max": int(vals.max()) if vals.size else None,
            "dn_median": float(np.median(vals)) if vals.size else None,
        }
        print(
            f"  change {pol}: {out_path.name}  "
            f"DN {vals.min() if vals.size else '-'}..{vals.max() if vals.size else '-'} "
            f"(median {np.median(vals) if vals.size else float('nan'):.0f})"
        )

    # latest HH alias
    latest_src = out_dir / f"nisar_hh_{dates[1].replace('-', '')}.tif"
    if latest_src.exists():
        import shutil

        latest = out_dir / "nisar_hh_latest.tif"
        shutil.copyfile(latest_src, latest)
        print(f"  wrote {latest} (copy of {latest_src.name})")

    meta = {
        "method": "browse_png_fallback",
        "hdf5_status": "blocked: ASF PROVISIONAL GCOV HDF5 requires Earthdata Login (GET -> OAuth 302)",
        "grid": {
            "crs": f"EPSG:{epsg}",
            "west": west,
            "north": north,
            "width": int(width),
            "height": int(height),
            "res_m": res,
            "transform": [res, 0.0, west, 0.0, -res, north],
        },
        "value_units": "8-bit browse DN (0-255)",
        "calibration": "NOT calibrated gamma0; browse quicklooks are independently stretched display images",
        "georeferencing": {
            "method": "linear mapping of browse PNG extent to ASF footprint bbox",
            "footprint_bbox_wgs84": list(fp_bbox),
            "note": "browse PNG has no embedded geotransform (KML sidecar is login-protected); error is kilometres",
        },
        "scenes": records,
        "changes": changes,
        "files": [
            f"nisar_hh_{dates[0].replace('-', '')}.tif",
            f"nisar_hv_{dates[0].replace('-', '')}.tif",
            f"nisar_hh_{dates[1].replace('-', '')}.tif",
            f"nisar_hv_{dates[1].replace('-', '')}.tif",
            "nisar_change_HH.tif",
            "nisar_change_HV.tif",
            "nisar_hh_latest.tif",
            "nisar_preview.png",
        ],
        "limitations": [
            "Browse PNGs are 8-bit quicklooks, not the GCOV linear-power rasters.",
            "Each polarization/date is stretched independently, so DN is not radiometrically comparable across dates.",
            "Georeferencing is a linear approximation from the scene footprint; error is kilometres.",
            "Change GeoTIFFs are display-only DN differences, not calibrated dB change.",
            "For calibrated gamma0/sigma0 use the --hdf5 mode with an Earthdata Login.",
        ],
    }
    meta_path = out_dir / "nisar_browse_metadata.json"
    meta_path.write_text(json.dumps(meta, indent=2))
    print(f"  wrote {meta_path}")

    if make_preview:
        make_browse_preview(out_dir, dates, meta)
    return meta


def make_browse_preview(out_dir: Path, dates: tuple[str, str], meta: dict) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import rasterio

    da = dates[0].replace("-", "")
    db = dates[1].replace("-", "")
    panels = [
        (f"nisar_hh_{da}.tif", f"HH browse DN {dates[0]}", "gray", (0, 255)),
        (f"nisar_hh_{db}.tif", f"HH browse DN {dates[1]}", "gray", (0, 255)),
        ("nisar_change_HH.tif", "HH DN change (later - earlier)", "RdBu_r", (-80, 80)),
        ("nisar_change_HV.tif", "HV DN change (later - earlier)", "RdBu_r", (-60, 60)),
    ]
    fig, axes = plt.subplots(2, 2, figsize=(10, 11), constrained_layout=True)
    for ax, (fname, title, cmap, lim) in zip(axes.ravel(), panels):
        path = out_dir / fname
        if not path.exists():
            ax.set_axis_off()
            ax.set_title(f"{title} (missing)")
            continue
        with rasterio.open(path) as ds:
            arr = ds.read(1).astype("float32")
            nodata = ds.nodata
            if nodata is not None:
                arr[arr == nodata] = np.nan
            extent = (ds.bounds.left, ds.bounds.right, ds.bounds.bottom, ds.bounds.top)
        if lim is None:
            vals = arr[np.isfinite(arr)]
            lim = tuple(np.percentile(vals, [2, 98])) if vals.size else (-1, 1)
        im = ax.imshow(arr, extent=extent, cmap=cmap, vmin=lim[0], vmax=lim[1], interpolation="nearest")
        ax.set_title(title, fontsize=9)
        ax.set_xticks([])
        ax.set_yticks([])
        cb = fig.colorbar(im, ax=ax, shrink=0.8, pad=0.02)
        cb.set_label("DN" if "change" not in fname else "DN change", fontsize=8)
    fig.suptitle(
        "NISAR L-band GCOV browse fallback over Elin Pelin, Bulgaria\n"
        "raw 8-bit quicklook values; display-only, not calibrated gamma0",
        fontsize=11,
    )
    out = out_dir / "nisar_preview.png"
    fig.savefig(out, dpi=180)
    plt.close(fig)
    print(f"  wrote {out}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)
    # The task-facing interface is `--browse` / `--hdf5`; accept those as
    # aliases for the `browse` / `h5` subcommands.
    if "--browse" in argv:
        argv = [a for a in argv if a != "--browse"]
        argv.insert(0, "browse")
    if "--hdf5" in argv:
        argv = [a for a in argv if a != "--hdf5"]
        argv.insert(0, "h5")

    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Flag aliases: --browse == 'browse', --hdf5 == 'h5'.\n"
            "Examples:\n"
            "  python scripts/nisar_extract.py --browse --dates 2026-06-20 2026-10-06\n"
            "  python scripts/nisar_extract.py --hdf5 /path/to/NISAR_..._20260620...h5\n"
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_search = sub.add_parser("search", help="query the ASF SearchAPI for GCOV scenes")
    p_search.add_argument("--bbox", nargs=4, type=float, default=DEFAULT_BBOX, metavar=("W", "S", "E", "N"))
    p_search.add_argument("--start", default="2026-06-01T00:00:00Z")
    p_search.add_argument("--end", default="2026-12-31T23:59:59Z")
    p_search.add_argument("--track", type=int, default=None)
    p_search.add_argument("--out", type=Path, default=CACHE_DIR / "search.json")

    p_inspect = sub.add_parser("inspect", help="print the GCOV HDF5 tree and attributes")
    p_inspect.add_argument("h5", type=Path)

    p_h5 = sub.add_parser("h5", help="calibrated extraction from a local GCOV HDF5 file")
    p_h5.add_argument("h5", nargs="+", type=Path)
    p_h5.add_argument("--bbox", nargs=4, type=float, default=DEFAULT_BBOX, metavar=("W", "S", "E", "N"))
    p_h5.add_argument("--out", type=Path, default=OUT_DIR)
    p_h5.add_argument("--pols", nargs="+", default=["HHHH", "HVHV"])
    p_h5.add_argument("--sigma0", action="store_true")
    p_h5.add_argument("--res", type=float, default=None)
    p_h5.add_argument("--label", default=None, help="output date/prefix (default: parse from filename)")
    p_h5.add_argument("--change", action="store_true", help="write nisar_change_<pol>.tif for two dates")

    p_browse = sub.add_parser("browse", help="public browse-PNG fallback")
    p_browse.add_argument("--scene-json", type=Path, default=CACHE_DIR / "search.json")
    p_browse.add_argument("--dates", nargs=2, required=True, metavar=("EARLY", "LATE"))
    p_browse.add_argument(
        "--grid",
        nargs=5,
        type=float,
        default=DEFAULT_GRID,
        metavar=("WEST", "NORTH", "WIDTH", "HEIGHT", "RES"),
    )
    p_browse.add_argument("--epsg", type=int, default=32634)
    p_browse.add_argument("--out", type=Path, default=OUT_DIR)
    p_browse.add_argument("--no-preview", action="store_true")

    args = parser.parse_args(argv)

    if args.command == "search":
        scenes = search_scenes(tuple(args.bbox), args.start, args.end, args.track)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(scenes, indent=2))
        print(f"{len(scenes)} scenes -> {args.out}")
        for s in scenes:
            print(scene_summary(s))
    elif args.command == "inspect":
        inspect_h5(args.h5)
    elif args.command == "h5":
        out = Path(args.out)
        for h5 in args.h5:
            print(f"== {h5}")
            extract_h5(
                h5,
                tuple(args.bbox),
                out,
                pols=tuple(args.pols),
                sigma0=args.sigma0,
                res=args.res,
                label=args.label,
            )
        if args.change and len(args.h5) == 2:
            dates = sorted(_date_from_name(Path(h).name) for h in args.h5)
            for pol in ("HH", "HV"):
                combine_change(out, dates[0], dates[1], pol)
    elif args.command == "browse":
        grid = (float(args.grid[0]), float(args.grid[1]), int(args.grid[2]), int(args.grid[3]), float(args.grid[4]))
        extract_browse(
            args.scene_json,
            tuple(args.dates),
            Path(args.out),
            grid=grid,
            epsg=args.epsg,
            make_preview=not args.no_preview,
        )
    else:  # pragma: no cover
        parser.error(f"unknown command {args.command}")


if __name__ == "__main__":
    main()
