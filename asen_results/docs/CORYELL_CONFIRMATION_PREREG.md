# Coryell confirmation test: pre-registration

_Written 2026-11-15 10:38 EET, **before** any data from the confirmation stack was downloaded.
The rules below must not be changed after the confirmation data exists._

## Why this test exists
On the discovery stacks (041D_073, 062A_017), an exploratory analysis found that leak sites look brighter in HH than
their matched controls while leaking, and lose that after the repair. The result was +0.25 dB [+0.11, +0.40], p = 0.0003,
n = 201 leaks. The placebo on control sites was +0.00 dB, p = 0.51.

The before/after windows were chosen **after** seeing a time-course plot, so that p-value is optimistic. This test checks
whether the same effect appears on data the analysis has never seen.

## Confirmation data
- NISAR L2 GCOV, stack **163A_017** (ascending, track 163, frame 017). It is full-frame, 40 MHz, HH+HV, non-beta, all passes.
  This stack was not used in discovery.
- Leaks: Coryell City WSD repair records in the NISAR window (on or after 2025-10-17), all causes except
  `Construction_Maintenance_Induce`, inside the district bounding box, with at least one pass of this stack within ±120 days.
- Controls: the same rule as in discovery. There are 3 per leak, on district pipes, 400-1500 m from the leak, with no other
  leak within 300 m / ±365 days, all on the same passes.
- Processing is identical to discovery (`pixi run coryell`, `--analyse`): 64 px patches and a Lee filter (ENL 4.5) on linear γ⁰.
  The valid mask uses `mask` and `inputDataExceptionMask == 0`. Usability needs ≥ 90% valid pixels and ≥ 80% valid in the centre disk.

## Primary metric (fixed)
- Feature: `sd_hh_contrast` = mean HH dB in the site disk (radius 3 px) minus the mean in the background ring (10-30 px).
- For each leak and pass: the leak's value minus the mean of that leak's controls on the same pass.
- For each leak: the mean of that difference over passes with Δt in **[-60, +14] days** (leaking), minus the mean over
  passes with Δt in **[+30, +120] days** (after). Δt = acquisition time - repair time. Leaks without passes in both windows are dropped.
- Statistic: the mean of that per-leak "drop" and a **one-sided Wilcoxon signed-rank test (drop > 0)**.

## Decision rule (fixed)
**CONFIRMED** only if all three hold:
1. The primary one-sided p < 0.05.
2. The mean drop is > 0.
3. The placebo is not significant: the same metric for each control vs. the other controls of its leak, two-sided p ≥ 0.05.

Otherwise: **NOT CONFIRMED**.

## Secondary (reported, not part of the decision)
- The same metric for HV (`sd_hv_contrast`).
- HH restricted to leaks ≥ 50 gpm.
- HH restricted to leaks that did not appear in the discovery analysis (fully independent leaks).

Note: many leaks appear in both discovery and confirmation. The confirmation observations are still new, because they come
from different satellite passes, dates and viewing geometry. The "not in discovery set" secondary test is the strictest version.

## How to run
```bash
pixi run coryell --confirm --dry-run        # plan + size
pixi run coryell --confirm --workers 6      # stream stack 163A_017 windows
pixi run coryell --confirm --analyse        # patches, features, then the pre-registered test
```
The result is written to `data/reports/coryell_confirmation.md`.
