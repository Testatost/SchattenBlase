from __future__ import annotations

from math import cos, pi, radians, sin, sqrt, tan

from core.geometry import (
    azimuth_vector,
    bbox_size,
    convex_hull,
    latlon_to_local_m,
    local_m_to_latlon,
    point_in_polygon,
    polygon_area_m2,
    rotate_points,
)
from core.objects import ShadowObject, TREE_KINDS

try:
    from shapely.geometry import Polygon
    from shapely.ops import unary_union
except Exception:  # pragma: no cover - optional speed/precision dependency
    Polygon = None
    unary_union = None


def _crown_radius(shape: str, angle: float) -> float:
    # Nur dezente Abweichungen, damit Kronen beim Bearbeiten stabil bleiben.
    if shape == "broadleaf_1":
        return 1.0 + 0.035 * sin(5.0 * angle) + 0.025 * cos(7.0 * angle)
    if shape == "broadleaf_2":
        return 1.0 + 0.025 * sin(4.0 * angle) + 0.020 * cos(6.0 * angle)
    if shape == "broadleaf_3":
        return 1.0 + 0.045 * sin(6.0 * angle) - 0.030 * cos(2.0 * angle)
    if shape in {"conifer_1", "conifer_2", "conifer_3"}:
        return 0.99 + 0.018 * sin(8.0 * angle)
    return 1.0


def _tree_layer_radius(shape: str, t: float) -> float:
    if shape == "conifer_1":
        return max(0.02, (1.0 - t) ** 0.72)
    if shape == "conifer_2":
        return max(0.015, (1.0 - t) ** 0.58)
    if shape == "conifer_3":
        # Kompakte, aber klar nadelbaumartige kegelige Krone.
        return max(0.025, (1.0 - t) ** 0.88) * (0.98 + 0.04 * sin(5.0 * pi * t))
    if shape == "broadleaf_1":
        return max(0.05, sin(pi * t) ** 0.44)
    if shape == "broadleaf_2":
        return max(0.04, sin(pi * min(t * 0.92 + 0.04, 1.0)) ** 0.54) * (0.82 + 0.25 * t)
    if shape == "broadleaf_3":
        return max(0.08, sin(pi * min(t * 0.88 + 0.06, 1.0)) ** 0.34) * (1.16 - 0.28 * t)
    return max(0.04, sin(pi * t) ** 0.45)


def tree_layer_points(width_m: float, shape: str, t: float, count: int = 56) -> list[tuple[float, float]]:
    radius = width_m * 0.5 * _tree_layer_radius(shape, t)
    y_scale = 1.18 if shape == "broadleaf_2" else (1.10 if shape == "broadleaf_3" else 1.0)
    x_scale = 0.82 if shape == "broadleaf_2" else 1.0
    points: list[tuple[float, float]] = []
    for i in range(count):
        angle = 2.0 * pi * i / count
        r = radius * _crown_radius(shape, angle)
        points.append((r * cos(angle) * x_scale, r * sin(angle) * y_scale))
    if not points:
        return points
    # Irreguläre Kronenformen dürfen organisch wirken, sollen aber nicht vom
    # Stammzentrum wegdriften. Deshalb wird jede Ebene wieder um das Zentrum
    # ihrer Hüllbox auf (0/0) gesetzt.
    min_x = min(x for x, _ in points); max_x = max(x for x, _ in points)
    min_y = min(y for _, y in points); max_y = max(y for _, y in points)
    cx = (min_x + max_x) * 0.5; cy = (min_y + max_y) * 0.5
    return [(x - cx, y - cy) for x, y in points]


def _tree_base_outline(obj: ShadowObject, shape: str, t: float) -> list[tuple[float, float]]:
    width = max(obj.crown_width_m or obj.width_m, 0.2)
    if len(obj.footprint_m) >= 3:
        pts = list(obj.footprint_m)
        xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
        cx = (min(xs) + max(xs)) * 0.5; cy = (min(ys) + max(ys)) * 0.5
        scale = _tree_layer_radius(shape, t) / max(_tree_layer_radius(shape, 0.5), 0.001)
        return [(cx + (x - cx) * scale, cy + (y - cy) * scale) for x, y in pts]
    return tree_layer_points(width, shape, t)


