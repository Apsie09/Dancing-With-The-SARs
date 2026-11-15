# NISAR coverage of the Coryell City Water Supply District

Checked 2026-11-14 against the ASF archive. Covers which NISAR L-band products
cover the district's leak repairs (`data/coryell/`), how they group into
comparable stacks, and how close each acquisition falls to a repair.

**Short answer:** the district has good coverage. **Track 41 descending,
frame 73 (`041_D_073`) covers all 322 leaks on all 30 dates** (2025-11-01 to
2026-10-27). Every date is dual-pol HH+HV at 10 m, with a consistent
PROVISIONAL (P05023) run of 24 dates from 2025-12-31 to 2026-10-15. Three
more ascending stacks (`062_A_017`, `062_A_018`, `163_A_017`) each cover part
of the district, which brings most leaks to about 6-day sampling. Half of the
leaks have an acquisition within 0-6 days before the repair on `041_D_073`
alone, and 245 of 322 do on at least one stack.

## 1. Method

- Tool: `asf_search` 14.1.0, Python 3.12, searching anonymously (no login
  needed). Scripts and raw output are in the scratchpad (see section 8).
- Search area: the leak extent (lon -97.888 to -97.429, lat 31.351 to 31.672)
  padded by about 2 km (0.021 deg lon, 0.018 deg lat).
- Leaks: `leak_survey.geojson`, `datetime >= 2025-10-17` UTC, ObjectId 1611
  dropped: **322 leaks**.

Exact search calls:

```python
import asf_search as asf
wkt = "POLYGON((-97.909 31.333,-97.408 31.333,-97.408 31.69,-97.909 31.69,-97.909 31.333))"
base = dict(dataset='NISAR', intersectsWith=wkt,
            start='2025-10-01T00:00:00Z', end='2026-11-14T23:59:59Z', maxResults=5000)
gcov = asf.search(**base, processingLevel='GCOV')   # 166 granules
gslc = asf.search(**base, processingLevel='GSLC')   # 164
gunw = asf.search(**base, processingLevel='GUNW')   # 139
# also tried: RRSD 80, RSLC 175, SME2 160, RIFG 0, RUNW 0, ROFF 0, GOFF 0
```

Equivalent direct API query:
`https://api.daac.asf.alaska.edu/services/search/param?dataset=NISAR&processingLevel=GCOV&intersectsWith=<WKT>&start=2025-10-01T00:00:00Z&end=2026-11-14T23:59:59Z&output=geojson`

How the filters behaved with NISAR:

- `intersectsWith`, `start`, `end`, `processingLevel`, `dataMaturity`
  (`BETA` 36, `PROVISIONAL` 125, `VALIDATED` 5 GCOV granules),
  `relativeOrbit`, `frame` and `flightDirection` **all work**. I checked this
  against a point in Germany (different tracks returned) and a September-only
  window (only September dates returned).
- **Pitfall:** `dataset='NISAR'` **without** `processingLevel` also returns
  `ECMWF_SMST` ancillary weather files. They have no geometry, so
  `intersectsWith` does not filter them out: 4,575 of the first 5,000 results
  were ECMWF files, and the search hit `maxResults`. Always pass
  `processingLevel`.
- The `polarization` property is `null` for NISAR. Use `mainBandPolarization`
  (`['HH','HV']`) or the polarization code in the file name.
- The `frameCoverage` property (`Full` / `Partial`) says whether the
  acquisition filled its standard frame. It does **not** say whether the
  district is covered, so I computed district coverage from the footprints.

Stacks: granules grouped by track, direction and frame. "District coverage"
is the share of the leak bounding box inside the CMR footprint polygon of the
latest full-frame 40 MHz granule, plus a per-date point-in-polygon test for
each leak. Pixel spacing comes from the range bandwidth in the file name and
the GCOV docs (40 MHz gives 10 m, 20 MHz gives 20 m, and frequency B at 5 MHz
gives 80 m).

Matching: for each stack, a leak counts only on dates whose footprint
contains it. "Last before" is the latest acquisition whose timestamp is on or
before the repair timestamp, and "first after" is the next one. **Day
differences are counted in local calendar days (America/Chicago).**
Descending passes (tracks 41, 113) are at about **20:18 local the evening
before** the UTC date in the file name. Ascending passes (tracks 62, 163) are
at about **05:44-05:52 local** on the same day. Example: the `041_D_073`
granule dated 2026-09-09 was acquired at 20:18 on 2026-09-08 local, so a
repair on 2026-09-09 counts as 1 day after it.

## 2. What is in the archive over the district

| Level | Granules | Notes |
|---|---|---|
| **GCOV** | 166 | 6 stacks, all DH (HH+HV), 10 m (20 m on two 20 MHz products). About 7 GB per file. |
| GSLC | 164 | Same 6 stacks and dates, DH. **22-24 GB per file.** Includes one VALIDATED date that has no GCOV yet (`113_D_073` 2026-11-01). |
| GUNW | 139 | **HH only (`4000_SH`, 40 MHz, no side band)**, 80 m. About 2.4 GB. Mostly 12-day pairs, some 24/36/48-day pairs across gaps. |
| RSLC | 175 | L1, radar geometry, 26-28 GB. |
| RRSD | 80 | L0B raw. |
| SME2 | 160 | L3 soil moisture, 200 m, about 0.13 GB. P05023 and X05010 only. Not fully calibrated, but worth a look given the topic. |
| RIFG, RUNW, ROFF, GOFF | 0 | None over this area. |

CRIDs seen: **X05009 and X05010 (BETA)**, **P05023 (PROVISIONAL)** and
**P05036 (VALIDATED)**.

## 3. GCOV stacks

All stacks are DH (HH+HV) with 10 m frequency A. "Leaks in" counts leaks
inside the reference footprint.

