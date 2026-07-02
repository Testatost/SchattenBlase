from __future__ import annotations
from datetime import datetime, timedelta
from time import monotonic
from zoneinfo import ZoneInfo
from PySide6.QtCore import QDate, QSignalBlocker, QTime, QTimer, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QColorDialog,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
    QTableWidgetItem,
    QSizePolicy,
)
from core.history import snapshot_state
from core.objects import SimulationState, TREE_KINDS
from core.solar import daylight_times, season_date, solar_position
from core.storage import load_library, load_object, save_ground, save_library, save_object, save_place
from i18n import I18n, available_languages, language_label
from ui.canvas import MapCanvas
from ui.control_panel import ControlPanel
from ui.metrics_panel import MetricsPanel
from ui.scene3d import Scene3DCanvas
from ui.main_window_actions import MainWindowActions
class MainWindow(MainWindowActions, QMainWindow):
    def __init__(self, i18n: I18n) -> None:
        super().__init__()
        self.i18n = i18n
        self.state = SimulationState()
        self.undo_stack: list[dict] = []
        self.redo_stack: list[dict] = []
        self._restoring = False
        self._last_snapshot = snapshot_state(self.state)
        self._last_history_push = 0.0
        self._last_map_plane_grab = 0.0
        self.timezone = ZoneInfo("Europe/Berlin")
        self.library = load_library()
        self.timer = QTimer(self)
        self.timer.setInterval(100)
        self.timer.timeout.connect(self.next_simulation_step)
        self._setup_ui()
        self._connect_signals()
        self.controls.refresh_library(self.library)
        self.retranslate()
        self.update_object_editor()
        self.update_metrics()
    def _setup_ui(self) -> None:
        self.splitter = QSplitter()
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(3, 3, 3, 3)
        left_layout.setSpacing(3)
        left.setMinimumWidth(0)
        left.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.preview_tabs = QTabWidget()
        self.canvas = MapCanvas(self.state, self.i18n)
        self.scene3d = Scene3DCanvas(self.state, self.i18n)
        self.scene3d.set_origin(*self.canvas.center_latlon())
        self.map_page = QWidget()
        map_layout = QVBoxLayout(self.map_page)
        map_layout.setContentsMargins(3, 3, 3, 3)
        map_layout.setSpacing(3)
        search_row = QHBoxLayout()
        self.map_search_label = QLabel()
        self.map_search_edit = QLineEdit()
        self.map_search_button = QPushButton()
        self.save_project_button = QPushButton()
        self.load_project_button = QPushButton()
        self.map_search_combo = QComboBox()
        self.top_language_combo = QComboBox()
        for code in available_languages():
            self.top_language_combo.addItem(language_label(code), code)
        search_row.addWidget(self.map_search_label)
        search_row.addWidget(self.map_search_edit, 1)
        search_row.addWidget(self.map_search_button)
        search_row.addWidget(self.map_search_combo, 2)
        search_row.addWidget(self.save_project_button)
        search_row.addWidget(self.load_project_button)
        search_row.addWidget(self.top_language_combo)
        map_layout.addLayout(search_row)
        map_layout.addWidget(self.canvas, 1)
        self.preview_tabs.addTab(self.map_page, "")
        self.preview_tabs.addTab(self.scene3d, "")
        self.metrics_toggle = QPushButton()
        self.metrics_toggle.setCheckable(True)
        self.metrics_toggle.setChecked(True)
        self.metrics_panel = MetricsPanel(self.state, self.i18n)
        self.metrics_panel.setMinimumWidth(0)
        self.metrics_panel.setMinimumHeight(185)
        self.metric_box = QWidget()
        metric_box_layout = QVBoxLayout(self.metric_box)
        metric_box_layout.setContentsMargins(0, 0, 0, 0)
        metric_box_layout.setSpacing(2)
        metric_box_layout.addWidget(self.metrics_toggle)
        metric_box_layout.addWidget(self.metrics_panel, 1)
        self.preview_splitter = QSplitter(Qt.Orientation.Vertical)
        self.preview_splitter.setHandleWidth(8)
        self.preview_splitter.addWidget(self.preview_tabs)
        self.preview_splitter.addWidget(self.metric_box)
        self.preview_splitter.setSizes([550, 240])
        left_layout.addWidget(self.preview_splitter, 1)
        self.controls = ControlPanel(self.i18n, self.timezone)
        self.controls.map_plane_button.setChecked(True)
        self.splitter.addWidget(left)
        self.splitter.addWidget(self.controls)
        self.splitter.setHandleWidth(14)
        self.splitter.setChildrenCollapsible(False)
        self.controls.setMinimumWidth(310)
        self.controls.setMaximumWidth(500)
        self.splitter.setSizes([1290, 370])
        self.setCentralWidget(self.splitter)
        self.statusBar().showMessage("")
    def _connect_signals(self) -> None:
        c = self.controls
        c.lang_combo.currentIndexChanged.connect(self.change_language)
        self.top_language_combo.currentIndexChanged.connect(self.change_language)
        c.goto_button.clicked.connect(self.apply_location)
        c.undo_button.clicked.connect(self.undo_action)
        c.redo_button.clicked.connect(self.redo_action)
        c.save_place_button.clicked.connect(self.save_current_place)
        c.load_place_button.clicked.connect(self.load_selected_place)
        c.import_buildings_button.clicked.connect(self.import_osm_buildings)
        c.object_import_buildings_button.clicked.connect(self.import_osm_buildings)
        c.offline_mode_check.toggled.connect(self.canvas.set_offline_only)
        c.download_visible_button.clicked.connect(self.download_visible_area)
        c.download_place_button.clicked.connect(self.download_offline_place)
        c.add_button.toggled.connect(self.activate_add_mode)
        c.draw_custom_button.toggled.connect(self.set_custom_mode_from_button)
        c.delete_button.clicked.connect(self.delete_selected)
        c.mesh_edit_check.toggled.connect(self.canvas.set_mesh_edit)
        c.mesh_edit_check.toggled.connect(self.scene3d.set_mesh_edit)
        c.show_dims_button.toggled.connect(self.scene3d.set_dimensions_selected)
        c.show_all_dims_button.toggled.connect(self.scene3d.set_dimensions_all)
        c.save_object_button.clicked.connect(self.save_selected_object)
        c.load_object_button.clicked.connect(self.load_saved_object)
        c.import_object_button.clicked.connect(self.import_object_file)
        c.export_object_button.clicked.connect(self.export_selected_object)
        c.selected_name_edit.textEdited.connect(self.update_selected_name)
        c.object_color_button.clicked.connect(self.pick_object_color)
        c.draw_ground_button.toggled.connect(self.set_ground_mode_from_button)
        c.edit_ground_button.toggled.connect(self.canvas.set_ground_edit)
        c.clear_ground_button.clicked.connect(self.canvas.clear_ground)
        c.save_ground_button.clicked.connect(self.save_current_ground)
        c.load_ground_button.clicked.connect(self.load_saved_ground)
        c.ground_title_edit.textEdited.connect(self.update_ground_name)
        c.ground_color_button.clicked.connect(self.pick_ground_color)
        c.sun_button.clicked.connect(self.apply_manual_sun)
        c.apply_season_button.clicked.connect(self.apply_season_date)
        c.start_button.clicked.connect(self.start_simulation)
        c.stop_button.clicked.connect(self.timer.stop)
        c.export_chart_button.clicked.connect(lambda: self.metrics_panel.chart_panel.chart.export(self))
        for key, check in [("ground_shadow", c.chart_ground_shadow_check), ("selected", c.chart_selected_check), ("selected_with", c.chart_selected_with_check), ("selected_without", c.chart_selected_without_check), ("ratio", c.chart_ratio_check)]:
            check.toggled.connect(lambda enabled, k=key: self.metrics_panel.chart_panel.chart.set_key_enabled(k, enabled))
            self.metrics_panel.chart_panel.chart.set_key_enabled(key, check.isChecked())
        c.next_button.clicked.connect(self.next_simulation_step)
        c.previous_button.clicked.connect(self.previous_simulation_step)
        c.reset_accumulated_button.clicked.connect(self.reset_accumulated_shadow)
        c.speed_slider.valueChanged.connect(self.update_speed_from_slider)
        c.speed_spin.valueChanged.connect(self.update_speed_from_spin)
        c.project_save_button.clicked.connect(self.save_project_file)
        c.project_load_button.clicked.connect(self.load_project_file)
        c.cleanup_button.clicked.connect(self.cleanup_program_data)
        self.map_search_button.clicked.connect(self.search_preview_place)
        self.save_project_button.clicked.connect(self.save_project_file)
        self.load_project_button.clicked.connect(self.load_project_file)
        self.map_search_edit.returnPressed.connect(self.search_preview_place)
        self.metrics_toggle.toggled.connect(self.set_metrics_visible)
        self.preview_tabs.currentChanged.connect(lambda _idx: self.refresh_3d_map_plane(force=True))
        self.metrics_panel.row_selected.connect(self.select_metrics_row)
        self.map_search_combo.activated.connect(self.load_preview_search_result)
        self.preview_tabs.currentChanged.connect(self.refresh_3d_map_plane)
        for spin in [c.height_spin, c.width_spin, c.depth_spin, c.trunk_spin, c.crown_width_spin, c.crown_height_spin, c.tilt_spin, c.orientation_spin]:
            spin.valueChanged.connect(self.update_selected_object)
        c.tilt_slider.valueChanged.connect(lambda v: c.tilt_spin.setValue(v))
        c.orientation_slider.valueChanged.connect(lambda v: c.orientation_spin.setValue(v))
        c.kind_combo.currentIndexChanged.connect(self.update_selected_kind)
        c.date_edit.dateChanged.connect(self.apply_sun_from_datetime)
        c.time_edit.timeChanged.connect(self.apply_sun_from_datetime)
        for spin in [c.axis_x_spin, c.axis_y_spin, c.axis_z_spin]:
            spin.valueChanged.connect(self.apply_view_rotation)
        for slider in [c.axis_x_slider, c.axis_y_slider, c.axis_z_slider]:
            slider.valueChanged.connect(self.apply_view_rotation_from_sliders)
        c.show_labels_check.toggled.connect(self.set_label_visibility)
        c.label_mode_combo.currentIndexChanged.connect(self.set_label_mode)
        c.map_plane_button.toggled.connect(self.scene3d.set_map_plane_visible)
        c.map_plane_button.toggled.connect(lambda _checked: self.refresh_3d_map_plane(force=True))
        c.reset_3d_button.clicked.connect(self.reset_view_rotation)
        self.canvas.object_selected.connect(self.update_object_editor)
        self.canvas.state_changed.connect(self.update_views)
        self.canvas.status_message.connect(self.statusBar().showMessage)
        self.canvas.zoom_changed.connect(self.sync_zoom_spin)
        self.canvas.center_changed.connect(self.sync_location_spins)
        self.canvas.mode_changed.connect(self.sync_action_buttons)
        self.scene3d.rotation_changed.connect(self.sync_view_rotation_spins)
        self.scene3d.mesh_edited.connect(self.scene3d_mesh_edited)
        self.scene3d.object_selected.connect(self.update_object_editor)
        self.scene3d.object_selected.connect(self.update_views)
        self._install_shortcuts()
    def retranslate(self) -> None:
        self.setWindowTitle(self.i18n.t("app.title"))
        self.preview_tabs.setTabText(0, self.i18n.t("view.map"))
        self.preview_tabs.setTabText(1, self.i18n.t("view.3d"))
        self.map_search_label.setText(self.i18n.t("search.label"))
        self.map_search_button.setText(self.i18n.t("search.button"))
        self.save_project_button.setText(self.i18n.t("project.save"))
        self.load_project_button.setText(self.i18n.t("project.load"))
        self.metrics_toggle.setText(self.i18n.t("metrics.toggle"))
        self.map_search_edit.setPlaceholderText(self.i18n.t("search.placeholder"))
        for index in range(self.top_language_combo.count()):
            self.top_language_combo.setItemText(index, language_label(self.top_language_combo.itemData(index)))
        self.controls.retranslate(self.i18n)
        self.metrics_panel.retranslate(self.i18n)
        self.canvas.set_language(self.i18n)
        self.scene3d.set_language(self.i18n)
        self.statusBar().showMessage(self.i18n.t("status.ready"))
    def change_language(self) -> None:
        sender = self.sender()
        combo = self.top_language_combo if sender is self.top_language_combo else self.controls.lang_combo
        code = combo.currentData()
        if code:
            self.i18n.set_language(code)
            for target in (self.top_language_combo, self.controls.lang_combo):
                idx = target.findData(code)
                if idx >= 0 and target.currentIndex() != idx:
                    with QSignalBlocker(target):
                        target.setCurrentIndex(idx)
            self.retranslate()
            self.update_object_editor()
            self.update_metrics()
    def apply_location(self) -> None:
        try:
            c = self.controls
            self.canvas.set_zoom(c.zoom_spin.value())
            self.canvas.center_on_latlon(c.lat_spin.value(), c.lon_spin.value())
            self.apply_sun_from_datetime()
        except Exception:
            self._warning("dialog.invalid_location")
    def save_current_place(self) -> None:
        name = self.controls.place_name_edit.text().strip()
        if not name:
            self._warning("dialog.missing_name")
            return
        lat, lon = self.canvas.center_latlon()
        save_place(self.library, name, lat, lon, self.canvas.zoom)
        self._persist_library("status.place_saved")
    def load_selected_place(self) -> None:
        entry = self.controls.place_combo.currentData()
        if not entry:
            return
        with QSignalBlocker(self.controls.lat_spin), QSignalBlocker(self.controls.lon_spin), QSignalBlocker(self.controls.zoom_spin):
            self.controls.lat_spin.setValue(float(entry.get("lat", 0.0)))
            self.controls.lon_spin.setValue(float(entry.get("lon", 0.0)))
            self.controls.zoom_spin.setValue(int(entry.get("zoom", self.canvas.zoom)))
        self.apply_location()
    def activate_add_mode(self, checked: bool = True) -> None:
        kind = self.controls.kind_combo.currentData() if checked else None
        if not kind:
            self.controls.add_button.setChecked(False) if checked else None
        self.canvas.set_add_mode(kind)
        self.scene3d.set_add_mode(kind)
    def set_custom_mode_from_button(self, checked: bool) -> None:
        self.canvas.set_custom_mode(checked)
        self.scene3d.set_custom_mode(checked)
        if checked:
            self.controls.add_button.setChecked(False); self.controls.draw_ground_button.setChecked(False)
    def set_ground_mode_from_button(self, checked: bool) -> None:
        self.canvas.set_ground_mode(checked)
        if checked:
            self.controls.add_button.setChecked(False); self.controls.draw_custom_button.setChecked(False)
    def sync_action_buttons(self, mode: str, enabled: bool) -> None:
        mapping = {"add": self.controls.add_button, "custom": self.controls.draw_custom_button, "ground": self.controls.draw_ground_button}
        button = mapping.get(mode)
        if button is not None:
            with QSignalBlocker(button):
                button.setChecked(enabled)
    def delete_selected(self) -> None:
        if self.state.delete_selected():
            self.canvas.redraw_overlays()
            self.update_object_editor()
            self.update_views()
            self.statusBar().showMessage(self.i18n.t("status.object_deleted"))
    def save_selected_object(self) -> None:
        obj = self.state.selected_object()
        name = self.controls.object_name_edit.text().strip()
        if obj is None:
            self._warning("dialog.no_object_selected")
            return
        if not name:
            self._warning("dialog.missing_name")
            return
        save_object(self.library, name, obj)
        self._persist_library("status.object_saved")
    def load_saved_object(self) -> None:
        entry = self.controls.object_combo.currentData()
        if not entry:
            return
        lat, lon = self.canvas.center_latlon()
        obj = load_object(entry, lat, lon)
        if obj:
            self.canvas.add_objects([obj])
            self.statusBar().showMessage(self.i18n.t("status.object_loaded"))
    def save_current_ground(self) -> None:
        name = self.controls.ground_name_edit.text().strip()
        if len(self.state.ground_polygon) < 3:
            self._warning("dialog.no_ground")
            return
        if not name:
            self._warning("dialog.missing_name")
            return
        self.state.ground_name = name
        save_ground(self.library, name, self.state.ground_polygon, self.state.ground_color)
        self._persist_library("status.ground_saved")
    def load_saved_ground(self) -> None:
        entry = self.controls.ground_combo.currentData()
        if not entry:
            return
        self.state.ground_polygon = [tuple(p) for p in entry.get("polygon", [])]
        self.state.ground_name = entry.get("name", "")
        self.state.ground_color = entry.get("color", self.state.ground_color)
        with QSignalBlocker(self.controls.ground_title_edit):
            self.controls.ground_title_edit.setText(self.state.ground_name)
        self.canvas.redraw_overlays()
        self.update_views()
        self.statusBar().showMessage(self.i18n.t("status.ground_loaded"))
    def _persist_library(self, status_key: str) -> None:
        save_library(self.library)
        self.controls.refresh_library(self.library)
        self.statusBar().showMessage(self.i18n.t(status_key))
    def update_object_editor(self) -> None:
        c = self.controls
        obj = self.state.selected_object()
        enabled = obj is not None
        for widget in [
            c.selected_name_edit,
            c.object_color_button,
            c.height_spin,
            c.width_spin,
            c.depth_spin,
            c.trunk_spin,
            c.crown_width_spin,
            c.crown_height_spin,
            c.tilt_spin, c.tilt_slider,
            c.orientation_spin, c.orientation_slider,
            c.delete_button,
            c.save_object_button,
            c.export_object_button,
        ]:
            widget.setEnabled(enabled)
        if obj is None:
            c.selected_label.setText(self.i18n.t("object.no_selection"))
            with QSignalBlocker(c.selected_name_edit):
                c.selected_name_edit.clear()
            return
        c.selected_label.setText(self.i18n.t("object.selected"))
        with QSignalBlocker(c.selected_name_edit):
            c.selected_name_edit.setText(obj.name)
        c.object_color_button.setStyleSheet(f"background-color: {obj.color or TREE_KINDS.get(obj.kind_key, TREE_KINDS['custom']).color};")
        is_tree = obj.is_tree()
        c.trunk_spin.setEnabled(is_tree)
        c.crown_width_spin.setEnabled(is_tree)
        c.crown_height_spin.setEnabled(is_tree)
        values = [
            (c.height_spin, obj.height_m),
            (c.width_spin, obj.width_m),
            (c.depth_spin, obj.depth_m or obj.width_m),
            (c.trunk_spin, obj.trunk_diameter_m),
            (c.crown_width_spin, obj.crown_width_m or obj.width_m),
            (c.crown_height_spin, obj.crown_height_m),
            (c.tilt_spin, obj.tilt_deg),
            (c.orientation_spin, obj.orientation_deg),
        ]
        for spin, value in values:
            with QSignalBlocker(spin):
                spin.setValue(value)
        for slider, value in [(c.tilt_slider, obj.tilt_deg), (c.orientation_slider, obj.orientation_deg)]:
            with QSignalBlocker(slider):
                slider.setValue(round(value))
        index = c.kind_combo.findData(obj.kind_key)
        with QSignalBlocker(c.kind_combo):
            c.kind_combo.setCurrentIndex(index if index >= 0 else 0)
    def update_selected_kind(self) -> None:
        kind = self.controls.kind_combo.currentData()
        if kind:
            with QSignalBlocker(self.controls.add_button):
                self.controls.add_button.setChecked(True)
            self.activate_add_mode(True)
    def update_selected_object(self) -> None:
        obj = self.state.selected_object()
        if obj is None:
            return
        c = self.controls
        sender = self.sender()
        obj.height_m = c.height_spin.value()
        obj.width_m = c.width_spin.value()
        obj.depth_m = c.depth_spin.value()
        kind = TREE_KINDS.get(obj.kind_key, TREE_KINDS["custom"])
        if obj.kind_key == "cube":
            v = c.height_spin.value() if sender is c.height_spin else (c.depth_spin.value() if sender is c.depth_spin else c.width_spin.value())
            obj.height_m = obj.width_m = obj.depth_m = v
            for spin in [c.height_spin, c.width_spin, c.depth_spin]:
                if spin is not sender:
                    with QSignalBlocker(spin): spin.setValue(v)
        if obj.is_tree() and sender is c.width_spin:
            with QSignalBlocker(c.crown_width_spin):
                c.crown_width_spin.setValue(c.width_spin.value())
            obj.crown_width_m = c.width_spin.value()
        obj.trunk_diameter_m = c.trunk_spin.value()
        obj.crown_width_m = c.crown_width_spin.value() if obj.is_tree() else obj.width_m
        obj.crown_height_m = min(c.crown_height_spin.value(), obj.height_m)
        if kind.crown_shape == "box":
            w = max(obj.width_m, 0.1) * 0.5; d = max(obj.depth_m or obj.width_m, 0.1) * 0.5
            obj.footprint_m = [(-w, -d), (w, -d), (w, d), (-w, d)]
        obj.tilt_deg = c.tilt_spin.value()
        obj.orientation_deg = c.orientation_spin.value()
        with QSignalBlocker(c.tilt_slider): c.tilt_slider.setValue(round(obj.tilt_deg))
        with QSignalBlocker(c.orientation_slider): c.orientation_slider.setValue(round(obj.orientation_deg))
        self.canvas.redraw_overlays()
        self.update_views()
    def update_selected_name(self, text: str) -> None:
        obj = self.state.selected_object()
        if obj is None:
            return
        obj.name = text.strip()
        self.canvas.redraw_overlays()
        self.update_views()
    def pick_object_color(self) -> None:
        obj = self.state.selected_object()
        if obj is None:
            return
        color = QColorDialog.getColor(QColor(obj.color or "#4a7d3c"), self, self.i18n.t("dialog.pick_color"))
        if color.isValid():
            obj.color = color.name()
            self.update_object_editor()
            self.canvas.redraw_overlays()
            self.update_views()
    def update_ground_name(self, text: str) -> None:
        self.state.ground_name = text.strip()
        self.canvas.redraw_overlays()
        self.update_views()
    def pick_ground_color(self) -> None:
        color = QColorDialog.getColor(QColor(self.state.ground_color), self, self.i18n.t("dialog.pick_color"))
        if color.isValid():
            self.state.ground_color = color.name()
            self.canvas.redraw_overlays()
            self.update_views()
    def apply_manual_sun(self) -> None:
        self.canvas.set_sun(self.controls.azimuth_spin.value(), self.controls.altitude_spin.value())
    def apply_sun_from_datetime(self) -> None:
        moment = self.current_datetime()
        lat, lon = self.canvas.center_latlon()
        sun = solar_position(moment, lat, lon)
        with QSignalBlocker(self.controls.azimuth_spin), QSignalBlocker(self.controls.altitude_spin):
            self.controls.azimuth_spin.setValue(sun.azimuth_deg)
            self.controls.altitude_spin.setValue(sun.altitude_deg)
        self.canvas.set_sun(sun.azimuth_deg, sun.altitude_deg)
        self.sync_sun_controls()
    def current_datetime(self) -> datetime:
        qd = self.controls.date_edit.date()
        qt = self.controls.time_edit.time()
        return datetime(qd.year(), qd.month(), qd.day(), qt.hour(), qt.minute(), tzinfo=self.timezone)
    def range_end_datetime(self) -> datetime:
        base = self.current_datetime()
        end = self.controls.end_time_edit.time()
        return base.replace(hour=end.hour(), minute=end.minute(), second=0, microsecond=0)
    def apply_season_date(self) -> None:
        c = self.controls
        season_key = c.season_combo.currentData()
        base = season_date(datetime.now(self.timezone).year, season_key).replace(tzinfo=self.timezone)
        sunrise, sunset = daylight_times(base, c.lat_spin.value(), c.lon_spin.value())
        with QSignalBlocker(c.date_edit), QSignalBlocker(c.time_edit), QSignalBlocker(c.start_time_edit), QSignalBlocker(c.end_time_edit):
            c.date_edit.setDate(QDate(base.year, base.month, base.day))
            c.time_edit.setTime(QTime(sunrise.hour, sunrise.minute))
            c.start_time_edit.setTime(QTime(sunrise.hour, sunrise.minute))
            c.end_time_edit.setTime(QTime(sunset.hour, sunset.minute))
        self.apply_sun_from_datetime()
        self.sync_sun_controls()
    def start_simulation(self) -> None:
        self.state.cumulative_shadow_m2h = 0.0
        self.metrics_panel.chart_panel.chart.clear()
        start = self.controls.start_time_edit.time()
        with QSignalBlocker(self.controls.time_edit):
            self.controls.time_edit.setTime(QTime(start.hour(), start.minute()))
        self.timer.setInterval(self.controls.speed_spin.value())
        self.apply_sun_from_datetime()
        self.timer.start()
    def next_simulation_step(self) -> None:
        current = self.current_datetime()
        end = self.range_end_datetime()
        if current >= end:
            self.timer.stop()
            return
        moment = min(current + timedelta(minutes=self.controls.step_spin.value()), end)
        hours = max(0.0, (moment - current).total_seconds() / 3600.0)
        self.state.cumulative_shadow_m2h += self.canvas.total_shadow_area() * hours
        if moment >= end:
            self.timer.stop()
        with QSignalBlocker(self.controls.date_edit), QSignalBlocker(self.controls.time_edit):
            self.controls.date_edit.setDate(QDate(moment.year, moment.month, moment.day))
            self.controls.time_edit.setTime(QTime(moment.hour, moment.minute))
        self.apply_sun_from_datetime()

    def previous_simulation_step(self) -> None:
        current = self.current_datetime()
        start_time = self.controls.start_time_edit.time()
        start = current.replace(hour=start_time.hour(), minute=start_time.minute(), second=0, microsecond=0)
        moment = max(current - timedelta(minutes=self.controls.step_spin.value()), start)
        with QSignalBlocker(self.controls.date_edit), QSignalBlocker(self.controls.time_edit):
            self.controls.date_edit.setDate(QDate(moment.year, moment.month, moment.day))
            self.controls.time_edit.setTime(QTime(moment.hour, moment.minute))
        self.apply_sun_from_datetime()
    def reset_accumulated_shadow(self) -> None:
        self.state.cumulative_shadow_m2h = 0.0
        self.update_views()
    def update_views(self) -> None:
        if not self._restoring:
            snap = snapshot_state(self.state)
            if snap != self._last_snapshot:
                now = monotonic()
                if now - self._last_history_push > 0.12:
                    self.undo_stack.append(self._last_snapshot)
                    self.undo_stack = self.undo_stack[-80:]
                    self.redo_stack.clear()
                    self._last_history_push = now
                self._last_snapshot = snap
        if self.canvas.add_kind_key is None and self.scene3d.add_kind_key is not None:
            self.scene3d.set_add_mode(None)
        if self.scene3d.add_kind_key is None and self.canvas.add_kind_key is not None and not (self.canvas.drawing_ground or self.canvas.drawing_custom):
            self.canvas.set_add_mode(None)
        try:
            self.scene3d.set_grid_bbox(self.canvas.visible_bbox())
        except Exception:
            pass
        self.refresh_3d_map_plane()
        self.update_metrics()
        self.scene3d.refresh()
    def refresh_3d_map_plane(self, *args, force: bool = False) -> None:
        if not getattr(self.scene3d, "show_map_plane", False):
            return
        now = monotonic()
        if not force and now - self._last_map_plane_grab < 0.5:
            return
        self._last_map_plane_grab = now
        hidden = list(getattr(self.canvas, "overlay_items", []))
        for item in hidden:
            item.setVisible(False)
        pixmap = self.canvas.viewport().grab()
        for item in hidden:
            item.setVisible(True)
        self.scene3d.set_map_plane_image(pixmap, self.canvas.visible_bbox())
    def update_metrics(self) -> None:
        absolute_ground = self.canvas.ground_area_absolute()
        relative_ground = self.canvas.ground_area()
        ground_shadow = min(self.canvas.total_shadow_on_ground(), relative_ground) if relative_ground > 0.0 else 0.0
        selected_with = self.canvas.selected_shadow_area_with_ground()
        selected_without = self.canvas.selected_shadow_area()
        per_object = self.canvas.per_object_shadow_areas()
        selected_ids = [obj.object_id for obj in self.state.selected_objects()]
        selected_area = ground_shadow if self.state.ground_selected else sum(per_object.get(object_id, 0.0) for object_id in selected_ids)
        self.metrics_panel.update_values(
            selected_area, selected_with, selected_without, self.canvas.total_shadow_area(),
            ground_shadow, relative_ground, per_object, self.current_datetime(),
        )
        ratio = (ground_shadow / relative_ground * 100.0) if relative_ground > 0.0 else 0.0
        c = self.controls
        c.absolute_ground_value.setText(f"{absolute_ground:.2f} m²")
        c.relative_ground_value.setText(f"{relative_ground:.2f} m²")
        c.ground_shadow_value.setText(f"{ground_shadow:.2f} m²")
        c.selected_value.setText(f"{selected_area:.2f} m²")
        c.selected_with_value.setText(f"{selected_with:.2f} m²")
        c.selected_without_value.setText(f"{selected_without:.2f} m²")
        c.ground_ratio_value.setText(f"{ratio:.1f} %")
        self.update_sim_metrics_table(relative_ground, per_object)
    def update_sim_metrics_table(self, ground: float, per_object: dict[str, float]) -> None:
        table = self.controls.sim_metrics_table
        self._sim_metric_row_ids = []
        rows = []
        if len(self.state.ground_polygon) >= 3:
            rows.append([self.state.ground_name or self.i18n.t("group.ground"), self.i18n.t("group.ground"), f"{ground:.2f}"])
            self._sim_metric_row_ids.append("ground")
        for obj in self.state.objects:
            kind = TREE_KINDS.get(obj.kind_key, TREE_KINDS["custom"])
            rows.append([obj.name or self.i18n.t(kind.label_key), self.i18n.t(kind.label_key), f"{per_object.get(obj.object_id, 0.0):.2f}"])
            self._sim_metric_row_ids.append(obj.object_id)
        table.setRowCount(len(rows))
        for row, values in enumerate(rows):
            for col, value in enumerate(values):
                table.setItem(row, col, QTableWidgetItem(value))
        table.resizeColumnsToContents()
    def select_sim_metrics_row(self, row: int, _col: int) -> None:
        ids = getattr(self, "_sim_metric_row_ids", [])
        if 0 <= row < len(ids):
            self.select_metrics_row(ids[row])
    def select_metrics_row(self, item_id: str) -> None:
        if item_id == "ground":
            self.state.ground_selected = True
            self.state.set_single_selection(None)
        else:
            self.state.set_single_selection(item_id)
            self.state.ground_selected = False
        self.canvas.redraw_overlays()
        self.update_object_editor()
        self.update_views()
    def set_metrics_visible(self, visible: bool) -> None:
        self.metrics_panel.setVisible(visible)
        if visible:
            self.preview_splitter.setSizes([550, 280])
        else:
            self.preview_splitter.setSizes([9999, max(26, self.metrics_toggle.sizeHint().height() + 6)])

    def _warning(self, message_key: str, **kwargs) -> None:
        QMessageBox.warning(self, self.i18n.t("dialog.error"), self.i18n.t(message_key, **kwargs))
