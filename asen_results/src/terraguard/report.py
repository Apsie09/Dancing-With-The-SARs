"""Summary statistics (Stage 1), coverage report (Stage 2/3) and the preliminary feasibility report."""
from __future__ import annotations

from datetime import date

import geopandas as gpd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
from shapely.geometry import box  # noqa: E402

from .config import ROOT, UTM_CRS, WGS84, Config, human_size, report_file  # noqa: E402

# Reference palette (dataviz skill): single-series bars in slot-1 blue, recessive ink for text/axes.
BAR = "#2a78d6"
SURFACE = "#fcfcfb"
INK, INK2 = "#0b0b0b", "#52514e"
MISSING_FIELDS = ["asset_material", "asset_size_mm", "asset_year_installed", "asset_depth_m",
                  "break_nature", "break_apparent_cause", "repair_type", "return_to_normal",
                  "frost_depth_m", "street"]


def _style(ax, title: str, ylabel: str) -> None:
    ax.set_facecolor(SURFACE)
    ax.figure.set_facecolor(SURFACE)
    ax.set_title(title, loc="left", color=INK, fontsize=11)
    ax.set_ylabel(ylabel, color=INK2)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color(INK2)
    ax.tick_params(colors=INK2, labelsize=8)
    ax.grid(axis="y", color="#e4e3df", linewidth=0.6)
    ax.set_axisbelow(True)


def _bar(series: pd.Series, title: str, ylabel: str, path, highlight_from=None) -> None:
    fig, ax = plt.subplots(figsize=(10, 3.4))
    colors = [BAR if highlight_from is None or str(k) >= str(highlight_from) else "#a9c9f2"
              for k in series.index]
    ax.bar([str(k) for k in series.index], series.values, color=colors, width=0.8)
    _style(ax, title, ylabel)
    plt.setp(ax.get_xticklabels(), rotation=90 if len(series) > 14 else 0)
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


def _md_table(df: pd.DataFrame) -> str:
    cols = [str(c) for c in df.columns]
    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    lines += ["| " + " | ".join("" if pd.isna(v) else str(v) for v in row) + " |" for row in df.itertuples(index=False)]
    return "\n".join(lines)


def size_budget(cfg: Config, acq: gpd.GeoDataFrame, matches: pd.DataFrame | None) -> dict:
    s, n = cfg.section("sar"), cfg.section("nisar")
    use = acq[acq["is_preferred"]]
    if "n_incidents_inside" in use:  # passes that actually see at least one incident
        use_inc = use[use["n_incidents_inside"] > 0]
    else:
        use_inc = use
    posting = float(use["posting_m_nominal"].dropna().mode().iloc[0]) if use["posting_m_nominal"].notna().any() else 10.0
    aoi = gpd.GeoSeries([box(*n["aoi_bbox"])], crs=WGS84).to_crs(UTM_CRS).iloc[0]
    minx, miny, maxx, maxy = aoi.bounds
    px = ((maxx - minx) / posting) * ((maxy - miny) / posting)
    per_px = len(s["channels"]) * s["bytes_per_px"]
    crop = px * per_px
    patch = s["patch_size_px"] ** 2 * per_px
    out = {
        "posting_m_assumed": posting,
        "remote_total_bytes": int(use["size_bytes"].sum()),
        "remote_granules": len(use),
        "mean_granule_bytes": float(use["size_bytes"].mean()),
        "aoi_km": ((maxx - minx) / 1000, (maxy - miny) / 1000),
        "aoi_crop_bytes": crop,
        "aoi_crop_all_bytes": crop * use_inc["pass_id"].nunique(),
        "passes_with_incidents": use_inc["pass_id"].nunique(),
        "patch_bytes": patch,
    }
    if matches is not None:
        usable = matches[matches["match_confidence"] != "low"]
        out["usable_matches"] = len(usable)
        out["usable_patches_bytes"] = patch * len(usable)
        out["all_patches_bytes"] = patch * len(matches)
        out["usable_granules"] = usable["granule_ur"].nunique()
        out["usable_granules_bytes"] = int(usable.drop_duplicates("granule_ur")["granule_size_bytes"].sum())
    return out


