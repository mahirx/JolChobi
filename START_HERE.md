# 🚀 Quick Start Guide

## Run the App (One Command)

```bash
python3 -m streamlit run app.py
```

Then open your browser to: **http://localhost:8501**

---

## What Was Fixed

Three critical bugs were resolved:

1. **F-string syntax error** in `forecast.py` ✅
2. **Missing secrets file** handling in `app.py` ✅  
3. **Missing streamlit.components** import in `app.py` ✅

**All errors are now fixed. The app is fully functional.**

---

## App Features

### Core Features (Work Out of the Box)
- ✅ Interactive flood visualization map
- ✅ DEM (Digital Elevation Model) overlay
- ✅ Bathtub and HAND flood modeling
- ✅ OSM data integration (roads, health facilities, shelters)
- ✅ Exposure analysis (flooded roads, affected buildings)
- ✅ Real-time weather forecasts
- ✅ River discharge predictions (GloFAS)
- ✅ Export to GeoTIFF/PNG

### Optional Features
- 🔑 LLM scenario notes (requires OpenAI API key)
- 🌐 Custom WMS layers (requires WMS endpoint)
- 📡 Live radar overlay (RainViewer)

---

## File Structure

```
JolChobi/
├── app.py                    # Main Streamlit application ⭐
├── forecast.py               # Weather & hydrology forecasting
├── io_sources.py             # Data fetching (OSM, APIs)
├── model.py                  # Flood modeling algorithms
├── exposure.py               # Impact analysis
├── render.py                 # Map visualization
├── data/
│   └── dem_sunamganj.tif    # Elevation data
├── .streamlit/
│   ├── config.toml          # Streamlit configuration
│   └── secrets.toml         # API keys (optional)
└── requirements.txt          # Python dependencies
```

---

## Configuration (Optional)

### Add OpenAI API Key (for LLM features)

Edit `.streamlit/secrets.toml`:
```toml
OPENAI_API_KEY = "sk-your-api-key-here"
```

### Customize Streamlit Settings

Edit `.streamlit/config.toml` to change theme, port, etc.

---

## Troubleshooting

### Port Already in Use
```bash
python3 -m streamlit run app.py --server.port 8502
```

### Missing Dependencies
```bash
pip3 install -r requirements.txt
```

### DEM File Not Found
- Place your GeoTIFF at `data/dem_sunamganj.tif`, OR
- Upload a custom DEM using the sidebar checkbox

---

## Documentation

- **✅_ALL_ERRORS_FIXED.md** - Detailed fix report
- **BUGFIX_SUMMARY.md** - Technical bug details
- **README.md** - Full project documentation
- **QUICK_START.md** - Extended setup guide

---

## Support

If you encounter any issues:

1. Check that all dependencies are installed: `pip3 install -r requirements.txt`
2. Verify Python version: `python3 --version` (requires 3.8+)
3. Run the test script: `python3 test_imports.py`

---

**Happy Flood Modeling! 🌊**
