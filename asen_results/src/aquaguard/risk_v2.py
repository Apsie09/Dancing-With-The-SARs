"""Stage 7c v2: normalised NISAR features + regularised models. Specified before seeing its results.

Changes vs v1 (everything else identical: data, folds, metrics, bootstrap):
  1. GCOV relative radiometric normalisation: each pass's city-wide median dB is subtracted before
     levels and pass-to-pass changes are computed (removes per-pass calibration / processing-version
     offsets and per-track level differences).
  2. Skewed inputs get a signed log1p transform in the logistic model (trees are invariant).
  3. "Does NISAR help?" logistic model: L1 penalty, strength chosen by NESTED spatially blocked CV
     (inner folds inside each outer training set; the outer test fold is never used for tuning).
  4. Baseline M0 (gradient boosting) gets monotonic constraints from domain knowledge
     (older pipe, more past breaks, more frost -> risk cannot decrease).
Both stage-2 models are kept: L1 logistic (primary judge with few events) and gradient boosting (cross-check).
"""
from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

from .config import Config, report_file
from .risk import BASE_FEATURES, _hgb, _metrics, nisar_features, prepare

MONOTONIC = {"age_years": 1, "prior_breaks_seg": 1, "breaks_seg_5y": 1, "nbr_breaks_2y": 1,
             "months_since_last_break": -1, "w_fdd": 1, "w_freeze_thaw_days": 1}
SKEWED = ["nis_gunw_los_sum_mm", "nis_gunw_los_abs_max_mm", "nis_gunw_los_z_abs_max", "nis_gcov_abs_hh_chg_max"]
C_GRID = [0.001, 0.003, 0.01, 0.03, 0.1, 0.3, 1.0]


def gcov_normalised(cfg: Config, ev: pd.DataFrame) -> pd.DataFrame:
    """GCOV features from pass-normalised dB (each pass minus its city-wide median)."""
    days = cfg.section("risk")["feature_window_days"]
    g = pd.read_parquet(cfg.path("processed_dir") / "seg_gcov.parquet")
    for c in ("hh_db", "hv_db"):
        g[c] = g[c] - g.groupby("granule_ur")[c].transform("median")
    g = g.sort_values(["main_id", "comparison_group", "time"])
    for c in ("hh_db", "hv_db", "hh_contrast"):
        g[f"{c}_chg"] = g.groupby(["main_id", "comparison_group"])[c].diff()
    parts = []
    for m in ev["month"].unique():
        s = pd.Timestamp(m.start_time, tz="UTC")
        parts.append(g[(g["time"] >= s - pd.Timedelta(days=days)) & (g["time"] < s)].assign(month=m))
    w = pd.concat(parts, ignore_index=True).groupby(["main_id", "month"]).agg(
        nis_gcov_hh_db=("hh_db", "mean"), nis_gcov_hv_db=("hv_db", "mean"), nis_gcov_hh_contrast=("hh_contrast", "mean"),
        nis_gcov_hh_chg=("hh_db_chg", "mean"), nis_gcov_hv_chg=("hv_db_chg", "mean"),
        nis_gcov_contrast_chg=("hh_contrast_chg", "mean"), nis_gcov_abs_hh_chg_max=("hh_db_chg", lambda s: s.abs().max()),
        nis_gcov_n=("hh_db", "size")).reset_index()
    return ev[["main_id", "month"]].merge(w, on=["main_id", "month"], how="left").drop(columns=["main_id", "month"])


def _design(ev: pd.DataFrame, cols: list[str], train: np.ndarray) -> pd.DataFrame:
    """Signed log1p for skewed columns, train-fold median imputation + missing flags."""
    X = ev[cols].astype(float).copy()
    for c in cols:
        if c in SKEWED:
            X[c] = np.sign(X[c]) * np.log1p(X[c].abs())
    flags = {f"{c}_missing": ev[c].isna().astype(float) for c in cols if c.startswith("nis_")}
    X = X.fillna(X[train].median())
    return pd.concat([X, pd.DataFrame(flags, index=X.index)], axis=1)


