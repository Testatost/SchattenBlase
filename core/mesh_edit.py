from __future__ import annotations

from math import cos, pi, sin, sqrt

from core.geometry import bbox_size, rotate_points
from core.objects import ShadowObject, TREE_KINDS
from core.simulation import object_footprint_local_m, tree_layer_points

Handle = tuple[str, float, float, float]


def _bbox(points: list[tuple[float, float]]) -> tuple[float, float, float, float]:
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return min(xs), min(ys), max(xs), max(ys)


def _bbox_points(obj: ShadowObject) -> list[tuple[float, float]]:
    kind = TREE_KINDS.get(obj.kind_key, TREE_KINDS["custom"])
    if obj.footprint_m and kind.crown_shape not in {"box", "sphere", "cylinder", "cone"}:
        return list(obj.footprint_m)
    if obj.is_tree():
        r = max(obj.crown_width_m or obj.width_m, 0.2) * 0.5
        return [(-r, -r), (r, -r), (r, r), (-r, r)]
    w = max(obj.width_m, 0.2) * 0.5
    d = max(obj.depth_m or obj.width_m, 0.2) * 0.5
    return [(-w, -d), (w, -d), (w, d), (-w, d)]


def _vertex_handles(obj: ShadowObject, z: float) -> list[Handle]:
    pts = object_footprint_local_m(obj) if not obj.footprint_m else rotate_points(list(obj.footprint_m), obj.orientation_deg + obj.rotation_z_deg)
    if 2 <= len(pts) <= 24:
        return [(f"vertex:{i}", x, y, z) for i, (x, y) in enumerate(pts)]
    return []


def edit_handles_local(obj: ShadowObject) -> list[Handle]:
    kind = TREE_KINDS.get(obj.kind_key, TREE_KINDS["custom"])
    z = max(0.0, obj.height_m)
    if obj.is_tree():
        pts = rotate_points(_bbox_points(obj), obj.orientation_deg + obj.rotation_z_deg)
        min_x, min_y, max_x, max_y = _bbox(pts)
        mid_x = (min_x + max_x) * 0.5
        mid_y = (min_y + max_y) * 0.5
        crown_h = min(max(obj.crown_height_m or obj.height_m * 0.65, 0.1), max(obj.height_m, 0.1))
        crown_bottom = max(0.0, obj.height_m - crown_h)
        shape = TREE_KINDS.get(obj.kind_key, TREE_KINDS["custom"]).crown_shape
        # Bei Nadelbäumen sitzt der bearbeitbare Griff an der breiten Krone,
        # nicht an der Spitze. Das verhindert sprunghafte Verformungen.
        t = 0.18 if shape in {"conifer_1", "conifer_2", "conifer_3"} else 0.50
        handle_z = crown_bottom + crown_h * t
        return [("left", min_x, mid_y, handle_z), ("right", max_x, mid_y, handle_z), ("top", mid_x, max_y, handle_z), ("bottom", mid_x, min_y, handle_z), ("scale", max_x, min_y, handle_z)]
    pts = rotate_points(_bbox_points(obj), obj.orientation_deg + obj.rotation_z_deg)
    min_x, min_y, max_x, max_y = _bbox(pts)
    mid_x = (min_x + max_x) * 0.5
    mid_y = (min_y + max_y) * 0.5
    mid_z = 0.0 if kind.crown_shape in {"cone", "pyramid", "box", "custom"} else z * 0.5
    handles = [("left", min_x, mid_y, mid_z), ("right", max_x, mid_y, mid_z), ("top", mid_x, max_y, mid_z), ("bottom", mid_x, min_y, mid_z), ("scale", max_x, min_y, mid_z)]
    handles.append(("height", 0.0, 0.0, z))
    return handles


def _unrotate(obj: ShadowObject, x: float, y: float) -> tuple[float, float]:
    from math import cos, radians, sin
    a = radians(-(obj.orientation_deg + obj.rotation_z_deg))
    ca, sa = cos(a), sin(a)
    return x * ca - y * sa, x * sa + y * ca


def _rescale(points: list[tuple[float, float]], min_x: float, min_y: float, max_x: float, max_y: float) -> list[tuple[float, float]]:
    old_min_x, old_min_y, old_max_x, old_max_y = _bbox(points)
    old_w = max(old_max_x - old_min_x, 0.001)
    old_h = max(old_max_y - old_min_y, 0.001)
    new_w = max(max_x - min_x, 0.05)
    new_h = max(max_y - min_y, 0.05)
    return [(min_x + (x - old_min_x) / old_w * new_w, min_y + (y - old_min_y) / old_h * new_h) for x, y in points]


def _ensure_footprint(obj: ShadowObject) -> None:
    kind = TREE_KINDS.get(obj.kind_key, TREE_KINDS["custom"])
    if kind.crown_shape in {"sphere", "cylinder", "cone"}:
        return
    if obj.footprint_m:
        return
    pts = object_footprint_local_m(obj)
    if 2 <= len(pts) <= 48:
        obj.footprint_m = [_unrotate(obj, x, y) for x, y in pts]


