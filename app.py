import os, io, json, requests, math, numpy as np
import streamlit as st
import folium
from folium.raster_layers import ImageOverlay, WmsTileLayer, TileLayer
from folium.plugins import MousePosition
import rasterio
from rasterio import features
from rasterio.warp import transform_bounds
import geopandas as gpd
from shapely.geometry import shape, mapping, Point, Polygon
from shapely.ops import unary_union
from PIL import Image
from pyproj import Transformer

st.set_page_config(page_title="JolChobi — Sunamganj Flood Visualizer", layout="wide")
st.title("JolChobi 🌊 — Sunamganj Flood Visualizer")
st.caption("Live OSM overlays + fast flood modeling for responders. (Hackathon MVP)")

with st.sidebar:
    st.header("Controls")
    method = st.selectbox("Method", ["Bathtub (fast)", "HAND (approx)"], index=0)

    st.subheader("Water level")
    preset = st.selectbox(
        "Presets (Surma gauge)",
        ["Custom","Surma: Warning +0.5 m","Surma: Warning +1.0 m","Surma: Severe +1.5 m","Surma: Extreme +2.0 m"],
        index=1
    )
    custom_level = st.slider("Custom water level above river (m)", 0.0, 6.0, 1.0, 0.1)

    st.subheader("Live layers (optional)")
    add_rain = st.checkbox("Add live radar (RainViewer tiles)")
    wms_url = st.text_input("WMS endpoint (optional)", "")
    wms_layer = st.text_input("WMS Layer name (optional)", "")

    st.subheader("Data")
    dem_path = st.text_input("DEM (GeoTIFF)", "data/dem_sunamganj.tif")
    overpass_endpoint = st.text_input("Overpass API", "https://overpass-api.de/api/interpreter")

    export = st.button("Export GeoTIFF + PNG")

def overpass(query:str, endpoint:str)->dict:
    r = requests.post(endpoint, data={"data": query}, timeout=90)
    r.raise_for_status()
    return r.json()

# Load DEM
if not os.path.exists(dem_path):
    st.error("DEM not found. Put a GeoTIFF at data/dem_sunamganj.tif or update the path.")
    st.stop()

with rasterio.open(dem_path) as src:
    dem = src.read(1).astype("float32")
    dem = np.where(dem<-1000, np.nan, dem)
    dem_bounds = src.bounds
    dem_crs = src.crs
    dem_transform = src.transform

# Map bounds in WGS84
try:
    T = Transformer.from_crs(dem_crs, "EPSG:4326", always_xy=True)
    w, s = T.transform(dem_bounds.left, dem_bounds.bottom)
    e, n = T.transform(dem_bounds.right, dem_bounds.top)
except Exception:
    from rasterio.warp import transform_bounds as tb
    w, s, e, n = tb(dem_crs, "EPSG:4326", *dem_bounds)

# Handy bbox for Overpass
sunam_bbox = (s, w, n, e)

def osm_points(endpoint, bbox, what:str):
    s, w, n, e = bbox
    if what=="health":
        selectors = [
            'node["amenity"~"hospital|clinic|doctors|pharmacy"]',
            'way["amenity"~"hospital|clinic|doctors|pharmacy"]',
            'relation["amenity"~"hospital|clinic|doctors|pharmacy"]'
        ]
    else:
        selectors = [
            'node["amenity"="shelter"]',
            'way["amenity"="shelter"]',
            'relation["amenity"="shelter"]'
        ]

    bbox_clause = "\n  ".join(f"{sel}({s},{w},{n},{e});" for sel in selectors)
    q = f"""
    [out:json][timeout:90];
    (
      {bbox_clause}
    );
    out center;
    """
    js = overpass(q, endpoint)
    pts = []
    for el in js.get("elements", []):
        if el["type"]=="node":
            lon, lat = el["lon"], el["lat"]
        else:
            c = el.get("center")
            if not c: continue
            lat, lon = c["lat"], c["lon"]
        name = (el.get("tags") or {}).get("name","")
        if what!="health":
            tags = el.get("tags", {})
            lname = name.lower()
            stype = (tags.get("shelter_type","") or "").lower()
            if not ("cyclone" in lname or "storm" in lname or "cyclone" in stype or "storm" in stype):
                continue
        pts.append({"name": name or what, "lon": lon, "lat": lat})
    return gpd.GeoDataFrame(pts, geometry=gpd.points_from_xy([p["lon"] for p in pts],[p["lat"] for p in pts]), crs="EPSG:4326")

def osm_roads(endpoint, bbox):
    s, w, n, e = bbox
    q = f"""
    [out:json][timeout:90];
    (
      way["highway"]( {s},{w},{n},{e} );
    );
    out geom;
    """
    js = overpass(q, endpoint)
    feats = []
    for el in js.get("elements", []):
        if el["type"] != "way":
            continue
        coords = [(nd["lon"], nd["lat"]) for nd in el.get("geometry", [])]
        if len(coords) < 2:
            continue
        feats.append({
            "name": (el.get("tags") or {}).get("name", ""),
            "geometry": {"type": "LineString", "coordinates": coords}
        })

    if not feats:
        return gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")

    # Build GeoDataFrame with geometry set explicitly
    geoms = [shape(f["geometry"]) for f in feats]
    gdf = gpd.GeoDataFrame(feats, geometry=geoms, crs="EPSG:4326")
    return gdf


# Inundation
river_elev = np.nanpercentile(dem, 15)
if preset == "Custom":
    level = custom_level
elif preset == "Surma: Warning +0.5 m":
    level = 0.5
elif preset == "Surma: Warning +1.0 m":
    level = 1.0
elif preset == "Surma: Severe +1.5 m":
    level = 1.5