def tree_crown_layers_local_m(obj: ShadowObject) -> list[tuple[float, list[tuple[float, float]]]]:
    kind = TREE_KINDS.get(obj.kind_key, TREE_KINDS["custom"])
    if not obj.is_tree():
        return []
    crown_height = min(max(obj.crown_height_m or obj.height_m * 0.65, 0.1), obj.height_m)
    crown_bottom = max(0.0, obj.height_m - crown_height)
    ts = [i / 18.0 for i in range(0, 19)] if kind.crown_shape in {"conifer_1", "conifer_2", "conifer_3"} else [0.05, 0.14, 0.25, 0.38, 0.52, 0.66, 0.80, 0.92, 0.98]
    layers = []
    for t in ts:
        z = crown_bottom + crown_height * t
        layers.append((z, rotate_points(_tree_base_outline(obj, kind.crown_shape, t), obj.orientation_deg + obj.rotation_z_deg)))
    return layers


def _regular_points(width_m: float, depth_m: float | None = None, count: int = 40) -> list[tuple[float, float]]:
    rx = max(width_m, 0.2) * 0.5
    ry = max(depth_m if depth_m is not None else width_m, 0.2) * 0.5
    return [(rx * cos(2.0 * pi * i / count), ry * sin(2.0 * pi * i / count)) for i in range(count)]


def _geometry_footprint(obj: ShadowObject) -> list[tuple[float, float]]:
    kind = TREE_KINDS.get(obj.kind_key, TREE_KINDS["custom"])
    if kind.crown_shape in {"sphere", "cylinder", "cone"}:
        return _regular_points(obj.width_m, obj.depth_m or obj.width_m, 48)
    if kind.crown_shape == "pyramid":
        w = max(obj.width_m, 0.2) * 0.5
        d = max(obj.depth_m or obj.width_m, 0.2) * 0.5
        return [(-w, -d), (w, -d), (w, d), (-w, d)]
    if kind.crown_shape == "plane":
        w = max(obj.width_m, 0.2) * 0.5
        d = max(obj.depth_m or 0.10, 0.02) * 0.5
        return [(-w, -d), (w, -d), (w, d), (-w, d)]
    return []


def _scaled_custom_footprint(obj: ShadowObject) -> list[tuple[float, float]]:
    kind = TREE_KINDS.get(obj.kind_key, TREE_KINDS["custom"])
    if kind.crown_shape in {"sphere", "cylinder", "cone"}:
        return _geometry_footprint(obj)
    if kind.crown_shape == "box":
        w = max(obj.width_m, 0.1) * 0.5
        d = max(obj.depth_m or obj.width_m, 0.1) * 0.5
        return [(-w, -d), (w, -d), (w, d), (-w, d)]
    if not obj.footprint_m:
        return _geometry_footprint(obj) or tree_layer_points(obj.width_m, "broad", 0.5)
    if obj.is_plane():
        length = sqrt((obj.footprint_m[1][0] - obj.footprint_m[0][0]) ** 2 + (obj.footprint_m[1][1] - obj.footprint_m[0][1]) ** 2)
        scale = obj.width_m / max(length, 0.001) if obj.width_m > 0.0 else 1.0
        return [(x * scale, y * scale) for x, y in obj.footprint_m]
    width, depth = bbox_size(obj.footprint_m)
    sx = (obj.width_m / max(width, 0.001)) if obj.width_m > 0.0 else 1.0
    sy = ((obj.depth_m or depth) / max(depth, 0.001)) if depth > 0.0 else sx
    return [(x * sx, y * sy) for x, y in obj.footprint_m]


def object_footprint_local_m(obj: ShadowObject) -> list[tuple[float, float]]:
    if obj.is_tree():
        kind = TREE_KINDS.get(obj.kind_key, TREE_KINDS["custom"])
        return rotate_points(_tree_base_outline(obj, kind.crown_shape, 0.5), obj.orientation_deg + obj.rotation_z_deg)
    return rotate_points(_scaled_custom_footprint(obj), obj.orientation_deg + obj.rotation_z_deg)


def object_footprint_latlon(obj: ShadowObject) -> list[tuple[float, float]]:
    return [local_m_to_latlon(x, y, obj.lat, obj.lon) for x, y in object_footprint_local_m(obj)]


def object_ground_contact_local_m(obj: ShadowObject) -> list[tuple[float, float]]:
    if obj.is_tree():
        radius = max(0.03, obj.trunk_diameter_m * 0.5)
        if obj.trunk_diameter_m <= 0.0:
            return []
        return tree_layer_points(radius * 2.0, "broad", 0.5, 24)
    return object_footprint_local_m(obj)


