"""Boosting models on Peter's Coryell train/test chip package, enriched with our data.

Package: ../pesho_coryell_data_package (274 leak repairs + 2,740 same-pass points on the pipe network;
train/test split by leak groups). Nothing in that folder is modified.

Features
  SAR (from the chips; stack 041D_073, same pass for a positive and its 10 negatives):
    per pass t-2, t-1, t0: centre 3x3 HH/HV dB, centre minus chip ring (>= 50 m), centre minus 250 m / 500 m circle
    median, centre minus district median, HV-HH, chip texture (std dB); changes t0-t-1 and t0-t-2.
    t+1 (after the repair) is used ONLY in a diagnostic variant: it is not available for detection.
  Context (our data):
    pipe install year -> age, depth, pressure class (district waterlines), diameter and material;
    leak history from all 1,691 Coryell records: leaks within 200 / 500 m repaired more than 60 days before t0
    (the 60-day gap avoids reproducing the negative-sampling rule: negatives have no leak within 300 m / +-60 d).
Excluded on purpose (they reveal the label by construction): dist_to_pipe_m (negatives are exactly on the line),
nearest_leak_pm60d_m / nearest_leak_days (sampling rule), loss_gpm, cause, repair_type, days_pass_to_repair.
"""
from __future__ import annotations

import json
import re
from datetime import date

import geopandas as gpd
import numpy as np
import pandas as pd

from .config import ROOT, Config, report_file

PKG = ROOT.parent / "pesho_coryell_data_package"
PASSES = ["t-2", "t-1", "t0", "t+1"]


def _depth_ft(s) -> float:
    nums = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", str(s))]
    return float(np.mean(nums)) if nums else np.nan


