"""
Data ingestion module for JolChobi flood visualizer.
Handles Overpass API, forecast APIs, and hydrology data.
"""
import json
import time
from typing import Dict, Tuple, Optional
import requests
import geopandas as gpd
import pandas as pd
from shapely.geometry import shape
import streamlit as st
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


def create_retry_session(retries: int = 3, backoff_factor: float = 0.5) -> requests.Session:
    """Create a requests session with retry logic."""
    session = requests.Session()
    retry = Retry(
        total=retries,
        read=retries,
        connect=retries,
        backoff_factor=backoff_factor,
        status_forcelist=(500, 502, 503, 504, 429),
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    return session


def overpass(query: str, endpoint: str, timeout: int = 90) -> dict:
    """Query Overpass API with retry logic."""
    session = create_retry_session()
    try:
        r = session.post(endpoint, data={"data": query}, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"Overpass API request failed: {str(e)}")


@st.cache_data(show_spinner=False, ttl=3600)
def osm_points(endpoint: str, bbox: Tuple[float, float, float, float], what: str) -> gpd.GeoDataFrame:
    """Fetch OSM points (health facilities or cyclone shelters) with caching."""
    s, w, n, e = bbox
    if what == "health":
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
        if el["type"] == "node":
            lon, lat = el["lon"], el["lat"]
        else:
            c = el.get("center")
            if not c:
                continue
            lat, lon = c["lat"], c["lon"]
        name = (el.get("tags") or {}).get("name", "")
        if what != "health":
            tags = el.get("tags", {})
            lname = name.lower()
            stype = (tags.get("shelter_type", "") or "").lower()
            if not ("cyclone" in lname or "storm" in lname or "cyclone" in stype or "storm" in stype):
                continue
        pts.append({"name": name or what, "lon": lon, "lat": lat})
    
    if not pts:
        return gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")
    
    return gpd.GeoDataFrame(
        pts,
        geometry=gpd.points_from_xy([p["lon"] for p in pts], [p["lat"] for p in pts]),
        crs="EPSG:4326"
    )


@st.cache_data(show_spinner=False, ttl=3600)
def osm_roads(endpoint: str, bbox: Tuple[float, float, float, float]) -> gpd.GeoDataFrame:
    """Fetch OSM roads with caching."""
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
        highway_type = (el.get("tags") or {}).get("highway", "unknown")
        feats.append({
            "name": (el.get("tags") or {}).get("name", ""),
            "highway": highway_type,
            "geometry": {"type": "LineString", "coordinates": coords}
        })

    if not feats:
        return gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")

    geoms = [shape(f["geometry"]) for f in feats]
    gdf = gpd.GeoDataFrame(feats, geometry=geoms, crs="EPSG:4326")
    return gdf


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
    session = create_retry_session()
    response = session.get(url, params=params, timeout=20)
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
    session = create_retry_session()
    response = session.get(url, params=params, timeout=20)
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
    session = create_retry_session()
    response = session.get(url, params=params, timeout=20)
    response.raise_for_status()
    return response.json()