def _trunk_layers(obj: ShadowObject) -> list[tuple[float, list[tuple[float, float]]]]:
    if not obj.is_tree() or obj.trunk_diameter_m <= 0.0:
        return []
    radius = max(0.03, obj.trunk_diameter_m * 0.5)
    top = max(0.2, obj.height_m - max(obj.crown_height_m, obj.height_m * 0.55))
    pts = tree_layer_points(radius * 2.0, "broad", 0.5, 24)
    return [(0.0, pts), (top, pts)]


def object_body_layers_local_m(obj: ShadowObject) -> list[tuple[float, list[tuple[float, float]]]]:
    if obj.is_tree():
        return _trunk_layers(obj) + tree_crown_layers_local_m(obj)
    kind = TREE_KINDS.get(obj.kind_key, TREE_KINDS["custom"])
    base = object_footprint_local_m(obj)
    if kind.crown_shape == "sphere":
        layers = []
        base = _regular_points(obj.width_m, obj.depth_m or obj.width_m, 72)
        # Ellipsoid/Kugel mit glatter Kontur. Unterseite berührt die Ebene bei
        # z=0, der maximale Durchmesser liegt auf halber Höhe.
        for t in [0.02, 0.06, 0.12, 0.20, 0.30, 0.40, 0.50, 0.60, 0.70, 0.80, 0.88, 0.94, 0.98]:
            r = max(0.02, sin(pi * t))
            z = max(obj.height_m, 0.1) * t
            layers.append((z, [(x * r, y * r) for x, y in base]))
        return layers
    if kind.crown_shape in {"cone", "pyramid"}:
        return [(0.0, base), (obj.height_m, [(0.0, 0.0) for _ in base])]
    return [(0.0, base), (obj.height_m, base)]


def _project_shadow_layer(obj: ShadowObject, z: float, footprint: list[tuple[float, float]], away_x: float, away_y: float, tan_alt: float) -> list[tuple[float, float]]:
    tilt_x, tilt_y = azimuth_vector(obj.orientation_deg)
    tilt = radians(obj.tilt_deg + obj.rotation_x_deg)
    vertical = max(0.0, z * cos(tilt))
    shadow_length = vertical / tan_alt
    # Neigung reduziert nur die wirksame senkrechte Höhe. Die Bodenfläche des
    # Körpers wird dadurch nicht seitlich aufgebläht.
    shift_x = away_x * shadow_length
    shift_y = away_y * shadow_length
    return [(x + shift_x, y + shift_y) for x, y in footprint]


def _union_parts_to_polygons(parts: list[list[tuple[float, float]]]) -> list[list[tuple[float, float]]]:
    valid = [p for p in parts if len(p) >= 3]
    if not valid:
        return []
    if Polygon is None or unary_union is None:
        return [convex_hull([pt for poly in valid for pt in poly])]
    geoms = []
    for pts in valid:
        poly = Polygon(pts)
        if not poly.is_valid:
            poly = poly.buffer(0)
        if not poly.is_empty:
            geoms.append(poly)
    if not geoms:
        return []
    geom = unary_union(geoms)
    if hasattr(geom, "simplify"):
        geom = geom.simplify(0.12, preserve_topology=True)
    polys = list(geom.geoms) if hasattr(geom, "geoms") else [geom]
    return [[(float(x), float(y)) for x, y in list(poly.exterior.coords)[:-1]] for poly in polys if not poly.is_empty]


def _connect_projected_layers(pts1: list[tuple[float, float]], pts2: list[tuple[float, float]]) -> list[list[tuple[float, float]]]:
    parts: list[list[tuple[float, float]]] = []
    if len(pts1) == 2 and len(pts2) == 2:
        return [[pts1[0], pts1[1], pts2[1], pts2[0]]]
    if len(pts1) != len(pts2) or len(pts1) < 3:
        return []
    n = len(pts1)
    for i in range(n):
        a = pts1[i]
        b = pts1[(i + 1) % n]
        c = pts2[(i + 1) % n]
        d = pts2[i]
        parts.append([a, b, c, d])
    return parts


