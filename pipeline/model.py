"""Weather-normalised expected-condition model and leak-likelihood fusion.

The model learns what VV backscatter, NDMI and land-surface temperature should
look like given rainfall history, soil moisture, evapotranspiration, season,
land cover and soil.  Positive/negative residuals are the unexplained part --
the part we attribute to a local water source (a leaking pipe) after testing
that the anomaly clusters on the pipeline corridor.

Outputs (outputs/):
  soil_moisture_anomaly.tif   relative dry-season moisture anomaly, 0-100
  leak_likelihood.tif         corridor-weighted leak screening score, 0-100
  persistence.tif             fraction of dry-season dates with wet residual
  thermal_anomaly.tif         evaporative-cooling score
  confidence.tif              data-density / evidence-agreement score
  hotspots.csv / hotspots.json
  validation.json / model_metrics.json
  scores.npz                  raw arrays for the map builder
"""
from __future__ import annotations

import json
import warnings
from datetime import datetime
from pathlib import Path

import geopandas as gpd
import lightgbm as lgb
import numpy as np
import pandas as pd
import rasterio
from pyproj import Transformer
from rasterio.features import rasterize
from scipy.ndimage import distance_transform_edt, maximum_filter, uniform_filter
from scipy.stats import rankdata
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

from pipeline.config import INTERIM, OUTPUTS, RAW, VECTORS, analysis_grid
from pipeline.features import (
    WEATHER_COLS,
    load_lst,
    load_s1,
    load_s2,
    load_static,
    load_weather,
    local_std,
    nearest_index,
    static_design,
)

warnings.filterwarnings("ignore", category=RuntimeWarning)
RNG = np.random.default_rng(42)
TRAIN_END = pd.Timestamp("2025-07-01")
VAL_END = pd.Timestamp("2026-01-01")
DRY_MONTHS = (6, 7, 8, 9)


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _read_tif(path: Path, grid: dict, resampling=rasterio.enums.Resampling.bilinear) -> np.ndarray | None:
    if not path.exists():
        return None
    from rasterio.warp import reproject

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


def _save_tif(arr: np.ndarray, path: Path, grid: dict, dtype: str = "float32") -> None:
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=grid["height"],
        width=grid["width"],
        count=1,
        dtype=dtype,
        crs=grid["crs"],
        transform=grid["transform"],
        nodata=np.nan,
        compress="deflate",
        predictor=3,
    ) as ds:
        ds.write(arr.astype(dtype), 1)


def _zscore_by_class(resid: np.ndarray, lc: np.ndarray, train_mask: np.ndarray) -> np.ndarray:
    """Robust z-score using per-land-cover training residual median/MAD."""
    z = np.full(resid.shape, np.nan, dtype="float32")
    for cls in np.unique(lc[np.isfinite(lc)]):
        m = (lc == cls) & train_mask & np.isfinite(resid)
        if m.sum() < 100:
            continue
        med = np.nanmedian(resid[m])
        mad = np.nanmedian(np.abs(resid[m] - med))
        scale = 1.4826 * mad
        if not np.isfinite(scale) or scale < 1e-6:
            scale = np.nanstd(resid[m]) or 1.0
        sel = lc == cls
        z[sel] = (resid[sel] - med) / scale
    # fallback for pixels without a class
    m = np.isfinite(resid) & ~np.isfinite(z)
    if m.any():
        med = np.nanmedian(resid[train_mask & np.isfinite(resid)])
        mad = np.nanmedian(np.abs(resid[train_mask & np.isfinite(resid)] - med))
        z[m] = (resid[m] - med) / (1.4826 * mad + 1e-6)
    return z


def _landcover_ids(lc: np.ndarray) -> np.ndarray:
    return np.where(np.isfinite(lc), np.rint(lc), -1).astype("int16")


