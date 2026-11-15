"""Exploratory signal check: is there localized backscatter change at break sites around the
reported date, compared with pre-event references on the same track?

Each subset rebuilds the reference from pre-event rows that pass the SAME filter (e.g. unfrozen
subset -> unfrozen references), compares event-window (or post-event) rows to pre-event rows
within each (incident, comparison group) with a paired Wilcoxon test, applies Benjamini-Hochberg
across all tests, and reports the minimum detectable effect (MDE) so a null result is interpretable.
"""
from __future__ import annotations

import warnings
from datetime import date

import h5py
import numpy as np
import pandas as pd
from scipy.stats import norm, wilcoxon

from .config import ROOT, Config
from .features import region_masks

POLS = ("hh", "hv")


def _localized_change(db, rows: pd.DataFrame, masks: dict) -> pd.DataFrame:
    """Per row: (centre - ring) of (dB - median of other pre rows), within incident x group."""
    out = []
    for (_, _), g in rows.groupby(["incident_id", "comparison_group"]):
        pre = g[g["cat"] == "pre_event"]
        for j, r in g.iterrows():
            ref = pre.drop(index=j, errors="ignore")
            if ref.empty:
                continue
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", RuntimeWarning)
                med = np.nanmedian(db[ref["patch_index"].to_numpy()], axis=0)
                d = db[r["patch_index"]] - med
                res = {"row": j}
                for b, p in enumerate(POLS):
                    res[p] = np.nanmean(d[b][masks["center"]]) - np.nanmean(d[b][masks["ring"]])
            out.append(res)
    return pd.DataFrame(out).set_index("row") if out else pd.DataFrame(columns=list(POLS))


def _bh(p: pd.Series) -> pd.Series:
    p = p.astype(float)
    order = p.sort_values().index
    m = p.notna().sum()
    q = pd.Series(np.nan, index=p.index)
    prev = 1.0
    for rank, i in reversed(list(enumerate(order[: m], 1))):
        prev = min(prev, p[i] * m / rank)
        q[i] = prev
    return q


def run(cfg: Config) -> pd.DataFrame:
    f = cfg.section("features")
    feat = pd.read_parquet(cfg.path("processed_dir") / "radar_features.parquet")
    inc = pd.read_parquet(cfg.incidents_parquet, columns=["incident_id", "road_closed", "hours_impacted"])
    feat = feat.merge(inc, on="incident_id", how="left")
    feat = feat[feat["q_usable"]].copy()
    feat["cat"] = feat["temporal_category"].astype(str)
    with h5py.File(ROOT / cfg.section("sar")["out_dir"] / "patches.h5", "r") as h5:
        db = h5["db_filtered"][:]
        valid = h5["valid"][:]
    db = np.where(valid[:, None], db, np.nan)
    size = db.shape[-1]

    long_impact = feat["hours_impacted"].isin(["8-12 hours", "12-16 hours", "16-20 hours", "20-24 hours"])
    closed = feat["road_closed"].isin(["Closed", "Partially Closed"])
    unfrozen = ~feat["env_frozen_or_snow"].fillna(True).astype(bool)
    big = feat["inf_asset_size_mm"] >= 300
    tight = (feat["cat"] != "potential_event_window") | feat["delta_days"].between(-3, 3)
    subsets = {
        "all": pd.Series(True, index=feat.index),
        "unfrozen (rows + refs)": unfrozen,
        "large mains >=300 mm": big,
        "road closed / >=8 h impact": closed | long_impact,
        "tight event window |dt|<=3 d": tight,
        "unfrozen + large or closed": unfrozen & (big | closed | long_impact),
    }
    radii = {"r=70 m (config)": f["center_radius_px"], "r=30 m": 1, "r=20 m": 0}

    results = []
    for rname, rad in radii.items():
        masks = region_masks(size, {**f, "center_radius_px": max(rad, 0.5)})
        for sname, sel in subsets.items():
            rows = feat[sel]
            ch = _localized_change(db, rows, masks)
            if ch.empty:
                continue
            rows = rows.join(ch, how="inner")
            per = rows.groupby(["incident_id", "comparison_group", "cat"])[list(POLS)].mean()
            pre_noise = rows.loc[rows["cat"] == "pre_event", list(POLS)].std()
            for test in ("potential_event_window", "post_event"):
                for p in POLS:
                    tab = per[p].unstack("cat")
                    if "pre_event" not in tab or test not in tab:
                        continue
                    pair = tab[["pre_event", test]].dropna()
                    n = len(pair)
                    diff = pair[test] - pair["pre_event"]
                    pval = wilcoxon(diff).pvalue if n >= 6 and diff.abs().sum() > 0 else np.nan
                    # MDE for a paired test (alpha 0.05 two-sided, power 0.8), Wilcoxon ~0.95 efficiency.
                    mde = (norm.ppf(0.975) + norm.ppf(0.8)) * diff.std() / np.sqrt(max(n, 1) * 0.95) if n > 2 else np.nan
                    results.append({"radius": rname, "subset": sname, "comparison": f"{test} vs pre",
                                    "pol": p.upper(), "n_incident_tracks": n, "n_incidents": pair.index.get_level_values(0).nunique(),
                                    "median_diff_db": float(diff.median()) if n else np.nan,
                                    "mde_db": mde, "pre_noise_db": float(pre_noise[p]), "p": pval})
    res = pd.DataFrame(results)
    res["q_bh"] = _bh(res["p"])
    out = cfg.path("reports_dir") / "signal_check.md"
    show = res.assign(median_diff_db=res["median_diff_db"].round(3), mde_db=res["mde_db"].round(2),
                      pre_noise_db=res["pre_noise_db"].round(2), p=res["p"].round(3), q_bh=res["q_bh"].round(3))
    lines = [f"# Localized-change signal check\n\n_Generated {date.today()} by `pixi run signal`._\n",
             "Localized change = (break-site disk - background ring) of (dB - median of pre-event acquisitions on the "
             "same track; leave-one-out for pre rows). Paired per incident x track; Wilcoxon; Benjamini-Hochberg q over "
             f"all {res['p'].notna().sum()} tests. MDE = smallest median shift detectable with 80% power at alpha 0.05.\n",
             "Exploratory analysis on the reported-date hypothesis. Subsets use post-incident fields (road closure, "
             "impact hours) for stratification only, never as model features.\n",
             show.to_markdown(index=False)]
    out.write_text("\n".join(lines) + "\n")
    res.to_parquet(cfg.path("reports_dir") / "signal_check.parquet")
    return res