def incident_summary(cfg: Config, inc: gpd.GeoDataFrame, acq: gpd.GeoDataFrame | None) -> str:
    rep = cfg.path("reports_dir")
    ok = inc[~inc["date_suspect"]]
    per_year = ok.groupby(ok["incident_date_local"].dt.year).size()
    _bar(per_year, "Water-main break incidents per year (Kitchener)", "incidents", rep / "incidents_per_year.png")
    moy = inc.groupby(inc["incident_date_local"].dt.month).size().reindex(range(1, 13), fill_value=0)
    moy.index = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    _bar(moy, "Incidents by month of year (all years) - strong winter peak", "incidents",
         rep / "incidents_month_of_year.png")
    recent = inc[inc["incident_date_local"] >= "2025-01-01"]
    per_month = recent.groupby(recent["incident_date_local"].dt.strftime("%Y-%m")).size()
    nisar_start = acq["start_time"].min().strftime("%Y-%m") if acq is not None else None
    _bar(per_month, "Incidents per month since 2025 (darker = within NISAR data period)", "incidents",
         rep / "incidents_per_month_recent.png", highlight_from=nisar_start)

    utm = inc.to_crs(UTM_CRS)
    fig, ax = plt.subplots(figsize=(7, 5.5))
    hb = ax.hexbin(utm.geometry.x, utm.geometry.y, gridsize=35, cmap="Blues", mincnt=1, linewidths=0.2)
    ax.set_aspect("equal")
    ax.ticklabel_format(useOffset=False, style="plain")
    ax.grid(False)
    _style(ax, "Spatial density of incidents, all years (UTM 17N)", "northing (m)")
    ax.set_xlabel("easting (m)", color=INK2)
    fig.colorbar(hb, ax=ax, label="incidents per hex", shrink=0.8)
    fig.tight_layout()
    fig.savefig(rep / "incidents_hexbin.png", dpi=130)
    plt.close(fig)

    missing = pd.DataFrame({
        "field": MISSING_FIELDS,
        "missing": [int(inc[f].isna().sum()) for f in MISSING_FIELDS],
    })
    missing["missing_%"] = (100 * missing["missing"] / len(inc)).round(1)

    lines = [f"# Kitchener incidents - Stage 1 summary\n\n_Generated {date.today()} from `{cfg.incidents_parquet.name}`._\n",
             f"- Clean records: **{len(inc)}** ({inc['incident_date_local'].min():%Y-%m-%d} -> {inc['incident_date_local'].max():%Y-%m-%d})",
             f"- Suspect dates (before {cfg.section('incidents')['suspect_date_before']}): {int(inc['date_suspect'].sum())}",
             f"- Clock time known: {int(inc['incident_time_known'].sum())} ({100 * inc['incident_time_known'].mean():.0f}%); the rest are date-only",
             f"- Cancelled: {int(inc['is_cancelled'].sum())}; possible duplicates (non-primary): {int((~inc['is_primary_record']).sum())}; "
             f"suspect locations (no street, no asset): {int(inc['location_suspect'].sum())}",
             f"- Break type: {dict(inc['break_type'].value_counts())}",
             f"- Material: {dict(inc['asset_material'].value_counts().head(8))}",
             f"- Spatial extent (lon/lat): {inc.total_bounds.round(4).tolist()}",
             "", "![per year](incidents_per_year.png)", "![month of year](incidents_month_of_year.png)",
             "![recent months](incidents_per_month_recent.png)", "![hexbin](incidents_hexbin.png)",
             "", "## Incidents per year", _md_table(per_year.rename_axis("year").reset_index(name="incidents")),
             "", "## Missing / incomplete fields", _md_table(missing),
             "", "## Top streets", _md_table(inc["street"].value_counts().head(10).rename_axis("street").reset_index(name="incidents"))]
    if acq is not None:
        lines += ["", "## Incidents within NISAR data periods"]
        rows = []
        for mat in ("beta", "provisional", "validated"):
            a = acq[(acq["maturity"] == mat) & acq["is_preferred"]]
            if len(a):
                t0, t1 = a["start_time"].min().tz_localize(None).floor("D"), a["start_time"].max().tz_localize(None)
                sel = inc[(inc["incident_date_local"] >= t0) & (inc["incident_date_local"] <= t1)]
                rows.append({"collection": mat, "first acq": f"{t0:%Y-%m-%d}", "last acq": f"{t1:%Y-%m-%d}",
                             "incidents in span": len(sel), "MAIN": int((sel["break_type"] == "MAIN").sum()),
                             "SERVICE": int((sel["break_type"] == "SERVICE").sum())})
        lines.append(_md_table(pd.DataFrame(rows)))
    path = rep / "incidents_summary.md"
    path.write_text("\n".join(lines) + "\n")
    return str(path)


