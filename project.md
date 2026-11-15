# Project context: Dancing with the SARs

Onboarding document for anyone (human or agent) working in this repository.
Read this first. It explains what we are building, why, what data we have to
work with, and what is still undecided.

Last updated: 2026-11-14. Facts about NISAR data were taken from the
[NISAR Data User Guide](https://nisar-docs.asf.alaska.edu/) on that date; the
mission is young and releases change quickly, so re-check anything
time-sensitive.

## 1. What this repository is

This is a team entry for the **NASA Space Apps Challenge 2026**, a global
weekend hackathon held on **November 14-15, 2026**. We are addressing the
challenge **"Dancing with the SARs"**.

- Challenge page: <https://www.spaceappschallenge.org/2026/challenges/dancing-with-the-sars/>
- Difficulty: Intermediate / Advanced. Subject: Earth Science.
- Full challenge text and resource list, saved verbatim:
  [`research/Challenge Description.md`](research/Challenge%20Description.md)

The repository is at the very start. At the time of writing it contains only
research notes, no code.

| Path | Contents |
|---|---|
| `project.md` | This document. |
| `research/Challenge Description.md` | Verbatim copy of the challenge statement and its Resources tab. |
| `research/Ideas for the Hackathon.md` | The team's initial idea notes. |

## 2. The challenge in one paragraph

> Build an interactive application that uses radar remote sensing data from the
> NASA-ISRO Synthetic Aperture Radar (NISAR) mission to track and visualize one
> or more types of surface change at locations around the world.

Earth's surface changes constantly (wetlands and floodplains expand and
retract, forests shrink from deforestation and wildfire, crops and soil
moisture change, glaciers and sea ice move, land deforms from earthquakes and
subsidence). These changes are hard to see and communicate. The challenge is to
make NISAR data accessible so that scientists, resource managers, educators,
decision-makers and the public can understand them.

## 3. What we are supposed to do

The challenge statement lays out three steps:

1. **Pick a study area.** Anywhere: a hometown, a wetland, an ice sheet, a
   wildfire, a flooded neighbourhood, a volcano.
2. **Download freely available NISAR data** from the listed resources.
   Supplemental data (optical imagery, GIS layers) is encouraged for context.
3. **Present the findings in an interactive digital medium** and **hypothesize
   the physical drivers** behind what is visible (or not visible) in the SAR
   data. The statement asks questions such as: why does the surface change
   over time, which polarizations highlight the change, and what future
   applications of NISAR are possible?

### What a good submission looks like

Taken from the Objectives and Potential Considerations sections:

- **Open-source and user-friendly.** The stated desired outcome is "an
  open-source, user-friendly solution that translates complex radar
  observations into actionable insights".
- **Interactive.** Suggested forms: change-detection maps, time-series
  animations, dashboards, image sliders, web maps, story maps.
- **NISAR at the centre.** Other sensors are framed as optional comparisons
  ("different frequencies from other sensors"), not as the main data source.
- **A time dimension.** Data from different dates to show change.
- **Context.** Ancillary datasets such as population or vegetation type.
- **Storytelling.** Compelling data visualization, local or personal context
  for the study area, and the human drivers (agriculture, industry) behind the
  change.
- **Physical interpretation.** Explain what the radar is responding to, not
  only where pixels changed.