def _silhouette_from_layers(obj: ShadowObject, layers: list[tuple[float, list[tuple[float, float]]]], away_x: float, away_y: float, tan_alt: float) -> list[list[tuple[float, float]]]:
    projected = [(z, _project_shadow_layer(obj, z, pts, away_x, away_y, tan_alt)) for z, pts in layers if len(pts) >= 2]
    if not projected:
        return []
    parts: list[list[tuple[float, float]]] = []
    # Nur echte Sweep-Flächen verwenden, keine konvexe Gesamthülle.
    # Die konvexe Hülle erzeugte große Schattenflächen auf der Sonnenseite
    # und bei konkaven Gebäuden falsche Dreiecke.
    for (_z1, pts1), (_z2, pts2) in zip(projected, projected[1:]):
        parts.extend(_connect_projected_layers(pts1, pts2))
        if len(pts2) >= 3:
            parts.append(pts2)
    if len(projected) == 1 and len(projected[0][1]) >= 3:
        parts.append(projected[0][1])
    return parts


def _round_shadow_from_layers(obj: ShadowObject, layers: list[tuple[float, list[tuple[float, float]]]], away_x: float, away_y: float, tan_alt: float) -> list[list[tuple[float, float]]]:
    # Runde Körper (Baumkrone, Busch, Zylinder, Kugel) brauchen eine glatte
    # Silhouette. Die Sweep-Flächen jeder einzelnen Kante erzeugen bei
    # ringförmigen Körpern sonst Dreiecke oder sägezahnartige Schatten.
    all_pts: list[tuple[float, float]] = []
    for z, pts in layers:
        if len(pts) >= 2:
            all_pts.extend(_project_shadow_layer(obj, z, pts, away_x, away_y, tan_alt))
    if len(all_pts) < 3:
        return []
    hull = convex_hull(all_pts)
    return [hull] if len(hull) >= 3 else []


def _sphere_shadow(obj: ShadowObject, away_x: float, away_y: float, tan_alt: float) -> list[list[tuple[float, float]]]:
    # Schatten einer Kugel/Ellipsoid als Silhouette vieler projizierter
    # Oberflächenpunkte. Das verhindert dreieckige Schatten von Ring-Layern.
    rx = max(obj.width_m, 0.2) * 0.5
    ry = max(obj.depth_m or obj.width_m, 0.2) * 0.5
    rz = max(obj.height_m, 0.1) * 0.5
    pts: list[tuple[float, float]] = []
    for j in range(0, 19):
        phi = -pi * 0.5 + pi * j / 18.0
        cp = cos(phi)
        z = rz + rz * sin(phi)
        scale = z / tan_alt
        for i in range(72):
            a = 2.0 * pi * i / 72.0
            x = rx * cp * cos(a)
            y = ry * cp * sin(a)
            pts.append((x + away_x * scale, y + away_y * scale))
    hull = convex_hull(pts)
    return [hull] if len(hull) >= 3 else []


def _shadow_for_round_geometry(obj: ShadowObject, away_x: float, away_y: float, tan_alt: float) -> list[list[tuple[float, float]]]:
    kind = TREE_KINDS.get(obj.kind_key, TREE_KINDS["custom"])
    layers = object_body_layers_local_m(obj)
    if kind.crown_shape == "sphere":
        return _sphere_shadow(obj, away_x, away_y, tan_alt)
    if kind.crown_shape == "cylinder":
        return _round_shadow_from_layers(obj, layers, away_x, away_y, tan_alt)
    if kind.crown_shape == "cone":
        # Kegel: runde Basis plus Spitze ergibt eine glatte Tropfenform statt
        # vieler einzelner Kantendreiecke.
        return _round_shadow_from_layers(obj, layers, away_x, away_y, tan_alt)
    return _union_parts_to_polygons(_silhouette_from_layers(obj, layers, away_x, away_y, tan_alt))


def shadow_polygons_local_m(obj: ShadowObject, sun_azimuth_deg: float, sun_altitude_deg: float) -> list[list[tuple[float, float]]]:
    if sun_altitude_deg <= 0.0 or obj.height_m <= 0.0 or obj.width_m <= 0.0:
        return []
    away_x, away_y = azimuth_vector((sun_azimuth_deg + 180.0) % 360.0)
    tan_alt = max(0.05, tan(radians(sun_altitude_deg)))
    kind = TREE_KINDS.get(obj.kind_key, TREE_KINDS["custom"])
    if obj.is_tree():
        parts: list[list[tuple[float, float]]] = []
        parts.extend(_round_shadow_from_layers(obj, _trunk_layers(obj), away_x, away_y, tan_alt))
        parts.extend(_round_shadow_from_layers(obj, tree_crown_layers_local_m(obj), away_x, away_y, tan_alt))
        return _union_parts_to_polygons(parts)
    if kind.crown_shape in {"sphere", "cylinder", "cone"}:
        return _shadow_for_round_geometry(obj, away_x, away_y, tan_alt)
    return _union_parts_to_polygons(_silhouette_from_layers(obj, object_body_layers_local_m(obj), away_x, away_y, tan_alt))


