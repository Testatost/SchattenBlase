from __future__ import annotations

import gzip
import math
import re
import urllib.error
import urllib.request
import zlib
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from config import APP_DATA_DIR, OSM_USER_AGENT
from core.geometry import latlon_to_local_m, local_m_to_latlon, polygon_centroid
from core.objects import ShadowObject

STREETS_GL_TILE_URL = "https://tiles.streets.gl/vector/{z}/{x}/{y}"
STREETS_GL_TILE_URLS = (
    "https://tiles.streets.gl/vector/{z}/{x}/{y}",
    "https://tiles.streets.gl/vector/{z}/{x}/{y}.pbf",
    "https://tiles.streets.gl/vector/{z}/{x}/{y}.mvt",
)
# Streets GL arbeitet intern mit einer festen Kachelgröße, die dem Slippy-
# Zoom 16 entspricht. Manche Server-/Mirror-Setups liefern dennoch nur eine
# Teilmenge; deshalb wird unten auf weitere Zoomstufen zurückgefallen.
STREETS_GL_ZOOMS = (16, 15, 14)
STREETS_GL_ZOOM = 16
MAX_VECTOR_TILES = 80
# Import-Limits: Die Qt-2D/Pseudo-3D-Ansicht rendert jedes Objekt einzeln.
# Streets-GL-Kacheln enthalten oft sehr viele Nebenobjekte. Ohne Begrenzung
# wird die Ansicht nach dem Import extrem träge.
MAX_IMPORTED_BUILDINGS = 650
MAX_IMPORTED_TREES = 0
MAX_POLYGON_VERTICES = 28
SIMPLIFY_TOLERANCE_M = 0.35
_EPS = 1e-7
_HEIGHT_RE = re.compile(r"[-+]?\d+(?:[\.,]\d+)?")


@dataclass
class _Feature:
    layer: str
    geometry_type: int
    properties: dict
    geometry: list[list[tuple[float, float]]]


class _PbfReader:
    def __init__(self, data: bytes) -> None:
        self.data = data
        self.pos = 0
        self.end = len(data)

    def eof(self) -> bool:
        return self.pos >= self.end

    def read_varint(self) -> int:
        shift = 0
        result = 0
        while self.pos < self.end:
            b = self.data[self.pos]
            self.pos += 1
            result |= (b & 0x7F) << shift
            if not (b & 0x80):
                return result
            shift += 7
            if shift > 70:
                raise ValueError("invalid varint")
        raise ValueError("unexpected end of pbf")

    def read_key(self) -> tuple[int, int]:
        key = self.read_varint()
        return key >> 3, key & 7

    def read_bytes(self) -> bytes:
        length = self.read_varint()
        start = self.pos
        self.pos += length
        if self.pos > self.end:
            raise ValueError("unexpected end of pbf bytes")
        return self.data[start:self.pos]

    def read_fixed32(self) -> int:
        if self.pos + 4 > self.end:
            raise ValueError("unexpected end of fixed32")
        value = int.from_bytes(self.data[self.pos:self.pos + 4], "little", signed=False)
        self.pos += 4
        return value

    def read_fixed64(self) -> int:
        if self.pos + 8 > self.end:
            raise ValueError("unexpected end of fixed64")
        value = int.from_bytes(self.data[self.pos:self.pos + 8], "little", signed=False)
        self.pos += 8
        return value

    def skip(self, wire: int) -> None:
        if wire == 0:
            self.read_varint()
        elif wire == 1:
            self.pos += 8
        elif wire == 2:
            self.pos += self.read_varint()
        elif wire == 5:
            self.pos += 4
        else:
            raise ValueError(f"unsupported pbf wire type {wire}")
        if self.pos > self.end:
            raise ValueError("unexpected end while skipping pbf field")


def _zigzag(value: int) -> int:
    return (value >> 1) ^ (-(value & 1))


def _maybe_decompress(data: bytes) -> bytes:
    if not data:
        return data
    if data[:2] == b"\x1f\x8b":
        return gzip.decompress(data)
    try:
        return zlib.decompress(data)
    except Exception:
        return data


