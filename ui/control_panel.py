from __future__ import annotations
from datetime import datetime
from zoneinfo import ZoneInfo
from PySide6.QtCore import QDate, Qt, QTime
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
    QTableWidget,
    QStackedWidget,
)
from config import DEFAULT_LAT, DEFAULT_LON, DEFAULT_ZOOM
from core.objects import TREE_KINDS
from core.storage import Library
from i18n import I18n, available_languages, language_label
from ui.kind_picker import KindPickerButton, render_kind_icon
class ControlPanel(QWidget):
    def __init__(self, i18n: I18n, timezone: ZoneInfo, parent=None) -> None:
        super().__init__(parent)
        self.i18n = i18n
        self.timezone = timezone
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(2)
        self._tab_row_top = QHBoxLayout()
        self._tab_row_bottom = QHBoxLayout()
        self._tab_row_top.setSpacing(2); self._tab_row_bottom.setSpacing(2)
        root.addLayout(self._tab_row_top)
        root.addLayout(self._tab_row_bottom)
        self._stack = QStackedWidget()
        root.addWidget(self._stack, 1)
        self._tab_buttons: list[QPushButton] = []
        self.page_specs = [
            ("map", "group.location"),
            ("ground", "group.ground"),
            ("objects", "group.objects"),
            ("simulation", "group.simulation"),
            ("view3d", "group.view3d"),
            ("exchange", "group.exchange"),
        ]
        self.page_layouts: dict[str, QVBoxLayout] = {}
        for key, _ in self.page_specs:
            self._add_page(key)
        self._build_map_page()
        self._build_object_page()
        self._build_ground_page()
        self._build_simulation_page()
        self._build_view3d_page()
        self._build_exchange_page()
        for layout in self.page_layouts.values():
            layout.addStretch(1)
    def _add_page(self, key: str) -> None:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        page = QWidget()
        layout = QVBoxLayout(page)
        scroll.setWidget(page)
        index = self._stack.addWidget(scroll)
        button = QPushButton()
        button.setCheckable(True)
        button.setAutoExclusive(True)
        button.setStyleSheet("QPushButton:checked{background-color:#5a8f54;color:white;}")
        button.clicked.connect(lambda _=False, i=index: self._select_tab(i))
        (self._tab_row_top if index < 3 else self._tab_row_bottom).addWidget(button)
        self._tab_buttons.append(button)
        if index == 0:
            button.setChecked(True)
        self.page_layouts[key] = layout
    def _select_tab(self, index: int) -> None:
        self._stack.setCurrentIndex(index)
        if 0 <= index < len(self._tab_buttons):
            self._tab_buttons[index].setChecked(True)
    def setTabText(self, index: int, text: str) -> None:
        if 0 <= index < len(self._tab_buttons):
            self._tab_buttons[index].setText(text)
    def _spin(self, minimum: float, maximum: float, step: float, decimals: int = 2) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(minimum, maximum)
        spin.setDecimals(decimals)
        spin.setSingleStep(step)
        return spin
    def _build_map_page(self) -> None:
        self.lang_combo = QComboBox()
        for code in available_languages():
            self.lang_combo.addItem(language_label(code), code)
        self.lang_label = QLabel()
        self.lang_label.setVisible(False)
        self.lang_combo.setVisible(False)
        self.location_group = QGroupBox()
        form = QFormLayout(self.location_group)
        self.lat_spin = self._spin(-85.0, 85.0, 0.000001, 6)
        self.lat_spin.setValue(DEFAULT_LAT)
        self.lon_spin = self._spin(-180.0, 180.0, 0.000001, 6)
        self.lon_spin.setValue(DEFAULT_LON)
        self.zoom_spin = QSpinBox()
        self.zoom_spin.setRange(1, 21)
        self.zoom_spin.setValue(DEFAULT_ZOOM)
        self.import_buildings_button = QPushButton()
        self.page_layouts["map"].addWidget(self.import_buildings_button)
        self.goto_button = QPushButton()
        self.undo_button = QPushButton()
        self.redo_button = QPushButton()
        self.lat_label = QLabel(); self.lon_label = QLabel(); self.zoom_label = QLabel()
        form.addRow(self.lat_label, self.lat_spin)
        form.addRow(self.lon_label, self.lon_spin)
        form.addRow(self.zoom_label, self.zoom_spin)
        for button in [self.goto_button, self.undo_button, self.redo_button]:
            form.addRow(button)
        self.page_layouts["map"].addWidget(self.location_group)
        self.place_group = QGroupBox()
        place_form = QFormLayout(self.place_group)
        self.place_name_edit = QLineEdit(); self.place_combo = QComboBox()
        self.save_place_button = QPushButton(); self.load_place_button = QPushButton()
        self.offline_mode_check = QCheckBox(); self.offline_query_edit = QLineEdit()
        self.offline_zmin_spin = QSpinBox(); self.offline_zmax_spin = QSpinBox()
        for spin in [self.offline_zmin_spin, self.offline_zmax_spin]:
            spin.setRange(1, 21)
        self.offline_zmin_spin.setValue(5); self.offline_zmax_spin.setValue(16)
        self.download_visible_button = QPushButton(); self.download_place_button = QPushButton()
        self.place_name_label = QLabel(); self.place_load_label = QLabel()
        place_form.addRow(self.place_name_label, self.place_name_edit)
        place_form.addRow(self.save_place_button)
        place_form.addRow(self.place_load_label, self.place_combo)
        place_form.addRow(self.load_place_button)
        self.page_layouts["map"].addWidget(self.place_group)
        self.offline_group = QGroupBox()
        off = QFormLayout(self.offline_group)
        self.offline_query_label = QLabel(); self.offline_zmin_label = QLabel(); self.offline_zmax_label = QLabel()
        off.addRow(self.offline_mode_check)
        off.addRow(self.offline_query_label, self.offline_query_edit)
        off.addRow(self.offline_zmin_label, self.offline_zmin_spin)
        off.addRow(self.offline_zmax_label, self.offline_zmax_spin)
        off.addRow(self.download_visible_button)
        off.addRow(self.download_place_button)
        self.page_layouts["map"].addWidget(self.offline_group)
    def _build_object_page(self) -> None:
        self.object_group = QGroupBox()
        form = QFormLayout(self.object_group)
        self.kind_combo = KindPickerButton()
        self.kind_combo.addItem("", None)
        kind_groups = [
            ("objects", [key for key, kind in TREE_KINDS.items() if kind.category == "geometry"]),
            ("broadleaf", [key for key in TREE_KINDS if key.startswith("broadleaf")]),
            ("conifer", [key for key in TREE_KINDS if key.startswith("conifer")]),
        ]
        for group, keys in kind_groups:
            for key in keys:
                kind = TREE_KINDS[key]
                self.kind_combo.addItem("", key, group=group, icon=render_kind_icon(kind))
        self.add_button = QPushButton()
        self.draw_custom_button = QPushButton()
        self.object_import_buildings_button = QPushButton()
        self.page_layouts["objects"].addWidget(self.object_import_buildings_button)
        self.delete_button = QPushButton()
        self.mesh_edit_check = QPushButton()
        self.mesh_edit_check.setCheckable(True)
        self.show_dims_button = QPushButton(); self.show_dims_button.setCheckable(True)
        self.show_all_dims_button = QPushButton(); self.show_all_dims_button.setCheckable(True)
        for b in [self.add_button, self.draw_custom_button, self.mesh_edit_check, self.show_dims_button, self.show_all_dims_button]:
            b.setCheckable(True); b.setStyleSheet("QPushButton:checked{background-color:#5a8f54;color:white;}")
        self.selected_label = QLabel()
        self.selected_name_edit = QLineEdit()
        self.object_color_button = QPushButton()
        self.height_spin = self._spin(0.1, 150.0, 0.1)
        self.width_spin = self._spin(0.1, 150.0, 0.1)
        self.depth_spin = self._spin(0.1, 150.0, 0.1)
        self.trunk_spin = self._spin(0.0, 8.0, 0.05)
        self.crown_width_spin = self._spin(0.1, 160.0, 0.1)
        self.crown_height_spin = self._spin(0.0, 150.0, 0.1)
        self.tilt_spin = self._spin(-80.0, 80.0, 1.0)
        self.orientation_spin = self._spin(0.0, 359.0, 1.0)
        self.tilt_slider = QSlider(Qt.Orientation.Horizontal); self.tilt_slider.setRange(-80, 80)
        self.orientation_slider = QSlider(Qt.Orientation.Horizontal); self.orientation_slider.setRange(0, 359)
        self.object_kind_label = QLabel()
        self.selected_name_label = QLabel()
        self.height_label = QLabel()
        self.width_label = QLabel()
        self.depth_label = QLabel()
        self.trunk_label = QLabel()
        self.crown_width_label = QLabel()
        self.crown_height_label = QLabel()
        self.tilt_label = QLabel()
        self.orientation_label = QLabel()
        for label, widget in [
            (self.object_kind_label, self.kind_combo),
            (None, self.add_button),
            (None, self.draw_custom_button),
            (None, self.delete_button),
            (None, self.mesh_edit_check),
            (None, self.show_dims_button),
            (None, self.show_all_dims_button),
            (None, self.selected_label),
            (self.selected_name_label, self.selected_name_edit),
            (None, self.object_color_button),
            (self.height_label, self.height_spin),
            (self.width_label, self.width_spin),
            (self.depth_label, self.depth_spin),
            (self.trunk_label, self.trunk_spin),
            (self.crown_width_label, self.crown_width_spin),
            (self.crown_height_label, self.crown_height_spin),
            (self.tilt_label, self.tilt_spin), (None, self.tilt_slider),
            (self.orientation_label, self.orientation_spin), (None, self.orientation_slider),
        ]:
            form.addRow(label, widget) if label else form.addRow(widget)
        self.page_layouts["objects"].addWidget(self.object_group)
        self.object_library_group = QGroupBox()
        library_form = QFormLayout(self.object_library_group)
        self.object_name_edit = QLineEdit()
        self.object_combo = QComboBox()
        self.save_object_button = QPushButton()
        self.load_object_button = QPushButton()
        self.import_object_button = QPushButton()
        self.export_object_button = QPushButton()
        self.object_name_label = QLabel()
        self.object_load_label = QLabel()
        library_form.addRow(self.object_name_label, self.object_name_edit)
        library_form.addRow(self.save_object_button)
        library_form.addRow(self.object_load_label, self.object_combo)
        library_form.addRow(self.load_object_button)
        library_form.addRow(self.import_object_button)
        library_form.addRow(self.export_object_button)
        # Objektbibliothek wird im Export-Reiter eingeblendet, damit der Objekt-Reiter kompakt bleibt.
    def _build_ground_page(self) -> None:
        self.ground_group = QGroupBox()
        layout = QVBoxLayout(self.ground_group)
        self.draw_ground_button = QPushButton()
        self.draw_ground_button.setCheckable(True)
        self.draw_ground_button.setStyleSheet("QPushButton:checked{background-color:#5a8f54;color:white;}")
        self.clear_ground_button = QPushButton()
        self.edit_ground_button = QPushButton()
        self.edit_ground_button.setCheckable(True)
        self.edit_ground_button.setStyleSheet("QPushButton:checked{background-color:#5a8f54;color:white;}")
        self.ground_title_edit = QLineEdit()
        self.ground_color_button = QPushButton()
        self.ground_title_label = QLabel()
        self.ground_hint_label = QLabel()
        self.ground_hint_label.setWordWrap(True)
        layout.addWidget(self.draw_ground_button)
        layout.addWidget(self.edit_ground_button)
        layout.addWidget(self.clear_ground_button)
        layout.addWidget(self.ground_title_label)
        layout.addWidget(self.ground_title_edit)
        layout.addWidget(self.ground_color_button)
        layout.addWidget(self.ground_hint_label)
        self.page_layouts["ground"].addWidget(self.ground_group)
        self.ground_library_group = QGroupBox()
        form = QFormLayout(self.ground_library_group)
        self.ground_name_edit = QLineEdit()
        self.ground_combo = QComboBox()
        self.save_ground_button = QPushButton()
        self.load_ground_button = QPushButton()
        self.ground_name_label = QLabel()
        self.ground_load_label = QLabel()
        form.addRow(self.ground_name_label, self.ground_name_edit)
        form.addRow(self.save_ground_button)
        form.addRow(self.ground_load_label, self.ground_combo)
        form.addRow(self.load_ground_button)
        self.page_layouts["ground"].addWidget(self.ground_library_group)
    def _build_sun_page(self) -> None:
        self.sun_group = QGroupBox(); form = QFormLayout(self.sun_group)
        now = datetime.now(self.timezone)
        self.sun_season_combo = QComboBox()
        for key in ["spring", "summer", "autumn", "winter"]:
            self.sun_season_combo.addItem("", key)
        self.sun_date_edit = QDateEdit(); self.sun_date_edit.setCalendarPopup(True); self.sun_date_edit.setDate(QDate(now.year, now.month, now.day))
        self.sun_time_edit = QTimeEdit(); self.sun_time_edit.setTime(QTime(now.hour, now.minute))
        self.sun_apply_season_button = QPushButton()
        self.azimuth_spin = self._spin(0.0, 359.0, 1.0); self.altitude_spin = self._spin(-20.0, 90.0, 1.0)
        self.azimuth_spin.setValue(180.0); self.altitude_spin.setValue(35.0)
        self.sun_button = QPushButton()
        self.sun_season_label = QLabel(); self.sun_date_label = QLabel(); self.sun_time_label = QLabel(); self.azimuth_label = QLabel(); self.altitude_label = QLabel()
        for label, widget in [(self.sun_season_label, self.sun_season_combo), (None, self.sun_apply_season_button), (self.sun_date_label, self.sun_date_edit), (self.sun_time_label, self.sun_time_edit), (self.azimuth_label, self.azimuth_spin), (self.altitude_label, self.altitude_spin), (None, self.sun_button)]:
            form.addRow(label, widget) if label else form.addRow(widget)
        self.page_layouts["sun"].addWidget(self.sun_group)
    def _build_simulation_page(self) -> None:
        self.sim_group = QGroupBox()
        form = QFormLayout(self.sim_group)
        self.season_combo = QComboBox()
        for key in ["spring", "summer", "autumn", "winter"]:
            self.season_combo.addItem("", key)
        now = datetime.now(self.timezone)
        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDate(QDate(now.year, now.month, now.day))
        self.time_edit = QTimeEdit()
        self.time_edit.setTime(QTime(now.hour, now.minute))
        self.start_time_edit = QTimeEdit()
        self.start_time_edit.setTime(QTime(6, 0))
        self.end_time_edit = QTimeEdit()
        self.end_time_edit.setTime(QTime(21, 0))
        self.step_spin = QSpinBox()
        self.step_spin.setRange(1, 240)
        self.step_spin.setValue(15)
        self.speed_spin = QSpinBox()
        self.speed_spin.setRange(10, 1000)
        self.speed_spin.setValue(100)
        self.speed_slider = QSlider(Qt.Orientation.Horizontal)
        self.speed_slider.setRange(10, 1000)
        self.speed_slider.setValue(100)
        row = QHBoxLayout()
        self.start_button = QPushButton()
        self.stop_button = QPushButton()
        self.next_button = QPushButton()
        self.previous_button = QPushButton()
        row.addWidget(self.start_button)
        row.addWidget(self.stop_button)
        row.addWidget(self.next_button)
        row.addWidget(self.previous_button)
        self.apply_season_button = QPushButton()
        self.azimuth_spin = self._spin(0.0, 359.0, 1.0)
        self.altitude_spin = self._spin(-20.0, 90.0, 1.0)
        self.azimuth_spin.setValue(180.0)
        self.altitude_spin.setValue(35.0)
        self.sun_button = QPushButton()
        self.reset_accumulated_button = QPushButton()
        self.season_label = QLabel()
        self.date_label = QLabel()
        self.time_label = QLabel()
        self.from_label = QLabel()
        self.to_label = QLabel()
        self.step_label = QLabel()
        self.speed_label = QLabel()
        self.azimuth_label = QLabel()
        self.altitude_label = QLabel()
        for label, widget in [
            (self.season_label, self.season_combo),
            (None, self.apply_season_button),
            (self.azimuth_label, self.azimuth_spin),
            (self.altitude_label, self.altitude_spin),
            (None, self.sun_button),
            (self.date_label, self.date_edit),
            (self.time_label, self.time_edit),
            (self.from_label, self.start_time_edit),
            (self.to_label, self.end_time_edit),
            (self.step_label, self.step_spin),
            (self.speed_label, self.speed_spin),
            (None, self.speed_slider),
        ]:
            form.addRow(label, widget) if label else form.addRow(widget)
        form.addRow(row)
        self.reset_accumulated_button.setVisible(False)
        self.page_layouts["simulation"].addWidget(self.sim_group)
        self.sim_values_group = QGroupBox()
        sim_values_form = QFormLayout(self.sim_values_group)
        self.absolute_ground_value = QLabel()
        self.relative_ground_value = QLabel()
        self.ground_shadow_value = QLabel()
        self.selected_value = QLabel()
        self.selected_with_value = QLabel()
        self.selected_without_value = QLabel()
        self.ground_ratio_value = QLabel()
        self.absolute_ground_label = QLabel()
        self.relative_ground_label = QLabel()
        self.chart_ground_shadow_check = QCheckBox(); self.chart_ground_shadow_check.setChecked(True)
        self.chart_selected_check = QCheckBox(); self.chart_selected_check.setChecked(False)
        self.chart_selected_with_check = QCheckBox(); self.chart_selected_with_check.setChecked(False)
        self.chart_selected_without_check = QCheckBox(); self.chart_selected_without_check.setChecked(False)
        self.chart_ratio_check = QCheckBox(); self.chart_ratio_check.setChecked(False)
        self.ground_shadow_label = self.chart_ground_shadow_check
        self.selected_value_label = self.chart_selected_check
        self.selected_with_label = self.chart_selected_with_check
        self.selected_without_label = self.chart_selected_without_check
        self.ground_ratio_label = self.chart_ratio_check
        for label, value in [
            (self.absolute_ground_label, self.absolute_ground_value),
            (self.relative_ground_label, self.relative_ground_value),
            (self.chart_ground_shadow_check, self.ground_shadow_value),
            (self.chart_selected_check, self.selected_value),
            (self.chart_selected_with_check, self.selected_with_value),
            (self.chart_selected_without_check, self.selected_without_value),
            (self.chart_ratio_check, self.ground_ratio_value),
        ]:
            sim_values_form.addRow(label, value)
        self.page_layouts["simulation"].addWidget(self.sim_values_group)
        self.sim_metrics_group = QGroupBox()
        sim_metric_layout = QVBoxLayout(self.sim_metrics_group)
        self.sim_metrics_table = QTableWidget(0, 3)
        sim_metric_layout.addWidget(self.sim_metrics_table)
        self.page_layouts["simulation"].addWidget(self.sim_metrics_group)
        self.export_chart_button = QPushButton()
    def _build_view3d_page(self) -> None:
        self.view3d_group = QGroupBox()
        form = QFormLayout(self.view3d_group)
        self.axis_x_spin = self._spin(0.0, 359.0, 1.0)
        self.axis_y_spin = self._spin(0.0, 359.0, 1.0)
        self.axis_z_spin = self._spin(0.0, 359.0, 1.0)
        self.axis_x_spin.setValue(20.0)
        self.axis_y_spin.setValue(0.0)
        self.axis_z_spin.setValue(0.0)
        self.axis_x_slider = QSlider(Qt.Orientation.Horizontal)
        self.axis_y_slider = QSlider(Qt.Orientation.Horizontal)
        self.axis_z_slider = QSlider(Qt.Orientation.Horizontal)
        for slider, value in [(self.axis_x_slider, 20), (self.axis_y_slider, 0), (self.axis_z_slider, 0)]:
            slider.setRange(0, 359)
            slider.setValue(value)
        self.show_labels_check = QCheckBox()
        self.show_labels_check.setChecked(True)
        self.label_mode_label = QLabel()
        self.label_mode_combo = QComboBox()
        for mode in ["all", "selected", "none"]:
            self.label_mode_combo.addItem("", mode)
        self.map_plane_button = QPushButton()
        self.map_plane_button.setCheckable(True)
        self.map_plane_button.setStyleSheet("QPushButton:checked{background-color:#5a8f54;color:white;}")
        self.reset_3d_button = QPushButton()
        self.axis_hint_label = QLabel()
        self.axis_hint_label.setWordWrap(True)
        self.axis_x_label = QLabel()
        self.axis_y_label = QLabel()
        self.axis_z_label = QLabel()
        form.addRow(self.axis_x_label, self.axis_x_spin)
        form.addRow(self.axis_x_slider)
        form.addRow(self.axis_y_label, self.axis_y_spin)
        form.addRow(self.axis_y_slider)
        form.addRow(self.axis_z_label, self.axis_z_spin)
        form.addRow(self.axis_z_slider)
        form.addRow(self.show_labels_check)
        form.addRow(self.label_mode_label, self.label_mode_combo)
        form.addRow(self.map_plane_button)
        form.addRow(self.reset_3d_button)
        form.addRow(self.axis_hint_label)
        self.page_layouts["view3d"].addWidget(self.view3d_group)
    def _build_exchange_page(self) -> None:
        self.exchange_group = QGroupBox()
        layout = QVBoxLayout(self.exchange_group)
        self.project_save_button = QPushButton()
        self.project_load_button = QPushButton()
        self.cleanup_hint_label = QLabel()
        self.cleanup_hint_label.setWordWrap(True)
        self.cleanup_button = QPushButton()
        layout.addWidget(self.project_save_button)
        layout.addWidget(self.project_load_button)
        layout.addWidget(self.export_chart_button)
        layout.addWidget(self.cleanup_hint_label)
        layout.addWidget(self.cleanup_button)
        self.page_layouts["exchange"].addWidget(self.exchange_group)
        self.page_layouts["exchange"].addWidget(self.object_library_group)
    def refresh_library(self, library: Library) -> None:
        for combo, entries in [
            (self.place_combo, library.places),
            (self.object_combo, library.objects),
            (self.ground_combo, library.grounds),
        ]:
            combo.clear()
            for entry in entries:
                combo.addItem(entry.get("name", ""), entry)
    def retranslate(self, i18n: I18n) -> None:
        self.i18n = i18n
        for index, (_, message_key) in enumerate(self.page_specs):
            self.setTabText(index, self.i18n.t(message_key))
        self._retranslate_map()
        self._retranslate_objects()
        self._retranslate_ground()
        self._retranslate_simulation()
        self._retranslate_view3d()
        self._retranslate_exchange()
    def _retranslate_map(self) -> None:
        self.lang_label.setText(self.i18n.t("language.label"))
        for index in range(self.lang_combo.count()):
            self.lang_combo.setItemText(index, language_label(self.lang_combo.itemData(index)))
        self.location_group.setTitle(self.i18n.t("group.location"))
        self.lat_label.setText(self.i18n.t("location.latitude"))
        self.lon_label.setText(self.i18n.t("location.longitude"))
        self.zoom_label.setText(self.i18n.t("location.zoom"))
        self.goto_button.setText(self.i18n.t("location.goto"))
        self.undo_button.setText(self.i18n.t("edit.undo"))
        self.redo_button.setText(self.i18n.t("edit.redo"))
        self.place_group.setTitle(self.i18n.t("library.places"))
        self.place_name_label.setText(self.i18n.t("library.name"))
        self.place_load_label.setText(self.i18n.t("library.saved"))
        self.save_place_button.setText(self.i18n.t("library.save_place"))
        self.load_place_button.setText(self.i18n.t("library.load_place"))
        self.import_buildings_button.setText(self.i18n.t("osm.import_buildings"))
        self.offline_group.setTitle(self.i18n.t("offline.group"))
        self.offline_mode_check.setText(self.i18n.t("offline.mode"))
        self.offline_query_label.setText(self.i18n.t("offline.query"))
        self.offline_zmin_label.setText(self.i18n.t("offline.zmin"))
        self.offline_zmax_label.setText(self.i18n.t("offline.zmax"))
        self.download_visible_button.setText(self.i18n.t("offline.download_visible"))
        self.download_place_button.setText(self.i18n.t("offline.download_place"))
    def _retranslate_objects(self) -> None:
        self.object_group.setTitle(self.i18n.t("group.objects"))
        labels = [
            (self.object_kind_label, "object.kind"),
            (self.selected_name_label, "object.name"),
            (self.object_color_button, "object.color"),
            (self.add_button, "object.add"),
            (self.draw_custom_button, "object.draw_custom"),
            (self.object_import_buildings_button, "osm.import_buildings"),
            (self.delete_button, "object.delete"),
            (self.mesh_edit_check, "object.mesh_edit"),
            (self.show_dims_button, "object.show_dimensions"),
            (self.show_all_dims_button, "object.show_all_dimensions"),
            (self.height_label, "object.height"),
            (self.width_label, "object.width"),
            (self.depth_label, "object.depth"),
            (self.trunk_label, "object.trunk"),
            (self.crown_width_label, "object.crown_width"),
            (self.crown_height_label, "object.crown_height"),
            (self.tilt_label, "object.tilt"),
            (self.orientation_label, "object.orientation"),
        ]
        for widget, key in labels:
            widget.setText(self.i18n.t(key))
        self.kind_combo.setItemText(0, self.i18n.t("object.none"))
        for index in range(1, self.kind_combo.count()):
            key = self.kind_combo.itemData(index)
            self.kind_combo.setItemText(index, self.i18n.t(TREE_KINDS[key].label_key))
        self.kind_combo.set_group_label("objects", self.i18n.t("group.objects"))
        self.kind_combo.set_group_label("broadleaf", self.i18n.t("picker.broadleaf"))
        self.kind_combo.set_group_label("conifer", self.i18n.t("picker.conifer"))
        self.object_library_group.setTitle(self.i18n.t("library.objects"))
        self.object_name_label.setText(self.i18n.t("library.name"))
        self.object_load_label.setText(self.i18n.t("library.saved"))
        self.save_object_button.setText(self.i18n.t("library.save_object"))
        self.load_object_button.setText(self.i18n.t("library.load_object"))
        self.import_object_button.setText(self.i18n.t("library.import_object"))
        self.export_object_button.setText(self.i18n.t("library.export_object"))
    def _retranslate_ground(self) -> None:
        self.ground_group.setTitle(self.i18n.t("group.ground"))
        self.draw_ground_button.setText(self.i18n.t("ground.draw"))
        self.edit_ground_button.setText(self.i18n.t("ground.edit"))
        self.clear_ground_button.setText(self.i18n.t("ground.clear"))
        self.ground_title_label.setText(self.i18n.t("ground.name"))
        self.ground_color_button.setText(self.i18n.t("ground.color"))
        self.ground_hint_label.setText(self.i18n.t("ground.finish_hint"))
        self.ground_library_group.setTitle(self.i18n.t("library.grounds"))
        self.ground_name_label.setText(self.i18n.t("library.name"))
        self.ground_load_label.setText(self.i18n.t("library.saved"))
        self.save_ground_button.setText(self.i18n.t("library.save_ground"))
        self.load_ground_button.setText(self.i18n.t("library.load_ground"))
    def _retranslate_sun(self) -> None:
        self.sun_group.setTitle(self.i18n.t("group.sun"))
        self.sun_season_label.setText(self.i18n.t("simulation.season")); self.sun_date_label.setText(self.i18n.t("simulation.date")); self.sun_time_label.setText(self.i18n.t("simulation.time"))
        self.azimuth_label.setText(self.i18n.t("sun.azimuth")); self.altitude_label.setText(self.i18n.t("sun.altitude"))
        self.sun_button.setText(self.i18n.t("sun.manual")); self.sun_apply_season_button.setText(self.i18n.t("simulation.apply_season"))
        for index in range(self.sun_season_combo.count()):
            self.sun_season_combo.setItemText(index, self.i18n.t(f"season.{self.sun_season_combo.itemData(index)}"))
    def _retranslate_simulation(self) -> None:
        self.sim_group.setTitle(self.i18n.t("group.simulation"))
        self.sim_values_group.setTitle(self.i18n.t("group.metrics"))
        self.sim_metrics_group.setTitle(self.i18n.t("metrics.object_table"))
        self.sim_metrics_table.setHorizontalHeaderLabels([self.i18n.t("metrics.object"), self.i18n.t("metrics.type"), self.i18n.t("metrics.shadow_m2")])
        self.absolute_ground_label.setText(self.i18n.t("metrics.absolute_ground_label"))
        self.relative_ground_label.setText(self.i18n.t("metrics.relative_ground_label"))
        self.ground_shadow_label.setText(self.i18n.t("metrics.ground_shadow_label"))
        self.selected_value_label.setText(self.i18n.t("metrics.selected_label"))
        self.selected_with_label.setText(self.i18n.t("metrics.selected_with_label"))
        self.selected_without_label.setText(self.i18n.t("metrics.selected_without_label"))
        self.ground_ratio_label.setText(self.i18n.t("metrics.ratio_label"))
        self.export_chart_button.setText(self.i18n.t("chart.export"))
        self.azimuth_label.setText(self.i18n.t("sun.azimuth"))
        self.altitude_label.setText(self.i18n.t("sun.altitude"))
        self.sun_button.setText(self.i18n.t("sun.manual"))
        for label, key in [
            (self.season_label, "simulation.season"),
            (self.date_label, "simulation.date"),
            (self.time_label, "simulation.time"),
            (self.from_label, "simulation.from"),
            (self.to_label, "simulation.to"),
            (self.step_label, "simulation.step"),
            (self.speed_label, "simulation.speed"),
        ]:
            label.setText(self.i18n.t(key))
        for button, key in [
            (self.start_button, "simulation.start"),
            (self.stop_button, "simulation.stop"),
            (self.next_button, "simulation.next"),
            (self.previous_button, "simulation.previous"),
            (self.apply_season_button, "simulation.apply_season"),
            (self.reset_accumulated_button, "simulation.reset_accumulated"),
        ]:
            button.setText(self.i18n.t(key))
        for index in range(self.season_combo.count()):
            self.season_combo.setItemText(index, self.i18n.t(f"season.{self.season_combo.itemData(index)}"))
    def _retranslate_view3d(self) -> None:
        self.view3d_group.setTitle(self.i18n.t("group.view3d"))
        self.axis_x_label.setText(self.i18n.t("view.axis_x"))
        self.axis_y_label.setText(self.i18n.t("view.axis_y"))
        self.axis_z_label.setText(self.i18n.t("view.axis_z"))
        self.show_labels_check.setText(self.i18n.t("view.show_labels"))
        self.label_mode_label.setText(self.i18n.t("view.label_mode"))
        for index in range(self.label_mode_combo.count()):
            self.label_mode_combo.setItemText(index, self.i18n.t(f"view.label_mode.{self.label_mode_combo.itemData(index)}"))
        self.map_plane_button.setText(self.i18n.t("view.map_plane"))
        self.reset_3d_button.setText(self.i18n.t("view.reset"))
        self.axis_hint_label.setText(self.i18n.t("view.axis_hint"))
    def _retranslate_exchange(self) -> None:
        self.exchange_group.setTitle(self.i18n.t("group.exchange"))
        self.project_save_button.setText(self.i18n.t("project.save"))
        self.project_load_button.setText(self.i18n.t("project.load"))
        self.export_chart_button.setText(self.i18n.t("chart.export"))
        self.cleanup_hint_label.setText(self.i18n.t("cleanup.hint"))
        self.cleanup_button.setText(self.i18n.t("cleanup.delete_all"))
