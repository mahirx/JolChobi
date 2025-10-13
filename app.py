import os, io, json, requests, math, textwrap, numpy as np
import streamlit as st
import folium
from folium.raster_layers import ImageOverlay, WmsTileLayer, TileLayer
from folium.plugins import MousePosition, MiniMap, Fullscreen
import rasterio
from rasterio import features
from rasterio.warp import transform_bounds
import geopandas as gpd
from shapely.geometry import shape, mapping, Point, Polygon
from shapely.ops import unary_union
from PIL import Image
from pyproj import Transformer, Proj
import pandas as pd
from datetime import datetime
import matplotlib
from branca.colormap import LinearColormap

matplotlib.use("Agg")
from matplotlib import colors

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
        index=1,
        key="preset_select"
    )
    custom_level = st.slider("Custom water level above river (m)", 0.0, 6.0, 1.0, 0.1, key="custom_level_slider")
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

    st.subheader("Forecast assist")
    st.caption("Pull the latest rainfall, river discharge, and optional GPT narrative to tune next-week water levels.")
    if st.button("Fetch 7-day outlook", use_container_width=True, key="fetch_forecast"):
        st.session_state["forecast_requested"] = True
        st.session_state["forecast_error"] = ""
        st.session_state["hydrology_error"] = ""
        st.session_state["precip_error"] = ""

    llm_api_key = st.text_input(
        "LLM API key (OpenAI, optional)",
        value="",
        type="password",
        key="llm_api_key_input",
        help="Stored only for this session. Provide if you want a GPT-based narrative for the scenario.",
    )
    llm_model = st.selectbox(
        "LLM model",
        ["gpt-4o-mini", "gpt-4.1-mini", "gpt-4o"],
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

def calculate_flooded_roads_km(roads_gdf, flood_mask, dem_transform, dem_crs):
    """Calculates the approximate length of flooded roads."""
    if roads_gdf.empty:
        return 0.0

    # Project roads to the DEM's CRS for accurate intersection
    roads_proj = roads_gdf.to_crs(dem_crs)

    # Create a polygon of the flooded area
    shapes = features.shapes(flood_mask, mask=(flood_mask == 1), transform=dem_transform)
    flood_polygons = [shape(geom) for geom, val in shapes if val == 1]
    if not flood_polygons:
        return 0.0
    
    flood_geom = unary_union(flood_polygons)

    # Find intersection and calculate length
    flooded_roads_geom = roads_proj.geometry.intersection(flood_geom)
    flooded_roads_gdf = gpd.GeoDataFrame(geometry=flooded_roads_geom, crs=dem_crs)
    
    # Length is in meters, convert to km
    return flooded_roads_gdf.length.sum() / 1000.0

@st.cache_data(show_spinner=False, ttl=3600)
def fetch_weekly_forecast(lat: float, lon: float) -> dict:
    """Fetch 7-day forecast from the Open-Meteo API."""
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat,
        "longitude": lon,
        "daily": ",".join([
            "precipitation_sum",
            "windspeed_10m_max",
            "temperature_2m_max"
        ]),
        "timezone": "UTC",
        "forecast_days": 7
    }
    response = requests.get(url, params=params, timeout=20)
    response.raise_for_status()
    return response.json()


@st.cache_data(show_spinner=False, ttl=1800)
def fetch_hourly_precipitation(lat: float, lon: float) -> dict:
    """Retrieve the last 48h + next 72h hourly precipitation totals."""
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": "precipitation,rain",
        "past_days": 2,
        "forecast_days": 3,
        "timezone": "UTC"
    }
    response = requests.get(url, params=params, timeout=20)
    response.raise_for_status()
    return response.json()


@st.cache_data(show_spinner=False, ttl=3600)
def fetch_hydrology_forecast(lat: float, lon: float) -> dict:
    """Pull daily river discharge projections from the Open-Meteo Flood API."""
    url = "https://flood-api.open-meteo.com/v1/flood"
    params = {
        "latitude": lat,
        "longitude": lon,
        "daily": "river_discharge,river_discharge_min,river_discharge_max,river_discharge_mean",
        "past_days": 3,
        "forecast_days": 10,
        "timezone": "UTC"
    }
    response = requests.get(url, params=params, timeout=20)
    response.raise_for_status()
    return response.json()


