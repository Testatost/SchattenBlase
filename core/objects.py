from __future__ import annotations

from dataclasses import asdict, dataclass, field
from uuid import uuid4

from core.geometry import bbox_size, distance_m


@dataclass(frozen=True)
class TreeKind:
    key: str
    label_key: str
    default_height_m: float
    default_width_m: float
    color: str
    crown_shape: str
    default_crown_height_m: float
    default_trunk_diameter_m: float
    category: str = "tree"


TREE_KINDS: dict[str, TreeKind] = {
    # Reduzierte Baumliste: nur noch 3 Laubbaum- und 3 Nadelbaum-Varianten.
    # Die alten artspezifischen Einträge werden beim Laden alter Projekte auf
    # diese Varianten abgebildet (siehe LEGACY_KIND_MAP).
    "broadleaf_1": TreeKind("broadleaf_1", "tree.broadleaf_1", 14.0, 10.0, "#3f8a3f", "broadleaf_1", 8.5, 0.45),
    "broadleaf_2": TreeKind("broadleaf_2", "tree.broadleaf_2", 18.0, 9.0, "#4f9342", "broadleaf_2", 11.5, 0.55),
    "broadleaf_3": TreeKind("broadleaf_3", "tree.broadleaf_3", 10.0, 12.0, "#6aa84f", "broadleaf_3", 5.5, 0.40),
    "broadleaf_4": TreeKind("broadleaf_4", "tree.broadleaf_4", 18.0, 4.5, "#4a8f3f", "broadleaf_4", 14.5, 0.35),
    "broadleaf_5": TreeKind("broadleaf_5", "tree.broadleaf_5", 12.0, 10.0, "#5f9c49", "broadleaf_5", 9.5, 0.50),
    "broadleaf_6": TreeKind("broadleaf_6", "tree.broadleaf_6", 9.0, 12.0, "#579146", "broadleaf_6", 3.5, 0.45),
    "conifer_1": TreeKind("conifer_1", "tree.conifer_1", 20.0, 7.0, "#245c45", "conifer_1", 16.0, 0.38),
    "conifer_2": TreeKind("conifer_2", "tree.conifer_2", 28.0, 8.0, "#2f6b48", "conifer_2", 23.0, 0.45),
    "conifer_3": TreeKind("conifer_3", "tree.conifer_3", 16.0, 5.0, "#2f6f55", "conifer_3", 13.0, 0.35),
    "conifer_4": TreeKind("conifer_4", "tree.conifer_4", 16.0, 11.0, "#3d7352", "conifer_4", 4.5, 0.55),
    "conifer_5": TreeKind("conifer_5", "tree.conifer_5", 14.0, 2.6, "#2d6b4c", "conifer_5", 12.5, 0.22),
    "shrub_1": TreeKind("shrub_1", "plant.shrub_1", 2.2, 2.8, "#4e8f3d", "shrub_1", 2.2, 0.0),
    "shrub_2": TreeKind("shrub_2", "plant.shrub_2", 3.2, 2.2, "#5a9a45", "shrub_2", 3.2, 0.0),
    "potted_1": TreeKind("potted_1", "plant.potted_1", 1.6, 1.2, "#4c8f45", "potted_1", 1.0, 0.45),
    "potted_2": TreeKind("potted_2", "plant.potted_2", 2.4, 0.9, "#3f7d46", "potted_2", 1.7, 0.40),
    "sphere": TreeKind("sphere", "geo.sphere", 4.0, 4.0, "#777db4", "sphere", 0.0, 0.0, "geometry"),
    "cube": TreeKind("cube", "geo.cube", 4.0, 4.0, "#9b6f45", "box", 0.0, 0.0, "geometry"),
    "cuboid": TreeKind("cuboid", "geo.cuboid", 4.0, 6.0, "#9b7a55", "box", 0.0, 0.0, "geometry"),
    "cylinder": TreeKind("cylinder", "geo.cylinder", 5.0, 3.0, "#6f7f99", "cylinder", 0.0, 0.0, "geometry"),
    "pyramid": TreeKind("pyramid", "geo.pyramid", 5.0, 5.0, "#b08a45", "pyramid", 0.0, 0.0, "geometry"),
    "cone": TreeKind("cone", "geo.cone", 5.0, 4.0, "#8a8a55", "cone", 0.0, 0.0, "geometry"),
    "plane": TreeKind("plane", "geo.plane", 3.0, 5.0, "#9a9a9a", "plane", 0.0, 0.0, "geometry"),
    "custom": TreeKind("custom", "object.custom", 5.0, 4.0, "#8c6d3f", "custom", 0.0, 0.0, "custom"),
    "building": TreeKind("building", "object.building", 9.0, 8.0, "#9b8f84", "custom", 0.0, 0.0, "building"),
}

