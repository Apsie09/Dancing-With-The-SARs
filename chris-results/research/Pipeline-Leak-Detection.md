# TerraGuard — Detecting Buried Water Pipeline Leaks from Space

A technical review and build plan for satellite-based screening of **drinking-water
and wastewater pipeline leaks**. Water only: no oil, no gas, no methane.

Written 2026-11-14. Every number is sourced; derived numbers show their
arithmetic so they can be audited.

> **Companion documents.** The detailed SAR physics, detection limits and
> mission comparison live in
> [`SAR-Pipeline-Leak-Research-Brief.md`](SAR-Pipeline-Leak-Research-Brief.md).
> This document is the water-specific synthesis and build plan; it cites that
> brief where the underlying numbers come from.

---

## 0. Scope and verdict

### 0.1 What this document covers

Buried **water** pipelines: potable transmission mains, distribution networks,
and wastewater force mains. The failure mode of interest is **leakage** —
a pressurised loss of water into the surrounding soil, whether a background
seep or a burst.

It does **not** cover oil, gas, methane, hydrogen, or district heating, except
where a district-heating result is the only available evidence for a physical
mechanism and is labelled as such.

### 0.2 The one-sentence thesis

> A buried water leak is invisible to a satellite, but the **wet soil around it
> is not** — and the strongest detector is not "find wet ground", it is
> **"find ground that stays wet when the weather says it should be dry."**

That reframing is the whole project. It turns an impossible supervised
classification problem into a tractable **weather-normalised anomaly-detection**
problem, trainable on unlabelled historical data, with a physical null
hypothesis you can test.

### 0.3 Six signature families

A leak perturbs the ground in six independent ways. The strongest system fuses
several, because each one fails in a different environment.

| Family | What changes | Primary sensors | Fails when |
|---|---|---|---|
| **Electromagnetic** | Soil dielectric constant, electrical conductivity, radar backscatter | SAR (L/C/X), passive microwave, EMI | Dry soil, dense vegetation, frozen ground |
| **Thermal** | Surface temperature, diurnal heating/cooling range, evaporation | TIR (satellite, airborne, UAV) | Cloud, small ΔT, vegetation, pavement |
| **Hydrological** | Persistent moisture, ponding, altered drainage | SAR, optical/SWIR, DEM | Rainfall masks it; drainage removes it |
| **Biological** | Vegetation vigour, species change, drought resilience | Optical (NDVI, NDMI, red edge) | Mature vegetation, irrigation, season |
| **Mechanical** | Subsidence, void growth, soil erosion, vibration | InSAR, DAS, LiDAR | Slow; needs long time series |
| **Hydraulic** | Pressure, flow, night-flow, mass balance | SCADA, DMA meters, acoustic | Small leaks below noise; needs utility data |

### 0.4 What is proven, what is not

| Claim | Evidence status |
|---|---|
| Commercial L-band SAR screening finds leaks at scale | **Operational**, vendor-reported: Affinity Water / SUEZ / ASTERRA screened 9,045 km, delivered 763 locations, confirmed **902 leaks**, **59 % non-surfacing**; crews inspected <4 % of the network (§2.1) |
| A learned model can classify leak vs non-leak from SAR features | **Peer-reviewed**: 86.3 % accuracy, 1,545 field-verified leaks, MDFLD-Net, Beijing/Tianjin (§2.2); 91.86 % on a water/sewer network, Yan et al. (§2.5) |
| Unsupervised anomaly detection finds leaks under pavement | **Peer-reviewed**: 81 % of known leaks found, 93 % inspection reduction, many false positives (§2.3) |
| L-band responds to moisture *below* the surface | **Peer-reviewed but moderate**: R² = 0.705 predicting subsurface relative dielectric constant from SAOCOM-1A, validated with GPR (§2.4) |
| Multisensor fusion beats any single method | **Peer-reviewed, small sample**: Cyprus, 2025 (§2.6) |
| Satellite thermal can detect a potable-water leak | **Not demonstrated at satellite resolution.** Airborne TIR can; 100 m satellite TIR cannot (§3) |
| InSAR detects leaks early | **Weak.** InSAR detects *consequences* (subsidence, voids) and *geohazards*, not the leak (§4.2) |
| Any of this works without field confirmation | **No.** Every credible study uses acoustic, GPR, excavation, or utility records to confirm |

**The honest framing for a judge or reviewer:** satellite data is a **triage
layer**. It reduces the search space; it does not replace acoustic correlation,
GPR, or excavation. The Affinity Water programme is explicit that field crews
used acoustic equipment to verify every flagged location.

### 0.5 The three propositions worth building

1. **Weather-normalised residual anomaly** (satellite-only, strongest PoC):
   predict the moisture-sensitive radar response from rainfall, season, soil and
   vegetation; flag locations that stay wet when the model says they should dry.
2. **Multi-signature fusion** (operational direction): combine radar, thermal
   and hydraulic evidence with explicit uncertainty.
3. **Leak-evolution modelling** (research direction): simulate the moisture
   plume in soil and match the predicted temporal signature against observation.

Details in §7.

---

## 1. The physics of a buried water leak

### 1.1 The chain from pipe to pixel

```
  PIPE FAILURE (hole, joint, crack, corrosion)
    │
    ├─(minutes–hours)──► soil pore pressure ↑, saturation ↑
    │                      ├─ dielectric constant ↑  → SAR σ⁰ ↑, phase centre moves
    │                      ├─ thermal inertia ↑      → cooler by day, warmer at night
    │                      ├─ evaporation ↑          → latent cooling
    │                      └─ electrical conductivity ↑ → EMI/ERT anomaly
    │
    ├─(hours–days)────► free water reaches surface
    │                      ├─ ponding / darkened soil → optical change
    │                      └─ surface wet patch       → TIR + LiDAR intensity change
    │
    ├─(days–weeks)────► root-zone waterlogging
    │                      └─ vegetation: greener in drought, or dies from anoxia
    │
    ├─(weeks–months)──► soil erosion, void growth
    │                      └─ subsidence, sinkhole, pavement failure → InSAR
    │
    └─(continuous)────► hydraulic signature
                           └─ night flow ↑, DMA mass balance ↑, pressure drop → SCADA
```

Two consequences follow, and they drive the whole design:

- **Fast signals are ephemeral.** Moisture and ponding disappear after dry
  weather or drainage works. You need frequent revisit or a long baseline.
- **Slow signals are ambiguous.** Subsidence has many causes. It confirms a
  leak; it does not find one early.

### 1.2 Why the pipe is invisible

1. **Depth.** Water mains are typically buried 0.9–1.5 m (deeper at crossings;
   shallower in rock). C-band (5.6 cm) senses the top ~2–5 cm of soil; L-band
   (24 cm) the top ~5–20 cm in dry soil, less when wet. Neither reaches the pipe.
2. **Attenuation.** Wet soil is lossy. Two-way C-band attenuation through 1 m of
   soil at field capacity is tens of dB.
3. **Scale.** A 100–600 mm pipe occupies 0.5–6 % of a 10 m pixel.

The satellite sees the **moisture column above and around the leak**, not the
pipe. That is why the retrieval target is *soil water content in the topsoil*,
and why the signal is strongest for shallow leaks in sandy, bare soil and
weakest for deep leaks under clay or pavement.

> **The pavement exception.** A leak under asphalt is hidden optically but not
> necessarily electromagnetically. Peng et al. (2026) showed L-band phase
> responds linearly to subsurface volumetric water content through at least
> **9 cm of asphalt** (0.53° of phase per 1 % VWC, r = −0.992), and that
> infiltration produces clear coherence loss and non-zero closure phase. This is
> the physical basis for the "leaks under paved surfaces" result in §2.3.

### 1.3 Detection budget for water

| Observable | Physical change required | Sensor | Native pixel | Threshold | Lag |
|---|---|---|---|---|---|
| **Soil moisture (amplitude)** | +5 % volumetric water content in top 5 cm | C-band σ⁰ | 10–20 m | **1.7 % SM/dB** (sandy loam), **4.8 % SM/dB** (clay) → 1–3 dB (Stanyer et al., 2025) | hours–days |
| **Soil moisture (phase)** | same, via phase-centre and coherence change | InSAR closure phase | 20–80 m | 0.53°/1 % VWC through 9 cm asphalt (Peng et al., 2026); cumulative closure phase tracks SM (Wig et al., 2024) | days–weeks |
| **Surface wetness** | albedo and NIR reflectance drop | Optical/SWIR | 10–20 m | NDMI change ≈ 0.05–0.15; soil darkening visible | hours–days |
| **Vegetation response** | canopy water and chlorophyll | Optical | 10 m | ΔNDVI ≈ 0.05; NMDI/NDWI more sensitive than NDVI (Cyprus 2025) | weeks–months |
| **Temperature** | surface radiometric temperature | TIR | 3.5–100 m | **LST accuracy 1–2 K**, not NEΔT; pixel-fill problem (§4.3) | hours–days |
| **Deformation** | vertical displacement | InSAR | 20–80 m | 8–10 mm/yr vs levelling/GNSS (Cigna et al., 2021) | months–years |
| **Ponding** | open water | SAR / optical | 10–20 m | dark SAR + low NDWI threshold | hours |

### 1.4 How water differs from oil and gas (and why that matters)

| Property | Water | Consequence for remote sensing |
|---|---|---|
| **Temperature contrast** | Small: potable water is 5–20 °C, soil 5–30 °C; ΔT often <5 K | Thermal is a weak primary detector; the signal is thermal *inertia*, not a hot pipe |
| **Persistence** | Background leaks run for months–years | Chronic wet anomalies are the norm → time-series methods work |
| **Chemistry** | Potable water is low-salinity, high-dielectric | Strong SAR contrast; but chlorine/fluoride can stress vegetation |
| **Leak rate** | Background 0.1–10 m³/h; burst 10–500 m³/h | Small leaks are numerous; large bursts are easy but rare |
| **Network density** | Urban, buried, thousands of km | Corridor constraint is powerful: you know where pipes are |
| **Non-revenue water** | 20–30 % globally, up to ~50 % with ageing infrastructure (Theocharidis et al., 2025) | The prize is large and the utility already has a business case |
| **Confounders** | Irrigation, rainfall, drainage, springs, leaky sewers | Weather normalisation is mandatory, not optional |

