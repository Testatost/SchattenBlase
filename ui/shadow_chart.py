from __future__ import annotations
from datetime import datetime
import csv
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QFileDialog, QGridLayout, QLabel, QPushButton, QSizePolicy, QWidget
from config import CHART_DIR
from i18n import I18n

class ShadowChart(QWidget):
    def __init__(self, i18n: I18n, parent=None) -> None:
        super().__init__(parent)
        self.i18n = i18n
        self.samples: list[tuple[float, dict[str, float]]] = []
        self.keys = ["ground_shadow", "selected", "selected_with", "selected_without", "ratio"]
        self.enabled: dict[str, bool] = {key: key == "ground_shadow" for key in self.keys}
        self.setMinimumHeight(205)
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._last_timestamp = 0.0
    def add_sample(self, moment: datetime | None, values: dict[str, float]) -> None:
        timestamp = moment.timestamp() if moment is not None else (self._last_timestamp + 1.0)
        if self.samples and timestamp == self.samples[-1][0]:
            self.samples[-1] = (timestamp, dict(values))
        else:
            self.samples.append((timestamp, dict(values)))
        self.samples = self.samples[-2000:]
        self._last_timestamp = timestamp
        self.update()
    def clear(self) -> None:
        self.samples.clear(); self._last_timestamp = 0.0; self.update()
    def set_key_enabled(self, key: str, enabled: bool) -> None:
        if key in self.enabled:
            self.enabled[key] = enabled
            self.update()
    def enabled_keys(self) -> list[str]:
        return [key for key in self.keys if self.enabled.get(key, False)]
    def export(self, parent=None) -> None:
        CHART_DIR.mkdir(parents=True, exist_ok=True)
        path, _ = QFileDialog.getSaveFileName(parent or self, self.i18n.t("chart.export"), str(CHART_DIR / "schattenverlauf.csv"), self.i18n.t("chart.export_filter"))
        if not path:
            return
        if path.lower().endswith(".png"):
            self.grab().save(path)
            return
        with open(path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh, delimiter=";")
            writer.writerow(["timestamp", "datetime", *self.keys])
            for ts, values in self.samples:
                writer.writerow([ts, datetime.fromtimestamp(ts).isoformat(timespec="seconds"), *[f"{values.get(k, 0.0):.6f}" for k in self.keys]])
    def paintEvent(self, _event) -> None:
        painter = QPainter(self); painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(6, 4, -6, -6)
        painter.fillRect(rect, QColor(26, 29, 31))
        painter.setPen(QPen(QColor(90, 96, 100), 1)); painter.drawRect(rect)
        enabled = self.enabled_keys()
        stats_width = 270 if rect.width() >= 1000 else 205
        plot = rect.adjusted(58, 18, -stats_width, -34)
        if plot.width() < 260:
            plot = rect.adjusted(48, 18, -18, -34)
            stats_width = 0
        painter.setPen(QPen(QColor(110, 116, 120), 1))
        painter.drawLine(QPointF(plot.left(), plot.top()), QPointF(plot.left(), plot.bottom()))
        painter.drawLine(QPointF(plot.left(), plot.bottom()), QPointF(plot.right(), plot.bottom()))
        if len(self.samples) < 2 or not enabled:
            painter.setPen(QColor(190, 190, 190)); painter.drawText(plot, Qt.AlignmentFlag.AlignCenter, self.i18n.t("chart.empty")); return
        xs = [s[0] for s in self.samples]; min_x, max_x = min(xs), max(xs)
        vals = [v.get(k, 0.0) for _t, v in self.samples for k in enabled]
        max_y = max(max(vals), 1.0); min_y = min(0.0, min(vals))
        span_y = max(max_y - min_y, 1.0)
        span_x = max(max_x - min_x, 1.0)
        label_map = {
            "ground_shadow": self.i18n.t("chart.ground_shadow"),
            "selected": self.i18n.t("chart.selected"),
            "selected_with": self.i18n.t("chart.selected_with"),
            "selected_without": self.i18n.t("chart.selected_without"),
            "ratio": self.i18n.t("chart.ratio"),
        }
        colors = {"ground_shadow": QColor(120, 180, 230), "selected": QColor(230, 190, 80), "selected_with": QColor(180, 130, 230), "selected_without": QColor(120, 210, 120), "ratio": QColor(230, 120, 120)}
        painter.setPen(QPen(QColor(62, 67, 72), 1))
        for i in range(6):
            y = plot.bottom() - plot.height() * i / 5.0
            value = min_y + span_y * i / 5.0
            painter.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
            painter.setPen(QColor(178, 182, 186))
            painter.drawText(QPointF(rect.left() + 4, y + 4), f"{value:.1f}")
            painter.setPen(QPen(QColor(62, 67, 72), 1))
        for i in range(6):
            x = plot.left() + plot.width() * i / 5.0
            ts = min_x + span_x * i / 5.0
            painter.drawLine(QPointF(x, plot.top()), QPointF(x, plot.bottom()))
            painter.setPen(QColor(178, 182, 186))
            painter.drawText(QPointF(x - 22, rect.bottom() - 8), datetime.fromtimestamp(ts).strftime("%H:%M"))
            painter.setPen(QPen(QColor(62, 67, 72), 1))
        for key in enabled:
            painter.setPen(QPen(colors.get(key, QColor(220, 220, 220)), 2))
            last = None
            for t, values in self.samples:
                px = plot.left() + (t - min_x) / span_x * plot.width()
                py = plot.bottom() - (values.get(key, 0.0) - min_y) / span_y * plot.height()
                point = QPointF(px, py)
                if last is not None:
                    painter.drawLine(last, point)
                last = point
        painter.setPen(QColor(210, 210, 210))
        painter.drawText(QPointF(plot.left() + 4, rect.top() + 12), self.i18n.t("chart.y_axis"))
        painter.drawText(QPointF(plot.right() - 70, rect.bottom() - 8), self.i18n.t("chart.time_axis"))
        if stats_width > 0:
            x = plot.right() + 14
            y = plot.top() + 3
            painter.setPen(QColor(210, 210, 210))
            for key in enabled:
                series = [v.get(key, 0.0) for _t, v in self.samples]
                if not series:
                    continue
                avg = sum(series) / len(series)
                painter.setPen(QPen(colors.get(key, QColor(220, 220, 220)), 3))
                painter.drawLine(QPointF(x, y + 6), QPointF(x + 22, y + 6))
                painter.setPen(QColor(220, 220, 220))
                painter.drawText(QPointF(x + 30, y + 10), label_map.get(key, key))
                y += 18
                painter.setPen(QColor(185, 190, 194))
                painter.drawText(QPointF(x + 30, y + 10), f"min: {min(series):.1f}   max: {max(series):.1f}   Ø: {avg:.1f}")
                y += 24

class ChartPanel(QWidget):
    def __init__(self, i18n: I18n, parent=None) -> None:
        super().__init__(parent)
        self.i18n = i18n
        self.chart = ShadowChart(i18n)
        self.setMinimumWidth(0)
        self.setMinimumHeight(215)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout = QGridLayout(self)
        layout.setContentsMargins(2, 0, 2, 2)
        layout.setSpacing(2)
        self.title = QLabel(); self.export_button = QPushButton()
        self.export_button.clicked.connect(lambda: self.chart.export(self))
        layout.addWidget(self.title, 0, 0, 1, 4)
        self.export_button.setVisible(False)
        layout.addWidget(self.chart, 1, 0, 1, 4)
        self.retranslate(i18n)
    def retranslate(self, i18n: I18n) -> None:
        self.i18n = i18n; self.chart.i18n = i18n
        self.title.setText(i18n.t("chart.title"))
        self.export_button.setText(i18n.t("chart.export"))