LEGACY_KIND_MAP: dict[str, str] = {
    "oak": "broadleaf_1", "lime": "broadleaf_1", "maple": "broadleaf_1", "beech": "broadleaf_1", "chestnut": "broadleaf_1", "plane_tree": "broadleaf_1",
    "ash": "broadleaf_2", "elm": "broadleaf_2", "red_oak": "broadleaf_2", "hornbeam": "broadleaf_2", "birch": "broadleaf_2", "poplar": "broadleaf_2",
    "acacia": "broadleaf_3", "field_maple": "broadleaf_3", "apple": "broadleaf_3", "cherry": "broadleaf_3", "rowan": "broadleaf_3", "willow": "broadleaf_3",
    "spruce": "conifer_1", "fir": "conifer_2", "larch": "conifer_2", "pine": "conifer_3",
    "boxwood": "shrub_1", "hazel_bush": "shrub_2", "rose_bush": "shrub_1", "hedge": "shrub_2",
}


@dataclass
class ShadowObject:
    kind_key: str
    lat: float
    lon: float
    height_m: float
    width_m: float
    depth_m: float = 0.0
    tilt_deg: float = 0.0
    crown_tilt_deg: float = 0.0
    orientation_deg: float = 0.0
    footprint_m: list[tuple[float, float]] = field(default_factory=list)
    trunk_diameter_m: float = 0.0
    crown_width_m: float = 0.0
    crown_height_m: float = 0.0
    rotation_x_deg: float = 0.0
    rotation_y_deg: float = 0.0
    rotation_z_deg: float = 0.0
    name: str = ""
    surface_mode: str = "solid"
    color: str = ""
    shadow_density: float = 1.0
    object_id: str = field(default_factory=lambda: uuid4().hex)

    @classmethod
    def from_kind(cls, kind_key: str, lat: float, lon: float) -> "ShadowObject":
        kind = TREE_KINDS[kind_key]
        footprint = []
        surface_mode = "solid"
        depth = kind.default_width_m
        if kind.crown_shape == "box":
            depth = kind.default_width_m if kind.key == "cube" else max(kind.default_width_m * 0.65, 0.2)
            w = kind.default_width_m * 0.5; d = depth * 0.5
            footprint = [(-w, -d), (w, -d), (w, d), (-w, d)]
        elif kind.crown_shape == "plane":
            # Rechteck/Wandfläche als dünner Quader mit echter Tiefe, damit
            # Breite, Tiefe und Höhe separat bearbeitet werden können.
            depth = 0.10
            w = kind.default_width_m * 0.5
            d = depth * 0.5
            footprint = [(-w, -d), (w, -d), (w, d), (-w, d)]
            surface_mode = "solid"
        return cls(
            kind_key=kind_key, lat=lat, lon=lon,
            height_m=kind.default_height_m, width_m=kind.default_width_m, depth_m=depth,
            trunk_diameter_m=kind.default_trunk_diameter_m,
            crown_width_m=kind.default_width_m, crown_height_m=kind.default_crown_height_m,
            footprint_m=footprint, surface_mode=surface_mode, color=kind.color,
        )

    @classmethod
    def from_custom_polygon(
        cls,
        lat: float,
        lon: float,
        footprint_m: list[tuple[float, float]],
        kind_key: str = "custom",
        height_m: float | None = None,
        name: str = "",
    ) -> "ShadowObject":
        kind = TREE_KINDS.get(kind_key, TREE_KINDS["custom"])
        width, depth = bbox_size(footprint_m)
        if len(footprint_m) == 2:
            size = max(distance_m(footprint_m[0], footprint_m[1]), 0.1)
            depth_value = 0.05
            surface_mode = "plane"
        else:
            # Imported OSM buildings and user polygons must keep their real
            # footprint. Do not inflate small buildings to the example default.
            size = max(width, 0.05)
            depth_value = max(depth, 0.05)
            surface_mode = "solid"
        return cls(
            kind_key=kind.key,
            lat=lat,
            lon=lon,
            height_m=height_m if height_m is not None else kind.default_height_m,
            width_m=size,
            depth_m=depth_value,
            footprint_m=footprint_m,
            name=name,
            surface_mode=surface_mode,
            color=kind.color,
        )

    def is_tree(self) -> bool:
        return TREE_KINDS.get(self.kind_key, TREE_KINDS["custom"]).category == "tree"

    def is_geometry(self) -> bool:
        return TREE_KINDS.get(self.kind_key, TREE_KINDS["custom"]).category == "geometry"

    def is_plane(self) -> bool:
        return self.surface_mode == "plane" or len(self.footprint_m) == 2

    def to_data(self) -> dict:
        data = asdict(self)
        data["footprint_m"] = [list(p) for p in self.footprint_m]
        return data

    @classmethod
    def from_data(cls, data: dict) -> "ShadowObject":
        values = dict(data)
        values["footprint_m"] = [tuple(p) for p in values.get("footprint_m", [])]
        values.setdefault("object_id", uuid4().hex)
        values.setdefault("name", "")
        values.setdefault("trunk_diameter_m", 0.0)
        values.setdefault("depth_m", values.get("width_m", 0.0))
        values.setdefault("crown_width_m", values.get("width_m", 0.0))
        values.setdefault("crown_height_m", 0.0)
        values.setdefault("rotation_x_deg", 0.0)
        values.setdefault("rotation_y_deg", 0.0)
        values.setdefault("rotation_z_deg", 0.0)
        values.setdefault("crown_tilt_deg", 0.0)
        try:
            values["shadow_density"] = min(1.0, max(0.0, float(values.get("shadow_density", 1.0))))
        except (TypeError, ValueError):
            values["shadow_density"] = 1.0
        values.setdefault("surface_mode", "plane" if len(values.get("footprint_m", [])) == 2 else "solid")
        if values.get("kind_key") not in TREE_KINDS:
            values["kind_key"] = LEGACY_KIND_MAP.get(values.get("kind_key", ""), "custom")
        kind = TREE_KINDS.get(values.get("kind_key", "custom"), TREE_KINDS["custom"])
        values.setdefault("color", kind.color)
        if kind.crown_shape in {"sphere", "cylinder", "cone"}:
            # Runde Standardkörper werden aus Breite/Tiefe/Höhe generiert und
            # nicht als altes Polygon-Footprint weiterverwendet.
            values["footprint_m"] = []
        return cls(**values)


