from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap, QPolygonF
from PySide6.QtWidgets import QMenu, QToolButton, QVBoxLayout, QWidget

from core.objects import TREE_KINDS, TreeKind


def render_kind_icon(kind: TreeKind, size: int = 28) -> QIcon:
    """Draws a small flat silhouette representing a tree/geometry kind."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    color = QColor(kind.color)
    painter.setPen(QPen(color.darker(150), max(1.0, size * 0.04)))
    painter.setBrush(color)
    margin = size * 0.12
    width = size - 2 * margin
    shape = kind.crown_shape

    if kind.category == "tree":
        trunk_w = size * 0.12
        trunk_h = size * 0.30
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#6b4a2b"))
        painter.drawRect(QRectF(size / 2 - trunk_w / 2, size - margin - trunk_h, trunk_w, trunk_h))
        painter.setPen(QPen(color.darker(150), max(1.0, size * 0.04)))
        painter.setBrush(color)
        crown_top = margin
        crown_bottom = size - margin - trunk_h * 0.7
        if shape.startswith("conifer"):
            points = QPolygonF([
                QPointF(size / 2, crown_top),
                QPointF(margin, crown_bottom),
                QPointF(size - margin, crown_bottom),
            ])
            painter.drawPolygon(points)
        else:
            painter.drawEllipse(QRectF(margin, crown_top, width, crown_bottom - crown_top))
    else:
        rect = QRectF(margin, margin, width, width)
        if shape == "sphere":
            painter.drawEllipse(rect)
        elif shape == "box":
            painter.drawRect(rect)
        elif shape == "cylinder":
            painter.drawRoundedRect(rect, width * 0.3, width * 0.15)
        elif shape == "pyramid":
            points = QPolygonF([
                QPointF(size / 2, margin),
                QPointF(margin, size - margin),
                QPointF(size - margin, size - margin),
            ])
            painter.drawPolygon(points)
        elif shape == "cone":
            points = QPolygonF([
                QPointF(size / 2, margin),
                QPointF(margin * 1.3, size - margin),
                QPointF(size - margin * 1.3, size - margin),
            ])
            painter.drawPolygon(points)
        elif shape == "plane":
            painter.drawRect(QRectF(margin, size / 2 - width * 0.15, width, width * 0.3))
        else:
            painter.drawRect(rect)
    painter.end()
    return QIcon(pixmap)


class KindPickerButton(QToolButton):
    """Drop-down button showing grouped icon previews instead of a plain list."""

    currentIndexChanged = Signal(int)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.setIconSize(self.iconSize() * 1.2)
        self._items: list[dict] = []
        self._actions: list = []
        self._group_menus: dict[str, QMenu] = {}
        self._group_labels: dict[str, str] = {}
        self._current_index = -1
        self._menu = QMenu(self)
        self.setMenu(self._menu)

    def addItem(self, text: str, data=None, group: str | None = None, icon: QIcon | None = None) -> int:
        index = len(self._items)
        self._items.append({"text": text, "data": data, "icon": icon, "group": group})
        target = self._menu
        if group is not None:
            target = self._group_menus.get(group)
            if target is None:
                target = self._menu.addMenu(self._group_labels.get(group, group))
                self._group_menus[group] = target
        action = target.addAction(icon, text) if icon else target.addAction(text)
        action.triggered.connect(lambda _checked=False, i=index: self.setCurrentIndex(i))
        self._actions.append(action)
        if self._current_index < 0:
            self._current_index = index
            self._update_button_display()
        return index

    def set_group_label(self, group: str, text: str) -> None:
        self._group_labels[group] = text
        menu = self._group_menus.get(group)
        if menu is not None:
            menu.setTitle(text)

    def count(self) -> int:
        return len(self._items)

    def itemData(self, index: int):
        return self._items[index]["data"]

    def setItemText(self, index: int, text: str) -> None:
        self._items[index]["text"] = text
        self._actions[index].setText(text)
        if index == self._current_index:
            self._update_button_display()

    def currentData(self):
        if 0 <= self._current_index < len(self._items):
            return self._items[self._current_index]["data"]
        return None

    def currentIndex(self) -> int:
        return self._current_index

    def findData(self, data) -> int:
        for i, item in enumerate(self._items):
            if item["data"] == data:
                return i
        return -1

    def setCurrentIndex(self, index: int) -> None:
        if index < 0 or index >= len(self._items) or index == self._current_index:
            return
        self._current_index = index
        self._update_button_display()
        self.currentIndexChanged.emit(index)

    def _update_button_display(self) -> None:
        item = self._items[self._current_index]
        self.setText(item["text"])
        self.setIcon(item["icon"] or QIcon())


class KindPickerBar(QWidget):
    """Vertical icon-only picker docked at the edge of the 3D preview.

    One button per category (geometry, broadleaf, conifer); each opens a
    drop-down with the kinds of that category. The button icon follows the
    last picked kind."""

    kind_selected = Signal(str)

    GROUPS = [
        ("geometry", "picker.geometry", "cube"),
        ("broadleaf", "picker.broadleaf", "broadleaf_1"),
        ("conifer", "picker.conifer", "conifer_1"),
    ]

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 6, 2, 6)
        layout.setSpacing(6)
        self._buttons: dict[str, QToolButton] = {}
        self._tooltip_keys: dict[str, str] = {}
        self._actions: list[tuple[object, str]] = []
        for group, tooltip_key, default_key in self.GROUPS:
            keys = [key for key, kind in TREE_KINDS.items() if self._in_group(key, kind, group)]
            button = QToolButton(self)
            button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
            button.setIconSize(QSize(30, 30))
            button.setAutoRaise(True)
            button.setStyleSheet("QToolButton::menu-indicator{image:none;}")
            button.setIcon(render_kind_icon(TREE_KINDS[default_key], 30))
            menu = QMenu(button)
            for key in keys:
                action = menu.addAction(render_kind_icon(TREE_KINDS[key]), "")
                action.triggered.connect(lambda _checked=False, g=group, k=key: self._on_pick(g, k))
                self._actions.append((action, key))
            button.setMenu(menu)
            layout.addWidget(button)
            self._buttons[group] = button
            self._tooltip_keys[group] = tooltip_key
        layout.addStretch(1)

    @staticmethod
    def _in_group(key: str, kind: TreeKind, group: str) -> bool:
        if group == "geometry":
            return kind.category == "geometry"
        return key.startswith(group)

    def _on_pick(self, group: str, key: str) -> None:
        self._buttons[group].setIcon(render_kind_icon(TREE_KINDS[key], 30))
        self.kind_selected.emit(key)

    def retranslate(self, i18n) -> None:
        for group, tooltip_key in self._tooltip_keys.items():
            self._buttons[group].setToolTip(i18n.t(tooltip_key))
        for action, key in self._actions:
            action.setText(i18n.t(TREE_KINDS[key].label_key))
