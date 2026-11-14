# Landslides with NISAR: literature review

Written 2026-11-14, during the hackathon. Purpose: decide whether a
landslide project is defensible, and if so which specific version of it is
not already done to death. All counts are from OpenAlex on 2026-11-14
(`title_and_abstract.search`), so they are order-of-magnitude, not exact.

## 0. Verdict in one paragraph

Landslides are **saturated as a generic remote-sensing topic and as a
hackathon cliché**, but **not saturated as a NISAR problem**. Nearly all
landslide SAR literature is C-band Sentinel-1 (1,280 papers mention
landslide + "Sentinel-1"; 3,085 mention landslide + InSAR; only 320 mention
landslide + "L-band"). The L-band niche is under-populated for a mundane
reason: until 2026 there was no free, global, systematic L-band SAR. ALOS-2
is commercial and tasking-limited, SAOCOM-1 needs registration and is
sparse, LuTan-1 is Chinese and restricted. NISAR removes that constraint.
So the defensible sentence is not "we detect landslides", it is **"we show
what becomes visible when the wavelength changes"**. If the project is
framed as landslide detection/mapping/susceptibility, it competes with
thousands of papers and a well-known NASA demo. If it is framed as the
L-band visibility gain, it is close to empty.

## 1. How crowded, numerically

| Query (title+abstract) | Total | Since 2024 | 2026 only |
|---|---|---|---|
| landslide + SAR | 2,515 | 680 | 248 |
| landslide + InSAR | 3,085 | 1,374 | 556 |
| landslide + Sentinel-1 | 1,280 | 570 | — |
| landslide + deep learning | — | 1,184 | — |
| landslide + ALOS | 555 | — | — |
| landslide + L-band | 320 | 84 | — |
| landslide + coherence | 593 | 256 | 132 |
| landslide + NISAR | 47 | 31 | — |
| NISAR (any topic) | 1,201 | — | — |

Read: roughly **10:1 InSAR-to-L-band** and **4:1 Sentinel-1-to-L-band**.
And of the 47 papers that mention NISAR and landslides, essentially none
analyse NISAR data — they are plans, mission descriptions, or outlook
paragraphs. No peer-reviewed landslide study using actual NISAR
acquisitions exists yet (as of this date).

Two 2026 reviews define the state of the art and both are worth skimming:
the InSAR-for-landslides review (Sensors 26(15), 4667) and the deep-learning
landslide review (NHESS 26, 487–529, which alone synthesises >400 studies
from 2020–2025).

## 2. What the recent literature actually says

### 2.1 InSAR for slow-moving landslides: mature, and its limits are known

The 2026 Sensors review lists the standard failure modes: geometric
distortion (layover/shadow), decorrelation, atmospheric delay, and the
inability to resolve 3D motion. InSAR works for *slow* movement and fails
for rapid failure, because of temporal phase aliasing (movement > λ/4
between acquisitions).

Practical consequence: a credible slow-landslide monitoring story needs
multi-year time series and many epochs. NISAR has ~12 months of data. It
cannot yet do what Sentinel-1 has done since 2014.

### 2.2 L-band vs C-band: the literature is unanimous, and it is NISAR's argument

This is the consistent finding across every recent comparison:

- **Strozzi et al. 2026** (NHESS 26, 2579–2607; published 4 Jun 2026) is the
  most useful paper for us. It evaluates ALOS-2 PALSAR-2, SAOCOM-1 and
  terrestrial L-band SAR on three large alpine rock-slope instabilities, and
  explicitly frames the result as guidance for NISAR, ALOS-4 and ROSE-L.
  Findings: L-band gives higher PS density and spatial continuity than
  C-band in all land-cover types, better delineates kinematic domains and
  toe activity, and holds coherence over very long temporal baselines
  (240 days at one site). It still fails where movement is fast (one slope
  was not resolved even at L-band). C-band PSI at the same sites was
  "scarce" in forested sectors.
- **Sensors 2026, 26(19), 6094**: L-band vs C-band InSAR for slow-moving
  landslides in the vegetated northern tropical Andes. Same direction.
- **Qijiang, Chongqing (2025, PMC12299697)**: multi-sensor comparison.
  ALOS-2/LuTan-1 (L) beat Sentinel-1 in vegetated and complex terrain;
  Sentinel-1 was better in urban/mining terrain and suffered more geometric
  distortion on slopes >25°.
