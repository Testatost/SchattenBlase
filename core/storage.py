from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from uuid import uuid4

from config import LIBRARY_FILE
from core.objects import ShadowObject


@dataclass
class Library:
    places: list[dict] = field(default_factory=list)
    objects: list[dict] = field(default_factory=list)
    grounds: list[dict] = field(default_factory=list)


def load_library(path: Path = LIBRARY_FILE) -> Library:
    if not path.exists():
        return Library()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return Library()
    return Library(
        places=list(data.get("places", [])),
        objects=list(data.get("objects", [])),
        grounds=list(data.get("grounds", [])),
    )


def save_library(library: Library, path: Path = LIBRARY_FILE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "places": library.places,
        "objects": library.objects,
        "grounds": library.grounds,
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _entry(name: str, payload: dict) -> dict:
    return {"id": uuid4().hex, "name": name.strip(), **payload}


def upsert_by_name(entries: list[dict], entry: dict) -> None:
    name = entry.get("name", "")
    for index, existing in enumerate(entries):
        if existing.get("name") == name:
            entry["id"] = existing.get("id", entry.get("id"))
            entries[index] = entry
            return
    entries.append(entry)


def save_place(library: Library, name: str, lat: float, lon: float, zoom: int) -> None:
    upsert_by_name(library.places, _entry(name, {"lat": lat, "lon": lon, "zoom": zoom}))


def save_object(library: Library, name: str, obj: ShadowObject) -> None:
    data = obj.to_data()
    data.pop("object_id", None)
    upsert_by_name(library.objects, _entry(name, {"object": data}))


def save_ground(library: Library, name: str, polygon: list[tuple[float, float]], color: str = "#1e5ab4") -> None:
    upsert_by_name(library.grounds, _entry(name, {"polygon": [list(p) for p in polygon], "color": color}))


def load_object(entry: dict, lat: float, lon: float) -> ShadowObject | None:
    data = entry.get("object")
    if not isinstance(data, dict):
        return None
    obj = ShadowObject.from_data(data)
    obj.lat = lat
    obj.lon = lon
    obj.object_id = uuid4().hex
    return obj