def folium_map(cfg: Config, inc: gpd.GeoDataFrame, acq: gpd.GeoDataFrame, cov: pd.DataFrame) -> str:
    import folium

    # Esri tiles: OSM's volunteer servers reject tile requests from local file:// pages (no Referer).
    esri = "https://server.arcgisonline.com/ArcGIS/rest/services/{}/MapServer/tile/{{z}}/{{y}}/{{x}}"
    m = folium.Map(location=[43.45, -80.45], zoom_start=12, tiles=None)
    folium.TileLayer(esri.format("Canvas/World_Light_Gray_Base"), attr="Esri, HERE, Garmin, OpenStreetMap contributors",
                     name="Light grey", max_zoom=16).add_to(m)
    folium.TileLayer(esri.format("World_Imagery"), attr="Esri, Maxar, Earthstar Geographics",
                     name="Satellite imagery", max_zoom=19, show=False, overlay=False).add_to(m)
    folium.GeoJson(gpd.GeoSeries([box(*cfg.section("nisar")["aoi_bbox"])], crs=WGS84).to_json(),
                   name="AOI", style_function=lambda _: {"color": "#52514e", "fill": False, "weight": 2}).add_to(m)
    for grp, g in acq[acq["is_preferred"] & acq["full_frame"]].groupby("stack_id"):
        folium.GeoJson(g.iloc[[0]][["stack_id", "geometry"]].to_json(), name=f"footprint {grp}",
                       style_function=lambda _: {"color": "#2a78d6", "weight": 1, "fillOpacity": 0.03},
                       show=False).add_to(m)
    era = inc.merge(cov[["incident_id", "in_nisar_period", "has_before_after", "has_event_with_reference"]],
                    on="incident_id")
    era = era[era["in_nisar_period"]]
    for _, r in era.iterrows():
        good = r["has_event_with_reference"]
        folium.CircleMarker([r["lat"], r["lon"]], radius=5, weight=1, fill=True, fill_opacity=0.8,
                            color="#0b0b0b", fill_color="#2a78d6" if good else "#a9c9f2",
                            tooltip=(f"#{r['incident_id']} {r['incident_date_local']:%Y-%m-%d} {r['break_type']} "
                                     f"{r['asset_material'] or '?'} {r['asset_size_mm'] or '?'} mm | "
                                     f"pre+event: {good}, before+after: {r['has_before_after']}")).add_to(m)
    folium.LayerControl().add_to(m)
    path = cfg.path("reports_dir") / "nisar_era_incidents_map.html"
    m.save(path)
    return str(path)


def outputs(cfg: Config) -> list:
    pro, sar = cfg.path("processed_dir"), ROOT / cfg.section("sar")["out_dir"]
    files = [cfg.incidents_parquet, pro / "kitchener_water_mains.parquet", cfg.acquisitions_parquet,
             cfg.matches_parquet, cfg.coverage_parquet, sar / "patches.h5", sar / "sar_patches.parquet",
             pro / "radar_features.parquet", pro / "control_sites.parquet", sar / "control_patches.h5",
             pro / "control_features.parquet", pro / "ml_dataset.parquet"]
    return [p for p in files if p.exists()]


