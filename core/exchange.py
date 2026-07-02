from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from core.geometry import convex_hull, polygon_centroid
from core.objects import ShadowObject

FORMAT = "schattensimulation-object-v1"


def export_object(path: Path, obj: ShadowObject) -> None:
    payload = {"format": FORMAT, "object": obj.to_data()}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def import_objects(path: Path, lat: float, lon: float) -> list[ShadowObject]:
    suffix = path.suffix.lower()
    if suffix == ".obj":
        return _import_obj(path, lat, lon)
    return _import_json(path, lat, lon)


def _import_json(path: Path, lat: float, lon: float) -> list[ShadowObject]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict) and data.get("format") == FORMAT:
        items = [data.get("object", {})]
    elif isinstance(data, dict) and "objects" in data:
        items = data.get("objects", [])
    elif isinstance(data, list):
        items = data
    else:
        items = [data]
    objects: list[ShadowObject] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        obj = ShadowObject.from_data(item)
        obj.lat = lat
        obj.lon = lon
        obj.object_id = uuid4().hex
        objects.append(obj)
    return objects


def _import_obj(path: Path, lat: float, lon: float) -> list[ShadowObject]:
    vertices: list[tuple[float, float, float]] = []
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        parts = line.strip().split()
        if len(parts) >= 4 and parts[0] == "v":
            try:
                vertices.append((float(parts[1]), float(parts[2]), float(parts[3])))
            except ValueError:
                pass
    if not vertices:
        return []
    min_z = min(z for _, _, z in vertices)
    height = max(0.1, max(z for _, _, z in vertices) - min_z)
    points = [(x, y) for x, y, _ in vertices]
    hull = convex_hull(points)
    if len(hull) > 2:
        cx, cy = polygon_centroid(hull)
        footprint = [(x - cx, y - cy) for x, y in hull]
    else:
        xs = sorted(points)[:1] + sorted(points)[-1:]
        cx = sum(x for x, _ in xs) / len(xs)
        cy = sum(y for _, y in xs) / len(xs)
        footprint = [(x - cx, y - cy) for x, y in xs]
    obj = ShadowObject.from_custom_polygon(lat, lon, footprint, height_m=height, name=path.stem)
    return [obj]