| Stack (track_dir_frame) | Pass (local) | Dates | First to last | District coverage | Leaks in | Preferred CRID per date | File size (GB) | Notes |
|---|---|---|---|---|---|---|---|---|
| **041_D_073** | 20:18 desc. | **30** | 2025-11-01 to 2026-10-27 | **100%** (all leaks at least 3.4 km inside the footprint on every date) | **322** | X05009 x5 (Nov 1 - Dec 19, 2025), **P05023 x24** (2025-12-31 to 2026-10-15), P05036 x1 (2026-10-27) | 6.7-7.0 | Most regular. Missing only 2026-08-04 (gap) and 2026-11-08 (not yet processed). |
| **062_A_017** | 05:44 asc. | 29 | 2025-11-02 to 2026-10-28 | 63% (south and east) | 221 | **P05023 x28** (the whole series), P05036 x1 | 6.7-6.9 | Fully backfilled as P05023. Missing 2026-03-02 and 2026-08-05 (gap). |
| 062_A_018 | 05:44 asc. | 15 | 2025-11-02 to 2026-10-28 | 77% (north and west) | 255 | X05009 x2 (partial frames), X05010 x2, P05023 x10 (2026-06-18 onwards), P05036 x1 | 1.97-7.4 | **No data 2026-01-25 to 2026-06-06.** 2026-08-17 has a full 20 MHz (20 m, 2.0 GB) and a partial 40 MHz product. The same pass as 062_A_017, so together they cover 100%. |
| 163_A_017 | 05:52 asc. | 27 | 2025-11-21 to 2026-10-23 | 53% (west) | 135 | X05009 x3 + X05010 x1 (to 2025-12-27), P05023 x22, P05036 x1 (2026-10-23) | 6.9-7.0 | Missing 2026-04-14 and 2026-07-31 (gap). 2026-08-12 is the first acquisition after the gap. |
| 041_D_072 | 20:18 desc. | 17 | 2025-11-01 to 2026-10-27 | 21% (north edge) | 34 | BETA x7 (4 partial frames), P05023 x9, P05036 x1 | 1.98-7.0 | **No data 2026-01-24 to 2026-06-05.** 2026-08-16 has a full 20 MHz product and a partial 40 MHz product. The same pass as 041_D_073. |
| 113_D_073 | 20:10 desc. | 27 | 2025-10-25 to 2026-10-20 | 0.4% | **0** | X05009 x1, P05023 x26 | 6.9-7.2 | Only touches the padded box. **Not useful.** |

Full per-date lists, with every granule name, CRID, footprint and size, are in
`gcov_granules.csv`. Dates per stack (UTC; `B` = BETA, `V` = VALIDATED,
unmarked = P05023):

- **041_D_073:** 2025-11-01B, 11-13B, 11-25B, 12-07B, 12-19B, 12-31,
  2026-01-12, 01-24, 02-05, 02-17, 03-01, 03-13, 03-25, 04-06, 04-18, 04-30,
  05-12, 05-24, 06-05, 06-17, 06-29, 07-11, 07-23, *[gap]*, 08-16, 08-28,
  09-09, 09-21, 10-03, 10-15, 10-27V
- **062_A_017:** 2025-11-02, 11-14, 11-26, 12-08, 12-20, 2026-01-01, 01-13,
  01-25, 02-06, 02-18, 03-14, 03-26, 04-07, 04-19, 05-01, 05-13, 05-25,
  06-06, 06-18, 06-30, 07-12, 07-24, *[gap]*, 08-17, 08-29, 09-10, 09-22,
  10-04, 10-16, 10-28V
- **062_A_018:** 2025-11-02B(partial), 12-20B(partial), 2026-01-01B, 01-13B,
  06-18, 06-30, 07-12, 07-24, *[gap]*, 08-17 (20 MHz), 08-29, 09-10, 09-22,
  10-04, 10-16, 10-28V
- **163_A_017:** 2025-11-21B, 12-03B, 12-15B, 12-27B, 2026-01-08, 01-20,
  02-01, 02-13, 02-25, 03-09, 03-21, 04-02, 04-26, 05-08, 05-20, 06-01,
  06-13, 06-25, 07-07, 07-19, *[gap]*, 08-12, 08-24, 09-05, 09-17, 09-29,
  10-11, 10-23V

Flags:

- **Data gap (2026-07-27 to 2026-08-10):** no GCOV on any stack falls inside
  it. The last dates before it are 07-23, 07-24 and 07-19, and the first
  after are 08-12 (163), 08-16 (41) and 08-17 (62). Leaks from about 08-01 to
  08-15 therefore have 16-22 days since the last acquisition.
- **CRID mixing inside stacks:**
  - `041_D_073`: BETA X05009 for 2025-11-01 to 12-19 was **not** reprocessed.
    2025-12-31 and 2026-01-12 exist as both BETA and P05023 (use P05023).
    2026-10-27 is VALIDATED P05036. A consistent single-CRID run is
    **2025-12-31 to 2026-10-15 (24 dates, P05023)**.
  - `062_A_017`: P05023 throughout. BETA duplicates exist for 4 dates; ignore
    them. 2026-10-28 is P05036.
  - `062_A_018`, `041_D_072`: BETA before the long hole, P05023 after it. In
    practice these are usable only from June 2026.
  - `163_A_017`: BETA to 2025-12-27, P05023 from 2026-01-08.
- **Duplicate versions:** 2026-06-17/18/22/25 have two P05023 granules each
  (counter `_001` produced in July, `_002` produced on 2026-08-10). I used
  `_002`; check which one ASF intends as current.
- **PROVISIONAL backfill, undocumented:** the availability page says
  PROVISIONAL covers acquisitions from 2026-06-17. The archive actually holds
  **P05023 products back to 2025-11-02**, all produced on 2026-08-05 to
  08-10. They exist for full-frame stacks but not for the BETA partial-frame
  dates.

## 4. Matching leaks to acquisitions

Days from the last acquisition before the repair to the repair, in local
days. "None" means no acquisition on that stack before the leak (leaks from
2025-10-17 to 10-31, before the first acquisitions).

| Stack | Leaks in footprint | 0-2 d | 3-6 d | 7-12 d | 13-24 d | >24 d | None | Median |
|---|---|---|---|---|---|---|---|---|
| **041_D_073** | 322 | 61 | 95 | 141 | 11 | 0 | 14 | 6 |
| 062_A_017 | 221 | 51 | 65 | 75 | 16 | 0 | 14 | 6 |
| 062_A_018 | 255 | 31 | 53 | 55 | 14 | 72 | 30 | 9 |
| 163_A_017 | 135 | 33 | 38 | 52 | 5 | 0 | 7 | 6 |
| 041_D_072 | 34 | 3 | 4 | 7 | 7 | 12 | 1 | 19 |
| **Best stack per leak** | 322 | **128** | **117** | 53 | 10 | 0 | 14 | - |

- **245 leaks** have an acquisition 0-6 days before the repair on at least one
  stack (156 on `041_D_073` alone). **100 of them** are on pipes of 4" or
  larger or have an entered loss of at least 50 gpm (table below).
- The 13-24 day cases are almost all early-August leaks hit by the data gap.
- **August-September 2026** (125 leaks, 95 in September). Acquisitions over
  the district:
  - `041_D_073`: Aug 16, Aug 28, Sep 9, Sep 21
  - `062_A_017/018`: Aug 17, Aug 29, Sep 10, Sep 22
  - `163_A_017`: Aug 12, Aug 24, Sep 5, Sep 17, Sep 29

  That is **6 distinct acquisition days in August and 7 in September**,
  about one every 4-5 days, but from three different geometries. On
  `041_D_073` alone, the 95 September leaks are spread fairly evenly from 1 to
  12 days after the last pass.