def summarize_forecast(forecast: dict) -> dict:
    daily = forecast.get("daily", {})
    dates = daily.get("time", [])
    rain = daily.get("precipitation_sum", [])
    wind = daily.get("windspeed_10m_max", [])
    temp = daily.get("temperature_2m_max", [])
    if not dates:
        raise ValueError("Forecast did not include daily outlook data")

    df = pd.DataFrame(
        {
            "Date": pd.to_datetime(dates),
            "Rain (mm)": rain,
            "Wind max (km/h)": wind,
            "Temp max (°C)": temp
        }
    )
    df["Date"] = df["Date"].dt.strftime("%a %d %b")

    rain_vals = pd.to_numeric(df["Rain (mm)"], errors="coerce").to_numpy(dtype="float32")
    wind_vals = pd.to_numeric(df["Wind max (km/h)"], errors="coerce").to_numpy(dtype="float32")
    temp_vals = pd.to_numeric(df["Temp max (°C)"], errors="coerce").to_numpy(dtype="float32")

    valid_rain = rain_vals[np.isfinite(rain_vals)]
    valid_wind = wind_vals[np.isfinite(wind_vals)]
    valid_temp = temp_vals[np.isfinite(temp_vals)]

    total_rain = float(valid_rain.sum()) if valid_rain.size else 0.0
    peak_wind = float(valid_wind.max()) if valid_wind.size else 0.0
    mean_temp = float(valid_temp.mean()) if valid_temp.size else 0.0

    suggested_extra = float(np.clip(total_rain / 200.0 + peak_wind / 150.0, 0.0, 6.0))

    return {
        "dataframe": df,
        "total_rain": total_rain,
        "peak_wind": peak_wind,
        "mean_temp": mean_temp,
        "suggested_extra": round(suggested_extra, 2),
        "issued_at": datetime.utcnow()
    }


def summarize_precip(hourly: dict) -> dict:
    data = hourly.get("hourly", {})
    times = pd.to_datetime(data.get("time", []))
    precip = pd.to_numeric(data.get("precipitation", []), errors="coerce")
    if times.empty:
        raise ValueError("Hourly precipitation feed returned no timestamps")

    df = pd.DataFrame({"Timestamp": times, "Precipitation (mm)": precip})
    df["Local Timestamp"] = df["Timestamp"].dt.tz_localize("UTC")

    cutoff_recent = datetime.utcnow() - pd.Timedelta(hours=48)
    recent = df[df["Timestamp"] >= cutoff_recent]
    upcoming = df[df["Timestamp"] > datetime.utcnow()]

    recent_total = float(recent["Precipitation (mm)"].sum())
    next_day = float(
        upcoming[upcoming["Timestamp"] <= datetime.utcnow() + pd.Timedelta(hours=24)]["Precipitation (mm)"].sum()
    )

    peak_hour = float(upcoming["Precipitation (mm)"].max()) if not upcoming.empty else 0.0

    return {
        "dataframe": df,
        "recent_total": round(recent_total, 1),
        "next_day_total": round(next_day, 1),
        "peak_hour": round(peak_hour, 2),
    }


def summarize_hydrology(hydrology: dict) -> dict:
    daily = hydrology.get("daily", {})
    dates = pd.to_datetime(daily.get("time", []))
    if dates.empty:
        raise ValueError("Flood API returned no discharge timeline")

    discharge = pd.to_numeric(daily.get("river_discharge", []), errors="coerce")
    discharge_min = pd.to_numeric(daily.get("river_discharge_min", []), errors="coerce")
    discharge_max = pd.to_numeric(daily.get("river_discharge_max", []), errors="coerce")
    discharge_mean = pd.to_numeric(daily.get("river_discharge_mean", []), errors="coerce")

    df = pd.DataFrame(
        {
            "Date": dates,
            "Discharge (m³/s)": discharge,
            "Discharge min (m³/s)": discharge_min,
            "Discharge max (m³/s)": discharge_max,
            "Discharge mean (m³/s)": discharge_mean,
        }
    ).dropna(subset=["Date"])
    df["Date"] = df["Date"].dt.tz_localize("UTC")

    current_discharge = float(df.iloc[0]["Discharge (m³/s)"]) if not df.empty else 0.0
    top_forecast = float(df["Discharge max (m³/s)"].iloc[:10].max()) if not df.empty else 0.0

    trend_window = df.iloc[:7]
    trend_delta = 0.0
    if len(trend_window) >= 2:
        trend_delta = float(trend_window["Discharge mean (m³/s)"].iloc[-1] - trend_window["Discharge mean (m³/s)"].iloc[0])

    return {
        "dataframe": df,
        "current_discharge": round(current_discharge, 2),
        "peak_discharge": round(top_forecast, 2),
        "trend_delta": round(trend_delta, 2),
    }