- **LuTan-1, Hunan (Remote Sens. 2025, 17(6), 960)**: L-band identifies
  landslides in southern Chinese hilly terrain where C-band is blocked by
  vegetation.
- **ESA MODULATE / Blatten (Aug 2025)**: L-band revealed slope instability
  years before the 2025 Blatten rock/ice avalanche, in terrain where
  Sentinel-1 was limited.

The physical reason is uncontroversial: 24 cm penetrates further into the
canopy and decorrelates more slowly than 5.6 cm. The cost is a coarser
resolution and greater sensitivity to ionospheric phase.

### 2.3 Rapid and co-seismic landslide detection: coherence, not phase

A separate, cheaper branch of the literature is the one that matters for a
48-hour build, because it needs no phase unwrapping:

- **Burrows et al. 2020** (NHESS 20, 3197): systematic test of radar
  coherence methods for rapid landslide detection across four events.
  Co-event coherence loss (CECL) was the best method when a post-event
  L-band (ALOS-2) image arrived within 2 weeks. L-band classifers
  outperformed C-band in most cases. Includes the useful physical
  statement that coherence loss "repaves" the surface.
- **Burrows et al. 2021** (NHESS 21, 2993): adding the first ALOS-2 image
  produced the largest single improvement in landslide-density prediction,
  and the authors recommend routinely incorporating L-band data. That is a
  pre-launch endorsement of exactly what NISAR now provides for free.
- **NHESS 22, 753 (2022)**: Sentinel-1 backscatter-change density heatmaps
  in Google Earth Engine. The "cheap operational" precedent, C-band only.
- **Nava et al. 2026** (GMD 19, 167–185): globally distributed co-seismic
  landslide detection from Sentinel-1 with deep neural networks. The
  state of the art in the DL branch, and the thing not to try to beat in a
  weekend.

### 2.4 Deep learning: this is where "overdone" is literally true

1,184 papers since 2024 on landslide + deep learning. The 2026 NHESS review
catalogues the models, datasets and failure modes. A CNN/transformer
landslide segmentation in a hackathon is competing with a mature field and
will not read as novel to anyone who knows it.

## 3. NISAR-specific state of the art

### 3.1 There is exactly one real NISAR landslide result, and it is excellent

**Garcia Gonzalez et al. (Scripps/UCSD, Aug 2026), "M7.5 Venezuela
Earthquake: Line of sight displacement revealed by NISAR, ALOS-2 and
Sentinel-1 Interferometry"** — <https://topex.ucsd.edu/VNZ_7.5/>

The 24 June 2026 Mw 7.2/7.5 doublet near Caracas is the first big test case
of NISAR InSAR, and it is a clean natural experiment:

- C-band Sentinel-1 produced the first interferograms but **lost coherence
  over the densely vegetated terrain within ~14 km of Caracas**, exactly
  where the damage was. It could not resolve east/vertical decomposition.
- NISAR L-band (4 tracks, all 12-day pairs) held coherence and resolved
  >900 mm LOS, >1200 mm horizontal.
- Using NISAR track T126D, they differenced pre- and post-seismic
  coherence and mapped **negative coherence change as landslides**, which
  matched the USGS ground-failure landslide report north of Caracas.
- Bonus: the USGS relocated the epicentre ~115 km east once NISAR products
  became available.

Caveats: they processed **L1 RSLC with GMTSAR** and used frequency A+B SLC
to correct ionospheric phase. That is a real processing chain, not a
weekend job. The hackathon-feasible subset is the coherence layer only.

### 3.2 What the products actually let you do

- **GUNW**: geocoded unwrapped phase at 80 m, coherence at 20/80 m,
  connected-components mask, ionospheric screen. Constraint from the user
  guide: **only co-polarised (HH or VV), only nearest-neighbour 12-day
  pairs, only frequency A**. So you cannot pick arbitrary date pairs from
  GUNW, and you get no cross-pol. For coherence-change work this is mostly
  fine — you get a ready-made 12-day coherence layer for every cycle.
- **GSLC**: all pairs possible, both HH and HV, but you must do your own
  interferometry (needs ISCE3 or GMTSAR).
- **GCOV**: HH/HV or VV/VH backscatter, terrain-corrected, easy. Amplitude
  change is weaker evidence than coherence for landslides but fine for
  debris flows, scar brightness, and vegetation loss.
