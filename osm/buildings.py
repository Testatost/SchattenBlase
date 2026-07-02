from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from uuid import uuid4

from config import OSM_USER_AGENT, OVERPASS_URL
from core.geometry import latlon_to_local_m, local_m_to_latlon, polygon_centroid
from core.objects import ShadowObject

_HEIGHT_RE = re.compile(r"[-+]?\d+(?:[\.,]\d+)?")
_EPS = 1e-7


def _height_from_tags(tags: dict) -> float:
    for key in ("height", "building:height", "est_height"):
        value = str(tags.get(key, ""))
        match = _HEIGHT_RE.search(value.replace(",", "."))
        if match:
            return max(1.0, float(match.group(0)))
    for key in ("building:levels", "levels"):
        value = str(tags.get(key, ""))
        match = _HEIGHT_RE.search(value.replace(",", "."))
        if match:
            return max(1.0, float(match.group(0)) * 3.2)
    if tags.get("barrier") in {"wall", "fence", "retaining_wall", "city_wall"}:
        return 2.5
    if tags.get("man_made") in {"tower", "silo", "storage_tank"}:
        return 12.0
    return 9.0


def _name_from_tags(tags: dict) -> str:
    for key in ("name", "building:name", "addr:housename", "operator", "ref"):
        value = str(tags.get(key, "")).strip()
        if value:
            return value
    return ""


def _query(south: float, west: float, north: float, east: float) -> str:
    # Gebäude können in OSM als einfache Ways, Multipolygon-Relationen oder als
    # 3D-Teilflächen building:part modelliert sein. Auf Uni-/Campusflächen sind
    # Bibliotheken und einzelne Einrichtungen aber nicht immer mit building=*,
    # sondern teils nur als amenity=library oder über den Namen erfasst. Diese
    # Flächen werden zusätzlich geladen und später auf sinnvolle Gebäudegrößen
    # begrenzt, damit z. B. Universitätsbibliotheken nicht fehlen.
    return f"""
    [out:json][timeout:60];
    (
      way["building"]({south},{west},{north},{east});
      relation["building"]({south},{west},{north},{east});
      way["building:part"]({south},{west},{north},{east});
      relation["building:part"]({south},{west},{north},{east});
      way["amenity"="library"]({south},{west},{north},{east});
      relation["amenity"="library"]({south},{west},{north},{east});
      way["name"~"Bibliothek|library",i]({south},{west},{north},{east});
      relation["name"~"Bibliothek|library",i]({south},{west},{north},{east});
    );
    out tags geom;
    """


def _object_from_polygon(polygon: list[tuple[float, float]], tags: dict) -> ShadowObject | None:
    if len(polygon) < 2:
        return None
    if len(polygon) == 2:
        origin_lat = sum(p[0] for p in polygon) / 2.0
        origin_lon = sum(p[1] for p in polygon) / 2.0
        footprint = [latlon_to_local_m(lat, lon, origin_lat, origin_lon) for lat, lon in polygon]
        return ShadowObject.from_custom_polygon(origin_lat, origin_lon, footprint, kind_key="building", height_m=_height_from_tags(tags), name=_name_from_tags(tags))
    if _same_point(polygon[0], polygon[-1]):
        polygon = polygon[:-1]
    origin_lat = sum(p[0] for p in polygon) / len(polygon)
    origin_lon = sum(p[1] for p in polygon) / len(polygon)
    local = [latlon_to_local_m(lat, lon, origin_lat, origin_lon) for lat, lon in polygon]
    cx, cy = polygon_centroid(local)
    center_lat, center_lon = local_m_to_latlon(cx, cy, origin_lat, origin_lon)
    footprint = [(x - cx, y - cy) for x, y in local]
    obj = ShadowObject.from_custom_polygon(
        center_lat,
        center_lon,
        footprint,
        kind_key="building",
        height_m=_height_from_tags(tags),
        name=_name_from_tags(tags),
    )
    obj.object_id = uuid4().hex
    return obj




def _polygon_area_local_m2(polygon: list[tuple[float, float]]) -> float:
    if len(polygon) < 3:
        return 0.0
    if _same_point(polygon[0], polygon[-1]):
        polygon = polygon[:-1]
    origin_lat = sum(p[0] for p in polygon) / len(polygon)
    origin_lon = sum(p[1] for p in polygon) / len(polygon)
    local = [latlon_to_local_m(lat, lon, origin_lat, origin_lon) for lat, lon in polygon]
    area = 0.0
    for (x1, y1), (x2, y2) in zip(local, local[1:] + local[:1]):
        area += x1 * y2 - x2 * y1
    return abs(area) * 0.5