def build_waterlevel_recommendation(
    forecast_summary: dict | None,
    hydrology_summary: dict | None,
    precip_summary: dict | None,
) -> dict | None:
    if not any([forecast_summary, hydrology_summary, precip_summary]):
        return None

    components = []
    total = 0.0

    if forecast_summary:
        rain_factor = forecast_summary["total_rain"] / 180.0
        wind_factor = forecast_summary["peak_wind"] / 200.0
        total += rain_factor + wind_factor
        components.append(
            {
                "label": "7-day rainfall",
                "value": round(rain_factor, 2),
                "context": f"{forecast_summary['total_rain']:.0f} mm total rain",
            }
        )
        components.append(
            {
                "label": "Peak wind",
                "value": round(wind_factor, 2),
                "context": f"{forecast_summary['peak_wind']:.0f} km/h gusts",
            }
        )

    if precip_summary:
        near_term = precip_summary["next_day_total"] / 120.0
        burst = np.clip(precip_summary["peak_hour"] / 30.0, 0.0, 1.2)
        total += near_term + burst
        components.append(
            {
                "label": "Next 24h rain",
                "value": round(near_term, 2),
                "context": f"{precip_summary['next_day_total']:.1f} mm expected",
            }
        )
        components.append(
            {
                "label": "Peak hourly rain",
                "value": round(burst, 2),
                "context": f"{precip_summary['peak_hour']:.2f} mm/h burst",
            }
        )

    if hydrology_summary:
        discharge_growth = 0.0
        if hydrology_summary["current_discharge"] > 0:
            discharge_growth = (
                hydrology_summary["peak_discharge"] - hydrology_summary["current_discharge"]
            ) / max(hydrology_summary["current_discharge"], 1.0)
        discharge_growth = np.clip(discharge_growth, -0.5, 4.0)
        trend_factor = hydrology_summary["trend_delta"] / 10.0
        total += discharge_growth + trend_factor
        components.append(
            {
                "label": "Peak discharge vs today",
                "value": round(discharge_growth, 2),
                "context": (
                    f"{hydrology_summary['current_discharge']:.1f}→{hydrology_summary['peak_discharge']:.1f} m³/s"
                ),
            }
        )
        components.append(
            {
                "label": "Weekly discharge trend",
                "value": round(trend_factor, 2),
                "context": f"Δ {hydrology_summary['trend_delta']:+.2f} m³/s over 1 week",
            }
        )

    suggested = float(np.clip(total, 0.0, 6.0))
    return {
        "suggested_extra": round(suggested, 2),
        "components": components,
        "generated_at": datetime.utcnow(),
    }


def request_llm_guidance(
    api_key: str,
    model: str,
    recommendation: dict | None,
    forecast_summary: dict | None,
    hydrology_summary: dict | None,
    precip_summary: dict | None,
    target_level: float,
) -> str:
    if not api_key:
        raise ValueError("Provide an API key to request LLM guidance.")

    bullet_lines = []
    if recommendation:
        for comp in recommendation.get("components", []):
            bullet_lines.append(f"- {comp['label']}: +{comp['value']:.2f} m ({comp['context']})")

    drivers_block = bullet_lines or ["- No quantitative drivers available."]
    summary_lines = [
        f"Target flood water surface: {target_level:.2f} m",
        f"Recommended extra depth: {recommendation['suggested_extra']:.2f} m" if recommendation else "Recommendation pending.",
        "Drivers:",
        *drivers_block,
    ]

    extra_context = {
        "forecast": forecast_summary or {},
        "hydrology": hydrology_summary or {},
        "precipitation": precip_summary or {},
    }

    prompt = textwrap.dedent(
        f"""
        You are advising rapid flood response teams for Sunamganj, Bangladesh.
        Using the quantitative inputs below, draft a concise paragraph (<=120 words)
        with actionable interpretation of the recommended flood stage increase and how
        recent rainfall and discharge outlooks influence that choice. Always mention
        notable risks if river discharge is surging or if extreme rain is imminent.

        Summary:
        {'\\n'.join(summary_lines)}

        Raw metrics (JSON):
        {json.dumps(extra_context, default=str)}
        """
    ).strip()

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You are a hydrologist supporting disaster responders."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
        "max_tokens": 280,
    }

    response = requests.post(
        "https://api.openai.com/v1/chat/completions", json=payload, headers=headers, timeout=45
    )
    response.raise_for_status()
    data = response.json()
    choices = data.get("choices")
    if not choices:
        raise RuntimeError("LLM response did not include any choices.")
    return choices[0]["message"]["content"].strip()