def shadow_polygon_local_m(obj: ShadowObject, sun_azimuth_deg: float, sun_altitude_deg: float) -> list[tuple[float, float]]:
    polys = shadow_polygons_local_m(obj, sun_azimuth_deg, sun_altitude_deg)
    if not polys:
        return []
    if len(polys) == 1:
        return polys[0]
    return convex_hull([pt for poly in polys for pt in poly])


def shadow_polygons_world_m(obj: ShadowObject, origin_lat: float, origin_lon: float, sun_azimuth_deg: float, sun_altitude_deg: float) -> list[list[tuple[float, float]]]:
    cx, cy = latlon_to_local_m(obj.lat, obj.lon, origin_lat, origin_lon)
    return [[(x + cx, y + cy) for x, y in poly] for poly in shadow_polygons_local_m(obj, sun_azimuth_deg, sun_altitude_deg)]


def shadow_polygon_world_m(obj: ShadowObject, origin_lat: float, origin_lon: float, sun_azimuth_deg: float, sun_altitude_deg: float) -> list[tuple[float, float]]:
    polys = shadow_polygons_world_m(obj, origin_lat, origin_lon, sun_azimuth_deg, sun_altitude_deg)
    return convex_hull([pt for poly in polys for pt in poly]) if len(polys) > 1 else (polys[0] if polys else [])


def shadow_polygon_latlon(obj: ShadowObject, sun_azimuth_deg: float, sun_altitude_deg: float) -> list[tuple[float, float]]:
    local = shadow_polygon_local_m(obj, sun_azimuth_deg, sun_altitude_deg)
    return [local_m_to_latlon(x, y, obj.lat, obj.lon) for x, y in local]


def shadow_area_raw_m2(obj: ShadowObject, sun_azimuth_deg: float, sun_altitude_deg: float) -> float:
    polys = shadow_polygons_local_m(obj, sun_azimuth_deg, sun_altitude_deg)
    exact = _union_area(polys)
    return exact if exact is not None else sum(polygon_area_m2(p) for p in polys)

def shadow_area_m2(obj: ShadowObject, sun_azimuth_deg: float, sun_altitude_deg: float) -> float:
    polys = shadow_polygons_local_m(obj, sun_azimuth_deg, sun_altitude_deg)
    exact = _union_area(polys, subtract=[object_ground_contact_local_m(obj)])
    return exact if exact is not None else sum(polygon_area_m2(p) for p in polys)


def _union_parts_to_area(polys: list[list[tuple[float, float]]]) -> float | None:
    if Polygon is None or unary_union is None:
        return None
    geoms = []
    for pts in polys:
        if len(pts) < 3:
            continue
        poly = Polygon(pts)
        if not poly.is_valid:
            poly = poly.buffer(0)
        if not poly.is_empty:
            geoms.append(poly)
    return float(unary_union(geoms).area) if geoms else 0.0


def _origin_for(objects: list[ShadowObject], ground: list[tuple[float, float]] | None = None) -> tuple[float, float]:
    points = list(ground or [])
    points.extend((o.lat, o.lon) for o in objects)
    if not points:
        return 0.0, 0.0
    return sum(p[0] for p in points) / len(points), sum(p[1] for p in points) / len(points)


def _shapely_poly(points: list[tuple[float, float]]):
    if Polygon is None or len(points) < 3:
        return None
    poly = Polygon(points)
    if not poly.is_valid:
        poly = poly.buffer(0)
    return poly if not poly.is_empty else None


