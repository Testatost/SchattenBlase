from __future__ import annotations
from copy import deepcopy
from math import atan2, cos, sin, sqrt
from PySide6.QtCore import QPointF, Qt, QLineF
from PySide6.QtGui import QColor, QPen, QPolygonF
from core.geometry import bbox_size, convex_hull, latlon_to_local_m, local_m_to_latlon
from core.objects import TREE_KINDS
from core.simulation import object_body_layers_local_m, object_footprint_local_m


def _dist(a, b) -> float:
    return sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2)


def _scale(v: QPointF, s: float) -> QPointF:
    return QPointF(v.x() * s, v.y() * s)


def _edge_normal(poly: list[QPointF], i: int) -> QPointF:
    a, b = poly[i], poly[(i + 1) % len(poly)]
    dx, dy = b.x() - a.x(), b.y() - a.y()
    n = QPointF(dy, -dx)
    l = max(1.0, sqrt(n.x() ** 2 + n.y() ** 2))
    return QPointF(n.x() / l, n.y() / l)


def _arrow(painter, tip: QPointF, tail: QPointF, size: float = 6.0) -> None:
    line = QLineF(tip, tail)
    ang = atan2(line.dy(), line.dx())
    painter.drawLine(tip, QPointF(tip.x() + cos(ang + 0.55) * size, tip.y() + sin(ang + 0.55) * size))
    painter.drawLine(tip, QPointF(tip.x() + cos(ang - 0.55) * size, tip.y() + sin(ang - 0.55) * size))


def _draw_dim_line(painter, a: QPointF, b: QPointF, offset: QPointF, text: str) -> None:
    a2, b2 = a + offset, b + offset
    painter.drawLine(a, a2); painter.drawLine(b, b2); painter.drawLine(a2, b2)
    _arrow(painter, a2, b2); _arrow(painter, b2, a2)
    mid = QPointF((a2.x() + b2.x()) * 0.5, (a2.y() + b2.y()) * 0.5)
    painter.drawText(mid + QPointF(4, -4), text)


def _draw_height_dim(view, painter, cx: float, cy: float, width: float, height: float) -> None:
    if height <= 0.0:
        return
    base = view._project(cx, cy, 0.0)
    top = view._project(cx, cy, height)
    ref = view._project(cx + max(width * 0.55, 1.0), cy, 0.0)
    off = ref - base
    l = max(1.0, sqrt(off.x() ** 2 + off.y() ** 2))
    _draw_dim_line(painter, base, top, QPointF(off.x() / l * 24.0, off.y() / l * 24.0), f"H {height:.1f} m")


def _draw_width_dim(view, painter, cx: float, cy: float, width: float) -> None:
    if width <= 0.0:
        return
    a = view._project(cx - width * 0.5, cy, 0.0)
    b = view._project(cx + width * 0.5, cy, 0.0)
    dx, dy = b.x() - a.x(), b.y() - a.y()
    l = max(1.0, sqrt(dx * dx + dy * dy))
    _draw_dim_line(painter, a, b, QPointF(dy / l * -18.0, dx / l * 18.0), f"B {width:.1f} m")

def _draw_depth_dim(view, painter, cx: float, cy: float, depth: float) -> None:
    if depth <= 0.0:
        return
    a = view._project(cx, cy - depth * 0.5, 0.0)
    b = view._project(cx, cy + depth * 0.5, 0.0)
    dx, dy = b.x() - a.x(), b.y() - a.y()
    l = max(1.0, sqrt(dx * dx + dy * dy))
    _draw_dim_line(painter, a, b, QPointF(dy / l * 18.0, dx / l * -18.0), f"T {depth:.1f} m")


def _draw_polygon_edge_dims(view, painter, pts: list[tuple[float, float]], limit: int = 4) -> None:
    if len(pts) < 3:
        return
    screen = [view._project(x, y, 0.0) for x, y in pts]
    edges = []
    for i, (a, b) in enumerate(zip(pts, pts[1:] + pts[:1])):
        length = _dist(a, b)
        sa, sb = screen[i], screen[(i + 1) % len(screen)]
        if length < 1.0 or _dist((sa.x(), sa.y()), (sb.x(), sb.y())) < 30.0:
            continue
        edges.append((length, i, a, b, sa, sb))
    for length, i, _a, _b, sa, sb in sorted(edges, reverse=True)[:limit]:
        n = _edge_normal(screen, i)
        _draw_dim_line(painter, sa, sb, _scale(n, 18.0), f"{length:.1f} m")


