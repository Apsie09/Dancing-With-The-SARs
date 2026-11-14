# Earth Observation and Remote Sensing: Fundamentals

A practical introduction to electromagnetic waves, satellite sensors, radar bands, environmental limitations, applications, and multisensor data fusion.

## 1. What is remote sensing?

Remote sensing means learning about an object or area without touching it. Earth-observation satellites measure electromagnetic radiation or other physical effects to infer properties of the atmosphere, oceans, land, ice, and human-built structures.

A satellite does not always produce a photograph. Its measurements may be radar backscatter, reflected sunlight, thermal emission, laser travel time, atmospheric absorption, or changes in the Earth's gravitational field.

Three questions help explain any sensor:

1. **What does it measure directly?** Examples: reflected radiation, emitted radiation, echo power, echo phase, or travel time.
2. **Which physical properties influence that measurement?** Examples: water content, temperature, roughness, chemical composition, surface height, and geometry.
3. **Under which conditions is the measurement reliable?** Examples: daylight, cloud cover, rain, snow, vegetation, and viewing angle.

**Direct measurement is not the same as a derived quantity.** For example, SAR directly measures properties of returned microwave signals; estimating soil moisture from those signals requires a model and assumptions.

## 2. Electromagnetic waves and wavelength

Electromagnetic radiation includes visible light, infrared, microwaves, and radio waves. All are governed by the relationship:

\[
\lambda = \frac{c}{f}
\]

Where:

- `λ` is wavelength, in metres (m).
- `f` is frequency, in hertz (Hz).
- `c` is the speed of light in vacuum, approximately `3 × 10^8 m/s`.

As frequency increases, wavelength decreases.

| Example | Frequency | Wavelength |
|---|---:|---:|
| Green visible light | ~545 THz | ~550 nm |
| Thermal infrared | ~30 THz | ~10 µm |
| X-band radar | 10 GHz | 3 cm |
| C-band radar | 5.4 GHz | 5.6 cm |
| L-band radar | 1.3 GHz | 23 cm |
| P-band radar | 435 MHz | 69 cm |

Unit conversions:

- `1 GHz = 10^9 Hz`.
- `1 MHz = 10^6 Hz`.
- `1 mm = 10^-3 m`.
- `1 µm = 10^-6 m`.
- `1 nm = 10^-9 m`.

### Why wavelength matters

Waves interact differently with objects depending on the wavelength relative to the object's structure and the object's electromagnetic properties. Leaves, branches, droplets, snow grains, bare soil, and buildings therefore respond differently at different wavelengths.

Wavelength alone does not determine penetration or image resolution. Material moisture, electrical conductivity, dielectric properties, surface roughness, radar bandwidth, instrument design, and viewing geometry also matter.

## 3. Active and passive sensors

**Passive sensors** detect radiation that already exists. They may measure reflected sunlight (optical imaging), naturally emitted thermal infrared radiation (surface temperature), or natural microwave emission (microwave radiometry).

**Active sensors** transmit energy and detect its return. Examples include SAR, radar altimeters, precipitation radar, and LiDAR. Their own illumination lets many active sensors operate at night.

| Technology | Active/passive | Direct observation | Commonly derived information |
|---|---|---|---|
| Visible/multispectral imaging | Passive | Reflected sunlight | Land cover, vegetation indices, water boundaries |
| Hyperspectral imaging | Usually passive | Detailed spectrum in many narrow bands | Minerals, vegetation traits, some gases |
| Thermal infrared imaging | Passive | Emitted infrared radiation | Surface or cloud-top temperature |
| Synthetic aperture radar (SAR) | Active | Microwave echo amplitude and often phase | Flood extent, surface change, deformation |
| Microwave radiometry | Passive | Microwave brightness temperature | Soil moisture, snow, sea ice, atmospheric properties |
| LiDAR/laser altimetry | Active | Laser echo travel times and waveform/photon returns | Surface elevation, canopy height |
| Radar altimetry | Active | Radar range/echo characteristics | Sea level, lake and river elevation, ice height |
| Precipitation/cloud radar | Active | Echoes from hydrometeors | Rain, snow, cloud vertical structure |
| Scatterometry | Active | Radar backscatter from several views | Ocean surface winds and roughness |
| GNSS reflectometry | Passive/bistatic receiver | Reflected navigation-satellite signals | Surface reflectivity, ocean winds, inundation indicators |
| Gravimetry | Non-imaging geophysical measurement | Changes in gravity-related satellite motion | Large-scale water and ice mass changes |

The label *hyperspectral* describes spectral sampling, not a particular part of the electromagnetic spectrum. A hyperspectral instrument can operate in visible/infrared ranges, and some instruments are designed for thermal infrared.