def _union_area(polygons: list[list[tuple[float, float]]], clip_polygon: list[tuple[float, float]] | None = None, subtract: list[list[tuple[float, float]]] | None = None) -> float | None:
    if Polygon is None or unary_union is None:
        return None
    geoms = [g for g in (_shapely_poly(p) for p in polygons) if g is not None]
    if not geoms:
        return 0.0
    geom = unary_union(geoms)
    blockers = [g for g in (_shapely_poly(p) for p in (subtract or [])) if g is not None]
    if blockers:
        geom = geom.difference(unary_union(blockers))
    clip = _shapely_poly(clip_polygon or [])
    if clip is not None:
        if blockers:
            clip = clip.difference(unary_union(blockers))
        geom = geom.intersection(clip)
    return max(0.0, float(geom.area))


def _raster_union_area(polygons: list[list[tuple[float, float]]], clip_polygon: list[tuple[float, float]] | None = None) -> float:
    valid = [poly for poly in polygons if len(poly) >= 3]
    if not valid:
        return 0.0
    bounds_polys = valid + ([clip_polygon] if clip_polygon and len(clip_polygon) >= 3 else [])
    min_x = min(x for poly in bounds_polys for x, _ in poly)
    max_x = max(x for poly in bounds_polys for x, _ in poly)
    min_y = min(y for poly in bounds_polys for _, y in poly)
    max_y = max(y for poly in bounds_polys for _, y in poly)
    width = max_x - min_x
    height = max_y - min_y
    if width <= 0.0 or height <= 0.0:
        return 0.0
    target_cells = 12_000
    cell = max(0.5, sqrt((width * height) / target_cells))
    cols = max(1, int(width / cell) + 1)
    rows = max(1, int(height / cell) + 1)
    boxes = []
    for poly in valid:
        xs = [p[0] for p in poly]
        ys = [p[1] for p in poly]
        boxes.append((min(xs), min(ys), max(xs), max(ys), poly))
    inside_count = 0
    for row in range(rows):
        y = min_y + (row + 0.5) * cell
        for col in range(cols):
            x = min_x + (col + 0.5) * cell
            if clip_polygon and not point_in_polygon((x, y), clip_polygon):
                continue
            for bx1, by1, bx2, by2, poly in boxes:
                if bx1 <= x <= bx2 and by1 <= y <= by2 and point_in_polygon((x, y), poly):
                    inside_count += 1
                    break
    return inside_count * cell * cell


def _shadow_polygons_world(objects: list[ShadowObject], origin: tuple[float, float], az: float, alt: float) -> list[list[tuple[float, float]]]:
    result: list[list[tuple[float, float]]] = []
    for obj in objects:
        result.extend(shadow_polygons_world_m(obj, origin[0], origin[1], az, alt))
    return result


def _object_footprints_world(objects: list[ShadowObject], origin: tuple[float, float], buildings_only: bool = False) -> list[list[tuple[float, float]]]:
    result = []
    for obj in objects:
        if buildings_only and TREE_KINDS.get(obj.kind_key, TREE_KINDS["custom"]).category != "building":
            continue
        cx, cy = latlon_to_local_m(obj.lat, obj.lon, origin[0], origin[1])
        fp = [(x + cx, y + cy) for x, y in object_ground_contact_local_m(obj)]
        if len(fp) >= 3:
            result.append(fp)
    return result


def _building_footprints_world(objects: list[ShadowObject], origin: tuple[float, float]) -> list[list[tuple[float, float]]]:
    return _object_footprints_world(objects, origin, True)


def total_shadow_area_m2(objects: list[ShadowObject], sun_azimuth_deg: float, sun_altitude_deg: float) -> float:
    origin = _origin_for(objects)
    polygons = _shadow_polygons_world(objects, origin, sun_azimuth_deg, sun_altitude_deg)
    area = _union_area(polygons, subtract=_object_footprints_world(objects, origin))
    return area if area is not None else _raster_union_area(polygons)


def total_shadow_on_ground_m2(objects: list[ShadowObject], ground_latlon: list[tuple[float, float]], sun_azimuth_deg: float, sun_altitude_deg: float) -> float:
    if len(ground_latlon) < 3:
        return 0.0
    origin = _origin_for(objects, ground_latlon)
    ground_local = [latlon_to_local_m(lat, lon, origin[0], origin[1]) for lat, lon in ground_latlon]
    polygons = _shadow_polygons_world(objects, origin, sun_azimuth_deg, sun_altitude_deg)
    blockers = _object_footprints_world(objects, origin)
    exact = _union_area(polygons, ground_local, blockers)
    area = exact if exact is not None else _raster_union_area(polygons, ground_local)
    return min(max(0.0, area), polygon_area_m2(ground_local))