### 1.5 Leak-rate arithmetic

Useful for converting "a leak" into "a wet patch":

- **1 m³/h** = 24 m³/day. At 30 % volumetric saturation, that saturates
  ~80 m³ of soil per day. Spread over a 1 m root zone, that is ~80 m² of
  wetted ground — **8 pixels of 10 m**, or 0.3 pixels of Landsat.
- **10 m³/h** (a significant distribution leak) = 240 m³/day → ~800 m² of
  affected soil. Clearly visible at 10–20 m.
- **0.1 m³/h** (a background weep) = 2.4 m³/day → ~8 m². **Not** reliably
  detectable from a satellite; this is the honest lower bound.
- **A 2–10 m³/day seep** was detected by low-altitude airborne TIR in the
  1980s (Eidenshink, 1985) — but that is 0.08–0.4 m³/h with a pixel size of
  metres, not a satellite.

> **There is no published minimum detectable leak rate for satellite water-leak
> detection.** The commercial vendors do not publish one; the peer-reviewed
> studies report accuracy against confirmed leaks, not detection probability as
> a function of leak rate. Any number quoted is an extrapolation. State that in
> your submission — it is the single fastest way to look credible.

---

## 2. What has actually been demonstrated

### 2.1 Commercial operations: ASTERRA, Utilis, SUEZ

**The Affinity Water programme (UK, 2025) is the best-documented operational
result.** SUEZ and ASTERRA used L-band SAR to survey five supply areas covering
**9,045 km** of distribution network. Published figures:

| Metric | Value |
|---|---|
| Network screened | 9,045 km |
| Locations delivered to field crews | 763 |
| Locations investigated | 546 (72 %) |
| **Leaks confirmed** | **902** |
| **Confirmed leaks with no surface manifestation** | **59 %** |
| Network physically inspected | **< 4 %** |
| Water recovered | 1.26 billion litres/year |
| Reported programme value | £2.06 M |
| Crew efficiency gain | 454 % |

The mechanism is stated plainly: *"ASTERRA Recover detects subsurface soil
moisture anomalies at pipe depth… moisture anomalies present at pipe depth long
before any evidence appears above ground."* Field crews then used **acoustic
equipment to verify and locate** every flagged leak.

**How to use this honestly:**

- It is **vendor-reported**, not an independent controlled trial. There is no
  published false-positive rate per km, no detection-probability curve, and no
  cost-per-leak breakdown.
- The 59 % non-surfacing figure is the most important number in the whole field:
  it says the satellite is finding leaks that visual and acoustic patrols would
  have missed. It also says **41 % were surfacing** — i.e. visible by other means.
- The programme confirms the economics, not the physics. Do not present it as
  proof that SAR can localise a leak to a metre.

**Other commercial providers:** Utilis (Israel, L-band SAR soil-moisture
retrieval, the other long-running operator), KnoWaterleak (Greece), and various
utility consultancies. Their methods are broadly similar; their validation
evidence is similarly thin in public.

### 2.2 MDFLD-Net, Beijing/Tianjin (2025) — the strongest peer-reviewed result

Li et al. (2025), *International Journal of Applied Earth Observation and
Geoinformation*, doi:10.1016/j.jag.2025.104915.

- **Data:** SAOCOM-1A **L-band** quad-pol + Sentinel-1 **C-band** dual-pol.
- **Features:** backscatter intensity, **H/A/α polarimetric decomposition**
  (entropy, anisotropy, mean scattering angle), and **interferometric closure
  phase**, fused in a multi-scale feature-extraction module.
- **Labels:** **1,545 leak samples** verified by field equipment across Beijing
  and Tianjin.
- **Results:** accuracy **0.863**, precision 0.875, recall 0.847, F1 0.860,
  inference 72 ms.
- **Ablation:** single-sensor models reached 0.698–0.772; dual-sensor fusion
  0.824–0.843; adding closure phase reached **0.863**.
- **Field test:** full-coverage SAR produced **595 candidate regions of
  interest**, which contained **406 field-verified leaks**.

**What it proves:** fusing L-band, C-band, polarimetry and closure phase beats
any single feature, with a large labelled dataset.

**What it does not prove:** the candidate regions are **much larger than a pipe
failure**. This is a *screening* result at region scale, not metre-level
localisation. It is also a single metropolitan setting with a specific pipe
stock and soil.

**Why it matters for TerraGuard:** it is the published template for the
multi-feature model, and it is the best evidence that **L-band + C-band
together** outperform either alone. Your differentiator can be adding
**weather normalisation** (which MDFLD-Net does not do) and **NISAR**
(which did not exist when the dataset was built).

### 2.3 Leaks under paved surfaces (2026) — the unsupervised result

Arabi et al. (2026), *Journal of Environmental Management*,
doi:10.1016/j.jenvman.2026.129209.

- **Setting:** arid environment, sparse vegetation, leaks under **paved
  surfaces** — the hardest optical case.
- **Method:** **unsupervised** anomaly detection on radar data, no leak labels
  used in training.
- **Results:** the best model identified **81 % of actual leaks**, while
  **reducing inspection effort by 93 %** — but with **a high number of false
  positives**.

**Why this matters more than the accuracy:** it shows you can start without a
large labelled dataset. For a two-day hackathon, that is the difference between
a project that runs and one that does not. It also matches the physical argument
in §1.2: radar sees subsurface moisture that optical cannot.

### 2.4 L-band + GPR, Tianjin (2025) — the physics validation

Zhang et al. (2025), *Remote Sensing* 17(8), 1386,
doi:10.3390/rs17081386.

- **Method:** combine **SAOCOM-1A L-band SAR** with **ground-penetrating radar**
  to predict the **subsurface soil relative dielectric constant (SSRDC)** — the
  physical quantity that actually changes when soil wets.
- **Ground truth:** SSRDC computed from GPR using the reflected-wave method at
  sample locations.
- **Model:** MLPNN best: **R² = 0.705, RMSE = 1.936, MAE = 1.664**.
- **Application:** predicted SSRDC above a threshold was treated as a potential
  leak location in Tianjin's water network.

**Why it matters:** this is the cleanest peer-reviewed evidence that **L-band
carries information about moisture below the surface**, not just a wet-looking
top layer. R² ≈ 0.7 is moderate — enough to screen, not enough to quantify.

### 2.5 Closure phase on a water/sewer network (2024)

Yan et al. (2024), *IEEE JSTARS*, doi:10.1109/JSTARS.2024.3443127.

- **Inputs:** SAR-derived moisture content + **InSAR closure phase**.
- **Model:** interpretable PCA + SVM (deliberately not a black box).
- **Labels:** **1,222 confirmed leak points** and **1,206 non-leak points** in
  Beijing and Tianjin.
- **Results:** **91.86 %** leak detection in Beijing's Fifth Ring Road;
  **88.10 %** non-leak detection in Huizhou.

This is the highest published accuracy for satellite liquid-leak detection, and
it is on a **water/sewer** network — directly in scope.

**The scientific caveat you must include.** Molan et al. (2020, *Remote
Sensing*) tested the same idea and concluded that coherence and closure phase
are **independent of the magnitude** of soil-moisture change and are
"inappropriate tools to estimate soil moisture changes" — they respond to the
*spatial diversity* of moisture within a resolution cell, not its mean. Wig et
al. (2024, *IEEE TGRS*) countered with a physical model (interference between
surface and subsurface reflections in a time-varying dielectric) and a field
test in Oklahoma showing that **cumulative** closure phase tracks in-situ soil
moisture, with terrain dependence.

**Correct framing:** closure phase is a **qualitative change detector** with a
plausible mechanism and two strong pipeline/water results. It is not yet a
calibrated moisture retrieval. Say that, and you are ahead of most submissions.

### 2.6 Cyprus, 2025 — multisensor validation, and what actually worked

Theocharidis et al. (2025), SPIE Sensors + Imaging, doi:10.1117/12.3069672.
Study area: Doros and Monagri community councils, Cyprus.

- **Satellite:** PlanetScope (3 m) + Sentinel-2 (10 m), acquired **during
  prolonged dry periods** to maximise contrast.
- **Ground:** drone surveys (cm-level), **acoustic noise loggers**, **GPR**
  profiling.
- **Key finding:** **NDVI and SAVI were less sensitive** to localised leakage;
  **moisture-sensitive indices (NMDI, NDWI) consistently highlighted leakage
  zones.**
- **Corroboration:** UAV imagery confirmed surface cracking and localised
  greening; GPR provided subsurface validation; one strong acoustic anomaly was
  probably a pressure-regulating valve, **not a leak** — a textbook false
  positive.
- **Context:** 20–30 % of distributed freshwater is lost before reaching
  consumers; up to ~50 % with ageing infrastructure.

**Three lessons:**

1. **Do not default to NDVI.** Moisture indices (NDMI, NMDI, NDWI) are the
   better optical features for water leaks, because the signal is water, not
   chlorophyll.
2. **Dry-season acquisition is a design choice, not a detail.** Contrast is
   maximal when the background is dry.
3. **Acoustic and GPR produce false positives too.** Fusion helps because the
   failure modes are independent.

### 2.7 Prior art you must acknowledge: ESA already funded this

| Project | What it did | Status |
|---|---|---|
| **SECO** (Space for clean and safe management of pipelines) | Two independent detectors along known water pipeline routes: **optical vegetation vigour** + **SAR soil moisture**; plus an InSAR strain/ground-motion service and point-cluster analysis | Completed feasibility study |
| **WATERLENS** | Screening and monitoring tools for ageing water infrastructure | ESA Space Solutions |
| **ZOE** | Self-powered water-grid management with **terrestrial + satellite data fusion** for continuous leak detection | ESA Space Solutions |
| **GeoAI_Watloss** | AI platform for locating leaks in water networks from satellite/aerial imagery + GNSS | ESA Space Solutions |