def _fit_l1(X, y, C, rng):
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    # all positives + 10% of negatives (class_weight='balanced' restores the balance; fits stay fast)
    keep = (y == 1) | (rng.random(len(y)) < 0.10)
    model = make_pipeline(StandardScaler(), LogisticRegression(l1_ratio=1.0, C=C, solver="liblinear",
                                                               class_weight="balanced", max_iter=500))
    return model.fit(X[keep], y[keep])


def run(cfg: Config) -> None:
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.metrics import roc_auc_score

    r = cfg.section("risk")
    rng = np.random.default_rng(r["seed"])
    print("Stage 7c v2 - normalised NISAR features + regularised models")
    seg, hist, ev, eval_months = prepare(cfg, rng)

    # ---- M0 v1 (as before) and v2 (monotonic constraints)
    m0v1 = _hgb(r["seed"]).fit(hist[BASE_FEATURES], hist["y"], sample_weight=hist["w"])
    m0v2 = HistGradientBoostingClassifier(learning_rate=0.05, max_iter=300, max_depth=4, min_samples_leaf=200,
                                          l2_regularization=1.0, categorical_features="from_dtype",
                                          monotonic_cst=MONOTONIC, random_state=r["seed"])
    m0v2.fit(hist[BASE_FEATURES], hist["y"], sample_weight=hist["w"])
    ev["m0v1"] = m0v1.predict_proba(ev[BASE_FEATURES])[:, 1]
    ev["m0_score"] = m0v2.predict_proba(ev[BASE_FEATURES])[:, 1]
    m0 = {"M0 v1 (boosting)": _metrics(ev["y"], ev["m0v1"]), "M0 v2 (boosting + monotonic)": _metrics(ev["y"], ev["m0_score"])}
    for k, v in m0.items():
        print(f"  {k}: AUC {v['auc']:.3f}, AP {v['avg_precision']:.4f}, top-5% capture {v['capture_top5pct']:.2f}")

    # ---- NISAR features: v1 GUNW/SME2 + pass-normalised GCOV
    nis = nisar_features(cfg, ev)
    gv2 = gcov_normalised(cfg, ev)
    nis[gv2.columns] = gv2.to_numpy()
    ev = pd.concat([ev.reset_index(drop=True), nis.reset_index(drop=True)], axis=1)
    nis_cols = list(nis.columns)
    p = ev["m0_score"].clip(1e-6, 1 - 1e-6)
    ev["m0_logit"] = np.log(p / (1 - p))
    blocks = np.array(sorted(ev["block"].unique()))
    rng.shuffle(blocks)
    fold_of = {b: i % 5 for i, b in enumerate(blocks)}
    ev["fold"] = ev["block"].map(fold_of)
    y = ev["y"].to_numpy()

    groups = {"gcov": [c for c in nis_cols if c.startswith("nis_gcov")],
              "gunw": [c for c in nis_cols if c.startswith("nis_gunw")],
              "sme2": [c for c in nis_cols if c.startswith("nis_sm")]}
    variants = {"A: baseline score": ["m0_logit"], "B: + all NISAR": ["m0_logit", *nis_cols],
                **{f"B: + {g} only": ["m0_logit", *cols] for g, cols in groups.items()}}

    preds, chosen, selected = {}, [], {}
    for name, cols in variants.items():
        # nested L1 logistic
        pred = np.zeros(len(ev))
        for k in range(5):
            tr = (ev["fold"] != k).to_numpy()
            te = ~tr
            X = _design(ev, cols, tr)
            inner_blocks = np.array(sorted(ev.loc[tr, "block"].unique()))
            inner_fold = ev.loc[tr, "block"].map({b: i % 4 for i, b in enumerate(inner_blocks)}).to_numpy()
            Xtr, ytr = X[tr].reset_index(drop=True), y[tr]
            best_c, best_auc = C_GRID[0], -1
            if len(cols) > 1:
                for C in C_GRID:
                    aucs = []
                    for j in range(4):
                        it, iv = inner_fold != j, inner_fold == j
                        if ytr[iv].sum() < 3:
                            continue
                        mdl = _fit_l1(Xtr[it], ytr[it], C, rng)
                        aucs.append(roc_auc_score(ytr[iv], mdl.predict_proba(Xtr[iv])[:, 1]))
                    if aucs and np.mean(aucs) > best_auc:
                        best_c, best_auc = C, float(np.mean(aucs))
            else:
                best_c = 1.0
            mdl = _fit_l1(Xtr, ytr, best_c, rng)
            pred[te] = mdl.predict_proba(X[te])[:, 1]
            chosen.append({"variant": name, "fold": k, "C": best_c, "inner_auc": best_auc})
            coef = mdl[-1].coef_[0]
            for c, w in zip(X.columns, coef):
                if c != "m0_logit":
                    selected.setdefault((name, c), []).append(abs(w) > 1e-8)
        preds[("logit_l1", name)] = pred
        # gradient boosting cross-check on the same (normalised) inputs
        pred = np.zeros(len(ev))
        for k in range(5):
            tr, te = ev["fold"] != k, ev["fold"] == k
            mdl = _hgb(r["seed"] + k).fit(ev.loc[tr, cols], ev.loc[tr, "y"])
            pred[te.to_numpy()] = mdl.predict_proba(ev.loc[te, cols])[:, 1]
        preds[("hgb", name)] = pred
        print(f"  done: {name}")

    res = pd.DataFrame([{"model": k, "variant": n, **_metrics(y, p)} for (k, n), p in preds.items()])
    blk_idx = {b: np.where(ev["block"].to_numpy() == b)[0] for b in blocks}
    diffs = []
    for kind in ("logit_l1", "hgb"):
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
    ch = pd.DataFrame(chosen).groupby("variant")["C"].agg(lambda s: ", ".join(f"{c:g}" for c in s)).rename("C per fold")
    sel = pd.Series({k: np.mean(v) for k, v in selected.items()}, name="selected_in_folds").reset_index()
    sel.columns = ["variant", "feature", "selected_frac"]
    sel = sel[(sel["variant"] == "B: + all NISAR") & (sel["selected_frac"] > 0)].sort_values("selected_frac", ascending=False)

    rep = cfg.path("reports_dir") / "risk_model_report_v2.md"
    rep.write_text("\n".join([
        f"# Break-risk prediction v2: normalised NISAR features + regularised models\n\n_Generated {date.today()} by `pixi run risk-v2`. "
        "Specified before seeing results; same data, folds, metrics and bootstrap as v1 (`risk_model_report.md`)._\n",
        "Changes: per-pass radiometric normalisation of GCOV (pass city median removed), signed log1p of skewed inputs, "
        "L1 logistic with nested spatially blocked CV for the penalty, monotonic constraints on the baseline.\n",
        "## Baseline M0 on the evaluation months (temporal hold-out)",
        pd.DataFrame(m0).T.round(4).to_markdown(), "",
        "## Same eval months, 5 spatial folds: baseline score (A) vs + NISAR (B)",
        res.round(4).to_markdown(index=False), "",
        f"## Paired block-bootstrap difference B - A ({r['n_boot']} resamples of 2 km blocks)",
        dif.round(4).to_markdown(index=False), "",
        "## L1 penalty chosen by inner CV (per outer fold)", ch.to_frame().to_markdown(), "",
        "## NISAR columns kept by L1 (B: + all NISAR), share of outer folds",
        sel.round(2).to_markdown(index=False) if len(sel) else "(none: L1 removed every NISAR column)", ""]) + "\n")
    with pd.option_context("display.width", 200):
        print(res.round(4).to_string(index=False)); print(); print(dif.round(4).to_string(index=False)); print()
        print(ch.to_string()); print(); print(sel.round(2).to_string(index=False) if len(sel) else "L1 kept no NISAR column")
    print(f"  report -> {report_file(rep)}")