## 4. How the atmosphere affects observations

Atmospheric molecules, cloud droplets, ice crystals, rain, and aerosols can absorb or scatter radiation. The strength of these effects depends heavily on wavelength.

### Clouds and fog

Clouds and fog scatter visible and near-infrared light, often preventing cameras from seeing the surface. Conventional surface-oriented thermal infrared sensors also struggle with opaque clouds and may instead observe cloud-top temperature.

Centimetre- and decimetre-wavelength radar generally passes through ordinary clouds and fog with little attenuation. This is why many SAR systems can image the ground in cloudy conditions.

### Rain

Rain affects microwave signals more strongly at shorter wavelengths and higher frequencies. Heavy precipitation may reduce signal quality for high-frequency radar. L-, S-, and many C-band radar applications are generally more tolerant, although performance still depends on the rain rate and system.

At millimetre wavelengths, atmospheric water and precipitation can become the target rather than just an obstacle. Cloud and precipitation radars intentionally measure how droplets and ice particles scatter their signals.

### Atmospheric absorption windows

Oxygen, water vapour, carbon dioxide, and other gases absorb radiation at characteristic wavelengths. Remote-sensing instruments are designed either to use comparatively transparent atmospheric windows to observe the surface, or to use absorption features deliberately to measure atmospheric composition.

**Key idea:** A wavelength that is poor for viewing the ground may be excellent for measuring the atmosphere.

## 5. Snow: three different problems

Snow needs special treatment because *falling snow*, *dry snowpack*, and *wet snowpack* behave differently.

1. **Falling snow:** particles in the atmosphere can scatter and attenuate signals. Precipitation radars are built to measure those particles.
2. **Dry snow on the ground:** often allows some microwave penetration, particularly at longer radar wavelengths. Signals may interact with the snow and with underlying terrain.
3. **Wet snow on the ground:** liquid water changes the dielectric properties and can strongly absorb or scatter radar energy, often hiding the underlying ground.

Optical sensors generally see the top of a snowpack rather than the soil beneath it. Thermal infrared measures the visible snow surface temperature in clear conditions. LiDAR typically measures the snow surface elevation, which can be compared with snow-free elevations to estimate depth.

A shorter wavelength that interacts strongly with snow may be better for **measuring snow properties**; a longer wavelength may be better for **observing beneath dry snow**. Neither is automatically superior.

## 6. Radar frequencies and bands

Radar bands are conventional frequency ranges. Exact boundaries may vary across standards and instruments.

| Band | Approximate frequency | Approximate wavelength | Typical Earth-observation uses |
|---|---|---|---|
| W | 75–110 GHz | 2.7–4 mm | Clouds, atmospheric profiling |
| Ka | 26.5–40 GHz | 7.5–11 mm | Rain/snow radar, altimetry |
| Ku | 12–18 GHz | 1.7–2.5 cm | Precipitation, ocean altimetry |
| X | 8–12 GHz | 2.5–3.8 cm | Detailed surface features, urban areas, ice |
| C | 4–8 GHz | 3.8–7.5 cm | Floods, agriculture, sea ice, deformation |
| S | 2–4 GHz | 7.5–15 cm | Vegetation, soil, weather applications |
| L | 1–2 GHz | 15–30 cm | Vegetation structure, soil moisture, deformation |
| P | ~0.3–1 GHz | 30–100 cm | Woody biomass, forest structure, selected subsurface studies |

### X-band

Shorter centimetre wavelengths are sensitive to fine surface features, smaller vegetation structures, and roughness. X-band SAR is used in detailed urban mapping, surface monitoring, sea ice, and deformation studies. Heavy rain can be more troublesome than at L-band.

### C-band

C-band is widely used for operational SAR monitoring. Its applications include flooding, crop monitoring, wet snow, marine observations, and ground deformation. Sentinel-1 operates around 5.405 GHz.

### L-band

L-band generally penetrates farther into many vegetation canopies than C- or X-band and can interact with woody vegetation and underlying surfaces. It is useful for forest structure, inundated vegetation, deformation, and moisture-related investigations. SAOCOM and the L-band component of NISAR are examples.

### P-band

P-band can interact with larger woody structures and penetrate farther into suitable vegetation canopies or exceptionally dry materials. It is relevant to forest biomass and certain geological studies. ESA's Biomass mission uses P-band radar around 435 MHz.

**Do not confuse penetration with spatial resolution.** A longer wavelength is not automatically lower-resolution. Radar range resolution primarily depends on transmitted bandwidth; SAR azimuth resolution depends on the synthetic aperture and processing geometry.