**Implication:** "SAR + NDVI along a pipeline" is **not novel**. Neither is
"satellite + ground sensors". The novelty has to come from the *method*, the
*normalisation*, or the *fusion*, not the data combination.

### 2.8 What none of them prove

- No study publishes a **detection-probability curve vs leak rate**.
- No study reports **false alarms per km per year** — the metric utilities
  actually buy on.
- No study demonstrates **metre-level localisation** from satellite alone.
- No study validates across **soil types and climates**.
- No study uses **NISAR** (the archive is one year old).
- No study fuses **satellite + hydraulic** evidence with a calibrated
  probabilistic model in the open literature.

Those gaps are the opportunity.

---

## 3. The method landscape — 20+ techniques

Grouped by physical family. "Evidence" is graded **A** (multiple independent
field validations), **B** (one or more peer-reviewed field studies),
**C** (physics sound, limited or no leak-specific validation), **D** (vendor
claim only).

### 3.1 SAR and microwave

| # | Technique | Leak signature | Evidence | Practical assessment for water |
|---|---|---|---|---|
| 1 | **SAR backscatter change (σ⁰)** | Wetter soil → higher dielectric → higher return | **B** | The workhorse. 1–3 dB for a 5 % moisture change. Needs a seasonal baseline and rain rejection. |
| 2 | **Polarimetric decomposition (H/A/α)** | Change in scattering mechanism | **B** | Used in MDFLD-Net; entropy/alpha separate surface from volume scattering. Needs quad-pol, which is scarce. |
| 3 | **InSAR closure phase** | Non-zero phase triplet from dielectric change with depth | **B** | The most sensitive moisture-phase observable; used in both MDFLD-Net and Yan 2024. Requires SLC + a triple of dates. |
| 4 | **SAR coherence change** | Loss of similarity from surface change | **C** | Useful as a support feature, highly ambiguous alone (rain, ploughing, harvest all decorrelate). |
| 5 | **L-band + C-band comparison** | Different penetration and vegetation response | **B** | The core of MDFLD-Net; L-band sees deeper and through canopy. NISAR enables this at 10–20 m. |
| 6 | **SAR surface-water / ponding** | Standing water → specular, dark return | **A** | Reliable when ponding exists, but ponding is a late-stage symptom. |
| 7 | **InSAR ground deformation** | Void growth, erosion, subsidence | **B** | Confirms severe leaks and geohazards; too slow for early detection. |
| 8 | **Passive microwave soil moisture** | Regional wetness | **C** | 9–50 km pixels: context only, never a leak detector. |

**Implementation note:** techniques 1–5 all need **complex data** (SLC) except
plain backscatter. If you only download GRD/COG products you cannot compute
coherence or closure phase. Decide early.

### 3.2 Optical, multispectral, hyperspectral

| # | Technique | Leak signature | Evidence | Practical assessment |
|---|---|---|---|---|
| 9 | **NDMI / SWIR moisture index** | Soil/vegetation water content | **B** | Best cheap optical feature; 20 m bands on Sentinel-2 (B8A, B11). |
| 10 | **NMDI** | NIR/SWIR water absorption | **B** | Cyprus 2025 found it among the best; needs SWIR. |
| 11 | **Hyperspectral absorption** | Spectral water/pigment features | **C** | High potential, expensive, hard to validate; PRISMA/EnMAP tasking. |
| 12 | **NDVI / EVI** | Vegetation vigour | **C** | Cyprus 2025 found it *less* sensitive than moisture indices. Use as context. |
| 13 | **Persistent dry-season greening** | Vegetation stays green while surroundings senesce | **B** | Strong for long-running rural leaks; a classic visual signature. |
| 14 | **High-resolution optical change** | Darkened soil, pavement damage, ponding | **B** | Works only when the effect is visible; good confirmation layer. |
| 15 | **Vegetation growth-pattern anomaly** | Local patch behaves differently over time | **C** | An interesting temporal-ML feature; non-specific. |
| 16 | **Evapotranspiration anomaly** | Extra water → extra ET | **C** | ECOSTRESS ET at 70 m; promising for large wet areas, too coarse for a leak. |

**Index formulas worth knowing:**

```
NDMI = (NIR − SWIR) / (NIR + SWIR)        Sentinel-2: (B8 − B11)/(B8 + B11)
NMDI = (NIR − (SWIR1 − SWIR2)) / (NIR + (SWIR1 − SWIR2))
NDWI = (Green − NIR) / (Green + NIR)      surface water, not soil moisture
```

Sentinel-2 B11 is 20 m; B8A is 20 m. Use B8A rather than B8 when pairing with
B11 to avoid resampling artefacts.

### 3.3 Thermal

| # | Technique | Leak signature | Evidence | Practical assessment |
|---|---|---|---|---|
| 17 | **Surface temperature anomaly** | Wet ground cooler by day | **B** (airborne), **C** (satellite) | Works at high resolution; 100 m satellite fails the pixel-fill test (§4.3). |
| 18 | **Day/night thermal inertia** | Wet soil heats/cools more slowly | **B** | The physically correct feature. Needs paired day and night acquisitions. |
| 19 | **Evaporative cooling** | Extra evaporation lowers surface T | **C** | Real in warm dry weather; small signal, easily confused with shading. |
| 20 | **Seasonal water/soil temperature contrast** | Pipe water warmer than frozen ground in winter | **C** | Best window in winter/spring in cold climates; ΔT 5–15 K. |
| 21 | **Airborne / UAV thermography** | Localised surface patterns | **A** | The demonstrated tool for water leaks at 5–15 cm pixels. |
| 22 | **High-resolution satellite thermal (3.5 m)** | Pipeline-scale halo | **C** | SatVu HotSat; physically plausible, **no published water-leak validation**. |

### 3.4 Ground-based confirmation

| # | Technology | What it measures | Evidence | Role |
|---|---|---|---|---|
| 23 | **GPR** | Subsurface reflections, dielectric contrasts | **A** | Locates wet zones and voids; validates satellite anomalies. |
| 24 | **ERT** | Electrical resistivity | **A** | Maps moisture and contamination plumes. |
| 25 | **EMI / FEM** | Apparent conductivity | **A** | Fast screening of moisture changes. |
| 26 | **Drone LiDAR intensity** | Wet-surface reflectance | **B** | 1.2 dB drop on grass, 2.2 dB on pavement (Bretreger et al., 2025). |
| 27 | **Soil moisture probes** | Volumetric water content | **A** | The ground truth for any moisture model. |
| 28 | **DTS** | Temperature along a fibre | **A** | Continuous, where fibre exists. |
| 29 | **DAS** | Leak-induced vibration | **A** | Continuous; a 1 mm hole at 5 bar ≈ 0.14 % of flow. |
| 30 | **Pressure/flow (SCADA, DMA)** | Hydraulic imbalance | **A** | The operational baseline; satellite adds spatial attribution. |
| 31 | **Acoustic correlators / hydrophones** | Leak noise and time delay | **A** | The standard localisation method; used to confirm every commercial satellite flag. |
| 32 | **Water chemistry / tracers** | Whether water matches network supply | **A** | Definitive confirmation, slow. |

### 3.5 Hydraulic / network-internal

| # | Technique | What it measures | Evidence | Role |
|---|---|---|---|---|
| 33 | **Mass balance / DMA metering** | Inflow − outflow | **A** | Detects district-level losses; no spatial precision. |
| 34 | **Night-flow analysis** | Minimum night flow | **A** | The classic background-leakage metric. |
| 35 | **Pressure transient analysis** | Wave reflections from a leak | **B** | Sensitive, but noisy networks. |
| 36 | **Hydraulic model calibration** | Residuals between modelled and measured pressure/flow | **A** | Localises to a pipe segment; the natural fusion partner for satellite. |
| 37 | **LeakDB / BattLeDIM benchmarks** | Simulated leak scenarios with labels | **n/a** | Train the hydraulic branch, **not** the SAR branch. |

---

## 4. What the physics says about each family's limits

### 4.1 SAR: the primary detector, with a hard noise floor

**Sensitivity depends on band, soil and vegetation.** Two independent
calibrations bracket the range:

| Study | Setting | Sensitivity |
|---|---|---|
| El Hajj et al. (2019) | ALOS-2 L-band HH, wheat/grass, NDVI < 0.7 | **0.27 dB per vol.%** |
| El Hajj et al. (2019) | Sentinel-1 C-band VV/VH, same cover | **0.12 dB per vol.%** |
| Stanyer et al. (2025) | Sentinel-1 VV, sandy loam | **0.59 dB per vol.%** (1 dB per 1.69 % SM) |
| Stanyer et al. (2025) | Sentinel-1 VV, clay | **0.21 dB per vol.%** (1 dB per 4.81 % SM) |

So a **5 % volumetric moisture increase** gives **0.6 dB** in the pessimistic
C-band case and **~3 dB** in the optimistic sandy-loam case. A 10 % increase
gives 1.2–5.9 dB.

**The real limit is speckle, not sensitivity.** Intensity speckle in dB scales as:

```
σ_dB ≈ 4.34 / √L        (L = number of independent looks)
```

| Product | Looks | Speckle σ | 3σ detection floor |
|---|---:|---:|---:|
| Sentinel-1 IW SLC | 1 | 4.3 dB | 13 dB |
| Sentinel-1 IW GRD-H, 10 m | ~5 | 1.9 dB | **5.8 dB** |
| Sentinel-1 IW GRD-M, 40 m | ~480 | 0.2 dB | 0.6 dB |
| NISAR GCOV, 20 m | 4–16 | 1.1–2.2 dB | 3.3–6.6 dB |

