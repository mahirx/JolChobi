# Migration Guide: Original → Improved JolChobi

This guide helps you transition from the original `app.py` to the improved modular version.

## Quick Migration

### Option 1: Run Improved Version Alongside Original

```bash
# Run enhanced version (now the main app)
streamlit run app.py

# Or run original v1.0
streamlit run appv1.py
```

### Option 2: Replace Original (Recommended)

```bash
# The improved version is now app.py (already done!)
# Original is preserved as appv1.py

# Just update dependencies
pip install -r requirements.txt
```

## Breaking Changes

### None! 

The improved version is **fully backward compatible**. All features from the original app work the same way, with these additions:

## New Features You Get

### 1. DEM Upload
```python
# Before: Only file path
dem_path = st.text_input("DEM (GeoTIFF)", "data/dem_sunamganj.tif")

# After: Upload OR file path
use_upload = st.checkbox("Upload custom DEM")
if use_upload:
    uploaded_dem = st.file_uploader("Upload DEM (GeoTIFF)", type=["tif", "tiff"])
```

### 2. Basemap Selection
```python
# Before: Only OpenStreetMap
m = folium.Map(location=[lat, lon], tiles="OpenStreetMap")

# After: 5 options
basemap = st.selectbox("Basemap", [
    "OpenStreetMap", 
    "CartoDB Positron", 
    "CartoDB Dark Matter",
    "Stamen Terrain",
    "Stamen Toner"
])
```

### 3. Opacity Controls
```python
# Before: Hardcoded
opacity=0.5  # DEM
opacity=0.8  # Flood

# After: User-controlled sliders
dem_opacity = st.slider("DEM opacity", 0.0, 1.0, 0.5, 0.05)
flood_opacity = st.slider("Flood opacity", 0.0, 1.0, 0.8, 0.05)
```

### 4. In-Memory Downloads
```python
# Before: Saves to disk
Image.fromarray(flood_rgba).save("flood_overlay.png")
st.success("Exports saved in current folder.")

# After: Download buttons (no disk writes)
st.download_button(
    label="📥 Download GeoTIFF",
    data=tif_buffer,
    file_name=f"jolchobi_flood_{timestamp}.tif"
)
```

### 5. COG Export
```python
# Before: Standard GeoTIFF
profile.update(dtype=rasterio.uint8, count=1, compress="lzw")

# After: Cloud Optimized GeoTIFF option
if export_cog:
    profile.update(
        tiled=True,
        blockxsize=256,
        blockysize=256,
        compress="deflate"
    )
```

## Code Migration Examples

### Using New Modules

#### Before (all in app.py):
```python
def overpass(query:str, endpoint:str)->dict:
    r = requests.post(endpoint, data={"data": query}, timeout=90)
    r.raise_for_status()
    return r.json()

roads = osm_roads(overpass_endpoint, sunam_bbox)
```

#### After (import from modules):
```python
from io_sources import osm_roads

roads = osm_roads(overpass_endpoint, sunam_bbox)  # Now cached!
```

### Exposure Analytics

#### Before (pixel sampling):
```python
def sample_mask(mask, lon, lat, transform):
    x, y = Tinv.transform(lon, lat)
    col = int((x - transform.c)/transform.a)
    row = int((y - transform.f)/transform.e)
    if 0 <= row < mask.shape[0] and 0 <= col < mask.shape[1]:
        return mask[row, col]
    return 0

health_in = sum(int(sample_mask(flood, r["lon"], r["lat"], dem_transform)>0) 
                for _, r in health.iterrows())
```

#### After (spatial joins):
```python
from exposure import calculate_point_exposure

health_in = calculate_point_exposure(health, flood, dem_transform, dem_crs)
```

### Flood Modeling

#### Before (inline):
```python
if method.startswith("Bathtub"):
    flood = (dem <= target_level).astype("uint8")
    surface_delta = np.maximum(target_level - dem, 0)
    # ... more code
```

#### After (modular):
```python
from model import bathtub_flood, hand_flood

if method.startswith("Bathtub"):
    flood, depth = bathtub_flood(dem, target_level)
else:
    hand = quick_hand(dem, dem_transform, dem_crs)
    flood, depth = hand_flood(dem, hand, level)
```

### Rendering

#### Before (save to disk):
```python
dem_rgba = np.dstack([dem_img, dem_img, dem_img, alpha])
Image.fromarray(dem_rgba, mode="RGBA").save("dem_overlay.png")
ImageOverlay(name="Elevation", image="dem_overlay.png", bounds=[[s,w],[n,e]]).add_to(m)
```

