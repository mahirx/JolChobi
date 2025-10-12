#!/usr/bin/env python3
"""Test script to verify all imports work correctly."""

print("Testing imports...")

try:
    print("✓ Testing io_sources...")
    from io_sources import (
        osm_points, osm_roads, fetch_weekly_forecast,
        fetch_hourly_precipitation, fetch_hydrology_forecast
    )
    
    print("✓ Testing model...")
    from model import (
        estimate_river_base_elevation, quick_hand, bathtub_flood,
        hand_flood, calculate_flood_area_km2
    )
    
    print("✓ Testing exposure...")
    from exposure import (
        calculate_flooded_roads_km, calculate_point_exposure
    )
    
    print("✓ Testing forecast...")
    from forecast import (
        summarize_forecast, summarize_precip, summarize_hydrology,
        build_waterlevel_recommendation, request_llm_guidance
    )
    
    print("✓ Testing render...")
    from render import (
        create_dem_overlay, create_flood_overlay, build_folium_map,
        add_legend, add_osm_layers
    )
    
    print("\n✅ All module imports successful!")
    print("\nNote: The app requires running with 'streamlit run app.py'")
    
except ImportError as e:
    print(f"\n❌ Import error: {e}")
    exit(1)
except Exception as e:
    print(f"\n❌ Unexpected error: {e}")
    exit(1)