- **SME2**: soil moisture at 200 m, on the same platform as the
  deformation data. Nothing in the literature has paired these yet.

### 3.3 The field is being actively solicited right now

- Taylor & Francis special issue, *Advancing Earth Observation with NISAR:
  Early Results in Data Processing, Geophysical Interpretation, and
  Multi-Source Synthesis*, explicitly lists "landslides" and "landslide
  slip-surface geometry and geomechanical parameters" as topics.
- NASA ARSET ran *Identifying Disaster Extent and Risk Using NISAR Surface
  Displacement* on **Nov 12 and Nov 19, 2026** (Eric Fielding, JPL), with
  landslides as the first named use case, plus OPERA displacement products.
  Slides are already posted. That is a free tutorial pipeline for this exact
  problem, published days ago.
- The NISAR Science Users' Handbook has a landslide section arguing L- and
  S-band both advance landslide science, via coherence mapping and rapid
  tasking.

Consequence for judging: NASA has spent the last two weeks teaching people
to do NISAR-InSAR-for-landslides. Expect other teams to attempt it. The
differentiator cannot be "we used NISAR GUNW for a landslide"; it has to be
a specific question.

## 4. Where the genuine gaps are

1. **Coherence-based landslide detection as a product, not a case study.**
   The method is validated (Burrows 2020) and demonstrated once with NISAR
   (Venezuela). Nobody has built the operational version: a regional
   pipeline that flags coherence-loss patches and suppresses the false
   positives (harvest, flooding, fire, building damage) using land cover.
   This is the one landslide idea that is both open and buildable.
2. **Landslides in the vegetated tropics/subtropics.** The C-band blind
   spot. This is where L-band wins by the largest margin, where ALOS-2 was
   data-starved, and where landslide mortality is highest. Not a
   wavelength-agnostic topic.
3. **Deformation + soil moisture coupling.** SME2 and GUNW are on the same
   satellite, on the same day. Antecedent moisture as a trigger is a
   standard idea in geomorphology and has never been tested with
   co-located, co-temporal L-band observations. Highest novelty, highest
   risk (SME2 validation status unverified).
4. **Rapid response latency.** NISAR forward processing advertises
   delivery within ~72 h. Nobody has measured what a 72-hour free global
   L-band landslide product is actually worth.

## 5. Why a landslide project is still a risky 48-hour build

- **Phase unwrapping can fail.** If the deliverable depends on GUNW
  displacement over steep terrain, you may end with a speckled map and no
  story. Coherence-only work avoids this.
- **One year of data.** No multi-year velocity trends, no meaningful
  seasonal baseline, and calibrated data only from 17 June 2026. Anything
  before October 2025 does not exist for NISAR.
- **No ground truth.** Judges will ask how you distinguish a landslide from
  a harvest, a flood, or a processing artefact. You need an independent
  reference (USGS ground-failure product, Sentinel-2, news reports) or an
  explicit false-positive control.
- **Event dependence.** The coherence-change method needs a dated trigger.
  In the NISAR era the well-documented one is Venezuela, June 2026 — which
  is also the one already published by Scripps.
- **Narrow.** One slope, one event is a thin answer to a brief that asks
  for a global-capable application.

## 6. Reframings and alternatives, ranked

**A. "The coherence blind spot" (recommended if staying with landslides).**
Not "we found a landslide" but "we measured what C-band cannot see". Over
one landslide-prone vegetated region, compute the fraction of terrain that
is coherent in NISAR L-band but decorrelated in Sentinel-1 C-band, and
quantify the population/infrastructure/landslide inventory inside that
blind spot. Uses coherence layers only (no unwrapping), is a measurement
rather than a case study, is visually striking, answers the challenge's
polarisation question with HH vs HV from GCOV, and is genuinely unpublished.
Risk: needs Sentinel-1 coherence for comparison, i.e. some processing.

**B. Danube Delta / Black Sea coastal wetland dynamics.**
Under-canopy inundation in reed beds, seasonal water extent, coastal
change. NISAR's flagship application, locally personal for a Bulgarian
team, easy with GCOV, and "why does the water disappear under the reeds"
is a good physics story. Less novel than A but far more robust to build.
Risk: the wetland/water topic is itself busy, and ARSET just ran a NISAR
surface-water training in October 2026.