#### After (in-memory):
```python
from render import create_dem_overlay

dem_data_url = create_dem_overlay(dem, [[s, w], [n, e]], opacity=dem_opacity)
ImageOverlay(name="Elevation", image=dem_data_url, bounds=[[s,w],[n,e]]).add_to(m)
```

## Performance Improvements

### Caching
All OSM and forecast API calls are now cached:

```python
@st.cache_data(show_spinner=False, ttl=3600)
def osm_roads(endpoint: str, bbox: Tuple) -> gpd.GeoDataFrame:
    # Cached for 1 hour
```

**Impact**: Slider adjustments no longer re-fetch OSM data!

### Retry Logic
API calls now retry automatically:

```python
from io_sources import create_retry_session

session = create_retry_session(retries=3, backoff_factor=0.5)
# Handles 429, 500, 502, 503, 504 with exponential backoff
```

**Impact**: More reliable in poor network conditions.

## Testing Your Migration

### 1. Install Dependencies
```bash
pip install -r requirements.txt
streamlit run app.py
```
### 2. Run Tests
```bash
# Install test dependencies
pip install -r tests/requirements-test.txt

# Run all tests
{{ ... }}

**Problem**: `ModuleNotFoundError: No module named 'io_sources'`

**Solution**: Ensure all module files are in the same directory as `app.py`:
```
Jolchobi/
├── app.py
├── io_sources.py
├── model.py
├── exposure.py
├── forecast.py
└── render.py
{{ ... }}

### Caching Issues

**Problem**: OSM data not updating

**Solution**: Clear Streamlit cache:
```bash
# In the app, press 'C' then 'Enter'
# Or programmatically:
st.cache_data.clear()
```

### API Rate Limits

**Problem**: Overpass API timeouts

**Solution**: The improved version has retry logic, but you can also:
```python
# Increase cache TTL to reduce requests
@st.cache_data(show_spinner=False, ttl=7200)  # 2 hours
```

### Memory Issues with Large DEMs

**Problem**: Out of memory with large uploads

**Solution**: 
```python
# Use chunked reading for large files
with rasterio.open(dem_path) as src:
    dem = src.read(1, out_shape=(src.height // 2, src.width // 2))
```

## Rollback Plan

If you need to revert:

```bash
# Restore original v1.0
cp appv1.py app.py

# Revert dependencies (if needed)
git checkout requirements.txt

# Or use original unpinned versions
pip install streamlit folium rasterio geopandas shapely numpy branca pyproj Pillow scipy requests matplotlib
```

## Getting Help

### Check Logs
```bash
# Run with verbose logging
streamlit run app.py --logger.level=debug
```

### Common Issues

1. **"DEM has no CRS"** → Ensure GeoTIFF has projection info
2. **"Overpass timeout"** → Retry or use different endpoint
3. **"LLM API error"** → Check API key and model availability
4. **"Spatial join failed"** → Ensure CRS compatibility

### Report Issues

If you find bugs:
1. Check `IMPROVEMENTS.md` for known issues
2. Run tests: `pytest tests/ -v`
3. Include error traceback and DEM metadata

## Next Steps

After migration:

1. ✅ **Test thoroughly** with your actual DEM data
2. ✅ **Configure API keys** in Streamlit secrets
3. ✅ **Customize colormaps** for your use case
4. ✅ **Add admin boundaries** (see Future Enhancements)
5. ✅ **Deploy** to Streamlit Cloud or your server

## API Key Configuration

### Streamlit Secrets (Recommended)

Create `.streamlit/secrets.toml`:
```toml
OPENAI_API_KEY = "sk-..."
```

The improved app checks for this automatically:
```python
llm_api_key = st.text_input(
    "LLM API key",
    value=st.secrets.get("OPENAI_API_KEY", "") if hasattr(st, 'secrets') else "",
    type="password"
)
```

### Environment Variables

```bash
export OPENAI_API_KEY="sk-..."
streamlit run app_improved.py
```

## Deployment Checklist

- [ ] Update `requirements.txt` with pinned versions
- [ ] Test with production DEM data
- [ ] Configure API keys in secrets
- [ ] Set appropriate cache TTLs
- [ ] Test all export formats
- [ ] Verify OSM data freshness
- [ ] Check forecast API limits
- [ ] Test on target deployment platform
- [ ] Document custom configurations
- [ ] Train users on new features

## Summary

The improved version is a **drop-in replacement** with:
- ✅ All original features preserved
- ✅ Better performance (caching, retries)
- ✅ More accurate analytics (spatial joins)
- ✅ Enhanced UX (uploads, controls, downloads)
- ✅ Production-ready code (modular, tested, typed)

**Recommended approach**: Run both versions in parallel for a week, then fully migrate to the improved version.
