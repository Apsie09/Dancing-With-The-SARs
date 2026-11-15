# Coryell event-signal data audit

Audited 2026-11-15 directly from `../data/coryell/leak_survey.geojson` and cached `data/sar/coryell*/` tables. No new imagery was downloaded. This audit describes label quality and observation coverage; it does not select events by their radar response.

## What the records establish

The raw survey contains 1,692 point records. The existing NISAR cohort contains 303 records after the project's time, geography and cause filters. Its one generic event field is `datetime`; the pipeline interprets this as repair time, but the available field itself does not certify repair start, completion or leak onset. Use **record reference time / presumed repair time** when interpreting this experiment.

There are no structured leak-onset, discovery, detection, independently verified repair-completion, GPS accuracy, burial-depth, or inspected-dry-control fields. `CreationDate` and `EditDate` are database lifecycle timestamps and must not substitute for those event times. `length_of_time_it_took_to_compl` describes completion/work duration, not how long water had leaked.

A scan of free-text duration and notes for leak-duration/discovery language found one older record (ObjectId 2, 2019) saying it leaked for several days. None of the 303 NISAR-cohort records supplied such timing. Inspection of all their unique duration strings and non-null notes found no defensibly confirmed active interval. Thus **zero confirmed-active windows can presently be constructed from these fields**. Any pre-reference window remains a proxy hypothesis, even immediately before the reference time.

| Field | Missing in 1,692 records | Missing in 303-record cohort |
|---|---:|---:|
| datetime | 1 | 0 |
| completion duration | 20 | 4 |
| repair type | 21 | 20 |
| estimated loss text | 7 | 1 |
| line size | 4 | 3 |
| pressure plane | 2 | 1 |
| notes | 1,391 | 243 |
| point geometry | 0 | 0 |

Counts above are null counts; blank/whitespace notes provide no additional evidence. All raw geometries are valid, and none have exactly duplicated coordinates. These checks do **not** establish positional accuracy. No per-record accuracy metadata is available.

The cached parsed flow estimate is present for 302 cohort records, with median 20 gpm, interquartile range 10–50 gpm, range 0–800 gpm. Seventy-nine records have estimated flow >=50 gpm. These are approximate reported rates, not instrument-validated leakage measurements.

## Explicit label-quality exceptions

- **ObjectId 1607:** estimated flow 0, cause `Other`, note explicitly says “Not a leak.” Exclude from a leak-positive experiment before examining SAR outcomes.
- **ObjectId 1658:** note says “Temporarily fixed.” Exclude from the primary pre/post proxy comparison, or separately flag that the post-reference period cannot be assumed repaired.
- Notes for 1505 and 1726 describe shallow conditions, 1746 describes approximately four-foot depth, and 1702 mentions a small green spot. These are isolated observations; selecting them after viewing outcomes would not yield an unbiased cohort.
- Existing `coryell.leaks()` numeric extraction mishandles leading-decimal strings such as `.25` (four historical records: 3, 4, 33, 976). **None is in the current 303-record cohort**, so this bug does not explain the present cohort's results. Future reprocessing should accept leading decimals.

## Cached observation availability

| Cache | Raw NPZ passes | Patch rows | Existing usable rows | Incident IDs with usable rows | Acquisition span |
|---|---:|---:|---:|---:|---|
| discovery `coryell` | 54 | 29,248 | 26,757 | 303 | 2025-11-02 to 2026-10-28 |
| prior confirmation `coryell_confirm` | 24 | 6,385 | 3,216 | 72 | 2026-01-08 to 2026-11-04 |

Discovery rows comprise 7,437 incident and 21,811 control patches across `041D_073_A40MHz_HH+HV` and `062A_017_A40MHz_HH+HV`. Prior confirmation comprises 1,648 incident and 4,737 control patches in `163A_017_A40MHz_HH+HV`. Existing `q_usable` is a patch-quality decision, not a label-quality decision.

As an illustrative coverage count only, requiring at least one usable incident observation in [-12,0) and [30,90] days relative to record reference time gives 177 discovery event IDs and 34 prior-confirmation IDs. These counts precede same-stack pairing, matched-control availability, explicit label exclusions and stricter selection, so they are not experiment sample sizes. They were calculated without inspecting response magnitudes.

## Defensible experiment rules

1. Describe the experiment as a **repair-relative proxy sensitivity analysis**, not a confirmed-active-leak test. Keep previous confirmation results intact; all cached data have already been used in earlier analyses.
2. Exclude explicit non-leaks and uncertain temporary fixes before splitting. Require finite coordinates, reference time and usable same-pass incident/control observations. Log every exclusion with an event ID and reason.
3. Use predeclared spatial scales and time windows. Keep a gap after the reference time to reduce immediate excavation/repair contamination, while acknowledging that a gap cannot certify recovery.
4. Preserve a general eligible cohort and a predeclared >=50 gpm sensitivity cohort. Flow and metadata completeness are outcome-independent quality indicators; neither establishes active duration. Do not choose a threshold because it yields a better SAR result.
5. Compare only within the same viewing/processing group. Match incident and controls on the same pass. Record sample counts after each requirement; many rows from one event are not independent events.
6. Split by event/location before comparing response alternatives. Existing caches cannot provide a genuinely untouched historical holdout; describe any new split as an internal replication and reserve future independent events for confirmation.
7. Obtain verified detection/start intervals, actual repair completion, positional accuracy, and post-repair condition from the utility for a future confirmed-active study. The present records cannot supply these through preprocessing alone.

## Reproduction

The audit used the project environment's Python with pandas/geopandas to inspect GeoJSON field completeness and notes, intersect `ObjectId` with cached `leaks.parquet`, count `q_usable` rows in `coryell_features.parquet`, and enumerate cached NPZ files. No credentials, remote requests, model fitting or outcome-based event selection were needed.
