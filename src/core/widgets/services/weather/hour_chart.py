from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, override

from PyQt6 import QtCore
from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QMouseEvent, QPainter, QPainterPath, QPaintEvent, QPalette, QPen
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from core.utils.tabular import set_tabular

# pyqtProperty exists at runtime but is missing from the PyQt6 type stubs
pyqtProperty: Callable[..., Any] = getattr(QtCore, "pyqtProperty")

BAR_WIDTH = 14
BAR_RADIUS = 2
# The plot is split in two bands so the line never touches a bar: the line above, the bars below
LABEL_HEIGHT = 14
LINE_TOP = 3
LINE_BAND = 22
BAR_MAX_HEIGHT = 40
MIN_TEMP_SPAN = 4
TIP_GAP = 8


@dataclass
class ChartHour:
    label: str
    temp: float
    temp_text: str
    feels_text: str
    rain: float


class HourTip(QFrame):
    """Stacked tooltip: the hour, its temperature, then feels and rain.

    The stylesheet gives it background-color (the box) and qproperty-radius; the box is painted here because a
    translucent top-level window does not paint a stylesheet background.
    """

    def __init__(self, parent: QWidget, rain_icon: str):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.ToolTip
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setProperty("class", "hour-tip")
        self._radius = 4

        self._hour = self._label("hour-tip-hour")
        self._temp = self._label("hour-tip-temp")
        self._feels = self._label("hour-tip-detail")
        self._drop = self._label("hour-tip-detail hour-tip-icon")
        self._drop.setText(rain_icon)
        self._rain = self._label("hour-tip-detail")

        detail = QHBoxLayout()
        detail.setContentsMargins(0, 0, 0, 0)
        detail.setSpacing(0)
        detail.addStretch(1)
        for part in (self._feels, self._drop, self._rain):
            detail.addWidget(part)
        detail.addStretch(1)

        column = QVBoxLayout(self)
        column.setContentsMargins(8, 4, 8, 4)
        column.setSpacing(0)
        column.addWidget(self._hour)
        column.addWidget(self._temp)
        column.addLayout(detail)

    def _get_radius(self) -> str:
        return f"{self._radius}px"

    # A string so the stylesheet can pass the --radius-tile token, whose value ends in px
    def _set_radius(self, radius: str) -> None:
        self._radius = int(str(radius).removesuffix("px"))
        self.update()

    radius: str = pyqtProperty(str, _get_radius, _set_radius)

    def _label(self, class_name: str) -> QLabel:
        part = QLabel(self)
        part.setProperty("class", class_name)
        part.setAlignment(Qt.AlignmentFlag.AlignCenter)
        set_tabular(part)
        return part

    @override
    def paintEvent(self, a0: QPaintEvent | None) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self.palette().color(self.backgroundRole()))
        painter.drawRoundedRect(QRectF(self.rect()), self._radius, self._radius)

    def show_hour(self, hour: ChartHour, left: float, right: float, anchor_x: float, anchor_y: float) -> None:
        """Show above the point (anchor_x, anchor_y), kept between left and right (the card's edges)."""
        self._hour.setText(hour.label)
        self._temp.setText(hour.temp_text)
        self._feels.setText(f"Feels {hour.feels_text} · ")
        self._rain.setText(f" {hour.rain:g}%")
        self.resize(self.sizeHint())
        x = min(max(anchor_x - self.width() / 2, left), max(right - self.width(), left))
        self.move(round(x), round(anchor_y - self.height() - TIP_GAP))
        if not self.isVisible():
            self.show()


class HourChart(QWidget):
    """Rain-chance bars under a temperature line for the next hours; hovering a bar opens its tooltip.

    Colors come from the stylesheet through the widget palette, like the other custom-painted widgets:
    background-color is the bars, selection-background-color the hovered bar, alternate-background-color the
    line and color the hour labels.
    """

    def __init__(self, hours: list[ChartHour], rain_icon: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.setProperty("class", "hour-chart")
        self.setMouseTracking(True)
        self._hours = hours
        self._hover: int | None = None
        self._rain_icon = rain_icon
        self._tip: HourTip | None = None

    def _color(self, role: QPalette.ColorRole) -> QColor:
        self.ensurePolished()
        return self.palette().color(role)

    def _step(self) -> float:
        return self.width() / max(len(self._hours), 1)

    def _bar_height(self, hour: ChartHour) -> float:
        return min(hour.rain, 100) / 100 * BAR_MAX_HEIGHT

    def _bar_top(self, index: int) -> float:
        return self.height() - LABEL_HEIGHT - self._bar_height(self._hours[index])

    def _line_y(self, temp: float, low: float, span: float) -> float:
        return LINE_TOP + (low + span - temp) / span * LINE_BAND

    def _hour_at(self, x: float) -> int | None:
        if not self._hours:
            return None
        return max(0, min(int(x / self._step()), len(self._hours) - 1))

    @override
    def paintEvent(self, a0: QPaintEvent | None) -> None:
        if not self._hours:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        step = self._step()
        bar_color = self._color(self.backgroundRole())
        hover_color = self._color(QPalette.ColorRole.Highlight)

        painter.setPen(Qt.PenStyle.NoPen)
        for index, hour in enumerate(self._hours):
            painter.setBrush(hover_color if index == self._hover else bar_color)
            painter.drawRoundedRect(
                QRectF(
                    index * step + step / 2 - BAR_WIDTH / 2, self._bar_top(index), BAR_WIDTH, self._bar_height(hour)
                ),
                BAR_RADIUS,
                BAR_RADIUS,
            )

        temps = [hour.temp for hour in self._hours]
        low = min(temps)
        span = max(max(temps) - low, MIN_TEMP_SPAN)
        line = QPainterPath()
        for index, hour in enumerate(self._hours):
            point = QPointF(index * step + step / 2, self._line_y(hour.temp, low, span))
            if index == 0:
                line.moveTo(point)
            else:
                line.lineTo(point)
        pen = QPen(self._color(QPalette.ColorRole.AlternateBase), 2)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(line)

        painter.setPen(self._color(self.foregroundRole()))
        painter.setFont(self.font())
        label_rect = QRectF(0, self.height() - LABEL_HEIGHT, self.width(), LABEL_HEIGHT)
        last = len(self._hours) - 1
        for index, alignment in (
            (0, Qt.AlignmentFlag.AlignLeft),
            (last // 2, Qt.AlignmentFlag.AlignHCenter),
            (last, Qt.AlignmentFlag.AlignRight),
        ):
            painter.drawText(label_rect, alignment | Qt.AlignmentFlag.AlignBottom, self._hours[index].label)

    @override
    def mouseMoveEvent(self, a0: QMouseEvent | None) -> None:
        if a0 is None:
            return
        index = self._hour_at(a0.position().x())
        if index is None or index == self._hover:
            return
        self._hover = index
        step = self._step()
        anchor = self.mapToGlobal(QPointF(index * step + step / 2, self._bar_top(index)).toPoint())
        card = self.window()
        left = card.mapToGlobal(card.rect().topLeft()).x()
        if self._tip is None:
            self._tip = HourTip(card, self._rain_icon)
        self._tip.show_hour(self._hours[index], left, left + card.width(), anchor.x(), anchor.y())
        self.update()

    @override
    def leaveEvent(self, a0: QtCore.QEvent | None) -> None:
        self._hover = None
        self._hide_tip()
        self.update()

    @override
    def hideEvent(self, a0: Any) -> None:
        self._hide_tip()

    def _hide_tip(self) -> None:
        if self._tip is not None:
            self._tip.hide()