**C. Peatland drainage and subsidence.**
Carbon relevance, poor C-band coverage historically, L-band + InSAR +
soil moisture. Strong science, weak local hook, needs a site outside the
region.

**D. Forest degradation under persistent cloud.**
HV time series, L-band penetrates, cloud-free tropics. Fits the brief's
"forests shrink" example directly. Crowded in optical, but the SAR version
is NISAR-native.

## 7. References

Peer-reviewed, recent first:

1. Strozzi, T., Jones, N., Agliardi, F., De Pedrini, A., Frey, O., Bernhard,
   P., Caduff, R., Ambrosi, C., Manconi, A. (2026). Monitoring the
   displacement of large alpine rock slope instabilities with L-band SAR
   interferometric techniques. *NHESS*, 26, 2579–2607.
   <https://doi.org/10.5194/nhess-26-2579-2026>
2. Jiang, P., Ma, Z., Mei, G. (2026). Review article: Deep learning for
   potential landslide identification: data, models, applications,
   challenges, and opportunities. *NHESS*, 26, 487–529.
   <https://doi.org/10.5194/nhess-26-487-2026>
3. InSAR Techniques for Landslide Study: A Review of Methods, Challenges,
   and Emerging Trends (2026). *Sensors*, 26(15), 4667.
   <https://doi.org/10.3390/s26154667>
4. Applicability of L-Band and C-Band InSAR for Detecting Slow-Moving
   Landslides in Vegetated Tropical Andes (2026). *Sensors*, 26(19), 6094.
   <https://doi.org/10.3390/s26196094>
5. Nava, L., Mondini, A., Bhuyan, K., Fang, C., Monserrat, O., Novellino,
   A., Catani, F. (2026). Sentinel-1 SAR-based globally distributed
   co-seismic landslide detection by deep neural networks. *GMD*, 19,
   167–185.
6. Applicability of Multi-Sensor and Multi-Geometry SAR Data for Landslide
   Detection in Southwestern China (2025). *Sensors* / PMC12299697.
7. Assessing the Landslide Identification Capability of LuTan-1 in Hilly
   Regions (2025). *Remote Sensing*, 17(6), 960.
8. Burrows, K., Walters, R.J., Milledge, D., Densmore, A.L. (2020). A
   systematic exploration of satellite radar coherence methods for rapid
   landslide detection. *NHESS*, 20, 3197–3214.
   <https://doi.org/10.5194/nhess-20-3197-2020>
9. Burrows, K. et al. (2021). Integrating empirical models and satellite
   radar can improve landslide detection for emergency response. *NHESS*,
   21, 2993. <https://doi.org/10.5194/nhess-21-2993-2021>
10. Generating landslide density heatmaps for rapid detection using
    open-access satellite radar data in Google Earth Engine (2022).
    *NHESS*, 22, 753.

Grey literature and mission documentation:

11. Garcia Gonzalez, R., Zebker, M., Brandin, M., Wu, B., Magen, Y.,
    Tymofyeyeva, E., Sandwell, D. (2026). M7.5 Venezuela Earthquake: Line
    of sight displacement revealed by NISAR, ALOS-2 and Sentinel-1
    Interferometry. Scripps Institution of Oceanography.
    <https://topex.ucsd.edu/VNZ_7.5/>
12. NASA ARSET (2026). Identifying Disaster Extent and Risk Using NISAR
    Surface Displacement, 12–19 Nov 2026.
    <https://www.earthdata.nasa.gov/learn/trainings/identifying-disaster-extent-risk-using-nisar-surface-displacement>
13. NISAR Data User Guide — GUNW, GCOV, availability.
    <https://nisar-docs.asf.alaska.edu/gunw>
14. NASA-ISRO SAR (NISAR) Mission Science Users' Handbook, landslide
    science section.
15. NISAR Interferometric Sensitivity to Biophysical Land Properties,
    FRINGE 2026 (ESA). Coherence decay with repeat interval, GSLC vs GUNW.
16. Taylor & Francis special issue: Advancing Earth Observation with NISAR.
    <https://think.taylorandfrancis.com/special_issues/advancing-earth-observation-with-nisar-early-results-in-data-processing-geophysical-interpretation-and-multi-source-synthesis>

## 8. Addendum: what the ML landslide papers actually train on

Four archetypes, in descending order of how much training happens.

