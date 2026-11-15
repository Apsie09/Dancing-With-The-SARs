"""Coryell leak-risk ranking per pipe piece and month (the Kitchener risk design, on Coryell data).

Inputs (repo root): data/coryell/{waterlines,leak_survey,pressure_zones}.geojson
Design: pipes are cut into pieces of at most 250 m; each piece x month is one row; the target is
"at least one non-construction leak repaired on this piece in this month". Features use only leaks
repaired before the month starts. Train 2020-10 .. 2025-10, hold out 2025-11 .. 2026-10 (the NISAR era).

Outputs:
  data/coryell/risk/pipe_risk.geojson     pieces with hold-out percentile ranks per month (for viz/)
  data/coryell/risk/risk_summary.json     metrics, per-month capture, rank of each hold-out leak
  pesho_coryell_data_package/risk_context.csv   risk score of every package sample at its t0 month
  asen_results/data/reports/coryell_risk.md
"""
from __future__ import annotations

import json
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.ops import substring
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import average_precision_score, roc_auc_score

from .config import Config

REPO = Path(__file__).resolve().parents[3]
SRC = REPO / "data" / "coryell"
OUT = SRC / "risk"
PKG = REPO / "pesho_coryell_data_package"
REPORT = REPO / "asen_results" / "data" / "reports" / "coryell_risk.md"
UTM = 32614
PIECE_M, SNAP_M = 250.0, 50.0
FIRST, TRAIN_FROM, TEST_FROM, LAST = "2019-10", "2020-10", "2025-11", "2026-10"
FEATS = ["own_all", "own_24", "own_12", "n200_all", "n200_24", "n500_all", "n500_24", "mo_since_own",
         "mo_since_200", "log_len", "dia", "galv", "zone", "m_sin", "m_cos"]


def pieces() -> gpd.GeoDataFrame:
    w = gpd.read_file(SRC / "waterlines.geojson").to_crs(UTM)
    rows = []
    for r in w.itertuples():
        n = max(1, int(np.ceil(r.geometry.length / PIECE_M)))
        step = r.geometry.length / n
        for k in range(n):
            dia = r.Diameter if np.isfinite(r.Diameter) else pd.to_numeric(str(r.Size).strip('"'), errors="coerce")
            rows.append({"pipe_id": int(r.OBJECTID), "size": r.Size, "dia": dia,
                         "galv": int(r.Material == "Galvanize"),
                         "geometry": substring(r.geometry, k * step, (k + 1) * step)})
    p = gpd.GeoDataFrame(rows, crs=UTM)
    p = p[p.length > 1].reset_index(drop=True)
    p["piece"] = p.index
    p["len_m"] = p.length
    z = gpd.read_file(SRC / "pressure_zones.geojson").to_crs(UTM)[["Name", "geometry"]]
    c = gpd.GeoDataFrame({"piece": p.piece}, geometry=p.geometry.interpolate(0.5, normalized=True), crs=UTM)
    zone = gpd.sjoin(c, z, how="left", predicate="within").drop_duplicates("piece").set_index("piece").Name
    p["zone_name"] = zone.reindex(p.piece).fillna("none").str.replace(" Plane", "").to_numpy()
    p["zone"] = p.zone_name.astype("category").cat.codes
    return p


def leaks() -> gpd.GeoDataFrame:
    L = gpd.read_file(SRC / "leak_survey.geojson")
    L["time"] = pd.to_datetime(L["datetime"], unit="ms", errors="coerce")
    L = L[L.time.notna() & (L.ObjectId != 1611)].to_crs(UTM)
    L["construction"] = L.cause_of_leak.eq("Construction_Maintenance_Induce")
    L["m"] = (L.time.dt.year - 2019) * 12 + L.time.dt.month - 10  # months since 2019-10
    return L[["ObjectId", "time", "m", "construction", "geometry"]].reset_index(drop=True)


