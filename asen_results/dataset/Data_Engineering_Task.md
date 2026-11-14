# TerraGuard — NISAR and Water Infrastructure Incident Data Integration

## Project Overview

TerraGuard is an Earth-observation and machine-learning project we are developping for the **NASA Space Apps Challenge 2026 — Dancing with the SARs**.

The objective is to identify potentially significant surface changes associated with water-pipeline failures using Synthetic Aperture Radar (SAR) imagery and geospatial water-infrastructure data.

Our current task is to develop a **reproducible data acquisition, preprocessing, and integration pipeline** that combines real-world water-main break records from Kitchener, Ontario, Canada, with satellite observations from NASA's NISAR mission.

The resulting dataset will support subsequent experimentation with classical machine learning, anomaly detection, and pretrained SAR foundation models.

**This development phase focuses exclusively on preparing and evaluating the dataset. Model training and application development are outside its initial scope.**

## 1. Data Sources

### A. Kitchener Water Main Breaks

Source: https://data.waterloo.ca/datasets/KitchenerGIS::water-main-breaks/explore

ArcGIS Feature Service:
https://services1.arcgis.com/qAo1OsXi67t7XgmS/ArcGIS/rest/services/Water_Main_Breaks/FeatureServer/0

The dataset contains geographically referenced water-main break incidents reported by the City of Kitchener.

Relevant attributes include:

- `WATBREAKINCIDENTID` — Incident identifier
- `INCIDENT_DATE` — Reported incident date
- `BREAK_TYPE` — Main-pipe or service-pipe failure
- `STATUS` — Repair or investigation status
- `STATUS_DATE` — Last status update
- `RETURN_TO_NORMAL` — Return-to-service date
- `ASSET_DEPTH` — Pipe burial depth
- `ASSET_SIZE` — Pipe diameter
- `ASSET_MATERIAL` — Pipe material
- `ASSET_YEAR_INSTALLED` — Installation year
- Geographic point geometry

**Objective:** Extract clean, geolocated incident records with meaningful temporal and infrastructure attributes.

### B. NASA NISAR Satellite Observations

NASA Earthdata:
https://search.asf.alaska.edu/

NISAR documentation:
https://nisar-docs.asf.alaska.edu/gcov/

Primary product: **NISAR Level-2 GCOV (Geocoded Polarimetric Covariance)**.

Relevant collections:

- `NISAR_L2_GCOV_V1` — Validated observations
- `NISAR_L2_GCOV_PROVISIONAL_V1` — Earlier provisional observations

GCOV provides calibrated, terrain-corrected radar-backscatter measurements, represented as gamma-0 power, together with geographic and instrument metadata.

Depending on the acquisition, useful channels may include HH, HV, VV, and VH.

The available polarizations, acquisition dates, resolution, and geographic coverage must be verified rather than assumed.

**Objective:** Retrieve suitable radar observations around documented water-main break locations.

Validated NISAR products begin with acquisitions from October 21, 2026, while provisional data covers acquisitions beginning June 17, 2026. Earlier beta observations may also be investigated separately.

## 2. Data Preprocessing Objectives

### Stage 1 — Incident Data Extraction

Develop a Python pipeline that:

1. Queries the Kitchener ArcGIS Feature Service.
2. Retrieves all available incident records using pagination.
3. Converts the results into a Pandas/GeoPandas dataset.
4. Standardizes incident timestamps and geographic coordinates.
5. Handles missing values, invalid locations, and duplicate incident records.
6. Filters events based on available NISAR acquisition dates.
7. Preserves relevant infrastructure characteristics.

Generate summary statistics covering:

- Incidents per year and month.
- Spatial distribution of incidents.
- Main-pipe versus service-pipe failures.
- Missing or incomplete fields.
- Incidents occurring within the NISAR observation period.

### Stage 2 — NISAR Data Discovery

Using NASA Earthdata APIs and the `earthaccess` Python library:

1. Define the geographic extent of Kitchener.
2. Search for NISAR GCOV acquisitions intersecting the study area.
3. Retrieve acquisition timestamps, footprints, polarizations, resolution, orbit information, and processing maturity.
4. Identify observations that can be compared consistently.
5. Determine which incident locations fall inside valid radar coverage.

Create a catalogue of available observations before downloading large satellite files.

**Key output:** A report showing how many incidents have potentially relevant NISAR observations.

### Stage 3 — Spatiotemporal Matching

For every documented break, identify candidate satellite observations from three periods:

- **Before the incident:** Establish reference conditions.
- **Around the incident:** Investigate whether the event could have been observed.
- **After the incident:** Examine possible changes following repair or restoration.

Use configurable temporal windows rather than assuming a fixed leak duration.

Record the time difference between each satellite observation and the reported incident.

Categorize matches as:

- `pre_event`
- `potential_event_window`
- `post_event`
- `timing_uncertain`

The incident date does not prove that a leak was active during a satellite acquisition. Treat the event-window designation as a matching hypothesis, not confirmed radar-visible leakage.

### Stage 4 — SAR Preprocessing

For each selected observation:

1. Read the NISAR GCOV HDF5 product.
2. Extract available radar-backscatter channels.
3. Apply valid-data and quality masks.
4. Handle invalid values, no-data regions, and radar artifacts.
5. Convert radar intensity into suitable analysis representations, including dB where appropriate.
6. Align observations using a consistent coordinate reference system and spatial grid.
7. Apply appropriate spatial filtering where necessary.
8. Extract geographic patches around incident locations.
9. Preserve calibration, acquisition geometry, polarization, and processing-version metadata.

Avoid comparing radar observations with incompatible polarizations, substantially different acquisition geometries, or unaccounted processing differences.

