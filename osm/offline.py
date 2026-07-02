from __future__ import annotations

import urllib.request
from pathlib import Path

from config import CACHE_DIR, OSM_TILE_URL, OSM_USER_AGENT, TILE_SIZE
from osm.mercator import latlon_to_global_px, tile_count


def tile_range_for_bbox(south: float, west: float, north: float, east: float, zoom: int) -> tuple[range, range]:
    x1, y1 = latlon_to_global_px(north, west, zoom)
    x2, y2 = latlon_to_global_px(south, east, zoom)
    max_tile = tile_count(zoom) - 1
    min_x = max(0, int(min(x1, x2) // TILE_SIZE))
    max_x = min(max_tile, int(max(x1, x2) // TILE_SIZE))
    min_y = max(0, int(min(y1, y2) // TILE_SIZE))
    max_y = min(max_tile, int(max(y1, y2) // TILE_SIZE))
    return range(min_x, max_x + 1), range(min_y, max_y + 1)


def count_tiles(south: float, west: float, north: float, east: float, z_min: int, z_max: int) -> int:
    total = 0
    for z in range(z_min, z_max + 1):
        xs, ys = tile_range_for_bbox(south, west, north, east, z)
        total += len(xs) * len(ys)
    return total


def download_tiles(
    south: float,
    west: float,
    north: float,
    east: float,
    z_min: int,
    z_max: int,
    cache_dir: Path = CACHE_DIR,
    max_tiles: int = 4000,
) -> int:
    total = count_tiles(south, west, north, east, z_min, z_max)
    if total > max_tiles:
        raise ValueError(str(total))
    downloaded = 0
    for z in range(z_min, z_max + 1):
        xs, ys = tile_range_for_bbox(south, west, north, east, z)
        for x in xs:
            for y in ys:
                path = cache_dir / str(z) / str(x) / f"{y}.png"
                if path.exists():
                    continue
                path.parent.mkdir(parents=True, exist_ok=True)
                request = urllib.request.Request(OSM_TILE_URL.format(z=z, x=x, y=y), headers={"User-Agent": OSM_USER_AGENT})
                with urllib.request.urlopen(request, timeout=15) as response:
                    path.write_bytes(response.read())
                downloaded += 1
    return downloaded