**This is the single most important practical correction:** a 1 dB anomaly is
**not** detectable in a single 10 m Sentinel-1 look, because the speckle floor
is ~5.8 dB at 3σ. You either multi-look to 40–60 m, or — better — average over
time and detect the anomaly against a seasonal baseline. Radiometric precision
comes from averaging, and averaging costs either space or time.

The confounders are not optional:

| Confounder | Effect | Fix |
|---|---|---|
| Rainfall | +2–6 dB, basin-wide | Reject dates within 1–5 days of >5 mm IMERG rain |
| Irrigation | Localised wet patches | Land-cover and season mask |
| Ploughing / harvest | Coherence loss, σ⁰ change | Mask agricultural fields or use stable targets |
| Freeze/thaw | 3–6 dB step | Mask frozen dates (soil temperature < 0 °C) |
| Vegetation growth | Volume scattering ↑ | Use HV/VV ratio, NDVI covariate |
| Soil type | 3× difference in dB sensitivity | SoilGrids covariate, or per-soil calibration |

### 4.2 InSAR: a consequence detector, not a leak detector

InSAR resolves **8–10 mm/yr** against levelling and GNSS (Cigna et al., 2021),
with <20 % relative error above 15 mm/yr. That is impressive — but a water leak
does not usually deform the ground at millimetres per year until it has been
eroding soil for a long time.

**Two limits that matter more than the headline accuracy:**

- **A single interferogram is atmosphere-limited at ~1–2 cm rms**, not
  millimetres (Zebker, 2021). A transient smaller than ~1 cm between two
  acquisitions is generally invisible. Millimetre-per-year trends need
  multi-year stacks.
- **Most sinkhole precursors are missed.** Theron et al. (2017) detected
  50 mm of movement in 55 days before one collapse, but **7 of 10 events had no
  detectable precursor at all.** InSAR is a supplement to inspection, not a
  substitute for it.

**Pipeline-specific evidence.** Bayramov et al. (2020) compared PSInSAR and SBAS
over 70 km of the Baku–Tbilisi–Ceyhan and South Caucasus pipelines (Azerbaijan,
Sentinel-1, 2018–2019). SBAS gave **more complete and less dispersed coverage
along the buried pipe** (SBAS −12 to +8 mm/yr; PS −46 to +33 mm/yr, i.e. much
noisier). SBAS agreed with GPS at R = 0.94, RMSE 1.5–2.5 mm; PS and SBAS
differed by 4.9–6 mm. **Use SBAS, not PS, for a linear buried asset.**

**A confounder specific to water leaks.** Zwieback et al. (2015) showed that a
**20 % change in soil moisture can produce >2 cm of apparent L-band
deformation**, because the phase centre moves as the dielectric profile changes.
That means a wet patch can masquerade as ground movement — and, conversely, that
InSAR "subsidence" above a leak may partly be a moisture artefact. Cross-check
any deformation anomaly against the backscatter/closure-phase record.

Where InSAR genuinely helps:

- **Void growth and sinkholes** in karst or granular soils.
- **Pavement and road subsidence** above a long-running leak.
- **Geohazard screening** of transmission mains (slope, fault, subsidence).
- **Differential settlement** of large-diameter mains and chambers.

Where it does not:

- Early detection of a small leak.
- Any site with low coherence (vegetation, construction, snow).

**Ranking:** InSAR is a **supporting** layer, not the primary detector. Put it
in the dashboard as "structural context", not as the leak alarm.

### 4.3 Thermal: why 100 m satellites cannot see a water leak

The critical correction: **use LST product accuracy (1–2 K), not instrument
NEΔT (0.1–0.4 K).** NEΔT is noise; LST accuracy includes atmospheric
correction, emissivity and surface heterogeneity. A 0.4 K NEΔT does **not**
mean a 0.4 K anomaly is detectable.

Apparent pixel anomaly for a source contrast ΔT:

```
ΔT_pixel ≈ f × ΔT_source,   f = anomaly width / pixel size
```

**Table: source contrast needed to produce a 2 K pixel anomaly.**

| Fill fraction f | Required source ΔT |
|---:|---:|
| 1 % (1 m in 100 m) | 200 K |
| 5 % | 40 K |
| 10 % | 20 K |
| 20 % | 10 K |
| 40 % | 5 K |
| 100 % | 2 K |

**Table: minimum anomaly width for a 5 K source to produce a 2 K pixel anomaly.**

| Sensor | Pixel | Minimum width |
|---|---:|---:|
| Landsat 8/9 TIRS | 100 m | **40 m** |
| ASTER TIR | 90 m | 36 m |
| ECOSTRESS | 38 m | 15 m |
| Sentinel-3 / MODIS | 1 km | 400 m |
| SatVu HotSat | 3.5 m | **1.4 m** |
| Airborne TIR | 0.5 m | 0.2 m |
| UAV TIR | 10 cm | 4 cm |

**For potable water, a 5 K contrast is already generous.** A leak in summer
might cool the surface by 2–5 K through evaporation; in winter it might warm it
by 5–15 K. Take 2 K as a realistic contrast and the required widths double:
**80 m at Landsat, 30 m at ECOSTRESS, 3 m at HotSat.**

**Conclusion:** free 100 m TIR cannot detect a water leak. It can detect a
**large wet patch or pond** tens of metres across, which is a late-stage
symptom. ECOSTRESS improves this to a 15–30 m patch. Only airborne/UAV TIR and
SatVu's 3.5 m HotSat approach pipeline scale — and they still see the **halo**,
not the pipe.

> **A note on NISAR resolution.** NISAR has **no thermal sensor**. Its 10–20 m
> GCOV and 80 m GUNW are radar products and cannot be compared with a thermal
> pixel. Do not mix the two in a resolution table — it is a common and
> immediately visible error.

**What thermal does add:** the **day/night thermal-inertia signature**. Wet soil
is cooler by day and warmer at night. A paired day/night acquisition, or a
time-series of pre-dawn images, is a genuinely independent physical channel from
SAR — and it is the right way to use thermal in a fusion model, rather than
looking for a single "hot spot".

**Evidence from water and district-heating work:**

- **Eidenshink (1985):** low-altitude airborne TIR detected **2–10 m³/day
  seepers** from buried rural water pipelines. The proof of principle — at
  metre-scale pixels, not satellite.
- **Friman et al. (2014):** airborne TIR over district-heating networks found
  >20 K surface anomalies, but of 549 / 193 / 283 detections in three cities,
  only **20 / 7 / 7 were confirmed leaks** (precision ≈ 3.6 % in the largest).
  High recall, very low precision.
- **Call et al. (2025), Phoenix:** five known water-leak sites; a thermal
  signal at 4 of 5, but after shadow/solar filtering the final detection rate
  was **60 %**.
- **Krapez et al. (2022), WADI:** airborne hyperspectral + TIR over French and
  Portuguese water networks; true events identified on about **50 % of
  occasions**, with many false alarms from ponds, irrigation and vegetation.
- **Risch et al. (2026):** aerial LWIR over a district-heating network raised
  detections from 908 to 1,660 using thermal isolines and pipeline-axis
  statistics — still requiring human review.

The honest summary: **thermal is a confirmation layer, best used as thermal
inertia, best at high resolution.**

### 4.4 Optical: useful, non-specific, and best in drought

Moisture indices respond to the same water that SAR sees, but only in the top
millimetres and only when the surface is visible. Their strengths are
**interpretability** (a human can see the green patch) and **resolution**
(10–20 m, and 3 m with PlanetScope).

Their weaknesses:

- **Cloud** — the reason SAR exists.
- **Vegetation masking** — dense canopy hides soil moisture.
- **Non-specificity** — drought, irrigation, fertiliser and disease all change
  NDVI.
- **Lag** — vegetation response takes weeks.

Cyprus 2025's finding that **NMDI/NDWI beat NDVI/SAVI** should shape your feature
set. Use moisture indices as the optical backbone, NDVI as context.

**Two cautionary results worth citing.** The classic one is van der Werff et al.
(2008): across agricultural fields, **red-edge variation between fields was
larger than the leak signal**, so a simple index threshold produces false
positives — a spatial-spectral approach (compare a pixel with its local
neighbourhood, not with a global threshold) is required. The second is Ma et al.
(2024): gas-induced vegetation stress is spectrally detectable, but in
controlled experiments the **stress radius was 0.83–1.07 m** — far below
satellite resolution. Vegetation is a confirmation layer, not a detector.

### 4.5 Passive microwave and gravity: context only

SMAP (9–36 km), SMOS (25–50 km), ASCAT (12.5 km) and GRACE (~300 km) are
**three to five orders of magnitude too coarse** for a pipeline. They are useful
for two things: regional wetness context (was the whole area wet?), and
groundwater/aquifer context for transmission mains. Never present them as leak
detectors.

---

## 5. Seven combinations worth building

Each entry: the idea, the evidence, and what would make it yours.

### 5.1 Detect moisture that refuses to dry — **top PoC candidate**

Train a model to predict the expected moisture-sensitive radar response from
rainfall history, season, soil and vegetation. When the surrounding land dries
but a corridor stays anomalously wet, flag it.

**Evidence:** consistent with the commercial method (ASTERRA explicitly targets
subsurface moisture anomalies) and with the dry-season design of the Cyprus
study. The *predictive residual* formulation is your implementation.

**Why it is strong:** an unexplained wet patch during a dry spell is far more
informative than a wet patch after rain. It is also the natural null hypothesis:
"this pixel behaves like its neighbours given the weather" vs "it does not".

**What would make it yours:** a published, reproducible residual model with
rainfall ablation — showing how much of the skill comes from weather
normalisation alone.

### 5.2 Measure thermal behaviour, not temperature

Compare the **day/night temperature range** of a corridor with matched
neighbouring ground, rather than looking for a hot or cold pixel.

```
DTR = T_day − T_night
```

Wet soil has higher heat capacity and thermal inertia, so its DTR is smaller.

