# Water pipe leaks and SAR: literature notes

Collected 2026-11-14 while checking the idea of detecting leaking water pipes
with NISAR. Search snippets and abstracts only; no full texts were read, so
treat numbers as unverified until someone opens the papers.

## The "Montreal InSAR leak study": not found

No study using InSAR to detect water pipe leaks in Montreal turned up. If
someone remembers a specific source, add it here. What does exist for Montreal:

- **Normand & Heggy, 2015, IEEE TGRS**, "InSAR Assessment of Surface
  Deformations in Urban Coastal Terrains Associated with Groundwater
  Dynamics" ([IEEE](https://ieeexplore.ieee.org/document/7192621/),
  [record](https://elmi.hbku.edu.qa/en/publications/insar-assessment-of-surface-deformations-in-urban-coastal-terrain/),
  [AGU 2014 abstract](https://agu.confex.com/agu/fm14/webprogram/Paper31205.html)).
  RADARSAT-2 C-band InSAR, 2008-2010, about 60 km2 of central Montreal Island.
  - 3-5 mm line-of-sight seasonal displacement, lagging aquifer head and
    river level by about three months.
  - About 1 mm/yr uplift over a 15 m clay layer and about 2 mm/yr subsidence
    on a topographic high (put down to evapotranspiration).
  - Displacement correlates with house foundation repairs (up to 89
    repairs/km2; the AGU abstract gives this for the Plateau and 8/km2
    city-wide).
  - About groundwater and foundations, **not pipes**. Still useful: it shows
    what background deformation a pipe signal would have to stand out from.
- Montreal leak detection research on the ground uses **infrared thermography**
  ([ISARC 2009](https://www.iaarc.org/publications/proceedings_of_the_26th_isarc/detecting_and_locating_leaks_in_underground_water_mains_using_thermography.html),
  [ASCE 2009](https://ascelibrary.com/doi/10.1061/%28ASCE%29CF.1943-5509.0000094))
  and **acoustic loggers**
  ([clustering model](https://research.polyu.edu.hk/en/publications/development-of-a-clustering-based-model-for-enhancing-acoustic-le/),
  [city listening system](https://thewaternetwork.com/_/urban-water-security/article-FfV/1-1-million-system-in-montreal-listens-for-leaks-OKd5XgtKAHmKd3cAeVeOCQ)).
- Scale of the problem: about 30% of Montreal's water is reportedly lost to
  leaks (Montreal Gazette via
  [The Water Network](https://thewaternetwork.com/_/urban-water-security/article-FfV/1-1-million-system-in-montreal-listens-for-leaks-OKd5XgtKAHmKd3cAeVeOCQ)).

## Two ways SAR can see a leak

1. **Moisture (backscatter / polarimetry).** Leaking water raises soil
   dielectric constant, which changes backscatter. L-band penetrates
   further into dry soil than shorter wavelengths. This is the approach used
   commercially and in most recent papers. **NISAR GCOV is this kind of
   data.**
2. **Deformation (InSAR).** Leaks wash out fine soil or swell clay, causing
   millimetre-scale subsidence or heave, sometimes ending in sinkholes. Fewer
   studies, mostly Italian.

## Moisture / polarimetric studies

- **ASTERRA (formerly Utilis)**, commercial, L-band polarimetric SAR looking
  for the signature of potable water near mapped pipes. Output is points of
  interest that field crews then verify. Deployments: Affinity Water UK
  ([case study](https://www.suez.com/-/media/suez-global/files/uk-files/case-studies/affinity-water-satellite-case-study.pdf)),
  Honolulu ([case study](https://www.wateronline.com/doc/case-study-how-honolulu-board-of-water-supply-uses-satellite-based-leak-detection-0001)),
  New Mexico, Texas, Japan ([overview](https://lidarmag.com/2023/02/14/l-band-locates-leaks/)).
  No Canadian deployment found. Vendor figures, not independent.
- **Beijing, IEEE JSTARS 2024**: PCA + SVM on SAR-derived moisture plus InSAR
  closure phase; 91.86% reported accuracy
  ([DOAJ](https://doaj.org/article/76feddb231744da5b2dc890dbd275081)).
- **Hong Kong, ISPRS 2025** (Ali et al.): six dual-pol L-band images against
  Water Supplies Department leak records, dense urban setting
  ([paper](https://isprs-archives.copernicus.org/articles/XLVIII-G-2025/147/2025/)).
- **Tianjin, Remote Sensing 2025** (Zhang, Guan, Duan): L-band PolSAR combined
  with ground-penetrating radar
  ([MDPI](https://mdpi.com/2072-4292/17/8/1386)).
- **J. Environmental Management 2026**: unsupervised anomaly detection on
  L-band PolSAR for leaks under pavement in arid, sparsely vegetated areas;
  81% of leaks found, about 7% false positives
  ([PubMed](https://pubmed.ncbi.nlm.nih.gov/41785796/)).

## Deformation (InSAR) studies

- **University of Padua**: DInSAR to test whether leaks relate to soil
  deformation in non-urban areas
  ([record](https://research.unipd.it/handle/11577/3471242)).
- **Transmission mains**: InSAR used to flag slow ground movement zones that
  may match leak positions ([DOI 10.1061/JITSE4.ISENG-2189](https://oa.mg/work/10.1061/jitse4.iseng-2189)).
- **Milan** (Planetek Italia with MM SpA): Sentinel-1 displacement near sewer
  and water networks, now an operational service
  ([NEREUS](https://www.nereus-regions.eu/download/5082)).
- **ESA SCIRES**: satellite radar + IoT + AI for early pipeline leak signs;
  pilots with Hera (Zocca) and Acea (Rome); finished September 2025
  ([ESA](https://business.esa.int/projects/scires)).

## Implications for a NISAR project (our reading, not from the papers)

- **Resolution is the main risk.** Leak signatures are metres to tens of
  metres across. GCOV is 10-20 m, GUNW 80 m. GUNW is probably too coarse for
  individual leaks; GCOV may catch large leaks or main breaks.
- **Moisture beats deformation for NISAR.** The method with the most evidence
  (L-band backscatter) matches GCOV, the easiest NISAR product.
- **Ground truth is needed.** Every study validates against utility leak or
  repair records. Check whether the study city publishes water main break
  data (Montreal's open data portal is worth checking; not verified).
  - **Checked 2026-11-14:** Montreal publishes "Réparations de bris sur le
    réseau d'eau potable" (CC-BY 4.0, Service de l'eau,
    [donnees.montreal.ca](https://donnees.montreal.ca/en/dataset/reparation-reseau-eau-potable),
    [Données Québec](https://www.donneesquebec.ca/recherche/dataset/vmtl-reparation-reseau-eau-potable)).
    One CSV, 24,077 repairs with date, borough and lat/lon (also MTM 8).
    Dates run 1972-02-04 to **2017-05-29**; the file has not been updated
    since 2018 despite the "annual" label. **No overlap with NISAR** (data
    from October 2025). CBC warns records before 2000 are unreliable.
- **Montreal winters.** Snow and frozen soil change backscatter strongly and
  would mask moisture signals for months. A warm or arid city is an easier
  first target.
- **Record length.** NISAR data starts October 2025, so any leak or break
  event studied must be after that.
- **Fit with the brief.** Soil moisture change around infrastructure is a
  surface change with a clear physical driver, so it fits, but it is a harder
  detection problem than flooding or vegetation change.
