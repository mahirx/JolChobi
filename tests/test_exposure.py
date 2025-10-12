"""
Unit tests for exposure analytics functions.
"""
import pytest
import numpy as np
import geopandas as gpd
from shapely.geometry import Point, LineString
from rasterio.transform import Affine
from pyproj import CRS
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from exposure import (
    build_flood_polygons,
    calculate_flooded_roads_km,
    calculate_point_exposure,
    sample_mask_at_point
)


class TestFloodPolygons:
    def test_simple_polygon(self):
        """Test flood polygon generation."""
        flood_mask = np.array([
            [0, 0, 0],
            [0, 1, 0],
            [0, 0, 0]
        ], dtype=np.uint8)
        
        transform = Affine(1, 0, 0, 0, -1, 3)
        crs = CRS.from_epsg(4326)
        
        gdf = build_flood_polygons(flood_mask, transform, crs)
        
        assert not gdf.empty
        assert len(gdf) == 1
        assert gdf.crs == crs
    
    def test_empty_flood(self):
        """Test with no flooding."""
        flood_mask = np.zeros((3, 3), dtype=np.uint8)
        transform = Affine(1, 0, 0, 0, -1, 3)
        crs = CRS.from_epsg(4326)
        
        gdf = build_flood_polygons(flood_mask, transform, crs)
        
        assert gdf.empty


class TestPointExposure:
    def test_points_in_flood(self):
        """Test point exposure calculation."""
        # Create flood mask
        flood_mask = np.array([
            [0, 0, 0, 0, 0],
            [0, 1, 1, 1, 0],
            [0, 1, 1, 1, 0],
            [0, 1, 1, 1, 0],
            [0, 0, 0, 0, 0]
        ], dtype=np.uint8)
        
        transform = Affine(1, 0, 0, 0, -1, 5)
        crs = CRS.from_epsg(4326)
        
        # Create points - some inside, some outside flood
        points_data = [
            {"name": "Inside 1", "geometry": Point(1.5, 3.5)},
            {"name": "Inside 2", "geometry": Point(2.5, 2.5)},
            {"name": "Outside", "geometry": Point(0.5, 0.5)}
        ]
        points_gdf = gpd.GeoDataFrame(points_data, crs=crs)
        
        exposed = calculate_point_exposure(points_gdf, flood_mask, transform, crs)
        
        assert exposed == 2  # Two points inside flood zone
    
    def test_empty_points(self):
        """Test with no points."""
        flood_mask = np.ones((3, 3), dtype=np.uint8)
        transform = Affine(1, 0, 0, 0, -1, 3)
        crs = CRS.from_epsg(4326)
        
        points_gdf = gpd.GeoDataFrame(geometry=[], crs=crs)
        
        exposed = calculate_point_exposure(points_gdf, flood_mask, transform, crs)
        
        assert exposed == 0


class TestFloodedRoads:
    def test_road_intersection(self):
        """Test flooded roads calculation."""
        # Create flood mask
        flood_mask = np.array([
            [0, 0, 0, 0, 0],
            [0, 1, 1, 1, 0],
            [0, 1, 1, 1, 0],
            [0, 1, 1, 1, 0],
            [0, 0, 0, 0, 0]
        ], dtype=np.uint8)
        
        transform = Affine(100, 0, 0, 0, -100, 500)  # 100m pixels
        crs = CRS.from_epsg(32645)  # UTM for metric calculations
        
        # Create a road that crosses the flood zone
        road_data = [
            {
                "name": "Main Road",
                "highway": "primary",
                "geometry": LineString([(150, 350), (350, 350)])  # Crosses flood
            }
        ]
        roads_gdf = gpd.GeoDataFrame(road_data, crs=crs)
        
        total_km, by_type = calculate_flooded_roads_km(roads_gdf, flood_mask, transform, crs)
        
        # Road crosses 3 flooded pixels (300m) = 0.3 km
        assert total_km > 0
        assert total_km < 0.5  # Reasonable bounds
        assert "primary" in by_type
    
    def test_no_roads(self):
        """Test with no roads."""
        flood_mask = np.ones((3, 3), dtype=np.uint8)
        transform = Affine(100, 0, 0, 0, -100, 300)
        crs = CRS.from_epsg(32645)
        
        roads_gdf = gpd.GeoDataFrame(geometry=[], crs=crs)
        
        total_km, by_type = calculate_flooded_roads_km(roads_gdf, flood_mask, transform, crs)
        
        assert total_km == 0.0
        assert by_type == {}


class TestSampleMask:
    def test_sample_at_point(self):
        """Test mask sampling at specific point."""
        mask = np.array([
            [0, 0, 0],
            [0, 1, 0],
            [0, 0, 0]
        ], dtype=np.uint8)
        
        transform = Affine(1, 0, 0, 0, -1, 3)
        crs = CRS.from_epsg(4326)
        
        # Sample at flooded location
        value = sample_mask_at_point(mask, 1.5, 1.5, transform, crs)
        assert value == 1
        
        # Sample at non-flooded location
        value = sample_mask_at_point(mask, 0.5, 0.5, transform, crs)
        assert value == 0
    
    def test_out_of_bounds(self):
        """Test sampling outside mask bounds."""
        mask = np.array([[1, 1], [1, 1]], dtype=np.uint8)
        transform = Affine(1, 0, 0, 0, -1, 2)
        crs = CRS.from_epsg(4326)
        
        value = sample_mask_at_point(mask, 10.0, 10.0, transform, crs)
        assert value == 0  # Should return 0 for out of bounds


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