@dataclass
class SimulationState:
    objects: list[ShadowObject] = field(default_factory=list)
    ground_polygon: list[tuple[float, float]] = field(default_factory=list)
    selected_object_id: str | None = None
    selected_object_ids: list[str] = field(default_factory=list)
    sun_azimuth_deg: float = 180.0
    sun_altitude_deg: float = 35.0
    cumulative_shadow_m2h: float = 0.0
    ground_name: str = ""
    ground_color: str = "#1e5ab4"
    ground_selected: bool = False
    show_labels: bool = True
    label_mode: str = "all"  # all | selected | none

    def label_visible_for(self, object_id: str | None = None, *, is_ground: bool = False) -> bool:
        if not self.show_labels:
            return False
        mode = getattr(self, "label_mode", "all")
        if mode == "none":
            return False
        if mode == "selected":
            if is_ground:
                return self.ground_selected
            ids = self.selected_object_ids or ([self.selected_object_id] if self.selected_object_id else [])
            return bool(object_id and object_id in ids)
        return True

    def selected_object(self) -> ShadowObject | None:
        object_id = self.selected_object_id or (self.selected_object_ids[-1] if self.selected_object_ids else None)
        if not object_id:
            return None
        return next((o for o in self.objects if o.object_id == object_id), None)

    def selected_objects(self) -> list[ShadowObject]:
        ids = self.selected_object_ids or ([self.selected_object_id] if self.selected_object_id else [])
        return [o for o in self.objects if o.object_id in ids]

    def set_single_selection(self, object_id: str | None) -> None:
        self.selected_object_id = object_id
        self.selected_object_ids = [object_id] if object_id else []

    def object_by_id(self, object_id: str | None) -> ShadowObject | None:
        if not object_id:
            return None
        return next((o for o in self.objects if o.object_id == object_id), None)

    def delete_selected(self) -> bool:
        ids = set(self.selected_object_ids or ([self.selected_object_id] if self.selected_object_id else []))
        if not ids:
            if self.ground_selected and self.ground_polygon:
                self.ground_polygon = []
                self.ground_selected = False
                return True
            return False
        before = len(self.objects)
        self.objects = [o for o in self.objects if o.object_id not in ids]
        removed = len(self.objects) != before
        if removed:
            self.selected_object_id = None
            self.selected_object_ids = []
        return removed