- **Hot spots** (about 1.5 km cells):

  | Cell centre | Zone | Leaks | Pipes 4" or larger | Covering stacks |
  |---|---|---|---|---|
  | (-97.488, 31.559) | Coryell City | 26 | 0 | 41D73, 62A17, 62A18 |
  | (-97.759, 31.483) | Pancake | 22 | 0 | 41D73, 62A17, 62A18, 163A17 |
  | (-97.571, 31.523) | Coryell City | 13 | 0 | 41D73, 62A17, 62A18 |
  | (-97.53 to -97.55, 31.45 to 31.48) | Riddle | 21 (three cells) | 19 | 41D73, 62A17 |
  | (-97.518, 31.509) | Crawford | 7 | 5 | 41D73, 62A17, 62A18 |

  The Riddle cluster has repeated 10" and 8" main repairs with 100-750 gpm
  losses (for example 1544, 1563, 1668, 1669, 1704, 1753, 1754). It is the
  strongest target, and both `041_D_073` and `062_A_017` cover it.

Full per-leak, per-stack results (last before, the acquisition before that,
first after, CRIDs, granule names) are in `leak_acquisition_matches.csv`.

### Priority leaks with an acquisition 0-6 days before the repair

These are leaks on pipes of 4" or larger, or with an entered loss of at least
50 gpm. For entries such as "15/300gpm" the larger number is used. Dates are
UTC granule dates; day counts are local days.

