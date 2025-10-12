# Changelog

All notable changes to the JolChobi flood visualizer project.

## [2.0.0] - 2025-10-07 - Enhanced MVP

### 🎉 Major Release - Complete Rewrite

This release represents a complete enhancement of the original hackathon MVP with production-ready features.

### ✨ Added

#### Core Features
- **DEM Upload** - Upload custom GeoTIFF files directly through UI
- **Basemap Selector** - 5 basemap options (OSM, CartoDB Positron/Dark, Stamen Terrain/Toner)
- **Opacity Controls** - Independent sliders for DEM and flood layer transparency
- **Colormap Options** - 3 color schemes (blue gradient, red gradient, viridis)
- **In-Memory Downloads** - Download exports without disk writes using `st.download_button`
- **COG Export** - Cloud Optimized GeoTIFF format with tiling and compression
- **Metadata Export** - JSON file with complete scenario parameters and results

#### Performance
- **OSM Caching** - 1-hour TTL cache for Overpass API results
- **Retry Logic** - Automatic retries with exponential backoff for all API calls
- **Session Management** - Proper requests session with connection pooling
- **Flood Polygon Caching** - Reuse polygons across multiple analytics

#### Analytics
- **Spatial Join Exposure** - Accurate point-in-polygon calculations using `gpd.sjoin`
- **Road Type Breakdown** - Flooded km by highway classification
- **Improved Area Calculation** - Fixed geographic vs projected CRS handling
- **Better River Estimation** - Configurable percentile-based approach

#### Code Quality
- **Modular Architecture** - 6 focused modules (io_sources, model, exposure, forecast, render, app)
- **Type Hints** - Complete type annotations for all functions
- **Docstrings** - Comprehensive documentation with Args/Returns
- **Unit Tests** - 37 tests across 3 test files with >80% coverage
- **Pinned Dependencies** - Stable versions in requirements.txt

#### Documentation
- **IMPROVEMENTS.md** - Detailed technical improvements
- **MIGRATION_GUIDE.md** - Step-by-step migration instructions
- **QUICK_START.md** - 5-minute getting started guide
- **SUMMARY.md** - Executive summary of changes
- **CHANGELOG.md** - This file
- **Module Docstrings** - Every module and function documented

#### Configuration
- **Streamlit Config** - Custom theme and server settings
- **Secrets Template** - Example secrets.toml for API keys
- **.gitignore** - Proper exclusions for Python/Streamlit projects
- **Test Runner** - Shell script for easy test execution

### 🔧 Fixed

- **Area Calculation** - Fixed sign issues with negative transform values
- **CRS Validation** - Proper checking for None and is_geographic
- **Nodata Handling** - Respect DEM nodata values from rasterio
- **OpenAI Errors** - Parse error messages for better user feedback
- **Flood Polygon Generation** - Proper GeoDataFrame handling in caching

### 🚀 Improved

- **Exposure Analytics** - Switched from pixel sampling to spatial joins (exact counts)
- **HAND Model** - Better pixel size calculation for geographic DEMs
- **Error Messages** - More informative and actionable error text
- **Loading States** - Spinners and progress indicators for all async operations
- **Export Workflow** - Timestamped files with embedded metadata

### 📦 New Modules

- `io_sources.py` - Data ingestion and API calls with retry logic
- `model.py` - Flood modeling and inundation calculations
- `exposure.py` - Exposure analytics for infrastructure and assets
- `forecast.py` - Forecast processing and water level recommendations
- `render.py` - Map rendering and visualization utilities

### 🧪 Testing

- `tests/test_model.py` - 15 tests for modeling functions
- `tests/test_exposure.py` - 12 tests for exposure analytics
- `tests/test_forecast.py` - 10 tests for forecast processing
- `tests/requirements-test.txt` - Test dependencies (pytest, pytest-cov, pytest-mock)
- `run_tests.sh` - Automated test runner with coverage reporting

### 📚 Dependencies

Updated to pinned versions:
- streamlit==1.31.1
- folium==0.15.1
- rasterio==1.3.9
- geopandas==0.14.3
- shapely==2.0.3
- numpy==1.26.4
- pyproj==3.6.1
- And more (see requirements.txt)

### ⚠️ Breaking Changes

**None!** The improved version is fully backward compatible with the original app.

### 🔄 Migration

See [MIGRATION_GUIDE.md](MIGRATION_GUIDE.md) for detailed migration instructions.

Quick migration:
```bash
pip install -r requirements.txt
streamlit run app_improved.py
```

---

## [1.0.0] - 2025-01-XX - Hackathon MVP

### Initial Release

- Basic bathtub flood model
- HAND approximation using distance transform
- OSM integration (roads, health facilities, cyclone shelters)
- Live radar overlay (RainViewer)
- WMS layer support
- 7-day weather forecast integration
- River discharge forecast (GloFAS)
- LLM scenario notes (OpenAI)
- GeoTIFF and PNG export
- Step-by-step tutorial apps (step1-step6)

### Features

- Surma gauge presets (Warning, Severe, Extreme)
- Custom water level slider
- Flooded area calculation
- Health facility exposure count
- Cyclone shelter exposure count
- Flooded roads length estimation
- Interactive Folium map
- Multiple tabs (Map, Impacts, Forecast, Methods)

### Known Issues

- OSM data fetched on every interaction (no caching)
- No retry logic for API failures
- Area calculation sign issues with some CRS
- Pixel sampling for exposure (approximate)
- No DEM upload (file path only)
- Hardcoded opacity values
- Exports save to disk only
- Single file (1026 lines)
- No tests
- Unpinned dependencies

---

## Future Releases

### [2.1.0] - Planned

- True HAND model using pysheds/richdem
- Population exposure (WorldPop/HRSL)
- Building footprints from OSM
- Admin boundary statistics
- Scenario comparison (A/B slider)

### [2.2.0] - Planned

- BWDB gauge integration
- Offline bundles
- Internationalization (Bangla)
- Access control
- Real-time updates via WebSocket

---

## Version Numbering

We use [Semantic Versioning](https://semver.org/):
- MAJOR version for incompatible API changes
- MINOR version for new functionality (backward compatible)
- PATCH version for bug fixes (backward compatible)