def sar_features(split: str, idx: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for r in idx.itertuples():
        z = np.load(PKG / split / r.sample_id / "sar.npz")
        meta = json.load(open(PKG / split / r.sample_id / "meta.json"))
        sar = z["sar"]
        pr, pc = meta["chip"]["point_row"], meta["chip"]["point_col"]
        yy, xx = np.mgrid[:20, :20]
        dist = np.hypot(yy + 0.5 - pr, xx + 0.5 - pc)
        centre, ring = dist <= 1.6, dist >= 5
        f = {"sample_id": r.sample_id}
        for k, role in enumerate(PASSES):
            p = meta["passes"][k]
            if not p["available"]:
                continue
            hh, hv, mask, exc = sar[k, 0], sar[k, 1], sar[k, 2], sar[k, 4]
            ok = (mask >= 1) & (mask <= 254) & (exc == 0) & (hh > 0) & (hv > 0)
            with np.errstate(divide="ignore", invalid="ignore"):
                dbh, dbv = np.where(ok, 10 * np.log10(hh), np.nan), np.where(ok, 10 * np.log10(hv), np.nan)
            if not np.isfinite(dbh[centre]).any():
                continue
            ch, cv = np.nanmean(dbh[centre]), np.nanmean(dbv[centre])
            t = role.replace("-", "m").replace("+", "p")
            f[f"sar_{t}_hh"], f[f"sar_{t}_hv"] = ch, cv
            f[f"sar_{t}_hvhh"] = cv - ch
            f[f"sar_{t}_hh_ring"] = ch - np.nanmean(dbh[ring])
            f[f"sar_{t}_hv_ring"] = cv - np.nanmean(dbv[ring])
            for rad in ("250", "500"):
                c = p["circles"][rad]
                f[f"sar_{t}_hh_c{rad}"] = ch - c["hh_db_median"]
                f[f"sar_{t}_hv_c{rad}"] = cv - c["hv_db_median"]
            d = p["district"]
            f[f"sar_{t}_hh_district_z"] = (ch - d["hh_db_median"]) / d["hh_db_std"]
            f[f"sar_{t}_hv_district_z"] = (cv - d["hv_db_median"]) / d["hv_db_std"]
            f[f"sar_{t}_hh_tex"] = np.nanstd(dbh)
            f[f"sar_{t}_valid"] = float(ok.mean())
        for a, b in (("t0", "tm1"), ("t0", "tm2"), ("tp1", "t0")):
            for v in ("hh", "hv", "hh_ring", "hv_ring", "hh_c250", "hv_c250"):
                if f"sar_{a}_{v}" in f and f"sar_{b}_{v}" in f:
                    f[f"chg_{a}_{b}_{v}"] = f[f"sar_{a}_{v}"] - f[f"sar_{b}_{v}"]
        rows.append(f)
    return pd.DataFrame(rows)


def context_features(idx: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    c = cfg.section("coryell")
    pipes = gpd.read_file(ROOT / c["pipes"])[["OBJECTID", "Year", "Depth", "Class"]]
    pipes["pipe_install_year"] = pd.to_numeric(pipes["Year"], errors="coerce")
    pipes["pipe_depth_ft"] = pipes["Depth"].map(_depth_ft)
    pipes["pipe_class"] = pd.to_numeric(pipes["Class"], errors="coerce")
    out = idx[["sample_id", "nearest_pipe_id", "pipe_diameter_in", "pipe_material", "zone", "utm_x", "utm_y", "t0_utc"]].merge(
        pipes.rename(columns={"OBJECTID": "nearest_pipe_id"})[["nearest_pipe_id", "pipe_install_year", "pipe_depth_ft", "pipe_class"]],
        on="nearest_pipe_id", how="left")
    t0 = pd.to_datetime(out["t0_utc"], utc=True)
    out["ctx_pipe_age_years"] = t0.dt.year - out["pipe_install_year"]
    out = out.rename(columns={"pipe_diameter_in": "ctx_pipe_diameter_in", "pipe_depth_ft": "ctx_pipe_depth_ft",
                              "pipe_class": "ctx_pipe_class", "pipe_material": "ctx_pipe_material", "zone": "ctx_zone"})
    # leak history strictly older than 60 days before t0
    L = gpd.read_file(ROOT / c["leaks"]).to_crs(c["utm_crs"])
    L["time"] = pd.to_datetime(L["datetime"], unit="ms", utc=True, errors="coerce")
    L = L[L["time"].notna()]
    lx, ly = L.geometry.x.to_numpy(), L.geometry.y.to_numpy()
    lt = L["time"].dt.tz_convert(None).to_numpy(dtype="datetime64[ns]")
    for col in ("ctx_leaks_200m_1y", "ctx_leaks_200m_all", "ctx_leaks_500m_1y", "ctx_leaks_500m_all", "ctx_days_since_leak_200m"):
        out[col] = np.nan
    for i, (x, y, t) in enumerate(zip(out["utm_x"], out["utm_y"], t0)):
        t = t.tz_convert(None)
        cutoff = (t - pd.Timedelta(days=60)).to_datetime64()
        year = (t - pd.Timedelta(days=425)).to_datetime64()
        d = np.hypot(lx - x, ly - y)
        past = lt < cutoff
        out.loc[i, "ctx_leaks_200m_all"] = int(((d <= 200) & past).sum())
        out.loc[i, "ctx_leaks_500m_all"] = int(((d <= 500) & past).sum())
        out.loc[i, "ctx_leaks_200m_1y"] = int(((d <= 200) & past & (lt >= year)).sum())
        out.loc[i, "ctx_leaks_500m_1y"] = int(((d <= 500) & past & (lt >= year)).sum())
        near = (d <= 200) & past
        out.loc[i, "ctx_days_since_leak_200m"] = (t.to_datetime64() - lt[near].max()) / np.timedelta64(1, "D") if near.any() else np.nan
    return out.drop(columns=["nearest_pipe_id", "utm_x", "utm_y", "t0_utc", "pipe_install_year"])


def _metrics(y, p, groups, rng, n_boot=2000):
    from sklearn.metrics import average_precision_score, roc_auc_score

    y, p, groups = np.asarray(y), np.asarray(p), np.asarray(groups)
    auc, ap = roc_auc_score(y, p), average_precision_score(y, p)
    # matched AUC: each positive vs its own same-pass negatives (immune to pass-level differences)
    m = []
    for g in np.unique(groups):
        s = groups == g
        pos, neg = p[s & (y == 1)], p[s & (y == 0)]
        if len(pos) and len(neg):
            m.append(np.mean([(pp > neg).mean() + 0.5 * (pp == neg).mean() for pp in pos]))
    ug = np.unique(groups)
    gi = {g: np.where(groups == g)[0] for g in ug}
    boots = []
    for _ in range(n_boot):
        pick = np.concatenate([gi[g] for g in rng.choice(ug, len(ug))])
        if y[pick].min() == y[pick].max():
            continue
        boots.append(roc_auc_score(y[pick], p[pick]))
    lo, hi = np.percentile(boots, [2.5, 97.5])
    return {"auc": auc, "auc_ci95": f"[{lo:.3f}, {hi:.3f}]", "matched_auc": float(np.mean(m)), "avg_precision": ap,
            "base_rate": y.mean()}


def run(cfg: Config) -> None:
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.inspection import permutation_importance

    print("Boosting on Peter's Coryell package (enriched)")
    rng = np.random.default_rng(42)
    data = {}
    for split in ("train", "test"):
        idx = pd.read_csv(PKG / split / "index.csv")
        df = idx[["sample_id", "label", "group_id", "t0_date"]].merge(sar_features(split, idx), on="sample_id")
        df = df.merge(context_features(idx, cfg), on="sample_id")
        data[split] = df
        print(f"  {split}: {len(df)} samples, {int(df['label'].sum())} positives")
    tr, te = data["train"], data["test"]
    out = cfg.path("processed_dir") / "pesho_enriched.parquet"
    pd.concat([tr.assign(split="train"), te.assign(split="test")]).to_parquet(out)

    for c in ("ctx_pipe_material", "ctx_zone"):
        cats = pd.CategoricalDtype(sorted(set(tr[c].dropna()) | set(te[c].dropna())))
        tr[c], te[c] = tr[c].astype(cats), te[c].astype(cats)
    pre = [c for c in tr.columns if (c.startswith("sar_t") or c.startswith("chg_")) and "tp1" not in c]
    post = [c for c in tr.columns if "tp1" in c]
    ctx = [c for c in tr.columns if c.startswith("ctx_")]
    variants = {
        "1. SAR only (t-2, t-1, t0)": pre,
        "2. context only (pipe + leak history)": ctx,
        "3. SAR + context": pre + ctx,
        "4. diagnostic: SAR incl. t+1 (after repair)": pre + post,
    }
    rows, models = [], {}
    for name, cols in variants.items():
        model = HistGradientBoostingClassifier(learning_rate=0.05, max_iter=300, max_depth=3, min_samples_leaf=40,
                                               l2_regularization=1.0, categorical_features="from_dtype", random_state=42)
        model.fit(tr[cols], tr["label"])
        p = model.predict_proba(te[cols])[:, 1]
        rows.append({"model": name, "n_features": len(cols), **_metrics(te["label"], p, te["group_id"].to_numpy(), rng)})
        models[name] = (model, cols)
        print(f"  {name}: test AUC {rows[-1]['auc']:.3f} {rows[-1]['auc_ci95']}, matched {rows[-1]['matched_auc']:.3f}, AP {rows[-1]['avg_precision']:.3f}")
    res = pd.DataFrame(rows)

    imp_tabs = []
    for name in ("3. SAR + context", "1. SAR only (t-2, t-1, t0)"):
        model, cols = models[name]
        pi = permutation_importance(model, te[cols], te["label"], scoring="roc_auc", n_repeats=20, random_state=0)
        imp = pd.DataFrame({"feature": cols, "auc_drop_mean": pi.importances_mean, "auc_drop_std": pi.importances_std})
        imp_tabs.append((name, imp.sort_values("auc_drop_mean", ascending=False).head(10)))

    rep = cfg.path("reports_dir") / "pesho_boosting.md"
    rep.write_text("\n".join([
        f"# Boosting on Peter's Coryell package, enriched\n\n_Generated {date.today()} by `pixi run pesho-model`._\n",
        f"Train {len(tr)} ({int(tr['label'].sum())} leaks) / test {len(te)} ({int(te['label'].sum())} leaks), Peter's group split. "
        "Base rate 1 leak : 10 same-pass points on the pipe network (negatives are 'no recorded leak', not verified non-leaks).\n",
        "Matched AUC = each leak ranked against its own 10 same-pass points (0.5 = chance). CI = bootstrap over leak groups.\n",
        res.round(3).to_markdown(index=False), "",
        *[f"## Permutation importance on test: {n}\n\n" + t.round(4).to_markdown(index=False) + "\n" for n, t in imp_tabs]]) + "\n")
    print(f"  enriched table -> {report_file(out)}")
    print(f"  report -> {report_file(rep)}")
    for n, t in imp_tabs:
        print(f"\n  top features ({n}):"); print(t.round(4).to_string(index=False))