else:
    level = 2.0
target_level = river_elev + level

def quick_hand(dem, transform):
    low = dem <= np.nanpercentile(dem, 10)
    try:
        from scipy.ndimage import distance_transform_edt
        dist = distance_transform_edt(~low)
        pix = (abs(transform.a) + abs(transform.e)) / 2.0
        return dist * pix
    except Exception:
        return np.where(low, 0, 1).astype("float32")

if method.startswith("Bathtub"):
    flood = (dem <= target_level).astype("uint8")
else:
    hand = quick_hand(dem, dem_transform)
    flood = (hand <= level).astype("uint8")

# Map
center_lat, center_lon = (s+n)/2, (w+e)/2
m = folium.Map(location=[center_lat, center_lon], zoom_start=9, control_scale=True, tiles="OpenStreetMap")

if add_rain:
    TileLayer(
        tiles="https://tilecache.rainviewer.com/v2/radar/last/256/{z}/{x}/{y}/2/1_1.png",
        attr="RainViewer",
        name="Live Radar",
        overlay=True,
        control=True,
        opacity=0.6
    ).add_to(m)

if wms_url and wms_layer:
    WmsTileLayer(
        url=wms_url,
        layers=wms_layer,
        name="External WMS",
        fmt="image/png",
        transparent=True,
        version="1.3.0",
        control=True,
        opacity=0.7
    ).add_to(m)

# DEM overlay
dem_norm = (dem - np.nanmin(dem)) / (np.nanmax(dem)-np.nanmin(dem)+1e-6)
dem_img = (np.nan_to_num(dem_norm)*255).astype("uint8")
dem_rgba = np.dstack([dem_img, dem_img, dem_img, np.where(np.isfinite(dem), 120, 0).astype("uint8")])
Image.fromarray(dem_rgba, mode="RGBA").save("dem_overlay.png")
ImageOverlay(name="Elevation (DEM)", image="dem_overlay.png", bounds=[[s,w],[n,e]], opacity=0.5).add_to(m)

# Flood overlay
flood_rgba = np.zeros((flood.shape[0], flood.shape[1], 4), dtype="uint8")
flood_rgba[flood==1] = np.array([43,131,186,160], dtype="uint8")
Image.fromarray(flood_rgba, mode="RGBA").save("flood_overlay.png")
ImageOverlay(name="Inundation", image="flood_overlay.png", bounds=[[s,w],[n,e]], opacity=0.8).add_to(m)

# Live OSM layers
st.info("Fetching live OSM layers…")
roads = osm_roads(overpass_endpoint, sunam_bbox)
health = osm_points(overpass_endpoint, sunam_bbox, what="health")
shelters = osm_points(overpass_endpoint, sunam_bbox, what="cyclone_shelter")

if not roads.empty:
    folium.GeoJson(roads.to_json(), name="Roads", style_function=lambda x: {"color":"#444","weight":1}).add_to(m)

if not health.empty:
    for _, r in health.iterrows():
        folium.CircleMarker(location=[r["lat"], r["lon"]], radius=4,
                            color="#2ca25f", fill=True, fill_opacity=0.9,
                            popup=f"Health: {r.get('name','health')}").add_to(m)

if not shelters.empty:
    for _, r in shelters.iterrows():
        folium.CircleMarker(location=[r["lat"], r["lon"]], radius=4,
                            color="#de2d26", fill=True, fill_opacity=0.9,
                            popup=f"Cyclone Shelter: {r.get('name','shelter')}").add_to(m)

MousePosition().add_to(m)
folium.LayerControl(collapsed=False).add_to(m)
st.components.v1.html(m._repr_html_(), height=700)

# Impacts
Tinv = Transformer.from_crs("EPSG:4326", dem_crs, always_xy=True)
def sample_mask(mask, lon, lat, transform):
    x, y = Tinv.transform(lon, lat)
    col = int((x - transform.c)/transform.a)
    row = int((y - transform.f)/transform.e)
    if 0 <= row < mask.shape[0] and 0 <= col < mask.shape[1]:
        return mask[row, col]
    return 0

health_in = sum(int(sample_mask(flood, r["lon"], r["lat"], dem_transform)>0) for _, r in health.iterrows()) if not health.empty else 0
shelter_in = sum(int(sample_mask(flood, r["lon"], r["lat"], dem_transform)>0) for _, r in shelters.iterrows()) if not shelters.empty else 0

# Area estimate that works for geographic CRS
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
pix_area = pixel_area_km2(dem_transform, dem_crs, lat_mid)
flood_km2 = float(np.sum(flood==1) * pix_area)

st.markdown("### Summary")
st.write(f"- Method: **{method}**")
st.write(f"- Water level above river (m): **{level:.2f}** (preset: **{preset}**)")
st.write(f"- Estimated flooded area: **{flood_km2:.2f} km²**")
st.write(f"- Health posts in flooded zone: **{health_in}**")
st.write(f"- Cyclone shelters in flooded zone: **{shelter_in}**")

if export:
    # GeoTIFF export (same georef as DEM)
    with rasterio.open(dem_path) as src:
        profile = src.profile
    profile.update(dtype=rasterio.uint8, count=1, nodata=0, compress="lzw")
    out_tif = "jolchobi_flood_sunamganj.tif"
    with rasterio.open(out_tif, "w", **profile) as dst:
        dst.write(flood.astype("uint8"), 1)
    out_png = "jolchobi_map.png"
    Image.fromarray(flood_rgba, mode="RGBA").save(out_png)
    st.success("Exports saved in current folder.")
    st.markdown(f"- **GeoTIFF**: `{out_tif}`")
    st.markdown(f"- **PNG**: `{out_png}`")
