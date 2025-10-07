# JolChobi 🌊 — Sunamganj Flood Visualizer (Enhanced MVP)

This repository contains **step-by-step Streamlit apps** that build up to the final JolChobi app.
You can run each step to verify your environment, then run the final `app.py`.

## 🚀 **NEW: Improved Version Available!**

We've created an **enhanced version** with major improvements:
- ✅ **Modular architecture** - Clean separation into 6 focused modules
- ✅ **Better performance** - Cached OSM layers, retry logic for APIs
- ✅ **Enhanced UX** - DEM upload, basemap selector, opacity controls
- ✅ **Accurate analytics** - Spatial joins for exposure, fixed area calculations
- ✅ **Professional exports** - COG format, metadata JSON, in-memory downloads
- ✅ **Production-ready** - Type hints, tests, pinned dependencies

**Quick start:**
```bash
pip install -r requirements.txt
streamlit run app.py
```

See [`IMPROVEMENTS.md`](IMPROVEMENTS.md) for full details and [`MIGRATION_GUIDE.md`](MIGRATION_GUIDE.md) for migration help.

## Prerequisites
- **Python 3.10 or 3.11**
- **Git (optional)**
- **IDE:** We recommend **Visual Studio Code** (VS Code).
  - Install VS Code, then install the "Python" extension (by Microsoft).

## Setup (Windows PowerShell, macOS Terminal, or Linux shell)
```bash
# 0) Change to a folder where you want the project
cd ~/Desktop

# 1) Create and enter project folder
mkdir JolChobi && cd JolChobi

# 2) (Optional but recommended) Create a virtual environment
python -m venv .venv
# Activate it
#   Windows PowerShell:
. .venv/Scripts/Activate.ps1
#   macOS/Linux:
source .venv/bin/activate

# 3) Install dependencies
pip install -r requirements.txt
```

> If you see build errors for **rasterio** or **geopandas**, try:
> - Windows: `pip install wheel` then `pip install --only-binary=:all: rasterio geopandas`
> - macOS with Homebrew: `brew install gdal` then `pip install rasterio geopandas`
> - Linux: `sudo apt-get install gdal-bin libgdal-dev` then `pip install rasterio geopandas`

## Project Structure
```
Jolchobi/
  app.py                  <- Final app
  requirements.txt
  README.md
  data/
    dem_sunamganj.tif     <- Synthetic DEM for offline testing
  step1_hello.py
  step2_base_map.py
  step3_dem_overlay.py
  step4_flood_model.py
  step5_osm_layers.py
  step6_exports.py
  assets/
```
> **Note:** `data/dem_sunamganj.tif` is a small **synthetic** elevation raster (georeferenced around Sunamganj).
> Replace it with a real SRTM/FABDEM clip when you can.

---

## Step-by-step “plug & chug”

### Step 1 — Hello Streamlit
```bash
streamlit run step1_hello.py
```
**You should see:** a page that says *“Hello Streamlit”*. If not, fix Python/Streamlit install.

### Step 2 — Base Map
```bash
streamlit run step2_base_map.py
```
**You should see:** a base OpenStreetMap centered on **Sunamganj**.

### Step 3 — DEM Overlay
```bash
streamlit run step3_dem_overlay.py
```
- Keep the default path: `data/dem_sunamganj.tif` (synthetic DEM).
- **You should see:** a gray semi-transparent elevation layer on the map.

### Step 4 — Simple Flood (Bathtub)
```bash
streamlit run step4_flood_model.py
```
- Move the **Water level** slider.
- **You should see:** blue flooded regions + a flooded area estimate.

### Step 5 — Live OSM Layers
```bash
streamlit run step5_osm_layers.py
```
- The app fetches **roads**, **health posts**, and **cyclone shelters** via **Overpass (OSM)** for the DEM bbox.
- **You should see:** lines/points added to the map. Click a point for its name.
- If Overpass is slow, try again or change the API endpoint in the sidebar.

### Step 6 — Exports
```bash
streamlit run step6_exports.py
```
- Click **Export GeoTIFF + PNG** to create `jolchobi_flood_sunamganj.tif` and `jolchobi_map.png` in the project folder.

---

## Final App
```bash
streamlit run app.py  # Enhanced version (v2.0)
# Or run original: streamlit run appv1.py
```
**Features:**
- Method: **Bathtub** or **HAND (approx)**
- Presets: **Surma** gauge levels
- Live overlays: **Radar** (RainViewer) and **any WMS** URL/layer
- Live OSM layers: roads, health posts, cyclone shelters
- Summary stats + Exports

**Tips:**
- For a **real DEM**, replace `data/dem_sunamganj.tif` with an SRTM/FABDEM **clip** covering Sunamganj.
- For **judge demos**, turn on radar and add a WMS (e.g., flood forecast) if you have the URL.

---

## Troubleshooting
- **Overpass timeout**: re-run, or switch endpoint in the sidebar.
- **Rasterio/GeoPandas install issues**:
  - Ensure Python 3.10/3.11.
  - Install OS-level GDAL (see top of this README).
- **Blank map**: Check that `dem_sunamganj.tif` exists and the path matches.

---

## Talking points for the hackathon
- *“JolChobi turns open data into actionable flood visuals for Sunamganj responders, highlighting **health posts** and **cyclone shelters** at risk and estimating flooded **road kilometers**.”*
- *“We support **live OSM**, **radar tiles**, and any **WMS**—plus one-click GeoTIFF/PNG exports for WhatsApp and field ops.”*
- *“Roadmap: plug-in to **BWDB Surma gauge**, higher-fidelity **HAND** from drainage networks, **SMS alerts**, and **offline bundles** for union parishads.”*

## WMS endpoint:
- https://gibs.earthdata.nasa.gov/wms/epsg4326/best/wms.cgi

## Layer name:
- MODIS_Terra_CorrectedReflectance_TrueColor
