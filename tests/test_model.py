"""
Unit tests for flood modeling functions.
"""
import pytest
import numpy as np
from rasterio.transform import Affine
from pyproj import CRS
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from model import (
    estimate_river_base_elevation,
    pixel_area_km2,
    bathtub_flood,
    hand_flood,
    calculate_flood_area_km2
)


class TestRiverBaseElevation:
    def test_basic_estimation(self):
        """Test river base elevation estimation."""
        dem = np.array([
            [10, 10, 10],
            [5, 2, 5],
            [10, 10, 10]
        ], dtype=np.float32)
        
        river_elev = estimate_river_base_elevation(dem, percentile=20)
        assert river_elev == pytest.approx(3.5, rel=0.1)
    
    def test_with_nan(self):
        """Test with NaN values."""
        dem = np.array([
            [10, np.nan, 10],
            [5, 2, 5],
            [10, 10, 10]
        ], dtype=np.float32)
        
        river_elev = estimate_river_base_elevation(dem, percentile=20)
        assert not np.isnan(river_elev)


class TestPixelArea:
    def test_geographic_crs(self):
        """Test area calculation for geographic CRS."""
        transform = Affine(0.001, 0, 90.0, 0, -0.001, 25.0)
        crs = CRS.from_epsg(4326)
        lat_mid = 25.0
        
        area = pixel_area_km2(transform, crs, lat_mid)
        
        # At 25°N, 0.001° ≈ 0.111 km (lon) × 0.111 km (lat) ≈ 0.012 km²
        assert area > 0
        assert area < 0.02  # Reasonable bounds
    
    def test_projected_crs(self):
        """Test area calculation for projected CRS."""
        transform = Affine(30, 0, 500000, 0, -30, 3000000)
        crs = CRS.from_epsg(32645)  # UTM 45N
        lat_mid = 25.0
        
        area = pixel_area_km2(transform, crs, lat_mid)
        
        # 30m × 30m = 900 m² = 0.0009 km²
        assert area == pytest.approx(0.0009, rel=0.01)
    
    def test_negative_transform_values(self):
        """Test with negative transform values (common for y-axis)."""
        transform = Affine(30, 0, 500000, 0, -30, 3000000)
        crs = CRS.from_epsg(32645)
        lat_mid = 25.0
        
        area = pixel_area_km2(transform, crs, lat_mid)
        assert area > 0  # Should always be positive


class TestBathtubFlood:
    def test_simple_flood(self):
        """Test basic bathtub flooding."""
        dem = np.array([
            [10, 10, 10],
            [5, 2, 5],
            [10, 10, 10]
        ], dtype=np.float32)
        
        flood, depth = bathtub_flood(dem, target_level=6.0)
        
        # Should flood cells with elevation <= 6
        assert flood[1, 0] == 1  # elevation 5
        assert flood[1, 1] == 1  # elevation 2
        assert flood[1, 2] == 1  # elevation 5
        assert flood[0, 0] == 0  # elevation 10
        
        # Check depths
        assert depth[1, 1] == pytest.approx(4.0)  # 6 - 2
        assert depth[1, 0] == pytest.approx(1.0)  # 6 - 5
    
    def test_no_flood(self):
        """Test when water level is below all terrain."""
        dem = np.array([[10, 10], [10, 10]], dtype=np.float32)
        flood, depth = bathtub_flood(dem, target_level=5.0)
        
        assert np.sum(flood) == 0
        assert np.sum(depth) == 0


class TestHandFlood:
    def test_hand_flood(self):
        """Test HAND-based flooding."""
        dem = np.array([
            [10, 10, 10],
            [5, 2, 5],
            [10, 10, 10]
        ], dtype=np.float32)
        
        hand = np.array([
            [8, 8, 8],
            [3, 0, 3],
            [8, 8, 8]
        ], dtype=np.float32)
        
        flood, depth = hand_flood(dem, hand, level=4.0)
        
        # Should flood cells with HAND <= 4
        assert flood[1, 0] == 1  # HAND 3
        assert flood[1, 1] == 1  # HAND 0
        assert flood[1, 2] == 1  # HAND 3
        assert flood[0, 0] == 0  # HAND 8


class TestFloodArea:
    def test_area_calculation(self):
        """Test flood area calculation."""
        flood = np.array([
            [0, 0, 0],
            [1, 1, 1],
            [0, 0, 0]
        ], dtype=np.uint8)
        
        transform = Affine(100, 0, 0, 0, -100, 0)  # 100m pixels
        crs = CRS.from_epsg(32645)  # UTM
        lat_mid = 25.0
        
        area = calculate_flood_area_km2(flood, transform, crs, lat_mid)
        
        # 3 pixels × (100m × 100m) = 30,000 m² = 0.03 km²
        assert area == pytest.approx(0.03, rel=0.01)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
