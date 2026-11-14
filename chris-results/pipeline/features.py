"""Feature engineering: align static layers, weather, S1/S2/LST onto one grid."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
from rasterio.enums import Resampling
from rasterio.warp import reproject

from pipeline.config import (
    INTERIM,
    MET,
    RAW,
    STATIC,
    analysis_grid,
)

STATIC_FILES = {
    "landcover": ("worldcover_aoi.tif", Resampling.nearest),
    "dem": ("dem_aoi.tif", Resampling.bilinear),
    "slope": ("slope_aoi.tif", Resampling.bilinear),
    "sand": ("soil_sand_0_5.tif", Resampling.bilinear),
    "clay": ("soil_clay_0_5.tif", Resampling.bilinear),
    "silt": ("soil_silt_0_5.tif", Resampling.bilinear),
    "soc": ("soil_soc_0_5.tif", Resampling.bilinear),
    "bd": ("soil_bdod_0_5.tif", Resampling.bilinear),
    "dist_built": ("dist_built_aoi.tif", Resampling.bilinear),
    "dist_road": ("dist_road_aoi.tif", Resampling.bilinear),
}

LC_NAMES = {
    10: "tree",
    20: "shrub",
    30: "grass",
    40: "crop",
    50: "built",
    60: "bare",
    70: "snow",
    80: "water",
    90: "wetland",
    95: "mangrove",
    100: "moss",
}


def _resample(path: Path, grid: dict, resampling: Resampling) -> np.ndarray:
    with rasterio.open(path) as ds:
        dest = np.full((grid["height"], grid["width"]), np.nan, dtype="float32")
        reproject(
            source=rasterio.band(ds, 1),
            destination=dest,
            dst_transform=grid["transform"],
            dst_crs=grid["crs"],
            src_nodata=ds.nodata,
            dst_nodata=np.nan,
            resampling=resampling,
        )
    return dest


def load_static(grid: dict | None = None) -> dict[str, np.ndarray]:
    grid = grid or analysis_grid()
    out = {}
    for name, (fname, resampling) in STATIC_FILES.items():
        p = STATIC / fname
        if not p.exists():
            print(f"static missing: {p}")
            out[name] = np.full((grid["height"], grid["width"]), np.nan, dtype="float32")
            continue
        out[name] = _resample(p, grid, resampling)
    # landcover to integer classes; keep a mask of valid pixels
    lc = out["landcover"]
    lc = np.where(np.isfinite(lc), np.rint(lc), np.nan)
    out["landcover"] = lc
    return out


def static_design(static: dict[str, np.ndarray]) -> tuple[np.ndarray, list[str], np.ndarray]:
    """Flatten static layers into a design matrix and one-hot land-cover columns."""
    lc = static["landcover"]
    valid = np.isfinite(lc) & (lc != 80)  # exclude open water
    cols, names = [], []

    def add(name, a):
        cols.append(a.ravel().astype("float32"))
        names.append(name)

    add("dem", static["dem"])
    add("slope", static["slope"])
    add("sand", static["sand"])
    add("clay", static["clay"])
    add("silt", static["silt"])
    add("soc", static["soc"])
    add("bd", static["bd"])
    add("dist_built", np.log1p(np.maximum(static["dist_built"], 0)))
    add("dist_road", np.log1p(np.maximum(static["dist_road"], 0)))

    for cls, lcname in LC_NAMES.items():
        if cls in (80,):  # water excluded, still encode if present
            continue
        add(f"lc_{lcname}", (lc == cls).astype("float32"))

    X = np.stack(cols, axis=1)
    return X, names, valid


def load_weather() -> pd.DataFrame:
    p = MET / "weather_daily.csv"
    w = pd.read_csv(p, parse_dates=["date"]).set_index("date").sort_index()
    w = w[~w.index.duplicated(keep="first")]
    # daily continuous index
    idx = pd.date_range("2022-01-01", "2026-11-14", freq="D")
    w = w.reindex(idx)
    w.index.name = "date"
    w["precip_sum"] = w["precip_sum"].fillna(0.0)
    for c in ["temp_mean", "temp_min", "temp_max", "rh_mean", "et0_sum", "sm0_7", "sm7_28", "sm28_100", "vpd_mean"]:
        if c in w:
            w[c] = w[c].interpolate(limit=7).ffill().bfill()
    if "radiation_mj_m2" not in w and "radiation_sum" in w:
        w["radiation_mj_m2"] = w["radiation_sum"] * 0.0036

    w["precip_1"] = w["precip_sum"].rolling(1).sum()
    for n in (3, 7, 14, 30, 60):
        w[f"precip_{n}"] = w["precip_sum"].rolling(n, min_periods=1).sum()
    w["temp_mean_3"] = w["temp_mean"].rolling(3, min_periods=1).mean()
    w["temp_mean_7"] = w["temp_mean"].rolling(7, min_periods=1).mean()
    w["temp_max_3"] = w["temp_max"].rolling(3, min_periods=1).max()
    w["et0_7"] = w["et0_sum"].rolling(7, min_periods=1).sum()
    w["et0_30"] = w["et0_sum"].rolling(30, min_periods=1).sum()
    w["vpd_7"] = w["vpd_mean"].rolling(7, min_periods=1).mean()

    # consecutive dry days (precip < 1 mm)
    dry = (w["precip_sum"] < 1.0).astype(int)
    groups = (~dry.astype(bool)).cumsum()
    w["dry_days"] = dry.groupby(groups).cumsum()

    # short-term wetness anomaly vs. the 31-day local mean
    w["sm0_7_anom"] = w["sm0_7"] - w["sm0_7"].rolling(31, center=True, min_periods=10).mean()
    w["sm7_28_anom"] = w["sm7_28"] - w["sm7_28"].rolling(31, center=True, min_periods=10).mean()

    month = w.index.month
    w["precip_30_anom"] = w["precip_30"] - w.groupby(month)["precip_30"].transform("mean")
    w["temp_7_anom"] = w["temp_mean_7"] - w.groupby(month)["temp_mean_7"].transform("mean")

    doy = w.index.dayofyear
    w["doy_sin"] = np.sin(2 * np.pi * doy / 365.25)
    w["doy_cos"] = np.cos(2 * np.pi * doy / 365.25)
    return w


WEATHER_COLS = [
    "precip_1",
    "precip_3",
    "precip_7",
    "precip_14",
    "precip_30",
    "precip_60",
    "temp_mean_3",
    "temp_mean_7",
    "temp_max_3",
    "et0_7",
    "et0_30",
    "sm0_7",
    "sm7_28",
    "sm28_100",
    "vpd_7",
    "dry_days",
    "sm0_7_anom",
    "sm7_28_anom",
    "precip_30_anom",
    "temp_7_anom",
    "doy_sin",
    "doy_cos",
]


def nearest_index(dates: np.ndarray, target: pd.Timestamp, max_days: int) -> int | None:
    if dates is None or len(dates) == 0:
        return None
    d = pd.to_datetime(dates)
    delta = np.abs((d - target).days)
    i = int(np.argmin(delta))
    return i if delta[i] <= max_days else None


def load_s1() -> dict:
    d = np.load(RAW / "s1_stack.npz", allow_pickle=True)
    return {k: d[k] for k in d.files}


def load_s2() -> dict:
    d = np.load(RAW / "s2_stack.npz", allow_pickle=True)
    return {k: d[k] for k in d.files}


def load_lst() -> dict:
    d = np.load(RAW / "lst_stack.npz", allow_pickle=True)
    return {k: d[k] for k in d.files}


def local_std(a: np.ndarray, size: int = 3) -> np.ndarray:
    """Local standard deviation with NaN awareness (fast uniform filter)."""
    from scipy.ndimage import uniform_filter

    v = np.isfinite(a)
    x = np.where(v, a, 0.0)
    n = uniform_filter(v.astype("float32"), size=size, mode="nearest")
    m = uniform_filter(x, size=size, mode="nearest")
    m2 = uniform_filter(x * x, size=size, mode="nearest")
    var = np.maximum(m2 - m * m, 0.0)
    return np.where(v, np.sqrt(var), np.nan).astype("float32")
