from __future__ import annotations
from math import cos, pi, radians, sin, sqrt
from copy import deepcopy
from time import monotonic
from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QPolygonF, QPixmap, QTransform, QRadialGradient
from PySide6.QtWidgets import QPushButton, QWidget
from config import DEFAULT_LAT, DEFAULT_LON
from core.geometry import convex_hull, latlon_to_local_m, local_m_to_latlon, polygon_centroid
from core.objects import ShadowObject, SimulationState, TREE_KINDS
from core.mesh_edit import apply_handle_drag, edit_handles_local
from core.simulation import object_body_layers_local_m, object_footprint_local_m, shadow_union_polygons_by_density_world
from i18n import I18n
from ui.scene3d_tools import draw_dimensions, copy_selected, paste_copied, hit_projected_object, grid_bounds_from_bbox
from ui.scene3d_gizmo import draw_gizmo

MAX_FULL_3D_OBJECTS = 350
MAX_3D_SHADOW_OBJECTS = 350
MAX_3D_LABEL_OBJECTS = 150

class Scene3DCanvas(QWidget):
    rotation_changed = Signal(float, float, float)
    mesh_edited = Signal()
    object_selected = Signal()
    def __init__(self, state: SimulationState, i18n: I18n, parent=None) -> None:
        super().__init__(parent)
        self.state = state
        self.i18n = i18n
        self.zoom = 4.0
        self.pan = QPointF(0.0, 0.0)
        self.rot_x = 20.0
        self.rot_y = 0.0
        self.rot_z = 0.0
        self.origin_latlon = (DEFAULT_LAT, DEFAULT_LON)
        self.reset_button = QPushButton(self.i18n.t("view.reset"), self)
        self.reset_button.clicked.connect(self.reset_view)
        self._last_pos: QPoint | None = None
        self._drag_mode = ""
        self._drag_handle = None
        self._drag_start_data = None
        self._drag_start_pos = None
        self._drag_start_handle_local = (0.0, 0.0)
        self.mesh_edit = False
        self.add_kind_key: str | None = None
        self.drawing_custom = False
        self.pending_custom: list[tuple[float, float]] = []
        self._copied_object = None
        self._last_mouse_pos = QPointF(0.0, 0.0)
        self.show_dims_selected = False
        self.show_dims_all = False
        self.show_map_plane = True
        self.map_plane_pixmap = QPixmap()
        self.map_plane_bounds = None
        self._shadow_cache_key = None
        self._shadow_cache_polys = []
        self._last_drag_emit = 0.0
        self._fast_object_render = False
        self.grid_bounds = (-80.0, -80.0, 80.0, 80.0)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMinimumSize(500, 350)
        self.setMouseTracking(True)
    def set_language(self, i18n: I18n) -> None:
        self.i18n = i18n
        self.reset_button.setText(self.i18n.t("view.reset"))
        self.update()
    def set_origin(self, lat: float, lon: float) -> None:
        self.origin_latlon = (lat, lon)
        self.update()
    def set_view_rotation(self, rx: float, ry: float, rz: float, emit: bool = False) -> None:
        self.rot_x = rx % 360.0
        self.rot_y = ry % 360.0
        self.rot_z = rz % 360.0
        self.update()
        if emit:
            self.rotation_changed.emit(self.rot_x, self.rot_y, self.rot_z)
    def set_mesh_edit(self, enabled: bool) -> None:
        self.mesh_edit = enabled
        self.update()
    def set_dimensions_selected(self, enabled: bool) -> None:
        self.show_dims_selected = enabled
        self.update()
    def set_dimensions_all(self, enabled: bool) -> None:
        self.show_dims_all = enabled
        self.update()
    def set_grid_bbox(self, bbox) -> None:
        try:
            self.grid_bounds = grid_bounds_from_bbox(self.origin_latlon, bbox)
        except Exception:
            self.grid_bounds = (-80.0, -80.0, 80.0, 80.0)
        self.update()
    def set_map_plane_visible(self, enabled: bool) -> None:
        self.show_map_plane = enabled
        self.update()
    def set_map_plane_image(self, pixmap: QPixmap, bbox=None) -> None:
        self.map_plane_pixmap = pixmap
        if bbox is not None:
            try:
                self.map_plane_bounds = grid_bounds_from_bbox(self.origin_latlon, bbox)
            except Exception:
                self.map_plane_bounds = None
        self.update()
    def invalidate_shadow_cache(self) -> None:
        self._shadow_cache_key = None
    def set_add_mode(self, kind_key: str | None) -> None:
        self.add_kind_key = kind_key
        if kind_key:
            self.drawing_custom = False
            self.pending_custom = []
    def set_custom_mode(self, enabled: bool) -> None:
        self.drawing_custom = enabled
        self.pending_custom = []
        if enabled:
            self.add_kind_key = None
        self.update()
    def reset_view(self) -> None:
        self.zoom = 4.0
        self.pan = QPointF(0.0, 0.0)
        self.set_view_rotation(20.0, 0.0, 0.0, True)
    def refresh(self) -> None:
        self.invalidate_shadow_cache()
        self.update()
    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor(238, 240, 242))
        origin = self._origin()
        self._draw_map_plane(painter)
        self._draw_grid(painter)
        self._draw_ground(painter, origin)
        self._draw_shadows(painter, origin)
        self._draw_objects(painter, origin)
        self._draw_selected_mesh(painter, origin)
        self._draw_custom_draft(painter)
        draw_dimensions(self, painter, origin)
        draw_gizmo(self, painter)
    def wheelEvent(self, event) -> None:
        old_zoom = self.zoom
        factor = 1.12 if event.angleDelta().y() > 0 else 1.0 / 1.12
        self.zoom = max(0.4, min(45.0, self.zoom * factor))
        pos = QPointF(event.position())
        base = self._base_point()
        rel = (pos - base - self.pan) / old_zoom
        self.pan = pos - base - rel * self.zoom
        self.update()
    def mousePressEvent(self, event) -> None:
        if event.button() not in {Qt.MouseButton.LeftButton, Qt.MouseButton.MiddleButton, Qt.MouseButton.RightButton}:
            return
        self.setFocus()
        self._last_mouse_pos = QPointF(event.position())
        self._last_pos = event.position().toPoint()
        if self.drawing_custom and event.button() == Qt.MouseButton.LeftButton:
            self._handle_custom_drawing(event)
            self._last_pos = None
            self._drag_mode = ""
            return
        if event.button() == Qt.MouseButton.LeftButton and self.add_kind_key:
            self._place_object(event.position())
            self._last_pos = None
            self._drag_mode = ""
            return
        if self._gizmo_rect().contains(self._last_pos):
            self._drag_mode = "gizmo"
        elif event.button() == Qt.MouseButton.LeftButton and self.mesh_edit:
            handle = self._hit_mesh_handle(event.position())
            if handle is not None:
                self._drag_handle = handle[0]
                obj = self.state.selected_object()
                self._drag_start_data = deepcopy(obj.to_data()) if obj is not None else None
                self._drag_start_pos = QPointF(event.position())
                if obj is not None:
                    ox, oy = latlon_to_local_m(obj.lat, obj.lon, self.origin_latlon[0], self.origin_latlon[1])
                    self._drag_start_handle_local = (handle[1] - ox, handle[2] - oy)
                self._drag_mode = "mesh"
            elif self._select_object_at(event.position(), bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier)):
                self._drag_mode = "move_obj" if not (event.modifiers() & Qt.KeyboardModifier.ControlModifier) else ""
            else:
                self._clear_selection()
                self._drag_mode = "rotate"
        elif event.button() == Qt.MouseButton.LeftButton:
            if self._select_object_at(event.position(), bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier)):
                self._drag_mode = "move_obj" if not (event.modifiers() & Qt.KeyboardModifier.ControlModifier) else ""
            else:
                self._clear_selection()
                self._drag_mode = "rotate"
        else:
            self._drag_mode = "pan"
    def mouseMoveEvent(self, event) -> None:
        if self._last_pos is None:
            return
        pos = event.position().toPoint()
        delta = pos - self._last_pos
        if self._drag_mode == "mesh" and self._drag_handle is not None:
            self._move_mesh_handle(delta, event.position())
            self._emit_drag_update()
        elif self._drag_mode == "move_obj":
            self._move_selected_object(delta)
            self._emit_drag_update()
        elif self._drag_mode in {"rotate", "gizmo"}:
            if event.buttons() & Qt.MouseButton.RightButton:
                self.rot_y = (self.rot_y + delta.x() * 0.4) % 360.0
            else:
                self.rot_z = (self.rot_z + delta.x() * 0.4) % 360.0
                self.rot_x = max(5.0, min(89.0, self.rot_x - delta.y() * 0.3))
            self.rotation_changed.emit(self.rot_x, self.rot_y, self.rot_z)
        else:
            self.pan += QPointF(delta)
        self._last_mouse_pos = QPointF(event.position())
        self._last_pos = pos
        self.update()
    def mouseReleaseEvent(self, event) -> None:
        mode = self._drag_mode
        self._last_pos = None
        self._drag_mode = ""
        self._drag_handle = None
        self._drag_start_data = None
        self._drag_start_pos = None
        if mode in {"mesh", "move_obj"}:
            self.invalidate_shadow_cache(); self.mesh_edited.emit()
    def _origin(self) -> tuple[float, float]:
        return self.origin_latlon
    def _base_point(self) -> QPointF:
        return QPointF(self.width() * 0.5, self.height() * 0.68)
    def _rotate3(self, x: float, y: float, z: float) -> tuple[float, float, float]:
        y = -y
        rz = radians(self.rot_z)
        rx = radians(self.rot_x)
        ry = radians(self.rot_y)
        x, y = x * cos(rz) - y * sin(rz), x * sin(rz) + y * cos(rz)
        y, z = y * cos(rx) - z * sin(rx), y * sin(rx) + z * cos(rx)
        x, z = x * cos(ry) + z * sin(ry), -x * sin(ry) + z * cos(ry)
        return x, y, z
    def _project(self, x: float, y: float, z: float = 0.0) -> QPointF:
        rx, ry, _ = self._rotate3(x, y, z)
        return self._base_point() + QPointF(rx * self.zoom, ry * self.zoom) + self.pan
    def _poly(self, points: list[tuple[float, float]], z: float = 0.0) -> QPolygonF:
        return QPolygonF([self._project(x, y, z) for x, y in points])
    def _visible_ground_bounds(self) -> tuple[float, float, float, float]:
        pts = []
        for sx, sy in [(0, 0), (self.width(), 0), (self.width(), self.height()), (0, self.height()), (self.width() * 0.5, self.height() * 0.5)]:
            try:
                pts.append(self._screen_to_ground(QPointF(float(sx), float(sy))))
            except Exception:
                pass
        min_x, min_y, max_x, max_y = self.grid_bounds
        if pts:
            xs = [p[0] for p in pts] + [min_x, max_x]
            ys = [p[1] for p in pts] + [min_y, max_y]
            min_x, max_x = min(xs), max(xs)
            min_y, max_y = min(ys), max(ys)
        pad = max(max_x - min_x, max_y - min_y, 1.0) * 0.04
        return min_x - pad, min_y - pad, max_x + pad, max_y + pad
    def _draw_map_plane(self, painter: QPainter) -> None:
        if not self.show_map_plane:
            return
        vmin_x, vmin_y, vmax_x, vmax_y = self._visible_ground_bounds()
        back_quad = [(vmin_x, vmin_y), (vmax_x, vmin_y), (vmax_x, vmax_y), (vmin_x, vmax_y)]
        painter.setBrush(QColor(222, 226, 229)); painter.setPen(Qt.PenStyle.NoPen)
        painter.drawPolygon(self._poly(back_quad, 0.0))
        if not self.map_plane_pixmap.isNull():
            # Die Kartenaufnahme muss georeferenziert auf genau dem BBox-Ausschnitt
            # liegen, aus dem sie im 2D-Kartenfenster abgegriffen wurde.
            # In v36 wurde sie versehentlich jedes Mal auf das aktuelle 3D-Sichtfeld
            # gestreckt. Dadurch wanderte die Karte unter den Gebäuden und passte
            # nicht mehr zu importierten OSM-Gebäuden/Grundflächen.
            gx1, gy1, gx2, gy2 = self.map_plane_bounds or (vmin_x, vmin_y, vmax_x, vmax_y)
            p00 = self._project(gx1, gy2, 0.0)
            p10 = self._project(gx2, gy2, 0.0)
            p01 = self._project(gx1, gy1, 0.0)
            w = max(1, self.map_plane_pixmap.width())
            h = max(1, self.map_plane_pixmap.height())
            transform = QTransform(
                (p10.x() - p00.x()) / w, (p10.y() - p00.y()) / w,
                (p01.x() - p00.x()) / h, (p01.y() - p00.y()) / h,
                p00.x(), p00.y(),
            )
            painter.save()
            painter.setOpacity(0.82)
            painter.setTransform(transform, False)
            painter.drawPixmap(0, 0, self.map_plane_pixmap)
            painter.restore()
            quad = [(gx1, gy1), (gx2, gy1), (gx2, gy2), (gx1, gy2)]
            painter.setPen(QPen(QColor(185, 190, 196), 1))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPolygon(self._poly(quad, 0.0))
        painter.setOpacity(1.0)
    def _draw_grid(self, painter: QPainter) -> None:
        painter.setPen(QPen(QColor(205, 209, 213), 1))
        min_x, min_y, max_x, max_y = self._visible_ground_bounds()
        step = 5 if max(max_x - min_x, max_y - min_y) <= 60 else 10
        start_x = int(min_x // step) * step; end_x = int(max_x // step + 1) * step
        start_y = int(min_y // step) * step; end_y = int(max_y // step + 1) * step
        for i in range(start_y, end_y + step, step):
            painter.drawLine(self._project(start_x, i, 0.0), self._project(end_x, i, 0.0))
        for i in range(start_x, end_x + step, step):
            painter.drawLine(self._project(i, start_y, 0.0), self._project(i, end_y, 0.0))
    def _draw_ground(self, painter: QPainter, origin: tuple[float, float]) -> None:
        if len(self.state.ground_polygon) < 3:
            return
        local = [latlon_to_local_m(lat, lon, origin[0], origin[1]) for lat, lon in self.state.ground_polygon]
        painter.setPen(QPen(QColor(30, 90, 180), 2, Qt.PenStyle.DashLine))
        painter.setBrush(QColor(self.state.ground_color))
        painter.setOpacity(0.35)
        painter.drawPolygon(self._poly(local))
        painter.setOpacity(1.0)
        if self.state.label_visible_for(is_ground=True) and self.state.ground_name:
            self._draw_text(painter, self.state.ground_name, local[0][0], local[0][1], 0.1)
    def _shadow_polys(self, origin: tuple[float, float]):
        # Bei Streets-GL-Importen können mehrere hundert Gebäude entstehen.
        # Die exakte Schattenvereinigung per Shapely ist dafür in der interaktiven
        # 3D-Ansicht zu teuer. Die numerische Auswertung bleibt unverändert; hier
        # wird nur die Vorschau-Zeichnung begrenzt.
        if len(self.state.objects) > MAX_3D_SHADOW_OBJECTS:
            return []
        key = (
            round(origin[0], 7),
            round(origin[1], 7),
            round(self.state.sun_azimuth_deg, 3),
            round(self.state.sun_altitude_deg, 3),
            len(self.state.objects),
            tuple(o.object_id for o in self.state.objects),
            tuple(round(getattr(o, "shadow_density", 1.0), 2) for o in self.state.objects),
        )
        if key != self._shadow_cache_key:
            self._shadow_cache_key = key
            self._shadow_cache_polys = shadow_union_polygons_by_density_world(self.state.objects, origin[0], origin[1], self.state.sun_azimuth_deg, self.state.sun_altitude_deg)
        return self._shadow_cache_polys
    def _draw_shadows(self, painter: QPainter, origin: tuple[float, float]) -> None:
        for density, polys in self._shadow_polys(origin):
            painter.setPen(QPen(QColor(45, 45, 45, max(1, round(120 * density))), 1))
            painter.setBrush(QColor(45, 45, 45, max(1, round(70 * density))))
            for poly in polys:
                if len(poly) >= 3:
                    painter.drawPolygon(self._poly(poly))
    def _draw_objects(self, painter: QPainter, origin: tuple[float, float]) -> None:
        entries = []
        total_count = len(self.state.objects)
        self._fast_object_render = total_count > MAX_FULL_3D_OBJECTS
        vmin_x, vmin_y, vmax_x, vmax_y = self._visible_ground_bounds()
        pad = max(25.0, max(vmax_x - vmin_x, vmax_y - vmin_y, 1.0) * 0.20)
        selected_ids = set(getattr(self.state, "selected_object_ids", []) or [])
        if self.state.selected_object_id:
            selected_ids.add(self.state.selected_object_id)

        for obj in self.state.objects:
            cx, cy = latlon_to_local_m(obj.lat, obj.lon, origin[0], origin[1])
            selected = obj.object_id in selected_ids
            radius = max(obj.width_m, obj.depth_m, obj.height_m, 2.0) * 1.6
            if not selected and (cx + radius < vmin_x - pad or cx - radius > vmax_x + pad or cy + radius < vmin_y - pad or cy - radius > vmax_y + pad):
                continue
            _sx, _sy, depth = self._rotate3(cx, cy, obj.height_m * 0.5)
            entries.append((depth, obj, cx, cy, selected))

        for _depth, obj, cx, cy, selected in sorted(entries, key=lambda e: e[0]):
            kind = TREE_KINDS.get(obj.kind_key, TREE_KINDS["custom"])
            painter.setPen(QPen(QColor(255, 255, 255) if selected else QColor(30, 70, 30), 2 if selected else 1))
            painter.setBrush(QColor(obj.color or kind.color))
            if obj.is_tree():
                self._draw_tree(painter, obj, cx, cy, QColor(obj.color or kind.color), selected)
            elif kind.crown_shape == "sphere":
                self._draw_sphere(painter, obj, cx, cy, selected)
            elif kind.crown_shape in {"cone", "pyramid"}:
                self._draw_layered_body(painter, obj, cx, cy)
            else:
                footprint = [(x + cx, y + cy) for x, y in object_footprint_local_m(obj)]
                self._draw_prism(painter, footprint, obj.height_m, obj)
            if (total_count <= MAX_3D_LABEL_OBJECTS or selected) and self.state.label_visible_for(obj.object_id) and obj.name:
                self._draw_text(painter, obj.name, cx, cy, obj.height_m + 0.5)
        self._fast_object_render = False
    def _fill_screen_hull(self, painter: QPainter, pts: list[QPointF], color: QColor) -> None:
        if len(pts) < 3:
            return
        hull = convex_hull([(p.x(), p.y()) for p in pts])
        if len(hull) >= 3:
            painter.setBrush(color)
            painter.drawPolygon(QPolygonF([QPointF(x, y) for x, y in hull]))
    def _draw_sphere(self, painter: QPainter, obj, cx: float, cy: float, selected: bool = False) -> None:
        # Glatte Projektions-Silhouette einer Kugel/Ellipsoid. Nicht als
        # gestapelte Pyramidenringe zeichnen, sonst entsteht je nach Blickwinkel
        # eine spitze/rautenförmige Form.
        rx = max(obj.width_m, 0.2) * 0.5
        ry = max(obj.depth_m or obj.width_m, 0.2) * 0.5
        rz = max(obj.height_m, 0.1) * 0.5
        center_z = rz
        samples: list[tuple[float, float, float]] = []
        for j in range(0, 19):
            phi = -pi * 0.5 + pi * j / 18.0
            cp = cos(phi)
            z = center_z + rz * sin(phi)
            for i in range(72):
                a = 2.0 * pi * i / 72.0
                x = cx + rx * cp * cos(a)
                y = cy + ry * cp * sin(a)
                samples.append(self._tilted_point(obj, x, y, z, cx, cy))
        projected = [self._project(x, y, z) for x, y, z in samples]
        if len(projected) < 3:
            return
        hull_xy = convex_hull([(p.x(), p.y()) for p in projected])
        if len(hull_xy) < 3:
            return
        base_color = QColor(obj.color or TREE_KINDS.get(obj.kind_key, TREE_KINDS['custom']).color)
        painter.setPen(QPen(QColor(255, 255, 255) if selected else QColor(30, 70, 30), 2 if selected else 1))
        painter.setBrush(base_color)
        painter.drawPolygon(QPolygonF([QPointF(x, y) for x, y in hull_xy]))

        # Dezente sichtbare Breiten-/Höhenringe, damit die Kugel als Volumen
        # erkennbar bleibt, aber keine transparenten Rückseiten simuliert werden.
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor(30, 70, 30, 150), 1))
        for t in (0.25, 0.50, 0.75):
            phi = -pi * 0.5 + pi * t
            cp = cos(phi)
            z = center_z + rz * sin(phi)
            pts = []
            for i in range(73):
                a = 2.0 * pi * i / 72.0
                x = cx + rx * cp * cos(a)
                y = cy + ry * cp * sin(a)
                tx, ty, tz = self._tilted_point(obj, x, y, z, cx, cy)
                pts.append(self._project(tx, ty, tz))
            painter.drawPolyline(QPolygonF(pts))
        for angle in (0.0, pi * 0.5):
            pts = []
            for j in range(1, 36):
                phi = -pi * 0.5 + pi * j / 36.0
                x = cx + rx * cos(phi) * cos(angle)
                y = cy + ry * cos(phi) * sin(angle)
                z = center_z + rz * sin(phi)
                tx, ty, tz = self._tilted_point(obj, x, y, z, cx, cy)
                pts.append(self._project(tx, ty, tz))
            painter.drawPolyline(QPolygonF(pts))


    def _draw_layered_body(self, painter: QPainter, obj, cx: float, cy: float) -> None:
        layers = [[self._tilted_point(obj, x + cx, y + cy, z, cx, cy) for x, y in pts] for z, pts in object_body_layers_local_m(obj)]
        base_color = painter.brush().color()
        selected = bool(obj and (obj.object_id == self.state.selected_object_id or obj.object_id in getattr(self.state, "selected_object_ids", [])))
        if self._fast_object_render and not selected:
            projected = [self._project(x, y, z) for layer in layers for x, y, z in layer]
            self._fill_screen_hull(painter, projected, base_color)
            return
        faces = []
        for pts1, pts2 in zip(layers, layers[1:]):
            count = min(len(pts1), len(pts2))
            for i in range(count):
                pts4 = [pts1[i], pts1[(i + 1) % count], pts2[(i + 1) % count], pts2[i]]
                depth = sum(self._rotate3(x, y, z)[2] for x, y, z in pts4) / 4.0
                faces.append((depth, QPolygonF([self._project(x, y, z) for x, y, z in pts4])))
        for _depth, face in sorted(faces, key=lambda f: f[0]):
            painter.setBrush(QColor(base_color).darker(108)); painter.drawPolygon(face)
        if layers and len(layers[-1]) >= 3:
            painter.setBrush(base_color); painter.drawPolygon(QPolygonF([self._project(x, y, z) for x, y, z in layers[-1]]))
    def _tilted_point(self, obj, x: float, y: float, z: float, cx: float = 0.0, cy: float = 0.0) -> tuple[float, float, float]:
        # Echte Starrkörper-Rotation um die Basis (cx, cy, 0) statt Scherung:
        # Das Objekt behält seine Maße und Fläche, nur der Winkel ändert sich.
        tilt = radians(obj.tilt_deg)
        if abs(tilt) < 1e-9:
            return x, y, z
        angle = radians(obj.orientation_deg + obj.rotation_z_deg)
        dir_x, dir_y = sin(angle), cos(angle)
        lx, ly = x - cx, y - cy
        along = lx * dir_x + ly * dir_y
        perp_x, perp_y = lx - along * dir_x, ly - along * dir_y
        along_rot = along * cos(tilt) + z * sin(tilt)
        z_rot = z * cos(tilt) - along * sin(tilt)
        return cx + perp_x + along_rot * dir_x, cy + perp_y + along_rot * dir_y, z_rot
    def _draw_prism(self, painter: QPainter, footprint: list[tuple[float, float]], height: float, obj=None) -> None:
        pivot_x = pivot_y = 0.0
        if obj is not None and footprint:
            xs = [p[0] for p in footprint]; ys = [p[1] for p in footprint]
            pivot_x = (min(xs) + max(xs)) * 0.5; pivot_y = (min(ys) + max(ys)) * 0.5
        if len(footprint) == 2:
            a, b = footprint
            at = self._tilted_point(obj, a[0], a[1], height, pivot_x, pivot_y) if obj else (a[0], a[1], height)
            bt = self._tilted_point(obj, b[0], b[1], height, pivot_x, pivot_y) if obj else (b[0], b[1], height)
            painter.drawPolygon(QPolygonF([self._project(*a, 0.0), self._project(*b, 0.0), self._project(*bt), self._project(*at)]))
            return
        if len(footprint) < 3:
            return
        top3 = [self._tilted_point(obj, x, y, height, pivot_x, pivot_y) if obj else (x, y, height) for x, y in footprint]
        bottom = [self._project(x, y, 0.0) for x, y in footprint]
        top = [self._project(x, y, z) for x, y, z in top3]
        base_color = painter.brush().color()
        selected = bool(obj and (obj.object_id == self.state.selected_object_id or obj.object_id in getattr(self.state, "selected_object_ids", [])))
        if self._fast_object_render and not selected:
            hull = convex_hull([(p.x(), p.y()) for p in (bottom + top)])
            if len(hull) >= 3:
                painter.setBrush(base_color)
                painter.drawPolygon(QPolygonF([QPointF(x, y) for x, y in hull]))
            return
        faces = []
        for i in range(len(footprint)):
            p1, p2 = footprint[i], footprint[(i + 1) % len(footprint)]
            t1, t2 = top3[i], top3[(i + 1) % len(top3)]
            depth = sum(self._rotate3(x, y, z)[2] for x, y, z in [(p1[0], p1[1], 0), (p2[0], p2[1], 0), t2, t1]) / 4.0
            faces.append((depth, QPolygonF([bottom[i], bottom[(i + 1) % len(bottom)], top[(i + 1) % len(top)], top[i]])))
        painter.setBrush(base_color); painter.drawPolygon(QPolygonF(top))
        for _depth, face in sorted(faces, key=lambda f: f[0]):
            side_color = QColor(base_color); side_color = side_color.darker(112)
            painter.setBrush(side_color); painter.drawPolygon(face)
    def _draw_tree(self, painter: QPainter, obj, cx: float, cy: float, color: QColor, selected: bool = False) -> None:
        trunk = max(0.0, obj.trunk_diameter_m)
        crown_bottom = max(0.0, obj.height_m - max(obj.crown_height_m, obj.height_m * 0.55))
        if trunk > 0.02 and crown_bottom > 0.05:
            painter.setPen(QPen(QColor(80, 55, 35), 1))
            painter.setBrush(QColor(95, 67, 40))
            radius = trunk * 0.5
            circle = [(cx + cos(2 * pi * i / 20) * radius, cy + sin(2 * pi * i / 20) * radius) for i in range(20)]
            self._draw_prism(painter, circle, crown_bottom, obj)
        painter.setPen(QPen(QColor(20, 70, 20), 1))
        painter.setBrush(QColor(color))
        layers = [[self._tilted_point(obj, x + cx, y + cy, z, cx, cy) for x, y in pts] for z, pts in object_body_layers_local_m(obj) if z >= crown_bottom]
        for pts1, pts2 in zip(layers, layers[1:]):
            count = min(len(pts1), len(pts2))
            for i in range(count):
                a = self._project(*pts1[i])
                b = self._project(*pts1[(i + 1) % count])
                c = self._project(*pts2[(i + 1) % count])
                d = self._project(*pts2[i])
                painter.drawPolygon(QPolygonF([a, b, c, d]))
        if layers:
            painter.drawPolygon(QPolygonF([self._project(x, y, z) for x, y, z in layers[-1]]))
        if selected and layers:
            painter.setPen(QPen(QColor(255, 255, 255), 3))
            for pts in (layers[0], layers[-1]):
                if len(pts) >= 3:
                    painter.drawPolyline(QPolygonF([self._project(x, y, z) for x, y, z in pts + [pts[0]]]))
    def _draw_custom_draft(self, painter: QPainter) -> None:
        if len(self.pending_custom) < 2: return
        painter.setPen(QPen(QColor(255,255,255), 2, Qt.PenStyle.DashLine)); painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPolyline(QPolygonF([self._project(x, y, 0.05) for x, y in self.pending_custom]))
    def _draw_selected_mesh(self, painter: QPainter, origin: tuple[float, float]) -> None:
        obj = self.state.selected_object()
        if obj is None or not self.mesh_edit:
            return
        handles = self._mesh_handles(origin)
        if not handles:
            return
        if not obj.is_tree():
            painter.setPen(QPen(QColor(255, 255, 255), 2, Qt.PenStyle.DashLine))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            vertices = [(x, y, z) for role, x, y, z in handles if role.startswith("vertex:")]
            if len(vertices) >= 2:
                pts = vertices + [vertices[0]]
                painter.drawPolyline(QPolygonF([self._project(x, y, z) for x, y, z in pts]))
            elif len(handles) >= 4:
                coords = {role: (x, y, z) for role, x, y, z in handles}
                left = coords.get("left"); right = coords.get("right"); top = coords.get("top"); bottom = coords.get("bottom")
                if left and right and top and bottom:
                    z = max(p[2] for p in coords.values())
                    rect = [(left[0], bottom[1]), (right[0], bottom[1]), (right[0], top[1]), (left[0], top[1]), (left[0], bottom[1])]
                    painter.drawPolyline(QPolygonF([self._project(x, y, z) for x, y in rect]))
        self._draw_mesh_handle_points(painter, origin)
    def _draw_mesh_handle_points(self, painter: QPainter, origin: tuple[float, float]) -> None:
        painter.setPen(QPen(QColor(20, 20, 20), 1))
        colors = {"height": QColor(230, 230, 120), "trunk": QColor(120, 80, 45), "crown_height": QColor(120, 190, 90)}
        for role, x, y, z in self._mesh_handles(origin):
            painter.setBrush(colors.get(role, QColor(255, 255, 255, 240)))
            size = 11.5 if role in {"scale", "height"} else 9.0
            painter.drawEllipse(self._project(x, y, z), size, size)
    def _mesh_handles(self, origin: tuple[float, float]):
        obj = self.state.selected_object()
        if obj is None:
            return []
        cx, cy = latlon_to_local_m(obj.lat, obj.lon, origin[0], origin[1])
        if obj.is_tree():
            crown_h = min(max(obj.crown_height_m or obj.height_m * 0.55, 0.1), obj.height_m)
            crown_bottom = max(0.0, obj.height_m - crown_h)
            handles = [(role, x + cx, y + cy, z) for role, x, y, z in edit_handles_local(obj)]
            ca, sa = cos(radians(obj.orientation_deg + obj.rotation_z_deg)), sin(radians(obj.orientation_deg + obj.rotation_z_deg))
            def rp(px, py): return cx + px * ca - py * sa, cy + px * sa + py * ca
            trunk = rp(max(obj.trunk_diameter_m, 0.05) * 0.5, 0)
            handles.extend([("height", cx, cy, obj.height_m), ("trunk", *trunk, crown_bottom * 0.5), ("crown_height", cx, cy, crown_bottom)])
            return handles
        handles = [(role, x + cx, y + cy, z) for role, x, y, z in edit_handles_local(obj)]
        if not any(role == "height" for role, *_ in handles):
            handles.append(("height", cx, cy, max(obj.height_m, 0.1)))
        return handles
    def _hit_mesh_handle(self, pos: QPointF):
        origin = self._origin()
        for role, x, y, z in self._mesh_handles(origin):
            if (self._project(x, y, z) - pos).manhattanLength() <= 16:
                return role, x, y, z
        return None
    def _emit_drag_update(self) -> None:
        now = monotonic()
        if now - self._last_drag_emit >= 0.06:
            self._last_drag_emit = now
            self.invalidate_shadow_cache(); self.mesh_edited.emit()
    def _screen_delta_to_world(self, delta: QPoint) -> tuple[float, float]:
        p0 = self._project(0, 0, 0); vx = self._project(1, 0, 0) - p0; vy = self._project(0, 1, 0) - p0
        det = vx.x() * vy.y() - vx.y() * vy.x()
        if abs(det) < 0.001: return delta.x() / max(self.zoom, 0.1), delta.y() / max(self.zoom, 0.1)
        return (delta.x() * vy.y() - delta.y() * vy.x()) / det, (vx.x() * delta.y() - vx.y() * delta.x()) / det
    def _restore_drag_object(self, obj: ShadowObject) -> None:
        data = self._drag_start_data
        if not data:
            return
        for key, value in data.items():
            if key == "footprint_m":
                setattr(obj, key, [tuple(p) for p in value])
            else:
                setattr(obj, key, value)

    def _move_mesh_handle(self, delta: QPoint, pos: QPointF) -> None:
        obj = self.state.selected_object()
        if obj is None or self._drag_handle is None:
            return
        role = str(self._drag_handle)
        # Statt absolute Mausposition direkt zu verwenden, wird immer vom
        # Startzustand aus gerechnet. Dadurch springen Baumkronen und Körper
        # beim ersten Pixel Drag nicht mehr zusammen.
        start_pos = self._drag_start_pos or QPointF(pos)
        self._restore_drag_object(obj)
        total = pos.toPoint() - start_pos.toPoint()
        dx, dy = self._screen_delta_to_world(total)
        lx = self._drag_start_handle_local[0] + dx
        ly = self._drag_start_handle_local[1] + dy
        if role == "height":
            obj.height_m = max(0.1, obj.height_m - total.y() / max(self.zoom, 0.1) * 0.45)
            if obj.kind_key == "cube":
                obj.width_m = obj.depth_m = obj.height_m
            obj.crown_height_m = min(max(obj.crown_height_m, 0.0), obj.height_m)
        elif role == "crown_height" and obj.is_tree():
            obj.crown_height_m = min(obj.height_m, max(0.1, obj.crown_height_m - total.y() / max(self.zoom, 0.1) * 0.45))
        elif role == "trunk" and obj.is_tree():
            obj.trunk_diameter_m = max(0.0, sqrt(lx * lx + ly * ly) * 2.0)
        else:
            apply_handle_drag(obj, role, lx, ly)
            if obj.kind_key == "cube":
                v = max(obj.width_m, obj.depth_m or 0.0, obj.height_m, 0.1)
                obj.width_m = obj.depth_m = obj.height_m = v
        self.update()

    def _finish_custom_object(self) -> None:
        if len(self.pending_custom) >= 2:
            cx, cy = polygon_centroid(self.pending_custom)
            fp = [(x - cx, y - cy) for x, y in self.pending_custom]
            lat, lon = local_m_to_latlon(cx, cy, self.origin_latlon[0], self.origin_latlon[1])
            obj = ShadowObject.from_custom_polygon(lat, lon, fp)
            self.state.objects.append(obj)
            self.state.set_single_selection(obj.object_id)
            self.state.ground_selected = False
            self.mesh_edited.emit(); self.object_selected.emit()
        self.pending_custom = []
        self.drawing_custom = False
        self.update()
    def _handle_custom_drawing(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.pending_custom.append(self._screen_to_ground(event.position()))
            self.update(); return
        # Abschluss nur per Enter. Rechte Maustaste bleibt zur Navigation frei.
    def mouseDoubleClickEvent(self, event) -> None:
        if self.drawing_custom:
            return
        super().mouseDoubleClickEvent(event)
    def _select_obj(self, obj, ctrl: bool = False) -> bool:
        self.state.ground_selected = False
        if ctrl:
            ids = list(getattr(self.state, "selected_object_ids", []))
            if obj.object_id in ids:
                ids.remove(obj.object_id)
            else:
                ids.append(obj.object_id)
            self.state.selected_object_ids = ids
            self.state.selected_object_id = ids[-1] if ids else None
        else:
            self.state.set_single_selection(obj.object_id)
        self.object_selected.emit(); self.update(); return True
    def _select_object_at(self, pos: QPointF, ctrl: bool = False) -> bool:
        origin = self._origin()
        entries = []
        for obj in self.state.objects:
            cx, cy = latlon_to_local_m(obj.lat, obj.lon, origin[0], origin[1])
            _sx, _sy, depth = self._rotate3(cx, cy, obj.height_m * 0.5)
            entries.append((depth, obj, cx, cy))
        for _depth, obj, cx, cy in sorted(entries, key=lambda e: e[0], reverse=True):
            if hit_projected_object(self, obj, cx, cy, pos):
                return self._select_obj(obj, ctrl)
            footprint = [(x + cx, y + cy) for x, y in object_footprint_local_m(obj)]
            if len(footprint) == 2:
                a = self._project(*footprint[0], obj.height_m * 0.5)
                b = self._project(*footprint[1], obj.height_m * 0.5)
                if min(a.x(), b.x()) - 5 <= pos.x() <= max(a.x(), b.x()) + 5 and min(a.y(), b.y()) - 5 <= pos.y() <= max(a.y(), b.y()) + 5:
                    return self._select_obj(obj, ctrl)
        return False
    def _clear_selection(self) -> None:
        if self.state.selected_object_id or self.state.ground_selected or getattr(self.state, "selected_object_ids", []):
            self.state.set_single_selection(None)
            self.state.ground_selected = False
            self.object_selected.emit()
            self.update()
    def _screen_to_ground(self, pos: QPointF) -> tuple[float, float]:
        p0 = self._project(0, 0, 0)
        vx = self._project(1, 0, 0) - p0
        vy = self._project(0, 1, 0) - p0
        px, py = pos.x() - p0.x(), pos.y() - p0.y()
        det = vx.x() * vy.y() - vx.y() * vy.x()
        if abs(det) < 0.001:
            return px / max(self.zoom, 0.1), py / max(self.zoom, 0.1)
        x = (px * vy.y() - py * vy.x()) / det
        y = (vx.x() * py - vx.y() * px) / det
        return x, y
    def _place_object(self, pos: QPointF) -> None:
        if not self.add_kind_key:
            return
        origin = self._origin()
        x, y = self._screen_to_ground(pos)
        lat, lon = local_m_to_latlon(x, y, origin[0], origin[1])
        obj = ShadowObject.from_kind(self.add_kind_key, lat, lon)
        self.state.objects.append(obj)
        self.state.set_single_selection(obj.object_id)
        self.state.ground_selected = False
        self.add_kind_key = None
        self.object_selected.emit()
        self.mesh_edited.emit()
        self.update()
    def _move_selected_object(self, delta: QPoint) -> None:
        obj = self.state.selected_object()
        if obj is None:
            return
        origin = self._origin()
        dx, dy = self._screen_delta_to_world(delta)
        x, y = latlon_to_local_m(obj.lat, obj.lon, origin[0], origin[1])
        obj.lat, obj.lon = local_m_to_latlon(x + dx, y + dy, origin[0], origin[1])
    def keyPressEvent(self, event) -> None:
        if self.drawing_custom and event.key() in {Qt.Key.Key_Return, Qt.Key.Key_Enter}:
            self._finish_custom_object(); return
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier and event.key() == Qt.Key.Key_C:
            copy_selected(self); return
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier and event.key() == Qt.Key.Key_V:
            if paste_copied(self, self._last_mouse_pos):
                self.object_selected.emit(); self.mesh_edited.emit(); self.update()
            return
        super().keyPressEvent(event)
    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        rect = self._gizmo_rect()
        self.reset_button.resize(150, 28)
        self.reset_button.move(int(rect.left() + 5), int(rect.bottom() + 8))
    def _draw_text(self, painter: QPainter, text: str, x: float, y: float, z: float) -> None:
        p = self._project(x, y, z)
        painter.setPen(QPen(QColor(20, 20, 20), 1))
        painter.drawText(p + QPointF(4, -4), text)
    def _gizmo_rect(self) -> QRectF:
        size = 160.0
        return QRectF(self.width() - size - 18.0, 18.0, size, size)
