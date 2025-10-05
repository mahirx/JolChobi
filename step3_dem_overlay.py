import streamlit as st
import folium
from folium.raster_layers import ImageOverlay
import numpy as np
import rasterio
from rasterio.warp import transform_bounds

st.set_page_config(page_title="JolChobi Step 3", layout="wide")
st.title("JolChobi • Step 3: DEM Overlay")

dem_path = st.text_input("DEM path (GeoTIFF)", "data/dem_sunamganj.tif")

with rasterio.open(dem_path) as src:
    dem = src.read(1).astype("float32")
    dem = np.where(dem<-1000, np.nan, dem)
    bounds = src.bounds
    crs = src.crs

# map bounds in WGS84
try:
    from pyproj import Transformer
    T = Transformer.from_crs(crs, "EPSG:4326", always_xy=True)
    w, s = T.transform(bounds.left, bounds.bottom)
    e, n = T.transform(bounds.right, bounds.top)
except Exception:
    from rasterio.warp import transform_bounds as tb
    w, s, e, n = tb(crs, "EPSG:4326", *bounds)

center_lat, center_lon = (s+n)/2, (w+e)/2
m = folium.Map(location=[center_lat, center_lon], zoom_start=9, control_scale=True)

# build grayscale overlay
dem_norm = (dem - np.nanmin(dem)) / (np.nanmax(dem)-np.nanmin(dem)+1e-6)
dem_img = (np.nan_to_num(dem_norm)*255).astype("uint8")
rgba = np.dstack([dem_img, dem_img, dem_img, np.where(np.isfinite(dem), 120, 0).astype("uint8")])

from PIL import Image
tmp = "dem_overlay_step3.png"
Image.fromarray(rgba, mode="RGBA").save(tmp)

ImageOverlay(name="Elevation (DEM)", image=tmp, bounds=[[s,w],[n,e]], opacity=0.5).add_to(m)
st.components.v1.html(m._repr_html_(), height=650)
st.success("DEM overlay added. You should see a gray hillshade-like layer.")