# --------------------------------------------------------------------------- with controls (Stage 6)
def _auc(pos: np.ndarray, neg: np.ndarray) -> float:
    from scipy.stats import mannwhitneyu

    if len(pos) == 0 or len(neg) == 0:
        return np.nan
    return mannwhitneyu(pos, neg).statistic / (len(pos) * len(neg))


def control_check(cfg: Config, n_boot: int = 1000) -> pd.DataFrame:
    """Does a naive change score rank incident sites above their matched controls (same passes)?

    AUC 0.5 = no better than chance. Scores use |localized change| (direction-agnostic) and the
    signed value (site darker -> higher score). CI: bootstrap over incidents (sites + controls together).
    Also: paired DiD test (site minus control mean) event-window vs pre-event per incident x track.
    """
    df = pd.read_parquet(cfg.path("processed_dir") / "ml_dataset.parquet")
    df = df[df["q_usable"]]
    rng = np.random.default_rng(0)
    rows = []
    for window in ("potential_event_window", "post_event", "pre_event"):
        w = df[df["temporal_category"].astype(str) == window]
        for feat in ("chg_ref_hh_contrast", "chg_ref_hv_contrast", "chg_prev_hh_contrast", "sd_hh_contrast"):
            for kind, sign in (("|x|", None), ("-x (darker)", -1)):
                v = w[["incident_id", "site_type", feat]].dropna()
                score = v[feat].abs() if sign is None else sign * v[feat]
                pos, neg = score[v["site_type"] == "incident"].to_numpy(), score[v["site_type"] == "control"].to_numpy()
                auc = _auc(pos, neg)
                ids = v["incident_id"].unique()
                boots = []
                g = {i: (score[(v["incident_id"] == i) & (v["site_type"] == "incident")].to_numpy(),
                         score[(v["incident_id"] == i) & (v["site_type"] == "control")].to_numpy()) for i in ids}
                for _ in range(n_boot):
                    pick = rng.choice(ids, len(ids))
                    P = np.concatenate([g[i][0] for i in pick]); N = np.concatenate([g[i][1] for i in pick])
                    boots.append(_auc(P, N))
                lo, hi = np.nanpercentile(boots, [2.5, 97.5]) if len(ids) > 5 else (np.nan, np.nan)
                rows.append({"window": window, "score": f"{kind} {feat}", "n_site_rows": len(pos),
                             "n_control_rows": len(neg), "n_incidents": len(ids), "auc": auc, "ci95_lo": lo, "ci95_hi": hi})
    auc = pd.DataFrame(rows)

    did_rows = []
    s = df[df["site_type"] == "incident"].copy()
    s["cat"] = s["temporal_category"].astype(str)
    for feat in ("did_ref_hh_contrast", "did_ref_hv_contrast", "did_prev_hh_contrast"):
        per = s.groupby(["incident_id", "comparison_group", "cat"])[feat].mean().unstack("cat")
        for test in ("potential_event_window", "post_event"):
            if "pre_event" not in per or test not in per:
                continue
            pair = per[["pre_event", test]].dropna()
            diff = pair[test] - pair["pre_event"]
            p = wilcoxon(diff).pvalue if len(pair) >= 6 else np.nan
            did_rows.append({"feature": feat, "comparison": f"{test} vs pre", "n_incident_tracks": len(pair),
                             "median_diff_db": float(diff.median()), "p": p})
    did_tab = pd.DataFrame(did_rows)
    did_tab["q_bh"] = _bh(did_tab["p"])

    out = cfg.path("reports_dir") / "signal_check_controls.md"
    out.write_text("\n".join([
        f"# Incident sites vs matched controls\n\n_Generated {date.today()} by `pixi run signal-controls`._\n",
        "Controls: points on the water-main network, 0.5-3 km from the incident, same material/size where possible, "
        "no recorded break within 300 m / +-365 d. Same passes as the incident. Controls are `unknown`, not negatives.\n",
        "## Can a naive change score rank incident sites above controls? (AUC, 0.5 = chance)",
        auc.round(3).to_markdown(index=False), "",
        "## Difference-in-differences: (site - control mean) in event/post window vs pre-event, paired per incident x track",
        did_tab.round(3).to_markdown(index=False), ""]) + "\n")
    auc.to_parquet(cfg.path("reports_dir") / "signal_check_controls_auc.parquet")
    did_tab.to_parquet(cfg.path("reports_dir") / "signal_check_controls_did.parquet")
    return auc, did_tab
