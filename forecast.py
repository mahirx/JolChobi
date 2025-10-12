"""
Forecast processing and water level recommendation module.
"""
import json
import textwrap
from typing import Dict, Optional
from datetime import datetime
import numpy as np
import pandas as pd
import requests
from io_sources import create_retry_session


def summarize_forecast(forecast: dict) -> dict:
    """Summarize 7-day weather forecast."""
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
    """Summarize hourly precipitation data."""
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
    """Summarize river discharge forecast."""
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
        trend_delta = float(
            trend_window["Discharge mean (m³/s)"].iloc[-1] - trend_window["Discharge mean (m³/s)"].iloc[0]
        )

    return {
        "dataframe": df,
        "current_discharge": round(current_discharge, 2),
        "peak_discharge": round(top_forecast, 2),
        "trend_delta": round(trend_delta, 2),
    }


def build_waterlevel_recommendation(
    forecast_summary: Optional[dict],
    hydrology_summary: Optional[dict],
    precip_summary: Optional[dict],
) -> Optional[dict]:
    """Build water level recommendation from forecast data."""
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
    recommendation: Optional[dict],
    forecast_summary: Optional[dict],
    hydrology_summary: Optional[dict],
    precip_summary: Optional[dict],
    target_level: float,
) -> str:
    """Request LLM-generated scenario guidance."""
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

    summary_text = '\n'.join(summary_lines)
    prompt = textwrap.dedent(
        f"""
        You are advising rapid flood response teams for Sunamganj, Bangladesh.
        Using the quantitative inputs below, draft a concise paragraph (<=120 words)
        with actionable interpretation of the recommended flood stage increase and how
        recent rainfall and discharge outlooks influence that choice. Always mention
        notable risks if river discharge is surging or if extreme rain is imminent.

        Summary:
        {summary_text}

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

    session = create_retry_session()
    try:
        response = session.post(
            "https://api.openai.com/v1/chat/completions",
            json=payload,
            headers=headers,
            timeout=45
        )
        response.raise_for_status()
        data = response.json()
        choices = data.get("choices")
        if not choices:
            raise RuntimeError("LLM response did not include any choices.")
        return choices[0]["message"]["content"].strip()
    except requests.exceptions.HTTPError as e:
        # Parse OpenAI error for better messages
        try:
            error_data = e.response.json()
            error_msg = error_data.get("error", {}).get("message", str(e))
            raise RuntimeError(f"OpenAI API error: {error_msg}")
        except:
            raise RuntimeError(f"LLM request failed: {str(e)}")
