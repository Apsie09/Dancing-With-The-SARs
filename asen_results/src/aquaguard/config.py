"""Pipeline configuration loaded from config/pipeline.toml."""
from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(os.environ.get("PIXI_PROJECT_ROOT", Path(__file__).resolve().parents[2]))
DEFAULT_CONFIG = ROOT / "config" / "pipeline.toml"

# Projected CRS used for all metric operations around Kitchener (WGS84 / UTM 17N, the GCOV grid CRS).
UTM_CRS = "EPSG:32617"
WGS84 = "EPSG:4326"

MATURITY = {
    "NISAR_L2_GCOV_BETA_V1": "beta",
    "NISAR_L2_GCOV_PROVISIONAL_V1": "provisional",
    "NISAR_L2_GCOV_V1": "validated",
}
MATURITY_RANK = {"beta": 0, "provisional": 1, "validated": 2}


@dataclass
class Config:
    raw: dict

    @classmethod
    def load(cls, path: str | Path | None = None) -> "Config":
        with open(path or DEFAULT_CONFIG, "rb") as f:
            return cls(tomllib.load(f))

    def section(self, name: str) -> dict:
        return self.raw[name]

    def path(self, key: str) -> Path:
        p = ROOT / self.raw["paths"][key]
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def incidents_parquet(self) -> Path:
        return self.path("processed_dir") / "kitchener_incidents.parquet"

    @property
    def acquisitions_parquet(self) -> Path:
        return self.path("processed_dir") / "nisar_acquisitions.parquet"

    @property
    def matches_parquet(self) -> Path:
        return self.path("processed_dir") / "incident_nisar_matches.parquet"

    @property
    def coverage_parquet(self) -> Path:
        return self.path("processed_dir") / "incident_coverage_summary.parquet"


def human_size(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024 or unit == "TB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{int(n)} B"
        n /= 1024
    return f"{n:.1f} TB"


def report_file(path: Path) -> str:
    """One-line size report for an output file (the user tracks data volumes closely)."""
    return f"{path.relative_to(ROOT)}  [{human_size(path.stat().st_size)}]"
