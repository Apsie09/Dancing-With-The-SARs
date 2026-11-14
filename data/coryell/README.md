# Coryell City Water Supply District leak repairs

Field records of water leak repairs made by the **Coryell City Water Supply
District** (CCWSD), a rural water utility in central Texas around Gatesville,
Coryell County (with some service in McLennan County). Each record is one
repair, logged on site by a crew using an ArcGIS Survey123 form, with a GPS
point.

This is our main ground-truth candidate for leaks **outside city limits**: a
rural network in open pasture, scrub and farmland, with exact coordinates and
records inside the NISAR data window.

## Source

| | |
|---|---|
| Publisher | Coryell City Water Supply District; GIS hosted by its consultant (ArcGIS Online accounts `kyler.allen_OEI_GIS`, `calli.chartrand_oei_gis`) |
| Layer | "Coryell City Leak Survey", Survey123 feature layer |
| Service URL | <https://services9.arcgis.com/AIKMFC1P7gpNycCX/arcgis/rest/services/survey123_7d36ae6d371c488ba8699e7c34bb1588/FeatureServer/0> |
| Also published | "Coryell City Water Supply District Leaks Dashboard" (ArcGIS Online), and year-to-date snapshot layers such as `Jan_Dec2025` and `Jan_Sept2026_Leaks` that duplicate this layer |
| Licence | **None stated.** Publicly queryable, but not published as open data. Credit the district and its consultant; ask them before any use beyond the hackathon. |
| Downloaded | 2026-11-14, full layer (all 1,692 records), unmodified |

## Files

| File | Contents |
|---|---|
| `leak_survey.geojson` | Raw export from the service (`outSR=4326`, `f=geojson`). Dates are epoch milliseconds, UTC. |
| `leak_survey.csv` | Same records, dates converted to ISO 8601 UTC, plus `longitude` / `latitude` (WGS 84) columns. |
| `waterlines.geojson` | District pipe network, 918 polylines (WGS 84): `Size` (text, e.g. `1.5"`), `Diameter` (inches, blank on 32 lines), `Material`, `Class`, `Depth`, `Year`, `LengthMile`, `MapSource` (remarks). From `CCWSDWaterline2026` layer 16 "Waterline" (last edited 2026-09-10; the most recent and most complete of the three copies on the host, vs 916 lines in `CCWSD_Waterlines_May_2026` and 886 in `CCWSD_Leak_Density_WFL1` layer 16). Downloaded 2026-11-14. The `Notes` field was **dropped** because its only two non-blank values held staff e-mail addresses and a person's name; everything else is unmodified. Class, depth and year are blank on about 99% of lines; material is PVC on 95%. |
| `pressure_zones.geojson` | The 7 pressure zones ("planes") as polygons: `Name`, `SquareMiles`. From `CCWSD_Leak_Density_WFL1` layer 19 "Coryell Pressure Planes", unmodified, downloaded 2026-11-14. Leak records also name zones not drawn here (Jonesboro Pancake, Turnersville). |

Pipes: `https://services9.arcgis.com/AIKMFC1P7gpNycCX/arcgis/rest/services/CCWSDWaterline2026/FeatureServer/16/query?where=1=1&outFields=*&outSR=4326&f=geojson`;
zones: same host, `CCWSD_Leak_Density_WFL1/FeatureServer/19/query?...` (both fit in one page). Same licence
situation as the leak layer. The map in [`viz/`](../../viz/) shows these layers.

To refresh, re-query the service (paginate with `resultOffset`, 1000 records
per page):

```
<service URL>/query?where=1=1&outFields=*&outSR=4326&f=geojson&resultOffset=0&resultRecordCount=1000
```

## Fields

| Field | Meaning |
|---|---|
| `ObjectId`, `globalid` | Record IDs |
| `datetime` | When the repair was logged on site (UTC). **Use this as the leak date.** |
| `CreationDate`, `EditDate` | When the record was created and last edited (UTC). `CreationDate` is usually within minutes of `datetime`. |
| `Creator`, `Editor` | ArcGIS account names of the field crew or GIS staff |
| `line_size` | Pipe diameter as text, e.g. `1.5"`, `6"`, `10"` |
| `type_of_repair` | `line_`, `fitting_`, `valve`, or combinations |
| `approximate_water_loss_gpm` | Estimated loss in US gallons per minute, **free text** (`5gpm`, `5 gpm`, `10`, `Unsure`); parse the number |
| `what_pressure_plane_did_the_lea` | District pressure zone (named after the communities served: Pancake, Coryell City, Riddle, Crawford, Mound, Levita, Jonesboro) |
| `cause_of_leak` | `Naturally_Occurred`, `Construction_Maintenance_Induce`, `Other` |
| `length_of_time_it_took_to_compl` | Repair time, free text. Some entries also say how long it leaked (e.g. "Leaked for several days"). |
| `notes` | Crew notes, free text. Some are very useful for validation (e.g. "Been leaking a while. Whole field flooded.", "Middle of nowhere. Good percentage of our water loss."). |