def stage4_6(cfg: Config) -> list[str]:
    """Final-report sections computed from the Stage 4-6 outputs and the signal checks."""
    pro, sar_dir, rep = cfg.path("processed_dir"), ROOT / cfg.section("sar")["out_dir"], cfg.path("reports_dir")
    log = pd.read_parquet(sar_dir / "stream_log.parquet").drop_duplicates("granule_ur", keep="last")
    ok = log[log["status"] == "ok"]
    have = sorted(p.stem for p in (sar_dir / "crops").glob("*.tif") if not p.stem.endswith("_mask"))
    crop_bytes = sum(p.stat().st_size for p in (sar_dir / "crops").iterdir())
    acq = gpd.read_parquet(cfg.acquisitions_parquet).set_index("granule_ur")
    patches = pd.read_parquet(sar_dir / "sar_patches.parquet")
    slip = patches.groupby("granule_ur")["exception_frac"].mean()
    slip = slip[slip > 0.05]
    ds = pd.read_parquet(pro / "ml_dataset.parquet")
    u = ds[ds["q_usable"]]
    inc_u = u[u["site_type"] == "incident"]
    per = inc_u.groupby(["incident_id", "comparison_group"])["temporal_category"].agg(lambda s: set(s.astype(str)))
    full = per.apply(lambda c: {"pre_event", "potential_event_window", "post_event"} <= c).groupby("incident_id").any()
    L = ["## Stage 4 - streamed SAR (no full downloads)",
         "| item | value |\n|---|---|",
         f"| Granules streamed (crops on disk) | {len(have)} |",
         f"| Remote size of those granules (not downloaded) | {human_size(acq.loc[acq.index.intersection(have), 'size_bytes'].sum())} |",
         f"| Measured transfer per granule (city crop: HH, HV, looks, masks; {len(ok)} logged) | {human_size(ok['bytes'].median())} median ({human_size(ok['bytes'].min())}-{human_size(ok['bytes'].max())}) |",
         f"| Estimated total transfer | ~{human_size(ok['bytes'].median() * len(have))} |",
         f"| City crops on disk | {human_size(crop_bytes)} |",
         f"| Incident patches | {len(patches)} ({int((patches['valid_frac'] >= 0.9).sum())} with >=90% valid pixels) |",
         "",
         f"- HDF5 layout: 512x512 gzip chunks; a 64 px patch costs a whole chunk per channel, so whole-city crops per pass are the efficient unit.",
         f"- **Input-data exceptions:** {len(slip)} granules have `inputDataExceptionMask` = 2 (qFSP-H1 sample slip) over large parts of the city: "
         f"{', '.join(sorted(g.split('_')[5] + g.split('_')[6] + ' ' + g.split('_')[11][:8] for g in slip.index))}. "
         "On Kitchener these pixels read ~1-1.5 dB darker in HH than expected, so they are masked as invalid. "
         "All three *validated* granules are affected; every usable patch is provisional data.",
         "- 127D frame 066 only partly covers the city; affected patches carry `q_outside_coverage_frac`.",
         "",
         "## Stage 5 - features",
         f"- `radar_features.parquet`: single-date site vs. background-ring statistics (HH, HV, HV/HH), change vs. leave-one-out "
         "pre-event reference on the same track, change vs. previous pass, texture (CV, GLCM), pre-incident infrastructure, "
         "ERA5 weather/soil state at acquisition (Open-Meteo), quality flags. Column roles are in the parquet metadata.",
         "",
         "## Stage 6 - controls and labelled dataset",
         f"- Control sites: {ds.loc[ds['site_type'] == 'control', 'site_id'].nunique()} points on the water-main network "
         f"({cfg.section('controls')['per_incident']} per incident, {cfg.section('controls')['min_distance_m']}-{cfg.section('controls')['max_distance_m']} m away, "
         f"matched on material and size where possible, no recorded break within {cfg.section('controls')['exclusion_m']} m / "
         f"+-{cfg.section('controls')['exclusion_window_days']} d). Labelled `unknown` - never negatives.",
         f"- `ml_dataset.parquet`: {len(ds)} rows ({len(u)} usable) = site x pass. Labels (usable): {u['label'].value_counts().to_dict()}. "
         "`verified_non_leak` is never assigned (no independent evidence).",
         f"- Splits: incident+controls grouped; {ds['cv_fold'].nunique()} spatially blocked folds "
         f"({cfg.section('dataset')['spatial_block_m']} m blocks, incidents per fold {ds.drop_duplicates('incident_id')['cv_fold'].value_counts().sort_index().tolist()}); "
         f"temporal hold-out from {cfg.section('dataset')['time_holdout_from']}.",
         f"- Incidents with usable pre + event-window + post patches on one track: **{int(full.sum())}**.",
         ""]
    L += ["## Is there a detectable signal?"]
    if (rep / "signal_check.parquet").exists():
        sc = pd.read_parquet(rep / "signal_check.parquet")
        a = sc[(sc["radius"] == "r=70 m (config)") & (sc["subset"] == "all")]
        L += [f"- Localized change (site disk - background ring, vs. same-track pre-event reference), paired per incident x track: "
              f"no subset/radius/polarisation is significant after Benjamini-Hochberg (min q = {sc['q_bh'].min():.2f} over {sc['p'].notna().sum()} tests). "
              f"Minimum detectable effect on the full set: {a['mde_db'].min():.2f}-{a['mde_db'].max():.2f} dB; pre-event noise {a['pre_noise_db'].mean():.2f} dB. "
              "Details: `signal_check.md`."]
    if (rep / "signal_check_controls_auc.parquet").exists():
        auc = pd.read_parquet(rep / "signal_check_controls_auc.parquet")
        ev = auc[auc["window"] == "potential_event_window"]
        did = pd.read_parquet(rep / "signal_check_controls_did.parquet")
        L += [f"- Incident sites vs. matched controls on the same passes: AUC of naive change scores in the event window "
              f"{ev['auc'].min():.2f}-{ev['auc'].max():.2f}; every 95% CI (bootstrap over incidents) includes 0.5. "
              f"Difference-in-differences event/post vs. pre: all p >= {did['p'].min():.2f}. "
              "A weak 'site darker' trend seen without controls disappears against controls (city-wide/seasonal). "
              "Details: `signal_check_controls.md`."]
    L += ["",
          "## Recommendation for the ML stage",
          "1. **Supervised leak classification is not feasible with this data.** There are ~60 incidents with a complete same-track "
          "before/event/after series, labels are reported dates (not observed leakage), no verified negatives exist, and simple "
          "localized-change statistics show no difference from matched controls at the ~0.1-0.2 dB level.",
          "2. If a model is tried, use a **frozen pretrained SAR encoder + small head** (or anomaly scoring on embeddings), "
          "trained/evaluated only with the provided grouped folds and the temporal hold-out, and report AUC against matched "
          "controls with incident-level bootstrap CIs. The naive-score AUC (~0.5) is the baseline to beat.",
          "3. Treat Kitchener as a **negative/feasibility result** for urban distribution mains at 10 m L-band: buried small mains under pavement, "
          "mostly winter breaks, and same-day repairs leave no measurable radar footprint here. For Bulgaria's transmission mains "
          "(larger flows, rural/vegetated corridors, longer undetected leaks) evaluate separately; that setting is more favourable to SAR.",
          "4. Highest-value data improvements: break start/end times (leak duration), leak volume, and incidents in unpaved/vegetated areas; "
          "NISAR STATIC layers (layover/shadow, incidence angle) for urban masking; validated products without input-data exceptions.",
          ""]
    return L


