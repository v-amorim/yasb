from collections.abc import Callable
from typing import Any, override

import PyQt6.QtCore as QtCore
from PyQt6.QtCore import QRectF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QMouseEvent, QPainter, QPainterPath, QPaintEvent, QPalette
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QSlider, QWidget

from core.utils.optical import center_icon_on_text
from core.utils.tabular import set_tabular

# pyqtProperty exists at runtime but is missing from the PyQt6 type stubs
pyqtProperty: Callable[..., Any] = getattr(QtCore, "pyqtProperty")

ELIDE_AFTER_CHARS = 24


class _ElidedLabel(QLabel):
    """A label that ends in an ellipsis when the row is too narrow, and never asks for more than ELIDE_AFTER_CHARS."""

    elision_changed = pyqtSignal(bool)

    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self._elided = False

    @override
    def sizeHint(self) -> QSize:
        hint = super().sizeHint()
        return QSize(min(hint.width(), self.fontMetrics().averageCharWidth() * ELIDE_AFTER_CHARS), hint.height())

    @override
    def minimumSizeHint(self) -> QSize:
        return QSize(0, super().minimumSizeHint().height())

    @override
    def paintEvent(self, a0: QPaintEvent | None) -> None:
        rect = self.contentsRect()
        text = self.fontMetrics().elidedText(self.text(), Qt.TextElideMode.ElideRight, rect.width())
        elided = text != self.text()
        if elided != self._elided:
            self._elided = elided
            self.elision_changed.emit(elided)
        style = self.style()
        if style is None:
            return
        painter = QPainter(self)
        style.drawItemText(
            painter, rect, int(self.alignment().value), self.palette(), self.isEnabled(), text, self.foregroundRole()
        )
        painter.end()


class FillSlider(QSlider):
    """A horizontal slider drawn as a row that fills up to its value, with an icon, a name and the value on top.

    Stylesheets color it like any widget: background-color for the empty track, selection-background-color
    for the filled part and color for the text. qproperty-radius rounds its corners. The icon, name and value
    are labels with the classes icon, label and value. A long name ends in an ellipsis.
    """

    right_clicked = pyqtSignal()

    def __init__(self, icon: str, name: str, parent: QWidget | None = None) -> None:
        super().__init__(Qt.Orientation.Horizontal, parent)
        self._radius = 4
        self.setRange(0, 100)
        self.setMinimumHeight(28)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 10, 0)
        layout.setSpacing(8)
        self._icon = self._add_label(layout, QLabel(icon, self), "icon")
        self._icon.setVisible(bool(icon))
        self._name = self._add_label(layout, _ElidedLabel(name, self), "label")
        self._name.elision_changed.connect(self._show_full_name)
        center_icon_on_text(self._icon, self._name)
        layout.setStretchFactor(self._name, 1)
        self._value = self._add_label(layout, QLabel("", self), "value")
        set_tabular(self._value)
        self._show_value(self.value())

    @override
    def sliderChange(self, change: QSlider.SliderChange) -> None:
        # Callers sync rows with signals blocked, so the label follows the value here, not through valueChanged
        if change == QSlider.SliderChange.SliderValueChange:
            self._show_value(self.value())
        super().sliderChange(change)

    @property
    def icon_label(self) -> QLabel:
        return self._icon

    def _add_label(self, layout: QHBoxLayout, label: QLabel, class_name: str) -> QLabel:
        label.setProperty("class", class_name)
        label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        layout.addWidget(label)
        return label

    def _show_full_name(self, elided: bool) -> None:
        self.setToolTip(self._name.text() if elided else "")

    def _show_value(self, value: int) -> None:
        self._value.setText(f"{value}%")

    def _get_radius(self) -> str:
        return f"{self._radius}px"

    # A string so the stylesheet can pass the --radius-tile token, whose value ends in px
    def _set_radius(self, radius: str) -> None:
        self._radius = int(str(radius).removesuffix("px"))
        self.update()

    radius: str = pyqtProperty(str, _get_radius, _set_radius)

    def _value_at(self, x: float) -> int:
        ratio = max(0.0, min(1.0, x / self.width())) if self.width() > 0 else 0.0
        return round(self.minimum() + ratio * (self.maximum() - self.minimum()))

    @override
    def mousePressEvent(self, ev: QMouseEvent | None) -> None:
        if ev is not None and ev.button() == Qt.MouseButton.RightButton:
            self.right_clicked.emit()
            ev.accept()
            return
        # The whole row is the handle: a press jumps to the cursor instead of paging toward it
        if ev is None or ev.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(ev)
            return
        self.setSliderDown(True)
        self.setValue(self._value_at(ev.position().x()))
        ev.accept()

    @override
    def mouseMoveEvent(self, ev: QMouseEvent | None) -> None:
        if ev is not None and self.isSliderDown():
            self.setValue(self._value_at(ev.position().x()))
            ev.accept()

    @override
    def mouseReleaseEvent(self, ev: QMouseEvent | None) -> None:
        if ev is not None and ev.button() == Qt.MouseButton.LeftButton and self.isSliderDown():
            self.setSliderDown(False)
            ev.accept()

    @override
    def paintEvent(self, ev: QPaintEvent | None) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        bounds = QRectF(self.rect())
        outline = QPainterPath()
        outline.addRoundedRect(bounds, self._radius, self._radius)
        painter.setClipPath(outline)

        palette = self.palette()
        painter.fillRect(bounds, palette.color(self.backgroundRole()))
        span = self.maximum() - self.minimum()
        ratio = (self.value() - self.minimum()) / span if span > 0 else 0.0
        painter.fillRect(
            QRectF(0, 0, bounds.width() * ratio, bounds.height()), palette.color(QPalette.ColorRole.Highlight)
        )
        painter.end()
