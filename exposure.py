"""
Exposure analytics module for calculating impacts on infrastructure and assets.
"""
from typing import Tuple, Dict
import numpy as np
import geopandas as gpd
from rasterio import features
from rasterio.transform import Affine
from shapely.geometry import shape
from shapely.ops import unary_union
from pyproj import CRS, Transformer
import streamlit as st


@st.cache_data(show_spinner=False)
def build_flood_polygons(_flood_mask: np.ndarray, _transform: Affine, _crs: CRS) -> gpd.GeoDataFrame:
    """
    Convert flood mask to polygon geometries.
    
    Args:
        _flood_mask: Binary flood mask
        _transform: Raster transform
        _crs: Coordinate reference system
    
    Returns:
        GeoDataFrame with flood polygons
    """
    shapes = features.shapes(_flood_mask, mask=(_flood_mask == 1), transform=_transform)
    flood_polygons = [shape(geom) for geom, val in shapes if val == 1]
    
    if not flood_polygons:
        return gpd.GeoDataFrame(geometry=[], crs=_crs)
    
    # Dissolve into single geometry
    flood_geom = unary_union(flood_polygons)
    return gpd.GeoDataFrame(geometry=[flood_geom], crs=_crs)


def calculate_flooded_roads_km(
    roads_gdf: gpd.GeoDataFrame,
    flood_mask: np.ndarray,
    dem_transform: Affine,
    dem_crs: CRS
) -> Tuple[float, Dict[str, float]]:
    """
    Calculate flooded road length in km, categorized by road type.
    
    Args:
        roads_gdf: GeoDataFrame with road geometries
        flood_mask: Binary flood mask
        dem_transform: Raster transform
        dem_crs: DEM coordinate reference system
    
    Returns:
        Tuple of (total_km, dict of km by highway type)
    """
    if roads_gdf.empty:
        return 0.0, {}

    # Project roads to the DEM's CRS for accurate intersection
    roads_proj = roads_gdf.to_crs(dem_crs)

    # Build flood polygons
    flood_gdf = build_flood_polygons(flood_mask, dem_transform, dem_crs)
    
    if flood_gdf.empty:
        return 0.0, {}
    
    flood_geom = flood_gdf.geometry.iloc[0]

    # Find intersection and calculate length
    flooded_roads_geom = roads_proj.geometry.intersection(flood_geom)
    flooded_roads_gdf = gpd.GeoDataFrame(
        geometry=flooded_roads_geom,
        crs=dem_crs
    )
    
    # Add highway type back
    flooded_roads_gdf['highway'] = roads_proj['highway'].values
    
    # Calculate total length in km
    total_km = flooded_roads_gdf.length.sum() / 1000.0
    
    # Calculate by road type
    by_type = {}
    if 'highway' in flooded_roads_gdf.columns:
        for hwy_type in flooded_roads_gdf['highway'].unique():
            if hwy_type and hwy_type != 'unknown':
                type_length = flooded_roads_gdf[
                    flooded_roads_gdf['highway'] == hwy_type
                ].length.sum() / 1000.0
                by_type[hwy_type] = float(type_length)
    
    return float(total_km), by_type


def calculate_point_exposure(
    points_gdf: gpd.GeoDataFrame,
    flood_mask: np.ndarray,
    dem_transform: Affine,
    dem_crs: CRS
) -> int:
    """
    Calculate number of points within flooded area using spatial join.
    
    Args:
        points_gdf: GeoDataFrame with point geometries
        flood_mask: Binary flood mask
        dem_transform: Raster transform
        dem_crs: DEM coordinate reference system
    
    Returns:
        Count of exposed points
    """
    if points_gdf.empty:
        return 0
    
    # Build flood polygons
    flood_gdf = build_flood_polygons(flood_mask, dem_transform, dem_crs)
    
    if flood_gdf.empty:
        return 0
    
    # Project points to DEM CRS
    points_proj = points_gdf.to_crs(dem_crs)
    
    # Spatial join
    joined = gpd.sjoin(points_proj, flood_gdf, how='inner', predicate='within')
    
    return len(joined)


def sample_mask_at_point(
    mask: np.ndarray,
    lon: float,
    lat: float,
    transform: Affine,
    dem_crs: CRS
) -> int:
    """
    Sample flood mask at a specific point (fallback method).
    
    Args:
        mask: Flood mask array
        lon: Longitude
        lat: Latitude
        transform: Raster transform
        dem_crs: DEM CRS
    
    Returns:
        Mask value at point (0 or 1)
    """
    try:
        Tinv = Transformer.from_crs("EPSG:4326", dem_crs, always_xy=True)
        x, y = Tinv.transform(lon, lat)
        col = int((x - transform.c) / transform.a)
        row = int((y - transform.f) / transform.e)
        
        if 0 <= row < mask.shape[0] and 0 <= col < mask.shape[1]:
            return int(mask[row, col])
    except Exception:
        pass
    
    return 0