| OID | Leak (local) | Pipe | Loss (as entered) | Zone | Acquisitions 0-6 days before: stack, UTC date (days) | 41D73 last before / first after (days) |
|---|---|---|---|---|---|---|
| 1509 | 2025-11-03 10:16 | 6" | 20 gallons a minute | Pancake | 62A18 11-02 (1), 41D73 11-01 (3) | 11-01 (3) / 11-13 (9) |
| 1518 | 2025-12-09 09:21 | 6" | 400 | Pancake | 41D73 12-07 (3), 163A17 12-03 (6) | 12-07 (3) / 12-19 (9) |
| 1521 | 2025-12-19 12:16 | 10" | 30gpm | Riddle | 41D73 12-19 (1) | 12-19 (1) / 12-31 (11) |
| 1522 | 2025-12-24 12:16 | 10" | 30 | Riddle | 62A17 12-20 (4), 41D73 12-19 (6) | 12-19 (6) / 12-31 (6) |
| 1523 | 2025-12-30 17:39 | 2" | 100 gallons | Pancake | 163A17 12-27 (3) | 12-19 (12) / 12-31 (0) |
| 1524 | 2025-12-31 23:25 | 6" | 50 gallons a minute | Pancake | 41D73 12-31 (1), 163A17 12-27 (4) | 12-31 (1) / 01-12 (11) |
| 1525 | 2026-01-02 12:51 | 3" | 100 GPM | Pancake | 62A18 01-01 (1), 41D72 12-31 (3), 41D73 12-31 (3), 163A17 12-27 (6) | 12-31 (3) / 01-12 (9) |
| 1526 | 2026-01-04 16:07 | 1.5" | 50gpm | Crawford | 62A17 01-01 (3), 41D73 12-31 (5) | 12-31 (5) / 01-12 (7) |
| 1533 | 2026-01-15 16:18 | 2" | 50 GPM | Pancake | 62A17 01-13 (2), 62A18 01-13 (2), 41D73 01-12 (4) | 01-12 (4) / 01-24 (8) |
| 1537 | 2026-02-02 10:21 | 2" | 50gpm | Pancake | 163A17 02-01 (1) | 01-24 (10) / 02-05 (2) |
| 1544 | 2026-02-10 12:15 | 10" | 200gpm | Riddle | 62A17 02-06 (4), 41D73 02-05 (6) | 02-05 (6) / 02-17 (6) |
| 1548 | 2026-02-17 11:33 | 6" | 20gpm | Pancake | 41D73 02-17 (1), 163A17 02-13 (4) | 02-17 (1) / 03-01 (11) |
| 1551 | 2026-02-18 13:02 | 4" | 50gpm | Crawford | 62A17 02-18 (0), 41D73 02-17 (2) | 02-17 (2) / 03-01 (10) |
| 1556 | 2026-02-22 16:12 | 3" | 750 gpm | Crawford | 62A17 02-18 (4), 41D73 02-17 (6) | 02-17 (6) / 03-01 (6) |
| 1557 | 2026-02-23 11:47 | 10" | 40 | Riddle | 62A17 02-18 (5) | 02-17 (7) / 03-01 (5) |
| 1563 | 2026-03-03 14:57 | 10" | 300 | Riddle | 41D73 03-01 (3) | 03-01 (3) / 03-13 (9) |
| 1567 | 2026-03-06 17:34 | 3" | 50Gpm | Pancake | 41D73 03-01 (6) | 03-01 (6) / 03-13 (6) |
| 1568 | 2026-03-06 19:35 | 2" | 75 Gpm | Crawford | 41D73 03-01 (6) | 03-01 (6) / 03-13 (6) |
| 1569 | 2026-03-13 09:42 | 4" | 40 GPM | Crawford | 41D73 03-13 (1) | 03-13 (1) / 03-25 (11) |
| 1570 | 2026-03-18 16:13 | 10" | 50gpm | Riddle | 62A17 03-14 (4), 41D73 03-13 (6) | 03-13 (6) / 03-25 (6) |
| 1571 | 2026-03-20 10:40 | 8" | 50 GPM | Riddle | 62A17 03-14 (6) | 03-13 (8) / 03-25 (4) |
| 1579 | 2026-04-23 13:04 | 6" | 15/300gpm | Pancake | 41D73 04-18 (6) | 04-18 (6) / 04-30 (6) |
| 1580 | 2026-04-23 14:40 | 4" | 120gpm | Pancake | 41D73 04-18 (6) | 04-18 (6) / 04-30 (6) |
| 1582 | 2026-04-27 15:33 | 6" | 20gpm | Pancake | 163A17 04-26 (1) | 04-18 (10) / 04-30 (2) |
| 1585 | 2026-04-28 09:54 | 4" | 15gpm | Pancake | 163A17 04-26 (2) | 04-18 (11) / 04-30 (1) |
| 1583 | 2026-04-28 13:00 | 1.5" | 50 GPM | Pancake | 163A17 04-26 (2) | 04-18 (11) / 04-30 (1) |
| 1587 | 2026-04-30 15:05 | 2.5" | 100 | Pancake | 41D73 04-30 (1), 163A17 04-26 (4) | 04-30 (1) / 05-12 (11) |
| 1588 | 2026-05-03 20:12 | 10" | 50 | Riddle | 62A17 05-01 (2), 41D73 04-30 (4) | 04-30 (4) / 05-12 (8) |
| 1590 | 2026-05-04 12:34 | 6" | 35gpm | Pancake | 41D73 04-30 (5) | 04-30 (5) / 05-12 (7) |
| 1596 | 2026-05-13 15:40 | 4" | 15gpm | Pancake | 41D73 05-12 (2), 163A17 05-08 (5) | 05-12 (2) / 05-24 (10) |
| 1597 | 2026-05-14 09:26 | 3" | 75 | Crawford | 62A17 05-13 (1), 41D73 05-12 (3) | 05-12 (3) / 05-24 (9) |
| 1598 | 2026-05-14 13:01 | 4" | 15 | Riddle | 62A17 05-13 (1), 41D73 05-12 (3) | 05-12 (3) / 05-24 (9) |
| 1599 | 2026-05-15 11:30 | 2" | 100gpm | Riddle | 62A17 05-13 (2), 41D73 05-12 (4) | 05-12 (4) / 05-24 (8) |
| 1600 | 2026-05-19 11:49 | 4" | 3gpm | Crawford | 62A17 05-13 (6) | 05-12 (8) / 05-24 (4) |
| 1603 | 2026-05-26 13:08 | 10" | 30 gpm | Riddle | 62A17 05-25 (1), 41D73 05-24 (3) | 05-24 (3) / 06-05 (9) |
| 1604 | 2026-05-26 17:09 | 8" | 50 | Riddle | 62A17 05-25 (1), 41D73 05-24 (3) | 05-24 (3) / 06-05 (9) |
| 1605 | 2026-05-26 17:16 | 8" | 40 GPM | Riddle | 62A17 05-25 (1), 41D73 05-24 (3) | 05-24 (3) / 06-05 (9) |
| 1606 | 2026-05-27 08:25 | 4" | 500 | Pancake | 41D73 05-24 (4) | 05-24 (4) / 06-05 (8) |
| 1607 | 2026-05-28 09:03 | 10" | 0 | Riddle | 62A17 05-25 (3), 41D73 05-24 (5) | 05-24 (5) / 06-05 (7) |
| 1614 | 2026-06-06 21:02 | 5" | 50 gpm | Pancake | 41D73 06-05 (2), 163A17 06-01 (5) | 06-05 (2) / 06-17 (10) |
| 1616 | 2026-06-10 08:43 | 2" | 150 | Riddle | 41D73 06-05 (6) | 06-05 (6) / 06-17 (6) |
| 1617 | 2026-06-10 13:45 | 1" | 100gpm | Jonesboro_Pancake | 41D73 06-05 (6) | 06-05 (6) / 06-17 (6) |
| 1618 | 2026-06-11 10:51 | 1.5" | 50gpm | Pancake | 62A17 06-06 (5) | 06-05 (7) / 06-17 (5) |
| 1619 | 2026-06-12 08:48 | 1.5" | 65gpm | Pancake | 62A17 06-06 (6) | 06-05 (8) / 06-17 (4) |
| 1620 | 2026-06-12 09:26 | 1.5" | 50gpm | Pancake | 62A17 06-06 (6) | 06-05 (8) / 06-17 (4) |
| 1623 | 2026-06-17 15:41 | 6" | 5 gpm | Pancake | 41D73 06-17 (1), 163A17 06-13 (4) | 06-17 (1) / 06-29 (11) |
| 1624 | 2026-06-18 15:30 | 6" | 65gpm | Pancake | 62A18 06-18 (0), 41D73 06-17 (2), 163A17 06-13 (5) | 06-17 (2) / 06-29 (10) |
| 1625 | 2026-06-21 15:30 | 6" | 250gpm | Pancake | 62A18 06-18 (3), 41D73 06-17 (5) | 06-17 (5) / 06-29 (7) |
| 1626 | 2026-06-22 15:38 | 5" | 80 | Pancake | 62A18 06-18 (4), 41D73 06-17 (6) | 06-17 (6) / 06-29 (6) |
| 1628 | 2026-06-23 17:10 | 2" | 50 gpm | Pancake | 62A18 06-18 (5) | 06-17 (7) / 06-29 (5) |
| 1635 | 2026-07-18 06:30 | 5" | 400 | Mound | 62A17 07-12 (6) | 07-11 (8) / 07-23 (4) |
| 1641 | 2026-07-30 11:16 | 2.5" | 100 | Pancake | 62A18 07-24 (6) | 07-23 (8) / 08-16 (16) |
| 1650 | 2026-08-12 20:50 | 6" | 40 GPM | Pancake | 163A17 08-12 (0) | 07-23 (21) / 08-16 (3) |
| 1653 | 2026-08-15 21:11 | 10" | 75 gpm | Riddle | 41D73 08-16 (0) | 08-16 (0) / 08-28 (12) |
| 1655 | 2026-08-18 15:54 | 6" | 45gpm | Crawford | 62A17 08-17 (1), 62A18 08-17 (1), 41D73 08-16 (3) | 08-16 (3) / 08-28 (9) |
| 1657 | 2026-08-21 15:50 | - | 800gpm | Riddle | 62A17 08-17 (4), 41D73 08-16 (6) | 08-16 (6) / 08-28 (6) |
| 1658 | 2026-08-23 12:56 | 8" | 5 | Pancake | 62A18 08-17 (6) | 08-16 (8) / 08-28 (4) |
| 1660 | 2026-08-24 11:37 | 4" | 20gpm | Pancake | 163A17 08-24 (0) | 08-16 (9) / 08-28 (3) |
| 1667 | 2026-08-29 22:06 | 6" | 110gpm | Riddle | 62A17 08-29 (0), 41D73 08-28 (2) | 08-28 (2) / 09-09 (10) |
| 1668 | 2026-08-30 00:50 | 10" | 100gpm | Riddle | 62A17 08-29 (1), 41D73 08-28 (3) | 08-28 (3) / 09-09 (9) |
| 1669 | 2026-08-30 18:09 | 10" | 100gpm | Riddle | 62A17 08-29 (1), 41D73 08-28 (3) | 08-28 (3) / 09-09 (9) |
| 1683 | 2026-09-04 18:20 | 1.5" | 50gpm | Pancake | 62A17 08-29 (6), 62A18 08-29 (6) | 08-28 (8) / 09-09 (4) |
| 1685 | 2026-09-07 08:24 | 5" | 300gpm | Mound | 163A17 09-05 (2) | 08-28 (11) / 09-09 (1) |
| 1692 | 2026-09-09 10:00 | 6" | 200 | Riddle | 41D73 09-09 (1) | 09-09 (1) / 09-21 (11) |
| 1693 | 2026-09-09 11:10 | 4" | 75 | Pancake | 41D73 09-09 (1), 163A17 09-05 (4) | 09-09 (1) / 09-21 (11) |
| 1696 | 2026-09-09 15:42 | 4" | 20 | Pancake | 41D72 09-09 (1), 41D73 09-09 (1), 163A17 09-05 (4) | 09-09 (1) / 09-21 (11) |
| 1702 | 2026-09-11 09:40 | 6" | 50gpm | Pancake | 62A18 09-10 (1), 41D73 09-09 (3), 163A17 09-05 (6) | 09-09 (3) / 09-21 (9) |
| 1704 | 2026-09-13 16:33 | 10" | 750 gpm | Riddle | 62A17 09-10 (3), 41D73 09-09 (5) | 09-09 (5) / 09-21 (7) |
| 1713 | 2026-09-15 11:33 | 8" | 25gpm/400gpm | Riddle | 62A17 09-10 (5) | 09-09 (7) / 09-21 (5) |
| 1714 | 2026-09-15 12:41 | 8" | 15gpm | Riddle | 62A17 09-10 (5) | 09-09 (7) / 09-21 (5) |
| 1732 | 2026-09-18 11:43 | 2.5" | 180gpm | Pancake | 163A17 09-17 (1) | 09-09 (10) / 09-21 (2) |
| 1750 | 2026-09-22 13:50 | 3" | 50gpm | Crawford | 62A17 09-22 (0), 62A18 09-22 (0), 41D73 09-21 (2) | 09-21 (2) / 10-03 (10) |
| 1753 | 2026-09-26 13:44 | 10" | 700gpm | Riddle | 62A17 09-22 (4), 41D73 09-21 (6) | 09-21 (6) / 10-03 (6) |
| 1754 | 2026-09-26 23:20 | 8" | 200 | Riddle | 62A17 09-22 (4), 41D73 09-21 (6) | 09-21 (6) / 10-03 (6) |
| 1761 | 2026-09-29 14:26 | 6" | 50 gallons a minute | Pancake | 163A17 09-29 (0) | 09-21 (9) / 10-03 (3) |
| 1762 | 2026-09-29 15:50 | 4" | 15 gpm | Pancake | 163A17 09-29 (0) | 09-21 (9) / 10-03 (3) |
| 1765 | 2026-09-30 15:01 | 4" | 5 gpm | Pancake | 163A17 09-29 (1) | 09-21 (10) / 10-03 (2) |
| 1766 | 2026-09-30 15:38 | 4" | 15 gpm | Pancake | 163A17 09-29 (1) | 09-21 (10) / 10-03 (2) |
| 1768 | 2026-10-03 14:03 | 10" | 150gpm | Pancake | 41D73 10-03 (1), 163A17 09-29 (4) | 10-03 (1) / 10-15 (11) |
| 1769 | 2026-10-04 02:11 | 6" | 50 | Pancake | 41D73 10-03 (2), 163A17 09-29 (5) | 10-03 (2) / 10-15 (10) |
| 1770 | 2026-10-04 02:14 | 3" | 120 | Pancake | 41D73 10-03 (2), 163A17 09-29 (5) | 10-03 (2) / 10-15 (10) |
| 1771 | 2026-10-04 13:17 | 6" | 200 gpm | Riddle | 62A17 10-04 (0), 41D73 10-03 (2) | 10-03 (2) / 10-15 (10) |
| 1772 | 2026-10-04 15:41 | 8" | 200gpm | Pancake | 62A18 10-04 (0), 41D73 10-03 (2), 163A17 09-29 (5) | 10-03 (2) / 10-15 (10) |
| 1775 | 2026-10-07 17:04 | 5" | 15gpm | Pancake | 62A18 10-04 (3), 41D72 10-03 (5), 41D73 10-03 (5) | 10-03 (5) / 10-15 (7) |
| 1778 | 2026-10-08 14:04 | 8" | 50gpm | Riddle | 62A17 10-04 (4), 41D73 10-03 (6) | 10-03 (6) / 10-15 (6) |
| 1779 | 2026-10-09 09:29 | 6" | 150gpm | Pancake | 62A18 10-04 (5) | 10-03 (7) / 10-15 (5) |
| 1780 | 2026-10-09 12:54 | 6" | 600gpm | Pancake | 62A18 10-04 (5) | 10-03 (7) / 10-15 (5) |
| 1782 | 2026-10-09 15:20 | 8" | 75 gpm | Pancake | 62A18 10-04 (5) | 10-03 (7) / 10-15 (5) |
| 1784 | 2026-10-12 11:29 | 8" | 50gpm | Pancake | 163A17 10-11 (1) | 10-03 (10) / 10-15 (2) |
| 1785 | 2026-10-12 13:51 | 8" | 500 | Pancake | 163A17 10-11 (1) | 10-03 (10) / 10-15 (2) |
| 1792 | 2026-10-19 10:11 | 6" | 15gpm | Pancake | 62A18 10-16 (3), 41D73 10-15 (5) | 10-15 (5) / 10-27 (7) |
| 1793 | 2026-10-19 11:06 | 4" | 130gpm | Pancake | 62A18 10-16 (3), 41D73 10-15 (5) | 10-15 (5) / 10-27 (7) |
| 1796 | 2026-10-19 14:53 | 6" | 200gpm | Pancake | 62A18 10-16 (3), 41D73 10-15 (5) | 10-15 (5) / 10-27 (7) |
| 1797 | 2026-10-21 09:29 | 2.5" | 80gpm | Riddle | 62A18 10-16 (5) | 10-15 (7) / 10-27 (5) |
| 1798 | 2026-10-22 09:25 | 6" | 50 escalated too 150 | Pancake | 62A18 10-16 (6) | 10-15 (8) / 10-27 (4) |
| 1799 | 2026-10-22 12:10 | 10" | 30gpm/escalated to 800 | Pancake | 62A18 10-16 (6) | 10-15 (8) / 10-27 (4) |
| 1801 | 2026-10-22 15:14 | 2" | 50gpm | Mound | 62A17 10-16 (6) | 10-15 (8) / 10-27 (4) |
| 1802 | 2026-10-23 10:55 | 8" | 75gpm | Pancake | 163A17 10-23 (0) | 10-15 (9) / 10-27 (3) |
| 1815 | 2026-10-28 14:07 | 2.5" | 100 | Pancake | 62A18 10-28 (0), 41D72 10-27 (2), 41D73 10-27 (2) | 10-27 (2) /  () |
| 1817 | 2026-11-02 12:21 | 10" | 80 | Riddle | 62A17 10-28 (5) | 10-27 (7) /  () |

