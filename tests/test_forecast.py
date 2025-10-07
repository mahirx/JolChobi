"""
Unit tests for forecast processing functions.
"""
import pytest
import pandas as pd
from datetime import datetime
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from forecast import (
    summarize_forecast,
    summarize_precip,
    summarize_hydrology,
    build_waterlevel_recommendation
)


class TestForecastSummary:
    def test_basic_summary(self):
        """Test forecast summarization."""
        forecast_data = {
            "daily": {
                "time": ["2025-01-01", "2025-01-02", "2025-01-03"],
                "precipitation_sum": [10.0, 20.0, 15.0],
                "windspeed_10m_max": [30.0, 40.0, 35.0],
                "temperature_2m_max": [25.0, 26.0, 24.0]
            }
        }
        
        summary = summarize_forecast(forecast_data)
        
        assert summary["total_rain"] == 45.0
        assert summary["peak_wind"] == 40.0
        assert summary["mean_temp"] == pytest.approx(25.0, rel=0.1)
        assert "dataframe" in summary
        assert "suggested_extra" in summary
    
    def test_empty_forecast(self):
        """Test with empty forecast data."""
        forecast_data = {"daily": {}}
        
        with pytest.raises(ValueError, match="did not include daily outlook"):
            summarize_forecast(forecast_data)


class TestPrecipSummary:
    def test_precip_summary(self):
        """Test precipitation summarization."""
        now = datetime.utcnow()
        times = pd.date_range(start=now - pd.Timedelta(hours=48), periods=120, freq='1H')
        
        precip_data = {
            "hourly": {
                "time": times.strftime("%Y-%m-%dT%H:%M").tolist(),
                "precipitation": [1.0] * 120  # 1mm per hour
            }
        }
        
        summary = summarize_precip(precip_data)
        
        assert summary["recent_total"] > 0
        assert summary["next_day_total"] >= 0
        assert "dataframe" in summary
    
    def test_empty_precip(self):
        """Test with empty precipitation data."""
        precip_data = {"hourly": {}}
        
        with pytest.raises(ValueError, match="returned no timestamps"):
            summarize_precip(precip_data)


class TestHydrologySummary:
    def test_hydrology_summary(self):
        """Test hydrology summarization."""
        dates = pd.date_range(start="2025-01-01", periods=10, freq='D')
        
        hydrology_data = {
            "daily": {
                "time": dates.strftime("%Y-%m-%d").tolist(),
                "river_discharge": [100.0, 110.0, 120.0, 130.0, 140.0, 150.0, 160.0, 170.0, 180.0, 190.0],
                "river_discharge_min": [90.0] * 10,
                "river_discharge_max": [200.0] * 10,
                "river_discharge_mean": [100.0, 105.0, 110.0, 115.0, 120.0, 125.0, 130.0, 135.0, 140.0, 145.0]
            }
        }
        
        summary = summarize_hydrology(hydrology_data)
        
        assert summary["current_discharge"] == 100.0
        assert summary["peak_discharge"] == 200.0
        assert summary["trend_delta"] > 0  # Increasing trend
        assert "dataframe" in summary
    
    def test_empty_hydrology(self):
        """Test with empty hydrology data."""
        hydrology_data = {"daily": {}}
        
        with pytest.raises(ValueError, match="returned no discharge timeline"):
            summarize_hydrology(hydrology_data)


class TestWaterLevelRecommendation:
    def test_combined_recommendation(self):
        """Test water level recommendation from multiple sources."""
        forecast_summary = {
            "total_rain": 100.0,
            "peak_wind": 50.0,
            "mean_temp": 25.0
        }
        
        precip_summary = {
            "next_day_total": 30.0,
            "peak_hour": 10.0
        }
        
        hydrology_summary = {
            "current_discharge": 100.0,
            "peak_discharge": 150.0,
            "trend_delta": 20.0
        }
        
        recommendation = build_waterlevel_recommendation(
            forecast_summary,
            hydrology_summary,
            precip_summary
        )
        
        assert recommendation is not None
        assert "suggested_extra" in recommendation
        assert "components" in recommendation
        assert len(recommendation["components"]) > 0
        assert recommendation["suggested_extra"] >= 0
        assert recommendation["suggested_extra"] <= 6.0
    
    def test_partial_data(self):
        """Test recommendation with partial data."""
        forecast_summary = {
            "total_rain": 50.0,
            "peak_wind": 30.0,
            "mean_temp": 25.0
        }
        
        recommendation = build_waterlevel_recommendation(
            forecast_summary,
            None,
            None
        )
        
        assert recommendation is not None
        assert recommendation["suggested_extra"] >= 0
    
    def test_no_data(self):
        """Test with no data."""
        recommendation = build_waterlevel_recommendation(None, None, None)
        
        assert recommendation is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