def panel(p: gpd.GeoDataFrame, L: gpd.GeoDataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    months = pd.period_range(FIRST, LAST, freq="M")
    n = len(p)
    own = gpd.sjoin_nearest(L, p[["piece", "geometry"]], max_distance=SNAP_M, distance_col="dist").drop_duplicates("ObjectId")
    pairs = {}
    for r in (200, 500):
        b = gpd.GeoDataFrame({"piece": p.piece}, geometry=p.geometry.buffer(r), crs=UTM)
        pairs[r] = gpd.sjoin(L[["m", "geometry"]], b, predicate="within")[["piece", "m"]]

    def counts(df, lo, hi):
        d = df[(df.m >= lo) & (df.m < hi)]
        return np.bincount(d.piece.to_numpy(), minlength=n)

    def since(df, k):
        d = df[df.m < k].groupby("piece").m.max()
        return (k - d).reindex(range(n)).fillna(999).to_numpy()

    target = own[~own.construction]
    out = []
    for k, per in enumerate(months):
        out.append(pd.DataFrame({
            "piece": p.piece.to_numpy(), "month": str(per), "k": k,
            "y": (counts(target, k, k + 1) > 0).astype(int),
            "own_all": counts(own, 0, k), "own_24": counts(own, k - 24, k), "own_12": counts(own, k - 12, k),
            "n200_all": counts(pairs[200], 0, k), "n200_24": counts(pairs[200], k - 24, k),
            "n500_all": counts(pairs[500], 0, k), "n500_24": counts(pairs[500], k - 24, k),
            "mo_since_own": since(own, k), "mo_since_200": since(pairs[200], k),
            "log_len": np.log(p.len_m.to_numpy()), "dia": p.dia.to_numpy(), "galv": p.galv.to_numpy(),
            "zone": p.zone.to_numpy(), "m_sin": np.sin(2 * np.pi * per.month / 12),
            "m_cos": np.cos(2 * np.pi * per.month / 12)}))
    return pd.concat(out, ignore_index=True), own


def _metrics(y, s, length) -> dict:
    order = np.argsort(-s, kind="stable")
    out = {"auc": float(roc_auc_score(y, s)), "avg_precision": float(average_precision_score(y, s))}
    for q in (1, 5, 10, 20):
        top = order[: int(np.ceil(len(y) * q / 100))]
        out[f"capture_top{q}"] = float(y[top].sum() / y.sum())
        out[f"length_share_top{q}"] = float(length[top].sum() / length.sum())
    return out


def _auc_ci(te: pd.DataFrame, col: str, n_boot: int = 200, seed: int = 0) -> list[float]:
    """Bootstrap over pipe pieces (a piece's 12 months are resampled together)."""
    rng = np.random.default_rng(seed)
    ids = te.piece.unique()
    grp = {i: g for i, g in te.groupby("piece")[["y", col]]}
    vals = []
    for _ in range(n_boot):
        b = pd.concat([grp[i] for i in rng.choice(ids, len(ids))])
        if b.y.nunique() == 2:
            vals.append(roc_auc_score(b.y, b[col]))
    return [float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5))]


