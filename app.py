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
import pandas as pd
import matplotlib

matplotlib.use("Agg")
from matplotlib import cm, colors

st.set_page_config(page_title="JolChobi — Sunamganj Flood Visualizer", layout="wide")
st.title("JolChobi 🌊 — Sunamganj Flood Visualizer")
st.caption("Live OSM overlays + fast flood modeling for responders. (Hackathon MVP)")

st.markdown(
    """
    This interactive dashboard blends live OpenStreetMap context layers with rapid flood modeling so response teams can
    explore what happens when the Surma river rises. Use the controls on the left to adjust the scenario and compare
    how assets are impacted.
    """
)

st.divider()

with st.sidebar:
    st.header("Controls")
    st.markdown(
        """
        Tune the scenario to understand how different modeling assumptions change the inundation footprint. Hover the
        ⓘ icons in the tabs for more context.
        """
    )

    method = st.selectbox("Method", ["Bathtub (fast)", "HAND (approx)"], index=0)
    st.caption("Bathtub quickly floods any pixel below the target level; HAND approximates real-world connectivity to channels.")

    st.subheader("Water level")
    preset = st.selectbox(
        "Presets (Surma gauge)",
        ["Custom","Surma: Warning +0.5 m","Surma: Warning +1.0 m","Surma: Severe +1.5 m","Surma: Extreme +2.0 m"],
        index=1
    )
    custom_level = st.slider("Custom water level above river (m)", 0.0, 6.0, 1.0, 0.1)
    st.caption("Presets follow local warning thresholds. Adjust the slider for bespoke what-if analysis.")

    st.subheader("Live layers (optional)")
    add_rain = st.checkbox("Add live radar (RainViewer tiles)")
    wms_url = st.text_input("WMS endpoint (optional)", "")
    wms_layer = st.text_input("WMS Layer name (optional)", "")
    st.caption("Add agency feeds or radar overlays to compare modeled water against observations.")

    st.subheader("Data")
    dem_path = st.text_input("DEM (GeoTIFF)", "data/dem_sunamganj.tif")
    overpass_endpoint = st.text_input("Overpass API", "https://overpass-api.de/api/interpreter")
    st.caption("DEM powers the elevation model; Overpass pulls the latest OSM roads, health facilities, and cyclone shelters.")

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
    surface_delta = np.maximum(target_level - dem, 0)
    surface_delta = np.where(np.isfinite(surface_delta), surface_delta, 0)
else:
    hand = quick_hand(dem, dem_transform)
    flood = (hand <= level).astype("uint8")
    surface_delta = np.maximum(level - hand, 0)
    surface_delta = np.where(np.isfinite(surface_delta), surface_delta, 0)

depth = np.zeros_like(surface_delta, dtype="float32")
mask = flood == 1
if np.any(mask):
    depth[mask] = surface_delta[mask]

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

# Flood overlay with depth-based gradient
max_depth = float(depth[mask].max()) if np.any(mask) else 0.0
palette_ceiling = 6.0  # align with control slider range for consistent comparisons
norm = colors.Normalize(vmin=0.0, vmax=palette_ceiling, clip=True)
normalized_depth = norm(depth)

cmap = cm.get_cmap("RdYlGn_r")  # green (shallow) → yellow → red (deep)
rgba = cmap(normalized_depth)
alpha = np.where(mask, np.clip(0.25 + 0.6 * normalized_depth, 0.0, 1.0), 0.0)
rgba[..., 3] = alpha

rgba[..., :3] = np.where(mask[..., None], rgba[..., :3], 0.0)
flood_rgba = (rgba * 255).astype("uint8")

Image.fromarray(flood_rgba, mode="RGBA").save("flood_overlay.png")
ImageOverlay(name="Inundation", image="flood_overlay.png", bounds=[[s,w],[n,e]], opacity=0.8).add_to(m)

# Live OSM layers
with st.spinner("Refreshing live OpenStreetMap layers…"):
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
map_html = m._repr_html_()

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

tab_map, tab_impacts, tab_methods = st.tabs([
    "Interactive map",
    "Exposure summary",
    "How the model works"
])

with tab_map:
    st.markdown("#### Interactive Flood Map")
    st.caption("Pan, zoom, and toggle layers to compare modeled inundation with live context feeds.")
    st.components.v1.html(map_html, height=700)
    with st.expander("Layer legend & tips", expanded=False):
        st.markdown(
            """
            - **Elevation (DEM)** — greyscale hillshade derived from the uploaded GeoTIFF.
            - **Inundation depth** — shades shift from soft green (shallow) to vivid red (deep) as the modeled water thickens.
            - **Live radar & WMS** — optional remote tiles so you can cross-check the model with observations.
            - **OSM features** — roads (dark grey), health facilities (green markers), and cyclone shelters (red markers).
            """
        )

with tab_impacts:
    st.markdown("#### Scenario Snapshot")
    metrics = st.columns(3, gap="large")
    metrics[0].metric("Flooded area", f"{flood_km2:.2f} km²")
    metrics[1].metric("Health sites at risk", int(health_in))
    metrics[2].metric("Cyclone shelters affected", int(shelter_in))

    snapshot_df = pd.DataFrame(
        [
            {"Category": "Health facilities", "Assets in flood": int(health_in)},
            {"Category": "Cyclone shelters", "Assets in flood": int(shelter_in)}
        ]
    )
    if snapshot_df["Assets in flood"].sum() > 0:
        st.bar_chart(snapshot_df.set_index("Category"))
    else:
        st.info("No mapped health facilities or cyclone shelters intersect the flooded area for this scenario.")

    st.markdown(
        f"""
        **Method**: `{method}` · **Preset**: `{preset}` · **Extra water above river**: `{level:.2f} m`

        The river base elevation is approximated from the 15th percentile of the DEM (≈ {river_elev:.2f} m). Pixels are
        flagged as inundated when they fall below the target water surface of {target_level:.2f} m. Colors transition from
        soft green through amber into red as depth increases (scaled on a 0-6 m palette), with red zones representing the
        deepest water (≈ {max_depth:.2f} m).
        """
    )

with tab_methods:
    st.markdown("#### Modeling Cheatsheet")
    st.markdown(
        """
        **Bathtub (fast)**
        : Fills every cell below the target level. Great for quick situational awareness.

        **HAND (approx)**
        : Uses a Height Above Nearest Drainage surface (approximated here with a fast distance-to-river proxy) to keep the
        flood connected to channels. Useful when you need to avoid isolated pits.

        **OSM live layers**
        : Each rerun fetches the latest features from Overpass so classifications and names stay fresh.

        **Custom overlays**
        : Add a WMS endpoint (e.g., national flood forecasts) or the RainViewer radar tiles to validate the extent visually.
        """
    )
    st.markdown(
        """
        The export button on the left packages the inundation mask as a GeoTIFF (aligned to your DEM) plus the RGBA PNG for
        briefing decks. Use these downloads to bring the scenario into QGIS or to share quick situational updates.
        """
    )

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
