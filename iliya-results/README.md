# iliya-results — gold and silver leak candidates

Leak records from public utility data, matched to NISAR L-band GCOV scenes taken while each leak was (very likely) leaking, with area soil moisture and rainfall for every scene. Built 15 Nov 2026 for NASA Space Apps 2026, *Dancing with the SARs*.

**Open `gold_silver_map.html` in a browser.** It is self-contained: one tab per source, water lines, towns and urban areas, land cover, and a **Download data** button. Keep the `data/` folder next to the HTML file so the download links work.

## Definitions

- **Gold**: a leak record (any kind of leak, not caused during the work) with a NISAR scene over its location taken between the leak's report/found time and its repair, or within **25 hours** before the repair.
- **Silver**: not gold, but a NISAR scene within **117 hours** (about 5 days) before the repair.
- **Dropped**: leaks whose recorded cause says they were made during work (construction, contractor strike, dig-in, cut). A missing cause is fine.
- **Why 25 h and 117 h**: in the 495 leaks with exact report and repair times (Wellington 417, Tuolumne 78), 80% had already been reported 25 h before the repair and 50% had been reported 117 h before. A gold scene therefore caught an existing leak at least 80% of the time, a silver one at least half the time (both are lower bounds, since leaks start before they are reported). These curves are mostly urban; rural utilities often repair the same day, so the true rural figures are probably a little lower. See `data/unfiltered/window_derivation.csv`.
- **Qualifying scenes**: the scenes that put a leak in its tier (gold: inside the report-to-repair window or within 25 h before repair; silver: within 117 h before repair). A pass that exists as both beta and calibrated files is counted once, using the calibrated file.
- **Scene conditions** (good / fair / poor): area weather at the scene hour from ERA5-Land via the Open-Meteo archive (~10 km grid, so the general area, not the leak spot). Good = under 2 mm of rain in the previous 72 h and soil moisture at or below the 60th percentile; poor = 10+ mm in 72 h, 5+ mm in 24 h, or soil moisture at or above the 85th percentile; fair = in between. Percentiles rank that hour against every hour Aug 2025 to Nov 2026 in the same grid cell. Last rain is reported for any amount and for events of 2 mm or more.
- **Setting**: US = Census incorporated places, census-designated places and 2020 urban areas (rural = outside all of them); NZ = Stats NZ Urban Rural 2023; Calgary = city.
- Calgary and Troy record repair dates only, so their windows are measured back from the start of the repair day.

## Counts

| Source | Gold (rural) | Silver (rural) | Leaks since Oct 2025 checked |
|---|---|---|---|
| Coryell, TX | 69 (69) | 114 (114) | 325 |
| Coweta Co., GA | 52 (34) | 115 (70) | 504 |
| Danville, KY | 44 (14) | 26 (8) | 148 |
| Erie Co., OH | 16 (11) | 33 (22) | 124 |
| Tuolumne, CA | 15 (2) | 13 (1) | 65 |
| Cego-Durango, TX | 11 (11) | 16 (16) | 49 |
| Lake City, FL | 8 (2) | 15 (1) | 40 |
| Laurens Co., SC | 5 (4) | 16 (13) | 72 |
| Elm Creek, TX | 3 (3) | 12 (12) | 25 |
| Jefferson PUD, WA | 1 (1) | 3 (1) | 11 |
| Wellington, NZ | 310 (0) | 65 (0) | 573 |
| Topeka, KS | 49 (2) | 196 (0) | 406 |
| Calgary, AB | 14 (0) | 38 (0) | 132 |
| Troy, OH | 0 (0) | 0 (0) | 12 |

## Files in `data/`

### `data/main_data/`: the labels
| File | What it holds |
|---|---|
| `gold_silver_leaks.csv` | One row per gold or silver leak: tier, why it qualifies, setting, report/repair times, distance to pipe, best NISAR scene and its conditions |
| `gold_silver_rural.csv` | The same, rural leaks only |
| `gold_silver_scenes.csv` | One row per qualifying NISAR scene per leak: ASF download link, hours after report / before repair, calibrated or beta, soil moisture, recent rain, last rain, conditions rating |

### `data/unfiltered/`: everything scored, and how
| File | What it holds |
|---|---|
| `all_scored_leaks.csv` | Every leak since Oct 2025 from every source, with its tier (gold, silver, none, or dropped as caused during work) |
| `window_derivation.csv` | Share of leaks already reported N hours before repair, per dataset (how 25 h and 117 h were chosen) |
| `gold_rules.csv` | The rules as applied |
| `gold_sources.csv` | One row per source: counts, fields used, source layer URLs |

### `data/context_layers/`: background layers
| File | What it holds |
|---|---|
| `gold_area_weather_daily.csv` | Daily rain and soil moisture for every weather grid cell used |
| `gold_water_lines.csv` | Water lines shown on the map, as WKT |

No names, customer numbers, street addresses or free-text notes are included. NISAR scene links point to ASF and need an Earthdata login to download.