## 5. Recommendation

1. **Start with `041_D_073` (track 41, descending, frame 73).**
   - It is the only stack covering every leak on every date.
   - It is DH, so HH and HV both come at 10 m.
   - It is the most regular stack: no holes except the instrument gap.
   - It has a single-CRID P05023 run from 2025-12-31 to 2026-10-15
     (24 dates).
   - 156 leaks have a pass 0-6 days before the repair.

   Use it as the reference time series. Drop the five BETA dates (Nov-Dec
   2025), and treat the VALIDATED 2026-10-27 date separately because its CRID
   differs.

   **First dates to pull**, for the August-October peak:
   - 2026-07-23 (pre-gap dry baseline)
   - 2026-08-16, 08-28, 09-09, 09-21, 10-03, 10-15

   That is 7 x about 6.9 GB if downloaded whole. Subset to the district
   instead with the recipe in section 6.
2. **Add `062_A_017` (track 62, ascending, frame 17) second.**
   - It covers the south and east of the district (221 leaks), including the
     Riddle and Crawford big-main clusters.
   - It is P05023 for its entire record (28 dates).
   - It is offset by about 0.4 days from track 41 and has a different look
     direction. Combined with `041_D_073`, it gives about 6-day sampling over
     those clusters and a second independent geometry to confirm a wet
     patch.
   - Same dates: 2026-07-24, 08-17, 08-29, 09-10, 09-22, 10-04, 10-16.
