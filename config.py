from __future__ import annotations

from pathlib import Path
import sys

APP_ID = "Schattenblase"
APP_VERSION = "0.1.0"
DEFAULT_LANGUAGE = "de"
DEFAULT_LAT = 52.520008
DEFAULT_LON = 13.404954
DEFAULT_ZOOM = 18
TILE_SIZE = 256


def _application_dir() -> Path:
    """Ordner der main.py bzw. der späteren ausführbaren Datei."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


APP_DIR = _application_dir()
APP_DATA_DIR = APP_DIR / "Schattenblase-Daten"
DATA_DIR = APP_DATA_DIR
CONFIG_DIR = APP_DATA_DIR / "config"
CACHE_DIR = APP_DATA_DIR / "osm_tiles"
PROJECT_DIR = APP_DATA_DIR / "projekte"
EXPORT_DIR = APP_DATA_DIR / "export"
OBJECT_DIR = EXPORT_DIR / "objekte"
CHART_DIR = EXPORT_DIR / "diagramme"
OSM_TILE_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
OSM_USER_AGENT = f"{APP_ID}/{APP_VERSION} (+local-pyside6)"
LIBRARY_FILE = CONFIG_DIR / "library.json"
OVERPASS_URL = "https://overpass-api.de/api/interpreter"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
