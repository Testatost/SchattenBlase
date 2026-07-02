from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QDate, QSignalBlocker, Qt, QTime, QTimer
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QFileDialog, QMessageBox

from config import PROJECT_DIR, OBJECT_DIR
from core.cleanup import remove_app_data
from core.history import restore_state, snapshot_state
from core.project import load_project, save_project
from core.exchange import export_object, import_objects
from core.storage import load_library
from osm.buildings import fetch_buildings_for_bbox
from osm.streets_gl import fetch_streetsgl_3d_for_bbox
from osm.geocode import search_places
from osm.offline import download_tiles


class MainWindowActions:
    def search_preview_place(self) -> None:
        try:
            results = search_places(self.map_search_edit.text())
            self.map_search_combo.clear()
            for item in results:
                self.map_search_combo.addItem(item.get("name", ""), item)
            if results:
                self.map_search_combo.setCurrentIndex(0)
                self._center_on_search_result(results[0])
            else:
                self.statusBar().showMessage(self.i18n.t("status.search_empty"))
        except Exception:
            self._warning("dialog.search_failed")

    def load_preview_search_result(self, *_args) -> None:
        item = self.map_search_combo.currentData()
        if item:
            self._center_on_search_result(item)

    def _center_on_search_result(self, item: dict) -> None:
        # Nominatim-Boundingboxes beschreiben oft eine ganze Gemeinde. Für die
        # Kartenzentrierung ist der Ergebnis-Mittelpunkt daher sichtbar genauer.
        lat = float(item.get("lat", self.controls.lat_spin.value()))
        lon = float(item.get("lon", self.controls.lon_spin.value()))
        zoom = 15
        with QSignalBlocker(self.controls.lat_spin), QSignalBlocker(self.controls.lon_spin), QSignalBlocker(self.controls.zoom_spin):
            self.controls.lat_spin.setValue(lat)
            self.controls.lon_spin.setValue(lon)
            self.controls.zoom_spin.setValue(zoom)
        self.preview_tabs.setCurrentIndex(0)
        self.canvas.set_zoom(zoom)
        self.canvas.center_on_latlon(lat, lon)
        for delay in (0, 80, 250, 600):
            QTimer.singleShot(delay, lambda la=lat, lo=lon, z=zoom: (self.canvas.set_zoom(z), self.canvas.center_on_latlon(la, lo)))
        self.apply_sun_from_datetime()

    def import_osm_buildings(self) -> None:
        try:
            south, west, north, east = self.canvas.visible_bbox()
        except Exception:
            self._warning("dialog.osm_import_failed")
            return

        try:
            buildings = fetch_streetsgl_3d_for_bbox(south, west, north, east)
        except Exception as exc:
            buildings = []
            fallback_reason = self.i18n.t("dialog.osm_fallback_reason_error", error=str(exc))
        else:
            fallback_reason = self.i18n.t("dialog.osm_fallback_reason_empty")

        if buildings:
            self.canvas.add_objects(buildings)
            self.statusBar().showMessage(self.i18n.t("status.streetsgl_imported", count=len(buildings)))
            return

        self.statusBar().showMessage(self.i18n.t("status.no_streetsgl_imported"))
        if not self._confirm_osm_fallback(fallback_reason):
            return

        try:
            fallback_buildings = fetch_buildings_for_bbox(south, west, north, east)
        except Exception:
            self._warning("dialog.osm_import_failed")
            return

        if fallback_buildings:
            self.canvas.add_objects(fallback_buildings)
            self.statusBar().showMessage(self.i18n.t("status.osm_fallback_imported", count=len(fallback_buildings)))
        else:
            self.statusBar().showMessage(self.i18n.t("status.no_buildings_imported"))

    def _confirm_osm_fallback(self, reason: str) -> bool:
        text = self.i18n.t("dialog.osm_fallback_text", reason=reason)
        result = QMessageBox.question(
            self,
            self.i18n.t("dialog.osm_fallback_title"),
            text,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return result == QMessageBox.StandardButton.Yes

    def download_visible_area(self) -> None:
        south, west, north, east = self.canvas.visible_bbox()
        self._download_bbox(south, west, north, east)

    def download_offline_place(self) -> None:
        try:
            results = search_places(self.controls.offline_query_edit.text(), limit=1)
            if not results:
                self._warning("dialog.search_failed")
                return
            bbox = results[0].get("bbox", [])
            if len(bbox) == 4:
                south, north, west, east = bbox
            else:
                lat, lon = results[0]["lat"], results[0]["lon"]
                south, west, north, east = lat - 0.02, lon - 0.02, lat + 0.02, lon + 0.02
            self._download_bbox(south, west, north, east)
        except Exception:
            self._warning("dialog.offline_failed")

    def _download_bbox(self, south: float, west: float, north: float, east: float) -> None:
        c = self.controls
        z_min, z_max = sorted([c.offline_zmin_spin.value(), c.offline_zmax_spin.value()])
        try:
            count = download_tiles(south, west, north, east, z_min, z_max)
            self.statusBar().showMessage(self.i18n.t("status.offline_downloaded", count=count))
            self.canvas.update_tiles()
        except ValueError as exc:
            self._warning("dialog.offline_too_large", count=str(exc))
        except Exception:
            self._warning("dialog.offline_failed")

    def save_project_file(self) -> None:
        PROJECT_DIR.mkdir(parents=True, exist_ok=True)
        path, _ = QFileDialog.getSaveFileName(self, self.i18n.t("dialog.save_project"), str(PROJECT_DIR / "projekt.schatten.json"), self.i18n.t("dialog.project_filter"))
        if not path:
            return
        try:
            lat, lon = self.canvas.center_latlon()
            save_project(Path(path), self.state, lat, lon, self.canvas.zoom)
            self.statusBar().showMessage(self.i18n.t("status.project_saved"))
        except Exception:
            self._warning("dialog.project_save_failed")

    def load_project_file(self) -> None:
        PROJECT_DIR.mkdir(parents=True, exist_ok=True)
        path, _ = QFileDialog.getOpenFileName(self, self.i18n.t("dialog.load_project"), str(PROJECT_DIR), self.i18n.t("dialog.project_filter"))
        if not path:
            return
        try:
            data = load_project(Path(path), self.state)
            self.canvas.set_zoom(int(data.get("zoom", self.canvas.zoom)))
            self.canvas.center_on_latlon(float(data.get("lat", self.canvas.lat)), float(data.get("lon", self.canvas.lon)))
            self.scene3d.set_origin(*self.canvas.center_latlon())
            self._sync_label_controls()
            self.canvas.redraw_overlays(); self.update_object_editor(); self.update_views()
            self.statusBar().showMessage(self.i18n.t("status.project_loaded"))
        except Exception:
            self._warning("dialog.project_load_failed")

    def import_object_file(self) -> None:
        OBJECT_DIR.mkdir(parents=True, exist_ok=True)
        path, _ = QFileDialog.getOpenFileName(self, self.i18n.t("dialog.import_object"), str(OBJECT_DIR), self.i18n.t("dialog.object_filter"))
        if not path:
            return
        try:
            lat, lon = self.canvas.center_latlon()
            objects = import_objects(Path(path), lat, lon)
            self.canvas.add_objects(objects)
            self.statusBar().showMessage(self.i18n.t("status.objects_imported", count=len(objects)))
        except Exception:
            self._warning("dialog.object_import_failed")

    def export_selected_object(self) -> None:
        obj = self.state.selected_object()
        if obj is None:
            self._warning("dialog.no_object_selected")
            return
        default = f"{obj.name or obj.kind_key}.json"
        OBJECT_DIR.mkdir(parents=True, exist_ok=True)
        path, _ = QFileDialog.getSaveFileName(self, self.i18n.t("dialog.export_object"), str(OBJECT_DIR / default), self.i18n.t("dialog.object_filter"))
        if not path:
            return
        try:
            export_object(Path(path), obj)
            self.statusBar().showMessage(self.i18n.t("status.object_exported"))
        except Exception:
            self._warning("dialog.object_export_failed")

    def update_speed_from_slider(self, value: int) -> None:
        with QSignalBlocker(self.controls.speed_spin):
            self.controls.speed_spin.setValue(value)
        self.timer.setInterval(value)

    def update_speed_from_spin(self, value: int) -> None:
        with QSignalBlocker(self.controls.speed_slider):
            self.controls.speed_slider.setValue(value)
        self.timer.setInterval(value)

    def cleanup_program_data(self) -> None:
        answer = QMessageBox.question(self, self.i18n.t("dialog.confirm"), self.i18n.t("cleanup.confirm"))
        if answer != QMessageBox.StandardButton.Yes:
            return
        remove_app_data()
        self.library = load_library()
        self.controls.refresh_library(self.library)
        self.statusBar().showMessage(self.i18n.t("status.cleanup_done"))

    def _install_shortcuts(self) -> None:
        self._shortcuts = []
        for sequence, handler in [
            (QKeySequence(QKeySequence.StandardKey.Undo), self.undo_action),
            (QKeySequence(QKeySequence.StandardKey.Redo), self.redo_action),
            (QKeySequence(Qt.Key.Key_Delete), self.delete_selected),
            (QKeySequence(Qt.Key.Key_Return), self.confirm_keyboard_action),
            (QKeySequence(Qt.Key.Key_Enter), self.confirm_keyboard_action),
        ]:
            shortcut = QShortcut(sequence, self)
            shortcut.activated.connect(handler)
            self._shortcuts.append(shortcut)

    def confirm_keyboard_action(self) -> None:
        if self.focusWidget() is self.map_search_edit:
            self.search_preview_place()
        elif self.canvas.drawing_ground:
            self.canvas.finish_ground()
        elif self.canvas.drawing_custom:
            self.canvas.finish_custom_object()
        elif getattr(self.scene3d, "drawing_custom", False):
            self.scene3d._finish_custom_object()

    def undo_action(self) -> None:
        if getattr(self.canvas, "undo_last_drawing_point", lambda: False)():
            return
        if not self.undo_stack:
            return
        self.redo_stack.append(snapshot_state(self.state))
        self._restore_snapshot(self.undo_stack.pop())

    def redo_action(self) -> None:
        if not self.redo_stack:
            return
        self.undo_stack.append(snapshot_state(self.state))
        self._restore_snapshot(self.redo_stack.pop())

    def _restore_snapshot(self, snap: dict) -> None:
        self._restoring = True
        restore_state(self.state, snap)
        self._last_snapshot = snapshot_state(self.state)
        self._sync_label_controls()
        self.canvas.redraw_overlays()
        self.update_object_editor()
        self.update_metrics()
        self.scene3d.refresh()
        self._restoring = False

    def set_label_visibility(self, enabled: bool) -> None:
        self.state.show_labels = enabled
        self.canvas.set_show_labels(enabled)
        self.scene3d.refresh()
        self.update_views()

    def _sync_label_controls(self) -> None:
        idx = self.controls.label_mode_combo.findData(getattr(self.state, "label_mode", "all"))
        if idx >= 0:
            with QSignalBlocker(self.controls.label_mode_combo):
                self.controls.label_mode_combo.setCurrentIndex(idx)
        with QSignalBlocker(self.controls.show_labels_check):
            self.controls.show_labels_check.setChecked(bool(getattr(self.state, "show_labels", True)))

    def set_label_mode(self) -> None:
        mode = self.controls.label_mode_combo.currentData() or "all"
        self.state.label_mode = mode
        self.canvas.set_label_mode(mode)
        self.scene3d.refresh()
        self.update_views()

    def scene3d_mesh_edited(self) -> None:
        if not getattr(self.scene3d, "drawing_custom", False):
            if self.canvas.drawing_custom:
                self.canvas.set_custom_mode(False)
            with QSignalBlocker(self.controls.draw_custom_button):
                self.controls.draw_custom_button.setChecked(False)
        self.canvas.redraw_overlays()
        self.update_object_editor()
        self.update_views()

    def apply_view_rotation(self) -> None:
        c = self.controls
        for slider, spin in [(c.axis_x_slider, c.axis_x_spin), (c.axis_y_slider, c.axis_y_spin), (c.axis_z_slider, c.axis_z_spin)]:
            with QSignalBlocker(slider):
                slider.setValue(int(spin.value()))
        self.scene3d.set_view_rotation(c.axis_x_spin.value(), c.axis_y_spin.value(), c.axis_z_spin.value())

    def apply_view_rotation_from_sliders(self) -> None:
        c = self.controls
        for spin, slider in [(c.axis_x_spin, c.axis_x_slider), (c.axis_y_spin, c.axis_y_slider), (c.axis_z_spin, c.axis_z_slider)]:
            with QSignalBlocker(spin):
                spin.setValue(slider.value())
        self.scene3d.set_view_rotation(c.axis_x_slider.value(), c.axis_y_slider.value(), c.axis_z_slider.value())

    def reset_view_rotation(self) -> None:
        self.scene3d.reset_view()
        self.sync_view_rotation_spins(self.scene3d.rot_x, self.scene3d.rot_y, self.scene3d.rot_z)

    def sync_view_rotation_spins(self, rx: float, ry: float, rz: float) -> None:
        c = self.controls
        with QSignalBlocker(c.axis_x_spin), QSignalBlocker(c.axis_y_spin), QSignalBlocker(c.axis_z_spin), QSignalBlocker(c.axis_x_slider), QSignalBlocker(c.axis_y_slider), QSignalBlocker(c.axis_z_slider):
            c.axis_x_spin.setValue(rx)
            c.axis_y_spin.setValue(ry)
            c.axis_z_spin.setValue(rz)
            c.axis_x_slider.setValue(int(rx))
            c.axis_y_slider.setValue(int(ry))
            c.axis_z_slider.setValue(int(rz))

    def sync_zoom_spin(self, zoom: int) -> None:
        with QSignalBlocker(self.controls.zoom_spin):
            self.controls.zoom_spin.setValue(zoom)

    def sync_location_spins(self, lat: float, lon: float, zoom: int) -> None:
        with QSignalBlocker(self.controls.lat_spin), QSignalBlocker(self.controls.lon_spin), QSignalBlocker(self.controls.zoom_spin):
            self.controls.lat_spin.setValue(lat)
            self.controls.lon_spin.setValue(lon)
            self.controls.zoom_spin.setValue(zoom)
        self.scene3d.set_origin(lat, lon)
        try:
            self.scene3d.set_grid_bbox(self.canvas.visible_bbox())
        except Exception:
            pass
        if hasattr(self, "refresh_3d_map_plane"):
            self.refresh_3d_map_plane()

    def sync_sun_controls(self) -> None:
        return

    def apply_sun_tab_datetime(self) -> None:
        self.apply_sun_from_datetime()

    def apply_sun_tab_season(self) -> None:
        self.apply_season_date()
