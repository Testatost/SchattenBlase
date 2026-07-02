from __future__ import annotations
from datetime import datetime
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QMessageBox, QPushButton, QSizePolicy, QVBoxLayout, QWidget
from core.objects import SimulationState
from i18n import I18n
from ui.shadow_chart import ChartPanel

class MetricsPanel(QWidget):
    row_selected = Signal(str)
    def __init__(self, state: SimulationState, i18n: I18n, parent=None) -> None:
        super().__init__(parent)
        self.state = state; self.i18n = i18n
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(3)
        self.top_widget = QWidget()
        top = QHBoxLayout(self.top_widget)
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(3)
        self.ground_label = QLabel(); self.ground_shadow_label = QLabel(); self.selected_area_label = QLabel()
        self.selected_with_label = QLabel(); self.selected_without_label = QLabel(); self.ratio_label = QLabel()
        self._metric_keys = ["ground", "ground_shadow", "selected", "selected_with", "selected_without", "ratio"]
        self._metric_labels = [self.ground_label, self.ground_shadow_label, self.selected_area_label, self.selected_with_label, self.selected_without_label, self.ratio_label]
        for key, label in zip(self._metric_keys, self._metric_labels):
            btn = QPushButton("[?]"); btn.setFixedWidth(32)
            btn.clicked.connect(lambda _=False, k=key: self._show_help(k))
            top.addWidget(btn); top.addWidget(label)
        layout.addWidget(self.top_widget)
        self.top_widget.setVisible(False)
        self.chart_panel = ChartPanel(i18n)
        layout.addWidget(self.chart_panel)
        self.retranslate(i18n)
    def retranslate(self, i18n: I18n) -> None:
        self.i18n = i18n
        self.chart_panel.retranslate(i18n)
    def update_values(self, selected_area: float, selected_with: float, selected_without: float, total: float, ground_shadow: float, ground: float, per_object: dict[str, float], moment: datetime | None = None) -> None:
        ratio = (ground_shadow / ground * 100.0) if ground > 0.0 else 0.0
        self.ground_label.setText(self.i18n.t("ground.area", area=ground))
        self.ground_shadow_label.setText(self.i18n.t("metrics.ground_shadow", area=ground_shadow))
        self.selected_area_label.setText(self.i18n.t("metrics.selected_area", area=selected_area))
        self.selected_with_label.setText(self.i18n.t("metrics.selected_with", area=selected_with))
        self.selected_without_label.setText(self.i18n.t("metrics.selected_without", area=selected_without))
        self.ratio_label.setText(self.i18n.t("metrics.ground_ratio", ratio=ratio))
        self.chart_panel.chart.add_sample(moment, {"ground_shadow": ground_shadow, "selected": selected_area, "selected_with": selected_with, "selected_without": selected_without, "ratio": ratio})
    def _show_help(self, key: str) -> None:
        QMessageBox.information(self, self.i18n.t("metrics.help_title"), self.i18n.t(f"metrics.help.{key}"))