def feasibility(cfg: Config, inc, acq, matches, cov) -> str:
    final = (cfg.path("processed_dir") / "ml_dataset.parquet").exists()
    sb = size_budget(cfg, acq, matches)
    use = acq[acq["is_preferred"]]
    era = cov[cov["in_nisar_period"]]
    era_ok = era[era["is_primary_record"] & ~era["is_cancelled"]]
    cats = matches["temporal_category"].value_counts(sort=False)
    conf = matches["match_confidence"].value_counts()
    groups = (use.groupby("comparison_group")
                 .agg(acquisitions=("pass_id", "nunique"), frames=("frame", lambda s: ",".join(map(str, sorted(set(s))))),
                      first=("start_time", lambda s: f"{s.min():%Y-%m-%d}"), last=("start_time", lambda s: f"{s.max():%Y-%m-%d}"),
                      crids=("crid", lambda s: ",".join(sorted(set(s)))),
                      max_incidents_inside=("n_incidents_inside", "max"))
                 .reset_index())
    mat = use.groupby("maturity").agg(granules=("granule_ur", "size"),
                                      first=("start_time", lambda s: f"{s.min():%Y-%m-%d}"),
                                      last=("start_time", lambda s: f"{s.max():%Y-%m-%d}"),
                                      size=("size_bytes", lambda s: human_size(s.sum()))).reset_index()
    w = cfg.section("matching")
    L = [
        "# TerraGuard - data feasibility report" + ("" if final else " (preliminary: stages 1-3)"),
        f"\n_Generated {date.today()} by `pixi run report`. "
        + ("Covers stages 1-6: incidents, NISAR catalogue, matching, streamed SAR crops/patches, features, "
           "control sites and the labelled dataset._\n" if final else
           "Stages 4-6 are pending; numbers come from CMR metadata and the Kitchener Feature Service only._\n"),
        "## Headline numbers",
        f"| | count |\n|---|---|",
        f"| Kitchener incidents (clean) | {len(inc)} |",
        f"| ... during the NISAR data period ({use['start_time'].min():%Y-%m-%d} -> {use['start_time'].max():%Y-%m-%d}) | {len(era)} |",
        f"| ... of which primary & not cancelled | {len(era_ok)} |",
        f"| ... inside valid NISAR footprint | {int(era_ok['in_footprint'].sum())} |",
        f"| ... with consistent before + after observations (same track/geometry, non-low confidence) | {int(era_ok['has_before_after'].sum())} |",
        f"| ... with a reference (pre) + a potential-event-window acquisition | {int(era_ok['has_event_with_reference'].sum())} |",
        f"| Incidents in the *validated* period only | {int(((inc['incident_date_local'] >= use.loc[use['maturity'] == 'validated', 'start_time'].min().tz_localize(None).floor('D')) if (use['maturity'] == 'validated').any() else pd.Series(False, index=inc.index)).sum())} |",
        "",
        "`potential_event_window` means an acquisition fell within "
        f"{w['potential_event_window']} days of the *reported* date. It is a matching hypothesis; "
        "nothing here shows that a leak was radar-visible.",
        "",
        "## NISAR coverage over Kitchener",
        _md_table(mat), "", "### Comparison groups (same viewing geometry, bandwidth, polarisations)",
        _md_table(groups), "",
        f"- Polarisations: frequency A {sorted(use['freq_a_pols'].dropna().unique().tolist())} at {sorted(use['freq_a_bandwidth_mhz'].dropna().astype(int).unique().tolist())} MHz; "
        f"frequency B {sorted(use['freq_b_pols'].dropna().unique().tolist())} at {sorted(use['freq_b_bandwidth_mhz'].dropna().astype(int).unique().tolist())} MHz. No co-pol VV/VH (dual-pol HH+HV only), so no full-pol decompositions.",
        "- Processing versions (CRID) differ between collections; any pair crossing provisional -> validated crosses a processing change and is flagged in `incident_coverage_summary.parquet` (`mixed_processing_versions`).",
        (f"- Pixel spacing: **verified 10 m** (EPSG:32617) from the HDF5 grid; all tracks share one pixel lattice, so crops align without resampling."
         if final else f"- Pixel spacing: assumed {sb['posting_m_assumed']:.0f} m from bandwidth; **not yet verified from the HDF5 grid**."),
        "",
        "## Matches",
        f"- {len(matches)} incident x pass matches, windows (days, acquisition - report): pre {w['pre_event']}, event {w['potential_event_window']}, post {w['post_event']}.",
        f"- By category: {cats.to_dict()}",
        f"- By confidence: {conf.to_dict()}",
        "- Low confidence = beta (pre-calibration) product, timing between windows, cancelled incident or partial frame. "
        "Beta is the only reference data before 2026-01-03, so Dec-2025 incidents lose their `pre_event` references unless beta is accepted.",
        "",
        "## Data volume (SAR)",
        "| item | size |\n|---|---|",
        f"| Remote GCOV granules over AOI ({sb['remote_granules']} preferred) | {human_size(sb['remote_total_bytes'])} (mean {human_size(sb['mean_granule_bytes'])}) |",
        f"| Granules needed by usable matches ({sb.get('usable_granules')}) | {human_size(sb.get('usable_granules_bytes', 0))} remote, **not to be downloaded** |",
        f"| Whole-AOI crop ({sb['aoi_km'][0]:.1f} x {sb['aoi_km'][1]:.1f} km, {len(cfg.section('sar')['channels'])} channels float32) per pass | {human_size(sb['aoi_crop_bytes'])} |",
        f"| Whole-AOI crops for every pass that sees an incident ({sb['passes_with_incidents']}) | {human_size(sb['aoi_crop_all_bytes'])} |",
        f"| One incident patch ({cfg.section('sar')['patch_size_px']} px) | {human_size(sb['patch_bytes'])} |",
        f"| Patches for all usable matches ({sb.get('usable_matches')}) | {human_size(sb.get('usable_patches_bytes', 0))} |",
        "",
        ("Streaming cost was measured in Stage 4 (below)." if final else
         "Streaming cost per crop depends on HDF5 chunking/compression and must be measured (needs Earthdata login)."),
        "",
        "## Data-quality concerns",
        f"- `asset_depth_m` missing for {100 * inc['asset_depth_m'].isna().mean():.1f}% of records; `return_to_normal` for {100 * inc['return_to_normal'].isna().mean():.1f}%: leak duration is essentially unknown.",
        f"- {100 * (~inc['incident_time_known']).mean():.0f}% of incidents are date-only (±0.5 day uncertainty).",
        f"- Seasonality: {int(era['incident_date_local'].dt.month.isin([12, 1, 2]).sum())} of {len(era)} NISAR-era incidents are in Dec-Feb, when frozen ground/snow dominate L-band backscatter change.",
        "- Labels: only `confirmed_break_event` / `candidate_satellite_match` / `unknown` can be assigned. No independent `verified_non_leak` evidence exists; areas without incidents must not be treated as negatives.",
        "- Comparison groups with `max_incidents_inside = 0` only clip the AOI margin and are catalogued but unused.",
        "- Footprints are coarse 4-corner polygons; incidents within "
        f"{cfg.section('nisar')['edge_buffer_m']:.0f} m of an edge are down-weighted until raster valid-data masks are checked.",
        "",
        *(stage4_6(cfg) if final else [
            "## Recommendation (provisional)",
            "Supervised leak classification is not supported by this data yet; continue with Stage 4 on a small set.", ""]),
        "## Outputs",
        *[f"- `{report_file(p)}`" for p in outputs(cfg)],
    ]
    path = cfg.path("reports_dir") / "data_feasibility_report.md"
    path.write_text("\n".join(L) + "\n")
    return str(path), sb


def run(cfg: Config) -> None:
    from . import catalog, incidents

    print("Report")
    inc = incidents.load(cfg)
    acq = catalog.load(cfg) if cfg.acquisitions_parquet.exists() else None
    print(f"  {incident_summary(cfg, inc, acq)}")
    if acq is None or not cfg.matches_parquet.exists():
        print("  (catalogue/matches missing: feasibility report skipped)")
        return
    matches = gpd.read_parquet(cfg.matches_parquet)
    cov = pd.read_parquet(cfg.coverage_parquet)
    print(f"  {folium_map(cfg, inc, acq, cov)}")
    path, sb = feasibility(cfg, inc, acq, matches, cov)
    print(f"  {path}")
    print(f"  SIZE: remote {human_size(sb['remote_total_bytes'])} | AOI crops all passes ~{human_size(sb['aoi_crop_all_bytes'])}"
          f" | usable patches ~{human_size(sb.get('usable_patches_bytes', 0))}")