In an idealized radar, slant-range resolution is:

\[
\Delta R \approx \frac{c}{2B}
\]

where `B` is the transmitted bandwidth. Ground-range resolution also depends on incidence angle.

## 7. How SAR works

A conventional radar transmits microwave pulses and measures their echoes. SAR uses the satellite's motion and coherent processing of echoes from successive positions to synthesize a much larger antenna aperture, enabling finer azimuth resolution.

A SAR measurement is affected by:

- **Dielectric properties:** Liquid water and material composition can change reflectivity.
- **Roughness:** A smooth surface can reflect radar energy away from the satellite; rougher features often scatter more energy back.
- **Geometry:** Incidence angle, slope orientation, buildings, and vegetation influence the return.
- **Polarization:** The transmitted and received electric-field orientations affect how targets scatter the signal.
- **Wavelength:** Different bands interact with different scales of structure and penetrate differently.

### Radar backscatter

Backscatter describes radar energy returned toward the sensor. Calibrated radar products often express it as a coefficient such as `sigma nought (σ⁰)`, sometimes in decibels (`dB`).

Bright radar pixels do **not** necessarily mean high terrain elevation. They commonly represent relatively strong backscatter. Calm open water often appears dark because it reflects energy away from the radar, but wind, waves, vegetation, and acquisition geometry can change this behavior.

### Polarization

Common channel labels are:

- `HH`: horizontal transmit, horizontal receive.
- `VV`: vertical transmit, vertical receive.
- `HV`: horizontal transmit, vertical receive.
- `VH`: vertical transmit, horizontal receive.

Different polarizations emphasize different scattering mechanisms. Cross-polarized channels can be valuable for vegetation and volume scattering, while co-polarized channels often provide useful surface and double-bounce responses. Interpretations depend on the scene and sensor.

### Interferometric SAR (InSAR)

InSAR compares the phase of compatible SAR acquisitions to estimate differences in radar path length. With careful processing, it can measure ground displacement along the radar line of sight or support terrain elevation estimation.

It does **not** automatically measure full three-dimensional movement. Orbit differences, atmospheric delays, changing vegetation, snow, and loss of coherence can complicate interpretation.

### Common SAR-specific limitations

- Radar shadows where terrain blocks the line of sight.
- Layover and geometric distortion on steep slopes or in cities.
- Speckle, a coherent interference pattern that makes imagery look grainy.
- Changes in backscatter caused by multiple physical processes, not a single cause.
- Loss of interferometric coherence when the scene changes too much.

## 8. Optical and infrared sensing

### Visible, near-infrared, and multispectral

Visible-light sensors observe reflected sunlight, typically around 0.4–0.7 µm. Near-infrared observations, often around 0.7–1.3 µm, are useful for vegetation and land-water boundaries.

A **multispectral** instrument samples a selected set of wavelength bands. For example, vegetation absorbs much of the red light used in photosynthesis and often reflects strongly in near-infrared. Their contrast enables the Normalized Difference Vegetation Index:

\[
NDVI = \frac{NIR - Red}{NIR + Red}
\]

Clouds, haze, and darkness limit reflected-sunlight imaging. Snow is visible but may conceal vegetation or ground beneath it.

### Shortwave infrared (SWIR)

SWIR, approximately 1.3–3 µm, contains absorption features useful for distinguishing moisture, minerals, burned terrain, vegetation condition, and snow characteristics. However, surface imaging in SWIR still generally requires sunlight and sufficiently clear skies.

### Thermal infrared

Thermal sensors detect naturally emitted radiation. Common atmospheric windows include approximately 3–5 µm (midwave infrared) and 8–14 µm (longwave infrared). They are used to estimate surface temperature, monitor fires, assess urban heat, and study water stress.

Thermal imaging works at night, but clouds and fog usually prevent accurate measurement of the ground temperature beneath them. Temperature retrieval also depends on surface emissivity and atmospheric correction.

### Hyperspectral imaging

Hyperspectral instruments measure many contiguous, narrow wavelength bands. This provides richer spectral signatures than an ordinary RGB image or a small set of broad bands.

Applications include mineral identification, vegetation chemistry, surface material classification, and gas detection. Its atmospheric and cloud limitations depend on the wavelengths used. Hyperspectral imaging is **not** inherently cloud penetrating.

## 9. Other major Earth-observation technologies

### Microwave radiometry

A microwave radiometer does not transmit radar pulses. It measures naturally emitted microwave radiation as **brightness temperature**. L-band radiometry is useful for near-surface soil moisture, while multi-frequency microwave radiometers can investigate sea ice, snow, clouds, and atmospheric water.

