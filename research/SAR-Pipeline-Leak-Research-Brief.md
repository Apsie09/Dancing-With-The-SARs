# SAR for Pipeline Leakage and Pipeline-Related Ground Change

**A research brief with quantitative detection limits**

Written 2026-11-14. Scope: InSAR deformation, amplitude/backscatter change,
soil-moisture products, polarimetry, case studies, and operational constraints.
Every number is sourced unless explicitly marked **derived** (arithmetic shown)
or **estimate**. Claims are graded:

| Grade | Meaning |
|---|---|
| **A** | Operational or multiply validated; independent ground truth |
| **B** | Peer-reviewed, one good case or limited validation |
| **C** | Proof-of-concept, laboratory, or single small study |
| **D** | Theoretical / plausible but not demonstrated |

---

## 0. Bottom line

1. **InSAR is proven for pipeline *geohazards*, not for leak detection.** It
   measures ground displacement along corridors at mm/yr precision in good
   conditions. It does not detect a buried pipe, and it does not detect a small
   leak unless the leak has already caused measurable ground movement. **Grade A**
   for geohazards; **Grade D** for small-leak detection by deformation alone.

2. **The best-documented "leak" deformation signals come from wells, not
   pipelines.** Casing breaches and well blowouts in the Permian Basin produced
   20 cm/yr uplift, 53 cm cumulative uplift, and 3 cm of subsidence in two weeks
   (Zebker et al., 2025; Karanam et al., 2024). These are the closest
   quantitative analogues to a pipeline leak, because the mechanism —
   pressurised fluid escaping into shallow ground — is the same. **Grade B.**

3. **Documented InSAR velocity accuracy is 8–10 mm/yr against GNSS and
   levelling, and 4–6 mm/yr between PSI and SBAS** (Cigna et al., 2021). The
   often-quoted "1 mm/yr" is an ideal-case precision, not an accuracy. **Grade A.**

4. **A single interferogram is atmosphere-limited at ~1–2 cm**, not mm
   (Zebker, 2021). Transient events smaller than ~1 cm between two acquisitions
   are generally invisible; multi-year stacks are needed for mm/yr trends.
   **Grade A.**

5. **Backscatter sensitivity to soil moisture is 0.12 dB per vol.% at C-band and
   0.27 dB per vol.% at L-band over bare/low-vegetation soil** (El Hajj et al.,
   2019). A 5 vol.% leak wetting produces ~0.6 dB (C) or ~1.4 dB (L) — at or
   below the speckle noise of a single 10 m Sentinel-1 pixel (~1.9 dB).
   **Grade B.**

6. **Soil-moisture products are 2–4 orders of magnitude too coarse for a
   pipeline corridor.** A 20 m × 20 m leak patch is 0.04 % of a 1 km Sentinel-1
   soil-moisture pixel and 0.012 % of a 9 km SMAP pixel. They are context
   layers, not detectors. **Grade A** (arithmetic).

7. **The strongest satellite liquid-leak result is supervised, urban, and
   water-network-specific:** 91.86 % leak-detection accuracy on 1,222 confirmed
   water-leak points using SAR-derived moisture plus InSAR closure phase
   (Yan et al., 2024). A second study reached 80 % with six ALOS-2 L-band
   images (Ali et al., 2025). Neither is a blind, transferable detector, and
   neither has been replicated on an oil or gas pipeline. **Grade B/C.**

8. **For marine oil slicks, SAR is mature** — operational since ERS-1 (1991),
   used by EMSA CleanSeaNet. But it detects the *slick*, not the pipeline, and
   look-alike discrimination remains the hard part (Alpers et al., 2017).
   **Grade A** for slick detection; **Grade B** for source attribution.

9. **Polarimetry (Freeman–Durden, Cloude–Pottier) is proven for sea oil-slick
   characterisation in research and some operations, but not for onshore
   hydrocarbon leaks.** The one well-known marsh study found vegetation
   structural damage, not oil, dominated the polarimetric change (Ramsey et al.,
   2011). **Grade B** (marine), **Grade D** (onshore pipeline leak).

10. **No peer-reviewed SAR detection study of the Keystone spills was found.**
    The same is true for most named onshore pipeline spills. The literature is
    about *corridor geohazards* and *infrastructure failure*, not event
    forensics. This is a negative finding worth stating explicitly.

---

## 1. InSAR for leak-related ground deformation

### 1.1 What InSAR measures, and what it does not

InSAR compares the phase of two SAR acquisitions. The phase difference is
proportional to the change in range along the line of sight (LOS):

```
Δφ = (4π / λ) · Δr_LOS
```

One full 2π cycle corresponds to:

| Band | λ | 2π displacement |
|---|---|---|
| X-band (TerraSAR-X, COSMO-SkyMed, ICEYE, Capella) | ~3.1 cm | ~15.5 mm |
| C-band (Sentinel-1, RADARSAT-2, RCM) | ~5.6 cm | ~27.8 mm |
| L-band (ALOS-2, NISAR) | ~24 cm | ~120 mm |
| P-band (airborne, experimental) | ~70 cm | ~350 mm |

Three consequences:

- **LOS, not vertical.** Vertical displacement is `d_LOS / cos(θ)`, with
  Sentinel-1 incidence θ ≈ 30–46°, so the vertical-to-LOS factor is 1.15–1.44.
- **North–south is nearly invisible.** A near-polar orbit gives the LOS vector a
  small north component; InSAR is sensitive mainly to vertical and east–west
  motion. Full 3-D decomposition needs ascending + descending + external data.
- **L-band is less sensitive per unit phase.** A 10 mm displacement is 0.08
  cycles at L-band but 0.36 cycles at C-band. L-band trades displacement
  sensitivity for coherence and penetration.

Multi-temporal methods (PSInSAR, SBAS, MSBAS) fit a displacement history over
tens of acquisitions, which is how mm/yr precision is reached.

### 1.2 Missions

| Mission | Band (λ) | Nominal resolution | Repeat | Swath | Cost / access | Status | Notes for pipelines |
|---|---|---|---|---|---|---|---|
| **Sentinel-1A/C** | C (5.6 cm) | 5 × 20 m (IW SLC); 10 m GRD-H; 40 m GRD-M | 12 d per sat; **6 d** with two | 250 km (IW), 400 km (EW) | Free, open | Operational; 1A (2014), 1C (2024), 1D launched Nov 2025 | The workhorse. Free archive since 2014. C-band decorrelates in vegetation. |
| **NISAR** | L (24 cm) + S (9.4 cm) | 5–10 m; GUNW 80 m; GCOV 10/20/80 m | **12 d** | 240 km | Free, open | Launched 2025-07-30; provisional data 2026-07-20 | Best vegetation coherence; L-band ionosphere is a real problem; archive starts Oct 2025. |
| **ALOS-2 PALSAR-2** | L (23.8 cm) | 3/6/10 m stripmap; 1 × 3 m spotlight; 60/100 m ScanSAR | **14 d** | 50–70 km (stripmap); 490 km (ScanSAR) | JAXA, mostly paid/archive | Operational since 2014 | Long L-band archive; commercial tasking; good for vegetated corridors. |
| **ALOS-4** | L | ~3 m spotlight; 20 m stripmap | 14 d | 200 km | JAXA | Launched 2024 | Successor; archive still short. |
| **TerraSAR-X / TanDEM-X** | X (3.1 cm) | 1–3 m | **11 d** | 10–30 km | DLR, commercial | Operational since 2007 | Highest resolution; poor coherence under vegetation; excellent for above-ground infrastructure and urban. |
| **COSMO-SkyMed** | X (3.1 cm) | 1 m spotlight; 3–5 m HIMAGE | 16 d per sat; **~12 h** with 4-sat constellation | 10–40 km | ASI/e-GEOS, commercial | Operational since 2007 | Rapid tasking; expensive; good for emergency response. |
| **RADARSAT-2** | C (5.6 cm) | 1–100 m | **24 d** | 18–500 km | CSA/MDA, commercial | Operational since 2007 | Quad-pol capability; long repeat is a limitation. |
| **RADARSAT Constellation (RCM)** | C | 3–100 m | **4 d** | 350 km | CSA, commercial | Operational since 2019 | Best free-ish C-band revisit; 3 satellites. |
| **ICEYE** | X | 0.25–1 m | Hours–days (tasking) | 5–100 km | Commercial | Operational since 2018 | Sub-daily tasking; priced per scene. |
| **Capella** | X | 0.25–1 m | Hours–days (tasking) | 5–100 km | Commercial | Operational since 2018 | Same niche as ICEYE. |
| **SAOCOM 1A/1B** | L | 10–100 m | 16 d | 40–350 km | CONAE, registration | Operational since 2018/2020 | L-band alternative to ALOS-2. |

Sources: mission fact sheets and eoPortal (NISAR, ALOS-2); ESA SentiWiki
(Sentinel-1 products); mission operator pages. Sentinel-1 product classes are
NRT-3h, Fast-24h, and Off-line; the 6-day repeat assumes two satellites in the
same orbital plane.

**Choice for a pipeline corridor:**

- **Routine, free, multi-year:** Sentinel-1. Best archive, best value.
- **Vegetated corridor, L-band coherence:** NISAR (free, 12 d) or ALOS-2
  (long archive, paid).