**a. Trained on a public benchmark, tested on the same benchmark.**
The benchmarks are optical, not SAR.

| Benchmark | Content | Size | Label source |
|---|---|---|---|
| Landslide4Sense (2022) | Sentinel-2 + ALOS PALSAR DEM/slope, 128×128 patches, 4 events / 14 regions | 3,799 patches | manual optical digitising |
| CAS Landslide Dataset (2023) | RGB satellite + UAV, 9 regions | 20,865 images | manual |
| DMLD (2024) | 1 m optical, 19 counties in Yunnan | 490 images, 1000×1000, ~990 instances | manual |

For scale, the CAS paper notes that before it, the largest public DL
landslide dataset was 3,799 images and the smallest was 59. These are small
datasets by DL standards, which is why the field leans on transfer learning,
synthetic data (GANs) and heavy augmentation.

**b. Trained on one to three hand-digitised event inventories.**
The modal paper. Typically a few thousand 64×64 or 128×128 patches cut from
one or two scenes, split randomly into train/val/test, reported as 90–97 %
accuracy. Nava et al. (2026) say this explicitly of the prior literature:
"Most existing studies have been tested on only a few events, often two or
three." Random patch splits from the same event leak spatial context and
inflate scores; almost none hold out an event.

**c. Trained across many events with held-out events.**
The exception, and the reference standard. Nava et al. (2026):

- 11 earthquake-triggered events worldwide. The abstract claims "≈73 000
  landslides", but that is a count of **digitised landslide polygons**, not
  training examples. Table 1 per event: Gorkha 24,915; Kaikōura 14,233;
  Capellades 51; Milin 939; PNG 11,607; Lombok 12,688; Hokkaido 7,837;
  Mesetas 837; Haiti 4,887; Luding 5,336; Sumatra 171. That sums to
  **83,501**, not 73,000. The first eight events alone sum to 73,107, so
  the abstract figure appears to predate the last three, or ~10k were
  dropped after layover/shadow masking. Trust the table, not the abstract.
- Input: Sentinel-1 GRD, 10 m, VV and VV+VH, ascending and descending,
  64×64 patches (~0.4 km²). A patch is positive only if >5 % of its pixels
  are landslide (~2,000 m²), and one patch can contain many individual
  landslides. **The number of training patches is never stated** in the
  paper. So the real training set is much smaller than the headline count.
- Labels: optical/manual inventories (Roback 2017 Gorkha, Tanyaş 2022,
  Fang 2024 ESSD global co-seismic dataset), clipped by layover/shadow masks.
- Class imbalance: the *natural* background-to-landslide patch ratio in the
  sampled grid is 8:1 (Hokkaido) to 120:1 (Gorkha), i.e. that is how rare
  landslides are on the ground, not a training choice. For training they
  subsample to an imbalance of 4:1–6:1 ("Train Imbalance" column,
  Table 4). The test-set ratio is capped at 10:1. So the reported
  precision/recall are measured at an artificially favourable prevalence
  and will overstate operational performance at 120:1.
- Split: 67/33 per event, plus two events never seen in development
  (Haiti 2021, Sumatra 2022) for the transfer test.
- 40 models trained (2 polarisations × 2 orbits × 10 temporal windows);
  best F1 82.5 %, accuracy 96.4 %.

Note what 96 % accuracy means at 8:1 imbalance: predicting all-background
already scores ~89 %. F1 is the only number worth reading.

**d. No training at all.**
The physics branch, and the one that works operationally:

- Burrows et al. (2020): coherence thresholds (co-event coherence loss),
  tuned per event, no learned parameters.
- Handwerger et al. (2022): Sentinel-1 backscatter-change density heatmaps
  in Google Earth Engine, threshold-based.
- Scripps NISAR Venezuela (2026): coherence differencing, compared against
  the USGS ground-failure product. No model.

**Consequences for us.** The bottleneck in this literature is labels, not
architectures. Every SAR training label in existence was digitised from
optical imagery, so the model learns "what the SAR looks like where an
optical interpreter drew a polygon". And there is no NISAR landslide
dataset at all — zero labelled NISAR examples. Training anything from
scratch on NISAR in 48 hours is not possible; the options are transfer from
Sentinel-1/ALOS-2 or a physically-justified threshold with an independent
reference. The strongest published results in the rapid-response setting
come from the threshold branch.
