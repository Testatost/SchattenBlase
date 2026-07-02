from __future__ import annotations

import json
from pathlib import Path

from core.history import restore_state, snapshot_state
from core.objects import SimulationState

FORMAT = "schattensimulation-project-v1"


def save_project(path: Path, state: SimulationState, lat: float, lon: float, zoom: int) -> None:
    payload = {
        "format": FORMAT,
        "map": {"lat": lat, "lon": lon, "zoom": zoom},
        "state": snapshot_state(state),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def load_project(path: Path, state: SimulationState) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("format") != FORMAT:
        raise ValueError("unsupported project file")
    restore_state(state, data.get("state", {}))
    return data.get("map", {})
