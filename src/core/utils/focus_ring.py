"""Keyboard focus in a card: a ring GAP px outside the focused control, drawn only when Tab moved the focus there."""

from typing import override

from PyQt6.QtCore import QEvent, QObject, QPoint, QRect, QRectF, Qt, pyqtProperty
from PyQt6.QtGui import QColor, QFocusEvent, QPainter, QPaintEvent, QPen
from PyQt6.QtWidgets import QApplication, QWidget

GAP = 2
WIDTH = 3
KEYBOARD = (Qt.FocusReason.TabFocusReason, Qt.FocusReason.BacktabFocusReason)


class FocusRing(QWidget):
    """A click-through ring over a card, around the control Tab focused."""

    def __init__(self, card: QWidget) -> None:
        super().__init__(card)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setProperty("class", "focus-ring")
        self._color = QColor("#7386D0")
        self._radius = 4
        self._round = False
        self._target_height = 0
        self.hide()

    def get_color(self) -> QColor:
        return self._color

    def set_color(self, color: QColor) -> None:
        self._color = QColor(color)
        self.update()

    def get_radius(self) -> str:
        return f"{self._radius}px"

    def set_radius(self, radius: str) -> None:
        self._radius = int(str(radius).removesuffix("px"))
        self.update()

    # Set by qproperty-ringcolor and qproperty-radius; lowercase because Qt's stylesheet parser lowercases property names
    ringcolor = pyqtProperty(QColor, fget=get_color, fset=set_color)
    radius = pyqtProperty(str, fget=get_radius, fset=set_radius)

    def corner_radius(self) -> float:
        """The ring's radius at the middle of its line, so it stays concentric with the control's corners."""
        inner = self._target_height / 2 if self._round else self._radius
        return inner + GAP + WIDTH / 2

    def show_around(self, control: QWidget) -> None:
        out = GAP + WIDTH
        top_left = control.mapTo(self.parentWidget(), QPoint(0, 0))
        self.setGeometry(QRect(top_left, control.size()).adjusted(-out, -out, out, out))
        # A square control here is a round button
        self._round = abs(control.width() - control.height()) <= 1
        self._target_height = control.height()
        self.show()
        self.raise_()

    @override
    def paintEvent(self, a0: QPaintEvent | None) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(self._color, WIDTH))
        half = WIDTH / 2
        rect = QRectF(self.rect()).adjusted(half, half, -half, -half)
        painter.drawRoundedRect(rect, self.corner_radius(), self.corner_radius())
        painter.end()


class _FocusWatcher(QObject):
    """One app-wide filter: a focus change inside a card with a ring moves or clears that ring."""

    @override
    def eventFilter(self, a0: QObject | None, a1: QEvent | None) -> bool:
        if a1 is None or not isinstance(a0, QWidget):
            return False
        if a1.type() == QEvent.Type.Hide:
            ring = getattr(a0, "focus_ring", None)
            if isinstance(ring, FocusRing):
                ring.hide()
            return False
        if a1.type() not in (QEvent.Type.FocusIn, QEvent.Type.FocusOut):
            return False
        ring = getattr(a0.window(), "focus_ring", None)
        if not isinstance(ring, FocusRing) or a0 is ring:
            return False
        if a1.type() == QEvent.Type.FocusIn and isinstance(a1, QFocusEvent) and a1.reason() in KEYBOARD:
            ring.show_around(a0)
        else:
            ring.hide()
        return False


_watcher: _FocusWatcher | None = None


def attach_focus_ring(card: QWidget) -> FocusRing:
    """Give a card window its focus ring; the first card also installs the app-wide watcher."""
    global _watcher
    app = QApplication.instance()
    if _watcher is None and app is not None:
        _watcher = _FocusWatcher()
        app.installEventFilter(_watcher)
    ring = FocusRing(card)
    setattr(card, "focus_ring", ring)
    return ring