- **Small or fast-moving feature, urban/rock:** TerraSAR-X or COSMO-SkyMed
  (1–3 m, but paid and sparse).
- **Emergency / rapid tasking:** ICEYE or Capella (hours–days, expensive).

### 1.3 Processing tools

| Tool | Type | What it does | Strengths | Limitations |
|---|---|---|---|---|
| **SNAP** (ESA) | GUI + CLI, free | Full Sentinel-1 workflow: calibration, coregistration, interferogram, deburst, unwrapping (SNAPHU), terrain correction; exports to StaMPS | Best-supported Sentinel-1 path; easy to learn | Memory-hungry; not ideal for large stacks; PS/SBAS need external tools |
| **ISCE2** (JPL/Caltech) | Python/C++, free | Interferometric processor for stripmap, TOPS, spotlight; produces wrapped/unwrapped products | Research-grade; supports many sensors; works with MintPy | Steep learning curve; TOPS burst handling is fiddly |
| **MintPy** | Python, free | Time-series inversion from ISCE/HyP3 products: SBAS, PS, network inversion, tropospheric correction, velocity | Excellent for stacks; well documented; reproducible | Needs a prepared stack; not a raw processor |
| **GMTSAR** | C/shell, free | InSAR + SBAS; classic and well-tested | Fast; good for stripmap; mature SBAS | GMT dependency; less friendly for Sentinel-1 TOPS |
| **Doris** (TU Delft) | C++, free | Differential InSAR, coregistration, unwrapping | Historically important; used in ESA production | Less actively developed; documentation dated |
| **StaMPS** | MATLAB/C++, free | Persistent Scatterer (PS) and SBAS-like processing | Strong PS implementation; widely cited | MATLAB licence; slow on large stacks |
| **SNAPHU** | C, free | Statistical phase unwrapping | Standard; robust | Can fail in low-coherence areas |
| **HyP3** (ASF) | Cloud service, free | On-demand Sentinel-1 interferograms, unwrapped, coherence, displacement | No local processing; ideal for a hackathon | Fixed parameters; 20–80 m products; quota |
| **LiCSAR / LiCSBAS** | Automated + Python | COMET's automated Sentinel-1 interferograms and time-series | Global, standardized, free | 0.05° frames; limited customization |
| **ARIA** (JPL) | Cloud/products | GUNW products, displacement, coherence | Standardized, free | 90 m; limited sensors |
| **GAMMA** | Commercial | Full InSAR/PS/SBAS suite | Industrial strength; used by commercial monitoring firms | Expensive licence |
| **SARPROZ** | Commercial | PS/SBAS, polarimetry, tomography | Strong for urban/structural | Expensive; Windows-centric |

**SBAS vs PSInSAR — the practical difference:**

- **PSInSAR** selects persistent scatterers (buildings, rock, bare ground) that
  remain coherent over years. Precision is high (1–2 mm/yr in ideal cases) but
  point density collapses over vegetation, farmland, and disturbed ground.
- **SBAS** uses many short-baseline interferograms and distributed scatterers.
  Coverage is much denser in natural terrain; precision is lower and results are
  smoother.
- **MSBAS** combines ascending and descending geometries to resolve vertical and
  east–west components.

The best pipeline-specific comparison is Bayramov et al. (2020), over 70 km of
the Baku–Tbilisi–Ceyhan and South Caucasus pipelines in Azerbaijan
(Sentinel-1, 2018–2019):

| Metric | PSInSAR | SBAS |
|---|---|---|
| Velocity range, KP21–31 | −46.07 to +33.46 mm/yr | −12.24 to +8.23 mm/yr |
| Velocity range, KP46–54 | −46.09 to +22.24 mm/yr | −21.65 to +5.1 mm/yr |
| Mean velocity (one section) | −1.36 mm/yr | −2.05 mm/yr |
| Standard deviation | 2.79–4.32 mm/yr | 2.62 mm/yr |
| Coverage along buried pipeline | Sparse, noisy | Continuous |
| SBAS vs GPS | — | R = 0.94, RMSE 1.51 mm (KP28+300); R = 0.90, RMSE 2.51 mm (KP52+500) |
| PS vs SBAS | — | R = 0.79–0.92, RMSE 4.9–6 mm |

**Conclusion:** along buried pipelines, SBAS gave more complete and less
dispersed coverage; PS was noisier and sparser. The 4.9–6 mm PS–SBAS difference
is itself a realistic uncertainty floor for pipeline work. **Grade B.**

### 1.4 Documented deformation magnitudes

These are the numbers to calibrate expectations against. None is a small
pipeline leak; all are geohazards, injection/production, or infrastructure
failure.

| Site / process | Sensor / method | Period | Magnitude | Source | Relevance |
|---|---|---|---|---|---|
| Baku–Tbilisi–Ceyhan & South Caucasus pipelines, Azerbaijan | Sentinel-1 PS/SBAS | 2018–2019 | PS −46 to +33 mm/yr; SBAS −12 to +8 mm/yr; means −1.4 to −2.7 mm/yr | Bayramov et al. 2020 | Corridor geohazard; tectonic + agricultural subsidence |
| Belridge oil field, California | RADARSAT-1/2, multi-satellite | 2001–2012 | Up to **80 cm/yr**; 3.92 m total; 3 m resolution; ±1 mm precision claimed | Henschel et al. 2014 | Extreme reservoir compaction; pipeline crossing |
| Karamay oil field, China | Sentinel-1 MSBAS, 32 asc + 34 desc | 2017–2018 | **160 mm/yr uplift**, 65 mm/yr horizontal | Yang et al. 2019 | Injection/production; not leak |
| Athabasca oil sands, Alberta (SAGD) | InSAR + reservoir model | ~2007–2013 | **1–4 cm/yr heave** above injectors; wellhead uplift | Pearse et al. 2014 | Steam injection; heave analogue |
| Norilsk, Russia (oil tank collapse, 29 May 2020) | Sentinel-1 SBAS | 2018–2020 | Mean **−30.8 mm/yr**; plant site ~−30 mm/yr; NW town −100 to −150 mm/yr | Zhang et al. 2022 | Permafrost failure; 21,000 t diesel spill |
| Arctic Alaska permafrost | Sentinel-1 SBAS + ICESat-2 | 2017–2022 | Seasonal subsidence **20–60 mm**; RMSE < 7 mm | Sadeghi Chorsi et al. 2024 | Thaw settlement; pipeline burial analogue |
| West Line II gas pipeline, Jiangxi, China | Sentinel-1A SBAS, 48 images | ~2020–2025 | **−19.5 to +19.1 mm/yr**; most within ±10 mm/yr; 121 candidates → 100 retained → 78 field-confirmed | Gao et al. 2026 | Operational geohazard screening |
| Permian Basin, Texas (Crane County) | Sentinel-1 InSAR | 2021–2024 | **53 cm uplift** Jan 2021–Oct 2023; **10 cm subsidence** Nov 2023–Sep 2024; well blowout | Zebker et al. 2025 | Well leakage analogue |
| Permian Basin, Texas (Andrews County) | Sentinel-1 InSAR | ~2017–2024 | **10 cm/yr uplift** from injection | Zebker et al. 2025 | Injection; induced seismicity |
| Permian Basin, New Mexico/Texas | Sentinel-1 InSAR | ~2017–2023 | **20 cm/yr uplift**; Jan 2022 blowout **3 cm subsidence in 2 weeks**; >3 MPa excess pressure | Karanam et al. 2024 | Closest leak analogue |
| New Mexico, casing breach | InSAR + Bayesian inversion | ~2017–2022 | Uplift consistent with shallow injection at breach depth | Graves et al. 2023 | Casing/seal failure analogue |
| Gauteng, South Africa, dolomite sinkhole | TerraSAR-X DInSAR, 20 stripmap | 1 year | **50 mm in 55 days**; features 40–100 m diameter; water pipeline ruptured 6 months later; **7 sinkhole events had no detectable deformation** | Theron et al. 2017 | Sinkhole precursor; important negative result |
| Bayou Corne, Louisiana, salt cavern collapse | UAVSAR | 2012 | Precursory movement reported at least 30 days before collapse | Jones & Blom 2014 (as cited in prior review) | Sinkhole analogue; verify before citing |
| In Salah, Algeria, CO2 injection | InSAR | 2004–2010 | cm-scale cumulative uplift above injectors | Rutqvist et al. 2010; Vasco et al. 2010 | Deep injection analogue; not a leak |

**What this table says:** InSAR reliably sees **cm/yr to m/yr** processes. A
small leak that produces **mm/yr** is at the edge of detectability and requires
a long, coherent stack. A leak that produces **cm in weeks** (blowout, erosion
void, sinkhole precursor) is detectable if the surface is coherent and the
acquisition cadence catches it.

### 1.5 What a leak actually does mechanically

This is where the literature is thin. A leak is a subsurface flow event; its
surface expression depends on the fluid and the soil.

