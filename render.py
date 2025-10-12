"""
Map rendering and visualization module.
"""
import io
from typing import Tuple, Optional
import numpy as np
from PIL import Image
import folium
from folium.raster_layers import ImageOverlay, WmsTileLayer, TileLayer
from folium.plugins import MousePosition, MiniMap, Fullscreen
from branca.colormap import LinearColormap
from matplotlib import colors
import base64


def create_dem_overlay(
    dem: np.ndarray,
    bounds: Tuple[Tuple[float, float], Tuple[float, float]],
    opacity: float = 0.5
) -> str:
    """
    Create DEM overlay as base64 data URL.
    
    Args:
        dem: Digital elevation model
        bounds: Map bounds [[s,w],[n,e]]
        opacity: Overlay opacity
    
    Returns:
        Base64 encoded image data URL
    """
    dem_norm = (dem - np.nanmin(dem)) / (np.nanmax(dem) - np.nanmin(dem) + 1e-6)
    dem_img = (np.nan_to_num(dem_norm) * 255).astype("uint8")
    alpha = np.where(np.isfinite(dem), int(opacity * 255), 0).astype("uint8")
    dem_rgba = np.dstack([dem_img, dem_img, dem_img, alpha])
    
    img = Image.fromarray(dem_rgba, mode="RGBA")
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)
    
    b64 = base64.b64encode(buf.read()).decode()
    return f"data:image/png;base64,{b64}"


def create_flood_overlay(
    flood_mask: np.ndarray,
    depth: np.ndarray,
    bounds: Tuple[Tuple[float, float], Tuple[float, float]],
    opacity: float = 0.8,
    colormap: str = "blue_gradient"
) -> Tuple[str, float]:
    """
    Create flood depth overlay as base64 data URL.
    
    Args:
        flood_mask: Binary flood mask
        depth: Flood depth array
        bounds: Map bounds [[s,w],[n,e]]
        opacity: Base opacity
        colormap: Color scheme name
    
    Returns:
        Tuple of (base64 data URL, max_depth)
    """
    mask = flood_mask == 1
    max_depth = float(depth[mask].max()) if np.any(mask) else 0.0
    palette_ceiling = max(max_depth, 1e-3)
    
    norm = colors.Normalize(vmin=0.0, vmax=palette_ceiling, clip=True)
    normalized_depth = norm(depth)
    
    if colormap == "blue_gradient":
        cmap = colors.LinearSegmentedColormap.from_list(
            "shallow_to_deep_blue",
            [
                (0.0, "#e0f3f8"),  # very light blue
                (0.25, "#abd9e9"),
                (0.5, "#74add1"),
                (0.75, "#4575b4"),
                (1.0, "#313695")   # deep indigo
            ]
        )
    elif colormap == "red_gradient":
        cmap = colors.LinearSegmentedColormap.from_list(
            "shallow_to_deep_red",
            [
                (0.0, "#fee5d9"),
                (0.25, "#fcae91"),
                (0.5, "#fb6a4a"),
                (0.75, "#de2d26"),
                (1.0, "#a50f15")
            ]
        )
    else:
        cmap = colors.LinearSegmentedColormap.from_list(
            "viridis_like",
            ["#440154", "#31688e", "#35b779", "#fde724"]
        )
    
    rgba = cmap(normalized_depth)
    alpha = np.where(mask, np.clip(0.25 + 0.6 * normalized_depth, 0.0, 1.0) * opacity, 0.0)
    rgba[..., 3] = alpha
    rgba[..., :3] = np.where(mask[..., None], rgba[..., :3], 0.0)
    flood_rgba = (rgba * 255).astype("uint8")
    
    img = Image.fromarray(flood_rgba, mode="RGBA")
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)
    
    b64 = base64.b64encode(buf.read()).decode()
    return f"data:image/png;base64,{b64}", max_depth


def build_folium_map(
    center_lat: float,
    center_lon: float,
    zoom: int = 9,
    basemap: str = "OpenStreetMap"
) -> folium.Map:
    """
    Create base folium map with controls.
    
    Args:
        center_lat: Center latitude
        center_lon: Center longitude
        zoom: Initial zoom level
        basemap: Basemap name
    
    Returns:
        Folium map object
    """
    # Map basemap names to tile URLs
    basemap_tiles = {
        "OpenStreetMap": "OpenStreetMap",
        "CartoDB Positron": "CartoDB positron",
        "CartoDB Dark Matter": "CartoDB dark_matter",
        "Stamen Terrain": "Stamen Terrain",
        "Stamen Toner": "Stamen Toner",
    }
    
    tiles = basemap_tiles.get(basemap, "OpenStreetMap")
    
    m = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=zoom,
        control_scale=True,
        tiles=tiles
    )
    
    MiniMap(toggle_display=True, position="bottomleft").add_to(m)
    Fullscreen(position="topright").add_to(m)
    
    return m


def add_legend(m: folium.Map, max_depth: float, colormap: str = "blue_gradient") -> None:
    """Add color legend to map."""
    if max_depth <= 0:
        return
    
    legend_max = max(max_depth, 0.5)
    
    if colormap == "blue_gradient":
        colors_list = ["#e0f3f8", "#abd9e9", "#74add1", "#4575b4", "#313695"]
    elif colormap == "red_gradient":
        colors_list = ["#fee5d9", "#fcae91", "#fb6a4a", "#de2d26", "#a50f15"]
    else:
        colors_list = ["#440154", "#31688e", "#35b779", "#fde724"]
    
    color_scale = LinearColormap(
        colors_list,
        vmin=0,
        vmax=legend_max,
        caption="Flood depth (m)",
    )
    color_scale.add_to(m)


def add_osm_layers(
    m: folium.Map,
    roads_gdf,
    health_gdf,
    shelters_gdf
) -> None:
    """Add OSM layers to map."""
    if not roads_gdf.empty:
        folium.GeoJson(
            roads_gdf.to_json(),
            name="Roads",
            style_function=lambda x: {"color": "#444", "weight": 1}
        ).add_to(m)

    if not health_gdf.empty:
        for _, r in health_gdf.iterrows():
            folium.CircleMarker(
                location=[r["lat"], r["lon"]],
                radius=4,
                color="#2ca25f",
                fill=True,
                fill_opacity=0.9,
                popup=f"Health: {r.get('name', 'health')}"
            ).add_to(m)

    if not shelters_gdf.empty:
        for _, r in shelters_gdf.iterrows():
            folium.CircleMarker(
                location=[r["lat"], r["lon"]],
                radius=4,
                color="#de2d26",
                fill=True,
                fill_opacity=0.9,
                popup=f"Cyclone Shelter: {r.get('name', 'shelter')}"
            ).add_to(m)
