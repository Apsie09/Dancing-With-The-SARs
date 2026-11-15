# Coryell City WSD — bundled vector data

This folder documents the public ArcGIS vectors used by the Coryell site in the TerraGuard
Evidence Explorer. The raw files are **fetched, privacy-trimmed and git-ignored**; the
privacy-safe export consumed by the app lives in `app/data/coryell/`.

```bash
python scripts/fetch_coryell.py        # writes the raw files here
python scripts/build_platform_data.py  # trims personal fields and builds app/data/coryell
```

| File (fetched, git-ignored) | Records | Contents |
|---|---:|---|
| `leak_survey.geojson` | 1,692 | Field leak-repair records, 2019-09-30 to 2026-11-11 (one outlier dropped by the platform) |
| `leak_survey.csv` | 1,692 | CSV view with ISO dates and lon/lat |
| `waterlines.geojson` | 918 | District pipe network: size, material, install year (mostly blank), depth (mostly blank) |
| `pressure_zones.geojson` | 7 | Pressure planes |

## Source and licence

- Publisher: Coryell City Water Supply District, Texas; GIS hosted by its consultant.
- Services: `services9.arcgis.com/AIKMFC1P7gpNycCX/...` (`survey123_…`, `CCWSDWaterline2026/16`,
  `CCWSD_Leak_Density_WFL1/19`).
- **Licence: none stated.** The layers are publicly queryable but not published as open data.
  They are bundled here for the NASA Space Apps hackathon demonstration only. Credit the
  district and its consultant; ask before any use beyond the hackathon or any redistribution.

## Privacy

- `Creator` and `Editor` staff account names are **not** exported into the app.
- Crew notes (`notes`), global IDs and raw free-text water-loss values are removed from the app
  events; the platform keeps only parsed pipe size, parsed loss number, cause, repair type and zone.
- The full `leak_survey.geojson` is the unmodified public export and still contains those fields;
  do not display it directly.

## Known issues

- ObjectId 1611 is a test entry near Galveston, ~340 km from the district; the platform drops it.
- ObjectId 564 has no date; the platform drops it, leaving **1,690 usable repairs**.
- Coordinates are where the crew logged the repair; accuracy is not stated, assume a few to tens
  of metres.
- Pressure-zone names in the leak records do not all appear in the polygon layer (e.g. Jonesboro
  Pancake, Turnersville).
- Repair dates are report dates, not leak-start dates.
