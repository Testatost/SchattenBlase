from __future__ import annotations

from copy import deepcopy

from core.objects import ShadowObject, SimulationState


def snapshot_state(state: SimulationState) -> dict:
    return {
        "objects": [obj.to_data() for obj in state.objects],
        "ground_polygon": [list(p) for p in state.ground_polygon],
        "selected_object_id": state.selected_object_id,
        "selected_object_ids": list(getattr(state, "selected_object_ids", [])),
        "sun_azimuth_deg": state.sun_azimuth_deg,
        "sun_altitude_deg": state.sun_altitude_deg,
        "cumulative_shadow_m2h": state.cumulative_shadow_m2h,
        "ground_name": state.ground_name,
        "ground_color": state.ground_color,
        "ground_selected": state.ground_selected,
        "show_labels": state.show_labels,
        "label_mode": getattr(state, "label_mode", "all"),
    }


def restore_state(state: SimulationState, snap: dict) -> None:
    data = deepcopy(snap)
    state.objects = [ShadowObject.from_data(item) for item in data.get("objects", [])]
    state.ground_polygon = [tuple(p) for p in data.get("ground_polygon", [])]
    state.selected_object_id = data.get("selected_object_id")
    state.selected_object_ids = list(data.get("selected_object_ids", [state.selected_object_id] if state.selected_object_id else []))
    state.sun_azimuth_deg = float(data.get("sun_azimuth_deg", 180.0))
    state.sun_altitude_deg = float(data.get("sun_altitude_deg", 35.0))
    state.cumulative_shadow_m2h = float(data.get("cumulative_shadow_m2h", 0.0))
    state.ground_name = data.get("ground_name", "")
    state.ground_color = data.get("ground_color", "#1e5ab4")
    state.ground_selected = bool(data.get("ground_selected", False))
    state.show_labels = bool(data.get("show_labels", True))
    state.label_mode = str(data.get("label_mode", "all"))
