# AquaGuard · presentation dashboard

An interactive, animated presentation for the **NASA Space Apps 2026** challenge
*“Dancing with the SARs”*. It tells the story of the Coryell water-leak map and
the NISAR before/after viewer.

Everything in the deck comes from two places:

- [`../viz/`](../viz/) — the interactive map, the NISAR pass browser and the
  before/after chip viewer.
- [`../scripts/`](../scripts/) — the scripts that fetch the district layers,
  cut the NISAR chips and render the district images.

It is plain HTML/CSS/JS plus [MapLibre GL JS](https://maplibre.org/) from a CDN.
No build step, no framework, no install.

## Run it

Browsers block `fetch()` of local files, so serve the **repository root** (not
this folder):

```sh
# from the repository root
python -m http.server 8000
```

Then open <http://localhost:8000/presentation/>.

An internet connection is needed for the fonts, MapLibre and the basemap tiles.
The map and the radar slide read local layers built by the scripts:

```
data/coryell/leak_survey.geojson
data/coryell/waterlines.geojson
data/coryell/nisar/acquisitions_041D073.json
data/coryell/nisar/leak_chips.json
data/coryell/nisar/chips/*.png
```

That folder is git-ignored. If it is missing, the map slide explains how to
rebuild it:

```sh
python scripts/fetch_coryell_data.py --steps vectors,footprints
```

The full NISAR chips need a free Earthdata login; see
[`../viz/README.md`](../viz/README.md) for the commands. The rest of the deck
works without the data.

## Controls

| Input | Action |
|---|---|
| `→` `↓` `Space` `PageDown` | Next slide |
| `←` `↑` `PageUp` | Previous slide |
| Scroll / trackpad | Move between slides (not while over the map or a panel) |
| Swipe left / right | Move between slides on touch |
| `Home` / `End` | First / last slide |
| `F` | Fullscreen |
| `N` | Speaker notes |
| `P` | Autoplay (11 s per slide) |
| `?` | Shortcut reminder |
| `Esc` | Close the notes drawer |

Interactive slides:

- **Live map** — play the 2019–2026 record forward, drag the timeline, recolour
  by pipe size / water loss / cause / year, switch basemaps, hover any repair.
- **24 passes** — toggle the 0–6 / 0–12 day window and natural / all causes,
  click any bar to inspect a pass.
- **Before / after** — drag the divider or press **Blink** to compare the two
  NISAR dates around a real repair.

## The twelve slides

| # | Slide | What it does |
|---|---|---|
| 1 | Cover | The pitch, with an animated radar scope |
| 2 | Seven years, one year | The record versus the NISAR window |
| 3 | Explore. Step. Compare. | The three views in `viz/` |
| 4 | Five scripts | Vectors → footprints → chips → images → map |
| 5 | Six layers | Repairs, pipes, zones, passes, chips, basemaps |
| 6 | Live dashboard | The Coryell repair map and time animation |
| 7 | 24 passes | Repairs after each pass, 0–6 / 0–12 days |
| 8 | Before / after | A real chip comparison with HH/HV stats |
| 9 | Reading the radar | HH, HV, ratio and contrast |
| 10 | What this is not | Limits, privacy and resolution |
| 11 | What comes next | More passes, more districts, field validation |
| 12 | Close | Links to the live map and the viz README |

The **speaker notes** for each slide are stored in the `data-notes` attribute of
the section. They can be edited directly in `index.html` or opened with `N`
while presenting.

## What the deck does not claim

The source material is the map and the radar viewer, not a trained detector.

- The points are **logged repairs**, not confirmed leak detections.
- The NISAR chips are **exploratory**; the district images have approximate
  georeferencing.
- A 10 m chip cannot resolve a metre-scale pipe. A bright pixel is not a leak.
- The NISAR window starts in late 2025, so only 322 of the 1,691 repairs can be
  compared with an L-band pass.
- The right output is a place to look first, with the uncertainty attached.

Privacy is built into the map: staff account names are never read, notes that
name people are withheld, the test record near Galveston is dropped, raw loss
text is never shown, and the meter/parcel layers are not used.

## Files

```
presentation/
├── index.html   # the slides, the map shell and the speaker notes
├── style.css    # design system, transitions and responsive layout
├── app.js       # navigation, reveals, map, pass chart, chip viewer, notes
└── README.md    # this file
```

## Related

- [`../viz/`](../viz/) — the full Coryell map and NISAR before/after viewer.
- [`../viz/README.md`](../viz/README.md) — data sources, layers, privacy rules.
- [`../scripts/`](../scripts/) — data fetching, chip rendering, NISAR extraction.
- [`../data/coryell/README.md`](../data/coryell/README.md) — the district data fields and licence.