Passive microwave measurements usually have much coarser spatial resolution than SAR because instrument antenna size constrains resolution. Their ability to operate through many cloud conditions is a major strength. Snow/frozen ground and rain can introduce retrieval errors depending on the product and frequency.

### LiDAR and laser altimetry

LiDAR transmits laser light and measures its return to infer distance. Spaceborne systems can sample ice-sheet elevation, forest canopy height, and terrain height. Some instruments record waveforms; others count returning photons.

LiDAR can operate at night but typically cannot observe the ground through dense clouds or fog. A laser return may come from the cloud or the snow surface rather than the underlying terrain.

### Radar altimetry

Radar altimeters determine distance from the spacecraft to the observed surface. Combined with precise orbit information and corrections, they support estimates of ocean surface height, ice elevation, and inland water levels. Some instruments use swath measurements rather than only a narrow ground track.

### Precipitation and cloud radar

These radars are designed to interact with atmospheric particles. Measurements can reveal precipitation intensity, vertical structure, particle distributions, and cloud properties. Their sensitivity to rain, snow, and clouds is a *feature*, not necessarily a failure.

### Scatterometry

A scatterometer measures radar backscatter from a surface at multiple viewing angles. On the ocean, wind changes small surface waves and therefore the radar return. Models convert those observations into wind speed and direction estimates.

### GNSS reflectometry (GNSS-R)

GNSS-R uses navigation-satellite signals that reflect from Earth. A receiver compares direct and reflected signals, or measures their delay/Doppler structure. Applications include ocean wind, soil moisture research, and inundation indicators. It relies on a bistatic arrangement rather than a dedicated transmitting radar on the observing satellite.

### Atmospheric spectrometry

Atmospheric spectrometers measure wavelengths absorbed or emitted by gases such as ozone, carbon monoxide, nitrogen dioxide, and carbon dioxide. Some measure total atmospheric columns; others retrieve vertical profiles. Many depend on sunlight and are affected by clouds, although certain microwave and thermal sounding methods can provide information under different conditions.

### Gravimetry

Gravity missions detect very small changes in Earth's gravity field using precise measurements of satellite motion. They can reveal large-scale changes in terrestrial water storage, glaciers, and ice sheets. They do not generate detailed photographs, and their geographic resolution is much coarser than optical or SAR imagery.

## 10. Cloud, rain, fog, and snow: Sensor suitability

The table is deliberately qualitative. "Useful" does not mean unaffected by weather, and "snow" refers to accumulated snow on the ground unless noted.

| Sensor type | Cloud/fog penetration | Heavy-rain tolerance | Observation over dry snow | Observation over wet snow | Night operation |
|---|---|---|---|---|---|
| Visible/NIR/SWIR | Poor for ground imaging | Poor | Sees snow surface | Sees snow surface | Generally no, if solar-reflectance based |
| Thermal infrared | Poor for ground imaging | Poor | Measures visible snow-surface temperature | Measures visible snow-surface temperature | Yes |
| Optical LiDAR | Limited | Limited | Usually measures snow surface | Usually measures snow surface | Yes |
| X-band SAR | Generally good | Variable | Some snow interaction/penetration | Strong wet-snow influence | Yes |
| C-band SAR | Excellent for ordinary clouds | Generally good | Often some penetration | Useful wet-snow response | Yes |
| L-band SAR | Excellent for ordinary clouds | Generally very good | Often deeper penetration | Penetration substantially reduced by liquid water | Yes |
| P-band SAR | Excellent for ordinary clouds | Generally very good | Can penetrate suitable dry materials | Material and moisture dependent | Yes |
| Passive microwave radiometry | Often good | Frequency dependent | Can measure snow properties, depending on frequency | Retrieval strongly affected by wetness | Yes |
| Precipitation/cloud radar | Designed to observe clouds/precipitation | Designed to detect precipitation, but echoes can attenuate | Not primarily a ground-imaging instrument | Not primarily a ground-imaging instrument | Yes |

The correct choice depends on **what you want to observe**: the ground *beneath* snow, the snowpack *itself*, or the precipitation *falling through the atmosphere*.

## 11. Combining sensors: Multisensor data fusion

Different sensors measure different properties and are subject to different errors. Combining them can strengthen an interpretation, but only when their measurements are compatible.

Examples:

| Application | Complementary observations | Why the combination helps |
|---|---|---|
| Flood mapping | SAR + rainfall + elevation + land cover | SAR suggests inundation; rainfall and terrain provide context; land cover helps distinguish permanent water |
| Flooded forests | L-band SAR + C-band SAR + forest maps | Longer wavelengths may provide additional information about water beneath vegetation |
| Crop water stress | SAR + passive microwave + thermal IR + multispectral | Combines backscatter, regional soil moisture, surface temperature, and plant condition |
| Forest biomass | P/L-band SAR + LiDAR + optical | Combines woody structure, canopy height samples, and vegetation classification |
| Snowmelt | C-band SAR + passive microwave + precipitation + elevation | Combines wet-snow changes, broader snow properties, snowfall, and terrain |
| Landslides | InSAR + elevation/slope + rainfall + geology | Connects observed displacement to terrain and environmental conditions |
| Fire assessment | Thermal IR + optical/SWIR + SAR | Connects hotspots, burn effects, and radar-visible surface change |
| Ocean storms | SAR + scatterometer + GNSS-R + altimetry | Combines local radar texture, broader wind estimates, reflections, and water height |

### Four important fusion problems

1. **Different spatial resolutions:** A 10 m SAR pixel and a 9 km soil-moisture grid cell do not represent the same physical area. Upsampling cannot create finer information.
2. **Different acquisition times:** Observations from different days may capture changing weather or land conditions. Time gaps must be tracked.
3. **Different measurement meanings:** SAR backscatter, thermal temperature, and NDVI are not interchangeable measures of "change". Each requires physical interpretation.
4. **Missing or unreliable data:** Optical imagery may be unusable under clouds while SAR continues observing; models must record uncertainty rather than pretending the missing measurement exists.

Useful integration methods include geographic co-registration, temporal alignment, quality masks, physically informed features, statistical estimation, and machine learning. Validation should use independent ground data when available.

## 12. Practical examples of satellite systems

These examples illustrate different measurement families rather than a complete catalogue:

| Mission | Main sensor type | Illustrative use |
|---|---|---|
| Sentinel-1 | C-band SAR | Floods, land change, deformation |
| SAOCOM-1A/1B | L-band SAR | Soil/vegetation, flooding, deformation |
| NISAR | L- and S-band SAR | Land and ice changes, ecosystems, deformation |
| ESA Biomass | P-band SAR | Forest woody biomass |
| Sentinel-2 | Multispectral optical | Vegetation, water, land cover |
| Landsat 8/9 | Multispectral and thermal infrared | Land change and surface temperature |
| EMIT / EnMAP | Imaging spectroscopy | Minerals and spectral material properties |
| SMAP | L-band microwave radiometry | Soil moisture and freeze/thaw |
| GPM | Precipitation radar and microwave instruments | Rain and snow |
| GEDI / ICESat-2 | Laser altimetry | Forest structure and surface elevation |
| SWOT | Radar interferometric altimetry | Inland and ocean water elevation |
| CYGNSS | GNSS reflectometry | Ocean surface winds and other reflections |
| GRACE-FO | Satellite gravimetry | Large-scale water/ice mass changes |

## 13. Key distinctions to remember

- **Radar is not the same as SAR.** SAR is a coherent radar imaging technique that exploits platform motion.
- **SAR does not directly detect "change" or "flood".** Algorithms infer these from radar measurements over time and context.
- **Microwave radiometry is passive.** It measures natural emission rather than transmitting radar pulses.
- **Multispectral versus hyperspectral is about spectral sampling.** Neither designation guarantees any particular weather tolerance.
- **Thermal infrared measures radiation, not temperature directly.** Temperature is retrieved using physical models and corrections.
- **Seeing through clouds is not seeing through wet snow.** Airborne droplets and a wet snowpack are different propagation environments.
- **Longer wavelength does not always mean better.** The objective may be to observe a material rather than penetrate it.
- **A sensor's band is not its image resolution.** Instrument bandwidth, antenna geometry, platform motion, processing, and viewing geometry all matter.
- **A satellite's data product is not always its raw sensor measurement.** Higher-level products contain algorithms, models, assumptions, and uncertainty.

## 14. Suggested conceptual learning sequence

1. Electromagnetic frequency and wavelength; absorption, reflection, scattering, and emission.
2. Atmospheric transmission windows and why clouds, fog, rain, ice, and snow behave differently.
3. Active versus passive instruments.
4. Radar bands, polarization, backscatter, synthetic aperture, and interferometric phase.
5. Multispectral, hyperspectral, thermal infrared, LiDAR, radiometry, and altimetry.
6. Spatial/temporal resolution, calibration, uncertainty, and multisensor fusion.

**Bottom line:** There is no single best Earth-observation sensor. Every technique measures a different physical interaction, at different wavelengths, resolutions, and times. A reliable observation system combines complementary measurements while respecting environmental and measurement limitations.
