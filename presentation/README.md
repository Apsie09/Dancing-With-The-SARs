# AquaGuard · presentation dashboard

An interactive, animated presentation for the **NASA Space Apps 2026** challenge
*“Dancing with the SARs”*. It tells the AquaGuard story — radar screening for
buried water networks — as a 12-slide dashboard, and includes a live map of the
Coryell City WSD repair record built with the same data and visual language as
[`../viz/`](../viz/).

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
The map itself reads the same local layers as `viz/`:

```
data/coryell/leak_survey.geojson
data/coryell/waterlines.geojson
```

That folder is git-ignored. If it is missing, the map slide explains how to
rebuild it:

```sh
python scripts/fetch_coryell_data.py --steps vectors,footprints
```

The rest of the deck works without the data.

## Controls

| Input | Action |
|---|---|
| `→` `↓` `Space` `PageDown` | Next slide |
| `←` `↑` `PageUp` | Previous slide |
| Scroll / trackpad | Move between slides (not while over the map or its panel) |
| Swipe left / right | Move between slides on touch |
| `Home` / `End` | First / last slide |
| `F` | Fullscreen |
| `N` | Speaker notes |
| `P` | Autoplay (11 s per slide) |
| `?` | Shortcut reminder |
| `Esc` | Close the notes drawer |

The map slide is fully interactive: play the 2019–2026 record forward, drag the
timeline, recolour by pipe size / water loss / cause / year, switch between the
dark canvas and aerial imagery, and hover any repair for its details.

## The twelve slides

| # | Slide | What it does |
|---|---|---|
| 1 | Cover | The pitch, with an animated radar scope |
| 2 | The problem | Non-revenue water, non-surfacing leaks, 1,691 local repairs |
| 3 | The signal | Expected condition → residual → persistence |
| 4 | One pipeline | The five-stage method |
| 5 | The data stack | Sentinel-1/2, Landsat, ERA5, static layers, network |
| 6 | Live dashboard | The Coryell repair map and time animation |
| 7 | Four networks | Bulgaria, Aguascalientes, Calgary, Coryell |
| 8 | Skill vs detection | Held-out R² versus label AUC |
| 9 | The negative result | Placebo-corridor validation and p-values |
| 10 | Why L-band | Sentinel-1 C-band versus NISAR L-band |
| 11 | Roadmap | What ships now, next and later |
| 12 | Close | Links to the live map, evidence explorer and code |

The **speaker notes** for each slide are stored in the `data-notes` attribute of
the section. They can be edited directly in `index.html` or opened with `N`
while presenting.

## Scientific honesty

The deck reports the result of the project's own validation rather than a
detector claim:

- The expected-condition models are skilful: Sentinel-1 VV R² **0.43–0.65** and
  NDMI R² **0.25–0.51** on held-out dates.
- The final leak score ranks historical repair points at **AUC ≈ 0.52–0.55**,
  where 0.50 is random.
- In Bulgaria the pipeline corridor is **not** statistically enriched against
  200 translated placebo corridors (mean p = 0.57, p95 p = 0.89).
- Coryell has a nominally small mean p (0.024) but its p95 test is 0.24, so it
  is reported as a weak positive, not a detection.

The product is a **screening and triage tool**. See
[`../docs/RESULTS.md`](../docs/RESULTS.md) and
[`../chris-results/docs/RESULTS.md`](../chris-results/docs/RESULTS.md) for the
full analysis.

## Files

```
presentation/
├── index.html   # the slides, the map shell and the speaker notes
├── style.css    # design system, transitions and responsive layout
├── app.js       # navigation, reveals, map, case switcher, notes
└── README.md    # this file
```

## Related

- [`../viz/`](../viz/) — the full Coryell leak map and NISAR before/after viewer.
- [`../chris-results/app/`](../chris-results/app/) — the multi-case evidence explorer.
- [`../outputs/aquaguard_map.html`](../outputs/aquaguard_map.html) — the self-contained Bulgaria map.
- [`../docs/SOLUTION.md`](../docs/SOLUTION.md) — the challenge-facing design.