def run(cfg: Config) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    p, L = pieces(), leaks()
    df, own = panel(p, L)
    df["len_m"] = np.exp(df.log_len)
    tr = df[(df.month >= TRAIN_FROM) & (df.month < TEST_FROM)]
    te = df[df.month >= TEST_FROM].copy()
    model = HistGradientBoostingClassifier(max_depth=4, learning_rate=0.05, max_iter=300, min_samples_leaf=100,
                                           l2_regularization=1.0, categorical_features=[FEATS.index("zone")],
                                           random_state=0).fit(tr[FEATS], tr.y)
    te["score"] = model.predict_proba(te[FEATS])[:, 1]
    te["pct"] = np.ceil(te.score.rank(ascending=False, method="first") / len(te) * 100).clip(1, 100).astype(int)
    y, ln = te.y.to_numpy(), te.len_m.to_numpy()
    res = {"model": _metrics(y, te.score.to_numpy(), ln),
           "leak history only (leaks within 200 m, all time)": _metrics(y, te.n200_all.to_numpy().astype(float), ln),
           "pipe length only": _metrics(y, ln, ln)}
    res["model"]["auc_ci"] = _auc_ci(te, "score")
    res["leak history only (leaks within 200 m, all time)"]["auc_ci"] = _auc_ci(te, "n200_all")

    # ---- outputs for the map
    months = sorted(te.month.unique())
    wide = te.pivot(index="piece", columns="month", values="pct")
    g = p[["piece", "pipe_id", "size", "dia", "len_m", "zone_name", "geometry"]].copy()
    g["len_m"] = g.len_m.round(0)
    for mo in months:
        g["r_" + mo.replace("-", "_")] = wide[mo].reindex(g.piece).to_numpy()
    g["r_best"] = wide.min(axis=1).reindex(g.piece).to_numpy()
    last = df[df.month == LAST].set_index("piece")
    g["leaks_on_piece"] = last.own_all.reindex(g.piece).to_numpy()
    g["leaks_200m"] = last.n200_all.reindex(g.piece).to_numpy()
    g.to_crs(4326).to_file(OUT / "pipe_risk.geojson", driver="GeoJSON", COORDINATE_PRECISION=6)

    own["month"] = own.time.dt.strftime("%Y-%m")
    hold = own[own.month.isin(months)].merge(te[["piece", "month", "pct"]], on=["piece", "month"], how="left")
    leak_rank = {int(r.ObjectId): {"piece": int(r.piece), "pct": int(r.pct), "dist_m": round(float(r.dist), 1),
                                   "construction": bool(r.construction)} for r in hold.itertuples()}
    per_month = [{"month": mo, "leaks": int(gm.y.sum()), "in_top5": int(gm.y[gm.pct <= 5].sum()),
                  "in_top20": int(gm.y[gm.pct <= 20].sum())} for mo, gm in te.groupby("month")]
    n_window = int(((L.time >= "2025-11-01") & (L.time < "2026-11-01")).sum())
    summary = {"months": months, "pieces": int(len(p)), "pipe_km": round(float(p.len_m.sum() / 1000), 1),
               "train": [TRAIN_FROM, "2025-10"], "holdout": [TEST_FROM, LAST],
               "holdout_rows": int(len(te)), "holdout_positives": int(y.sum()),
               "leaks_in_holdout_window": n_window, "leaks_snapped_within_50m": int(len(hold)),
               "metrics": res, "per_month": per_month, "leak_rank": leak_rank,
               "features": FEATS, "piece_m": PIECE_M, "snap_m": SNAP_M}
    (OUT / "risk_summary.json").write_text(json.dumps(summary, indent=1))

    # ---- risk score for Peter's package samples, at the month of each sample's t0 (always in the hold-out)
    pkg_auc = None
    if (PKG / "train" / "index.csv").exists():
        idx = pd.concat([pd.read_csv(PKG / s / "index.csv") for s in ("train", "test")], ignore_index=True)
        pts = gpd.GeoDataFrame(idx[["sample_id", "split", "label", "t0_date"]],
                               geometry=gpd.points_from_xy(idx.utm_x, idx.utm_y), crs=UTM)
        j = gpd.sjoin_nearest(pts, p[["piece", "geometry"]], distance_col="piece_dist_m").drop_duplicates("sample_id")
        j["month"] = j.t0_date.str.slice(0, 7)
        j = j.merge(te[["piece", "month", "score", "pct"] + FEATS[:9]], on=["piece", "month"], how="left")
        cols = ["sample_id", "split", "label", "month", "piece", "piece_dist_m", "score", "pct"] + FEATS[:9]
        j[cols].rename(columns={"score": "risk_score", "pct": "risk_pct", "month": "risk_month"}).round(
            {"piece_dist_m": 1, "risk_score": 6}).to_csv(PKG / "risk_context.csv", index=False)
        t = j[(j.split == "test") & j.score.notna()]
        pkg_auc = {"n": int(len(t)), "positives": int(t.label.sum()), "auc": float(roc_auc_score(t.label, t.score)),
                   "missing_score": int(j.score.isna().sum())}
        summary["package_test"] = pkg_auc
        (OUT / "risk_summary.json").write_text(json.dumps(summary, indent=1))

    rows = "\n".join(
        f"| {k} | {v['auc']:.3f}{' [%.3f, %.3f]' % tuple(v['auc_ci']) if 'auc_ci' in v else ''} | {v['avg_precision']:.4f} | "
        + " | ".join(f"{v[f'capture_top{q}']:.0%} ({v[f'length_share_top{q}']:.0%} of length)" for q in (1, 5, 10, 20)) + " |"
        for k, v in res.items())
    REPORT.write_text(f"""# Coryell leak-risk ranking per pipe piece and month

_Generated by `pixi run coryell-risk`._

- {len(p)} pipe pieces of at most {PIECE_M:.0f} m ({summary['pipe_km']} km of pipe); one row per piece and month.
- Target: at least one non-construction leak repaired on the piece in the month (leak snapped to the nearest piece within {SNAP_M:.0f} m).
- Features use only leaks repaired before the month starts: leak counts on the piece and within 200 m / 500 m, months since the last one, piece length, diameter, galvanised flag, pressure zone, month of year. No radar.
- Train {TRAIN_FROM} to 2025-10 ({len(tr)} rows, {int(tr.y.sum())} positive). Hold-out {TEST_FROM} to {LAST}: {len(te)} rows, {int(y.sum())} positive.
- {len(hold)} of the {n_window} leaks repaired in the hold-out window snap to a pipe within {SNAP_M:.0f} m.

| Ranking | AUC [95% CI] | Avg precision | Top 1% | Top 5% | Top 10% | Top 20% |
|---|---|---|---|---|---|---|
{rows}

"Top q%" is the share of hold-out leaks inside the q% highest-ranked piece-months, with the share of pipe length those rows hold in brackets. The AUC interval resamples pipe pieces.

Peter's package, test split, risk score at each sample's t0 month: {('AUC %.3f on %d samples (%d leaks)' % (pkg_auc['auc'], pkg_auc['n'], pkg_auc['positives'])) if pkg_auc else 'package not found'}. Negatives there are drawn in proportion to pipe length, so this number also reflects where leaks concentrate.
""")
    print(REPORT.read_text())