# Inundation
river_mask = dem <= np.nanpercentile(dem, 5)
river_elev = np.nanmean(dem[river_mask])

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
st.session_state["latest_target_level"] = float(target_level)

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

forecast_summary = st.session_state.get("forecast_summary")
forecast_error = st.session_state.get("forecast_error", "")
precip_summary = st.session_state.get("precip_summary")
precip_error = st.session_state.get("precip_error", "")
hydrology_summary = st.session_state.get("hydrology_summary")
hydrology_error = st.session_state.get("hydrology_error", "")
recommendation = st.session_state.get("waterlevel_recommendation")
llm_recommendation = st.session_state.get("llm_recommendation")
llm_error = st.session_state.get("llm_error", "")

m = folium.Map(location=[center_lat, center_lon], zoom_start=9, control_scale=True, tiles="OpenStreetMap")
MiniMap(toggle_display=True, position="bottomleft").add_to(m)
Fullscreen(position="topright").add_to(m)

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
palette_ceiling = max(max_depth, 1e-3)
norm = colors.Normalize(vmin=0.0, vmax=palette_ceiling, clip=True)
normalized_depth = norm(depth)

cmap = colors.LinearSegmentedColormap.from_list(
    "shallow_to_deep_red",
     [
        (0.0, "#e0f3f8"),  # very light blue
        (0.25, "#abd9e9"),
        (0.5, "#74add1"),
        (0.75, "#4575b4"),
        (1.0, "#313695")   # deep indigo
    ]
)
rgba = cmap(normalized_depth)
alpha = np.where(mask, np.clip(0.25 + 0.6 * normalized_depth, 0.0, 1.0), 0.0)
rgba[..., 3] = alpha

rgba[..., :3] = np.where(mask[..., None], rgba[..., :3], 0.0)
flood_rgba = (rgba * 255).astype("uint8")

Image.fromarray(flood_rgba, mode="RGBA").save("flood_overlay.png")
ImageOverlay(name="Inundation", image="flood_overlay.png", bounds=[[s,w],[n,e]], opacity=0.8).add_to(m)
if palette_ceiling > 0:
    legend_max = max(palette_ceiling, 0.5)
    color_scale = LinearColormap(
        ["#e0f3f8", "#abd9e9", "#74add1", "#4575b4", "#313695"],
        vmin=0,
        vmax=legend_max,
        caption="Flood depth (m)",
    )
    color_scale.add_to(m)

with st.sidebar:
    st.subheader("Forecast insight")
    if st.session_state.get("forecast_inflight"):
        st.info("Fetching forecast outlook…")
    elif forecast_error:
        st.warning(f"Forecast unavailable: {forecast_error}")
    elif any([forecast_summary, hydrology_summary, precip_summary]):
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
                st.experimental_rerun()

        if forecast_summary:
            st.caption(
                f"7-day totals: {forecast_summary['total_rain']:.0f} mm rain · "
                f"peak wind {forecast_summary['peak_wind']:.0f} km/h · "
                f"average max temp {forecast_summary['mean_temp']:.1f} °C."
            )
        if precip_summary and not precip_error:
            st.caption(
                f"Next 24h rain {precip_summary['next_day_total']:.1f} mm · "
                f"Peak hourly burst {precip_summary['peak_hour']:.2f} mm."
            )
        if hydrology_summary and not hydrology_error:
            st.caption(
                f"River discharge now {hydrology_summary['current_discharge']:.1f} m³/s, "
                f"peaking near {hydrology_summary['peak_discharge']:.1f} m³/s (Δ {hydrology_summary['trend_delta']:+.2f})."
            )
        if hydrology_error:
            st.warning(f"Hydrology feed issue: {hydrology_error}")
        if precip_error:
            st.warning(f"Hourly rain feed issue: {precip_error}")
        if st.session_state.get("llm_inflight"):
            st.info("Generating LLM scenario note…")
        elif llm_error:
            st.warning(f"LLM guidance failed: {llm_error}")
        elif llm_recommendation:
            st.success("LLM scenario note ready in the outlook tab.")

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