3. **Optional:**
   - `163_A_017` for the western Pancake area (135 leaks, P05023 from
     2026-01-08; dates 08-12, 08-24, 09-05, 09-17, 09-29, 10-11).
   - `062_A_018` for the northern part from June 2026 onward.
   - Skip `041_D_072` (north sliver, holes, partial frames) and `113_D_073`
     (no coverage).
4. **Within a stack, compare only the same track, frame and direction.**
   Don't difference a descending 20:18 scene against an ascending 05:44
   scene: incidence angle, look direction and morning dew all differ.

Download URLs for the recommended dates (`.h5`, Earthdata login needed).
Browse images (`..._LATLON.png` plus `.kml`) are public; replace `.h5` with
`_LATLON.png` and `NISAR/` with `BROWSE/` in the path.

`041_D_073`:

```
https://nisar.asf.earthdatacloud.nasa.gov/NISAR/NISAR_L2_GCOV_PROVISIONAL_V1/NISAR_L2_PR_GCOV_026_041_D_073_4005_DHDH_A_20260723T011828_20260723T011903_P05023_N_F_J_001/NISAR_L2_PR_GCOV_026_041_D_073_4005_DHDH_A_20260723T011828_20260723T011903_P05023_N_F_J_001.h5
https://nisar.asf.earthdatacloud.nasa.gov/NISAR/NISAR_L2_GCOV_PROVISIONAL_V1/NISAR_L2_PR_GCOV_028_041_D_073_4005_DHDH_A_20260816T011827_20260816T011901_P05023_N_F_J_001/NISAR_L2_PR_GCOV_028_041_D_073_4005_DHDH_A_20260816T011827_20260816T011901_P05023_N_F_J_001.h5
https://nisar.asf.earthdatacloud.nasa.gov/NISAR/NISAR_L2_GCOV_PROVISIONAL_V1/NISAR_L2_PR_GCOV_029_041_D_073_4005_DHDH_A_20260828T011827_20260828T011901_P05023_N_F_J_001/NISAR_L2_PR_GCOV_029_041_D_073_4005_DHDH_A_20260828T011827_20260828T011901_P05023_N_F_J_001.h5
https://nisar.asf.earthdatacloud.nasa.gov/NISAR/NISAR_L2_GCOV_PROVISIONAL_V1/NISAR_L2_PR_GCOV_030_041_D_073_4005_DHDH_A_20260909T011826_20260909T011901_P05023_N_F_J_001/NISAR_L2_PR_GCOV_030_041_D_073_4005_DHDH_A_20260909T011826_20260909T011901_P05023_N_F_J_001.h5
https://nisar.asf.earthdatacloud.nasa.gov/NISAR/NISAR_L2_GCOV_PROVISIONAL_V1/NISAR_L2_PR_GCOV_031_041_D_073_4005_DHDH_A_20260921T011826_20260921T011901_P05023_N_F_J_001/NISAR_L2_PR_GCOV_031_041_D_073_4005_DHDH_A_20260921T011826_20260921T011901_P05023_N_F_J_001.h5
https://nisar.asf.earthdatacloud.nasa.gov/NISAR/NISAR_L2_GCOV_PROVISIONAL_V1/NISAR_L2_PR_GCOV_032_041_D_073_4005_DHDH_A_20261003T011827_20261003T011901_P05023_N_F_J_001/NISAR_L2_PR_GCOV_032_041_D_073_4005_DHDH_A_20261003T011827_20261003T011901_P05023_N_F_J_001.h5
https://nisar.asf.earthdatacloud.nasa.gov/NISAR/NISAR_L2_GCOV_PROVISIONAL_V1/NISAR_L2_PR_GCOV_033_041_D_073_4005_DHDH_A_20261015T011827_20261015T011901_P05023_N_F_J_001/NISAR_L2_PR_GCOV_033_041_D_073_4005_DHDH_A_20261015T011827_20261015T011901_P05023_N_F_J_001.h5
```

`062_A_017`:

```
https://nisar.asf.earthdatacloud.nasa.gov/NISAR/NISAR_L2_GCOV_PROVISIONAL_V1/NISAR_L2_PR_GCOV_026_062_A_017_4005_DHDH_A_20260724T114402_20260724T114437_P05023_N_F_J_001/NISAR_L2_PR_GCOV_026_062_A_017_4005_DHDH_A_20260724T114402_20260724T114437_P05023_N_F_J_001.h5
https://nisar.asf.earthdatacloud.nasa.gov/NISAR/NISAR_L2_GCOV_PROVISIONAL_V1/NISAR_L2_PR_GCOV_028_062_A_017_4005_DHDH_A_20260817T114401_20260817T114436_P05023_N_F_J_001/NISAR_L2_PR_GCOV_028_062_A_017_4005_DHDH_A_20260817T114401_20260817T114436_P05023_N_F_J_001.h5
https://nisar.asf.earthdatacloud.nasa.gov/NISAR/NISAR_L2_GCOV_PROVISIONAL_V1/NISAR_L2_PR_GCOV_029_062_A_017_4005_DHDH_A_20260829T114401_20260829T114436_P05023_N_F_J_001/NISAR_L2_PR_GCOV_029_062_A_017_4005_DHDH_A_20260829T114401_20260829T114436_P05023_N_F_J_001.h5
https://nisar.asf.earthdatacloud.nasa.gov/NISAR/NISAR_L2_GCOV_PROVISIONAL_V1/NISAR_L2_PR_GCOV_030_062_A_017_4005_DHDH_A_20260910T114401_20260910T114436_P05023_N_F_J_001/NISAR_L2_PR_GCOV_030_062_A_017_4005_DHDH_A_20260910T114401_20260910T114436_P05023_N_F_J_001.h5
https://nisar.asf.earthdatacloud.nasa.gov/NISAR/NISAR_L2_GCOV_PROVISIONAL_V1/NISAR_L2_PR_GCOV_031_062_A_017_4005_DHDH_A_20260922T114401_20260922T114436_P05023_N_F_J_001/NISAR_L2_PR_GCOV_031_062_A_017_4005_DHDH_A_20260922T114401_20260922T114436_P05023_N_F_J_001.h5
https://nisar.asf.earthdatacloud.nasa.gov/NISAR/NISAR_L2_GCOV_PROVISIONAL_V1/NISAR_L2_PR_GCOV_032_062_A_017_4005_DHDH_A_20261004T114401_20261004T114436_P05023_N_F_J_001/NISAR_L2_PR_GCOV_032_062_A_017_4005_DHDH_A_20261004T114401_20261004T114436_P05023_N_F_J_001.h5
https://nisar.asf.earthdatacloud.nasa.gov/NISAR/NISAR_L2_GCOV_PROVISIONAL_V1/NISAR_L2_PR_GCOV_033_062_A_017_4005_DHDH_A_20261016T114401_20261016T114436_P05023_N_F_J_001/NISAR_L2_PR_GCOV_033_062_A_017_4005_DHDH_A_20261016T114401_20261016T114436_P05023_N_F_J_001.h5
```

Or with `asf_search`, by name:

```python
names = [  # 041_D_073, P05023
  "NISAR_L2_PR_GCOV_030_041_D_073_4005_DHDH_A_20260909T011826_20260909T011901_P05023_N_F_J_001",
  # ...
]
asf.granule_search(names)
```

## 6. Inside the GCOV file (verified 2026-11-15)

Opened remotely: `041_D_073` 2026-09-09,
`NISAR_L2_PR_GCOV_030_041_D_073_4005_DHDH_A_20260909T011826_20260909T011901_P05023_N_F_J_001.h5`
(product version 1.0.11). Only small byte ranges were read; nothing was
downloaded whole. Earthdata login is through `~/.netrc` (present, with a
`urs.earthdata.nasa.gov` entry).

### Structure

| Item | Value |
|---|---|
| Groups | `/science/LSAR/GCOV/grids/frequencyA`, `.../frequencyB`, plus `/science/LSAR/GCOV/metadata/{attitude, calibrationInformation, ceosAnalysisReadyData, orbit, processingInformation, radarGrid, sourceData}` and `/science/LSAR/identification` |
| Covariance terms (A and B) | `listOfCovarianceTerms = [HHHH, HVHV]`, `listOfPolarizations = [HH, HV]`. Diagonal terms only; no off-diagonal terms for DH. |
| Supporting layers | `mask` (uint8), `numberOfLooks` (float32), `rtcGammaToSigmaFactor` (float32), `inputDataExceptionMask` (uint8), `numberOfSubSwaths`, `projection`, `xCoordinates`, `yCoordinates`, `xCoordinateSpacing`, `yCoordinateSpacing` |
| dtype and storage | float32, chunked 512 x 512, gzip |
| frequencyA grid | **34,128 rows x 34,776 cols, 10 m** (`xCoordinateSpacing = 10`, `yCoordinateSpacing = -10`) |
| frequencyB grid | 4,266 x 4,347, 80 m |
| CRS | `projection` = **EPSG:32614** (WGS 84 / UTM 14N), with full WKT in its `spatial_ref` attribute. The district is in the same zone, so there is no zone mismatch. |
| Coordinates | `xCoordinates` / `yCoordinates` are 1-D pixel centres (`pixel_coordinate_convention = center`). x runs from 398,885 to 746,635 m. **y decreases** from 3,566,875 to 3,225,605 m. |
| Fill / nodata | Covariance terms and `numberOfLooks` have `_FillValue = NaN` (the HDF5 dataset fill is 0). In `mask`, **1..n = valid (subswath number), 0 = invalid (partially focused), 255 = outside the acquisition**. |
| **Units** | **Linear power (gamma-0), not dB.** `units = "1"` (dimensionless), `valid_min = 0`. File statistics for HHHH: min 9e-17, mean 0.162, max 33,835; for HVHV: mean 0.034. Convert with `10*log10(x)` for display. Multiply by `rtcGammaToSigmaFactor` to get sigma-0. |

Oddity: `frequencyB/inputDataExceptionMask` has the frequency A shape
(34,128 x 34,776) rather than the 80 m grid. It is harmless, but don't
assume all frequency B layers share one shape.

### Subset recipe (tested)

What worked: `requests` with the `.netrc` follows ASF to Earthdata login and
then to a signed S3/CloudFront URL. `h5py` then reads that URL through
`fsspec` HTTP range requests.

Library versions: Python 3.12.10, h5py 3.16.0 (HDF5 2.0.0), fsspec 2026.9.0,
requests 2.34.2, numpy 2.5.4, pyproj 3.8.0, rasterio 1.5.2 (GDAL 3.12.2). The
full script is `subset_gcov.py` in the scratchpad.

```python
import requests, fsspec, h5py, numpy as np, rasterio
from rasterio.transform import from_origin
from pyproj import Transformer

url = "https://nisar.asf.earthdatacloud.nasa.gov/NISAR/.../<granule>.h5"
W, S, E, N = -97.5706, 31.431, -97.5094, 31.499          # lon/lat box

signed = requests.get(url, headers={"Range": "bytes=0-0"}).url   # auth via ~/.netrc
f = fsspec.filesystem("http").open(signed, block_size=2**20, cache_type="blockcache")
g = h5py.File(f, "r")["/science/LSAR/GCOV/grids/frequencyA"]

epsg = int(g["projection"][()])                           # 32614
x, y = g["xCoordinates"][:], g["yCoordinates"][:]         # pixel centres, y decreasing
tr = Transformer.from_crs(4326, epsg, always_xy=True)
xs, ys = tr.transform([W, E, E, W], [S, S, N, N])
c0, c1 = np.searchsorted(x, min(xs)), np.searchsorted(x, max(xs)) + 1
r0, r1 = np.searchsorted(-y, -max(ys)), np.searchsorted(-y, -min(ys)) + 1

hh = g["HHHH"][r0:r1, c0:c1]; hv = g["HVHV"][r0:r1, c0:c1]  # only the needed chunks are fetched
mask = g["mask"][r0:r1, c0:c1]

transform = from_origin(x[c0] - 5, y[r0] + 5, 10, 10)    # pixel centre -> corner
with rasterio.open("subset.tif", "w", driver="GTiff", height=r1 - r0, width=c1 - c0, count=2,
                   dtype="float32", crs=f"EPSG:{epsg}", transform=transform, nodata=np.nan,
                   compress="deflate") as dst:
    dst.write(hh, 1); dst.write(hv, 2)                    # linear gamma0
```

