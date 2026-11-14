"""Stage 7c: segment x month break-risk model; does NISAR add predictive value?

Design (forecast, leakage-safe):
  * Unit: water-main segment x calendar month. Target: >= 1 recorded break on the segment in that month.
  * Every feature uses only data available BEFORE the month starts (weather and NISAR from the prior
    `feature_window_days`; break history strictly before the month).
  * Baseline M0 (infrastructure + break history + season + weather) is trained on history
    (history_from .. eval_from) and scored on the evaluation months (temporal hold-out).
  * On the evaluation months, two models are compared with the same spatially blocked CV folds:
      A = baseline score only            B = baseline score + NISAR features
    The difference in AUC / average precision / top-5% capture, with a block bootstrap CI, is the
    measured added value of NISAR.
"""
from __future__ import annotations

import json
from datetime import date

import geopandas as gpd
import numpy as np
import pandas as pd
import requests
from scipy.spatial import cKDTree

from .config import UTM_CRS, Config, report_file

BASE_FEATURES = ["log_length_m", "material", "pipe_size_mm", "age_years", "install_year_missing",
                 "prior_breaks_seg", "breaks_seg_5y", "months_since_last_break", "nbr_breaks_2y",
                 "month_sin", "month_cos", "w_fdd", "w_tmin", "w_freeze_thaw_days", "w_precip_mm", "w_snow_cm"]


# --------------------------------------------------------------------------- inputs
def link_breaks(cfg: Config, mains: gpd.GeoDataFrame, inc: gpd.GeoDataFrame) -> pd.DataFrame:
    r = cfg.section("risk")
    inc = inc[inc["is_primary_record"] & ~inc["is_cancelled"] & ~inc["date_suspect"]].to_crs(UTM_CRS)
    mu = mains.to_crs(UTM_CRS)
    ids = set(mu["main_id"].dropna().astype(int))
    direct = inc["asset_id"].isin(ids)
    near = gpd.sjoin_nearest(inc[~direct][["incident_id", "geometry"]], mu[["main_id", "geometry"]],
                             max_distance=r["link_max_distance_m"], distance_col="d").drop_duplicates("incident_id")
    out = pd.concat([
        pd.DataFrame({"incident_id": inc.loc[direct, "incident_id"], "main_id": inc.loc[direct, "asset_id"].astype(int),
                      "link": "asset_id"}),
        pd.DataFrame({"incident_id": near["incident_id"], "main_id": near["main_id"].astype(int), "link": "nearest"})])
    out = gpd.GeoDataFrame(out.merge(inc[["incident_id", "incident_date_local", "geometry"]], on="incident_id"),
                           geometry="geometry", crs=UTM_CRS)
    out["month"] = out["incident_date_local"].dt.to_period("M")
    print(f"  breaks linked to segments: {len(out)} of {len(inc)} ({out['link'].value_counts().to_dict()})")
    return out


def weather_daily(cfg: Config, start: str, end: str) -> pd.DataFrame:
    path = cfg.path("raw_dir") / "open_meteo_daily_kitchener.parquet"
    if path.exists():
        w = pd.read_parquet(path)
        if w.index.min() <= pd.Timestamp(start) and w.index.max() >= pd.Timestamp(end) - pd.Timedelta(days=5):
            return w
    f = cfg.section("features")
    p = {"latitude": f["weather_lat"], "longitude": f["weather_lon"], "start_date": start, "end_date": end,
         "daily": "temperature_2m_mean,temperature_2m_min,temperature_2m_max,precipitation_sum,snowfall_sum",
         "timezone": "America/Toronto"}
    j = requests.get("https://archive-api.open-meteo.com/v1/archive", params=p, timeout=300).json()["daily"]
    w = pd.DataFrame(j).assign(time=lambda d: pd.to_datetime(d["time"])).set_index("time")
    w.to_parquet(path)
    print(f"  daily weather cache -> {report_file(path)}")
    return w