| Leak type | Primary mechanism | Surface observable | Expected magnitude | Evidence |
|---|---|---|---|---|
| **Water / sewer** | Exfiltration, internal erosion, void growth | Local subsidence, sinkhole; soil moisture increase | mm–cm over weeks–months; collapse can be metres | **B** (Yan 2024; Theron 2017; CFD-DEM studies) |
| **Oil / hydrocarbon** | Dielectric change; vegetation stress; little deformation unless erosion | Backscatter decrease; NDVI/NDMI drop; maybe no deformation | 1–5 dB (theoretical); cm-scale only if erosion | **C/D** (Ahmadian 2013; Abdelgwad 2016; no satellite demo) |
| **Natural gas** | Drying, cooling (Joule–Thomson), vegetation stress; no direct SAR signature | Backscatter decrease; possible frost heave; methane detected optically | <1–2 dB; mm–cm heave (speculative) | **D** for SAR; **A** for optical methane |
| **CO2** | Pressure, vegetation stress, possible leakage | InSAR if pressure changes; optical/thermal for vegetation | mm–cm | **C** (CCS analogues) |
| **Brine / saltwater** | Increases conductivity and ε; dissolution in salt karst | Backscatter increase; subsidence | dB; cm–dm | **C** (salt mining InSAR) |

**Key physical point:** a leak does not create a "leak-shaped" deformation
source. It creates a *pressure* or *erosion* source whose surface expression is
governed by soil mechanics. The same surface signal could come from a leaking
pipe, a leaking well, a bad casing, a natural sinkhole, or groundwater
withdrawal. InSAR detects the *consequence*, not the cause.

### 1.6 Realistic detection limits

| Observable | Method | Documented / derived threshold | Conditions | Source |
|---|---|---|---|---|
| Multi-year vertical velocity | PS/SBAS | **8–10 mm/yr** vs GNSS; **8 mm/yr** vs levelling; **4–6 mm/yr** PS–SBAS | 2 years Sentinel-1, good coherence | Cigna et al. 2021 (A) |
| Multi-year velocity, ideal PS | PS | **1–2 mm/yr** precision | Urban/rock, long stack | Crosetto et al. 2016 (B) |
| Single-pair displacement | DInSAR | **~10–20 mm** | Atmosphere-limited | Zebker 2021 (A) |
| Transient event between acquisitions | DInSAR | **>1–2 cm** to be unambiguous | Good coherence | Derived from Zebker 2021 |
| Sinkhole precursor | DInSAR | **50 mm / 55 days** detected; **7/10 events missed** | X-band, urban dolomite | Theron et al. 2017 (B) |
| Spatial resolution | — | 5 × 20 m (S1 IW SLC); 3–10 m (ALOS-2); 1–3 m (X-band); 80 m (NISAR GUNW) | — | Mission specs |
| Temporal cadence | — | 6–12 d (S1); 12 d (NISAR); 14 d (ALOS-2); 11 d (TSX); 24 d (RADARSAT-2); 4 d (RCM); hours–days (ICEYE/Capella) | — | Mission specs |

**Important nuance — accuracy vs precision vs detection threshold:**

- **Precision** is repeatability (how similar two estimates are): 4–6 mm/yr
  between PS and SBAS.
- **Accuracy** is closeness to truth: 8–10 mm/yr against GNSS.
- **Detection threshold** is the smallest signal that rises above noise for a
  given stack; it improves with the number of acquisitions, coherence, and
  atmospheric correction.
- A **10 mm/yr** leak signal in a 2-year Sentinel-1 stack is at the edge of the
  noise; a **20–30 mm/yr** signal is robust; a **50 mm** transient in 2 months is
  robust if coherence holds.

**Why "mm/yr" claims need care:** the 1 mm/yr figures in vendor marketing come
from ideal PS stacks (many years, thousands of points, stable bedrock). For a
pipeline corridor crossing farmland, forest, or seasonally frozen ground, the
realistic number is the Cigna 8–10 mm/yr, and often worse.

---

## 2. Amplitude / backscatter change detection

### 2.1 The dielectric physics

Radar backscatter from soil is controlled by the **complex dielectric
constant** ε = ε′ − jε″. At microwave frequencies:

| Material | ε′ (relative) |
|---|---|
| Air | 1 |
| Dry soil | ~3–5 |
| Diesel / crude oil | ~2–3 |
| Liquid water | ~80 |

A small increase in volumetric water content produces a large increase in the
mixture ε′ because water dominates the mixture. That raises the Fresnel
reflection coefficient and therefore σ⁰. The reverse holds for oil: oil
displaces water in the pore space, lowering ε′ and σ⁰.

**First-order calculation (derived, smooth surface, normal incidence):**

```
R = |(√ε − 1) / (√ε + 1)|²
ε = 20 (moist soil): R = 0.403
ε = 4  (dry/oily soil): R = 0.111
ΔR = 10 log10(0.403 / 0.111) = 5.6 dB
```

So a wetting/drying or water/oil displacement can plausibly produce **~5 dB**
on a smooth bare surface. This is an upper bound: real surfaces are rough,
vegetation-covered, and viewed at 30–45°, which reduces the contrast.

**Penetration depth:**

| Band | Typical soil penetration | Source |
|---|---|---|
| C-band (5.6 cm) | ~1–2 cm (wet soil); ~2–5 cm (dry) | Ulaby et al. 1986; El Hajj et al. 2019 |
| L-band (24 cm) | ~5–10 cm (wet); ~10–20 cm (dry) | El Hajj et al. 2019; NISAR docs |
| P-band (70 cm) | **5–35 cm**, median 24.5–27 cm | Fluhrer et al. 2022 |

The pipe at 0.9–1.8 m depth is far below all of these. **The satellite sees the
soil above the pipe, not the pipe.** Even L-band does not reach a typical
buried transmission line.

### 2.2 Measured sensitivity to soil moisture

The best-controlled C- vs L-band comparison is El Hajj et al. (2019), using
simultaneous ALOS-2 and Sentinel-1 data over wheat, maize, and grassland in
Tunisia:

| Cover | Band / polarization | Sensitivity |
|---|---|---|
| Wheat & grassland, NDVI < 0.7 | **L-band HH** | **0.27 dB / vol.%** |
| Wheat & grassland, NDVI < 0.7 | **C-band VV and VH** | **0.12 dB / vol.%** |
| Wheat & grassland, NDVI > 0.7 | L-band HH | 0.19 dB / vol.% |
| Wheat & grassland, NDVI > 0.7 | C-band | **insensitive** |
| Maize, NDVI > 0.7 | C-band VV | penetrates via multiple scattering; still sensitive |

**What this means for a leak:**

- A **5 vol.%** moisture increase (a realistic wet patch) gives **~0.6 dB**
  (C-band) or **~1.4 dB** (L-band) over bare/low vegetation.
- A **10 vol.%** increase gives **~1.2 dB** (C) or **~2.7 dB** (L).
- A **20 vol.%** increase gives **~2.4 dB** (C) or **~5.4 dB** (L).

But these are **bare-soil** numbers. Under closed canopy (NDVI > 0.7), C-band
sees only the canopy and is effectively blind to surface moisture; L-band still
penetrates but at reduced sensitivity.

### 2.3 Speckle: the real limit on change detection

SAR intensity is affected by speckle. For `L` independent looks, the standard
deviation of the intensity in dB is approximately:

```
σ_dB ≈ 4.34 / √L
```

**Derived examples (standard speckle statistics):**

| Product | Looks (approx.) | σ_dB | 3σ detection threshold | Effective resolution for 1 dB at 3σ |
|---|---|---|---|---|
| Sentinel-1 IW SLC | 1 | 4.3 dB | 13 dB | ~170 looks → >100 m |
| Sentinel-1 IW GRD-H (10 m) | 5 | 1.9 dB | 5.8 dB | ~34 pixels → ~58 m |
| Sentinel-1 IW GRD-M (40 m) | ~484 | 0.2 dB | 0.6 dB | pixel-level (40 m) |
| NISAR GCOV 20 m | ~4–16 (mode-dependent) | 1.1–2.2 dB | 3.3–6.6 dB | 30–100 m |

**The trade-off is unavoidable:** radiometric precision comes from averaging,
and averaging costs spatial resolution. A 1 dB moisture anomaly cannot be
detected at 10 m from a single Sentinel-1 look; it can be detected at ~40–60 m
after multi-looking, or as a time-series anomaly against a baseline.

### 2.4 Vegetation effects

- **C-band** penetrates only the top of the canopy. At NDVI > 0.7 it is
  insensitive to surface moisture (El Hajj et al. 2019). Crops, pasture, and
  forest mask the leak.
- **L-band** penetrates further; it retains sensitivity at NDVI > 0.7 (0.19
  dB/vol.% in El Hajj et al. 2019). This is the main reason L-band is preferred
  for vegetated corridors.
- **X-band** is surface/canopy-top only; it decorrelates fastest and is best for
  urban/rock/bare surfaces.
- **Vegetation structure changes** (growth, harvest, ploughing) produce larger
  σ⁰ changes than moisture. Any operational detector must use a seasonal
  baseline, not a fixed threshold.

### 2.5 Oil contamination on land

Laboratory work confirms that hydrocarbon contamination lowers soil ε′ and
backscatter at microwave frequencies:

- Ahmadian et al. (2013) measured permittivity and backscattering coefficient of
  diesel-contaminated soil at C-band (5.3 GHz) across contamination levels and
  incidence angles (10–80°). The paper is a measurement/simulation study, not a
  satellite detection demonstration.
- Abdelgwad & Said (2016) measured complex permittivity of lubricant-oil-
  contaminated sandy soil from 500 MHz to 4 GHz, confirming the dielectric
  contrast.
- Abdelgwad & Said (2017) designed an L-band GPR antenna explicitly for
  detecting soil contamination from underground oil pipeline leaks — a
  ground-based, not satellite, method.

**The gap:** there is no peer-reviewed satellite demonstration of detecting an
onshore oil pipeline leak from its dielectric signature. The physics is
plausible, the magnitudes are small (a few dB at best), and vegetation/roughness
confound the signal. Treat this as **Grade D** for satellite leak detection.

### 2.6 What the leak-detection studies actually show

**Yan et al. (2024), IEEE JSTARS** — the strongest liquid-leak result:

- Inputs: SAR-derived moisture content + InSAR closure phase.
- Classifier: PCA + SVM (interpretable).
- Training: **1,222 confirmed leak points and 1,206 non-leak points** in Beijing
  and Tianjin, China.
- Results: **91.86 %** leak-detection accuracy in Beijing's Fifth Ring Road;
  **88.10 %** non-leak-detection accuracy in Huizhou, Guangdong.
- Caveats: supervised, urban water/sewer network, abundant coherent scatterers,
  known candidate points. Not a blind detector; not tested on oil/gas.

**Ali et al. (2025), ISPRS Archives** — L-band, Hong Kong:

- Six dual-pol ALOS-2 L-band images (HH/VV) + Hong Kong Water Supplies
  Department leak records.
- Features: GLCM texture + backscatter; stacking ensemble.
- Result: **80 % accuracy**.
- Caveats: data imbalance, no physical leak features, small sample. The authors
  explicitly list these as unresolved.

**Peng et al. (2026), Int. J. Applied Earth Obs.** — controlled L-band
experiment:

- L-band Mini-SAR in an anechoic chamber, asphalt layer.
- Subsurface echoes detectable through **at least 9 cm of asphalt**; modeling
  suggests >30 cm with more power/aperture.
- Interferometric phase, coherence, and closure phase respond to
  infiltration-induced subsurface moisture changes.
- Relevance: supports the physical basis for L-band closure-phase leak
  detection in paved urban settings; not a satellite demonstration.

**Ramsey et al. (2011), Remote Sensing** — the cautionary marsh study:

- UAVSAR L-band, Barataria Bay, Louisiana, before/after Deepwater Horizon.
- Freeman–Durden and Cloude–Pottier decompositions highlighted nearshore
  changes, but the dominant signal was **structural damage of shoreline marsh
  vegetation**, not oil.
- The authors conclude that "multiple factors prevent unambiguous determination
  of whether UAVSAR detected oil in interior marshes."

### 2.7 Realistic magnitudes: a summary

| Change | C-band σ⁰ | L-band σ⁰ | Detectability |
|---|---|---|---|
| 5 vol.% moisture increase, bare soil | ~0.6 dB | ~1.4 dB | Marginal single-pair; detectable in a time-series baseline |
| 10 vol.% moisture increase, bare soil | ~1.2 dB | ~2.7 dB | Detectable at 40–60 m after multi-looking |
| 20 vol.% moisture increase, bare soil | ~2.4 dB | ~5.4 dB | Detectable, but heavy rain does the same |
| Oil displacement of water, smooth soil | ~5 dB (theoretical upper bound) | ~5 dB | Plausible but unproven; roughness/vegetation confound |
| Freeze/thaw transition | 3–6 dB drop | 3–6 dB drop | Major false-alarm source |
| Ploughing / harvest | 3–10 dB | 3–10 dB | Major false-alarm source |

**The dominant confounders are rainfall, freeze/thaw, and agriculture — not
sensor noise.** Any detector must be conditioned on meteorology and land
management.

---

## 3. SAR + soil-moisture products: the scale problem

### 3.1 Product resolutions and accuracies

| Product | Native resolution | Accuracy (documented) | Source |
|---|---|---|---|
| **SMAP L3** | 36 km | ubRMSE < 0.04 m³/m³ (mission requirement) | Colliander et al. 2022 |
| **SMAP L3 enhanced** | 9 km | ~0.04–0.056 m³/m³ | Colliander et al. 2022; El Hajj et al. 2018 |
| **SMAP/Sentinel-1 L2** | 3 km / 1 km | lower accuracy than SMAP 9 km in validation | El Hajj et al. 2018 |
| **SMOS** | 25–50 km | ubRMSD ~5.9 vol.% | El Hajj et al. 2018 |
| **ASCAT** | 25 km / 12.5 km; 1 km downscaled | ubRMSD ~5.6 vol.% (combined SMAP/ASCAT/S1 average) | El Hajj et al. 2018 |
| **Sentinel-1 SSM** | **1 km** (operational product); 100 m (research); 20 m native | good over plains/agriculture; poor over forest/topography | Bauer-Marschallinger et al. 2019 |
| **NISAR SME2** | 200 m | not yet validated at scale | NISAR product docs |
| **ESA CCI** | 0.25° (~25 km) | multi-sensor merge | ESA CCI |

**Key accuracy point:** even the best satellite soil-moisture products have
**ubRMSE ~0.04–0.06 m³/m³ (4–6 vol.%)**. A leak wetting a patch by 5 vol.% is
at the product's noise level even before the spatial dilution problem.

### 3.2 The scale arithmetic

| Product pixel | Area | 20 m × 20 m leak patch | Fraction of pixel |
|---|---|---|---|
| 20 m (S1 native) | 400 m² | 400 m² | **100 %** |
| 100 m (S1 research) | 10,000 m² | 400 m² | 4 % |
| 1 km (S1 SSM) | 1,000,000 m² | 400 m² | **0.04 %** |
| 9 km (SMAP) | 81,000,000 m² | 400 m² | **0.0005 %** |
| 36 km (SMAP L3) | 1,296,000,000 m² | 400 m² | **0.00003 %** |

A 1 km-long, 20 m-wide pipeline corridor is 20,000 m² — **2 %** of a 1 km pixel,
**0.025 %** of a 9 km pixel. The leak's moisture signal is diluted by 50× to
4,000× before it reaches the product.

**Conclusion:** coarse soil-moisture products cannot detect a pipeline leak.
They can:

- provide regional antecedent wetness (to normalize backscatter),
- flag rainfall that would cause false positives,
- support a hydrological interpretation,
- characterize drought/flood context.

They cannot be the detector. **Grade A** (arithmetic).

### 3.3 Why the products are coarse

Passive microwave radiometers measure brightness temperature at L-band
(1.4 GHz, 21 cm). The antenna size needed for 10 km resolution from orbit is
~6–9 m; SMAP uses a 6 m deployable mesh antenna and still gets 36–40 km.
SMOS uses a synthetic aperture radiometer for ~35–50 km. Resolution is
physics-limited, not a data-processing choice. Downscaling to 1–9 km is
**model-based** (thermal inertia, vegetation index, SAR backscatter), not a
direct measurement, and inherits the model's assumptions.

### 3.4 The only corridor-scale SAR moisture observable

Sentinel-1 native backscatter at 10–20 m is the only spaceborne SAR measurement
that can resolve a corridor. But:

- it is **relative**, not absolute (change detection against a baseline),
- it is **surface-only** (top 1–5 cm at C-band),
- it is **speckle-limited** (see §2.3),
- it is **confounded** by roughness, vegetation, and freeze/thaw.

That is why operational leak detection uses **anomalies against a seasonal
baseline**, not absolute soil moisture.

---

## 4. Polarimetric SAR

### 4.1 The decompositions

**Freeman–Durden (1998)** decomposes the covariance matrix into three physical
mechanisms:

```
[C] = P_s [C]_surface + P_d [C]_double-bounce + P_v [C]_volume
```

- **Surface (P_s):** Bragg scattering from bare soil, water, roads.
- **Double-bounce (P_d):** ground–trunk, ground–wall, inundated vegetation.
- **Volume (P_v):** vegetation canopy.

**Cloude–Pottier (1997)** eigen-decomposes the coherency matrix into entropy
`H` (0–1), anisotropy `A`, and mean scattering angle `α` (0–90°):

| Scattering | H | α |
|---|---|---|
| Surface | low | 0–20° |
| Volume | high | ~45° |
| Double-bounce | high | >45° |

**Yamaguchi et al. (2005)** adds a fourth (helix) component for
non-reflection-symmetric targets.

### 4.2 What a leak would change

- **Wetting** increases surface scattering (P_s), generally lowering H and α.
- **Oil contamination** lowers ε, weakening surface scattering; if it kills
  vegetation, P_v falls and the pixel may shift toward surface or double-bounce.
- **Erosion/void** changes roughness and geometry; may increase double-bounce
  from the cavity.
- **Marine oil slicks** damp Bragg waves, reducing σ⁰ and changing the
  polarimetric pedestal; the signal is a departure from slick-free Bragg
  scattering.

The problem: **vegetation structure and surface roughness produce larger
polarimetric changes than moisture or oil.** A pixel can move from volume to
surface because it was harvested, not because it leaked.

