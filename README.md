# GUBAD: Global Urban Built-up Area Dataset — Processing Code

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

This repository contains the production code for the **Global Urban Built-up Area Dataset (GUBAD)**, a multi-epoch dataset of urban built-up areas (UBA) for 1,611 global cities with populations exceeding 300,000 (2000–2025).

&gt; **Manuscript status:** Code accompanying the manuscript *"A Global Urban Built-up Area Dataset for Cities with Populations Exceeding 300,000 (2000–2025)"*.
&gt; 

&gt; **Dataset:** The GUBAD data product (vector shapefiles, supplementary tables, and metadata) is available separately on Zenodo: `https://doi.org/10.5281/zenodo.20051123`.

---

## Repository Structure
GUBAD-code/

├── Python/ # Google Earth Engine (GEE) extraction workflows

├── Shell/           # Batch orchestration and pipeline scripts

└── cpp/             # Post-processing and temporal filtering (CUDA/GDAL)

---

## 1. Python (`ee_get_ISAs.py`, `ee_get_dataset.py`)

**Purpose:** Extract impervious surface areas (ISA) from multi-source satellite imagery via Google Earth Engine (GEE).

**Key workflow:**
1. `ee_get_dataset.py` — Constructs GEE image collections:
   - **2000–2015:** Landsat 5/7/8 (Collection 2 Level-2, surface reflectance)
     - Computes NDVI, NDWI, NDBI
   - **2020–2025:** Sentinel-2 MSI (harmonized surface reflectance)
     - Computes NDVI, NDWI, NDBI
     - Integrates Sentinel-1 GRD VV backscatter (SAR)
     - Integrates VIIRS DNB monthly composites (nighttime lights)
2. `ee_get_ISAs.py` — City-level ISA extraction:
   - Loads city boundaries and stratified training samples (GHSL-SMOD / ESA WorldCover)
   - Trains a Random Forest classifier (100 trees, `minLeafPopulation=5`) per city
   - Classifies ISA and applies a mode filter (`Kernel.square(1.5)`)
   - Exports results to Google Drive as 30 m (2000–2015) or 10 m (2020–2025) GeoTIFFs
3. `batch_ISA_to_builtup_constraint.py` — Batch conversion and refinement of city-level built-up areas:
   - Loads impervious surface / built-up area shapefiles and administrative boundaries
   - Identifies intersecting administrative districts and allows users to select valid city extents
   - Clips built-up area polygons by selected administrative boundaries
   - Removes small fragmented patches smaller than 10,000 m² and recalculates built-up area
   - Applies optional temporal consistency constraints across multiple years
      ▪ Manual constraint mode
      ▪ Sequential year-by-year constraint mode
      ▪ No-constraint copy mode
   - Exports intermediate and final city-level built-up area shapefiles with standardized filenames
   - Saves user selections and completion markers to support breakpoint continuation
4. `batch_apply_manual_kml_patches.py` — Batch refinement of built-up area results using manually interpreted KML files:
   - Loads constrained built-up area shapefiles and Google Earth-based manual KML corrections
   - Adds missing built-up areas from `_bu.kml` files
   - Removes false built-up areas using `_cai.kml` files
   - Automatically matches correction files by city and year
   - Recalculates built-up area and cleans attribute fields
   - Exports final patched shapefiles with standardized names
   - Logs processing information and reports years with unexpected area decreases
5. `batch_remove_water_from_builtup.py` — Batch water-body removal from corrected built-up area results:
   - Loads checked and manually corrected built-up area shapefiles
   - Loads and dissolves provincial water-body polygon datasets
   - Automatically matches each city to the corresponding provincial water mask
   - Removes water-covered areas from built-up polygons using spatial difference
   - Repairs geometries and removes empty results
   - Recalculates built-up area after water removal
   - Exports final city-year shapefiles with standardized names

**Dependencies:**
- Python 3.8+
- `earthengine-api`
- `geopandas`, `numpy`, `osgeo.gdal`
- `rclone` (for downloading from Google Drive)

**Usage:**
```bash
# Authenticate GEE first
earthengine authenticate

# Extract ISA for all cities in a continent/country
python3 ee_get_ISAs.py /path/to/boundaries/*/* /path/to/output -y -m 1

```

##  2. Shell (isas_gen.sh, isas_filter.sh)
**Purpose:** Orchestrate batch processing across 1,611 cities and 6 epochs.
**Workflow:**
1. `isas_gen.sh` — Wrapper for ee_get_ISAs.py:
    - Iterates over city boundary shapefiles (02_boundaries/continent/country/city.shp)
    - Manages GEE task queues and parallel execution
    - Triggers post-processing upon completion
2. `isas_filter.sh` — Prepares file lists for temporal filtering:
    - Organizes exported TIFFs by city and epoch (2000, 2005, 2010, 2015, 2020, 2025)
    - Calls the C++ temporal consistency filter

**Directory convention:**
31_ISA/

├── L0/   # Raw ISA exports from GEE

└── L1/   # Temporally filtered ISA (output of cpp binary)


##  3. C++ (main_IS_filter.cpp, defs.h)
**Purpose:** Enforce temporal consistency across ISA epochs using GPU-accelerated isotonic regression (PAVA).

**Implementation:**

    - Reads 6 epoch TIFFs per city (GDAL API)
    - Applies the Pool-Adjacent-Violators Algorithm (PAVA) at the pixel level
    - Ensures non-decreasing impervious-surface trends from 2000 → 2025
    - Suppresses noise-induced temporal "spikes" without enforcing artificial growth
    - CUDA-accelerated for global-scale throughput
    
**Dependencies:**

    - GDAL (≥ 2.4)
    - CUDA Toolkit
    - CImg (for TIFF I/O)
    - NVIDIA GPU (compute capability ≥ 5.0)
