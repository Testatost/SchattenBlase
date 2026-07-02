from __future__ import annotations

from math import atan2, cos, degrees, radians, sin, sqrt
from typing import Iterable

EARTH_RADIUS_M = 6_378_137.0


def latlon_to_local_m(lat: float, lon: float, origin_lat: float, origin_lon: float) -> tuple[float, float]:
    x = radians(lon - origin_lon) * EARTH_RADIUS_M * cos(radians(origin_lat))
    y = radians(lat - origin_lat) * EARTH_RADIUS_M
    return x, y


def local_m_to_latlon(x: float, y: float, origin_lat: float, origin_lon: float) -> tuple[float, float]:
    lat = origin_lat + degrees(y / EARTH_RADIUS_M)
    lon = origin_lon + degrees(x / (EARTH_RADIUS_M * cos(radians(origin_lat))))
    return lat, lon


def polygon_area_m2(points: Iterable[tuple[float, float]]) -> float:
    pts = list(points)
    if len(pts) < 3:
        return 0.0
    area = 0.0
    for i, (x1, y1) in enumerate(pts):
        x2, y2 = pts[(i + 1) % len(pts)]
        area += x1 * y2 - x2 * y1
    return abs(area) * 0.5


def signed_polygon_area(points: Iterable[tuple[float, float]]) -> float:
    pts = list(points)
    if len(pts) < 3:
        return 0.0
    area = 0.0
    for i, (x1, y1) in enumerate(pts):
        x2, y2 = pts[(i + 1) % len(pts)]
        area += x1 * y2 - x2 * y1
    return area * 0.5


def polygon_centroid(points: list[tuple[float, float]]) -> tuple[float, float]:
    area = signed_polygon_area(points)
    if len(points) < 3 or abs(area) < 1e-9:
        if not points:
            return 0.0, 0.0
        return sum(p[0] for p in points) / len(points), sum(p[1] for p in points) / len(points)
    cx = 0.0
    cy = 0.0
    for i, (x1, y1) in enumerate(points):
        x2, y2 = points[(i + 1) % len(points)]
        cross = x1 * y2 - x2 * y1
        cx += (x1 + x2) * cross
        cy += (y1 + y2) * cross
    factor = 1.0 / (6.0 * area)
    return cx * factor, cy * factor


def latlon_polygon_area_m2(points: list[tuple[float, float]]) -> float:
    if len(points) < 3:
        return 0.0
    origin_lat = sum(p[0] for p in points) / len(points)
    origin_lon = sum(p[1] for p in points) / len(points)
    local = [latlon_to_local_m(lat, lon, origin_lat, origin_lon) for lat, lon in points]
    return polygon_area_m2(local)


def distance_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    return sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2)


def bearing_deg(a: tuple[float, float], b: tuple[float, float]) -> float:
    dx = b[0] - a[0]
    dy = b[1] - a[1]
    return (degrees(atan2(dx, dy)) + 360.0) % 360.0


def rotate_points(points: list[tuple[float, float]], angle_deg: float) -> list[tuple[float, float]]:
    angle = radians(angle_deg)
    ca = cos(angle)
    sa = sin(angle)
    return [(x * ca - y * sa, x * sa + y * ca) for x, y in points]


def bbox_size(points: list[tuple[float, float]]) -> tuple[float, float]:
    if not points:
        return 0.0, 0.0
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return max(xs) - min(xs), max(ys) - min(ys)


def convex_hull(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    unique = sorted(set((round(x, 8), round(y, 8)) for x, y in points))
    if len(unique) <= 1:
        return unique

    def cross(o: tuple[float, float], a: tuple[float, float], b: tuple[float, float]) -> float:
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower: list[tuple[float, float]] = []
    for p in unique:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)

    upper: list[tuple[float, float]] = []
    for p in reversed(unique):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)

    return lower[:-1] + upper[:-1]


def point_in_polygon(point: tuple[float, float], polygon: list[tuple[float, float]]) -> bool:
    x, y = point
    inside = False
    if len(polygon) < 3:
        return False
    j = len(polygon) - 1
    for i, (xi, yi) in enumerate(polygon):
        xj, yj = polygon[j]
        intersects = (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-12) + xi
        if intersects:
            inside = not inside
        j = i
    return inside


def azimuth_vector(azimuth_deg: float) -> tuple[float, float]:
    az = radians(azimuth_deg)
    return sin(az), cos(az)