### 4.3 Marine oil slicks — the proven application

- Migliaccio et al. (2015) review the physical processing approach: oil slicks
  depart from Bragg scattering, and polarimetric features can distinguish oil
  from a broad class of look-alikes in an unsupervised way. The approach is
  demonstrated at L-, C-, and X-band, and in dual, full, and compact modes.
- Zhang et al. (2017) compared fully and compact polarimetric classifications on
  the 2011 Norwegian oil-on-water experiment; the π/2 compact mode performed
  best among dual/compact modes, and four features were sufficient for most
  classifications.
- Quigley et al. (2023) showed that the commonly used "damping ratio" method
  gives inconsistent values for the same scene; three alternative methods were
  tested, and the histogram method was most consistent. Thickness retrieval
  remains research-grade.
- **Alpers et al. (2017)** is the essential caution: many oil-spill algorithms
  are trained on subjective interpretations, not on-site validation; the claimed
  high success rates are often not reproducible; and polarimetric H/A/α is not
  necessarily better than single-pol for oil/biogenic discrimination.

**Verdict:** polarimetry is **Grade A/B** for marine slick detection and
characterisation; it is not a pipeline leak detector except where the pipeline
discharges into water.

### 4.4 Onshore hydrocarbon detection — the evidence gap

- **Ramsey et al. (2011)** is the best-known land study. UAVSAR L-band over
  Barataria Bay marsh before/after Deepwater Horizon. Freeman–Durden and
  Cloude–Pottier decompositions showed a change from surface/volume to double/
  even bounce, consistent with oil exposure — but also consistent with marsh
  structural damage. The authors explicitly could not unambiguously attribute
  the signal to oil.
- **Ahmadian et al. (2013)** and **Abdelgwad & Said (2016)** establish the
  dielectric contrast in the laboratory.
- **No satellite study** demonstrates onshore pipeline oil-leak detection via
  polarimetry. The signal is too weak relative to vegetation/roughness, and
  quad-pol coverage is limited.

### 4.5 The dual-pol reality

- Sentinel-1 is **dual-pol** (VV+VH or HH+HV) in IW mode.
- NISAR is mostly **dual-pol**; quad-pol only in some modes/regions.
- ALOS-2 offers quad-pol in some modes, but coverage is sparse and data are
  paid.
- RADARSAT-2 offers quad-pol, but 24-day repeat.

**Do not design around Freeman–Durden unless you have confirmed a quad-pol
acquisition over your site.** With dual-pol, the useful features are:

- **HV/VV** (or HV/HH): vegetation structure; insensitive to incidence angle.
- **VV** alone: surface moisture/roughness.
- **Co-pol correlation** (if HH and VV available): surface vs volume.

---

## 5. Case studies with quantitative results

### 5.1 InSAR pipeline geohazards

**Azerbaijan — Baku–Tbilisi–Ceyhan and South Caucasus pipelines (Bayramov et
al., 2020).** 70 km corridor crossing two active seismic faults. Sentinel-1
PS-InSAR and SBAS over 2018–2019. Continuous subsidence from KP 13–70; uplift
from KP 0–13. PS velocities −46 to +33 mm/yr; SBAS −12 to +8 mm/yr. SBAS vs GPS:
R = 0.94, RMSE 1.51 mm; R = 0.90, RMSE 2.51 mm. PS vs SBAS: RMSE 4.9–6 mm. The
authors recommend SBAS for buried pipeline corridors because of coverage and
lower dispersion. **Grade B.**

**Belridge oil field, California (Henschel et al., 2014).** 12 years of
multi-satellite InSAR (RADARSAT-1/2). Deformation up to **80 cm/yr**, maximum
total **3.92 m**, 3 m ground resolution, ±1 mm precision claimed, 2-day revisit
from the RADARSAT constellation. Validated with GNSS. This is an extreme
reservoir-compaction case, not a leak, but it shows what dense stacks can
resolve. **Grade B.**

**Karamay oil field, China (Yang et al., 2019).** 32 ascending + 34 descending
Sentinel-1 scenes, MSBAS 2-D decomposition. Maximum uplift **160 mm/yr**,
horizontal **65 mm/yr**, modeled with a dislocation source. **Grade B.**

**Athabasca oil sands, Alberta (Pearse et al., 2014).** Persistent heave of
**1–4 cm/yr** above SAGD injector wells, correlated with steam injection; also
localized wellhead uplift. Reservoir modeling explains it via porous flow and
thermal expansion. **Grade B.** This is the best "heave" analogue for a
pressurised-fluid leak, but the source is injection, not leakage.

**West Line II gas pipeline, Jiangxi, China (Gao et al., 2026).** 48 Sentinel-1A
images, SBAS + GIS + optical validation. Deformation **−19.5 to +19.1 mm/yr**,
most within ±10 mm/yr. 121 candidate disaster points → 100 retained after
excluding 21 human-interference points → **78 field-confirmed** geohazards
(landslides, collapses, slope water damage). **Grade B.** This is the best
template for operational corridor screening.

**Ordos Basin, China (Yang et al., 2025).** DS-InSAR + failure-probability
matrix for large-scale oil/gas pipeline risk mapping. The paper is a framework,
not a leak detector; it integrates deformation, susceptibility, and
vulnerability. **Grade C.**

### 5.2 Permafrost and cold-region pipelines

**Norilsk, Russia (Zhang et al., 2022).** The 29 May 2020 oil tank collapse
spilled 21,000 t of diesel. SBAS-InSAR (Sentinel-1, Aug 2018–Dec 2020) showed
mean subsidence **−30.8 mm/yr**; the plant site ~**−30 mm/yr**; the northwestern
town **−100 to −150 mm/yr**. The precursor condition was summer thaw on slopes
>15° after 2–3 consecutive years of +2 °C/yr warming. **Grade B.** This is a
permafrost infrastructure failure, not a pipeline leak, but it is the canonical
"precursor detected before spill" case.

**Arctic Alaska (Sadeghi Chorsi et al., 2024).** Sentinel-1 SBAS + ICESat-2,
2017–2022. Seasonal subsidence **20–60 mm**, linear-fit RMSE **<7 mm**. **Grade
B.** This is the magnitude to expect for thaw settlement along a buried
pipeline.

**China–Russia crude oil pipeline, Da Xing'anling (Wang et al., 2022).** SBAS-
InSAR + ground surveys in discontinuous permafrost. The study resolves
differential freeze–thaw deformation along the route. **Grade B/C** (preprint;
numbers not extracted here).

### 5.3 Sinkholes and urban water leaks

**Gauteng, South Africa (Theron et al., 2017).** 20 TerraSAR-X stripmap
acquisitions over one year, dolomitic terrain. Three previously unknown
deformation features, 40–100 m diameter; maximum **50 mm over 55 days**. One was
confirmed by field investigation; a water supply pipeline ruptured six months
after the initial observation. **However, seven sinkhole events occurred during
the observation period with no detectable deformation.** **Grade B.** This is
the single most important negative result in the sinkhole literature: not all
collapses have InSAR precursors.

**Beijing/Tianjin water network (Yan et al., 2024).** 1,222 confirmed leak
points + 1,206 non-leak points. PCA+SVM on SAR moisture + InSAR closure phase.
**91.86 %** leak detection in Beijing's Fifth Ring Road; **88.10 %** non-leak
detection in Huizhou. **Grade B** (supervised, urban, water/sewer).

**Hong Kong water network (Ali et al., 2025).** Six ALOS-2 L-band dual-pol
images + utility leak records; GLCM + backscatter + stacking ensemble. **80 %
accuracy.** **Grade C.** The authors flag data imbalance and missing physics.

### 5.4 Well leakage and blowouts — the closest analogue

**Crane County, Permian Basin (Zebker et al., 2025).** Sentinel-1 InSAR:
**53 cm of uplift** from January 2021 to October 2023, followed by **10 cm of
subsidence** from November 2023 to September 2024, associated with a well
blowout. In Andrews County, **10 cm/yr uplift** from injection. In Ward County,
leakage may occur in regions experiencing subsidence because production-induced
subsidence offsets injection-induced uplift. **Grade B.** This is the strongest
quantitative "leak seen from space" case, but it is a well, not a pipeline.

**Permian Basin blowout (Karanam et al., 2024).** Over-pressurized wastewater
aquifer produced **20 cm/yr uplift**; a January 2022 blowout produced **3 cm of
subsidence in two weeks**; modeled excess pressure >3 MPa. **Grade B.**

**New Mexico casing breach (Graves et al., 2023).** InSAR uplift over a well
with a casing breach; Bayesian inversion shows shallow injection at breach depth
is required to fit the data. **Grade B.** This is the cleanest demonstration
that InSAR can discriminate a shallow leak from a deep injection.

### 5.5 Marine pipeline failures

