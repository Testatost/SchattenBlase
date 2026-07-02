from __future__ import annotations

from math import atan, cos, degrees, log, pi, radians, sinh, tan

from config import TILE_SIZE

EARTH_CIRCUMFERENCE_M = 40_075_016.686


def clamp_lat(lat: float) -> float:
    return max(-85.05112878, min(85.05112878, lat))


def latlon_to_global_px(lat: float, lon: float, zoom: int) -> tuple[float, float]:
    lat = clamp_lat(lat)
    scale = TILE_SIZE * (2**zoom)
    x = (lon + 180.0) / 360.0 * scale
    lat_rad = radians(lat)
    y = (1.0 - log(tan(lat_rad) + 1.0 / cos(lat_rad)) / pi) / 2.0 * scale
    return x, y


def global_px_to_latlon(x: float, y: float, zoom: int) -> tuple[float, float]:
    scale = TILE_SIZE * (2**zoom)
    lon = x / scale * 360.0 - 180.0
    n = pi - 2.0 * pi * y / scale
    lat = degrees(atan(sinh(n)))
    return lat, lon


def meters_per_pixel(lat: float, zoom: int) -> float:
    return cos(radians(clamp_lat(lat))) * EARTH_CIRCUMFERENCE_M / (TILE_SIZE * (2**zoom))


def tile_count(zoom: int) -> int:
    return 2**zoom