def effective_ground_area_m2(objects: list[ShadowObject], ground_latlon: list[tuple[float, float]]) -> float:
    if len(ground_latlon) < 3:
        return 0.0
    origin = _origin_for(objects, ground_latlon)
    ground_local = [latlon_to_local_m(lat, lon, origin[0], origin[1]) for lat, lon in ground_latlon]
    if Polygon is None:
        return polygon_area_m2(ground_local)
    ground = _shapely_poly(ground_local)
    if ground is None:
        return 0.0
    for blocker in _object_footprints_world(objects, origin):
        geom = _shapely_poly(blocker)
        if geom is not None:
            ground = ground.difference(geom)
    return max(0.0, float(ground.area))


def effective_object_shadow_areas_m2(objects: list[ShadowObject], sun_azimuth_deg: float, sun_altitude_deg: float) -> dict[str, float]:
    if not objects:
        return {}
    if Polygon is None or unary_union is None:
        return {obj.object_id: shadow_area_m2(obj, sun_azimuth_deg, sun_altitude_deg) for obj in objects}
    origin = _origin_for(objects)
    sun_x, sun_y = azimuth_vector(sun_azimuth_deg)
    entries = []
    centers = {}
    for obj in objects:
        obj_polys = shadow_polygons_world_m(obj, origin[0], origin[1], sun_azimuth_deg, sun_altitude_deg)
        geoms = [g for g in (_shapely_poly(p) for p in obj_polys) if g is not None]
        poly = unary_union(geoms) if geoms else None
        cx, cy = latlon_to_local_m(obj.lat, obj.lon, origin[0], origin[1])
        centers[obj.object_id] = (obj, cx, cy)
        if poly is None:
            entries.append((0.0, obj.object_id, None))
            continue
        entries.append((-(cx * sun_x + cy * sun_y), obj.object_id, poly))
    blockers = [g for g in (_shapely_poly(p) for p in _object_footprints_world(objects, origin)) if g is not None]
    blocker_union = unary_union(blockers) if blockers else None
    result = {obj.object_id: 0.0 for obj in objects}
    covered = None
    for _order, object_id, poly in sorted(entries, key=lambda x: x[0]):
        if poly is None:
            continue
        visible = poly if covered is None else poly.difference(covered)
        if blocker_union is not None:
            visible = visible.difference(blocker_union)
        result[object_id] = max(0.0, float(visible.area))
        covered = poly if covered is None else unary_union([covered, poly])
    return result


def object_shadow_areas_m2(objects: list[ShadowObject], sun_azimuth_deg: float, sun_altitude_deg: float) -> dict[str, float]:
    return effective_object_shadow_areas_m2(objects, sun_azimuth_deg, sun_altitude_deg)


def shadow_union_polygons_world(objects: list[ShadowObject], origin_lat: float, origin_lon: float, sun_azimuth_deg: float, sun_altitude_deg: float) -> list[list[tuple[float, float]]]:
    polygons = _shadow_polygons_world(objects, (origin_lat, origin_lon), sun_azimuth_deg, sun_altitude_deg)
    if Polygon is None or unary_union is None:
        return [p for p in polygons if len(p) >= 3]
    geoms = [g for g in (_shapely_poly(p) for p in polygons) if g is not None]
    if not geoms:
        return []
    geom = unary_union(geoms)
    if hasattr(geom, "simplify"):
        geom = geom.simplify(0.12, preserve_topology=True)
    blockers = [g for g in (_shapely_poly(p) for p in _object_footprints_world(objects, (origin_lat, origin_lon))) if g is not None]
    if blockers:
        geom = geom.difference(unary_union(blockers))
    polys = list(geom.geoms) if hasattr(geom, "geoms") else [geom]
    result: list[list[tuple[float, float]]] = []
    for poly in polys:
        if poly.is_empty:
            continue
        result.append([(float(x), float(y)) for x, y in list(poly.exterior.coords)[:-1]])
    return result


def shadow_union_polygons_latlon(objects: list[ShadowObject], sun_azimuth_deg: float, sun_altitude_deg: float) -> list[list[tuple[float, float]]]:
    origin = _origin_for(objects)
    return [[local_m_to_latlon(x, y, origin[0], origin[1]) for x, y in poly] for poly in shadow_union_polygons_world(objects, origin[0], origin[1], sun_azimuth_deg, sun_altitude_deg)]