def _smooth_tree_outline(shape: str, min_x: float, min_y: float, max_x: float, max_y: float, count: int = 56) -> list[tuple[float, float]]:
    cx = (min_x + max_x) * 0.5
    cy = (min_y + max_y) * 0.5
    rx = max((max_x - min_x) * 0.5, 0.05)
    ry = max((max_y - min_y) * 0.5, 0.05)
    base = tree_layer_points(2.0, shape, 0.5, count)
    bx1, by1, bx2, by2 = _bbox(base)
    bw = max((bx2 - bx1) * 0.5, 0.001)
    bh = max((by2 - by1) * 0.5, 0.001)
    return [(cx + x / bw * rx, cy + y / bh * ry) for x, y in base]


def apply_handle_drag(obj: ShadowObject, role: str, x: float, y: float) -> None:
    if role.startswith("vertex:"):
        _ensure_footprint(obj)
        try:
            idx = int(role.split(":", 1)[1])
        except ValueError:
            idx = -1
        if 0 <= idx < len(obj.footprint_m):
            obj.footprint_m[idx] = _unrotate(obj, x, y)
            width, depth = bbox_size(obj.footprint_m)
            obj.width_m = max(width, 0.1)
            obj.depth_m = max(depth, 0.1)
        return
    if obj.is_tree():
        if not obj.footprint_m or len(obj.footprint_m) < 3:
            kind = TREE_KINDS.get(obj.kind_key, TREE_KINDS["custom"])
            # Ausgangskontur der Baumkrone organisch übernehmen, nicht als Rechteck.
            # Die vier Griffe verschieben danach nur die jeweilige Hüllkante und
            # verformen diese Kontur proportional.
            width = max(obj.crown_width_m or obj.width_m, 0.2)
            obj.footprint_m = tree_layer_points(width, kind.crown_shape, 0.5, 48)
        ux, uy = _unrotate(obj, x, y)
        pts = list(obj.footprint_m)
        min_x, min_y, max_x, max_y = _bbox(pts)
        center_x = (min_x + max_x) * 0.5
        center_y = (min_y + max_y) * 0.5
        min_size = 0.35
        if role == "left":
            min_x = min(ux, max_x - min_size)
        elif role == "right":
            max_x = max(ux, min_x + min_size)
        elif role == "top":
            max_y = max(uy, min_y + min_size)
        elif role == "bottom":
            min_y = min(uy, max_y - min_size)
        elif role == "scale":
            half = max(abs(ux - center_x), abs(uy - center_y), min_size * 0.5)
            min_x, max_x = center_x - half, center_x + half
            min_y, max_y = center_y - half, center_y + half
        kind = TREE_KINDS.get(obj.kind_key, TREE_KINDS["custom"])
        obj.footprint_m = _smooth_tree_outline(kind.crown_shape, min_x, min_y, max_x, max_y)
        width, depth = bbox_size(obj.footprint_m)
        obj.crown_width_m = max(width, depth, 0.2)
        obj.width_m = max(width, 0.2)
        obj.depth_m = max(depth, 0.2)
        return
    kind = TREE_KINDS.get(obj.kind_key, TREE_KINDS["custom"])
    if kind.crown_shape in {"sphere", "cylinder", "cone"}:
        ux, uy = _unrotate(obj, x, y)
        w = max(obj.width_m, 0.1)
        d = max(obj.depth_m or obj.width_m, 0.1)
        half_w = w * 0.5
        half_d = d * 0.5
        if role == "left":
            half_w = max(abs(ux), 0.05)
        elif role == "right":
            half_w = max(abs(ux), 0.05)
        elif role == "top":
            half_d = max(abs(uy), 0.05)
        elif role == "bottom":
            half_d = max(abs(uy), 0.05)
        elif role == "scale":
            half = max(abs(ux), abs(uy), 0.05)
            half_w = half_d = half
        obj.width_m = max(half_w * 2.0, 0.1)
        obj.depth_m = max(half_d * 2.0, 0.1)
        if kind.crown_shape == "sphere" and role == "scale":
            obj.height_m = max(obj.width_m, obj.depth_m)
            obj.width_m = obj.depth_m = obj.height_m
        obj.footprint_m = []
        return
    if not obj.footprint_m:
        _ensure_footprint(obj)
    if not obj.footprint_m:
        obj.width_m = max(0.1, sqrt(x * x + y * y) * 2.0)
        return
    ux, uy = _unrotate(obj, x, y)
    x, y = ux, uy
    pts = list(obj.footprint_m)
    min_x, min_y, max_x, max_y = _bbox(pts)
    center_x = (min_x + max_x) * 0.5
    center_y = (min_y + max_y) * 0.5
    if role == "left":
        min_x = min(x, max_x - 0.05)
    elif role == "right":
        max_x = max(x, min_x + 0.05)
    elif role == "top":
        max_y = max(y, min_y + 0.05)
    elif role == "bottom":
        min_y = min(y, max_y - 0.05)
    elif role == "scale":
        half = max(abs(x - center_x), abs(y - center_y), 0.05)
        min_x, max_x = center_x - half, center_x + half
        min_y, max_y = center_y - half, center_y + half
    obj.footprint_m = _rescale(pts, min_x, min_y, max_x, max_y)
    width, depth = bbox_size(obj.footprint_m)
    obj.width_m = max(width, 0.1)
    obj.depth_m = max(depth, 0.1)