**Nord Stream, Baltic Sea (September 2022).** Four leaks from three pipelines.
Methane release estimates: **~220 ± 30 kt** (Jia et al., 2022); **443–486 kt**
(Nature Communications, 2025); **~465 kt** (Harris et al., 2025, Nature). The
leak diameter was estimated at **0.5–0.7 km** from Pléiades Neo imagery (Soldi
et al., 2023). **SAR's role:** surface surveillance, vessel monitoring, and
detection of the surface foam/turbulence; **the methane itself was quantified by
optical/atmospheric sensors** (Landsat 8, Sentinel-2B, TROPOMI, aircraft), not
by SAR. Dogniaux et al. (2024) documented the Landsat 8 and Sentinel-2B sea-foam
observations. **Grade A** for the event; **Grade B** for SAR's specific
contribution.

**Deepwater Horizon, Gulf of Mexico (2010).** The most-studied marine oil spill
in SAR history. UAVSAR L-band, Radarsat-2, Sentinel-1 (later), and airborne
SAR. Oil slicks are detected as dark patches; thickness and volume remain
uncertain. Ramsey et al. (2011) is the key marsh-impact study. **Grade A** for
slick mapping; **Grade C** for thickness/volume.

### 5.6 Negative findings

- **Keystone:** no peer-reviewed SAR detection study of the 2017, 2019, or 2022
  spills was found. The prior project review mentions "Keystone 2022"; that
  should be treated as unverified until a source is produced.
- **Most named onshore spills:** SAR literature is about corridor geohazards and
  infrastructure failure, not event forensics. The absence of studies is itself
  informative: small onshore leaks do not produce a reliable satellite SAR
  signature.
- **Gas pipeline leaks:** no InSAR demonstration. Methane is detected optically
  (Sentinel-5P, EMIT, GHGSat, Carbon Mapper), not by C/L-band SAR.

---

## 6. Practical constraints

### 6.1 Revisit frequency

| Mission | Repeat | Effective revisit with constellation | Comment |
|---|---|---|---|
| Sentinel-1 | 12 d | **6 d** (2 sats); ~4 d with 3 | Free; the backbone |
| NISAR | 12 d | 12 d | Free; L-band |
| ALOS-2 | 14 d | 14 d | L-band; paid |
| TerraSAR-X | 11 d | 11 d (1 sat); 1–3 d tasking at mid-latitudes | X-band; paid |
| COSMO-SkyMed | 16 d | **~12 h** (4 sats) | X-band; paid |
| RADARSAT-2 | 24 d | 24 d | C-band; paid |
| RCM | 4 d | 4 d | C-band; paid |
| ICEYE / Capella | tasking | hours–days | X-band; paid |

**A leak is a continuous process; a satellite is a sampling instrument.** A
6–12 day cadence will miss short-lived wet patches and fast sinkhole collapse.
The exception is a persistent leak, which can be detected as a recurring anomaly.

### 6.2 Resolution

- **Sentinel-1 IW:** 5 × 20 m SLC; 10 m GRD-H; 40 m GRD-M. A 20 m pipeline
  right-of-way is 1–2 pixels wide.
- **NISAR:** 5–10 m GCOV; 80 m GUNW. The 80 m deformation product is too coarse
  for a corridor; the 10 m GCOV is usable for backscatter/coherence.
- **ALOS-2:** 3–10 m stripmap; 1 × 3 m spotlight.
- **X-band:** 1–3 m (TSX/CSK); 0.25–1 m (ICEYE/Capella). Only at this scale can
  a single pipe or a small sinkhole be resolved.
- **Soil moisture products:** 1 km to 36 km — 2–4 orders of magnitude too coarse.

### 6.3 Temporal decorrelation

- **C-band:** coherence over crops falls below ~0.3 within one 6–12 day cycle
  during growth; over bare soil, rock, and urban it remains high for months.
- **L-band:** coherence survives weeks–months in low vegetation and forest;
  better through canopy, but ionospheric effects grow.
- **X-band:** decorrelates fastest in vegetation; best for urban/rock/bare
  surfaces and above-ground infrastructure.
- **Snow, ploughing, harvest, fire:** destroy coherence and produce backscatter
  changes that mimic leaks.
- **Global Sentinel-1 coherence dataset:** Kellndorfer et al. (2022) provides
  seasonal C-band coherence statistics for 2019–2020, useful for planning.

### 6.4 Atmospheric artifacts

- **Troposphere:** variable water vapour produces **~2 cm rms** phase error in a
  single interferogram, and can be several times larger; correction reduces it
  to ~2 cm, not to mm (Zebker, 2021). This is the dominant error for single-pair
  InSAR.
- **Stacking** reduces the temporal component; weather-model corrections
  (GACOS, ERA5) reduce the stratified component; neither is perfect.
- **Ionosphere:** at L-band, the ionospheric phase can be several cm to tens of
  cm, especially at low latitudes and high solar activity. Split-spectrum
  methods can mitigate it; it is a real disadvantage of L-band relative to
  C-band.
- **Orbit errors:** long-wavelength ramps; mitigated by network adjustment and
  GNSS ties.

### 6.5 Orbit geometry

- **LOS projection:** vertical = LOS / cos(θ); for Sentinel-1, factor 1.15–1.44.
- **Ascending vs descending:** needed to separate vertical and east–west;
  a single geometry mixes them.
- **North–south:** nearly invisible.
- **Layover/shadow:** in steep terrain (mountain pipelines), geometric
  distortions mask or distort the signal.
- **NISAR is left-looking:** different geometry from Sentinel-1 (right-looking);
  this affects joint analysis and change detection.

### 6.6 Cost

| Item | Cost |
|---|---|
| Sentinel-1 data | **Free** |
| NISAR data | **Free** |
| ALOS-2 | Free for some research/archive; commercial tasking paid |
| TerraSAR-X | DLR science proposal (free for funded science); commercial paid |
| COSMO-SkyMed | Commercial, paid |
| RADARSAT-2 / RCM | Commercial, paid |
| ICEYE / Capella | Commercial, paid per scene/area |
| SNAP, ISCE2, MintPy, GMTSAR, Doris, StaMPS, SNAPHU | **Free/open source** |
| GAMMA, SARPROZ | Commercial licences (tens of kUSD) |
| Cloud compute for a national corridor | Hundreds to thousands of USD/month |

**Commercial tasking is not publicly list-priced.** Industry practice is
per-scene or per-km² negotiation; budget figures are commonly in the high
hundreds to low thousands of USD per tasked scene. Treat this as an **estimate**,
not a published price. The free Sentinel-1/NISAR archive is the only realistic
basis for a sustained, large-area monitoring programme.

### 6.7 Latency

| Source | Latency |
|---|---|
| Sentinel-1 NRT-3h | ~3 hours after acquisition |
| Sentinel-1 Fast-24h | ~24 hours |
| Sentinel-1 Off-line | days–weeks |
| NISAR | hours–days (product dependent) |
| Commercial X-band | minutes–hours (tasking) |
| InSAR processing (local) | minutes–hours per interferogram; days for a large stack |
| Time-series update | days–weeks after a new acquisition |

**For leak response, SAR latency is not the bottleneck — revisit cadence and
signal strength are.** A leak that develops and is repaired between two
acquisitions is invisible.

### 6.8 Validation

- **Ground truth is scarce.** The best public datasets are PHMSA incident
  reports (US), utility leak records (municipal), and operator in-line
  inspection data (proprietary).
- **A detector without ground truth is a demo, not a measurement.** The Yan
  (2024) and Ali (2025) studies are credible precisely because they had
  confirmed leak/non-leak points.
- **Rainfall, freeze/thaw, and land management must be covariates**, not
  afterthoughts.

---

## 7. Proven vs speculative

| Claim | Grade | Evidence | Caveat |
|---|---|---|---|
| InSAR measures corridor ground motion at mm/yr precision | **A** | Cigna 2021; Bayramov 2020; Henschel 2014 | 8–10 mm/yr accuracy, not 1 mm/yr |
| InSAR detects landslides, subsidence, thaw settlement affecting pipelines | **A** | Guthrie 2018; Down 2020/2021; Gao 2026 | Needs coherent surface and a stack |
| InSAR detects sinkhole precursors | **B** | Theron 2017 | 7/10 events had no precursor |
| InSAR detects well/casing leakage | **B** | Zebker 2025; Karanam 2024; Graves 2023 | Wells, not pipelines |
| InSAR detects small pipeline leaks | **D** | No peer-reviewed demonstration | Requires leak-induced cm-scale deformation |
| SAR backscatter detects leak-induced soil moisture | **B/C** | Yan 2024; Ali 2025; El Hajj 2019 | Supervised, urban, water; not oil/gas |
| SAR backscatter detects oil contamination on land | **D** | Lab only (Ahmadian 2013; Abdelgwad 2016) | No satellite demonstration |
| Polarimetry detects marine oil slicks | **A/B** | Migliaccio 2015; Alpers 2017 | Look-alikes; thickness uncertain |
| Polarimetry detects onshore pipeline oil leaks | **D** | Ramsey 2011 (ambiguous) | Vegetation/roughness dominate |
| Soil-moisture products can detect pipeline leaks | **D** | Scale arithmetic | 2–4 orders too coarse |
| SAR detects gas leaks directly | **D** | No C/L-band methane sensitivity | Methane is optical/IR |
| SAR detects the Nord Stream leak | **B** | Soldi 2023; Dogniaux 2024 | Surface/foam/vessel surveillance; methane quantified optically |

---

## 8. Implications for a NISAR-based pipeline project

