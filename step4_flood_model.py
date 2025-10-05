import streamlit as st
import folium
from folium.raster_layers import ImageOverlay
import numpy as np
import rasterio

st.set_page_config(page_title="JolChobi Step 4", layout="wide")
st.title("JolChobi • Step 4: Simple Flood (Bathtub)")

dem_path = st.text_input("DEM path (GeoTIFF)", "data/dem_sunamganj.tif")
water_level_m = st.slider("Water level above river (m)", 0.0, 6.0, 1.0, 0.1)

with rasterio.open(dem_path) as src:
    dem = src.read(1).astype("float32")
    dem = np.where(dem<-1000, np.nan, dem)
    bounds = src.bounds
    crs = src.crs
    transform = src.transform

# reference "river level" using low percentile
river_elev = np.nanpercentile(dem, 15)
target = river_elev + water_level_m
flood = (dem <= target).astype("uint8")

# map center
try:
    from pyproj import Transformer
    T = Transformer.from_crs(crs, "EPSG:4326", always_xy=True)
    w, s = T.transform(bounds.left, bounds.bottom)
    e, n = T.transform(bounds.right, bounds.top)
except Exception:
    from rasterio.warp import transform_bounds as tb
    w, s, e, n = tb(crs, "EPSG:4326", *bounds)

m = folium.Map(location=[(s+n)/2, (w+e)/2], zoom_start=9, control_scale=True)

# DEM
dem_norm = (dem - np.nanmin(dem)) / (np.nanmax(dem)-np.nanmin(dem)+1e-6)
dem_img = (np.nan_to_num(dem_norm)*255).astype("uint8")
rgba_dem = np.dstack([dem_img, dem_img, dem_img, np.where(np.isfinite(dem), 120, 0).astype("uint8")])
from PIL import Image
Image.fromarray(rgba_dem, mode="RGBA").save("dem_overlay_step4.png")
ImageOverlay(name="Elevation (DEM)", image="dem_overlay_step4.png", bounds=[[s,w],[n,e]], opacity=0.5).add_to(m)

# Flood (blue)
rgba_flood = np.zeros((flood.shape[0], flood.shape[1], 4), dtype="uint8")
rgba_flood[flood==1] = np.array([43,131,186,160], dtype="uint8")
Image.fromarray(rgba_flood, mode="RGBA").save("flood_overlay_step4.png")
ImageOverlay(name="Inundation", image="flood_overlay_step4.png", bounds=[[s,w],[n,e]], opacity=0.8).add_to(m)

st.components.v1.html(m._repr_html_(), height=680)

# Approx area calc: handle geographic CRS
def pixel_area_km2(transform, crs, lat_mid):
    a = abs(transform.a); e = abs(transform.e)
    if crs and getattr(crs, "is_geographic", False):
        deg_to_km = 111.32
        lon_km = deg_to_km*math.cos(math.radians(lat_mid))
        lat_km = deg_to_km
        return a*lon_km * e*lat_km
    else:
        return (a*e)/1e6

lat_mid = (s+n)/2
pix_area = pixel_area_km2(transform, crs, lat_mid)
flood_km2 = float(np.sum(flood==1) * pix_area)
st.info(f"Estimated flooded area: {flood_km2:.2f} km²")