# Calculate flooded roads if the GeoDataFrame is available
flooded_roads_km = 0.0
if 'roads' in locals() and not roads.empty:
    flooded_roads_km = calculate_flooded_roads_km(roads, flood, dem_transform, dem_crs)

tab_map, tab_impacts, tab_forecast, tab_methods = st.tabs([
    "Interactive map",
    "Exposure summary",
    "Next-week outlook",
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
            - **Inundation depth** — pale blue tiles mark shallow water and intensify to deep indigo where the model predicts the highest depths.
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

    snapshot_df = pd.DataFrame(
        [
            {"Category": "Roads (km)", "Assets in flood": f"{flooded_roads_km:.1f}"},
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

        The river base elevation is approximated from the average of the lowest 5% of DEM cells (≈ {river_elev:.2f} m). Pixels are
        flagged as inundated when they fall below the target water surface of {target_level:.2f} m. Colors transition from
        light blue into deep indigo as depth increases, with the darkest tiles representing the deepest water detectable in this
        scenario (≈ {max_depth:.2f} m).
        """
        + (
            "\n\n"
            + "Combined outlook recommends +"
            + f"{recommendation['suggested_extra']:.2f} m based on rainfall, hourly bursts, and river discharge."
            if recommendation
            else ""
        )
    )

with tab_forecast:
    st.markdown("#### 7-day meteorological outlook")
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
        if recommendation:
            narrative += (
                f" Combined driver score recommends **+{recommendation['suggested_extra']:.2f} m** at the gauge."
            )
        st.markdown(narrative)
        st.caption("Source: Open-Meteo API (refreshed hourly; cached locally for one hour).")
    elif forecast_error:
        st.warning("Forecast data not available yet. Try fetching the 7-day outlook from the sidebar.")
    else:
        st.info("Fetch the 7-day outlook from the sidebar to populate this tab with rainfall and wind projections.")

    if precip_summary:
        st.markdown("#### Hourly precipitation (last 48h → next 72h)")
        precip_cols = st.columns(3)
        precip_cols[0].metric("Last 48h", f"{precip_summary['recent_total']:.1f} mm")
        precip_cols[1].metric("Next 24h", f"{precip_summary['next_day_total']:.1f} mm")
        precip_cols[2].metric("Peak hourly", f"{precip_summary['peak_hour']:.2f} mm/h")
        precip_df = precip_summary["dataframe"].set_index("Local Timestamp").sort_index()
        st.area_chart(precip_df["Precipitation (mm)"], height=220)
        st.caption("Source: Open-Meteo hourly precipitation (UTC timestamps shown).")
    elif precip_error:
        st.warning(f"Hourly precipitation timeline unavailable: {precip_error}")

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
    elif hydrology_error:
        st.warning(f"River discharge forecast unavailable: {hydrology_error}")

    if llm_recommendation:
        st.markdown("#### LLM scenario brief")
        st.info(llm_recommendation)
    elif llm_error:
        st.warning(f"LLM scenario note unavailable: {llm_error}")
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
        : Each rerun fetches the latest features from Overpass so classifications and names stay fresh.

        **Custom overlays**
        : Add a WMS endpoint (e.g., national flood forecasts) or the RainViewer radar tiles to validate the extent visually.

        **Hydrology feed**
        : River discharge scenarios come from the Open-Meteo Flood API (Copernicus GloFAS), highlighting rises that warrant extra depth.

        **LLM narrative (optional)**
        : Provide an OpenAI API key in the sidebar to generate a short GPT-based briefing that ties the numbers together.
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