**What NISAR genuinely adds:**

- **L-band coherence through vegetation.** This is the strongest technical case
  for NISAR over Sentinel-1 in a pipeline corridor. C-band decorrelates in
  crops/forest within days; L-band survives the 12-day repeat.
- **Deeper penetration** (5–20 cm vs 1–5 cm), which better samples the soil
  layer a leak wets.
- **Free, global, 12-day coverage** with 5–10 m GCOV and 80 m GUNW.
- **Closure-phase potential.** The surface/subsurface interference term that
  makes closure phase non-zero is stronger at L-band; this is the most
  defensible "why NISAR" argument for a moisture/leak project.

**What NISAR does not add:**

- **No historical archive before October 2025.** Nord Stream 2022, Norilsk 2020,
  Keystone 2022 are out.
- **No operational leak-detection algorithm.** NISAR is a sensor, not a leak
  detector.
- **80 m GUNW is too coarse** for a 20 m corridor; use GCOV/GSLC at 10–20 m for
  backscatter/coherence, and GUNW only for regional deformation context.
- **L-band ionosphere** is a real noise source, especially at high latitude.
- **No validated SME2 soil moisture at scale**; 200 m is still 10× too coarse
  for a corridor.

**A defensible framing:**

> "We use NISAR L-band to detect and visualize corridor-scale surface change —
> moisture, coherence, and deformation — along a pipeline right-of-way, and we
> test those anomalies against known leak and geohazard records. We do not claim
> to detect the leak itself; we claim to detect its surface footprint and to
> rank candidate locations for field inspection."

That framing is honest, matches the challenge's "surface change" theme, and
avoids overstating SAR's capabilities.

---

## 9. Key references

### InSAR and pipelines

- Bayramov, E., Buchroithner, M. F., & Kada, M. (2020). Radar Remote Sensing to
  Supplement Pipeline Surveillance Programs through Measurements of Surface
  Deformations and Identification of Geohazard Risks. *Remote Sensing*, 12(23),
  3934. https://doi.org/10.3390/rs12233934
- Cigna, F., Esquivel Ramírez, R., & Tapete, D. (2021). Accuracy of Sentinel-1
  PSI and SBAS InSAR Displacement Velocities against GNSS and Geodetic Leveling
  Monitoring Data. *Remote Sensing*, 13(23), 4800.
  https://doi.org/10.3390/rs13234800
- Theron, A., Engelbrecht, J., Kemp, J., Kleynhans, W., & Turnbull, T. (2017).
  Detection of Sinkhole Precursors Through SAR Interferometry: Radar and
  Geological Considerations. *IEEE Geoscience and Remote Sensing Letters*,
  14(6), 871–875. https://doi.org/10.1109/LGRS.2017.2684905
- Henschel, M. D., Deschamps, B., Robert, G., & Gailing, R. (2014). Multi-
  Satellite InSAR Deformation Analysis for Pipeline Monitoring: Operational
  Application, Results and Validation in the Belridge Oil Field, 2001–2012.
  *International Pipeline Conference*, IPC2014-33665.
  https://doi.org/10.1115/IPC2014-33665
- Guthrie, R. H., Reid, E., Richmond, J., Ghuman, P., & Cormier, Y. (2018).
  InSAR and the Pipeline Geohazards Toolbox: Instructions for Use As of 2018.
  *International Pipeline Conference*, IPC2018-78571.
  https://doi.org/10.1115/IPC2018-78571
- Froese, C., van der Kooij, M., & Kosar, K. (2004). Advances in the Use of
  Spaceborne InSAR for Application to Pipeline Route Selection and Integrity
  Management. *International Pipeline Conference*, IPC2004-0013, 259–267.
  https://doi.org/10.1115/IPC2004-0013
- Singhroy, V. H., Li, J., Blais-Stevens, A., & Fobert, M. A. (2018). InSAR
  Monitoring of Pipeline Routes. *IGARSS 2018*, 212–215.
  https://doi.org/10.1109/IGARSS.2018.8517873
- Down, M. (2020). *PR-686-183908-R01 InSAR Monitoring of Pipeline Geohazards in
  Vegetated and Very Large Non-Vegetated Areas*. PRCI.
  https://doi.org/10.55274/r0011679
- Down, M. (2021). *PR686-203903-R02 Ongoing InSAR Geohazard Monitoring of
  Pipeline Right-of Ways in the Appalachian Mountains*. PRCI.
  https://doi.org/10.55274/r0012178
- Down, M., & Leighton, J. (2025). Pipeline Geohazard Detection Using Satellite
  InSAR. In *Wiley eBooks* (pp. 549–556).
  https://doi.org/10.1002/9781119909668.ch37
- Gao, M., Liang, J., Ai, J., Liu, Z., & Ren, X. (2026). Early Identification of
  Geological Hazards for Oil and Gas Pipelines Based on SBAS-InSAR and GIS.
  *Applied Sciences*, 16(11), 5701. https://doi.org/10.3390/app16115701
- Yang, Y., Liu, Y., Guo, Y., Shen, J., Xie, C., Zhang, N., Tian, B., Zhu, Y., &
  Mao, Y. (2025). An InSAR-Based Framework for Advanced Large-Scale Failure
  Probability Assessment of Oil and Gas Pipelines. *Remote Sensing*, 17(3), 504.
  https://doi.org/10.3390/rs17030504

### Deformation case studies

- Zhang, P., Chen, Y., Ran, Y., et al. (2022). Permafrost Early Deformation
  Signals before the Norilsk Oil Tank Collapse in Russia. *Remote Sensing*,
  14(19), 5036. https://doi.org/10.3390/rs14195036
- Pearse, J., Singhroy, V., Samsonov, S., & Li, J. (2014). Anomalous surface
  heave induced by enhanced oil recovery in northern Alberta: InSAR observations
  and numerical modeling. *Journal of Geophysical Research: Solid Earth*,
  119(8), 6630–6649. https://doi.org/10.1002/2013JB010885
- Yang, C., Zhang, D., Zhao, C., Han, B., & Sun, R. (2019). Ground Deformation
  Revealed by Sentinel-1 MSBAS-InSAR Time-Series over Karamay Oilfield, China.
  *Remote Sensing*, 11(17), 2027. https://doi.org/10.3390/rs11172027
- Zebker, M., Smye, K. M., Chen, J. A., & Hennings, P. (2025). Injection-Related
  Hazards in the Permian Basin as Characterized by Spaceborne InSAR and In Situ
  Measurements. *Geophysical Research Letters*.
  https://doi.org/10.1029/2025GL115231
- Karanam, V., Lu, Z., & Kim, J.-W. (2024). Investigation of Oil Well Blowouts
  Triggered by Wastewater Injection in the Permian Basin, USA. *Geophysical
  Research Letters*. https://doi.org/10.1029/2024GL109435
- Graves, E. J., Rinehart, A. J., Grapenthin, R., Angarita, M., & Grigg, J.
  (2023). InSAR-observed surface deformation in New Mexico's Permian Basin shows
  threats and opportunities presented by leaky injection wells. *Scientific
  Reports*, 13. https://doi.org/10.1038/s41598-023-42696-9
- Sadeghi Chorsi, T., Meyer, F. J., & Dixon, T. H. (2024). Toward long-term
  monitoring of regional permafrost thaw with satellite interferometric
  synthetic aperture radar. *The Cryosphere*, 18(8), 3723–3740.
  https://doi.org/10.5194/tc-18-3723-2024

### InSAR methods and errors

- Ferretti, A., Prati, C., & Rocca, F. (2001). Permanent scatterers in SAR
  interferometry. *IEEE Transactions on Geoscience and Remote Sensing*, 39(1),
  8–20. https://doi.org/10.1109/36.898661
- Berardino, P., Fornaro, G., Lanari, R., & Sansosti, E. (2002). A new algorithm
  for surface deformation monitoring based on small baseline differential SAR
  interferograms. *IEEE Transactions on Geoscience and Remote Sensing*, 40(11),
  2375–2383. https://doi.org/10.1109/TGRS.2002.803792
- Crosetto, M., Monserrat, O., Cuevas-González, M., Devanthéry, N., & Crippa, B.
  (2016). Persistent Scatterer Interferometry: A review. *ISPRS Journal of
  Photogrammetry and Remote Sensing*, 115, 78–89.
  https://doi.org/10.1016/j.isprsjprs.2015.10.011
- Massonnet, D., & Feigl, K. L. (1998). Radar interferometry and its application
  to changes in the Earth's surface. *Reviews of Geophysics*, 36(4), 441–500.
  https://doi.org/10.1029/97RG03139
- Zebker, H. A. (2021). Accuracy of a Model-Free Algorithm for Temporal InSAR
  Tropospheric Correction. *Remote Sensing*, 13(3), 409.
  https://doi.org/10.3390/rs13030409
- Sadeghi, Z., Wright, T., Hooper, A. J., & Jordan, C. J. (2021). Benchmarking
  and inter-comparison of Sentinel-1 InSAR velocities and time series. *Remote
  Sensing of Environment*, 256, 112306.
  https://doi.org/10.1016/j.rse.2021.112306
