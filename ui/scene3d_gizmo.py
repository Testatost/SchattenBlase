from __future__ import annotations
from PySide6.QtCore import QPointF
from PySide6.QtGui import QColor, QPen
from PySide6.QtCore import Qt


def draw_gizmo(view, painter) -> None:
    rect = view._gizmo_rect(); center = rect.center(); radius = rect.width() * 0.43
    painter.setPen(QPen(QColor(70, 70, 70), 1)); painter.setBrush(QColor(255, 255, 255, 210))
    painter.drawEllipse(center, radius, radius)
    painter.setBrush(Qt.BrushStyle.NoBrush); painter.setPen(QPen(QColor(160, 160, 160), 1))
    for factor in (-0.55, 0.0, 0.55):
        painter.drawEllipse(center, radius, radius * (1.0 - abs(factor) * 0.55))
        painter.drawEllipse(center, radius * (1.0 - abs(factor) * 0.55), radius)
    axes = [("X", (1, 0, 0), QColor(180, 40, 40)), ("Y", (0, 1, 0), QColor(40, 150, 60)), ("Z", (0, 0, 1), QColor(40, 80, 190))]
    for label, (x, y, z), color in axes:
        rx, ry, _ = view._rotate3(x, y, z)
        end = center + QPointF(rx * radius * 0.88, ry * radius * 0.88)
        painter.setPen(QPen(color, 4)); painter.drawLine(center, end); painter.drawText(end + QPointF(-6, -6), label)