Test on the Riddle cluster:
- Window: lon -97.5706 to -97.5094, lat 31.431 to 31.499, which is the
  cluster padded by about 1 km.
- Result: 763 x 593 px at 10 m, UTM 635,750-641,680 E and
  3,478,240-3,485,870 N.
- Corner check: the upper-left corner maps back to (-97.5706, 31.4997) and
  the lower-right to (-97.5093, 31.4302), so the subset lands where it
  should.
- Speed: about 46 s in total. Earthdata authentication took about 8 s, and
  opening the file and reading coordinates took about 7 s.
- Data transferred: about **30 MB** (29 blocks of 1 MiB fetched, out of a
  6.95 GB file).
- Output: `gcov_041D073_20260909_riddle.tif` (4.4 MB; bands HHHH, HVHV,
  numberOfLooks) and `..._mask.tif`, in the scratchpad `nisar_coryell/`.

Sanity check of the values:
- All pixels have `mask = 1`.
- HH median **-15.0 dB** (2nd-98th percentile: -20.7 to -4.5 dB).
- HV median **-21.8 dB** (-26.3 to -12.8 dB).
- Looks median 5.0.

These are typical L-band gamma-0 values for dry pasture and scrub, which
again confirms linear storage. Single-pixel values at leak points range from
-21 to +11 dB. That is speckle and point targets, so average over windows
(for example 5 x 5 pixels or more) before comparing dates.

GDAL alternative: GDAL 3.12.2 with `/vsicurl/` also authenticates and reads
data. It needs `GDAL_HTTP_NETRC=YES`, `GDAL_HTTP_COOKIEFILE` and
`GDAL_HTTP_COOKIEJAR` pointing to a scratch file, and
`GDAL_DISABLE_READDIR_ON_OPEN=EMPTY_DIR`. The path form that worked is
`HDF5:"/vsicurl/<url>"://science/LSAR/GCOV/grids/frequencyA/HHHH`.
However, before GDAL 3.13 the HDF5 driver returns **no georeferencing**, so
you would have to build the transform from `xCoordinates` / `yCoordinates`
yourself. Use h5py, or GDAL 3.13 or newer.

The browse PNG and KML files are served without login; `.h5` and
`.iso.xml` need it.

## 7. Open issues

- **Subset rather than download.** The district (45 x 35 km) is about 3% of
  a frame, and full files are about 7 GB (GCOV) or 22 GB (GSLC). A 14-file
  download of the recommended set would be about 96 GB. The h5py recipe in
  section 6 reads a 6 x 8 km window for about 30 MB. The whole district
  (about 4,700 x 3,600 px) should be roughly 0.5-1 GB per date; that is an
  estimate, not tested.
- **Signed URLs expire** (they are short-lived S3/CloudFront links). Request
  a new one for each session or batch.
- **Footprints are CMR 4-corner approximations.** Check the `mask` layer for
  real valid-data edges, especially where the 062_A_017 / 062_A_018 and
  041_D_072 / 041_D_073 frame boundaries cross the district. All leaks are at
  least 3.4 km inside the `041_D_073` polygons.
- **Reprocessing in 2027** will supersede everything acquired before
  2026-10-21. Record CRIDs alongside any result.
- **The CRID switch at 2026-10-21** (P05023 to P05036) falls inside the
  October leak cluster. Treat the 10-23, 10-27 and 10-28 dates as a different
  version.
- **Duplicate `_001` / `_002` P05023 granules** for 2026-06-17 to 06-25: it
  is unclear which one ASF considers current.
- **Filename flags** after the CRID (for example `N_F_J`, `F_F_J`): the
  middle letter matches full or partial frame. The meaning of the first and
  last letters is not documented here, and `J` appears even where CMR says
  `JOINT_OBSERVATION=False`.
- **Leak start is unknown.** Repairs are logged when fixed, so a 0-day
  acquisition may already show the leak, but a leak that ran for weeks may
  also show on earlier dates. Use the "acquisition before that" column in the
  CSV for a pre-leak baseline.
- **Ascending passes are at about 05:45 local** (possible dew), and
  descending passes at 20:18 local. Keep geometries separate.
- **SME2 soil moisture** (200 m) exists for the same stacks and is tiny. It
  is too coarse for single leaks but could give context on regional wetness,
  for example rain events that would confound a leak signal.

## 8. Files

- `data/coryell/nisar_gcov_footprints.geojson`: one polygon per GCOV stack
  (6 features) with track, direction, frame, date list, CRID per date, share
  of the district covered and leaks inside. Polygon = CMR footprint of the
  latest full-frame 40 MHz granule.
- Scratchpad (temporary):
  `C:/Users/PETAR~1.BUY/AppData/Local/Temp/claude/c67b889a1737c5e6/62abc516-66fe-4838-84c8-33f7a7b05962/scratchpad/nisar_coryell/`
  - `asf_search_GCOV.geojson`, `asf_search_GSLC.geojson`,
    `asf_search_GUNW.geojson`, `asf_search_RSLC.geojson`,
    `asf_search_RRSD.geojson`, `asf_search_SME2.geojson`: raw search results
    with footprints
  - `gcov_granules.csv`: every GCOV granule with stack, CRID, maturity,
    bandwidth, spacing, size, share of the district covered, leaks inside,
    URL and footprint WKT
  - `leak_acquisition_matches.csv`: one row per leak and stack
  - `analysis.json`: stack summaries and the 0-6 day matches
  - `gcov_041D073_20260909_riddle.tif` (+ `_mask.tif`): the tested subset
    of the Riddle cluster (linear gamma-0, EPSG:32614, 10 m)
  - Scripts are one level up (`search1.py`, `search2.py`, `analyze.py`,
    `extra.py`, `inspect_gcov.py`, `subset_gcov.py`).
