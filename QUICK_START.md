# JolChobi Quick Start Guide

## 🎯 Get Running in 5 Minutes

### Step 1: Install Dependencies
```bash
pip install -r requirements.txt
```

### Step 2: Run the App
```bash
streamlit run app.py
```

### Step 3: Explore Features

The app will open in your browser at `http://localhost:8501`

## 🎮 Key Features to Try

### 1. **Upload Your Own DEM**
- ☑️ Check "Upload custom DEM" in sidebar
- 📤 Upload a GeoTIFF file
- 🗺️ Map updates automatically

### 2. **Adjust Water Levels**
- 🎚️ Use presets: Warning +0.5m, Severe +1.5m, etc.
- 🔧 Or drag the custom slider (0-6m)
- 👁️ Watch flood extent change in real-time

### 3. **Change Visualization**
- 🗺️ **Basemap**: Try CartoDB Positron or Stamen Terrain
- 🎨 **Colormap**: Switch between blue, red, or viridis gradients
- 🔆 **Opacity**: Adjust DEM and flood layer transparency

### 4. **Fetch Live Data**
- 🌦️ Click "Fetch 7-day outlook" for weather forecast
- 📊 View rainfall, wind, and river discharge predictions
- 🤖 Add OpenAI API key for AI-generated scenario notes

### 5. **Export Results**
- 💾 Choose "In-memory download" (no disk clutter)
- ☑️ Enable "Export as COG" for cloud-optimized GeoTIFF
- ☑️ Include metadata JSON for full scenario details
- 📥 Click "Export GeoTIFF + PNG" to download

## 📊 Understanding the Tabs

### **Interactive Map**
- Pan, zoom, toggle layers
- Click markers for facility names
- Use layer control (top right) to show/hide

### **Exposure Summary**
- See flooded area in km²
- Count affected health facilities and shelters
- View flooded roads by type (primary, secondary, etc.)

### **Next-Week Outlook**
- 7-day rainfall and wind forecast
- Hourly precipitation chart
- River discharge predictions
- AI scenario brief (if API key provided)

### **How the Model Works**
- Learn about Bathtub vs HAND methods
- Understand data sources
- See what's new in this version

## 🔑 Optional: Add OpenAI API Key

For AI-generated scenario notes:

### Method 1: Streamlit Secrets (Recommended)
Create `.streamlit/secrets.toml`:
```toml
OPENAI_API_KEY = "sk-your-key-here"
```

### Method 2: Enter in Sidebar
- Paste key in "LLM API key" field
- Select model (gpt-4o-mini is fastest/cheapest)
- Click "Ask LLM for scenario note"

## 🧪 Test with Sample Data

The included synthetic DEM (`data/dem_sunamganj.tif`) works out of the box:

```bash
# Just run the app - it uses the sample DEM by default
streamlit run app.py
```

Try these scenarios:
1. **Low flood**: Preset "Warning +0.5 m"
2. **Moderate**: Preset "Severe +1.5 m"  
3. **Extreme**: Preset "Extreme +2.0 m"
4. **Custom**: Slider to 3.5 m

## 🐛 Troubleshooting

### "DEM not found"
- Ensure `data/dem_sunamganj.tif` exists
- Or upload your own GeoTIFF

### "Overpass timeout"
- OSM data fetch failed - just retry
- Or change endpoint in sidebar

### "LLM guidance failed"
- Check API key is valid
- Ensure you have credits
- Try a different model

### Slow performance
- First run caches OSM data (takes ~30s)
- Subsequent runs are instant (1-hour cache)
- Large DEMs may need more RAM

## 📚 Learn More

- **Full improvements**: See [`IMPROVEMENTS.md`](IMPROVEMENTS.md)
- **Migration guide**: See [`MIGRATION_GUIDE.md`](MIGRATION_GUIDE.md)
- **Run tests**: `pytest tests/ -v`

## 🎯 Next Steps

1. ✅ Try the app with sample data
2. ✅ Upload your own DEM for your area
3. ✅ Fetch live forecast data
4. ✅ Export results as COG
5. ✅ Read the full documentation
6. ✅ Contribute improvements!

## 💡 Pro Tips

- **Keyboard shortcuts**: Press `R` to rerun, `C` to clear cache
- **Multiple scenarios**: Open app in multiple browser tabs
- **Compare methods**: Toggle between Bathtub and HAND
- **Save presets**: Bookmark URLs with parameters
- **Batch export**: Run headless with Selenium for automation

## 🚀 Deploy to Production

### Streamlit Cloud
```bash
# Push to GitHub
git add .
git commit -m "Deploy JolChobi"
git push

# Deploy at share.streamlit.io
# Add secrets in dashboard
```

### Docker
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD ["streamlit", "run", "app.py", "--server.port=8501"]
```

### Local Server
```bash
# Run on custom port
streamlit run app.py --server.port=8080

# Run in background
nohup streamlit run app.py &
```

---

**Happy Flood Modeling! 🌊**

For questions or issues, check the documentation or open an issue on GitHub.
