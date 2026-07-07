from __future__ import annotations
from math import floor
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QPolygonF, QFont
from PySide6.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsLineItem,
    QGraphicsPixmapItem,
    QGraphicsPolygonItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
    QGraphicsView,
)
from config import DEFAULT_LAT, DEFAULT_LON, DEFAULT_ZOOM, TILE_SIZE
from core.geometry import latlon_polygon_area_m2, latlon_to_local_m, local_m_to_latlon, polygon_area_m2, polygon_centroid
from core.objects import ShadowObject, SimulationState, TREE_KINDS
from core.mesh_edit import apply_handle_drag, edit_handles_local
from core.simulation import (
    object_footprint_latlon,
    effective_ground_area_m2,
    object_ground_contact_local_m,
    object_shadow_areas_m2,
    shadow_area_m2,
    shadow_area_raw_m2,
    shadow_union_polygons_by_density_latlon,
    total_shadow_area_m2,
    total_shadow_on_ground_m2,
)
from i18n import I18n
from osm.mercator import global_px_to_latlon, latlon_to_global_px, meters_per_pixel, tile_count
from osm.tile_manager import TileManager

MAX_MAP_SHADOW_OBJECTS = 350
MAX_MAP_LABEL_OBJECTS = 250

class MapCanvas(QGraphicsView):
    state_changed = Signal()
    object_selected = Signal()
    status_message = Signal(str)
    zoom_changed = Signal(int)
    center_changed = Signal(float, float, int)
    mode_changed = Signal(str, bool)
    def __init__(self, state: SimulationState, i18n: I18n, parent=None) -> None:
        super().__init__(parent)
        self.state = state
        self.i18n = i18n
        self.lat = DEFAULT_LAT
        self.lon = DEFAULT_LON
        self.zoom = DEFAULT_ZOOM
        self.max_tile_zoom = 19
        self.tile_manager = TileManager(parent=self)
        self.tile_manager.tile_ready.connect(self._tile_ready)
        self.tile_items: dict[tuple[int, int, int], QGraphicsPixmapItem] = {}
        self.overlay_items: list[QGraphicsItem] = []
        self.add_kind_key: str | None = None
        self.drawing_ground = False
        self.drawing_custom = False
        self.mesh_edit = False
        self.ground_edit = False
        self.pending_ground: list[tuple[float, float]] = []
        self.pending_custom: list[tuple[float, float]] = []
        self._drag_object_id: str | None = None
        self._drag_handle: tuple[str, str] | None = None
        self._drag_ground_index: int | None = None
        self._right_pan_active = False
        self._right_pan_last = None
        self.scene_obj = QGraphicsScene(self)
        self.setScene(self.scene_obj)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.horizontalScrollBar().valueChanged.connect(lambda _: self._view_moved())
        self.verticalScrollBar().valueChanged.connect(lambda _: self._view_moved())
        self._apply_scene_rect()
        self.center_on_latlon(self.lat, self.lon)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
    def set_language(self, i18n: I18n) -> None:
        self.i18n = i18n
        self.redraw_overlays()
    def set_sun(self, azimuth_deg: float, altitude_deg: float) -> None:
        self.state.sun_azimuth_deg = azimuth_deg
        self.state.sun_altitude_deg = altitude_deg
        self.redraw_overlays()
        self.state_changed.emit()
    def set_mesh_edit(self, enabled: bool) -> None:
        self.mesh_edit = enabled
        self.redraw_overlays()
    def set_ground_edit(self, enabled: bool) -> None:
        self.ground_edit = enabled
        if enabled and len(self.state.ground_polygon) >= 3:
            self.state.ground_selected = True
            self.state.set_single_selection(None)
        self.redraw_overlays()
    def set_show_labels(self, enabled: bool) -> None:
        self.state.show_labels = enabled
        self.redraw_overlays()
    def set_label_mode(self, mode: str) -> None:
        self.state.label_mode = mode
        self.redraw_overlays()
    def set_offline_only(self, enabled: bool) -> None:
        self.tile_manager.set_offline_only(enabled)
        self.update_tiles()
    def set_add_mode(self, kind_key: str | None) -> None:
        self.add_kind_key = kind_key
        self.drawing_ground = False
        self.drawing_custom = False
        self.pending_custom = []
        self.setDragMode(QGraphicsView.DragMode.NoDrag if kind_key else QGraphicsView.DragMode.ScrollHandDrag)
        self.status_message.emit(self.i18n.t("status.add_mode") if kind_key else self.i18n.t("status.ready"))
        self.mode_changed.emit("add", bool(kind_key))
    def set_ground_mode(self, enabled: bool) -> None:
        self.drawing_ground = enabled
        self.drawing_custom = False
        self.add_kind_key = None
        self.pending_ground = list(self.state.ground_polygon) if enabled and self.state.ground_selected and len(self.state.ground_polygon) >= 3 else []
        self.setDragMode(QGraphicsView.DragMode.NoDrag if enabled else QGraphicsView.DragMode.ScrollHandDrag)
        self.status_message.emit(self.i18n.t("status.ground_mode") if enabled else self.i18n.t("status.ready"))
        self.mode_changed.emit("ground", enabled)
        self.redraw_overlays()
    def set_custom_mode(self, enabled: bool) -> None:
        self.drawing_custom = enabled
        self.drawing_ground = False
        self.add_kind_key = None
        self.pending_custom = []
        self.setDragMode(QGraphicsView.DragMode.NoDrag if enabled else QGraphicsView.DragMode.ScrollHandDrag)
        self.status_message.emit(self.i18n.t("status.custom_mode") if enabled else self.i18n.t("status.ready"))
        self.mode_changed.emit("custom", enabled)
        self.redraw_overlays()
    def clear_ground(self) -> None:
        self.state.ground_polygon = []
        self.state.ground_selected = False
        self.pending_ground = []
        self.ground_edit = False
        self.drawing_ground = False
        self.mode_changed.emit("ground", False)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.redraw_overlays()
        self.state_changed.emit()
    def center_on_latlon(self, lat: float, lon: float) -> None:
        self.lat = lat
        self.lon = lon
        x, y = latlon_to_global_px(lat, lon, self.zoom)
        self.centerOn(x, y)
        self.update_tiles()
        self.redraw_overlays()
        self._emit_center_changed()
    def set_zoom(self, zoom: int, anchor_pos=None) -> None:
        new_zoom = max(1, min(21, zoom))
        if new_zoom == self.zoom:
            return
        if anchor_pos is None:
            old_lat, old_lon = self.center_latlon()
            self.zoom = new_zoom
            self._apply_scene_rect()
            self.center_on_latlon(old_lat, old_lon)
        else:
            anchor_scene = self.mapToScene(anchor_pos)
            anchor_lat, anchor_lon = global_px_to_latlon(anchor_scene.x(), anchor_scene.y(), self.zoom)
            viewport_center = QPointF(self.viewport().rect().center())
            offset = QPointF(anchor_pos) - viewport_center
            self.zoom = new_zoom
            self._apply_scene_rect()
            new_x, new_y = latlon_to_global_px(anchor_lat, anchor_lon, self.zoom)
            self.centerOn(QPointF(new_x, new_y) - offset)
            self.update_tiles()
            self.redraw_overlays()
        self.zoom_changed.emit(self.zoom)
        self._emit_center_changed()
    def center_latlon(self) -> tuple[float, float]:
        p = self.mapToScene(self.viewport().rect().center())
        return global_px_to_latlon(p.x(), p.y(), self.zoom)
    def _emit_center_changed(self) -> None:
        try:
            lat, lon = self.center_latlon()
            self.center_changed.emit(lat, lon, self.zoom)
        except Exception:
            pass
    def visible_bbox(self) -> tuple[float, float, float, float]:
        rect = self.mapToScene(self.viewport().rect()).boundingRect()
        lat1, lon1 = global_px_to_latlon(rect.left(), rect.top(), self.zoom)
        lat2, lon2 = global_px_to_latlon(rect.right(), rect.bottom(), self.zoom)
        return min(lat1, lat2), min(lon1, lon2), max(lat1, lat2), max(lon1, lon2)
    def selected_area_m2(self) -> float:
        if self.state.ground_selected and len(self.state.ground_polygon) >= 3:
            return self.ground_area()
        objs = self.state.selected_objects()
        if not objs:
            return 0.0
        area = 0.0
        for obj in objs:
            pts = object_ground_contact_local_m(obj)
            if len(pts) >= 3:
                area += polygon_area_m2(pts)
        return area
    def selected_shadow_area_with_ground(self) -> float:
        objs = self.state.selected_objects()
        if not objs:
            return self.total_shadow_on_ground() if self.state.ground_selected else 0.0
        return sum(shadow_area_raw_m2(obj, self.state.sun_azimuth_deg, self.state.sun_altitude_deg) for obj in objs)
    def selected_shadow_area(self) -> float:
        objs = self.state.selected_objects()
        if not objs:
            return self.total_shadow_on_ground() if self.state.ground_selected else 0.0
        return sum(shadow_area_m2(obj, self.state.sun_azimuth_deg, self.state.sun_altitude_deg) for obj in objs)
    def total_shadow_area(self) -> float:
        return total_shadow_area_m2(self.state.objects, self.state.sun_azimuth_deg, self.state.sun_altitude_deg)
    def total_shadow_on_ground(self) -> float:
        return total_shadow_on_ground_m2(
            self.state.objects,
            self.state.ground_polygon,
            self.state.sun_azimuth_deg,
            self.state.sun_altitude_deg,
        )
    def per_object_shadow_areas(self) -> dict[str, float]:
        return object_shadow_areas_m2(self.state.objects, self.state.sun_azimuth_deg, self.state.sun_altitude_deg)
    def ground_area_absolute(self) -> float:
        if len(self.state.ground_polygon) < 3:
            return 0.0
        origin = self.state.ground_polygon[0]
        pts = [latlon_to_local_m(lat, lon, origin[0], origin[1]) for lat, lon in self.state.ground_polygon]
        return polygon_area_m2(pts)
    def ground_area(self) -> float:
        return effective_ground_area_m2(self.state.objects, self.state.ground_polygon)
    def redraw_overlays(self) -> None:
        for item in self.overlay_items:
            self.scene_obj.removeItem(item)
        self.overlay_items = []
        self._draw_shadows()
        self._draw_ground()
        self._draw_custom_draft()
        self._draw_objects()
        self._draw_mesh_handles()
    def _tile_zoom(self) -> int:
        return min(self.zoom, self.max_tile_zoom)
    def _tile_scale(self) -> float:
        return float(2 ** max(0, self.zoom - self.max_tile_zoom))
    def _view_moved(self) -> None:
        self.update_tiles()
        self.viewport().update()
    def update_tiles(self) -> None:
        if not self.scene():
            return
        rect = self.mapToScene(self.viewport().rect()).boundingRect()
        tile_zoom = self._tile_zoom()
        tile_scale = self._tile_scale()
        span = TILE_SIZE * tile_scale
        max_tile = tile_count(tile_zoom) - 1
        min_x = max(0, floor(rect.left() / span))
        max_x = min(max_tile, floor(rect.right() / span))
        min_y = max(0, floor(rect.top() / span))
        max_y = min(max_tile, floor(rect.bottom() / span))
        needed = set()
        for x in range(min_x, max_x + 1):
            for y in range(min_y, max_y + 1):
                key = (self.zoom, x, y)
                needed.add(key)
                if key not in self.tile_items:
                    self.tile_manager.request_tile(tile_zoom, x, y)
        for key, item in list(self.tile_items.items()):
            if key not in needed or key[0] != self.zoom:
                self.scene_obj.removeItem(item)
                del self.tile_items[key]
        self._emit_center_changed()
    def _apply_scene_rect(self) -> None:
        size = TILE_SIZE * tile_count(self.zoom)
        self.scene_obj.setSceneRect(QRectF(0, 0, size, size))
        self.tile_manager.cancel_except_zoom(self._tile_zoom())
        self.tile_items.clear()
        self.scene_obj.clear()
        self.overlay_items = []
    def _tile_ready(self, z: int, x: int, y: int, pixmap) -> None:
        if z != self._tile_zoom():
            return
        key = (self.zoom, x, y)
        if key in self.tile_items:
            return
        scale = self._tile_scale()
        item = QGraphicsPixmapItem(pixmap)
        item.setTransformationMode(Qt.TransformationMode.FastTransformation)
        item.setScale(scale)
        item.setPos(x * TILE_SIZE * scale, y * TILE_SIZE * scale)
        item.setZValue(-100)
        self.scene_obj.addItem(item)
        self.tile_items[key] = item
    def _scene_latlon(self, pos: QPointF) -> tuple[float, float]:
        return global_px_to_latlon(pos.x(), pos.y(), self.zoom)
    def _latlon_point(self, lat: float, lon: float) -> QPointF:
        x, y = latlon_to_global_px(lat, lon, self.zoom)
        return QPointF(x, y)
    def _draw_shadows(self) -> None:
        # Exakte Schatten-Unionen sind bei großen Streets-GL-Importen der
        # teuerste Teil der interaktiven Karte. Die Flächenberechnung selbst
        # bleibt verfügbar; nur die Karten-Vorschau wird bei sehr vielen
        # Objekten übersprungen.
        if len(self.state.objects) > MAX_MAP_SHADOW_OBJECTS:
            return
        for density, polygons in shadow_union_polygons_by_density_latlon(self.state.objects, self.state.sun_azimuth_deg, self.state.sun_altitude_deg):
            for polygon in polygons:
                if len(polygon) < 3:
                    continue
                item = QGraphicsPolygonItem(QPolygonF([self._latlon_point(lat, lon) for lat, lon in polygon]))
                item.setPen(QPen(QColor(45, 45, 45, max(1, round(150 * density))), 1))
                item.setBrush(QColor(45, 45, 45, max(1, round(85 * density))))
                item.setZValue(20)
                self.scene_obj.addItem(item)
                self.overlay_items.append(item)
    def _draw_polygon_overlay(self, polygon: list[tuple[float, float]], color: QColor, z: int, dashed: bool = False):
        if not polygon:
            return None
        item = QGraphicsPolygonItem(QPolygonF([self._latlon_point(lat, lon) for lat, lon in polygon]))
        style = Qt.PenStyle.DashLine if dashed else Qt.PenStyle.SolidLine
        item.setPen(QPen(color, 3, style))
        fill = QColor(color)
        fill.setAlpha(45)
        item.setBrush(fill)
        item.setZValue(z)
        self.scene_obj.addItem(item)
        self.overlay_items.append(item)
        return item
    def _draw_ground(self) -> None:
        polygon = self.pending_ground if self.drawing_ground and self.pending_ground else self.state.ground_polygon
        item = self._draw_polygon_overlay(polygon, QColor(self.state.ground_color), 30, True)
        if item is not None and not self.drawing_ground:
            item.setData(1, "ground")
            if self.state.ground_selected:
                item.setPen(QPen(QColor(255, 255, 255), 4, Qt.PenStyle.DashLine))
            if self.state.label_visible_for(is_ground=True) and self.state.ground_name:
                self._draw_label(polygon, self.state.ground_name, 52)
            if self.ground_edit and self.state.ground_selected:
                self._draw_ground_handles(polygon)
    def _draw_custom_draft(self) -> None:
        if self.drawing_custom and self.pending_custom:
            self._draw_polygon_overlay(self.pending_custom, QColor(140, 90, 20), 35, True)
    def _draw_ground_handles(self, polygon: list[tuple[float, float]]) -> None:
        for idx, (lat, lon) in enumerate(polygon):
            p = self._latlon_point(lat, lon)
            size = 17.0
            item = QGraphicsEllipseItem(p.x() - size / 2.0, p.y() - size / 2.0, size, size)
            item.setBrush(QColor(255, 255, 255))
            item.setPen(QPen(QColor(20, 20, 20), 2))
            item.setZValue(70)
            item.setData(1, "ground_handle")
            item.setData(2, idx)
            self.scene_obj.addItem(item)
            self.overlay_items.append(item)
    def _draw_objects(self) -> None:
        for obj in self.state.objects:
            points = [self._latlon_point(lat, lon) for lat, lon in object_footprint_latlon(obj)]
            if len(points) < 2:
                continue
            kind = TREE_KINDS.get(obj.kind_key, TREE_KINDS["custom"])
            selected = obj.object_id == self.state.selected_object_id or obj.object_id in getattr(self.state, "selected_object_ids", [])
            pen_color = QColor(255, 255, 255) if selected else QColor(20, 70, 20)
            if len(points) == 2:
                item = QGraphicsLineItem(points[0].x(), points[0].y(), points[1].x(), points[1].y())
                item.setPen(QPen(pen_color if selected else QColor(obj.color or kind.color), 7 if selected else 4))
            else:
                item = QGraphicsPolygonItem(QPolygonF(points))
                item.setBrush(QColor(obj.color or kind.color))
                item.setPen(QPen(pen_color, 3 if selected else 1))
            item.setZValue(40)
            item.setData(0, obj.object_id)
            self.scene_obj.addItem(item)
            self.overlay_items.append(item)
            if (len(self.state.objects) <= MAX_MAP_LABEL_OBJECTS or selected) and self.state.label_visible_for(obj.object_id) and obj.name:
                self._draw_label(object_footprint_latlon(obj), obj.name, 65)
    def _draw_label(self, polygon: list[tuple[float, float]], text: str, z: int) -> None:
        if not polygon or not text:
            return
        lat = sum(p[0] for p in polygon) / len(polygon)
        lon = sum(p[1] for p in polygon) / len(polygon)
        item = QGraphicsSimpleTextItem(text)
        item.setBrush(QColor(20, 20, 20))
        item.setPos(self._latlon_point(lat, lon))
        item.setZValue(z)
        self.scene_obj.addItem(item)
        self.overlay_items.append(item)
    def _editable_handles(self, obj: ShadowObject) -> list[tuple[str, tuple[float, float]]]:
        handles = []
        for role, x, y, _z in edit_handles_local(obj):
            handles.append((role, local_m_to_latlon(x, y, obj.lat, obj.lon)))
        return handles
    def _draw_mesh_handles(self) -> None:
        obj = self.state.selected_object()
        if not self.mesh_edit or obj is None:
            return
        for role, (lat, lon) in self._editable_handles(obj):
            p = self._latlon_point(lat, lon)
            size = 18.0 if role == "scale" else 15.0
            item = QGraphicsEllipseItem(p.x() - size / 2.0, p.y() - size / 2.0, size, size)
            item.setBrush(QColor(255, 255, 255))
            item.setPen(QPen(QColor(20, 20, 20), 2))
            item.setZValue(60)
            item.setData(1, "mesh_handle")
            item.setData(0, obj.object_id)
            item.setData(2, role)
            self.scene_obj.addItem(item)
            self.overlay_items.append(item)
    def drawForeground(self, painter: QPainter, rect) -> None:
        super().drawForeground(painter, rect)
        painter.save(); painter.resetTransform()
        lat, _lon = self.center_latlon()
        mpp = max(0.001, meters_per_pixel(lat, self.zoom))
        candidates = [1, 2, 5, 10, 20, 30, 50, 100, 200, 500, 1000, 2000]
        length_m = next((m for m in candidates if 50 <= m / mpp <= 150), candidates[-1])
        px = length_m / mpp; x2 = self.viewport().width() - 28; y = self.viewport().height() - 44; x1 = x2 - px
        painter.setPen(QPen(QColor(20, 20, 20), 3)); painter.drawLine(QPointF(x1, y), QPointF(x2, y))
        painter.setFont(QFont(painter.font().family(), max(8, painter.font().pointSize())))
        painter.drawText(QPointF(x1, y - 8), f"{length_m:g} m")
        painter.setPen(QPen(QColor(20, 20, 20), 1)); painter.drawText(QPointF(12, self.viewport().height() - 22), self.i18n.t("status.tile_info"))
        painter.restore()
    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self.add_kind_key:
            lat, lon = self._scene_latlon(self.mapToScene(event.position().toPoint()))
            self._add_object(ShadowObject.from_kind(self.add_kind_key, lat, lon))
            self.status_message.emit(self.i18n.t("status.object_added"))
            return
        if self.drawing_ground or self.drawing_custom:
            if event.button() == Qt.MouseButton.RightButton:
                self._right_pan_active = True
                self._right_pan_last = event.position().toPoint()
                return
            if self.drawing_ground:
                self._handle_polygon_drawing(event, self.pending_ground, self.finish_ground)
                return
            if self.drawing_custom:
                self._handle_polygon_drawing(event, self.pending_custom, self.finish_custom_object)
                return
        if event.button() == Qt.MouseButton.LeftButton:
            item = self.itemAt(event.position().toPoint())
            if item and item.data(1) == "ground_handle":
                self._drag_ground_index = int(item.data(2))
                self.setDragMode(QGraphicsView.DragMode.NoDrag)
                return
            if item and item.data(1) == "mesh_handle":
                self._drag_handle = (item.data(0), str(item.data(2)))
                self.setDragMode(QGraphicsView.DragMode.NoDrag)
                return
            if item and item.data(1) == "ground":
                self.state.ground_selected = True
                self.state.set_single_selection(None)
                self.redraw_overlays()
                self.object_selected.emit()
                self.state_changed.emit()
                return
            object_id = item.data(0) if item else None
            if object_id:
                self.state.ground_selected = False
                if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                    ids = list(getattr(self.state, "selected_object_ids", []))
                    if object_id in ids:
                        ids.remove(object_id)
                    else:
                        ids.append(object_id)
                    self.state.selected_object_ids = ids
                    self.state.selected_object_id = ids[-1] if ids else None
                    self._drag_object_id = None
                else:
                    self.state.set_single_selection(object_id)
                    self._drag_object_id = object_id
                    self.setDragMode(QGraphicsView.DragMode.NoDrag)
                self.redraw_overlays()
                self.object_selected.emit()
                self.state_changed.emit()
                return
            if self.state.selected_object_id or self.state.ground_selected or getattr(self.state, "selected_object_ids", []):
                self.state.set_single_selection(None)
                self.state.ground_selected = False
                self.redraw_overlays()
                self.object_selected.emit()
                self.state_changed.emit()
        super().mousePressEvent(event)
    def mouseMoveEvent(self, event) -> None:
        if self._right_pan_active and self._right_pan_last is not None:
            point = event.position().toPoint()
            delta = point - self._right_pan_last
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - delta.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta.y())
            self._right_pan_last = point
            return
        if self._drag_handle:
            self._move_handle(self._drag_handle[0], self._drag_handle[1], event.position().toPoint())
            return
        if self._drag_ground_index is not None:
            if 0 <= self._drag_ground_index < len(self.state.ground_polygon):
                self.state.ground_polygon[self._drag_ground_index] = self._scene_latlon(self.mapToScene(event.position().toPoint()))
                self.redraw_overlays()
                self.state_changed.emit()
            return
        if self._drag_object_id:
            obj = self.state.object_by_id(self._drag_object_id)
            if obj is not None:
                obj.lat, obj.lon = self._scene_latlon(self.mapToScene(event.position().toPoint()))
                self.redraw_overlays()
                self.state_changed.emit()
            return
        super().mouseMoveEvent(event)
    def mouseReleaseEvent(self, event) -> None:
        if self._right_pan_active and event.button() == Qt.MouseButton.RightButton:
            self._right_pan_active = False
            self._right_pan_last = None
            self.update_tiles()
            return
        if self._drag_object_id or self._drag_handle or self._drag_ground_index is not None:
            self._drag_object_id = None
            self._drag_handle = None
            self._drag_ground_index = None
            self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
            self.update_tiles()
            self.object_selected.emit()
            self.state_changed.emit()
            return
        super().mouseReleaseEvent(event)
        self.update_tiles()
    def _move_handle(self, object_id: str, role: str, point) -> None:
        obj = self.state.object_by_id(object_id)
        if obj is None:
            return
        lat, lon = self._scene_latlon(self.mapToScene(point))
        x, y = latlon_to_local_m(lat, lon, obj.lat, obj.lon)
        apply_handle_drag(obj, role, x, y)
        self.redraw_overlays()
        self.state_changed.emit()
    def mouseDoubleClickEvent(self, event) -> None:
        if self.drawing_ground or self.drawing_custom:
            return
        super().mouseDoubleClickEvent(event)
    def keyPressEvent(self, event) -> None:
        if event.key() in {Qt.Key.Key_Return, Qt.Key.Key_Enter}:
            if self.drawing_ground:
                self.finish_ground()
                return
            if self.drawing_custom:
                self.finish_custom_object()
                return
        if event.key() == Qt.Key.Key_Escape:
            if self.drawing_ground:
                self.pending_ground = []
                self.drawing_ground = False
                self.mode_changed.emit("ground", False)
                self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
                self.redraw_overlays()
                self.state_changed.emit()
                return
            if self.drawing_custom:
                self.pending_custom = []
                self.drawing_custom = False
                self.mode_changed.emit("custom", False)
                self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
                self.redraw_overlays()
                self.state_changed.emit()
                return
        super().keyPressEvent(event)
    def undo_last_drawing_point(self) -> bool:
        if self.drawing_ground and self.pending_ground:
            self.pending_ground.pop()
            self.redraw_overlays()
            self.state_changed.emit()
            return True
        if self.drawing_custom and self.pending_custom:
            self.pending_custom.pop()
            self.redraw_overlays()
            self.state_changed.emit()
            return True
        return False
    def wheelEvent(self, event) -> None:
        delta = event.angleDelta().y()
        if delta > 0:
            self.set_zoom(self.zoom + 1, event.position().toPoint())
        elif delta < 0:
            self.set_zoom(self.zoom - 1, event.position().toPoint())
    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.update_tiles()
        self.redraw_overlays()
    def _handle_polygon_drawing(self, event, target: list[tuple[float, float]], finish_callback) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            lat, lon = self._scene_latlon(self.mapToScene(event.position().toPoint()))
            target.append((lat, lon))
            self.redraw_overlays()
            self.state_changed.emit()
            return
        # Abschluss nur per Enter. Rechte Maustaste bleibt zum Verschieben der Ansicht frei.
    def _add_object(self, obj: ShadowObject) -> None:
        self.state.objects.append(obj)
        self.state.ground_selected = False
        self.state.set_single_selection(obj.object_id)
        self.add_kind_key = None
        self.drawing_custom = False
        self.mode_changed.emit("add", False)
        self.mode_changed.emit("custom", False)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.redraw_overlays()
        self.object_selected.emit()
        self.state_changed.emit()
    def add_objects(self, objects: list[ShadowObject]) -> None:
        self.state.objects.extend(objects)
        if objects:
            self.state.ground_selected = False
            self.state.set_single_selection(objects[-1].object_id)
        self.redraw_overlays()
        self.object_selected.emit()
        self.state_changed.emit()
    def finish_ground(self) -> None:
        if len(self.pending_ground) >= 3:
            self.state.ground_polygon = list(self.pending_ground)
            self.state.ground_selected = True
            self.status_message.emit(self.i18n.t("status.ground_finished"))
        self.pending_ground = []
        self.drawing_ground = False
        self.mode_changed.emit("ground", False)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.redraw_overlays()
        self.state_changed.emit()
    def finish_custom_object(self) -> None:
        if len(self.pending_custom) >= 2:
            origin_lat = sum(p[0] for p in self.pending_custom) / len(self.pending_custom)
            origin_lon = sum(p[1] for p in self.pending_custom) / len(self.pending_custom)
            local = [latlon_to_local_m(lat, lon, origin_lat, origin_lon) for lat, lon in self.pending_custom]
            cx, cy = polygon_centroid(local)
            center_lat, center_lon = local_m_to_latlon(cx, cy, origin_lat, origin_lon)
            footprint = [(x - cx, y - cy) for x, y in local]
            self._add_object(ShadowObject.from_custom_polygon(center_lat, center_lon, footprint))
            self.status_message.emit(self.i18n.t("status.custom_finished"))
        self.pending_custom = []
        self.drawing_custom = False
        self.mode_changed.emit("custom", False)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.redraw_overlays()
        self.state_changed.emit()