def weather_features(w: pd.DataFrame, months: pd.PeriodIndex, days: int) -> pd.DataFrame:
    rows = []
    for m in months:
        s = m.start_time
        x = w.loc[s - pd.Timedelta(days=days):s - pd.Timedelta(days=1)]
        rows.append({"month": m, "w_fdd": float((-x["temperature_2m_mean"]).clip(lower=0).sum()),
                     "w_tmin": float(x["temperature_2m_min"].min()),
                     "w_freeze_thaw_days": int(((x["temperature_2m_min"] < 0) & (x["temperature_2m_max"] > 0)).sum()),
                     "w_precip_mm": float(x["precipitation_sum"].sum()), "w_snow_cm": float(x["snowfall_sum"].sum())})
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- panel
def build_rows(seg: pd.DataFrame, rows: pd.DataFrame, breaks: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    """Add break-history features to (main_id, month) rows using only breaks before each month."""
    by_seg = {k: np.sort(v.to_numpy(dtype="datetime64[ns]"))
              for k, v in breaks.groupby("main_id")["incident_date_local"]}
    # neighbourhood: breaks within radius of the segment midpoint
    bxy = np.c_[breaks.geometry.x, breaks.geometry.y]
    bt = breaks["incident_date_local"].to_numpy(dtype="datetime64[ns]")
    tree = cKDTree(bxy)
    mid = seg.set_index("main_id")[["mx", "my"]]
    nb = {}
    for mid_id, (x, y) in mid.iterrows():
        idx = tree.query_ball_point((x, y), cfg.section("risk")["neighbour_radius_m"])
        nb[mid_id] = np.sort(bt[idx]) if idx else np.array([], dtype="datetime64[ns]")
    t = rows["month"].dt.start_time.to_numpy(dtype="datetime64[ns]")
    t5 = (rows["month"].dt.start_time - pd.DateOffset(years=5)).to_numpy(dtype="datetime64[ns]")
    t2 = (rows["month"].dt.start_time - pd.DateOffset(years=2)).to_numpy(dtype="datetime64[ns]")
    prior, prior5, since, nbr = (np.zeros(len(rows)) for _ in range(4))
    empty = np.array([], dtype="datetime64[ns]")
    for i, mid_id in enumerate(rows["main_id"].to_numpy()):
        d = by_seg.get(mid_id, empty)
        k = np.searchsorted(d, t[i])
        prior[i] = k
        prior5[i] = k - np.searchsorted(d, t5[i])
        since[i] = (t[i] - d[k - 1]) / np.timedelta64(30, "D") if k else np.nan
        n = nb[mid_id]
        nbr[i] = np.searchsorted(n, t[i]) - np.searchsorted(n, t2[i])
    rows = rows.assign(prior_breaks_seg=prior, breaks_seg_5y=prior5, months_since_last_break=since, nbr_breaks_2y=nbr)
    rows = rows.merge(seg[["main_id", "log_length_m", "material", "pipe_size_mm", "install_year", "block"]], on="main_id")
    rows["age_years"] = rows["month"].dt.year - rows["install_year"]
    rows["install_year_missing"] = rows["install_year"].isna().astype(int)
    mo = rows["month"].dt.month
    rows["month_sin"], rows["month_cos"] = np.sin(2 * np.pi * mo / 12), np.cos(2 * np.pi * mo / 12)
    return rows


# --------------------------------------------------------------------------- NISAR features
def nisar_features(cfg: Config, rows: pd.DataFrame) -> pd.DataFrame:
    """Per (main_id, month): aggregate segment-level NISAR samples from the window before the month."""
    pro = cfg.path("processed_dir")
    days = cfg.section("risk")["feature_window_days"]
    months = rows["month"].unique()
    out = rows[["main_id", "month"]].copy()

    def windowed(tab: pd.DataFrame, tcol: str = "time") -> pd.DataFrame:
        parts = []
        for m in months:
            s = pd.Timestamp(m.start_time, tz="UTC")
            w = tab[(tab[tcol] >= s - pd.Timedelta(days=days)) & (tab[tcol] < s)]
            parts.append(w.assign(month=m))
        return pd.concat(parts, ignore_index=True)

    # GCOV: change vs previous acquisition on the same comparison group (same geometry)
    g = pd.read_parquet(pro / "seg_gcov.parquet").sort_values(["main_id", "comparison_group", "time"])
    for c in ("hh_db", "hv_db", "hh_contrast"):
        g[f"{c}_chg"] = g.groupby(["main_id", "comparison_group"])[c].diff()
    gw = windowed(g).groupby(["main_id", "month"]).agg(
        nis_gcov_hh_db=("hh_db", "mean"), nis_gcov_hv_db=("hv_db", "mean"), nis_gcov_hh_contrast=("hh_contrast", "mean"),
        nis_gcov_hh_chg=("hh_db_chg", "mean"), nis_gcov_hv_chg=("hv_db_chg", "mean"),
        nis_gcov_contrast_chg=("hh_contrast_chg", "mean"), nis_gcov_abs_hh_chg_max=("hh_db_chg", lambda s: s.abs().max()),
        nis_gcov_n=("hh_db", "size")).reset_index()

    # GUNW: local LOS movement, normalised by each pair's city-wide spread (atmospheric noise level)
    u = pd.read_parquet(pro / "seg_gunw.parquet")
    spread = u.groupby("granule_ur")["los_local_mm"].transform(lambda s: s.abs().median() * 1.4826)
    u["los_z"] = u["los_local_mm"] / spread.where(spread > 0)
    uw = windowed(u).groupby(["main_id", "month"]).agg(
        nis_gunw_los_sum_mm=("los_local_mm", "sum"), nis_gunw_los_abs_max_mm=("los_local_mm", lambda s: s.abs().max()),
        nis_gunw_los_z_mean=("los_z", "mean"), nis_gunw_los_z_abs_max=("los_z", lambda s: s.abs().max()),
        nis_gunw_coherence=("coherence", "mean"), nis_gunw_n=("los_local_mm", "size")).reset_index()

    # SME2: soil moisture level, wetness relative to the city, change vs previous retrieval
    s = pd.read_parquet(pro / "seg_sme2.parquet").sort_values(["main_id", "time"])
    s["sm_rel_city"] = s["soil_moisture"] - s["city_sm_median"]
    s["sm_chg"] = s.groupby("main_id")["soil_moisture"].diff()
    sw = windowed(s).groupby(["main_id", "month"]).agg(
        nis_sm_mean=("soil_moisture", "mean"), nis_sm_rel_city=("sm_rel_city", "mean"), nis_sm_chg=("sm_chg", "mean"),
        nis_sm_from_neighbourhood=("sm_from_neighbourhood", "mean"), nis_sm_n=("soil_moisture", "size")).reset_index()

    for t in (gw, uw, sw):
        out = out.merge(t, on=["main_id", "month"], how="left")
    return out.drop(columns=["main_id", "month"])


# --------------------------------------------------------------------------- models
def _hgb(seed: int):
    from sklearn.ensemble import HistGradientBoostingClassifier

    return HistGradientBoostingClassifier(learning_rate=0.05, max_iter=300, max_depth=4, min_samples_leaf=200,
                                          l2_regularization=1.0, categorical_features="from_dtype", random_state=seed)


def _metrics(y, p) -> dict:
    from sklearn.metrics import average_precision_score, roc_auc_score

    y, p = np.asarray(y), np.asarray(p)
    top = p >= np.quantile(p, 0.95)
    return {"auc": roc_auc_score(y, p), "avg_precision": average_precision_score(y, p),
            "capture_top5pct": y[top].sum() / max(y.sum(), 1), "base_rate": y.mean()}


def run(cfg: Config) -> None:
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    r = cfg.section("risk")
    rng = np.random.default_rng(r["seed"])
    print("Stage 7c - segment x month break-risk model")
    mains = gpd.read_parquet(cfg.path("processed_dir") / "kitchener_water_mains.parquet")
    inc = gpd.read_parquet(cfg.incidents_parquet)
    breaks = link_breaks(cfg, mains, inc)

    mu = mains.to_crs(UTM_CRS)
    mid = mu.geometry.interpolate(0.5, normalized=True)
    blk = cfg.section("dataset")["spatial_block_m"]
    seg = pd.DataFrame({"main_id": mu["main_id"].astype(int), "log_length_m": np.log1p(mu["length_m"]),
                        "material": mu["material"].fillna("UNK"), "pipe_size_mm": mu["pipe_size_mm"],
                        "install_year": mu["install_year"].astype("float"), "mx": mid.x, "my": mid.y,
                        "block": (mid.x // blk).astype(int).astype(str) + "_" + (mid.y // blk).astype(int).astype(str)})

    hist_months = pd.period_range(r["history_from"], pd.Timestamp(r["eval_from"]) - pd.Timedelta(days=1), freq="M")
    eval_months = pd.period_range(r["eval_from"], r["eval_to"], freq="M")
    pos = breaks.groupby(["main_id", "month"]).size().rename("n_breaks").reset_index()

    # history rows: all positives + sampled negatives (weighted back)
    hp = pos[pos["month"].isin(hist_months)][["main_id", "month"]]
    n_neg = int(len(seg) * len(hist_months) * r["negative_sample_frac"])
    neg = pd.DataFrame({"main_id": rng.choice(seg["main_id"], n_neg),
                        "month": hist_months[rng.integers(0, len(hist_months), n_neg)]})
    hist = pd.concat([hp.assign(y=1, w=1.0), neg.assign(y=0, w=1 / r["negative_sample_frac"])])
    hist = hist.drop_duplicates(["main_id", "month"])
    ev = pd.MultiIndex.from_product([seg["main_id"], eval_months], names=["main_id", "month"]).to_frame(index=False)
    ev = ev.merge(pos, on=["main_id", "month"], how="left").assign(y=lambda d: d["n_breaks"].notna().astype(int), w=1.0)
    ev = ev.drop(columns="n_breaks")

    w = weather_daily(cfg, f"{hist_months[0].start_time - pd.Timedelta(days=40):%Y-%m-%d}", f"{eval_months[-1].end_time:%Y-%m-%d}")
    wf = weather_features(w, hist_months.append(eval_months), r["feature_window_days"])
    hist = build_rows(seg, hist, breaks, cfg).merge(wf, on="month")
    ev = build_rows(seg, ev, breaks, cfg).merge(wf, on="month")
    # pipes not yet installed are not at risk
    hist = hist[~(hist["install_year"] > hist["month"].dt.year)]
    ev = ev[~(ev["install_year"] > ev["month"].dt.year)]
    for d in (hist, ev):
        d["material"] = d["material"].astype(pd.CategoricalDtype(sorted(seg["material"].unique())))
    print(f"  history rows: {len(hist)} ({int(hist['y'].sum())} break-months) | eval rows: {len(ev)} "
          f"({int(ev['y'].sum())} break-months, {len(eval_months)} months)")

    # ---- M0 baseline: trained on history, scored on eval months (temporal hold-out)
    m0 = _hgb(r["seed"]).fit(hist[BASE_FEATURES], hist["y"], sample_weight=hist["w"])
    ev["m0_score"] = m0.predict_proba(ev[BASE_FEATURES])[:, 1]
    m0_eval = _metrics(ev["y"], ev["m0_score"])
    print(f"  M0 baseline on eval months: AUC {m0_eval['auc']:.3f}, AP {m0_eval['avg_precision']:.4f} "
          f"(base rate {m0_eval['base_rate']:.5f}), top-5% capture {m0_eval['capture_top5pct']:.2f}")

    # ---- NISAR features and CV comparison A vs B on the eval months
    nis = nisar_features(cfg, ev)
    ev = pd.concat([ev.reset_index(drop=True), nis.reset_index(drop=True)], axis=1)
    nis_cols = list(nis.columns)
    ev["m0_logit"] = np.log(ev["m0_score"].clip(1e-6, 1 - 1e-6) / (1 - ev["m0_score"].clip(1e-6, 1 - 1e-6)))
    blocks = np.array(sorted(ev["block"].unique()))
    rng.shuffle(blocks)
    fold_of = {b: i % 5 for i, b in enumerate(blocks)}
    ev["fold"] = ev["block"].map(fold_of)
    print("  NISAR feature coverage on eval rows:",
          {k: f"{ev[c].notna().mean():.0%}" for k, c in (("gcov", "nis_gcov_hh_db"), ("gunw", "nis_gunw_los_sum_mm"), ("sme2", "nis_sm_mean"))})

    def cv(cols, kind):
        pred = np.zeros(len(ev))
        for k in range(5):
            tr, te = ev["fold"] != k, ev["fold"] == k
            if kind == "logit":
                X = ev[cols].astype(float)
                med = X[tr].median()
                X = X.fillna(med)
                for c in cols:
                    if c.startswith("nis_"):
                        X[c + "_missing"] = ev[c].isna().astype(float)
                model = make_pipeline(StandardScaler(), LogisticRegression(C=0.1, max_iter=2000, class_weight="balanced"))
                model.fit(X[tr], ev.loc[tr, "y"])
                pred[te.to_numpy()] = model.predict_proba(X[te])[:, 1]
            else:
                model = _hgb(r["seed"] + k).fit(ev.loc[tr, cols], ev.loc[tr, "y"])
                pred[te.to_numpy()] = model.predict_proba(ev.loc[te, cols])[:, 1]
        return pred

    groups = {"gcov": [c for c in nis_cols if c.startswith("nis_gcov")],
              "gunw": [c for c in nis_cols if c.startswith("nis_gunw")],
              "sme2": [c for c in nis_cols if c.startswith("nis_sm")]}
    variants = {"A: baseline score": ["m0_logit"], "B: + all NISAR": ["m0_logit", *nis_cols],
                **{f"B: + {g} only": ["m0_logit", *cols] for g, cols in groups.items()}}
    preds, rows = {}, []
    for kind in ("logit", "hgb"):
        for name, cols in variants.items():
            p = cv(cols, kind)
            preds[(kind, name)] = p
            rows.append({"model": kind, "variant": name, **_metrics(ev["y"], p)})
    res = pd.DataFrame(rows)

    # block bootstrap CI for the difference B - A (paired, same resampled blocks)
    blk_idx = {b: np.where(ev["block"].to_numpy() == b)[0] for b in blocks}
    y = ev["y"].to_numpy()
    diffs = []
    for kind in ("logit", "hgb"):
        a = preds[(kind, "A: baseline score")]
        for name in variants:
            if name.startswith("A"):
                continue
            b = preds[(kind, name)]
            d_auc, d_ap = [], []
            for _ in range(r["n_boot"]):
                pick = np.concatenate([blk_idx[x] for x in rng.choice(blocks, len(blocks))])
                if y[pick].sum() < 5:
                    continue
                ma, mb = _metrics(y[pick], a[pick]), _metrics(y[pick], b[pick])
                d_auc.append(mb["auc"] - ma["auc"])
                d_ap.append(mb["avg_precision"] - ma["avg_precision"])
            diffs.append({"model": kind, "variant": name, "delta_auc": np.median(d_auc),
                          "delta_auc_ci": f"[{np.percentile(d_auc, 2.5):+.3f}, {np.percentile(d_auc, 97.5):+.3f}]",
                          "delta_ap": np.median(d_ap),
                          "delta_ap_ci": f"[{np.percentile(d_ap, 2.5):+.4f}, {np.percentile(d_ap, 97.5):+.4f}]"})
    dif = pd.DataFrame(diffs)

    # outputs
    out = cfg.path("processed_dir") / "risk_panel_eval.parquet"
    keep = ev.copy()
    for (kind, name), p in preds.items():
        keep[f"pred_{kind}_{name.split(':')[0]}{'' if name.startswith('A') else '_' + name.split('+ ')[1].replace(' ', '_')}"] = p
    keep["month"] = keep["month"].astype(str)
    keep.to_parquet(out)
    hist_path = cfg.path("processed_dir") / "risk_panel_history_sample.parquet"
    hist.assign(month=hist["month"].astype(str)).to_parquet(hist_path)

    rep = cfg.path("reports_dir") / "risk_model_report.md"
    rep.write_text("\n".join([
        f"# Break-risk prediction: does NISAR add value?\n\n_Generated {date.today()} by `pixi run risk`._\n",
        f"Unit: water-main segment x month. Target: >= 1 recorded break. Features use only data before each month "
        f"(weather and NISAR from the prior {r['feature_window_days']} days). Evaluation months {eval_months[0]} .. {eval_months[-1]}: "
        f"{len(ev)} segment-months, {int(ev['y'].sum())} with a break.\n",
        "## Baseline M0 (infrastructure + break history + season + weather), trained on history, temporal hold-out",
        f"AUC {m0_eval['auc']:.3f}, average precision {m0_eval['avg_precision']:.4f} (base rate {m0_eval['base_rate']:.5f}), "
        f"top-5% riskiest segment-months capture {m0_eval['capture_top5pct']:.0%} of breaks.\n",
        "## Same eval months, 5 spatially blocked folds: baseline score (A) vs + NISAR (B)",
        res.round(4).to_markdown(index=False), "",
        f"## Paired block-bootstrap difference B - A ({r['n_boot']} resamples of 2 km blocks)",
        dif.round(4).to_markdown(index=False), "",
        "NISAR coverage on eval rows: " + ", ".join(f"{k} {ev[c].notna().mean():.0%}" for k, c in
                                                   (("gcov", "nis_gcov_hh_db"), ("gunw", "nis_gunw_los_sum_mm"), ("sme2", "nis_sm_mean"))),
        ""]) + "\n")
    print(res.round(4).to_string(index=False))
    print()
    print(dif.round(4).to_string(index=False))
    print(f"  panels -> {report_file(out)}, {report_file(hist_path)}")
    print(f"  report -> {report_file(rep)}")
