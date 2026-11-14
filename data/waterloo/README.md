# City of Waterloo (Ontario) watermain breaks

- **Dataset:** Watermain Breaks (point layer)
- **Publisher:** City of Waterloo, Ontario, Canada (City of Waterloo Open Data)
- **Landing page:** https://data.waterloo.ca/datasets/City-of-Waterloo::watermain-breaks
- **Feature service:** https://services.arcgis.com/ZpeBVw5o1kjit7LT/arcgis/rest/services/Watermain_Breaks/FeatureServer/0
- **Licence:** Waterloo Open Data User Licence (adapted from the UK Open Government Licence), https://data.waterloo.ca/pages/open-data-licence.
  Attribution is optional. If you give credit, use the licence's wording:
  *"Contains information provided by the City of Waterloo under licence."*
  The data is provided "as is" with no warranty.
- **Update frequency:** the portal does not state one. The service's data was last edited on 2026-10-31.
- **Downloaded:** 2026-11-14 (portal CSV and GeoJSON exports)
- **Records:** 1,197 breaks, dated 2000-01-06 to 2026-09-20. 35 of them are dated on or after 2025-10-17, the start of NISAR data.
  Every record has coordinates.

## Files

- `watermain_breaks.csv`: UTF-8 with a BOM. The `Break Date` values look like `7/24/2008 12:00:00 AM` (day precision only).
- `watermain_breaks.geojson`: EPSG:4326 points.

## Fields

`OBJECTID` (ID), `BREAK_DATE` / `Break Date` (date of the break), `BREAK_YEAR` (year as text),
`PIPE_RPLCD` / `Pipe Was Subsequently Replaced` (Yes/No), `LATITUDE`, `LONGITUDE` (WGS84). The CSV also has
`x` and `y`, which repeat the longitude and latitude.

## Known quirks

- OBJECTIDs 763 and 765 are exact duplicates (same date and location).
- OBJECTIDs 321 and 394 share the same location, one day apart.
