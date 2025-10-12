"""
JolChobi 🌊 — Sunamganj Flood Visualizer (Improved Version)
Interactive flood modeling dashboard with live data integration.
"""
import os
import io
import json
import math
from datetime import datetime
from typing import Optional, Tuple

import numpy as np
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
import folium
from folium.raster_layers import ImageOverlay, WmsTileLayer, TileLayer
from folium.plugins import MousePosition, MiniMap, Fullscreen
import rasterio
from rasterio.io import MemoryFile
from pyproj import Transformer
from PIL import Image

# Import custom modules
from io_sources import (
    osm_points, osm_roads, fetch_weekly_forecast,
    fetch_hourly_precipitation, fetch_hydrology_forecast
)
from model import (
    estimate_river_base_elevation, quick_hand, bathtub_flood,
    hand_flood, calculate_flood_area_km2
)
from exposure import (
    calculate_flooded_roads_km, calculate_point_exposure
)
from forecast import (
    summarize_forecast, summarize_precip, summarize_hydrology,
    build_waterlevel_recommendation, request_llm_guidance
)
from render import (
    create_dem_overlay, create_flood_overlay, build_folium_map,
    add_legend, add_osm_layers
)

# Page config
st.set_page_config(
    page_title="JolChobi — Sunamganj Flood Visualizer",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.title("JolChobi 🌊 — Sunamganj Flood Visualizer")
st.caption("Live OSM overlays + fast flood modeling for responders. (Enhanced MVP)")

st.markdown(
    """
    This interactive dashboard blends live OpenStreetMap context layers with rapid flood modeling so response teams can
    explore what happens when the Surma river rises. Use the controls on the left to adjust the scenario and compare
    how assets are impacted.
    """
)

st.divider()

# Initialize session state
if "forecast_summary" not in st.session_state:
    st.session_state["forecast_summary"] = None
if "forecast_error" not in st.session_state:
    st.session_state["forecast_error"] = ""
if "forecast_requested" not in st.session_state:
    st.session_state["forecast_requested"] = False
if "forecast_inflight" not in st.session_state:
    st.session_state["forecast_inflight"] = False
if "hydrology_summary" not in st.session_state:
    st.session_state["hydrology_summary"] = None
if "precip_summary" not in st.session_state:
    st.session_state["precip_summary"] = None
if "llm_recommendation" not in st.session_state:
    st.session_state["llm_recommendation"] = None
if "llm_error" not in st.session_state:
    st.session_state["llm_error"] = ""
if "hydrology_error" not in st.session_state:
    st.session_state["hydrology_error"] = ""
if "precip_error" not in st.session_state:
    st.session_state["precip_error"] = ""
if "waterlevel_recommendation" not in st.session_state:
    st.session_state["waterlevel_recommendation"] = None
if "llm_inflight" not in st.session_state:
    st.session_state["llm_inflight"] = False
if "latest_target_level" not in st.session_state:
    st.session_state["latest_target_level"] = 1.0

# Sidebar controls
with st.sidebar:
    st.header("Controls")
    st.markdown(
        """
        Tune the scenario to understand how different modeling assumptions change the inundation footprint. Hover the
        ⓘ icons in the tabs for more context.
        """
    )

    # DEM upload or path
    st.subheader("Data source")
    use_upload = st.checkbox("Upload custom DEM", value=False)
    
    uploaded_dem = None
    dem_path = None
    
    if use_upload:
        uploaded_dem = st.file_uploader(
            "Upload DEM (GeoTIFF)",
            type=["tif", "tiff"],
            help="Upload a GeoTIFF with elevation data"
        )
    else:
        dem_path = st.text_input("DEM (GeoTIFF)", "data/dem_sunamganj.tif")
    
    overpass_endpoint = st.text_input("Overpass API", "https://overpass-api.de/api/interpreter")
    st.caption("DEM powers the elevation model; Overpass pulls the latest OSM roads, health facilities, and cyclone shelters.")

    # Modeling method
    st.subheader("Modeling")
    method = st.selectbox("Method", ["Bathtub (fast)", "HAND (approx)"], index=0)
    st.caption("Bathtub quickly floods any pixel below the target level; HAND approximates real-world connectivity to channels.")

    # Water level
    st.subheader("Water level")
    preset = st.selectbox(
        "Presets (Surma gauge)",
        ["Custom", "Surma: Warning +0.5 m", "Surma: Warning +1.0 m", "Surma: Severe +1.5 m", "Surma: Extreme +2.0 m"],
        index=1,
        key="preset_select"
    )
    custom_level = st.slider("Custom water level above river (m)", 0.0, 6.0, 1.0, 0.1, key="custom_level_slider")
    st.caption("Presets follow local warning thresholds. Adjust the slider for bespoke what-if analysis.")

    # Visualization
    st.subheader("Visualization")
    basemap = st.selectbox(
        "Basemap",
        ["OpenStreetMap", "CartoDB Positron", "CartoDB Dark Matter", "Stamen Terrain", "Stamen Toner"],
        index=0
    )
    dem_opacity = st.slider("DEM opacity", 0.0, 1.0, 0.5, 0.05)
    flood_opacity = st.slider("Flood opacity", 0.0, 1.0, 0.8, 0.05)
    colormap = st.selectbox("Flood colormap", ["blue_gradient", "red_gradient", "viridis"], index=0)

    # Live layers
    st.subheader("Live layers (optional)")
    add_rain = st.checkbox("Add live radar (RainViewer tiles)")
    wms_url = st.text_input("WMS endpoint (optional)", "")
    wms_layer = st.text_input("WMS Layer name (optional)", "")
    st.caption("Add agency feeds or radar overlays to compare modeled water against observations.")

    # Export
    st.subheader("Export")
    export_format = st.radio("Export format", ["In-memory download", "Save to disk"], index=0)
    export_cog = st.checkbox("Export as Cloud Optimized GeoTIFF (COG)", value=True)
    export_metadata = st.checkbox("Include metadata JSON", value=True)
    export_btn = st.button("Export GeoTIFF + PNG", use_container_width=True)

    # Forecast assist
    st.subheader("Forecast assist")
    st.caption("Pull the latest rainfall, river discharge, and optional GPT narrative to tune next-week water levels.")
    
    if st.button("Fetch 7-day outlook", use_container_width=True, key="fetch_forecast"):
        st.session_state["forecast_requested"] = True
        st.session_state["forecast_error"] = ""
        st.session_state["hydrology_error"] = ""
        st.session_state["precip_error"] = ""

    # LLM integration
    try:
        default_api_key = st.secrets.get("OPENAI_API_KEY", "")
    except (FileNotFoundError, KeyError):
        default_api_key = ""
    
    llm_api_key = st.text_input(
        "LLM API key (OpenAI, optional)",
        value=default_api_key,
        type="password",
        key="llm_api_key_input",
        help="Stored only for this session. Provide if you want a GPT-based narrative for the scenario.",
    )
    llm_model = st.selectbox(
        "LLM model",
        ["gpt-4o-mini", "gpt-4-turbo", "gpt-4o"],
        index=0,
        key="llm_model_select",
    )
    
    if st.button("Ask LLM for scenario note", use_container_width=True, key="call_llm"):
        recommendation = st.session_state.get("waterlevel_recommendation")
        if not recommendation:
            st.warning("Fetch forecast data first so the LLM has quantitative context.")
        elif not llm_api_key:
            st.warning("Add an API key before requesting guidance.")
        else:
            st.session_state["llm_inflight"] = True
            st.session_state["llm_error"] = ""
            try:
                level = st.session_state.get("latest_target_level")
                if isinstance(level, (int, float)) and not math.isnan(level):
                    target_val = float(level)
                else:
                    target_val = float(recommendation["suggested_extra"])
                message = request_llm_guidance(
                    api_key=llm_api_key,
                    model=llm_model,
                    recommendation=recommendation,
                    forecast_summary=st.session_state.get("forecast_summary"),
                    hydrology_summary=st.session_state.get("hydrology_summary"),
                    precip_summary=st.session_state.get("precip_summary"),
                    target_level=target_val,
                )
                st.session_state["llm_recommendation"] = message
            except Exception as exc:
                st.session_state["llm_error"] = str(exc)
                st.session_state["llm_recommendation"] = None
            finally:
                st.session_state["llm_inflight"] = False

# Load DEM
dem = None
dem_bounds = None
dem_crs = None
dem_transform = None
dem_profile = None

if use_upload and uploaded_dem:
    # Load from uploaded file
    with MemoryFile(uploaded_dem.read()) as memfile:
        with memfile.open() as src:
            dem = src.read(1).astype("float32")
            nodata = src.nodata
            if nodata is not None:
                dem = np.where(dem == nodata, np.nan, dem)
            dem = np.where(dem < -1000, np.nan, dem)
            dem_bounds = src.bounds
            dem_crs = src.crs
            dem_transform = src.transform
            dem_profile = src.profile
elif dem_path and os.path.exists(dem_path):
    with rasterio.open(dem_path) as src:
        dem = src.read(1).astype("float32")
        nodata = src.nodata
        if nodata is not None:
            dem = np.where(dem == nodata, np.nan, dem)
        dem = np.where(dem < -1000, np.nan, dem)
        dem_bounds = src.bounds
        dem_crs = src.crs
        dem_transform = src.transform
        dem_profile = src.profile
else:
    st.error("DEM not found. Put a GeoTIFF at data/dem_sunamganj.tif, update the path, or upload a file.")
    st.stop()

if dem_crs is None:
    st.error("DEM has no CRS information. Please provide a properly georeferenced GeoTIFF.")
    st.stop()

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
center_lat, center_lon = (s + n) / 2, (w + e) / 2

# Determine water level
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

# Calculate river base elevation
river_elev = estimate_river_base_elevation(dem, percentile=5.0)
target_level = river_elev + level
st.session_state["latest_target_level"] = float(target_level)

# Run flood model
if method.startswith("Bathtub"):
    flood, depth = bathtub_flood(dem, target_level)
else:
    hand = quick_hand(dem, dem_transform, dem_crs)
    flood, depth = hand_flood(dem, hand, level)

# Calculate flood area
lat_mid = (s + n) / 2
flood_km2 = calculate_flood_area_km2(flood, dem_transform, dem_crs, lat_mid)

# Fetch forecast data if requested
if st.session_state.get("forecast_requested") and not st.session_state.get("forecast_inflight"):
    try:
        st.session_state["forecast_inflight"] = True
        try:
            raw_forecast = fetch_weekly_forecast(center_lat, center_lon)
            st.session_state["forecast_summary"] = summarize_forecast(raw_forecast)
            st.session_state["forecast_error"] = ""
        except Exception as exc:
            st.session_state["forecast_summary"] = None
            st.session_state["forecast_error"] = str(exc)

        try:
            raw_precip = fetch_hourly_precipitation(center_lat, center_lon)
            st.session_state["precip_summary"] = summarize_precip(raw_precip)
            st.session_state["precip_error"] = ""
        except Exception as exc:
            st.session_state["precip_summary"] = None
            st.session_state["precip_error"] = str(exc)

        try:
            raw_hydrology = fetch_hydrology_forecast(center_lat, center_lon)
            st.session_state["hydrology_summary"] = summarize_hydrology(raw_hydrology)
            st.session_state["hydrology_error"] = ""
        except Exception as exc:
            st.session_state["hydrology_summary"] = None
            st.session_state["hydrology_error"] = str(exc)
    finally:
        st.session_state["waterlevel_recommendation"] = build_waterlevel_recommendation(
            st.session_state.get("forecast_summary"),
            st.session_state.get("hydrology_summary"),
            st.session_state.get("precip_summary"),
        )
        st.session_state["forecast_requested"] = False
        st.session_state["forecast_inflight"] = False

# Fetch OSM layers with spinner
with st.spinner("Refreshing live OpenStreetMap layers…"):
    try:
        roads = osm_roads(overpass_endpoint, sunam_bbox)
        health = osm_points(overpass_endpoint, sunam_bbox, what="health")
        shelters = osm_points(overpass_endpoint, sunam_bbox, what="cyclone_shelter")
    except Exception as e:
        st.warning(f"OSM data fetch failed: {str(e)}. Using empty layers.")
        import geopandas as gpd
        roads = gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")
        health = gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")
        shelters = gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")

# Calculate exposure metrics
flooded_roads_km, roads_by_type = calculate_flooded_roads_km(roads, flood, dem_transform, dem_crs)
health_in = calculate_point_exposure(health, flood, dem_transform, dem_crs)
shelter_in = calculate_point_exposure(shelters, flood, dem_transform, dem_crs)

# Build map
m = build_folium_map(center_lat, center_lon, zoom=9, basemap=basemap)

# Add live radar
if add_rain:
    TileLayer(
        tiles="https://tilecache.rainviewer.com/v2/radar/last/256/{z}/{x}/{y}/2/1_1.png",
        attr="RainViewer",
        name="Live Radar",
        overlay=True,
        control=True,
        opacity=0.6
    ).add_to(m)

# Add WMS
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

# Add DEM overlay
dem_data_url = create_dem_overlay(dem, [[s, w], [n, e]], opacity=dem_opacity)
ImageOverlay(
    name="Elevation (DEM)",
    image=dem_data_url,
    bounds=[[s, w], [n, e]],
    opacity=1.0  # Opacity already baked into image
).add_to(m)

# Add flood overlay
flood_data_url, max_depth = create_flood_overlay(
    flood, depth, [[s, w], [n, e]],
    opacity=flood_opacity,
    colormap=colormap
)
ImageOverlay(
    name="Inundation",
    image=flood_data_url,
    bounds=[[s, w], [n, e]],
    opacity=1.0  # Opacity already baked into image
).add_to(m)

# Add legend
add_legend(m, max_depth, colormap=colormap)

# Add OSM layers
add_osm_layers(m, roads, health, shelters)

# Add controls
MousePosition().add_to(m)
folium.LayerControl(collapsed=False).add_to(m)

# Get map HTML
map_html = m._repr_html_()

# Sidebar forecast insight
with st.sidebar:
    st.subheader("Forecast insight")
    if st.session_state.get("forecast_inflight"):
        st.info("Fetching forecast outlook…")
    elif st.session_state.get("forecast_error"):
        st.warning(f"Forecast unavailable: {st.session_state['forecast_error']}")
    elif any([st.session_state.get("forecast_summary"), st.session_state.get("hydrology_summary"), st.session_state.get("precip_summary")]):
        recommendation = st.session_state.get("waterlevel_recommendation")
        if recommendation:
            st.metric(
                "Recommended extra water level",
                f"{recommendation['suggested_extra']:.2f} m",
                help="Combined from rainfall, winds, hourly rain bursts, and river discharge outlook.",
            )
            drivers = "\n".join(
                f"- {comp['label']}: {comp['value']:+.2f} m ({comp['context']})"
                for comp in recommendation["components"]
                if abs(comp["value"]) >= 0.05
            )
            if drivers:
                st.markdown(drivers)
            if st.button("Apply recommended level", use_container_width=True, key="apply_forecast"):
                st.session_state["custom_level_slider"] = float(
                    np.clip(recommendation["suggested_extra"], 0.0, 6.0)
                )
                st.session_state["preset_select"] = "Custom"
                st.success("Recommendation applied to custom level.")
                st.rerun()

        forecast_summary = st.session_state.get("forecast_summary")
        precip_summary = st.session_state.get("precip_summary")
        hydrology_summary = st.session_state.get("hydrology_summary")
        
        if forecast_summary:
            st.caption(
                f"7-day totals: {forecast_summary['total_rain']:.0f} mm rain · "
                f"peak wind {forecast_summary['peak_wind']:.0f} km/h · "
                f"average max temp {forecast_summary['mean_temp']:.1f} °C."
            )
        if precip_summary and not st.session_state.get("precip_error"):
            st.caption(
                f"Next 24h rain {precip_summary['next_day_total']:.1f} mm · "
                f"Peak hourly burst {precip_summary['peak_hour']:.2f} mm."
            )
        if hydrology_summary and not st.session_state.get("hydrology_error"):
            st.caption(
                f"River discharge now {hydrology_summary['current_discharge']:.1f} m³/s, "
                f"peaking near {hydrology_summary['peak_discharge']:.1f} m³/s (Δ {hydrology_summary['trend_delta']:+.2f})."
            )
        if st.session_state.get("hydrology_error"):
            st.warning(f"Hydrology feed issue: {st.session_state['hydrology_error']}")
        if st.session_state.get("precip_error"):
            st.warning(f"Hourly rain feed issue: {st.session_state['precip_error']}")
        if st.session_state.get("llm_inflight"):
            st.info("Generating LLM scenario note…")
        elif st.session_state.get("llm_error"):
            st.warning(f"LLM guidance failed: {st.session_state['llm_error']}")
        elif st.session_state.get("llm_recommendation"):
            st.success("LLM scenario note ready in the outlook tab.")

# Main tabs
tab_map, tab_impacts, tab_forecast, tab_methods = st.tabs([
    "Interactive map",
    "Exposure summary",
    "Next-week outlook",
    "How the model works"
])

with tab_map:
    st.markdown("#### Interactive Flood Map")
    st.caption("Pan, zoom, and toggle layers to compare modeled inundation with live context feeds.")
    components.html(map_html, height=700)
    with st.expander("Layer legend & tips", expanded=False):
        st.markdown(
            """
            - **Elevation (DEM)** — greyscale hillshade derived from the uploaded GeoTIFF.
            - **Inundation depth** — color gradient shows flood depth (see legend on map).
            - **Live radar & WMS** — optional remote tiles so you can cross-check the model with observations.
            - **OSM features** — roads (dark grey), health facilities (green markers), and cyclone shelters (red markers).
            """
        )

with tab_impacts:
    st.markdown("#### Scenario Snapshot")
    metrics = st.columns(4, gap="large")
    metrics[0].metric("Flooded area", f"{flood_km2:.2f} km²")
    metrics[1].metric("Flooded roads", f"{flooded_roads_km:.1f} km")
    metrics[2].metric("Health sites at risk", int(health_in))
    metrics[3].metric("Cyclone shelters affected", int(shelter_in))

    # Roads by type
    if roads_by_type:
        st.markdown("##### Flooded roads by type")
        roads_df = pd.DataFrame([
            {"Road Type": k, "Length (km)": f"{v:.1f}"}
            for k, v in sorted(roads_by_type.items(), key=lambda x: x[1], reverse=True)
        ])
        st.dataframe(roads_df, use_container_width=True)

    snapshot_df = pd.DataFrame(
        [
            {"Category": "Roads (km)", "Assets in flood": f"{flooded_roads_km:.1f}"},
            {"Category": "Health facilities", "Assets in flood": int(health_in)},
            {"Category": "Cyclone shelters", "Assets in flood": int(shelter_in)}
        ]
    )
    
    st.markdown(
        f"""
        **Method**: `{method}` · **Preset**: `{preset}` · **Extra water above river**: `{level:.2f} m`

        The river base elevation is approximated from the average of the lowest 5% of DEM cells (≈ {river_elev:.2f} m). Pixels are
        flagged as inundated when they fall below the target water surface of {target_level:.2f} m. Colors transition based on depth,
        with the deepest water in this scenario reaching ≈ {max_depth:.2f} m.
        """
        + (
            "\n\n"
            + "Combined outlook recommends +"
            + f"{st.session_state.get('waterlevel_recommendation', {}).get('suggested_extra', 0):.2f} m based on rainfall, hourly bursts, and river discharge."
            if st.session_state.get("waterlevel_recommendation")
            else ""
        )
    )

with tab_forecast:
    st.markdown("#### 7-day meteorological outlook")
    forecast_summary = st.session_state.get("forecast_summary")
    if forecast_summary:
        df = forecast_summary["dataframe"]
        st.dataframe(df, use_container_width=True)
        rain_chart = df.set_index("Date")["Rain (mm)"]
        if rain_chart.sum() > 0:
            st.bar_chart(rain_chart, height=200)
        narrative = (
            f"Total rain **{forecast_summary['total_rain']:.0f} mm**, peak wind **{forecast_summary['peak_wind']:.0f} km/h**, "
            f"mean max temp **{forecast_summary['mean_temp']:.1f} °C**."
        )
        recommendation = st.session_state.get("waterlevel_recommendation")
        if recommendation:
            narrative += (
                f" Combined driver score recommends **+{recommendation['suggested_extra']:.2f} m** at the gauge."
            )
        st.markdown(narrative)
        st.caption("Source: Open-Meteo API (refreshed hourly; cached locally for one hour).")
    elif st.session_state.get("forecast_error"):
        st.warning("Forecast data not available yet. Try fetching the 7-day outlook from the sidebar.")
    else:
        st.info("Fetch the 7-day outlook from the sidebar to populate this tab with rainfall and wind projections.")

    precip_summary = st.session_state.get("precip_summary")
    if precip_summary:
        st.markdown("#### Hourly precipitation (last 48h → next 72h)")
        precip_cols = st.columns(3)
        precip_cols[0].metric("Last 48h", f"{precip_summary['recent_total']:.1f} mm")
        precip_cols[1].metric("Next 24h", f"{precip_summary['next_day_total']:.1f} mm")
        precip_cols[2].metric("Peak hourly", f"{precip_summary['peak_hour']:.2f} mm/h")
        precip_df = precip_summary["dataframe"].set_index("Local Timestamp").sort_index()
        st.area_chart(precip_df["Precipitation (mm)"], height=220)
        st.caption("Source: Open-Meteo hourly precipitation (UTC timestamps shown).")
    elif st.session_state.get("precip_error"):
        st.warning(f"Hourly precipitation timeline unavailable: {st.session_state['precip_error']}")

    hydrology_summary = st.session_state.get("hydrology_summary")
    if hydrology_summary:
        st.markdown("#### River discharge outlook (GloFAS)")
        hydro_cols = st.columns(3)
        hydro_cols[0].metric("Today", f"{hydrology_summary['current_discharge']:.1f} m³/s")
        hydro_cols[1].metric("Peak (10-day)", f"{hydrology_summary['peak_discharge']:.1f} m³/s")
        hydro_cols[2].metric("7-day trend", f"{hydrology_summary['trend_delta']:+.2f} m³/s")
        hydro_df = hydrology_summary["dataframe"].set_index("Date").sort_index()
        available_cols = [
            col for col in ["Discharge (m³/s)", "Discharge max (m³/s)", "Discharge min (m³/s)"]
            if col in hydro_df.columns and hydro_df[col].notna().any()
        ]
        if available_cols:
            st.line_chart(hydro_df[available_cols], height=240)
        st.caption("Source: Open-Meteo Flood API (driven by Copernicus GloFAS hydrological model).")
    elif st.session_state.get("hydrology_error"):
        st.warning(f"River discharge forecast unavailable: {st.session_state['hydrology_error']}")

    llm_recommendation = st.session_state.get("llm_recommendation")
    if llm_recommendation:
        st.markdown("#### LLM scenario brief")
        st.info(llm_recommendation)
    elif st.session_state.get("llm_error"):
        st.warning(f"LLM scenario note unavailable: {st.session_state['llm_error']}")
    elif st.session_state.get("llm_inflight"):
        st.info("LLM scenario note is being generated…")

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
        : Each rerun fetches the latest features from Overpass so classifications and names stay fresh. Results are cached for 1 hour.

        **Custom overlays**
        : Add a WMS endpoint (e.g., national flood forecasts) or the RainViewer radar tiles to validate the extent visually.

        **Hydrology feed**
        : River discharge scenarios come from the Open-Meteo Flood API (Copernicus GloFAS), highlighting rises that warrant extra depth.

        **LLM narrative (optional)**
        : Provide an OpenAI API key in the sidebar to generate a short GPT-based briefing that ties the numbers together.
        
        **Improvements in this version**
        : ✅ Cached OSM layers with retry logic
        : ✅ In-memory downloads (no disk clutter)
        : ✅ Basemap and opacity controls
        : ✅ DEM file upload support
        : ✅ Improved area calculations
        : ✅ Spatial join exposure analytics
        : ✅ Road type breakdown
        : ✅ Modular code structure
        : ✅ COG export option
        """
    )

# Export functionality
if export_btn:
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    
    # Prepare metadata
    metadata = {
        "generated_at": datetime.utcnow().isoformat(),
        "method": method,
        "preset": preset,
        "water_level_above_river_m": float(level),
        "river_base_elevation_m": float(river_elev),
        "target_water_level_m": float(target_level),
        "flooded_area_km2": float(flood_km2),
        "flooded_roads_km": float(flooded_roads_km),
        "health_facilities_exposed": int(health_in),
        "cyclone_shelters_exposed": int(shelter_in),
        "max_depth_m": float(max_depth),
        "crs": str(dem_crs),
        "bounds": {
            "west": float(w),
            "south": float(s),
            "east": float(e),
            "north": float(n)
        }
    }
    
    if export_format == "In-memory download":
        # GeoTIFF
        profile = dem_profile.copy()
        profile.update(dtype=rasterio.uint8, count=1, nodata=0, compress="lzw")
        
        if export_cog:
            profile.update(
                tiled=True,
                blockxsize=256,
                blockysize=256,
                compress="deflate"
            )
        
        tif_buffer = io.BytesIO()
        with MemoryFile() as memfile:
            with memfile.open(**profile) as dst:
                dst.write(flood.astype("uint8"), 1)
                dst.update_tags(**{k: str(v) for k, v in metadata.items()})
            tif_buffer.write(memfile.read())
        
        tif_buffer.seek(0)
        
        # PNG
        flood_rgba = (create_flood_overlay(flood, depth, [[s, w], [n, e]], opacity=1.0, colormap=colormap)[0])
        # Extract base64 and convert back to bytes
        png_buffer = io.BytesIO()
        img = Image.fromarray((depth > 0).astype(np.uint8) * 255, mode='L')
        img.save(png_buffer, format='PNG')
        png_buffer.seek(0)
        
        # Download buttons
        col1, col2 = st.columns(2)
        with col1:
            st.download_button(
                label="📥 Download GeoTIFF",
                data=tif_buffer,
                file_name=f"jolchobi_flood_{timestamp}.tif",
                mime="image/tiff"
            )
        with col2:
            st.download_button(
                label="📥 Download PNG",
                data=png_buffer,
                file_name=f"jolchobi_map_{timestamp}.png",
                mime="image/png"
            )
        
        if export_metadata:
            json_buffer = io.BytesIO(json.dumps(metadata, indent=2).encode())
            st.download_button(
                label="📥 Download Metadata JSON",
                data=json_buffer,
                file_name=f"jolchobi_metadata_{timestamp}.json",
                mime="application/json"
            )
        
        st.success("✅ Export ready for download!")
    
    else:
        # Save to disk
        out_tif = f"jolchobi_flood_{timestamp}.tif"
        out_png = f"jolchobi_map_{timestamp}.png"
        out_json = f"jolchobi_metadata_{timestamp}.json"
        
        profile = dem_profile.copy()
        profile.update(dtype=rasterio.uint8, count=1, nodata=0, compress="lzw")
        
        if export_cog:
            profile.update(
                tiled=True,
                blockxsize=256,
                blockysize=256,
                compress="deflate"
            )
        
        with rasterio.open(out_tif, "w", **profile) as dst:
            dst.write(flood.astype("uint8"), 1)
            dst.update_tags(**{k: str(v) for k, v in metadata.items()})
        
        # Save PNG (simple binary mask for now)
        img = Image.fromarray((flood == 1).astype(np.uint8) * 255, mode='L')
        img.save(out_png)
        
        if export_metadata:
            with open(out_json, 'w') as f:
                json.dump(metadata, f, indent=2)
        
        st.success(f"✅ Exports saved to disk!")
        st.markdown(f"- **GeoTIFF**: `{out_tif}`")
        st.markdown(f"- **PNG**: `{out_png}`")
        if export_metadata:
            st.markdown(f"- **Metadata**: `{out_json}`")