# --------------------------------------------------------------------------- #
# build the training table
# --------------------------------------------------------------------------- #
def build_table(dates, pix_idx, s1, s2, lst, weather, Sx, grid):
    h, w = grid["height"], grid["width"]
    flat = lambda a: a.ravel()[pix_idx] if a.ndim == 2 else a
    rows = []
    meta = []
    for di, date in enumerate(dates):
        ts = pd.Timestamp(date)
        vv = s1["vv"][di]
        vh = s1["vh"][di]
        ndmi_i = nearest_index(s2["dates"], ts, 10)
        lst_i = nearest_index(lst["dates"], ts, 10)
        ndmi = s2["ndmi"][ndmi_i] if ndmi_i is not None else np.full((h, w), np.nan, "float32")
        ndvi = s2["ndvi"][ndmi_i] if ndmi_i is not None else np.full((h, w), np.nan, "float32")
        lstv = lst["lst"][lst_i] if lst_i is not None else np.full((h, w), np.nan, "float32")
        if lst_i is not None:
            lstv = np.where((lstv > -20) & (lstv < 60), lstv, np.nan)
            lst_anom = lstv - np.nanmedian(lstv)
        else:
            lst_anom = np.full((h, w), np.nan, "float32")
        vv_std = local_std(vv, 3)

        wrow = weather.loc[ts, WEATHER_COLS].to_numpy(dtype="float32") if ts in weather.index else np.full(len(WEATHER_COLS), np.nan, "float32")
        temporal = np.column_stack(
            [
                flat(vv),
                flat(vh),
                flat(vv_std),
                flat(ndmi),
                flat(ndvi),
                flat(lstv),
                flat(lst_anom),
            ]
        )
        X = np.concatenate(
            [
                Sx[pix_idx],
                temporal,
                np.broadcast_to(wrow, (len(pix_idx), len(wrow))),
            ],
            axis=1,
        )
        rows.append(X.astype("float32"))
        meta.append(
            np.column_stack(
                [
                    np.full(len(pix_idx), di, dtype="int32"),
                    pix_idx,
                ]
            )
        )
    X = np.vstack(rows)
    meta = np.vstack(meta)
    return X, meta


def temporal_names():
    return ["vv", "vh", "vv_std3", "ndmi", "ndvi", "lst", "lst_anom"] + WEATHER_COLS