def _parse_value(raw: bytes):
    import struct

    r = _PbfReader(raw)
    value = None
    while not r.eof():
        field, wire = r.read_key()
        if field == 1 and wire == 2:
            value = r.read_bytes().decode("utf-8", "replace")
        elif field == 2 and wire == 5:
            value = struct.unpack("<f", r.read_fixed32().to_bytes(4, "little"))[0]
        elif field == 3 and wire == 1:
            value = struct.unpack("<d", r.read_fixed64().to_bytes(8, "little"))[0]
        elif field == 4 and wire == 0:
            value = int(r.read_varint())
        elif field == 5 and wire == 0:
            value = int(r.read_varint())
        elif field == 6 and wire == 0:
            value = _zigzag(r.read_varint())
        elif field == 7 and wire == 0:
            value = bool(r.read_varint())
        else:
            r.skip(wire)
    return value


def _parse_feature(raw: bytes) -> dict:
    r = _PbfReader(raw)
    feature = {"id": None, "tags": [], "type": 0, "geometry": []}
    while not r.eof():
        field, wire = r.read_key()
        if field == 1 and wire == 0:
            feature["id"] = r.read_varint()
        elif field == 2 and wire == 2:
            sub = _PbfReader(r.read_bytes())
            while not sub.eof():
                feature["tags"].append(sub.read_varint())
        elif field == 3 and wire == 0:
            feature["type"] = r.read_varint()
        elif field == 4 and wire == 2:
            sub = _PbfReader(r.read_bytes())
            while not sub.eof():
                feature["geometry"].append(sub.read_varint())
        else:
            r.skip(wire)
    return feature


def _parse_layer(raw: bytes) -> dict:
    r = _PbfReader(raw)
    layer = {"name": "", "features": [], "keys": [], "values": [], "extent": 4096, "version": 2}
    while not r.eof():
        field, wire = r.read_key()
        if field == 1 and wire == 2:
            layer["name"] = r.read_bytes().decode("utf-8", "replace")
        elif field == 2 and wire == 2:
            layer["features"].append(_parse_feature(r.read_bytes()))
        elif field == 3 and wire == 2:
            layer["keys"].append(r.read_bytes().decode("utf-8", "replace"))
        elif field == 4 and wire == 2:
            layer["values"].append(_parse_value(r.read_bytes()))
        elif field == 5 and wire == 0:
            layer["extent"] = r.read_varint()
        elif field == 15 and wire == 0:
            layer["version"] = r.read_varint()
        else:
            r.skip(wire)
    return layer


def _decode_geometry(values: list[int]) -> list[list[tuple[int, int]]]:
    rings: list[list[tuple[int, int]]] = []
    current: list[tuple[int, int]] = []
    x = 0
    y = 0
    i = 0
    while i < len(values):
        cmd_int = values[i]
        i += 1
        command = cmd_int & 0x7
        count = cmd_int >> 3
        if command in (1, 2):  # MoveTo, LineTo
            if command == 1 and current:
                rings.append(current)
                current = []
            for _ in range(count):
                if i + 1 >= len(values):
                    return rings
                x += _zigzag(values[i])
                y += _zigzag(values[i + 1])
                i += 2
                current.append((x, y))
        elif command == 7:  # ClosePath
            for _ in range(count):
                if current and current[0] != current[-1]:
                    current.append(current[0])
                if current:
                    rings.append(current)
                    current = []
        else:
            break
    if current:
        rings.append(current)
    return rings


def _tile_to_latlon(z: int, x: int, y: int, gx: float, gy: float, extent: int) -> tuple[float, float]:
    n = 2 ** z
    lon = (x + gx / extent) / n * 360.0 - 180.0
    merc = math.pi * (1.0 - 2.0 * (y + gy / extent) / n)
    lat = math.degrees(math.atan(math.sinh(merc)))
    return lat, lon