All of the "Potential Considerations" are optional ("you may, but are not
required to").

### Not verified yet

The general Space Apps submission requirements (project page fields, demo
format, deadline in local time, judging criteria) have **not** been checked.
Look them up on <https://www.spaceappschallenge.org/2026/> and in the
participant guides under <https://www.spaceappschallenge.org/resources/>
before planning the final deliverable.

## 4. Current state of the idea

The only idea recorded so far (`research/Ideas for the Hackathon.md`):

- Track unusual movement or changes of ships in the Black Sea using SAR data.
- SAR works in cloudy weather.
- Two people will work on the data.

**This idea is not confirmed and has open risks against the brief.** Do not
build on it without checking with the team.

- The challenge theme is *surface change*, and every example is a land, ice or
  water-extent process. Ships are not mentioned in the statement.
- The challenge asks for NISAR data specifically. NISAR's published coverage is
  "most landmasses and sea ice"; whether it images the open Black Sea is
  **unverified**. Check the Reference Observation Plan app and search ASF
  Vertex over the area before committing.
- Ship monitoring does appear in the partner resources: Canada's RADARSAT
  Constellation Mission lists maritime surveillance and ship monitoring. That
  would make a non-NISAR sensor the main data source, which sits awkwardly with
  the brief.
- A 12-day-cycle satellite sees a given spot rarely, so it captures snapshots
  of ship positions, not movement tracks. (The 12-day figure comes from the
  GCOV file-naming description, "12-day cycles", and the Worldview "12Day"
  layer.)

### 4.1 Direction under evaluation: water pipeline leaks — AquaGuard (2026-11-14)

A second candidate direction has been researched in depth:
[`research/Pipeline-Leak-Detection.md`](research/Pipeline-Leak-Detection.md),
with the underlying SAR physics and detection limits in
[`research/SAR-Pipeline-Leak-Research-Brief.md`](research/SAR-Pipeline-Leak-Research-Brief.md).

**Scope is water only** — drinking-water and wastewater pipelines. Oil, gas,
methane and district heating are explicitly out of scope.

Summary of the review: a buried water leak is invisible to a satellite, but the
wet soil around it is not. The strongest formulation is not "find wet ground" but
**"find ground that stays wet when the weather says it should be dry"** — a
weather-normalised residual anomaly along a known pipe corridor. Six independent
signature families are available (electromagnetic, thermal, hydrological,
biological, mechanical, hydraulic); the strongest system fuses several because
each fails in a different environment.

Evidence base:

- **Commercial:** Affinity Water / SUEZ / ASTERRA screened 9,045 km of network
  with L-band SAR, delivered 763 locations, confirmed **902 leaks**, of which
  **59 % had no surface manifestation**; crews inspected <4 % of the network.
  Vendor-reported, not an independent trial; every site was confirmed with
  acoustic equipment.
- **Peer-reviewed:** MDFLD-Net (2025) reports **86.3 % accuracy** on 1,545
  field-verified leaks using L-band + C-band + polarimetry + closure phase;
  Yan et al. (2024) report **91.86 %** on a water/sewer network; an unsupervised
  study under paved surfaces (2026) found **81 % of leaks with a 93 % reduction
  in inspection effort**, but many false positives.
- **Physics:** L-band responds to subsurface moisture (R² = 0.705 predicting
  relative dielectric constant, validated with GPR); a 5 % moisture increase
  gives 0.6–3 dB of backscatter, but the **speckle floor at 10 m is ~5.8 dB**, so
  time-series averaging or 40–60 m multi-looking is mandatory.
- **Thermal:** 100 m satellite TIR cannot detect a water leak — a 5 K anomaly
  needs a 40 m-wide patch to register 2 K. Only airborne/UAV TIR and SatVu's
  3.5 m HotSat approach pipeline scale, and they see the halo, not the pipe.

**Critical constraint:** the NISAR archive starts October 2025, so no historical
leak can be studied with NISAR. Use Sentinel-1 (2014–present) as the temporal
backbone and NISAR for the most recent year and the L-band vs C-band comparison.
NISAR is left-looking, unlike Sentinel-1's right-looking geometry.

**Novelty:** ESA has already funded SECO, WATERLENS and ZOE, and "SAR + NDVI"
is not novel. The defensible contributions are (A) weather-normalised residual
anomaly detection with a published rainfall ablation and false-alarm rate per km
per year, (B) radar + thermal + hydraulic fusion with calibrated uncertainty, or
(C) physics-informed leak-evolution modelling.

**Validation:** public point-level water-leak data is scarce. Toronto publishes
both watermain breaks and the pipe network with diameter/material; NYC, Chicago,
Madison and DC Water publish break records. Treat breaks as weak labels (they are
bursts, not background leaks) and use the "anomaly appears → repair → anomaly
disappears" test as the strongest available validation.

Alternatives that fit the brief directly and can use the same Black Sea
region: coastal or port change, river delta and wetland extent (for example
the Danube Delta), flooding, agricultural cycles, or land subsidence.

## 5. SAR in brief

Enough background to read the data sensibly.

- **Active sensor.** SAR emits its own microwave pulses and records the echo,
  so it works day and night and through cloud, smoke and haze. Optical sensors
  are passive and depend on sunlight.
- **Synthetic aperture.** A long antenna is synthesized by combining a sequence
  of acquisitions from a short real antenna, giving high spatial resolution.
- **What it is sensitive to.** Surface **roughness** and the **dielectric
  constant**. Water has a high dielectric constant, so SAR highlights water
  bodies, flood inundation and soil moisture. Smooth open water reflects the
  pulse away and looks dark.
- **Backscatter and polarization.** The strength of the echo in different
  transmit/receive polarizations (HH, HV, VV, VH) carries information about
  structure, geometry and material. Cross-polarized channels (HV, VH) respond
  strongly to vegetation volume.
- **Phase and interferometry (InSAR).** Comparing the phase of two acquisitions
  measures surface movement at centimetre scale (earthquakes, subsidence,
  glacier flow).
- **Speckle.** SAR images are grainy by nature. Averaging (multi-looking) or
  filtering is normal before comparing dates.

Primers: [Intro to SAR](https://www.earthdata.nasa.gov/learn/earth-observation-data-basics/sar),
[Intro to Remote Sensing](https://www.earthdata.nasa.gov/learn/earth-observation-data-basics/remote-sensing).

## 6. The data: NISAR

### Mission facts

| Property | Value |
|---|---|
| Partners | NASA and ISRO. Launched 2025-07-30. |
| Bands | L-band (24 cm wavelength) and S-band (9.3 cm). |
| L-band coverage | Global: most landmasses and sea ice, on a regular repeat cycle, since August 2025. |
| S-band coverage | Select areas, primarily India. |
| Swath | About 240 km for most L-band acquisitions. |
| Native resolution | 7 m along-track, 2-8 m cross-track depending on mode. |
| Look direction | Left-looking (full Antarctic coverage, gap around the North Pole). |
| Polarization modes | Single (SH = HH, SV = VV), dual (DH = HH+HV, DV = VV+VH), quad (QP), compact (RH, RV). The mode varies by region. |
| Data policy | Free and open. |

Where the data lives:

- **L-band**: archived by the Alaska Satellite Facility (ASF), hosted in NASA
  Earthdata Cloud on AWS. This is the data we will use.
- **S-band**: distributed by ISRO through
  [Bhoonidhi](https://bhoonidhi.nrsc.gov.in/bhoonidhi/index.html).

Which mode covers which region is shown in the
[Reference Observation Plan app](https://experience.arcgis.com/experience/6052a864cd01459393884a7f751558e3).

### Products

All products are HDF5 files. Level 1 products are in radar (range-Doppler)
coordinates and cannot be overlaid on a map directly. **Level 2 and 3 products
are geocoded and described as analysis-ready; start there.**

| Level | Short name | What it is | Pixel spacing | Geocoded |
|---|---|---|---|---|
| 0 | RRSD | Raw radar signal data | n/a | No |
| 1 | RSLC | Focused single look complex image | native | No |
| 1 | RIFG | Wrapped interferogram | 30 m | No |
| 1 | RUNW | Unwrapped interferogram (displacement) | 80 m | No |
| 1 | ROFF | Pixel offsets from speckle tracking (mainly ice) | 90 m | No |
| 2 | **GCOV** | Terrain-corrected backscatter (polarimetric covariance) | 10, 20 or 80 m | Yes (UTM) |
| 2 | **GSLC** | Geocoded single look complex, per polarization | 5-40 m | Yes |
| 2 | **GUNW** | Geocoded unwrapped interferogram (displacement) | 80 m | Yes |
| 2 | GOFF | Geocoded pixel offsets (mainly ice) | 80 m | Yes |
| 3 | SME2 | Soil moisture (three algorithms) | 200 m | Yes (EASE-Grid 2.0) |

Which product for which kind of change:

- **GCOV** is the default choice for this project. It is calibrated gamma-0
  backscatter power, radiometrically terrain-corrected using the Copernicus
  DEM, usable like an RTC product. It suits flood and water extent, vegetation
  and forest disturbance, agriculture, and general before/after change
  detection. The user guide calls it the easiest product for GIS beginners.
- **GUNW** is for ground deformation: earthquakes, subsidence, volcanoes.
- **GSLC** is for custom change maps and coherence, and for deriving
  off-diagonal polarimetric terms in dual-pol data. Files are large and need
  SAR expertise.
- **GOFF** is for glacier and ice motion.
- **SME2** is for soil moisture.

### Inside a GCOV file

- Covariance terms live at
  `/science/LSAR/GCOV/grids/frequency[A|B]/<TERM>`.
- Diagonal terms are real-valued backscatter intensity: `HHHH`, `HVHV`,
  `VVVV`, `VHVH` (and `RHRH`, `RVRV` for compact-pol). Which ones exist depends
  on the acquisition's polarization mode.
- Off-diagonal complex terms (`HHHV`, `HHVV`, ...) exist only for quad-pol
  acquisitions.
- Supporting layers in the same group: `numberOfLooks`, `mask`,
  `rtcGammaToSigmaFactor`.
- `frequencyA` is the primary science band (typically 10 or 20 m).
  `frequencyB` is mainly for atmospheric correction and is coarser (80 m).
- Whether stored power is linear or dB is not stated in the guide. Check the
  dataset attributes; assume linear power and convert with `10 * log10(x)` for
  display only after confirming.
- The user guide is inconsistent about term names (one page shows `HH`, another
  `HHHH`). List the datasets in a real file before hard-coding paths.

File names encode, in order: mission and instrument, level, processing type,
product ID, cycle number, relative orbit (track, 001-173), direction (A/D),
frame (001-176), bandwidth mode codes, polarization codes, source, start and
end time (UTC), CRID (processing version), and a few quality flags.
**To compare dates, use scenes with the same track, frame and direction.**

### Availability and caveats

| Maturity | Released | Covers acquisitions | Notes |
|---|---|---|---|
| BETA | 2026-02-27 | 2025-10-17 to 2026-01-20 | Not fully calibrated. Up to 8 acquisitions per track. |
| PROVISIONAL | 2026-07-20 | from 2026-06-17 | Calibrated, partially validated. CRID P05023. |
| VALIDATED | 2026-11-06 | from 2026-10-21 | Levels 0-2 only. CRID P05036. |

Things that will bite a time-series analysis:

- **Do not mix maturity levels or CRIDs blindly.** Differences between
  processing versions can look like surface change.
- **Permanent data gap** from 2026-07-27 to 2026-08-10.
- **Short record.** The archive starts in late 2025, so about one year of data
  exists and seasonal comparisons have at most one cycle. Events before
  October 2025 cannot be studied with NISAR.
- **Data acquired before 2026-10-21 will be reprocessed in 2027.**
- Known issues per release:
  <https://nisar-docs.asf.alaska.edu/nisar-known-issues>.
- **Files are large.** Subset to the area of interest instead of downloading
  whole frames where possible.

### Access

A free **Earthdata Login** account is required for every download:
<https://urs.earthdata.nasa.gov/>. Store credentials in a `.netrc` file in the
home directory (`C:/Users/<name>/.netrc` on Windows):

```
machine urs.earthdata.nasa.gov
    login <username>
    password <password>
```

Never commit `.netrc` or credentials to this repository.

| Method | Use it for |
|---|---|
| [ASF Vertex](https://search.asf.alaska.edu/) | Browsing and searching by map. Best first stop for checking coverage of a study area. |
| [`asf_search`](https://docs.asf.alaska.edu/asf_search/basics/) (Python) | Scripted search and download. |
| [`earthaccess`](https://earthaccess.readthedocs.io/en/stable/) (Python) | General NASA Earthdata access. |
| [Earthdata Search](https://search.earthdata.nasa.gov/search) | Searching all NASA holdings, including supplemental data. |
| [Worldview](https://worldview.earthdata.nasa.gov/) | Quick visual browse of NISAR GCOV layers and time comparison without downloading. |
| GDAL `/vsicurl/` | Reading or subsetting a remote HDF5 without downloading the whole file. |
| Direct AWS S3 | In-cloud processing. |

Search and download with `asf_search` (from the user guide):

```python
import asf_search as asf

results = asf.search(dataset='NISAR', processingLevel='GCOV',
                     dataMaturity='VALIDATED')
results.download(path='path/to/data/')   # uses .netrc
```

Standard `asf_search` filters such as `intersectsWith` (WKT), `start` and
`end` are expected to work with the NISAR dataset, but this has not been
tested here.

Remote subsetting with GDAL:

```
gdalinfo "/vsicurl/https://<DOWNLOAD URL>"
gdal_translate -of GTiff \
  "/vsicurl/https://<DOWNLOAD URL>"://science/LSAR/GCOV/grids/frequencyA/HHHH out.tif
```

This needs `GDAL_HTTP_NETRC=YES` plus `GDAL_HTTP_COOKIEFILE` and
`GDAL_HTTP_COOKIEJAR` set. Details: <https://nisar-docs.asf.alaska.edu/gdal>.

### Tooling notes

- **GDAL 3.13.0 or newer** reads NISAR HDF5 natively. With older GDAL, use the
  `NETCDF:` driver prefix or rename `.h5` to `.nc`.
- **QGIS 4.2+** and **ArcGIS Pro 3.4.0+** open Level 2 and 3 grids directly.
- In Python, `h5py` and `xarray` read the files; the structure follows netCDF
  CF conventions.
- **ISCE3** is the processing library behind the products. It is only needed
  for custom SAR processing and requires expertise.
- There is **no ready-made NISAR tile or image service** for web maps yet
  (Earthdata GIS image services and Harmony subsetting are still in
  development). A web app will need its own pre-processed rasters, for example
  Cloud-Optimized GeoTIFFs or pre-rendered tiles made from GCOV subsets.

## 7. Other resources from the challenge page

Learning and inspiration:

- [NISAR Data User Guide](https://nisar-docs.asf.alaska.edu/): the main
  technical reference. Useful pages: `/products-overview`,
  `/availability-overview`, `/access-overview`, `/using-overview`, `/gcov`,
  `/gdal`, `/asf-search`.
- [NISAR Cookbook](https://asfopensarlab.github.io/NISAR_Cookbook/)
  ([repository](https://github.com/ASFOpenSARlab/NISAR_Cookbook)): Python
  notebooks for working with NISAR data. Linked from the user guide.
- [NISAR Science Algorithms](https://github.com/NISAR-Science-Algorithms):
  science team notebooks for higher-level products.
- [NISAR StoryMaps](https://nisar.jpl.nasa.gov/applications/arcgis-storymaps/):
  SAR applications for floods, wildfires, subsidence, oil slicks, glacier
  motion. Good models for the storytelling part.
- [NISAR Applications White Papers](https://nisar.jpl.nasa.gov/applications/societal-benefit/):
  two-page overviews per application area.
- [NASA ARSET Trainings](https://appliedsciences.nasa.gov/get-involved/training):
  courses on remote sensing, SAR and NISAR.
- [UAVSAR Postcards](https://uavsar.jpl.nasa.gov/education/postcards.html):
  false-colour composites of airborne SAR.

Partner agency data (supplemental; each site has its own terms of use):

- **CSA (Canada)**:
  [RADARSAT Constellation Mission](https://donnees-data.asc-csa.gc.ca/en/dataset/rcm)
  (C-band; maritime surveillance, disasters, ecosystems),
  [RADARSAT-1 archive](https://donnees-data.asc-csa.gc.ca/en/dataset/radarsat1)
  (1995 onward, open licence), and a
  [SAR Python tutorial](https://github.com/asc-csa/Synthetic_Aperture_Radar_Tutorial).
- **CONAE (Argentina)**:
  [SAOCOM catalogue](https://catalogos.conae.gov.ar/catalogo/catalogoSatSaocomInfo.html)
  (L-band; registration required).

## 8. Guidance for agents working here

- **Check the brief before building.** A feature that does not help someone
  see or understand surface change in NISAR data is probably out of scope.
- **Time is the main constraint.** The hackathon is two days. Prefer a small
  study area, one change type, a handful of dates and a working demo over a
  general platform.
- **Confirm data exists before designing around it.** Search Vertex or
  `asf_search` for the study area first: check that scenes exist, on which
  dates, in which polarization mode and at which maturity level.
- **Keep large data out of git.** NISAR files are large. Store downloads
  outside the repository or in a git-ignored directory, and commit only
  scripts that reproduce them plus small derived products.
- **Keep it open-source.** The challenge asks for an open-source solution. Use
  openly licensed dependencies and data.
- **Record sources.** Add findings and references to `research/` so the final
  write-up can cite them.
- **State uncertainty.** Several facts in this document are marked unverified.
  If you verify or disprove one, update this file.

## 9. Open questions

1. Which study area and which type of surface change? (See section 4.)
2. Does NISAR have usable coverage, in a suitable mode, over that area?
3. What form does the deliverable take: web map, dashboard, story map?
4. What are the official submission requirements and deadline?
5. What stack do we build on? Nothing has been chosen.
