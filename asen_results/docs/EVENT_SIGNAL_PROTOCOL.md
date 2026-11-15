# Coryell event-relative multiscale diagnostic protocol

Frozen before extracting or inspecting this experiment's SAR summaries, 2026-11-15.
This is a new diagnostic on previously explored data, **not preregistered independent confirmation**.

## Question and interpretation
Does local SAR intensity relative to same-pass control sites decrease after the recorded repair?
Unknown leak onset and uncertain repair-date semantics mean the pre-period is a proxy, not verified
active leakage. A decrease can also reflect excavation, vegetation or other repair-associated changes.

## Fixed analysis
- Offline existing `data/sar/coryell{,_confirm}` raw linear gamma0 patches and metadata only.
- Non-beta acquisitions; exclude construction/maintenance-induced events; no outcome-based event selection.
- Primary: HH disk radius 30 m minus 100–300 m background annulus, each computed as
  `10 log10(mean(valid positive linear gamma0))`. Secondary: radii 10/60 m and HV.
- Existing 64x64 patches have documented 10 m spacing and center index 32 (the extraction's rounded
  site coordinate). This is spacing, not a claim about independent physical resolution. No Lee filter.
- Existing validity mask encodes 0 < mask < 255, exception == 0 and positive finite HH;
  additionally require positive finite values for the measured polarization. Whole-patch valid >=90%,
  disk and annulus valid >=80%. No missing observation is counted as zero.
- Each pass: incident contrast minus mean of >=2 valid matched controls, within the same stack/pass.
- Primary windows: strictly pre-repair [-30,0) days and post [30,90] days, >=2 usable passes each
  per event/stack. Supplementary coverage sensitivity: >=1 each, labelled separately.
- Compute pre minus post within each event/stack, then equal-weight available stacks within event.
  Thus an event contributes once, regardless of number of passes or stacks.
- Placebo: choose the lexicographically first control site per event before reading signal values;
  compare it to the mean of remaining controls on identical incident-eligible passes. Require at least
  one remaining control. Do not average all leave-one-out pseudo-sites (which cancels algebraically).
- Deterministic 70/30 internal development/validation split by SHA256 of event ID modulo 10 (<3 is
  validation). No scale/window selection from either split. Data were explored before this experiment,
  and geographically nearby events/shared scenes can remain correlated across splits.
- Report all fixed scales, per-stack effects, event counts, 95% event-bootstrap mean-effect intervals
  (2,000 draws, seed 20261115), and large-event >=50 gpm secondary subgroup. Intervals are conditional
  on the observed sites/passes; shared scene/spatial dependence may make them optimistic.
- Primary assessment uses internal validation, HH 30 m, >=2 passes. Report estimates and uncertainty,
  not a classifier accuracy claim. Supplementary comparisons are descriptive, not independent tests.
- Plot all fixed repair-relative 15-day bins, event-averaged within bins, with no outcome-selected examples.

## Reproducibility
Run from `asen_results`: `PYTHONPATH=src .pixi/envs/default/bin/python -m aquaguard.event_signal`.
Outputs are new `data/reports/event_signal*` artifacts; original caches/reports are untouched.
