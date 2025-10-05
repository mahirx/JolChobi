import streamlit as st
import folium, requests, json
from folium.raster_layers import ImageOverlay
import numpy as np
import rasterio, math

st.set_page_config(page_title="JolChobi Step 5", layout="wide")
st.title("JolChobi • Step 5: Live OSM Layers (roads, health, cyclone shelters)")

dem_path = st.text_input("DEM path (GeoTIFF)", "data/dem_sunamganj.tif")
overpass_endpoint = st.text_input("Overpass API", "https://overpass-api.de/api/interpreter")
water_level_m = st.slider("Water level above river (m)", 0.0, 6.0, 1.0, 0.1)

def overpass(query, endpoint):
    r = requests.post(endpoint, data={"data": query}, timeout=90)
    r.raise_for_status()
    return r.json()

with rasterio.open(dem_path) as src:
    dem = src.read(1).astype("float32")
    dem = np.where(dem<-1000, np.nan, dem)
    bounds = src.bounds
    crs = src.crs
    transform = src.transform

# map bounds
try:
    from pyproj import Transformer
    T = Transformer.from_crs(crs, "EPSG:4326", always_xy=True)
    w, s = T.transform(bounds.left, bounds.bottom)
    e, n = T.transform(bounds.right, bounds.top)
except Exception:
    from rasterio.warp import transform_bounds as tb
    w, s, e, n = tb(crs, "EPSG:4326", *bounds)

# flood
river_elev = np.nanpercentile(dem, 15)
target = river_elev + water_level_m
flood = (dem <= target).astype("uint8")

# OSM bbox string
bbox = f"({s},{w},{n},{e})"

# Roads
q_roads = f"""
[out:json][timeout:90];
way["highway"]{bbox};
out geom;
"""
js_roads = overpass(q_roads, overpass_endpoint)

# Health (amenity)
q_health = f"""
[out:json][timeout:90];
(
  node["amenity"~"hospital|clinic|doctors|pharmacy"]{bbox};
  way["amenity"~"hospital|clinic|doctors|pharmacy"]{bbox};
  relation["amenity"~"hospital|clinic|doctors|pharmacy"]{bbox};
);
out center;
"""
js_health = overpass(q_health, overpass_endpoint)

# Cyclone shelters (best-effort tags)
q_shelter = f"""
[out:json][timeout:90];
(
  node["amenity"="shelter"]{bbox};
  way["amenity"="shelter"]{bbox};
  relation["amenity"="shelter"]{bbox};
);
out center;
"""
js_shelter = overpass(q_shelter, overpass_endpoint)

m = folium.Map(location=[(s+n)/2, (w+e)/2], zoom_start=9, control_scale=True)

# DEM overlay
dem_norm = (dem - np.nanmin(dem)) / (np.nanmax(dem)-np.nanmin(dem)+1e-6)
dem_img = (np.nan_to_num(dem_norm)*255).astype("uint8")
from PIL import Image
rgba_dem = np.dstack([dem_img, dem_img, dem_img, np.where(np.isfinite(dem), 120, 0).astype("uint8")])
Image.fromarray(rgba_dem, mode="RGBA").save("dem_overlay_step5.png")
ImageOverlay(name="Elevation (DEM)", image="dem_overlay_step5.png", bounds=[[s,w],[n,e]], opacity=0.5).add_to(m)

# Flood overlay
rgba_flood = np.zeros((flood.shape[0], flood.shape[1], 4), dtype="uint8")
rgba_flood[flood==1] = np.array([43,131,186,160], dtype="uint8")
Image.fromarray(rgba_flood, mode="RGBA").save("flood_overlay_step5.png")
ImageOverlay(name="Inundation", image="flood_overlay_step5.png", bounds=[[s,w],[n,e]], opacity=0.8).add_to(m)

# Roads layer
import shapely.geometry as sg, geopandas as gpd
roads_geoms = []
for el in js_roads.get("elements", []):
    if el.get("type")!="way": continue
    coords = [(n["lat"], n["lon"]) for n in el.get("geometry", [])]
    if len(coords) < 2: continue
    # flip to lon,lat order for GeoJSON
    coords_ll = [(lon, lat) for (lat,lon) in coords]
    roads_geoms.append(sg.LineString(coords_ll))
if roads_geoms:
    gdf = gpd.GeoDataFrame(geometry=roads_geoms, crs="EPSG:4326")
    folium.GeoJson(gdf.to_json(), name="Roads", style_function=lambda x: {"color":"#444","weight":1}).add_to(m)

# Health points
def add_points(js, label, color):
    for el in js.get("elements", []):
        if el["type"]=="node":
            lat, lon = el["lat"], el["lon"]
        else:
            c = el.get("center")
            if not c: continue
            lat, lon = c["lat"], c["lon"]
        name = (el.get("tags") or {}).get("name", label)
        folium.CircleMarker(location=[lat, lon], radius=4, color=color, fill=True, fill_opacity=0.9, popup=f"{label}: {name}").add_to(m)

add_points(js_health, "Health", "#2ca25f")
# Filter cyclone shelters by name/tag hint
filtered = {"elements": []}
for el in js_shelter.get("elements", []):
    tags = el.get("tags", {})
    name = (tags.get("name","") or "").lower()
    stype = (tags.get("shelter_type","") or "").lower()
    if "cyclone" in name or "storm" in name or "cyclone" in stype or "storm" in stype:
        filtered["elements"].append(el)
add_points(filtered, "Cyclone Shelter", "#de2d26")

folium.LayerControl(collapsed=False).add_to(m)
st.components.v1.html(m._repr_html_(), height=700)
st.success("Live OSM layers added. Try zooming and clicking points.")

# Impact (simple point-in-flood sampling)
from pyproj import Transformer
Tinv = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
def sample_mask(mask, lon, lat, transform):
    x, y = Tinv.transform(lon, lat)
    col = int((x - transform.c)/transform.a)
    row = int((y - transform.f)/transform.e)
    if 0 <= row < mask.shape[0] and 0 <= col < mask.shape[1]:
        return mask[row, col]
    return 0

health_in = 0
for el in filtered.get("elements", []): pass
for el in js_health.get("elements", []):
    if el["type"]=="node": lat, lon = el["lat"], el["lon"]
    else:
        c = el.get("center")
        if not c: continue
        lat, lon = c["lat"], c["lon"]
    health_in += int(sample_mask(flood, lon, lat, transform)>0)

shelter_in = 0
for el in filtered.get("elements", []):
    if el["type"]=="node": lat, lon = el["lat"], el["lon"]
    else:
        c = el.get("center")
        if not c: continue
        lat, lon = c["lat"], c["lon"]
    shelter_in += int(sample_mask(flood, lon, lat, transform)>0)

# area calc
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
flood_km2 = float(np.sum(flood==1)*pix_area)

st.markdown(f"### Summary")
st.write(f"- Water level: **{water_level_m:.2f} m**")
st.write(f"- Estimated flooded area: **{flood_km2:.2f} km²**")
st.write(f"- Health posts in flood: **{health_in}**")
st.write(f"- Cyclone shelters in flood: **{shelter_in}**")