def _draw_tree_dims(view, painter, obj, cx: float, cy: float) -> None:
    crown_w = max(obj.crown_width_m or obj.width_m, obj.width_m)
    trunk_h = max(0.0, obj.height_m - max(obj.crown_height_m, obj.height_m * 0.55))
    _draw_height_dim(view, painter, cx, cy, crown_w, obj.height_m)
    _draw_width_dim(view, painter, cx, cy, crown_w)
    if trunk_h > 0.05:
        base = view._project(cx, cy, 0.0)
        top = view._project(cx, cy, trunk_h)
        _draw_dim_line(painter, base, top, QPointF(-28.0, 0.0), f"St-H {trunk_h:.1f} m")
    if obj.trunk_diameter_m > 0.02:
        z = min(trunk_h * 0.35, max(obj.height_m * 0.25, 0.1))
        a = view._project(cx - obj.trunk_diameter_m * 0.5, cy, z)
        b = view._project(cx + obj.trunk_diameter_m * 0.5, cy, z)
        _draw_dim_line(painter, a, b, QPointF(0.0, 18.0), f"St-B {obj.trunk_diameter_m:.2f} m")

def draw_dimensions(view, painter, origin) -> None:
    if not (getattr(view, 'show_dims_selected', False) or getattr(view, 'show_dims_all', False)):
        return
    selected = view.state.selected_object_id
    painter.setPen(QPen(QColor(18, 18, 18), 1))
    for obj in view.state.objects:
        if not getattr(view, 'show_dims_all', False) and obj.object_id != selected:
            continue
        cx, cy = latlon_to_local_m(obj.lat, obj.lon, origin[0], origin[1])
        width = max(obj.crown_width_m or obj.width_m, obj.width_m)
        if obj.is_tree():
            _draw_tree_dims(view, painter, obj, cx, cy)
            continue
        kind = TREE_KINDS.get(obj.kind_key, TREE_KINDS['custom'])
        pts = [(x + cx, y + cy) for x, y in object_footprint_local_m(obj)]
        if kind.crown_shape in {'sphere', 'cylinder', 'cone', 'pyramid'}:
            _draw_width_dim(view, painter, cx, cy, obj.width_m)
            _draw_depth_dim(view, painter, cx, cy, getattr(obj, 'depth_m', obj.width_m) or obj.width_m)
        elif len(pts) >= 3:
            _draw_polygon_edge_dims(view, painter, pts)
        elif len(pts) == 2:
            sa, sb = view._project(*pts[0], 0.0), view._project(*pts[1], 0.0)
            dx, dy = sb.x() - sa.x(), sb.y() - sa.y(); l = max(1.0, sqrt(dx * dx + dy * dy))
            _draw_dim_line(painter, sa, sb, QPointF(dy / l * -18.0, dx / l * 18.0), f"{_dist(pts[0], pts[1]):.1f} m")
        _draw_height_dim(view, painter, cx, cy, obj.width_m, obj.height_m)


def copy_selected(view) -> bool:
    obj = view.state.selected_object()
    if obj is None:
        return False
    view._copied_object = deepcopy(obj)
    return True


def paste_copied(view, pos: QPointF) -> bool:
    obj = getattr(view, '_copied_object', None)
    if obj is None:
        return False
    new_obj = deepcopy(obj)
    new_obj.object_id = __import__('uuid').uuid4().hex
    x, y = view._screen_to_ground(pos)
    lat, lon = local_m_to_latlon(x, y, view.origin_latlon[0], view.origin_latlon[1])
    new_obj.lat, new_obj.lon = lat, lon
    view.state.objects.append(new_obj)
    view.state.set_single_selection(new_obj.object_id)
    view.state.ground_selected = False
    return True


def hit_projected_object(view, obj, cx: float, cy: float, pos: QPointF) -> bool:
    points = []
    for z, layer in object_body_layers_local_m(obj):
        for x, y in layer:
            points.append(view._project(x + cx, y + cy, z))
    if not points:
        points = [view._project(x + cx, y + cy, obj.height_m * 0.5) for x, y in object_footprint_local_m(obj)]
    if len(points) < 3:
        return False
    hull = convex_hull([(p.x(), p.y()) for p in points])
    if len(hull) < 3:
        return False
    poly = QPolygonF([QPointF(x, y) for x, y in hull])
    # Kein breites Bounding-Rect mehr: Gebäude dürfen nicht schon aus großer
    # Entfernung angewählt werden. Nur tatsächliche Projektion plus kleine Toleranz.
    if poly.containsPoint(pos, Qt.FillRule.OddEvenFill):
        return True
    c = poly.boundingRect().center()
    if poly.boundingRect().width() < 18 and poly.boundingRect().height() < 18:
        return (QPointF(c) - pos).manhattanLength() <= 14
    return False


def grid_bounds_from_bbox(origin: tuple[float, float], bbox) -> tuple[float, float, float, float]:
    south, west, north, east = bbox
    pts = [
        latlon_to_local_m(south, west, *origin), latlon_to_local_m(south, east, *origin),
        latlon_to_local_m(north, east, *origin), latlon_to_local_m(north, west, *origin),
    ]
    xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)
