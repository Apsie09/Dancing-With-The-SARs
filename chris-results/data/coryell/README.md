# Coryell City WSD — bundled vector data

This folder documents the public ArcGIS source vectors for the Coryell case in the AquaGuard
Evidence Explorer. The raw files are **fetched and git-ignored**. `prepare_coryell.py` subsets
them into a fixed 10 × 10 km case, which the shared pipeline then processes like the other cases.

```bash
python scripts/fetch_coryell.py         # writes the raw files here
python case_studies/prepare_coryell.py  # 10 x 10 km case + 72 summer labels
CASE=case_studies/coryell/case.json
AQUAGUARD_CASE=$CASE python -m pipeline.acquire --workers 16
AQUAGUARD_CASE=$CASE python -m pipeline.model
AQUAGUARD_CASE=$CASE python -m pipeline.make_map
python scripts/build_platform_data.py   # exports app/data/coryell
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
- Crew notes (`notes`), global IDs and raw free-text water-loss values are removed from the case
  labels and the app events; the app keeps only ID, date, cause, pipe size and coordinates.
- The full `leak_survey.geojson` is the unmodified public export and still contains those fields;
  do not display it directly.

## Known issues

- ObjectId 1611 is a test entry near Galveston, ~340 km from the district; the case drops it.
- ObjectId 564 has no date; the case drops it.
- The district export has 1,690 usable repairs; the case uses the **72 summer repairs inside the
  10 × 10 km AOI** (June–September 2025–2026).
- Coordinates are where the crew logged the repair; accuracy is not stated, assume a few to tens
  of metres.
- The case AOI is UTM 14N x = 634,555–644,555 m, y = 3,479,328–3,489,328 m
  (lon −97.584…−97.477, lat 31.441…31.530).
- Pressure-zone names in the leak records do not all appear in the polygon layer (e.g. Jonesboro
  Pancake, Turnersville).
- Repair dates are report dates, not leak-start dates.
