"""Offline unit tests for the matching / cataloguing logic (no network)."""
import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import box

from terraguard.catalog import annotate
from terraguard.config import Config
from terraguard.matching import categorize, incident_reference_time

WINDOWS = {"pre_event": (-120, -21), "potential_event_window": (-14, 3), "post_event": (10, 120)}


def test_categorize_windows_and_gaps():
    delta = np.array([-60.0, -21.0, -18.0, 0.0, 3.0, 5.0, 30.0])
    out = categorize(delta, np.zeros_like(delta), WINDOWS)
    assert out.tolist() == ["pre_event", "pre_event", "timing_uncertain", "potential_event_window",
                            "potential_event_window", "timing_uncertain", "post_event"]


def test_categorize_uncertainty_straddling_boundary_is_uncertain():
    # 2.8 days is inside the event window, but +/-0.5 d crosses its +3 d edge.
    out = categorize(np.array([2.8, 2.0]), np.array([0.5, 0.5]), WINDOWS)
    assert out.tolist() == ["timing_uncertain", "potential_event_window"]


def test_reference_time_date_only_uses_local_noon():
    inc = pd.DataFrame({
        "incident_date": pd.to_datetime(["2026-01-10 00:00", "2026-01-10 15:00"], utc=True),
        "incident_date_local": pd.to_datetime(["2026-01-10", "2026-01-10"]),
        "incident_time_known": [False, True],
    })
    ref, unc = incident_reference_time(inc, "America/Toronto")
    assert ref.iloc[0] == pd.Timestamp("2026-01-10 17:00", tz="UTC")  # noon EST = 17:00 UTC
    assert ref.iloc[1] == pd.Timestamp("2026-01-10 15:00", tz="UTC")
    assert unc.tolist() == [0.5, 0.0]


def _granule(name, collection, maturity, start, counter, produced):
    return {"granule_ur": name + f"_{counter:03d}", "collection": collection, "maturity": maturity,
            "start_time": pd.Timestamp(start, tz="UTC"), "stack_id": "162_A_024", "radar_mode": "4005",
            "product_counter": counter, "production_time": pd.Timestamp(produced, tz="UTC"), "track": 162,
            "direction": "A", "frame": 24, "freq_a_bandwidth_mhz": 40, "freq_a_pols": "HH+HV",
            "geometry": box(-81, 43, -80, 44)}


def test_annotate_supersedes_and_prefers_higher_maturity():
    rows = [
        _granule("G1", "NISAR_L2_GCOV_PROVISIONAL_V1", "provisional", "2026-06-20T10:24:13", 1, "2026-07-01"),
        _granule("G1", "NISAR_L2_GCOV_PROVISIONAL_V1", "provisional", "2026-06-20T10:24:13", 2, "2026-08-01"),
        _granule("G2", "NISAR_L2_GCOV_BETA_V1", "beta", "2026-01-08T10:16:27", 1, "2026-01-20"),
        _granule("G3", "NISAR_L2_GCOV_PROVISIONAL_V1", "provisional", "2026-01-08T10:16:27", 1, "2026-09-01"),
    ]
    gdf = gpd.GeoDataFrame(rows, geometry="geometry", crs="EPSG:4326")
    out = annotate(gdf, Config.load(), incidents=None).set_index("granule_ur")
    assert out.loc["G1_001", "is_superseded"] and not out.loc["G1_001", "is_preferred"]
    assert out.loc["G1_002", "is_preferred"]
    assert not out.loc["G2_001", "is_preferred"] and out.loc["G3_001", "is_preferred"]
    assert out.loc["G3_001", "pass_id"] == "162A_20260108"
    assert out.loc["G3_001", "comparison_group"] == "162A_A40MHz_HH+HV"