def _is_building_like(tags: dict, polygon: list[tuple[float, float]]) -> bool:
    if tags.get("building") or tags.get("building:part"):
        return True
    name = str(tags.get("name", ""))
    is_library = tags.get("amenity") == "library" or re.search(r"bibliothek|library", name, re.I)
    if not is_library:
        return False
    # Amenity-/Namensflächen können auch ganze Campusareale sein. Für den
    # Gebäudeimport nur realistische Gebäudeflächen übernehmen.
    return 10.0 <= _polygon_area_local_m2(polygon) <= 25000.0

def _same_point(a: tuple[float, float], b: tuple[float, float]) -> bool:
    return abs(a[0] - b[0]) <= _EPS and abs(a[1] - b[1]) <= _EPS


def _polygon_from_way(element: dict) -> list[tuple[float, float]]:
    return [(float(p["lat"]), float(p["lon"])) for p in element.get("geometry", []) if "lat" in p and "lon" in p]


def _member_segments(element: dict) -> list[list[tuple[float, float]]]:
    segments: list[list[tuple[float, float]]] = []
    for member in element.get("members", []):
        if member.get("role") not in {"outer", ""}:
            continue
        geom = member.get("geometry", [])
        poly = [(float(p["lat"]), float(p["lon"])) for p in geom if "lat" in p and "lon" in p]
        if len(poly) >= 2:
            segments.append(poly)
    return segments


def _merge_outer_segments(segments: list[list[tuple[float, float]]]) -> list[list[tuple[float, float]]]:
    remaining = [list(seg) for seg in segments if len(seg) >= 2]
    rings: list[list[tuple[float, float]]] = []
    while remaining:
        ring = remaining.pop(0)
        changed = True
        while changed and not _same_point(ring[0], ring[-1]):
            changed = False
            for i, seg in enumerate(remaining):
                if _same_point(ring[-1], seg[0]):
                    ring.extend(seg[1:]); remaining.pop(i); changed = True; break
                if _same_point(ring[-1], seg[-1]):
                    ring.extend(reversed(seg[:-1])); remaining.pop(i); changed = True; break
                if _same_point(ring[0], seg[-1]):
                    ring = seg[:-1] + ring; remaining.pop(i); changed = True; break
                if _same_point(ring[0], seg[0]):
                    ring = list(reversed(seg[1:])) + ring; remaining.pop(i); changed = True; break
        if len(ring) >= 4 and _same_point(ring[0], ring[-1]):
            rings.append(ring)
        elif len(ring) >= 3:
            # Fallback für Relationen, bei denen Overpass bereits eine fast
            # vollständige Außenlinie liefert, aber der letzte Punkt nicht exakt
            # mit dem ersten identisch ist.
            rings.append(ring)
    return rings


def _polygons_from_relation(element: dict) -> list[list[tuple[float, float]]]:
    segments = _member_segments(element)
    direct_rings = [seg for seg in segments if len(seg) >= 4 and _same_point(seg[0], seg[-1])]
    open_segments = [seg for seg in segments if not (len(seg) >= 4 and _same_point(seg[0], seg[-1]))]
    return direct_rings + _merge_outer_segments(open_segments)


def _polygon_key(polygon: list[tuple[float, float]]) -> tuple[tuple[float, float], ...]:
    if polygon and _same_point(polygon[0], polygon[-1]):
        polygon = polygon[:-1]
    return tuple((round(lat, 7), round(lon, 7)) for lat, lon in polygon)


def fetch_buildings_for_bbox(south: float, west: float, north: float, east: float, limit: int = 500) -> list[ShadowObject]:
    data = urllib.parse.urlencode({"data": _query(south, west, north, east)}).encode("utf-8")
    request = urllib.request.Request(
        OVERPASS_URL,
        data=data,
        headers={"User-Agent": OSM_USER_AGENT, "Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        payload = json.loads(response.read().decode("utf-8"))
    objects: list[ShadowObject] = []
    seen: set[tuple[tuple[float, float], ...]] = set()
    for element in payload.get("elements", []):
        tags = element.get("tags", {})
        candidates = [_polygon_from_way(element)] if element.get("type") == "way" else _polygons_from_relation(element)
        for polygon in candidates:
            if not _is_building_like(tags, polygon):
                continue
            key = _polygon_key(polygon)
            if not key or key in seen:
                continue
            seen.add(key)
            obj = _object_from_polygon(polygon, tags)
            if obj is not None:
                objects.append(obj)
            if len(objects) >= limit:
                return objects
    return objects
