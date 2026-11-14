"""CLI: python -m terraguard {incidents,catalog,match,report,all} [--config PATH]"""
import argparse
import time

from . import catalog, controls, nisar_aux, risk, segments, dataset, features, incidents, mains, matching, probe, report, sar, signal_check
from .config import Config

STAGES = {"incidents": incidents.run, "catalog": catalog.run, "match": matching.run, "report": report.run}


def main() -> None:
    p = argparse.ArgumentParser(prog="terraguard")
    p.add_argument("stage", choices=[*STAGES, "all", "probe", "sar", "patches", "features", "signal", "mains", "controls", "dataset", "signal-controls", "aux", "segments", "risk"])
    p.add_argument("--incidents", type=int, default=None, help="sar: number of top incidents (default from config)")
    p.add_argument("--all", action="store_true", help="sar: stream every granule with a usable match")
    p.add_argument("--workers", type=int, default=None, help="sar: parallel streaming processes")
    p.add_argument("--dry-run", action="store_true", help="sar: print the plan and sizes, stream nothing")
    p.add_argument("--granule", default=None, help="probe: granule_ur to test (default: first validated one)")
    p.add_argument("--block-size-mb", type=float, default=1.0, help="probe: HTTP range block size")
    p.add_argument("--config", default=None, help="path to pipeline.toml (default: config/pipeline.toml)")
    a = p.parse_args()
    cfg = Config.load(a.config)
    if a.stage == "sar":
        sar.run(cfg, a.incidents, a.all, a.workers, a.dry_run)
        return
    if a.stage == "patches":
        idx = sar.extract_patches(cfg)
        print(f"{len(idx)} patches written")
        return
    if a.stage == "risk":
        risk.run(cfg)
        return
    if a.stage == "segments":
        segments.run(cfg)
        return
    if a.stage == "aux":
        nisar_aux.run(cfg, a.workers or 6, a.dry_run)
        return
    if a.stage == "signal-controls":
        auc, did_tab = signal_check.control_check(cfg)
        print(auc.round(3).to_string(index=False)); print(); print(did_tab.round(3).to_string(index=False))
        return
    if a.stage == "controls":
        from rich.progress import BarColumn, MofNCompleteColumn, Progress, TextColumn, TimeElapsedColumn, TimeRemainingColumn
        with Progress(TextColumn("[bold]{task.description}"), BarColumn(), MofNCompleteColumn(),
                      TimeElapsedColumn(), TimeRemainingColumn()) as prog:
            controls.run(cfg, prog)
        return
    if a.stage == "dataset":
        dataset.run(cfg)
        return
    if a.stage == "mains":
        mains.run(cfg)
        return
    if a.stage == "signal":
        res = signal_check.run(cfg)
        import pandas as pd
        with pd.option_context("display.width", 200, "display.max_rows", 200):
            print(res.round(3).to_string(index=False))
        return
    if a.stage == "features":
        features.run(cfg)
        return
    if a.stage == "probe":
        probe.run(cfg, a.granule, int(a.block_size_mb * (1 << 20)))
        return
    for name in (STAGES if a.stage == "all" else [a.stage]):
        t = time.time()
        STAGES[name](cfg)
        print(f"  [{name} done in {time.time() - t:.1f}s]\n")


if __name__ == "__main__":
    main()
