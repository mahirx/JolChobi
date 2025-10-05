import streamlit as st
import folium, requests, json, numpy as np, rasterio, math
from folium.raster_layers import ImageOverlay
from PIL import Image

st.set_page_config(page_title="JolChobi Step 6", layout="wide")
st.title("JolChobi • Step 6: Exports + Final Polish")

dem_path = st.text_input("DEM path (GeoTIFF)", "data/dem_sunamganj.tif")
water_level_m = st.slider("Water level above river (m)", 0.0, 6.0, 1.2, 0.1)
export = st.button("Export GeoTIFF + PNG")

with rasterio.open(dem_path) as src:
    dem = src.read(1).astype("float32")
    dem = np.where(dem<-1000, np.nan, dem)
    bounds = src.bounds
    crs = src.crs
    transform = src.transform

# bounds in WGS84
try:
    from pyproj import Transformer
    T = Transformer.from_crs(crs, "EPSG:4326", always_xy=True)
    w, s = T.transform(bounds.left, bounds.bottom)
    e, n = T.transform(bounds.right, bounds.top)
except Exception:
    from rasterio.warp import transform_bounds as tb
    w, s, e, n = tb(crs, "EPSG:4326", *bounds)

river_elev = np.nanpercentile(dem, 15)
target = river_elev + water_level_m
flood = (dem <= target).astype("uint8")

m = folium.Map(location=[(s+n)/2, (w+e)/2], zoom_start=9, control_scale=True)
dem_norm = (dem - np.nanmin(dem)) / (np.nanmax(dem)-np.nanmin(dem)+1e-6)
dem_img = (np.nan_to_num(dem_norm)*255).astype("uint8")
rgba_dem = np.dstack([dem_img, dem_img, dem_img, np.where(np.isfinite(dem), 120, 0).astype("uint8")])
Image.fromarray(rgba_dem, mode="RGBA").save("dem_overlay_step6.png")
ImageOverlay(name="Elevation (DEM)", image="dem_overlay_step6.png", bounds=[[s,w],[n,e]], opacity=0.5).add_to(m)

rgba_flood = np.zeros((flood.shape[0], flood.shape[1], 4), dtype="uint8")
rgba_flood[flood==1] = np.array([43,131,186,160], dtype="uint8")
Image.fromarray(rgba_flood, mode="RGBA").save("flood_overlay_step6.png")
ImageOverlay(name="Inundation", image="flood_overlay_step6.png", bounds=[[s,w],[n,e]], opacity=0.8).add_to(m)

st.components.v1.html(m._repr_html_(), height=680)

if export:
    # GeoTIFF export
    with rasterio.open(dem_path) as src:
        prof = src.profile
    prof.update(dtype=rasterio.uint8, count=1, nodata=0, compress="lzw")
    out_tif = "jolchobi_flood_sunamganj.tif"
    with rasterio.open(out_tif, "w", **prof) as dst:
        dst.write(flood.astype("uint8"), 1)

    # PNG export
    out_png = "jolchobi_map.png"
    Image.fromarray(rgba_flood, mode="RGBA").save(out_png)

    st.success("Exports saved.")
    st.markdown(f"- **GeoTIFF**: `{out_tif}`")
    st.markdown(f"- **PNG**: `{out_png}`")
