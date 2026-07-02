from __future__ import annotations

from collections import deque

from PySide6.QtCore import QPoint

from core.geometry import latlon_to_local_m, local_m_to_latlon, polygon_centroid
from core.objects import ShadowObject


def _is_structure_color(r: int, g: int, b: int) -> bool:
    # OpenStreetMap Carto renders most buildings as a muted beige/grey-brown.
    # The ranges are deliberately strict to avoid detecting school yards, grass,
    # roads, water and our own shadow overlays as buildings.
    building = 194 <= r <= 226 and 184 <= g <= 214 and 174 <= b <= 206
    beige_order = 2 <= r - g <= 22 and 0 <= g - b <= 22
    muted = max(r, g, b) - min(r, g, b) <= 34
    not_landuse = not (r > 232 and g > 225)
    return building and beige_order and muted and not_landuse


def _component_boxes(mask: list[list[bool]], step: int, width: int, height: int) -> list[tuple[int, int, int, int, int]]:
    rows, cols = len(mask), len(mask[0]) if mask else 0
    seen = [[False] * cols for _ in range(rows)]
    boxes = []
    for y in range(rows):
        for x in range(cols):
            if seen[y][x] or not mask[y][x]:
                continue
            q = deque([(x, y)])
            seen[y][x] = True
            min_x = max_x = x
            min_y = max_y = y
            count = 0
            while q:
                cx, cy = q.popleft()
                count += 1
                min_x, max_x = min(min_x, cx), max(max_x, cx)
                min_y, max_y = min(min_y, cy), max(max_y, cy)
                for nx, ny in ((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)):
                    if 0 <= nx < cols and 0 <= ny < rows and not seen[ny][nx] and mask[ny][nx]:
                        seen[ny][nx] = True
                        q.append((nx, ny))
            boxes.append((min_x * step, min_y * step, min((max_x + 1) * step, width), min((max_y + 1) * step, height), count))
    return boxes


def _box_to_object(canvas, x1: int, y1: int, x2: int, y2: int) -> ShadowObject:
    corners = [(x1, y1), (x2, y1), (x2, y2), (x1, y2)]
    latlon = [canvas._scene_latlon(canvas.mapToScene(QPoint(x, y))) for x, y in corners]
    origin_lat = sum(p[0] for p in latlon) / 4.0
    origin_lon = sum(p[1] for p in latlon) / 4.0
    local = [latlon_to_local_m(lat, lon, origin_lat, origin_lon) for lat, lon in latlon]
    cx, cy = polygon_centroid(local)
    center_lat, center_lon = local_m_to_latlon(cx, cy, origin_lat, origin_lon)
    footprint = [(x - cx, y - cy) for x, y in local]
    return ShadowObject.from_custom_polygon(center_lat, center_lon, footprint, "building", 6.0)


def detect_structures(canvas, max_objects: int = 120) -> list[ShadowObject]:
    image = canvas.viewport().grab().toImage()
    width, height = image.width(), image.height()
    if width <= 0 or height <= 0:
        return []
    step = 2
    rows, cols = max(1, height // step), max(1, width // step)
    mask = [[False] * cols for _ in range(rows)]
    for row in range(rows):
        py = min(row * step, height - 1)
        for col in range(cols):
            px = min(col * step, width - 1)
            c = image.pixelColor(px, py)
            mask[row][col] = _is_structure_color(c.red(), c.green(), c.blue())
    objects = []
    min_cells = max(12, int(rows * cols * 0.000025))
    max_cells = int(rows * cols * 0.006)
    for x1, y1, x2, y2, count in _component_boxes(mask, step, width, height):
        box_w, box_h = x2 - x1, y2 - y1
        if count < min_cells or count > max_cells or box_w < 8 or box_h < 8:
            continue
        if box_w > width * 0.16 or box_h > height * 0.16:
            continue
        fill = count * step * step / max(1, box_w * box_h)
        if fill < 0.45:
            continue
        objects.append(_box_to_object(canvas, x1, y1, x2, y2))
        if len(objects) >= max_objects:
            break
    return objects
