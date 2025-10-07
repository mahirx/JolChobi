"""
Flood modeling and inundation calculation module.
"""
import math
from typing import Tuple, Optional
import numpy as np
from rasterio.transform import Affine
from pyproj import Geod, CRS


def estimate_river_base_elevation(dem: np.ndarray, percentile: float = 5.0) -> float:
    """
    Estimate river base elevation from DEM.
    
    Args:
        dem: Digital elevation model array
        percentile: Percentile of lowest values to use (default 5%)
    
    Returns:
        Estimated river elevation in meters
    """
    river_mask = dem <= np.nanpercentile(dem, percentile)
    return float(np.nanmean(dem[river_mask]))


def quick_hand(dem: np.ndarray, transform: Affine, crs: Optional[CRS] = None) -> np.ndarray:
    """
    Approximate Height Above Nearest Drainage using distance transform.
    
    Args:
        dem: Digital elevation model
        transform: Raster transform
        crs: Coordinate reference system
    
    Returns:
        Approximate HAND surface
    """
    low = dem <= np.nanpercentile(dem, 10)
    try:
        from scipy.ndimage import distance_transform_edt
        dist = distance_transform_edt(~low)
        
        # Calculate pixel size more accurately
        if crs and crs.is_geographic:
            # For geographic CRS, use average latitude
            lat_mid = 0.0  # Will be passed from caller
            pix = abs(transform.a) * 111320 * math.cos(math.radians(lat_mid))
        else:
            pix = math.sqrt(abs(transform.a) * abs(transform.e))
        
        return dist * pix
    except Exception:
        return np.where(low, 0, 1).astype("float32")


def bathtub_flood(dem: np.ndarray, target_level: float) -> Tuple[np.ndarray, np.ndarray]:
    """
    Simple bathtub flood model.
    
    Args:
        dem: Digital elevation model
        target_level: Target water surface elevation
    
    Returns:
        Tuple of (flood_mask, depth_array)
    """
    flood = (dem <= target_level).astype("uint8")
    surface_delta = np.maximum(target_level - dem, 0)
    surface_delta = np.where(np.isfinite(surface_delta), surface_delta, 0)
    
    depth = np.zeros_like(surface_delta, dtype="float32")
    mask = flood == 1
    if np.any(mask):
        depth[mask] = surface_delta[mask]
    
    return flood, depth


def hand_flood(dem: np.ndarray, hand: np.ndarray, level: float) -> Tuple[np.ndarray, np.ndarray]:
    """
    HAND-based flood model.
    
    Args:
        dem: Digital elevation model
        hand: Height Above Nearest Drainage surface
        level: Water level above drainage
    
    Returns:
        Tuple of (flood_mask, depth_array)
    """
    flood = (hand <= level).astype("uint8")
    surface_delta = np.maximum(level - hand, 0)
    surface_delta = np.where(np.isfinite(surface_delta), surface_delta, 0)
    
    depth = np.zeros_like(surface_delta, dtype="float32")
    mask = flood == 1
    if np.any(mask):
        depth[mask] = surface_delta[mask]
    
    return flood, depth


def pixel_area_km2(transform: Affine, crs: Optional[CRS], lat_mid: float) -> float:
    """
    Calculate pixel area in km² with proper handling of geographic vs projected CRS.
    
    Args:
        transform: Raster transform
        crs: Coordinate reference system
        lat_mid: Middle latitude for geographic calculations
    
    Returns:
        Pixel area in square kilometers
    """
    a = abs(transform.a)
    e = abs(transform.e)
    
    if crs and crs.is_geographic:
        # Use pyproj.Geod for accurate area calculation
        geod = Geod(ellps="WGS84")
        
        # Calculate area of a pixel at the middle latitude
        lon_deg = a
        lat_deg = e
        
        # Approximate area using geodesic calculations
        deg_to_km = 111.32
        lon_km = deg_to_km * math.cos(math.radians(lat_mid))
        lat_km = deg_to_km
        
        return lon_deg * lon_km * lat_deg * lat_km
    else:
        # Projected CRS - simple calculation
        return (a * e) / 1e6


def calculate_flood_area_km2(flood_mask: np.ndarray, transform: Affine, crs: Optional[CRS], lat_mid: float) -> float:
    """Calculate total flooded area in km²."""
    pix_area = pixel_area_km2(transform, crs, lat_mid)
    return float(np.sum(flood_mask == 1) * pix_area)