## What is in it (checked 2026-11-14)

- **1,692 records**, 2019-09-30 to **2026-11-11**. Crews enter leaks the same
  day, so the layer is live.
- **Every record has a point.** One record has no `datetime` (ObjectId 564).
- Records per year: 2019: 86, 2020: 168, 2021: 223, 2022: 299, 2023: 235,
  2024: 211, 2025: 173, 2026: 296.
- **NISAR window (on or after 2025-10-17): 323 records**, 2025-10-17 to
  2026-11-11. One is the outlier below, so **322 usable**.
  - Monthly: 2025-10: 14, 11: 6, 12: 7, 2026-01: 13, 02: 24, 03: 13,
    04: 14, 05: 19, 06: 21, 07: 14, 08: 30, **09: 95**, 10: 48, 11 (to the
    11th): 5. The September spike is real field entries (each logged within
    0-4 days), not a bulk upload.
  - Pipe sizes: mostly small (1.5" 95, 1" 47, 3" 35, 2" 30). **87 are on
    4" or larger** (6" 26, 10" 26, 4" 20, 8" 15).
  - Water loss mostly 5-50 gpm. Repairs take 15 minutes to 3 hours; how long
    each leak ran before it was found is usually unknown.
  - Cause: 300 "Naturally_Occurred", 19 construction or maintenance, 4 other.
- Extent of the usable window records: longitude -97.888 to -97.429,
  latitude 31.351 to 31.672 (about 45 x 35 km).

## Known issues

- **Outlier:** ObjectId 1611 (2026-06-02) is near Galveston (29.506, -94.991),
  about 340 km from the district, with every attribute blank. Probably a test
  entry; drop it.
- **Free-text fields** (`approximate_water_loss_gpm`,
  `length_of_time_it_took_to_compl`, `notes`) need parsing; spellings and
  units vary.
- **Personal data:** the data is unmodified. `Creator` / `Editor` hold staff
  account names, and a few `notes` name crew members or residents. **Don't
  show these columns on screen or in the demo.**
- Coordinates are where the crew stood when submitting the form, presumably
  at the repair. Accuracy is not stated; assume a few metres to tens of metres.

## Using it with NISAR

- Filter on `datetime >= 2025-10-17` and drop ObjectId 1611.
- The district is in **UTM zone 14N (EPSG:32614)**; NISAR GCOV grids are in
  UTM, so check the zone of each GCOV frame and reproject the points to match.
- Prefer leaks on **4" or larger** pipes, with **higher water loss**, or with
  notes saying they ran for a long time: those are the most likely to leave a
  wet patch visible at 10-20 m pixel spacing.
- NISAR revisits every 12 days and most leaks are fixed within hours of being
  found, so for each leak look for the last acquisition **before** the repair
  date (the leak may already have been running) and compare with earlier
  dates on the same track and frame.
- August-September 2026 is hot and dry in central Texas: the best season for a
  soil moisture signal, and the month with the most leaks.

```python
import geopandas as gpd

leaks = gpd.read_file("data/coryell/leak_survey.geojson")
leaks["datetime"] = gpd.pd.to_datetime(leaks["datetime"], unit="ms", utc=True)
leaks = leaks[(leaks["datetime"] >= "2025-10-17") & (leaks["ObjectId"] != 1611)]
leaks = leaks.to_crs(32614)
```

## Related layers (not downloaded)

The same consultant account publishes the district's **pipe network** as
lines, with size, material, class, depth and install year, which is useful as
a corridor mask for anomaly detection. For example:

- `CCWSD_Leak_Density_WFL1`, layer 16 "Water Lines" (886 lines):
  <https://services9.arcgis.com/AIKMFC1P7gpNycCX/arcgis/rest/services/CCWSD_Leak_Density_WFL1/FeatureServer/16>
- Newer snapshots: `CCWSDWaterline2026`, `CCWSD_Waterlines_May_2026`
  (same host, `/arcgis/rest/services/<name>/FeatureServer`).

The `CCWSD_Leak_Density_WFL1` service also contains meter and parcel layers
with customer and owner names; we don't need those.
