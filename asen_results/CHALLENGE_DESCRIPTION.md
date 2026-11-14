# NASA Space Apps Challenge 2026 — Dancing with the SARs

**Category:** Earth Science  
**Difficulty:** Intermediate / Advanced  
**Official challenge:** https://www.spaceappschallenge.org/2026/challenges/dancing-with-the-sars/?tab=details

## 1. Challenge Overview

Earth's surface constantly changes due to natural processes and human activities. These changes include flooding, wetland loss, deforestation, wildfires, agricultural development, soil-moisture variations, glacier movement, earthquakes, and land subsidence.

Despite their environmental and societal importance, these changes can be difficult to observe, analyze, visualize, and communicate effectively.

**The challenge is to develop an interactive application using radar remote-sensing data from the NASA–ISRO Synthetic Aperture Radar (NISAR) mission to track and visualize one or more types of Earth's surface changes across selected geographic locations.**

The application should make complex satellite radar observations understandable, visually compelling, and useful to a broader audience.

## 2. Scientific Background

Earth observation commonly relies on two remote-sensing approaches.

### Passive Remote Sensing

Passive sensors measure naturally occurring electromagnetic radiation, usually sunlight reflected from Earth's surface.

Optical satellite imagery can provide information about vegetation, water, soil, minerals, and land-cover characteristics through different spectral bands.

### Active Remote Sensing — SAR

Synthetic Aperture Radar (SAR) is an active remote-sensing technology. It transmits microwave signals toward Earth's surface and measures their reflected energy, known as radar backscatter.

SAR offers several important capabilities:

- Collecting observations during both daytime and nighttime.
- Operating through clouds and many adverse weather conditions.
- Observing changes in surface roughness, structure, and moisture-related properties.
- Monitoring water bodies, floods, forests, agricultural areas, sea ice, and glaciers.
- Measuring small surface displacements using appropriate interferometric techniques.

Radar responses depend on characteristics including surface geometry, roughness, dielectric properties, radar wavelength, and polarization.

Different SAR polarizations can reveal different aspects of Earth's surface.

The NISAR mission provides radar observations suitable for studying environmental processes and surface changes over time.

## 3. Main Objective

Develop an **interactive, accessible, and preferably open-source application** that leverages NISAR radar data to monitor and communicate changes on Earth's surface.

The solution should:

1. Select one or more meaningful environmental or geological phenomena.
2. Identify geographic regions relevant to those phenomena.
3. Obtain and analyze suitable NISAR satellite observations.
4. Track and visualize changes in Earth's surface over time, where suitable multitemporal data is available.
5. Communicate the observed changes through intuitive interactive visualizations.
6. Provide scientific context and reasonable hypotheses about the physical processes responsible for those changes.
7. Make the results understandable and useful to scientists, environmental managers, educators, decision-makers, or the general public.

The application should transform complex radar observations into useful information, not merely display unprocessed satellite images.

## 4. Potential Application Domains

The challenge allows participants to choose their own geographic area and type of surface change.

Potential use cases include:

- **Flood monitoring:** Tracking changing water extent in rivers, wetlands, and floodplains.
- **Deforestation:** Observing changes in forest cover and vegetation structure.
- **Wildfire impacts:** Analyzing surface changes following forest fires.
- **Agricultural monitoring:** Tracking changes in agricultural land, crop structure, and soil conditions.
- **Glacier and ice monitoring:** Visualizing changes in glaciers, ice sheets, or sea ice.
- **Earthquake and deformation monitoring:** Studying displacement related to earthquakes, volcanic activity, or subsidence.
- **Coastal monitoring:** Investigating shoreline and coastal wetland changes.
- **Human environmental impact:** Examining changes associated with agriculture, urban development, or industrial activity.

These are examples, not a restrictive list.

## 5. Data Sources

### Primary Dataset: NISAR

NISAR radar remote-sensing observations should form the foundation of the proposed solution.

Relevant data may include multiple acquisition dates, different radar polarizations, and other available radar measurements suitable for the selected analysis.

### Supplementary Datasets

The challenge explicitly permits and encourages incorporating additional data where useful.

Examples include:

- Optical satellite imagery, such as Landsat or Sentinel-2.
- Additional SAR observations from other satellite missions.
- Geographic Information System (GIS) layers.
- Vegetation and land-cover information.
- Population and settlement data.
- Environmental and geographic contextual datasets.

Supplementary data should provide context, help interpret observed changes, or improve the application's usefulness.

**Important:** Optical imagery and other modalities may complement the radar analysis, but NISAR should remain central to the solution.

## 6. Recommended Capabilities

The challenge encourages, but does not mandate, the following:

### Multitemporal Analysis

Compare satellite observations from different dates to identify and explain environmental changes.

### Radar Polarization Analysis

Investigate how different SAR polarizations respond to different surface characteristics and whether they help distinguish particular phenomena.

### Multisensor Analysis

Compare radar observations with other frequencies or optical data, when appropriate.

### Interactive Visualization

Possible features include:

- Interactive geographic maps.
- Before-and-after image comparisons.
- Time-series animations.
- Change-detection overlays.
- Interactive dashboards.
- Story maps and explanatory visualizations.

### Environmental Interpretation

Explain potential physical and human causes of the observed changes.

Where possible, identify the implications for ecosystems, infrastructure, natural resources, and communities.

### Scientific Storytelling

Make the data understandable to non-specialists, communicating not only what changed but also why the change may matter.

## 7. Expected Outcome

The desired result is a user-friendly, open-source-oriented interactive solution that demonstrates the usefulness of NISAR data for understanding changes on Earth.

A successful project should provide:

- A clearly defined environmental or geological problem.
- A meaningful use of NISAR radar data.
- An appropriate study region.
- Visual evidence of the relevant surface changes.
- An interactive and understandable presentation.
- A scientific explanation of the observations and their possible causes.
- A compelling demonstration of the application's potential value.

The challenge does **not** require a specific programming language, software framework, machine-learning architecture, or predefined environmental phenomenon.

Machine learning is optional and may be incorporated where it meaningfully contributes to the solution.

## 8. Project Development Guiding Principles

When designing the application:

- Keep NISAR observations central to the project.
- Select an achievable and scientifically meaningful problem.
- Prioritize real satellite observations and reproducible analysis.
- Use complementary datasets when they add information.
- Distinguish measured changes from hypotheses about their causes.
- Design the user experience around interpreting geospatial information.
- Aim for a functional prototype with a convincing demonstration.
- Avoid introducing unnecessary technical complexity that does not improve the scientific or practical value.

## 9. Central Design Question

**How can we transform NISAR radar observations, potentially combined with other Earth-observation data, into an interactive application that helps people detect, understand, and act upon meaningful changes on Earth's surface?**

The final application concept, environmental phenomenon, study region, data-processing methodology, and technical architecture remain to be selected by the development team.