**Evidence:** thermal inertia is an established soil-moisture retrieval
principle; water-leak TIR studies show the day/night sign flip. Not validated
for leak localisation at satellite resolution.

**Constraint:** needs paired day and night acquisitions of comparable quality.
Landsat's 10:00 / 22:00 overpasses are usable; ECOSTRESS's variable ISS orbit is
not. This is a genuinely novel feature if you can get the pairs.

### 5.3 Combine three radar signatures

Use **L-band backscatter**, **polarimetric decomposition**, and
**multi-temporal interferometric features** together, and classify patterns
rather than thresholds.

**Evidence:** MDFLD-Net did exactly this and reported 86.3 % accuracy; its
ablation shows closure phase adds ~2 percentage points over dual-sensor fusion
alone (0.843 → 0.863).

**What would make it yours:** reproduce a simpler version and test whether
adding **rainfall history** improves robustness. That is a clean, publishable
ablation.

### 5.4 Connect satellite anomalies to hydraulic-network behaviour

If pressure sensors show an unexplained loss in one district, and SAR shows a
persistent moisture anomaly near one of its pipes, fuse the two.

**Evidence:** ESA SECO, WATERLENS and ZOE all describe satellite + terrestrial
fusion. The open literature does not contain a calibrated probabilistic fusion
model with published performance.

**What would make it yours:** a Bayesian or graph-based fusion with explicit
priors and a reported **false-alarm rate per km per year**. This is the most
commercially valuable direction and the hardest to validate without a utility
partner.

### 5.5 Detect vegetation that behaves unusually during drought

Compare vegetation above the pipe with matched vegetation away from it. If a
narrow strip stays green through repeated droughts, investigate.

**Evidence:** demonstrated in dry regions; the Cyprus study used exactly this
logic (with moisture indices outperforming NDVI). Older work along a 25 km
corridor reduced the field-search area substantially.

**Limitation:** irrigation, soil differences and springs produce the same
effect. Strongest as an **independent confirmation** of a radar anomaly.

### 5.6 Use existing telecom fibre as an acoustic sensor

**Dark fibre DAS** turns unused telecommunications fibre in the same ducts as
water mains into a continuous acoustic array.

**Evidence:** Sharif et al. (2026, *Sensors* 26(7), 2152) ran a real urban field
trial over **17 km of fibre** with **2.6 m spatial resolution**, detecting
controlled leaks with a sparse-autoencoder anomaly detector, benchmarked
against a commercial acoustic leak detector.

**Why it is interesting:** it is continuous, city-scale, and uses infrastructure
that already exists. It is the natural **confirmation tier** for a satellite
screening product, not a competitor to it.

### 5.7 Actively heat a sensing cable and measure the cooling

Apply controlled heating to a fibre along a pipe; saturated soil and moving
seepage change the thermal response.

**Evidence:** D'Aniello et al. (2024, *Tunnelling and Underground Space
Technology*) modelled the thermal response of actively heated fibre to
background leakage in water mains, including heating power and time.

**Role:** premium confirmation for high-value sections (transmission mains,
dams, reservoirs). Not a satellite method, but a strong "what next" slide.

---

## 6. TerraGuard Leak Intelligence — the architecture

A **physics-informed, temporal, multisensor anomaly-detection** system. The
design principle: **learn what normal looks like, then flag persistent
departures** — do not train a classifier to recognise leaks from a handful of
labelled images.

```
┌──────────────────────────────────────────────────────────────────┐
│ 0. CORRIDOR                                                     │
│    Pipe network (GIS / OSM) → analysis segments of 100–500 m     │
│    Buffer 50–150 m. Every prediction is tied to a segment.       │
└───────────────────────────┬──────────────────────────────────────┘
                            ▼
┌──────────────────────────────────────────────────────────────────┐
│ 1. EXPECTED-CONDITION MODEL                                     │
│    Predict σ⁰, NDMI and thermal behaviour from weather +        │
│    soil + vegetation + season.                                   │
│    σ̂⁰_t = f(rain_t−30:t, T_t, NDVI_t, soil, season, angle)       │
│    residual A_t = σ⁰_obs,t − σ̂⁰_t                                │
└───────────────────────────┬──────────────────────────────────────┘
                            ▼
┌──────────────────────────────────────────────────────────────────┐
│ 2. TEMPORAL ANOMALY                                             │
│    Persistence, change-point, isolation forest, then TCN        │
│    Output: anomaly score + onset date + duration                │
└───────────────────────────┬──────────────────────────────────────┘
                            ▼
┌──────────────────────────────────────────────────────────────────┐
│ 3. EVIDENCE FUSION                                              │
│    Radar residual + thermal inertia + optical moisture +        │
│    hydraulic residual + repair history                          │
│    Output: calibrated probability, not a raw score              │
└───────────────────────────┬──────────────────────────────────────┘
                            ▼
┌──────────────────────────────────────────────────────────────────┐
│ 4. INSPECTION PRIORITY MAP                                      │
│    Ranked segments with evidence, uncertainty and recommended    │
│    field check (acoustic / GPR / visual)                        │
└──────────────────────────────────────────────────────────────────┘
```

### 6.1 Stage 1 — expected-condition model

The core equation:

```
σ̂⁰_t = f( R_{t−30:t}, T_t, NDVI_t, soil, season, incidence angle, track )
A_t   = σ⁰_observed,t − σ̂⁰_t
```

**Features:**

- Rainfall: cumulative 1, 3, 7, 14, 30 days (IMERG or ERA5-Land)
- Temperature: air temp, soil temp, freeze/thaw flag
- Vegetation: NDVI, NDMI at the same date
- Soil: clay fraction, sand fraction, organic carbon (SoilGrids)
- Geometry: incidence angle, pass direction, relative orbit
- Season: day of year, harmonics

**Model:** start with **XGBoost or LightGBM** regression. It handles missing
data, is interpretable with SHAP, trains in minutes, and is easy to defend.
A neural network buys little at this stage.

**Training data:** historical **normal-condition** observations. You do not need
thousands of leaks. You do need to exclude known leak periods and disturbances
from the baseline — use the utility's repair records where available.

**Critical detail:** train and validate **per track and per land-cover class**.
A model trained on one relative orbit will not transfer to another.

### 6.2 Stage 2 — temporal anomaly detection

| Model | Purpose | When to use |
|---|---|---|
| **Persistence rule** | Flag residuals above threshold for ≥2 consecutive dates | First, always. Baseline for everything else |
| **Change-point detection** (PELT, BOCPD) | Find when an anomaly starts | Onset dating, repair-response analysis |
| **Isolation Forest** | Unusual feature combinations | Unsupervised baseline, no labels |
| **XGBoost classifier** | Leak vs non-leak with labels | Once you have confirmed leaks |
| **Temporal CNN / TCN** | Learn sequence shape | When you have >100 labelled events |
| **ConvLSTM** | Spatial + temporal moisture patterns | Research |
| **Multimodal transformer** | Fuse SAR, optical, thermal | Only after simpler baselines |

**Do not start with a transformer.** Start with persistence + change-point +
XGBoost, then benchmark anything fancier against it. If the fancy model does not
beat the simple one on a spatially blocked test set, the simple one wins.

### 6.3 Stage 3 — repair records as a natural experiment

The most convincing validation available to a small team:

```
anomaly appears → leak confirmed → pipe repaired → anomaly disappears
```

This temporal signature is much stronger than "wet ground near a pipe". It is
not conclusive — excavation, backfill and vegetation disturbance also change the
signal — but it is a **retrospective labelled dataset** you can build from
public repair records.

**Implementation:** for each confirmed repair, extract the residual time series
for the segment, and test whether the anomaly amplitude drops after the repair
date relative to matched control segments. Report the effect size.

### 6.4 Stage 4 — corridor and graph constraint

Do not produce a free-floating heatmap. Produce a **ranked list of pipe
segments**.

- **Nodes:** valves, junctions, pumps, DMA boundaries, meters.
- **Edges:** pipe sections with diameter, material, age, depth.
- **Observations:** radar residual, optical moisture, thermal, pressure/flow.

A simple network-constrained Bayesian model is easier to defend than a GNN.
The constraint does most of the work: a moisture anomaly **on** a pipe is worth
far more than one 200 m away.

### 6.5 Confidence scoring

A transparent score beats an opaque probability:

```
confidence = w1·radar_residual
           + w2·persistence
           + w3·weather_unexplained
           + w4·corridor_proximity
           + w5·optical_agreement
           + w6·thermal_agreement
           + w7·hydraulic_anomaly
           − w8·rainfall_explanation
```

Publish the weights and the ablation. Judges and utilities both trust a system
that shows its reasoning.

---

## 7. Novelty — what to claim

ESA has already funded SECO, WATERLENS and ZOE (§2.7). ASTERRA and Utilis are
commercial. MDFLD-Net and Yan et al. are published. **"SAR + NDVI" is not novel.**

Three defensible directions:

### Direction A — weather-normalised leak anomaly detection

**Research question:** can we identify persistent moisture anomalies that
rainfall, soil, season and vegetation cannot explain?

**Why it is novel:** the published SAR leak models (MDFLD-Net, Yan) are
**classifiers on hand-picked dates**, not **residual models against an
environmental expectation**. Nobody has published a rigorous ablation showing
how much leak-detection skill survives weather normalisation.

**Deliverable:** a residual model, a spatial-block validation, and a
false-alarm rate per km per year.

**Risk:** low. **Effort:** medium. **Best satellite-only PoC.**

### Direction B — radar + thermal + hydraulic fusion

**Research question:** does multi-signature fusion outperform radar-only
screening?

**Why it is novel:** ESA projects describe fusion; the open literature does not
contain a calibrated probabilistic fusion with published performance. The
thermal-inertia channel in particular is under-exploited.

**Deliverable:** a fusion model with per-channel ablation and calibrated
uncertainty.

**Risk:** medium (needs hydraulic data). **Effort:** high. **Best operational
direction.**