- Parizzi, A., Brcich, R. F., & De Zan, F. (2021). InSAR Performance for
  Large-Scale Deformation Measurement. *IEEE Transactions on Geoscience and
  Remote Sensing*, 59(10), 8510–8520.
  https://doi.org/10.1109/TGRS.2020.3039006
- Raspini, F., Caleca, F., Del Soldato, M., et al. (2022). Review of satellite
  radar interferometry for subsidence analysis. *Earth-Science Reviews*, 235,
  104239. https://doi.org/10.1016/j.earscirev.2022.104239

### Backscatter, soil moisture, and dielectrics

- Zwieback, S., Hensley, S., & Hajnsek, I. (2015). Assessment of soil moisture
  effects on L-band radar interferometry. *Remote Sensing of Environment*, 164,
  77–89. https://doi.org/10.1016/j.rse.2015.04.012
- El Hajj, M., Baghdadi, N. N., Bazzi, H., & Zribi, M. (2019). Penetration
  Analysis of SAR Signals in the C and L Bands for Wheat, Maize, and Grasslands.
  *Remote Sensing*, 11(1), 31. https://doi.org/10.3390/rs11010031
- Fluhrer, A., Jagdhuber, T., Tabatabaeenejad, A., et al. (2022). Remote Sensing
  of Complex Permittivity and Penetration Depth of Soils Using P-Band SAR
  Polarimetry. *Remote Sensing*, 14(12), 2755.
  https://doi.org/10.3390/rs14122755
- Bauer-Marschallinger, B., Freeman, V., Cao, S., et al. (2019). Toward Global
  Soil Moisture Monitoring With Sentinel-1: Harnessing Assets and Overcoming
  Obstacles. *IEEE Transactions on Geoscience and Remote Sensing*, 57(1),
  520–539. https://doi.org/10.1109/TGRS.2018.2858004
- El Hajj, M., Baghdadi, N. N., Zribi, M., et al. (2018). Evaluation of SMOS,
  SMAP, ASCAT and Sentinel-1 Soil Moisture Products at Sites in Southwestern
  France. *Remote Sensing*, 10(4), 569. https://doi.org/10.3390/rs10040569
- Colliander, A., Reichle, R. H., Crow, W. T., et al. (2022). Validation of Soil
  Moisture Data Products From the NASA SMAP Mission. *IEEE Journal of Selected
  Topics in Applied Earth Observations and Remote Sensing*, 15, 364–392.
  https://doi.org/10.1109/JSTARS.2021.3124743
- Kellndorfer, J., Cartus, O., Lavalle, M., et al. (2022). Global seasonal
  Sentinel-1 interferometric coherence and backscatter data set. *Scientific
  Data*, 9, 73. https://doi.org/10.1038/s41597-022-01189-6
- Ahmadian, N., Hasan, S., & Calla, O. P. N. (2013). Permittivity and
  Backscattering Coefficient of Diesel Oil-Contaminated Soil at C Band
  (5.3 GHz). *International Journal of Microwave Science and Technology*, 2013,
  950862. https://doi.org/10.1155/2013/950862
- Abdelgwad, A. H., & Said, T. M. (2016). Measured Dielectric Permittivity of
  Contaminated Sandy Soil at Microwave Frequency. *Journal of Microwaves,
  Optoelectronics and Electromagnetic Applications*, 15(2), 115–122.
  https://doi.org/10.1590/2179-10742016v15i2591

### Leak detection and polarimetry

- Yan, Y., Le, X., Yang, T., & Yu, H. (2024). Interpretable PCA and SVM-Based
  Leak Detection Algorithm for Identifying Water Leakage Using SAR-Derived
  Moisture Content and InSAR Closure Phase. *IEEE Journal of Selected Topics in
  Applied Earth Observations and Remote Sensing*, 17, 15136–15147.
  https://doi.org/10.1109/JSTARS.2024.3443127
- Ali, E., Xie, L., Sani-Mohammed, A., Xu, W., & Zayed, T. (2025). Scalable
  Detection of Underground Water Leaks in Dense Urban Environments Using L-Band
  SAR and Machine Learning. *ISPRS Archives*, XLVIII-G-2025, 147–153.
  https://doi.org/10.5194/isprs-archives-XLVIII-G-2025-147-2025
- Peng, W., Xiao, H., Fu, H., & Liu, G. (2026). Detection of soil moisture
  variations beneath an asphalt layer using L-band SAR. *International Journal
  of Applied Earth Observation and Geoinformation*.
  https://doi.org/10.1016/j.jag.2026.105592
- Freeman, A., & Durden, S. L. (1998). A three-component scattering model for
  polarimetric SAR data. *IEEE Transactions on Geoscience and Remote Sensing*,
  36(3), 963–973. https://doi.org/10.1109/36.673687
- Cloude, S. R., & Pottier, E. (1997). An entropy based classification scheme
  for land applications of polarimetric SAR. *IEEE Transactions on Geoscience
  and Remote Sensing*, 35(1), 68–78. https://doi.org/10.1109/36.551935
- Yamaguchi, Y., Moriyama, T., Ishido, M., & Yamada, H. (2005). Four-component
  scattering model for polarimetric SAR image decomposition. *IEEE Transactions
  on Geoscience and Remote Sensing*, 43(8), 1699–1706.
  https://doi.org/10.1109/TGRS.2005.852084
- Migliaccio, M., Nunziata, F., & Buono, A. (2015). SAR polarimetry for sea oil
  slick observation. *International Journal of Remote Sensing*, 36(12),
  3243–3273. https://doi.org/10.1080/01431161.2015.1057301
- Alpers, W., Holt, B., & Zeng, K. (2017). Oil spill detection by imaging radars:
  Challenges and pitfalls. *Remote Sensing of Environment*, 201, 133–147.
  https://doi.org/10.1016/j.rse.2017.09.002
- Ramsey, E., Rangoonwala, A., Suzuoki, Y., & Jones, C. E. (2011). Oil Detection
  in a Coastal Marsh with Polarimetric Synthetic Aperture Radar (SAR). *Remote
  Sensing*, 3(12), 2630–2662. https://doi.org/10.3390/rs3122630
- Zhang, Y., Li, Y., Liang, X. S., & Tsou, J. Y. (2017). Comparison of Oil Spill
  Classifications Using Fully and Compact Polarimetric SAR Images. *Applied
  Sciences*, 7(2), 193. https://doi.org/10.3390/app7020193
- Quigley, C., Johansson, A. M., & Jones, C. E. (2023). An Investigation on the
  Damping Ratio of Marine Oil Slicks in Synthetic Aperture Radar Imagery. *IEEE
  Journal of Selected Topics in Applied Earth Observations and Remote Sensing*,
  16, 5488–5501. https://doi.org/10.1109/JSTARS.2023.3285145

### Nord Stream

- Jia, M., et al. (2022). The Nord Stream pipeline gas leaks released
  approximately 220,000 tonnes of methane into the atmosphere. *Environmental
  Science and Ecotechnology*, 12, 100210.
  https://doi.org/10.1016/j.ese.2022.100210
- Harris, S. J., et al. (2025). Methane emissions from the Nord Stream subsea
  pipeline leaks. *Nature*, 637, 1124–1130.
  https://doi.org/10.1038/s41586-024-08396-8
- Dogniaux, M., et al. (2024). Report on Landsat 8 and Sentinel-2B observations
  of the Nord Stream 2 pipeline methane leak. *Atmospheric Measurement
  Techniques*, 17(9), 2777–2787. https://doi.org/10.5194/amt-17-2777-2024
- Soldi, G., et al. (2023). Monitoring of Critical Undersea Infrastructures: The
  Nord Stream and Other Recent Case Studies. *IEEE Aerospace and Electronic
  Systems Magazine*. https://doi.org/10.1109/MAES.2023.3285075

### Mission and tool documentation

- NASA NISAR mission overview: https://nisar.jpl.nasa.gov/mission/mission-overview/
- NISAR eoPortal: https://www.eoportal.org/satellite-missions/nisar
- ALOS-2 eoPortal: https://www.eoportal.org/satellite-missions/alos-2
- ESA SentiWiki, Sentinel-1 products: https://sentiwiki.copernicus.eu/web/s1-products
- Sentinel-1 mission: https://en.wikipedia.org/wiki/Sentinel-1
- TerraSAR-X: https://en.wikipedia.org/wiki/TerraSAR-X
- COSMO-SkyMed: https://en.wikipedia.org/wiki/COSMO-SkyMed
- RADARSAT-2: https://en.wikipedia.org/wiki/RADARSAT-2
- ICEYE: https://en.wikipedia.org/wiki/ICEYE
- Capella Space: https://en.wikipedia.org/wiki/Capella_Space
- SNAP: https://step.esa.int/main/toolboxes/snap/
- ISCE2: https://github.com/isce-framework/isce2
- MintPy: https://github.com/insarlab/MintPy
- GMTSAR: https://github.com/gmtsar/gmtsar
- Doris: https://github.com/TUDelftGeodesy/doris
- StaMPS: https://github.com/dbekaert/StaMPS
- HyP3: https://hyp3-docs.asf.alaska.edu/
- LiCSAR: https://comet.nerc.ac.uk/comet-lics-portal/
- ARIA: https://aria.jpl.nasa.gov/