# --------------------------------------------------------------------------- #
def main() -> None:
    grid = analysis_grid()
    h, w = grid["height"], grid["width"]
    print("loading ...")
    s1 = load_s1()
    s2 = load_s2()
    lst = load_lst()
    weather = load_weather()
    static = load_static(grid)

    s1_dates = pd.to_datetime(s1["dates"])
    keep = (s1_dates >= pd.Timestamp("2022-01-01")) & (s1_dates <= pd.Timestamp("2026-11-14"))
    idx = np.flatnonzero(keep)
    order = np.argsort(s1_dates[idx].to_numpy())
    idx = idx[order]
    for k in ("vv", "vh", "valid"):
        s1[k] = s1[k][idx]
    s1["dates"] = s1_dates[idx].to_numpy()
    dates = pd.to_datetime(s1["dates"])
    print(f"S1 dates used: {len(dates)}  {dates.min().date()} -> {dates.max().date()}")

    # clip implausible optical values
    for k in ("ndmi", "ndvi"):
        s2[k] = np.clip(s2[k], -1.0, 1.0)

    Sx, snames, valid2d = static_design(static)
    valid_idx = np.flatnonzero(valid2d.ravel())
    lc = _landcover_ids(static["landcover"])
    lc_flat = lc.ravel()

    # distance priors
    dist_water = _read_tif(INTERIM / "dist_water_main.tif", grid)
    dist_gas = _read_tif(INTERIM / "dist_gas.tif", grid)
    if dist_water is None:
        dist_water = _read_tif(INTERIM / "dist_water.tif", grid)
    if dist_water is None:
        dist_water = np.full((h, w), 1e4, dtype="float32")
    if dist_gas is None:
        dist_gas = np.full((h, w), 1e4, dtype="float32")

    # sample pixels: corridor + random background
    corridor = ((dist_water.ravel() < 120) | (dist_gas.ravel() < 120)) & valid2d.ravel()
    corridor_idx = np.flatnonzero(corridor)
    pool = np.setdiff1d(valid_idx, corridor_idx, assume_unique=False)
    n_bg = min(14000, len(pool))
    bg_idx = RNG.choice(pool, size=n_bg, replace=False) if n_bg else np.array([], dtype=int)
    pix_idx = np.unique(np.concatenate([corridor_idx, bg_idx]))
    print(f"pixels: {len(pix_idx)} ({len(corridor_idx)} corridor, {len(bg_idx)} background)")

    X, meta = build_table(dates.to_numpy(), pix_idx, s1, s2, lst, weather, Sx, grid)
    names = snames + temporal_names()
    print("table", X.shape)

    # targets from the temporal block
    t0 = len(snames)
    y_vv = X[:, t0 + 0]
    y_ndmi = X[:, t0 + 3]
    y_lst = X[:, t0 + 5]

    date_of_row = dates.to_numpy()[meta[:, 0]]
    train = date_of_row < TRAIN_END.to_datetime64()
    val = (date_of_row >= TRAIN_END.to_datetime64()) & (date_of_row < VAL_END.to_datetime64())
    test = date_of_row >= VAL_END.to_datetime64()

    # drop target columns from features to avoid leakage
    drop = {t0 + 0, t0 + 3, t0 + 5, t0 + 6}  # vv, ndmi, lst, lst_anom
    feat_idx = [i for i in range(X.shape[1]) if i not in drop]
    Xf = X[:, feat_idx]
    fnames = [names[i] for i in feat_idx]

    models: dict[str, lgb.LGBMRegressor] = {}
    metrics: dict[str, dict] = {}
    for target_name, y in (("vv", y_vv), ("ndmi", y_ndmi)):
        if target_name == "lst":
            ok = np.isfinite(y) & (y > -20) & (y < 60)
        else:
            ok = np.isfinite(y)
        tr = train & ok
        te = test & ok
        m = lgb.LGBMRegressor(
            objective="regression_l1",
            n_estimators=450,
            learning_rate=0.045,
            num_leaves=63,
            min_child_samples=40,
            subsample=0.8,
            subsample_freq=1,
            colsample_bytree=0.85,
            reg_lambda=1.0,
            n_jobs=-1,
            random_state=42,
            verbose=-1,
        )
        m.fit(Xf[tr], y[tr])
        pred = m.predict(Xf[te])
        metrics[target_name] = {
            "n_train": int(tr.sum()),
            "n_test": int(te.sum()),
            "mae": float(mean_absolute_error(y[te], pred)),
            "rmse": float(np.sqrt(mean_squared_error(y[te], pred))),
            "r2": float(r2_score(y[te], pred)),
            "target_mean": float(np.nanmean(y[te])),
            "target_std": float(np.nanstd(y[te])),
        }
        models[target_name] = m
        print(target_name, metrics[target_name])

    # full residual cubes for all valid pixels, per date
    n = len(dates)
    z_moist = np.full((n, h, w), np.nan, dtype="float16")
    z_therm = np.full((n, h, w), np.nan, dtype="float16")
    vv_resid = np.full((n, h, w), np.nan, dtype="float16")
    ndmi_resid = np.full((n, h, w), np.nan, dtype="float16")
    lst_resid = np.full((n, h, w), np.nan, dtype="float16")
    lc_full = lc.ravel()

    # residual scaling from training rows
    train_rows = train & np.isfinite(y_vv)
    resid_train_vv = y_vv[train_rows] - models["vv"].predict(Xf[train_rows])
    stats_vv = (np.nanmedian(resid_train_vv), 1.4826 * np.nanmedian(np.abs(resid_train_vv - np.nanmedian(resid_train_vv))) + 0.1)
    tr_ndmi = train & np.isfinite(y_ndmi)
    resid_train_ndmi = y_ndmi[tr_ndmi] - models["ndmi"].predict(Xf[tr_ndmi])
    stats_ndmi = (np.nanmedian(resid_train_ndmi), 1.4826 * np.nanmedian(np.abs(resid_train_ndmi - np.nanmedian(resid_train_ndmi))) + 0.005)
    print("residual scales", {"vv": stats_vv, "ndmi": stats_ndmi})

    for di, date in enumerate(dates):
        ts = pd.Timestamp(date)
        vv = s1["vv"][di]
        vh = s1["vh"][di]
        ndmi_i = nearest_index(s2["dates"], ts, 10)
        lst_i = nearest_index(lst["dates"], ts, 10)
        ndmi = s2["ndmi"][ndmi_i] if ndmi_i is not None else np.full((h, w), np.nan, "float32")
        ndvi = s2["ndvi"][ndmi_i] if ndmi_i is not None else np.full((h, w), np.nan, "float32")
        lstv = lst["lst"][lst_i] if lst_i is not None else np.full((h, w), np.nan, "float32")
        if lst_i is not None:
            lstv = np.where((lstv > -20) & (lstv < 60), lstv, np.nan)
        lst_anom = lstv - np.nanmedian(lstv)
        vv_std = local_std(vv, 3)
        wrow = weather.loc[ts, WEATHER_COLS].to_numpy(dtype="float32") if ts in weather.index else np.full(len(WEATHER_COLS), np.nan, "float32")

        temporal = np.column_stack(
            [
                vv.ravel()[valid_idx],
                vh.ravel()[valid_idx],
                vv_std.ravel()[valid_idx],
                ndmi.ravel()[valid_idx],
                ndvi.ravel()[valid_idx],
                lstv.ravel()[valid_idx],
                lst_anom.ravel()[valid_idx],
            ]
        )
        Xv = np.concatenate(
            [Sx[valid_idx], temporal, np.broadcast_to(wrow, (len(valid_idx), len(wrow)))],
            axis=1,
        )[:, feat_idx].astype("float32")

        p_vv = models["vv"].predict(Xv)
        p_ndmi = models["ndmi"].predict(Xv)
        r_vv = temporal[:, 0] - p_vv
        r_ndmi = temporal[:, 3] - p_ndmi

        z_vv = (r_vv - stats_vv[0]) / stats_vv[1]
        z_ndmi = (r_ndmi - stats_ndmi[0]) / stats_ndmi[1]
        zm = np.nanmean(np.column_stack([z_vv, z_ndmi]), axis=1)

        # direct local thermal anomaly: cooler than the scene median = positive
        la = temporal[:, 6]
        if np.isfinite(la).sum() > 100:
            med_la = np.nanmedian(la)
            mad_la = np.nanmedian(np.abs(la - med_la))
            zt = -(la - med_la) / (1.4826 * mad_la + 0.3)
        else:
            zt = np.full(len(la), np.nan)

        def put(cube, vals):
            flat = cube[di].ravel()
            flat[valid_idx] = vals.astype("float16")
            cube[di] = flat.reshape(h, w)

        put(z_moist, np.clip(zm, -6, 6))
        put(z_therm, np.clip(zt, -6, 6))
        put(vv_resid, r_vv)
        put(ndmi_resid, r_ndmi)
        if di % 40 == 0:
            print("  residual cube", di + 1, "/", n)

    dts = pd.to_datetime(dates)
    jj = np.isin(dts.month, DRY_MONTHS)
    years = sorted(set(dts[jj].year))
    print("dry-season years", years)

    def year_mean(cube, year):
        m = jj & (dts.year == year)
        if m.sum() == 0:
            return np.full((h, w), np.nan, "float32")
        return np.nanmean(cube[m].astype("float32"), axis=0)

    moist_years = {y: year_mean(z_moist, y) for y in years}
    therm_years = {y: year_mean(z_therm, y) for y in years}
    moist_dry = np.nanmean(np.stack([moist_years[y] for y in years]), axis=0)
    thermal = np.nanmean(np.stack([therm_years[y] for y in years]), axis=0)
    persist = np.nanmean((z_moist[jj].astype("float32") > 0.5), axis=0)
    n_obs = np.sum(np.isfinite(z_moist[jj].astype("float32")), axis=0)
    agreement = (
        (moist_dry > 0.3).astype("float32")
        + (persist > 0.3).astype("float32")
        + (thermal > 0.2).astype("float32")
    ) / 3.0

    # Smooth the evidence to the scale of a shallow leakage plume (3x3 = 60 m).
    def smooth_nan(a, size=3):
        v = np.isfinite(a)
        x = np.where(v, a, 0.0)
        num = uniform_filter(x, size=size, mode="nearest")
        den = uniform_filter(v.astype("float32"), size=size, mode="nearest")
        return np.where(den > 0.2, num / np.maximum(den, 1e-6), np.nan)

    moist_s = smooth_nan(moist_dry, 3)
    persist_s = smooth_nan(persist, 3)
    thermal_s = smooth_nan(thermal, 3)

    # optional NISAR L-band change layer
    nisar_score = np.full((h, w), np.nan, dtype="float32")
    nisar_raw = None
    for cand in [
        RAW / "nisar" / "nisar_change_HH.tif",
        RAW / "nisar" / "nisar_change_hh.tif",
        RAW / "nisar" / "change_HH.tif",
    ]:
        if cand.exists():
            nisar_raw = _read_tif(cand, grid)
            break
    nisar_used = False
    if nisar_raw is not None and np.isfinite(nisar_raw).mean() > 0.2:
        med = np.nanmedian(nisar_raw)
        mad = np.nanmedian(np.abs(nisar_raw - med))
        nisar_score = np.clip((nisar_raw - med) / (1.4826 * mad + 1e-6), 0, 3) / 3.0
        nisar_used = True
        print("NISAR change layer integrated")

    # leak score
    moist_norm = np.clip(np.nan_to_num(moist_s, nan=-1) / 2.5, 0, 1)
    persist_norm = np.clip(np.nan_to_num(persist_s, nan=0), 0, 1)
    therm_norm = np.clip(np.nan_to_num(thermal_s, nan=-1) / 2.5, 0, 1)
    # NISAR browse change is shown as an independent layer, not used in the
    # quantitative score: it is 8-bit browse imagery, not calibrated gamma0.
    weights = [0.55, 0.25, 0.20]
    parts = [moist_norm, persist_norm, therm_norm]
    leak_raw = np.sum([wi * pi for wi, pi in zip(weights, parts)], axis=0)

    water_w = np.exp(-((dist_water / 60.0) ** 2))
    gas_w = np.exp(-((dist_gas / 60.0) ** 2))
    pipe_w = np.maximum(water_w, 0.8 * gas_w)
    leak_weighted = leak_raw * (0.18 + 0.82 * pipe_w)

    # Interpretable scores: moisture is centred at 50 (dry < 50 < wet);
    # leak is a physical evidence score with corridor weighting, not a percentile,
    # so the map keeps a meaningful gradient instead of saturating.
    sm_score = 50.0 + 25.0 * np.clip(moist_s, -2, 2)
    leak_phys = leak_raw / 0.45
    leak_score = 100.0 * np.clip(leak_phys, 0, 1) * (0.05 + 0.95 * pipe_w)

    # confidence
    confidence = 100.0 * np.clip(n_obs / 25.0, 0, 1) * (0.4 + 0.6 * agreement)
    confidence = np.where(valid2d, confidence, np.nan)

    # ------------------------------------------------------------------ #
    # pipeline enrichment test: real corridor vs. translated placebo lines
    # ------------------------------------------------------------------ #
    validation: dict = {"model_metrics": metrics, "nisar_layer_present": nisar_used}
    water_main = VECTORS / "water_main.geojson"
    if water_main.exists():
        gdf = gpd.read_file(water_main).to_crs(grid["crs"])
        geom = gdf.geometry.iloc[0]
        actual_mask = rasterize(
            [(geom, 1)], out_shape=(h, w), transform=grid["transform"], fill=0, all_touched=True
        ).astype(bool)
        valid_m = valid2d & np.isfinite(moist_dry)
        actual_vals = moist_dry[actual_mask & valid_m]
        actual = np.nanmean(actual_vals)
        actual_p95 = np.nanpercentile(actual_vals, 95) if np.isfinite(actual_vals).sum() > 20 else np.nan
        rand, rand_p95 = [], []
        for _ in range(200):
            dx, dy = RNG.uniform(-1800, 1800, 2)
            from shapely.affinity import translate

            g3 = translate(geom, xoff=dx, yoff=dy)
            m3 = rasterize(
                [(g3, 1)], out_shape=(h, w), transform=grid["transform"], fill=0, all_touched=True
            ).astype(bool)
            if (m3 & valid_m).sum() < 20:
                continue
            vals = moist_dry[m3 & valid_m]
            rand.append(np.nanmean(vals))
            rand_p95.append(np.nanpercentile(vals, 95))
        if rand:
            rand = np.array(rand)
            rand_p95 = np.array(rand_p95)
            p = float((1 + np.sum(rand >= actual)) / (1 + len(rand)))
            p95 = float((1 + np.sum(rand_p95 >= actual_p95)) / (1 + len(rand_p95)))
            validation["pipeline_enrichment"] = {
                "actual_corridor_mean": float(actual),
                "placebo_mean": float(np.mean(rand)),
                "placebo_p95": float(np.percentile(rand, 95)),
                "ratio": float(actual / (np.mean(rand) + 1e-9)),
                "p_value": p,
                "actual_corridor_p95": float(actual_p95),
                "placebo_p95_of_p95": float(np.percentile(rand_p95, 95)),
                "ratio_p95": float(actual_p95 / (np.mean(rand_p95) + 1e-9)),
                "p_value_p95": p95,
                "n_placebo": int(len(rand)),
                "buffer_m": 30,
            }
            print("pipeline enrichment", validation["pipeline_enrichment"])

    # ------------------------------------------------------------------ #
    # hotspots
    # ------------------------------------------------------------------ #
    smooth = np.nan_to_num(leak_score, nan=0)
    mx = maximum_filter(smooth, size=7)
    cand = np.argwhere((smooth == mx) & (smooth > 30))
    cand = sorted(cand, key=lambda rc: smooth[tuple(rc)], reverse=True)
    chosen = []
    for r, c in cand:
        if all((r - rr) ** 2 + (c - cc) ** 2 > (150 / grid["res"]) ** 2 for rr, cc, _ in chosen):
            chosen.append((int(r), int(c), float(smooth[r, c])))
        if len(chosen) >= 12:
            break
    tf = Transformer.from_crs(grid["crs"], "EPSG:4326", always_xy=True)
    hotspots = []
    for r, c, sc in chosen:
        x = grid["transform"].c + (c + 0.5) * grid["res"]
        y = grid["transform"].f - (r + 0.5) * grid["res"]
        lon, lat = tf.transform(x, y)
        # best dates at the hotspot (3x3 neighbourhood)
        nb = z_moist[:, max(0, r - 1) : r + 2, max(0, c - 1) : c + 2].astype("float32")
        tsmean = np.nanmean(nb, axis=(1, 2))
        pool = np.flatnonzero(jj & np.isfinite(tsmean))
        good = pool[np.argsort(tsmean[pool])[-3:][::-1]] if len(pool) else np.array([], dtype=int)
        hotspots.append(
            {
                "id": len(hotspots) + 1,
                "lat": float(lat),
                "lon": float(lon),
                "row": r,
                "col": c,
                "leak_score": round(sc, 1),
                "moisture_z": round(float(moist_dry[r, c]), 2),
                "persistence": round(float(persist[r, c]), 2),
                "thermal_z": round(float(thermal[r, c]), 2),
                "confidence": round(float(confidence[r, c]), 0),
                "dist_water_m": round(float(dist_water[r, c]), 0),
                "dist_gas_m": round(float(dist_gas[r, c]), 0),
                "landcover": int(static["landcover"][r, c]) if np.isfinite(static["landcover"][r, c]) else None,
                "top_dates": [str(pd.Timestamp(dates[i]).date()) for i in good if np.isfinite(tsmean[i])],
                "top_z": [round(float(tsmean[i]), 2) for i in good if np.isfinite(tsmean[i])],
            }
        )
    (OUTPUTS / "hotspots.json").write_text(json.dumps(hotspots, indent=2))
    pd.DataFrame(hotspots).to_csv(OUTPUTS / "hotspots.csv", index=False)

    # ------------------------------------------------------------------ #
    # save
    # ------------------------------------------------------------------ #
    lay = {
        "soil_moisture_anomaly": sm_score,
        "leak_likelihood": leak_score,
        "persistence": np.where(valid2d, persist, np.nan),
        "thermal_anomaly": np.where(valid2d, thermal, np.nan),
        "confidence": confidence,
        "moisture_raw_z": np.where(valid2d, moist_dry, np.nan),
        "moisture_smooth_z": np.where(valid2d, moist_s, np.nan),
        "nisar_score": np.where(valid2d, nisar_score, np.nan) if nisar_used else None,
    }
    for name, a in lay.items():
        if a is not None:
            _save_tif(a, OUTPUTS / f"{name}.tif", grid)

    _save_tif(dist_water, OUTPUTS / "dist_water.tif", grid)

    np.savez_compressed(
        OUTPUTS / "scores.npz",
        sm_score=sm_score.astype("float32"),
        leak_score=leak_score.astype("float32"),
        moist_dry=moist_dry.astype("float32"),
        moist_smooth=moist_s.astype("float32"),
        persist=persist.astype("float32"),
        thermal=thermal.astype("float32"),
        confidence=confidence.astype("float32"),
        valid=valid2d,
        landcover=lc,
        n_obs=n_obs.astype("int16"),
        years=np.array(years),
        year_moist=np.stack([moist_years[y] for y in years]).astype("float32"),
        grid_transform=np.array([grid["transform"].a, grid["transform"].b, grid["transform"].c, grid["transform"].d, grid["transform"].e, grid["transform"].f]),
        grid_crs=grid["crs"],
    )

    # residual cubes for time-series charts
    np.savez_compressed(
        INTERIM / "residual_cubes.npz",
        z_moist=z_moist,
        z_thermal=z_therm,
        dates=dates.to_numpy().astype("datetime64[D]").astype(str),
    )

    validation["hotspots"] = hotspots
    validation["generated"] = datetime.utcnow().isoformat() + "Z"
    validation["s1_dates"] = int(len(dates))
    validation["dry_season_dates"] = int(jj.sum())
    validation["pixels_valid"] = int(valid2d.sum())
    (OUTPUTS / "validation.json").write_text(json.dumps(validation, indent=2))
    (OUTPUTS / "model_metrics.json").write_text(json.dumps(metrics, indent=2))
    print("saved outputs to", OUTPUTS)


if __name__ == "__main__":
    main()