def _latlon_to_tile(lat: float, lon: float, zoom: int) -> tuple[int, int]:
    lat = max(min(lat, 85.05112878), -85.05112878)
    n = 2 ** zoom
    x = int((lon + 180.0) / 360.0 * n)
    y = int((1.0 - math.log(math.tan(math.radians(lat)) + 1.0 / math.cos(math.radians(lat))) / math.pi) / 2.0 * n)
    return max(0, min(n - 1, x)), max(0, min(n - 1, y))


def _feature_properties(feature: dict, keys: list[str], values: list) -> dict:
    props: dict = {}
    tags = feature.get("tags", [])
    for i in range(0, len(tags) - 1, 2):
        k_i = tags[i]
        v_i = tags[i + 1]
        if 0 <= k_i < len(keys) and 0 <= v_i < len(values):
            props[str(keys[k_i])] = values[v_i]
    return props


def _parse_vector_tile(data: bytes, z: int, x: int, y: int) -> list[_Feature]:
    data = _maybe_decompress(data)
    r = _PbfReader(data)
    out: list[_Feature] = []
    while not r.eof():
        field, wire = r.read_key()
        if field != 3 or wire != 2:
            r.skip(wire)
            continue
        layer = _parse_layer(r.read_bytes())
        name = str(layer.get("name", ""))
        keys = layer.get("keys", [])
        values = layer.get("values", [])
        extent = int(layer.get("extent", 4096) or 4096)
        for feature in layer.get("features", []):
            geom_type = int(feature.get("type", 0) or 0)
            rings_int = _decode_geometry(feature.get("geometry", []))
            rings = [
                [_tile_to_latlon(z, x, y, px, py, extent) for px, py in ring]
                for ring in rings_int
                if len(ring) >= 1
            ]
            if rings:
                out.append(_Feature(name, geom_type, _feature_properties(feature, keys, values), rings))
    return out


def _normalize_key(name: str) -> str:
    # Streets GL/Planetiler nutzt teils camelCase (minHeight, roofColor),
    # klassische OSM-Tags nutzen Doppelpunkte (building:levels). Für den
    # Import werden beide Formen auf denselben Vergleichsschlüssel reduziert.
    name = re.sub(r"(?<!^)(?=[A-Z])", "_", str(name)).lower()
    return re.sub(r"[^a-z0-9]+", "", name)


def _get_ci(props: dict, *names: str):
    lookup = {_normalize_key(k): v for k, v in props.items()}
    for name in names:
        key = _normalize_key(name)
        if key in lookup:
            return lookup[key]
    return None


def _float_from_value(value, default: float | None = None) -> float | None:
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return float(value)
    match = _HEIGHT_RE.search(str(value).replace(",", "."))
    if match:
        return float(match.group(0))
    return default


def _is_truthy(value) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y", "ja"}


def _height_from_props(props: dict) -> float:
    # In OpenMapTiles-/Planetiler-Kacheln steht bei 3D-Gebäuden häufig
    # render_height statt height. Streets GL selbst verwendet dagegen u. a.
    # height/minHeight/levels/roofHeight. Schattenblase kennt keine schwebenden
    # Bauteile; deshalb wird jeweils die sichtbare Körperhöhe übernommen.
    render_height = _float_from_value(_get_ci(props, "render_height", "renderHeight"))
    if render_height is not None:
        min_height = _float_from_value(_get_ci(props, "render_min_height", "renderMinHeight", "min_height", "minHeight", "building:min_level", "minLevel"), 0.0) or 0.0
        if _get_ci(props, "building:min_level", "minLevel") is not None and _get_ci(props, "min_height", "minHeight", "render_min_height", "renderMinHeight") is None:
            min_height *= 3.2
        return max(1.0, render_height - min_height)

    total_height = _float_from_value(_get_ci(props, "height", "building:height", "building_height", "buildingHeight", "est_height"))
    min_height = _float_from_value(_get_ci(props, "min_height", "minHeight", "building:min_height", "buildingMinHeight"), 0.0) or 0.0
    if total_height is not None:
        return max(1.0, total_height - min_height)

    levels = _float_from_value(_get_ci(props, "building:levels", "levels", "building_levels", "buildingLevels"))
    min_level = _float_from_value(_get_ci(props, "building:min_level", "minLevel", "buildingMinLevel"), 0.0) or 0.0
    roof_height = _float_from_value(_get_ci(props, "roof:height", "roofHeight", "buildingRoofHeight"), 0.0) or 0.0
    if levels is not None:
        usable_levels = max(0.0, levels - min_level)
        # Streets GL nutzt 4 m als Etagen-Fallback; das passt besser zu dessen
        # Kachelparametern als der niedrigere klassische OSM-Fallback.
        return max(1.0, usable_levels * 4.0 + roof_height)
    if roof_height > 0:
        return max(1.0, roof_height)
    return 9.0