### Direction C — physics-informed leak-evolution modelling

**Research question:** can we predict how a leak's moisture plume evolves in
different soils, and use the predicted temporal signature to identify candidate
leaks?

**Why it is novel:** coupling variably saturated flow (Richards equation) to
electromagnetic scattering is established in GPR research but has not been
transferred to satellite time series.

**Deliverable:** a forward model of σ⁰(t) for a given leak rate, soil and depth,
compared with observed time series.

**Risk:** high. **Effort:** high. **Best research direction, weakest hackathon
fit.**

### What *TerraGuard* can uniquely claim in a 48-hour build

Pick one sentence and defend it:

> "We detect **persistent, weather-unexplained moisture anomalies along known
> water-pipeline corridors**, using NISAR L-band as the primary observable,
> Sentinel-1 as the temporal backbone, and Sentinel-2/ECOSTRESS as independent
> corroboration — and we validate against public water-main-break records."

That is honest, specific, and testable.

---

## 8. Data — what to get, and what it can actually do

### 8.1 SAR (primary)

| Dataset | Product | Resolution | Coverage | Access | Cost |
|---|---|---|---|---|---|
| **NISAR L-band** | GCOV, GSLC, GUNW, SME2 | 10/20/80 m; 5–40 m SLC; 200 m soil moisture | Global land, **Oct 2025 →** | [ASF Vertex](https://search.asf.alaska.edu/), `asf_search`, `earthaccess` | Free, Earthdata login |
| **Sentinel-1** | GRD, SLC | 10 m GRD; 5×20 m SLC | Global, **2014 →** | [Copernicus Data Space](https://dataspace.copernicus.eu/), ASF, [GEE](https://earthengine.google.com/) | Free |
| **Sentinel-1 InSAR on demand** | HyP3 interferogram, coherence | 20–80 m | 2014 → | [ASF HyP3](https://hyp3-docs.asf.alaska.edu/) | Free (quota) |
| **ARIA S1 GUNW** | Unwrapped interferogram | 90 m | 2014 → | ASF / Earthdata | Free |
| **EGMS** | Ground-motion points | 5×20 m points; 100 m grid | **EU27 + Iceland + Norway + UK**, 2015/2020–2025; **sparse in rural corridors** | [EGMS](https://egms.land.copernicus.eu/) | Free, EU login |
| **COMET-LiCS** | Ready interferograms + coherence | ~100 m | Global S1 frame grid, 2014 → | [COMET-LiCS](https://comet.nerc.ac.uk/comet-lics-portal/) | Free |
| **SAOCOM-1** | L-band quad-pol | 10–100 m | 2018 → | CONAE catalogue | Free with registration |
| **ALOS-2** | L-band | 3–100 m | 2014 → | JAXA G-Portal | Free for research |
| **TerraSAR-X / PAZ** | X-band | 1–3 m | 2007 → | DLR proposal | Free for science |

**Which NISAR product for which job:**

- **GCOV (10 m)** — backscatter change, dual-pol ratios, corridor mapping.
  This is your default.
- **GUNW (80 m)** — deformation, without running a processor. Too coarse for a
  corridor, fine for a subsidence region.
- **GSLC (5–40 m)** — only if you need your own coherence or closure phase.
- **SME2 (200 m)** — soil moisture, **but 200 m is 10× too coarse for a 20 m
  corridor**, and no VALIDATED collection exists yet. Use as regional context.

**The NISAR trap, stated plainly:** the archive starts **October 2025**. You
cannot study a historical leak with NISAR. VALIDATED products only exist from
**2026-10-21**; PROVISIONAL from 2026-06-17; do not mix maturity levels in a
time series. There is a permanent gap **2026-07-27 → 2026-08-10**. NISAR's
repeat is **12 days**, giving ~25–35 scenes per track per year. That is enough
for a short stack, not a multi-year trend.

**Two geometry and access details that bite in joint analysis:**

- **NISAR is left-looking; Sentinel-1 is right-looking.** The line-of-sight
  projection and the sign of the geometry differ. Do not co-stack them without
  accounting for look direction.
- **Sentinel-1 SLC archives differ by portal.** ASF has global SLC from 2014;
  CDSE's SLC archive outside Europe starts around February 2021. For a long
  non-European baseline, use ASF.

**Ready-made InSAR without processing:** ARIA-S1-GUNW (ASF, 2014–present,
~30 m posting) and COMET-LiCS (~100 m) let you skip ISCE2/SNAP entirely.
OpenScienceLab provides free cloud notebooks with MintPy and HyP3 pre-installed.

**Practical staging:** use **Sentinel-1 (2018–2026)** to build and validate the
model, then apply the same pipeline to **NISAR** for the most recent year and
compare L-band vs C-band. That is a legitimate, honest use of both missions.

### 8.2 Optical and SWIR

| Dataset | Use | Resolution | Access |
|---|---|---|---|
| **Sentinel-2** | NDMI, NMDI, NDVI, route finding | 10–20 m | CDSE, GEE |
| **PlanetScope** | 3 m context, dry-season contrast | 3 m | Planet education/research quota |
| **SkySat** | 0.5–0.8 m confirmation | 0.5–0.8 m | Planet, commercial |
| **Landsat 8/9** | Long baseline, land cover | 30 m | USGS EarthExplorer, GEE |
| **PRISMA / EnMAP** | Hyperspectral moisture/stress | 30 m | ASI / DLR, proposal |

### 8.3 Thermal

| Dataset | Pixel | Revisit | Access | Honest use |
|---|---|---|---|---|
| **Landsat 8/9 TIRS** | 100 m | 16 d each, 8 d combined | Free | Large wet patches, thermal inertia with day/night pairs |
| **ECOSTRESS** | 38×69 m | ~1–5 d, variable | [LP DAAC](https://lpdaac.usgs.gov/products/eco3etptjplv001/) | 15–30 m halos; ET |
| **ASTER** | 90 m | 16 d | Free | Legacy, emissivity; SWIR failed 2008 |
| **Sentinel-3 SLSTR** | 1 km | daily | Free | Regional context only |
| **SatVu HotSat** | **3.5 m** | tasking | Commercial | Pipeline-scale halo; **no water-leak validation** |
| **Airborne / UAV TIR** | 0.1–1 m | on demand | Survey | The demonstrated confirmation tool |

**Reality check:** SatVu HotSat-2 has been commercially operational since June
2026, HotSat-3 launched October 2026. 3.5 m MWIR, ~2 K accuracy, ~16 km² scenes.
It is the first commercial satellite that can plausibly see a pipeline-scale
thermal halo — but there is **no published demonstration of it detecting a
buried water leak**. Treat it as a research opportunity, and check cost and
tasking before designing around it.

### 8.4 Environmental covariates

| Dataset | Variable | Resolution | Access |
|---|---|---|---|
| **IMERG** | Precipitation, 30 min | 0.1° | NASA GES DISC |
| **ERA5-Land** | Temp, soil moisture, ET, wind | 9 km, hourly | [Copernicus CDS](https://cds.climate.copernicus.eu/) |
| **SMAP L3/L4** | Soil moisture | 9–36 km | [NSIDC](https://nsidc.org/data/smap) |
| **ESA CCI / S1 soil moisture** | Soil moisture | 1 km | CDSE |
| **SoilGrids** | Texture, carbon, bulk density | 250 m | [soilgrids.org](https://soilgrids.org/) |
| **Copernicus DEM** | Terrain, slope | 30 m | CDSE |
| **ESA WorldCover** | Land cover | 10 m | GEE |

**Rainfall is mandatory.** Every backscatter or closure-phase anomaly must be
tested against precipitation for the preceding 1–5 days, or you will detect
every rainstorm as a leak.

### 8.5 Ground truth — the hardest part

Public, point-level water-leak data is scarce. Your options, in order of usefulness:

| Source | What it gives | Access | Caveat |
|---|---|---|---|
| **City open-data portals** | Dated water-main break points | See table below | Break ≠ leak; repairs are the label |
| **Utility repair records** | Confirmed leaks, pipe attributes | Partner agreement | Best data; usually not public |
| **Acoustic/GPR survey reports** | Confirmed leak locations | Partner | Small samples |
| **News reports of main breaks** | Geocodable events | Web | Incomplete, biased to big bursts |
| **LeakDB** | Simulated leak scenarios, pressure/flow | [GitHub](https://github.com/KIOS-Research/LeakDB) | **No satellite signature** — hydraulic branch only |
| **BattLeDIM / L-Town** | Hydraulic benchmark with labelled leaks | [Zenodo](https://doi.org/10.5281/zenodo.4017659) | Simulated; not satellite training data |

**City portals with point-level water-main-break data** (verify current terms
before use):

| City | Dataset | Why it is useful |
|---|---|---|
| **Toronto** | [Watermain Breaks](https://open.toronto.ca/dataset/watermain-breaks/) + [Watermains](https://open.toronto.ca/dataset/watermains/) | Both break records **and** the pipe network with diameter/material — the rare complete pair |
| **New York City** | Water main breaks since 2009/2010 | Large, long record; dense network |
| **Chicago** | Water pipe breaks / open repository | Long record; flat terrain |
| **Madison, WI** | [Water main breaks](https://data-cityofmadison.opendata.arcgis.com/maps/water-main-breaks) | Clean, small, easy |
| **Washington DC** | [DC Water open data](https://www.dcwater.com/resources/open-data-portal) | Utility-run portal |
| **Oklahoma City** | Open data portal | Includes utility layers |

**The honest caveat:** a *break* is a burst, not a background leak. Bursts are
often repaired within hours, before a satellite overpass. Background leaks are
the bigger volume but are rarely in public records. So public break data is a
**weak label** — useful for "did an anomaly appear near a reported event", not
for training a production classifier.

**Best realistic validation for a hackathon:** the **repair-response test**
(§6.3) on a handful of well-documented breaks, plus a **spatial-block
holdout** on the anomaly detector itself. Be explicit that the labels are weak.

---

## 9. Validation and metrics

### 9.1 The protocol

1. **Positive set:** confirmed leaks/repairs with coordinates and dates.
2. **Negative set:** matched segments on the same network, same land cover, same
   season, no reported event.
3. **Spatial block split** — hold out whole districts, not random points. Random
   splits leak information through spatial autocorrelation and inflate accuracy.
4. **Temporal split** — train on earlier years, test on later ones.
5. **Ablation** — radar only; + rain; + optical; + thermal; + hydraulic.

### 9.2 The metrics that matter

| Metric | Why |
|---|---|
| **Recall at fixed precision** | Utilities cannot chase unlimited false alarms |
| **False alarms per km per year** | The operational cost metric |
| **Inspection effort saved (%)** | The commercial value metric (Arabi 2026 reports 93 %) |
| **Localisation error (m)** | Whether the crew can find it |
| **Onset-date error (days)** | Whether it is early enough to matter |
| **Precision-recall AUC** | Threshold-free comparison |

Do **not** report accuracy alone. A 95 % accuracy on a dataset with 2 % leaks is
worse than useless.

### 9.3 Sanity checks before believing an anomaly

1. Same track, same pass direction, same incidence angle?
2. Did it rain in the previous 5 days?
3. Did vegetation change (NDVI)?
4. Is it aligned with a pipe, or a random blob?
5. Does it persist for 2–6 weeks?
6. Is the ground frozen?
7. Is it irrigation, a pond, or a drainage feature?
8. Did the anomaly disappear after a reported repair?

---

## 10. The 48-hour build plan

Two people, two days, one study area, one story. Scope ruthlessly.

### 10.1 Choose the study area first

Two competing requirements:

- **Signal:** a dry/semi-arid city gives strong moisture contrast and low
  vegetation masking.
- **Labels:** a city with open break records and pipe GIS gives validation.

If you cannot have both, **prioritise signal** and use qualitative validation
(news reports, a handful of documented breaks). A visible, physically explained
anomaly is a better demo than a statistically rigorous null result.

**Shortlist:**

| Site | Signal | Labels | NISAR | Verdict |
|---|---|---|---|---|
| **Toronto** | Medium (vegetation, snow) | **Excellent** (breaks + pipes) | Yes | Best for method + validation |
| **Madison, WI** | Medium | Good (breaks) | Yes | Small, clean, fast |
| **Cyprus (Doros/Monagri)** | **Strong** (semi-arid) | Published case study | Yes | Best for physics story |
| **Beijing/Tianjin** | Medium | Published (not public) | Yes | Reproduce MDFLD-Net conceptually |
| **Phoenix / Tucson** | **Strong** | Sparse | Yes | Best visual, weakest labels |
| **A dry EU city** (e.g. Murcia, Zaragoza) | Strong | Sparse (EGMS helps) | Yes | Good compromise |

### 10.2 Day 1

| Time | Task | Output |
|---|---|---|
| 0–2 h | Pick corridor + dates. Confirm NISAR and Sentinel-1 coverage. | Scene list, track/frame locked |
| 2–4 h | Download Sentinel-1 GRD strip and NISAR GCOV clip. Subset to corridor. | 2–10 GeoTIFFs |
| 4–6 h | Build the σ⁰ baseline and the rainfall covariate. Plot the time series of 20 random corridor pixels. | Baseline figure |
| 6–8 h | Implement the residual + persistence rule. Threshold. Overlay the pipe network. | First anomaly map |
| 8–10 h | Add Sentinel-2 NDMI and (if available) one ECOSTRESS scene. | Multi-layer map |

### 10.3 Day 2

| Time | Task | Output |
|---|---|---|
| 0–3 h | Validate: overlay documented breaks; run the repair-response test if data exists. | Validation table |
| 3–5 h | Build the interactive map: time slider, corridor profile, click → evidence panel. | Working demo |
| 5–7 h | Write the physics panel: dielectric constant, penetration depth, L vs C band, why dry-season matters. | Story content |
| 7–9 h | Record the demo, write the summary, state limitations. | Submission |

### 10.4 The minimum viable demo

If everything slips:

> One NISAR GCOV pair → residual against a Sentinel-1 seasonal baseline →
> corridor overlay → one documented break → one paragraph of physics.

That is enough to be credible, and it is achievable in a day.

### 10.5 What not to do

- Do not attempt full InSAR time-series processing from scratch.
- Do not download 500 scenes.
- Do not build a deep-learning model on 20 labels.
- Do not claim metre-level localisation.
- Do not present a wet pixel as a confirmed leak.
- Do not forget the rainfall layer — it is the difference between a detector and
  a rain detector.

---

## 11. Limitations to state explicitly

1. **No published minimum detectable leak rate.** The method detects
   consequences, not leaks, and the detection probability depends on soil,
   depth, vegetation, leak rate and weather.
2. **Resolution mismatch.** A 10–20 m pixel is 10–100× wider than a pipe. You
   produce **segment-level** candidates, not leak points.
3. **Weak labels.** Public break records are bursts, not background leaks, and
   are biased to visible events.
4. **Confounders are strong.** Rainfall, irrigation, drainage, freeze/thaw,
   construction and vegetation management all mimic the signal.
5. **L-band is not a moisture meter.** It responds to integrated dielectric
   change over a depth interval; retrieval is model-dependent.
6. **Closure phase is contested.** One camp says it retrieves soil moisture; the
   other says it cannot (Molan 2020 vs Wig 2024).
7. **NISAR is one year old.** No multi-year trend, no validated soil-moisture
   collection, and no historical event.
8. **Thermal at free resolution cannot see a pipe.** Only large wet patches and
   high-resolution commercial/airborne TIR are viable.
9. **False alarms are the norm.** The best published unsupervised result had
   81 % recall **with many false positives**; the best commercial programme
   still used acoustics to confirm every site.
10. **Ethics and privacy.** High-resolution imagery of private property and
    infrastructure has security implications. Do not publish critical
    infrastructure locations or leak vulnerabilities.

---

## 12. References

Verified DOIs and URLs. Accessed 2026-11-14.

### Water-leak detection: satellite and multisensor

1. Li, et al. (2025). A SAR-based deep multi-feature fusion network (MDFLD-Net)
   for water leakage detection. *International Journal of Applied Earth
   Observation and Geoinformation*. doi:10.1016/j.jag.2025.104915
2. Arabi, et al. (2026). Automated detection of pipe water leaks under paved
   surfaces with machine learning analysis of satellite radar data. *Journal of
   Environmental Management*. doi:10.1016/j.jenvman.2026.129209
3. Zhang, et al. (2025). Combined L-Band Polarimetric SAR and GPR Data to
   Develop Models for Leak Detection in the Water Pipeline Networks. *Remote
   Sensing* 17(8), 1386. doi:10.3390/rs17081386
4. Yan, Y. et al. (2024). Interpretable PCA and SVM-Based Leak Detection
   Algorithm for Identifying Water Leakage Using SAR-Derived Moisture Content
   and InSAR Closure Phase. *IEEE JSTARS*.
   doi:10.1109/JSTARS.2024.3443127
5. Eslam Ali, et al. (2025). Scalable Detection of Underground Water Leaks in
   Dense Urban Environments Using L-Band SAR and Machine Learning. *ISPRS
   Archives* XLVIII-G-2025.
   doi:10.5194/isprs-archives-xlviii-g-2025-147-2025
6. Theocharidis, C. et al. (2025). Detection of Water Pipeline Leakages Using
   High-Resolution Satellite Imagery and Auxiliary Ground Data in Cyprus.
   *SPIE Sensors + Imaging*. doi:10.1117/12.3069672
7. Fajardo, et al. (2025). Water leak detection through satellite imagery and
   deep learning. *Sustainable Water Resources Management*.
   doi:10.1007/s40899-025-01212-9
8. Sharif, et al. (2026). Urban Water Leakage Detection System over Dark Fiber
   Networks Based on Distributed Acoustic Sensing and Sparse Autoencoders.
   *Sensors* 26(7), 2152. doi:10.3390/s26072152
9. Bretreger, et al. (2025). Using drone-based LiDAR intensity measurements to
   identify underground water pipe leaks through wet surface detection.
   *Sustainable and Resilient Infrastructure*.
   doi:10.1080/23789689.2025.2523707
10. D'Aniello, et al. (2024). Thermal response to background leakages around an
    actively heated fiber optic sensor for leak detection in water distribution
    mains. *Tunnelling and Underground Space Technology*.
    doi:10.1016/j.tust.2024.105904
11. SUEZ / ASTERRA (2025). *Satellite Leak Detection finds 902 leaks across
    9,000 km — Affinity Water Case Study*.
    https://www.suez.com/en/uk/case-studies/satellite-leak-detection-delivers-results-affinity-water

### SAR physics and methods

12. Stanyer, C. et al. (2025). Soil Texture, Soil Moisture, and Sentinel-1
    Backscattering. *Remote Sensing* 17(3), 542. doi:10.3390/rs17030542
13. Peng, W. et al. (2026). Detection of soil moisture variations beneath an
    asphalt layer using L-band SAR. *International Journal of Applied Earth
    Observation and Geoinformation*. doi:10.1016/j.jag.2026.105592
14. Wig, E. et al. (2024). Fine-Resolution Measurement of Soil Moisture From
    Cumulative InSAR Closure Phase. *IEEE TGRS*.
    doi:10.1109/TGRS.2024.3399069
15. Molan, Y. E. et al. (2020). Can InSAR Coherence and Closure Phase Be Used to
    Estimate Soil Moisture Changes? *Remote Sensing* 12(9), 1511.
    doi:10.3390/rs12091511
16. Gronnemose, W. et al. (2025). The Sensitivity of InSAR Closure Phase to
    Spatial Variations of Soil Structure and Moisture. *IEEE TGRS*.
    doi:10.1109/TGRS.2025.3570192
17. Karamvasis, K. et al. (2026). Toward Improved Soil Moisture Retrieval Using
    NISAR InSAR Closure Phase Measurements. EARSeL 2026.
    doi:10.5281/zenodo.23766604
18. Cigna, F. et al. (2021). Accuracy of Sentinel-1 PSI and SBAS InSAR
    Displacement Velocities against GNSS and Geodetic Leveling Monitoring Data.
    *Remote Sensing* 13(23), 4800. doi:10.3390/rs13234800
19. El Hajj, M. et al. (2019). Soil moisture retrieval over irrigated
    grasslands using X, C and L band SAR data. *Remote Sensing* 11(1), 31.
    doi:10.3390/rs11010031
20. Zwieback, S., Hensley, S., & Hajnsek, I. (2015). Assessment of soil
    moisture effects on L-band radar interferometry. *Remote Sensing of
    Environment* 164, 77–89. doi:10.1016/j.rse.2015.04.012
21. Theron, A. et al. (2017). Detection of sinkhole precursors through SAR
    interferometry: Radar interferometry for sinkhole detection. *IEEE
    Geoscience and Remote Sensing Letters* 14(6), 871–875.
    doi:10.1109/LGRS.2017.2684905
22. Bayramov, E., Buchroithner, M., & Kada, M. (2020). Quantitative assessment
    of ground deformation along the Baku–Tbilisi–Ceyhan and South Caucasus
    pipelines using Sentinel-1 InSAR. *Remote Sensing* 12(23), 3934.
    doi:10.3390/rs12233934
23. Zebker, H. A. (2021). Accuracy of a model-free algorithm for estimating
    atmospheric delay in InSAR. *Remote Sensing* 13(3), 409.
    doi:10.3390/rs13030409

### Thermal

19. Friman, O. et al. (2014). Methods for large-scale monitoring of district
    heating systems using airborne thermography. *IEEE TGRS* 52(8), 5175–5182.
    doi:10.1109/TGRS.2013.2287238
20. Eidenshink, J. C. (1985). Detection of leaks in buried rural water pipelines
    using thermal infrared images. *Photogrammetric Engineering and Remote
    Sensing* 51(5), 561–564.
21. Call, L. et al. (2025). Elevation models, shadows, and infrared: Integrating
    datasets for thermographic leak detection. *Remote Sensing* 17(14), 2399.
    doi:10.3390/rs17142399
22. Krapez, J.-C. et al. (2022). Multispectral optical remote sensing for
    water-leak detection. *Sensors* 22(3), 1057. doi:10.3390/s22031057
23. Risch, T. et al. (2026). Guided leak detection in district heating networks
    from aerial thermal imagery. *ISPRS Annals* X-4/W8-2025, 623–629.
    doi:10.5194/isprs-annals-X-4-W8-2025-623-2026
24. Vollmer, E. et al. (2025). Leak detection using thermal imagery: Deep
    learning versus traditional computer vision. *ISPRS Journal of
    Photogrammetry and Remote Sensing*.
    doi:10.1016/j.isprsjprs.2025.06.006

### Optical

25. van der Werff, H. et al. (2008). A spatial-spectral approach for
    visualization of vegetation stress resulting from pipeline leakage.
    *Sensors* 8(6), 3733–3743. doi:10.3390/s8063733
26. Ma, P. et al. (2024). Natural gas induced vegetation stress identification
    and discrimination from hyperspectral imaging for pipeline leakage
    detection. *Remote Sensing* 16(6), 1029. doi:10.3390/rs16061029

### Ground and hydraulic

29. Hu, Z., Tariq, S., & Zayed, T. (2021). A comprehensive review of acoustic
    based leak localization method in pressurized pipelines. *Mechanical Systems
    and Signal Processing* 161, 107994.
    doi:10.1016/j.ymssp.2021.107994
30. Stajanca, P. et al. (2018). Detection of leak-induced pipeline vibrations
    using fiber-optic distributed acoustic sensing. *Sensors* 18(9), 2841.
    doi:10.3390/s18092841
31. Korlapati, N. V. S. et al. (2022). Review and analysis of pipeline leak
    detection methods. *Journal of Pipeline Science and Engineering*.
    doi:10.1016/j.jpse.2022.100074
32. Vrachimis, S. G. et al. (2020). BattLeDIM: Battle of the Leakage Detection
    and Isolation Methods. doi:10.5281/zenodo.4017659
33. KIOS Research Centre. LeakDB. https://github.com/KIOS-Research/LeakDB

### Missions and data

34. NISAR Data User Guide. https://nisar-docs.asf.alaska.edu/ —
    availability, GCOV, GUNW, SME2, known issues.
35. European Ground Motion Service. https://egms.land.copernicus.eu/
36. ESA Space Solutions — SECO. https://business.esa.int/projects/seco
37. ESA Space Solutions — WATERLENS. https://business.esa.int/projects/waterlens
38. ESA Space Solutions — ZOE. https://business.esa.int/projects/zoe
39. ESA Space Solutions — GeoAI_Watloss.
    https://business.esa.int/projects/geoaiwatloss
40. SatVu HotSat specifications. https://www.satellitevu.com/
41. NASA LP DAAC — ECOSTRESS. https://lpdaac.usgs.gov/products/eco3etptjplv001/
42. Copernicus Data Space Ecosystem. https://dataspace.copernicus.eu/
43. City of Toronto Open Data — Watermain Breaks.
    https://open.toronto.ca/dataset/watermain-breaks/
44. City of Toronto Open Data — Watermains.
    https://open.toronto.ca/dataset/watermains/

---

## Appendix A — Two calculations for the slide deck

**1. Why 100 m thermal cannot see a water leak.**

```
water leak ΔT (generous, summer evaporative cooling) = 5 K
required pixel anomaly to beat LST accuracy          = 2 K
required fill fraction f = 2 / 5                     = 0.40
Landsat pixel 100 m  → anomaly must be ≥ 40 m wide
ECOSTRESS 38 m       → anomaly must be ≥ 15 m wide
HotSat 3.5 m         → anomaly must be ≥ 1.4 m wide
```

A 1 m pipe plus a 2 m halo is 3 % fill at Landsat → 0.15 K. **Invisible.**

**2. How big a leak a 1 dB SAR change represents.**

```
sandy loam: 1.69 % volumetric water content per dB
            3 dB  ≈ +5.1 % SM  (a realistic leak footprint)
clay:       4.81 % per dB
            3 dB  ≈ +14.4 % SM (needs a much wetter leak)
```

This is why the same leak is easier to see in sand than in clay, and why a
result from Arizona does not transfer to Toronto.

---

## Appendix B — Starter code

Documented access patterns; not tested against a live account.

### B.1 Find NISAR and Sentinel-1 over a corridor

```python
import asf_search as asf

aoi = "POLYGON((-79.42 43.68,-79.32 43.68,-79.32 43.62,-79.42 43.62,-79.42 43.68))"

nisar = asf.search(
    dataset="NISAR",
    processingLevel="GCOV",
    intersectsWith=aoi,
    start="2025-10-01T00:00:00Z",
    end="2026-11-14T23:59:59Z",
)
print(len(nisar), "NISAR GCOV scenes")

s1 = asf.search(
    dataset="SENTINEL-1",
    processingLevel="GRD_HD",
    beamMode="IW",
    intersectsWith=aoi,
    start="2018-01-01T00:00:00Z",
    end="2026-11-14T23:59:59Z",
    polarization="VV+VH",
)
print(len(s1), "Sentinel-1 IW GRD scenes")
```

Filter to **one relative orbit, one direction, one frame** before building a
time series. Mixing tracks creates look-angle differences that look like change.

### B.2 Read one NISAR GCOV layer without downloading the frame

```bash
export GDAL_HTTP_NETRC=YES
export GDAL_HTTP_COOKIEFILE=/tmp/cookies.txt
export GDAL_HTTP_COOKIEJAR=/tmp/cookies.txt

URL="https://<download-url-from-vertex>"

gdalinfo "/vsicurl/${URL}"

gdal_translate -of GTiff \
  -projwin_srs EPSG:4326 -projwin -79.42 43.68 -79.32 43.62 \
  "/vsicurl/${URL}"://science/LSAR/GCOV/grids/frequencyA/HHHH \
  corridor_hh.tif
```

List the subdatasets first. Term names have appeared as both `HH` and `HHHH`,
and which polarizations exist depends on the acquisition mode.

### B.3 Residual anomaly in Google Earth Engine

```javascript
var corridor = pipes.map(function(f) { return f.buffer(150); });

var col = ee.ImageCollection('COPERNICUS/S1_GRD')
  .filterBounds(corridor)
  .filter(ee.Filter.eq('instrumentMode', 'IW'))
  .filter(ee.Filter.eq('orbitProperties_pass', 'DESCENDING'))
  .filter(ee.Filter.eq('relativeOrbitNumber_start', 114))
  .select('VV');

// Seasonal baseline: same 60-day window across all years
var baseline = col.filter(ee.Filter.calendarRange(6, 8, 'month')).median();

var drySeason = col.filterDate('2024-07-01', '2024-08-15').median();

var anomaly = drySeason.subtract(baseline).rename('dB_anomaly');
Map.addLayer(anomaly.clip(corridor),
  {min: -4, max: 4, palette: ['red', 'white', 'blue']},
  'Dry-season residual');
```

Then threshold `anomaly > 1.5` dB, require the connected component to touch the
corridor, and reject dates within 2 days of >5 mm IMERG rainfall.

### B.4 The four checks that kill most false positives

1. Frozen ground? (soil temp < 0 °C)
2. Rain in the last 5 days?
3. Vegetation change (NDVI)?
4. Aligned with the pipe, and persistent for ≥ 2 dates?

---

*Compiled 2026-11-14 for the TerraGuard project. NISAR availability facts are
as of this date and will change; re-check
`nisar-docs.asf.alaska.edu/availability-overview` before relying on them.*