The original radar measurements should be retained separately from normalized ML inputs.

### Stage 5 — Feature Extraction

Prepare features that could be informative for detecting changes in the environment surrounding water pipelines.

**SAR features:**
- Radar-backscatter intensity.
- Backscatter differences between acquisition dates.
- Polarization ratios, where available.
- Local texture and spatial statistics.
- Temporal deviations from reference observations.
- Localized change relative to surrounding background areas.

**Infrastructure features:**
- Pipe material.
- Pipe diameter.
- Installation year and estimated age.
- Pipe burial depth.
- Break type and historical incident attributes.

**Optional environmental features:**
- Precipitation before the satellite acquisition.
- Land-cover classification.
- Vegetation indices from optical satellite imagery.
- Local terrain information.

Do not include attributes recorded after the incident as predictive features for a model intended to identify leaks before they are reported.

### Stage 6 — Dataset Construction

Construct a machine-learning-ready dataset in which each sample corresponds to a geographically defined observation associated with a specific satellite acquisition.

The dataset should preserve:

- Incident ID, if applicable.
- Geographic coordinates and patch geometry.
- Satellite acquisition time.
- Time difference relative to the incident.
- SAR image patch or derived features.
- Infrastructure metadata.
- Environmental context, where available.
- Observation quality indicators.
- Label source and confidence.

**Label categories:**

- `confirmed_break_event` — An incident is documented at the location and date.
- `candidate_satellite_match` — A satellite observation is temporally and spatially relevant, but active leakage is not confirmed.
- `unknown` — Insufficient information to determine leakage status.
- `verified_non_leak` — Only when independent evidence confirms the absence of leakage.

Never automatically label all areas without recorded incidents as negative examples.

Separate geographic areas, incident groups, and time periods appropriately when creating future training and evaluation splits to avoid data leakage.

## 3. Expected Deliverables

### A. Incident dataset

`kitchener_incidents.parquet`

Clean, documented water-main break records with valid coordinates, standardized dates, and infrastructure metadata.

### B. NISAR catalogue

`nisar_acquisitions.parquet`

Metadata for all discovered NISAR acquisitions intersecting the study area, including acquisition timestamps, footprints, polarization, orbit, and processing maturity.

### C. Spatiotemporal matches

`incident_nisar_matches.parquet`

A table associating incident records with candidate radar observations, including time offsets, geographic overlap, quality indicators, and matching confidence.

### D. Processed satellite patches

Georeferenced radar patches stored in a suitable format such as GeoTIFF, Zarr, or NumPy arrays, with metadata linking every patch to its source acquisition.

### E. Feature dataset

`radar_features.parquet`

A tabular dataset containing extracted radar, infrastructure, and optional environmental features for future machine-learning experiments.

### F. Feasibility report

`data_feasibility_report.md`

Summarize:

- Total number of Kitchener incidents.
- Number of incidents during the NISAR observation period.
- Number with valid satellite geographic coverage.
- Number with suitable before/after observations.
- Number potentially observed during an active leakage window.
- Available radar polarizations and processing limitations.
- Missing labels and data-quality concerns.
- Recommendation for the next ML stage.

## 4. Proposed Technology Stack

- **Python** — Main processing language.
- **Pandas / GeoPandas** — Incident and geographic data processing.
- **Requests** — ArcGIS API integration.
- **earthaccess** — NASA Earthdata search and access.
- **h5py / xarray** — Reading satellite HDF5 data.
- **Rasterio / rioxarray** — Geospatial raster processing.
- **NumPy / SciPy** — Numerical analysis and feature extraction.
- **Matplotlib / Folium** — Diagnostic visualizations.

The pipeline should be modular, reproducible, and capable of processing selected geographic subsets without requiring complete downloads of every available satellite scene.

## 5. Future Machine Learning Stage

Once the dataset has been constructed and evaluated, choose the model based on the available data.

Potential approaches include:

- **XGBoost / Random Forest:** Supervised classification if sufficient reliable labels can be established.
- **Isolation Forest:** Unsupervised anomaly detection when reliable negative and event-time labels are unavailable.
- **AnySat / SAR-W-SimMIM:** Pretrained radar feature extraction, followed by downstream classification or anomaly detection.
- **Transfer learning:** Investigate adaptation of representations learned from historical SAR imagery to NISAR observations.

The architecture should be selected after assessing the data, not before.

## 6. Scientific Limitations

SAR does not directly observe broken underground pipes.

It measures radar scattering from the surrounding environment, potentially revealing moisture-related or structural changes.

Detectability depends on pipe depth, surface material, rainfall, soil characteristics, vegetation, spatial resolution, and the timing of the satellite acquisition.

The prepared dataset must therefore distinguish documented infrastructure incidents from verified radar-observable leakage signatures.

Additionally, Kitchener's urban distribution network differs substantially from Bulgaria's reservoir-to-city transmission infrastructure. Any transfer between these settings will require separate evaluation.

## 7. Definition of Success

This phase is successful when we have:

1. A reproducible pipeline for downloading and cleaning Kitchener incident records.
2. A verified inventory of NISAR coverage over Kitchener.
3. A reliable spatial and temporal matching procedure.
4. A small collection of processed SAR examples associated with documented incidents.
5. An initial feature dataset suitable for ML experimentation.
6. An evidence-based decision about whether supervised leakage detection is feasible.

**The final goal is not to claim that leaks have already been detected, but to establish whether the available satellite and infrastructure data can support training a scientifically credible detection model.**

This preprocessing pipeline will form the foundation of TerraGuard's future ML development and its eventual application to Bulgarian water infrastructure.