def _name_from_props(props: dict) -> str:
    for key in ("name", "label", "name:de", "building:name", "addr:housename", "operator", "ref"):
        value = _get_ci(props, key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _looks_like_building(layer: str, props: dict) -> bool:
    if _is_truthy(_get_ci(props, "hide_3d", "hide3d")):
        return False
    layer_l = layer.lower()
    if any(token in layer_l for token in ("building", "building_part", "building-part", "indoor")):
        return True
    keys = {_normalize_key(k) for k in props.keys()}
    if any(k in keys for k in (
        "building", "buildingpart", "buildinglevels", "buildingheight",
        "renderheight", "height", "minheight", "buildingminheight",
        "roofshape", "roofheight", "roofcolour", "roofcolor",
        "buildingtype", "ispart"
    )):
        return True
    kind = str(_get_ci(props, "kind", "class", "type", "feature", "subclass") or "").lower()
    return "building" in kind


def _looks_like_tree(layer: str, props: dict, geom_type: int) -> bool:
    layer_l = layer.lower()
    if geom_type != 1:
        return False
    if "tree" in layer_l:
        return True
    natural = str(_get_ci(props, "natural") or "").lower()
    typ = str(_get_ci(props, "type", "kind", "class") or "").lower()
    return natural == "tree" or typ in {"tree", "tree_row"}


def _same_point(a: tuple[float, float], b: tuple[float, float]) -> bool:
    return abs(a[0] - b[0]) <= _EPS and abs(a[1] - b[1]) <= _EPS


def _polygon_bounds_latlon(polygon: list[tuple[float, float]]) -> tuple[float, float, float, float]:
    lats = [p[0] for p in polygon]
    lons = [p[1] for p in polygon]
    return min(lats), min(lons), max(lats), max(lons)


def _bounds_intersect(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> bool:
    south_a, west_a, north_a, east_a = a
    south_b, west_b, north_b, east_b = b
    return not (east_a < west_b or east_b < west_a or north_a < south_b or north_b < south_a)


def _perpendicular_distance(point: tuple[float, float], start: tuple[float, float], end: tuple[float, float]) -> float:
    px, py = point
    sx, sy = start
    ex, ey = end
    dx = ex - sx
    dy = ey - sy
    if abs(dx) < 1e-12 and abs(dy) < 1e-12:
        return math.hypot(px - sx, py - sy)
    return abs(dy * px - dx * py + ex * sy - ey * sx) / math.hypot(dx, dy)


def _rdp(points: list[tuple[float, float]], tolerance: float) -> list[tuple[float, float]]:
    if len(points) <= 3:
        return points
    start = points[0]
    end = points[-1]
    max_dist = -1.0
    index = 0
    for i in range(1, len(points) - 1):
        dist = _perpendicular_distance(points[i], start, end)
        if dist > max_dist:
            index = i
            max_dist = dist
    if max_dist > tolerance:
        left = _rdp(points[:index + 1], tolerance)
        right = _rdp(points[index:], tolerance)
        return left[:-1] + right
    return [start, end]


def _simplify_local_polygon(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    if len(points) <= MAX_POLYGON_VERTICES:
        return points
    closed = points + [points[0]]
    simplified = _rdp(closed, SIMPLIFY_TOLERANCE_M)[:-1]
    if len(simplified) < 3:
        simplified = points
    if len(simplified) > MAX_POLYGON_VERTICES:
        step = len(simplified) / MAX_POLYGON_VERTICES
        simplified = [simplified[int(i * step)] for i in range(MAX_POLYGON_VERTICES)]
    return simplified


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


def _color_from_props(props: dict) -> str:
    value = _get_ci(props, "building:colour", "building:color", "buildingColor", "colour", "color")
    if value is None or not str(value).strip():
        return ""
    if isinstance(value, int):
        return f"#{value & 0xFFFFFF:06x}"
    color = str(value).strip()
    named = {
        "white": "#d8d4c8", "grey": "#9b9b92", "gray": "#9b9b92",
        "brown": "#8b6f55", "red": "#9c5b50", "yellow": "#b6a36b",
        "brick": "#8a5a4b", "beige": "#b8aa95", "concrete": "#9c9a90",
    }
    if color.lower() in named:
        return named[color.lower()]
    if color.startswith("#") and len(color) in {4, 7}:
        return color
    try:
        return f"#{int(color) & 0xFFFFFF:06x}"
    except Exception:
        return ""


def _object_from_polygon(polygon: list[tuple[float, float]], props: dict) -> ShadowObject | None:
    if len(polygon) < 3:
        return None
    if _same_point(polygon[0], polygon[-1]):
        polygon = polygon[:-1]
    if len(polygon) < 3:
        return None

    origin_lat = sum(p[0] for p in polygon) / len(polygon)
    origin_lon = sum(p[1] for p in polygon) / len(polygon)
    local = [latlon_to_local_m(lat, lon, origin_lat, origin_lon) for lat, lon in polygon]

    area = 0.0
    for (x1, y1), (x2, y2) in zip(local, local[1:] + local[:1]):
        area += x1 * y2 - x2 * y1
    area = abs(area) * 0.5
    if area < 2.0 or area > 200000.0:
        return None

    cx, cy = polygon_centroid(local)
    center_lat, center_lon = local_m_to_latlon(cx, cy, origin_lat, origin_lon)
    footprint = _simplify_local_polygon([(x - cx, y - cy) for x, y in local])
    obj = ShadowObject.from_custom_polygon(center_lat, center_lon, footprint, kind_key="building", height_m=_height_from_props(props), name=_name_from_props(props))
    color = _color_from_props(props)
    if color:
        obj.color = color
    obj.object_id = uuid4().hex
    return obj

def _object_from_point(point: tuple[float, float], props: dict) -> ShadowObject:
    leaf = str(_get_ci(props, "leaf_type", "leaf:type", "taxon", "species", "type", "kind") or "").lower()
    kind_key = "conifer_1" if any(token in leaf for token in ("needle", "conifer", "spruce", "pine", "fir", "nadel")) else "broadleaf_1"
    obj = ShadowObject.from_kind(kind_key, point[0], point[1])
    height = _float_from_value(_get_ci(props, "height"))
    if height is not None:
        obj.height_m = max(1.0, height)
        obj.crown_height_m = max(1.0, obj.height_m * 0.55)
        obj.crown_width_m = max(1.0, obj.width_m)
    name = _name_from_props(props)
    if name:
        obj.name = name
    return obj


def _polygon_key(polygon: list[tuple[float, float]]) -> tuple[tuple[float, float], ...]:
    if polygon and _same_point(polygon[0], polygon[-1]):
        polygon = polygon[:-1]
    return tuple((round(lat, 7), round(lon, 7)) for lat, lon in polygon)


def _tile_cache_path(z: int, x: int, y: int) -> Path:
    return APP_DATA_DIR / "streets_gl_tiles" / str(z) / str(x) / f"{y}.pbf"


def _load_tile(z: int, x: int, y: int) -> bytes:
    cache = _tile_cache_path(z, x, y)
    if cache.exists() and cache.stat().st_size > 0:
        return cache.read_bytes()
    last_error: Exception | None = None
    for template in STREETS_GL_TILE_URLS:
        url = template.format(z=z, x=x, y=y)
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": OSM_USER_AGENT,
                "Accept": "application/x-protobuf,application/vnd.mapbox-vector-tile,application/octet-stream,*/*",
                "Accept-Encoding": "gzip, deflate, identity",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=25) as response:
                data = response.read()
            if data:
                cache.parent.mkdir(parents=True, exist_ok=True)
                cache.write_bytes(data)
                return data
        except Exception as exc:
            last_error = exc
            continue
    if last_error is not None:
        raise last_error
    return b""


def _tile_ranges(south: float, west: float, north: float, east: float, zoom: int) -> tuple[range, range]:
    x1, y1 = _latlon_to_tile(north, west, zoom)
    x2, y2 = _latlon_to_tile(south, east, zoom)
    return range(min(x1, x2), max(x1, x2) + 1), range(min(y1, y2), max(y1, y2) + 1)


def fetch_streetsgl_3d_for_bbox(south: float, west: float, north: float, east: float, limit: int = MAX_IMPORTED_BUILDINGS) -> list[ShadowObject]:
    """Importiert 3D-nahe Objekte aus Streets-GL-Vektorkacheln.

    Streets GL rendert keine fertigen Mesh-Dateien aus, sondern erzeugt seine
    Geometrie zur Laufzeit aus OSM-Vektorkacheln. Diese Funktion liest deshalb
    die Kacheln direkt, übernimmt Gebäude-/building:part-Geometrien, Höhen,
    Namen und einfache Baum-Punkte und wandelt sie in bearbeitbare
    Schattenblase-Objekte um.
    """
    objects: list[ShadowObject] = []
    seen_polygons: set[tuple[tuple[float, float], ...]] = set()
    seen_points: set[tuple[float, float]] = set()
    last_error: Exception | None = None
    query_bounds = (south, west, north, east)
    building_count = 0
    tree_count = 0

    for zoom in STREETS_GL_ZOOMS:
        xs, ys = _tile_ranges(south, west, north, east, zoom)
        tile_count = len(xs) * len(ys)
        if tile_count > MAX_VECTOR_TILES:
            last_error = ValueError(f"{tile_count} Streets-GL-Kacheln bei Zoom {zoom}")
            continue

        for x in xs:
            for y in ys:
                try:
                    features = _parse_vector_tile(_load_tile(zoom, x, y), zoom, x, y)
                except urllib.error.HTTPError as exc:
                    if exc.code in {204, 404}:
                        continue
                    last_error = exc
                    continue
                except Exception as exc:
                    last_error = exc
                    continue

                for feature in features:
                    if feature.geometry_type == 3 and _looks_like_building(feature.layer, feature.properties):
                        if building_count >= limit:
                            continue
                        for ring in feature.geometry:
                            if len(ring) < 4:
                                continue
                            if not _bounds_intersect(_polygon_bounds_latlon(ring), query_bounds):
                                continue
                            key = _polygon_key(ring)
                            if not key or key in seen_polygons:
                                continue
                            seen_polygons.add(key)
                            obj = _object_from_polygon(ring, feature.properties)
                            if obj is not None:
                                objects.append(obj)
                                building_count += 1
                    elif MAX_IMPORTED_TREES > 0 and feature.geometry_type == 1 and _looks_like_tree(feature.layer, feature.properties, feature.geometry_type):
                        if tree_count >= MAX_IMPORTED_TREES:
                            continue
                        point = feature.geometry[0][0]
                        if not (south <= point[0] <= north and west <= point[1] <= east):
                            continue
                        key = (round(point[0], 7), round(point[1], 7))
                        if key in seen_points:
                            continue
                        seen_points.add(key)
                        objects.append(_object_from_point(point, feature.properties))
                        tree_count += 1

                    if building_count >= limit and tree_count >= MAX_IMPORTED_TREES:
                        return objects

        if objects:
            return objects

    if last_error is not None and not objects:
        raise last_error
    return objects
