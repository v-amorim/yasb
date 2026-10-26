"""Bar-anchored popups float as their own cards: centred under the bar, a gap above them, a thread up to the item."""

from collections.abc import Callable

from PyQt6.QtCore import QEasingCurve, QPoint, QPropertyAnimation, QRect, Qt, pyqtProperty
from PyQt6.QtGui import QColor, QPainter, QPaintEvent
from PyQt6.QtWidgets import QApplication, QWidget

from core.bar_motion import animations_enabled

GAP = 18
DROP = 8
DROP_MS = 180
EXIT_MS = 120
THREAD_WIDTH = 2
# The card's border width: the thread runs into it so the two read as one line
BORDER = 2


def fade_ms(floating: bool, opening: bool, base: int) -> int:
    """How long a popup's fade runs: none when Windows animations are off, else the card's or the plain popup's own."""
    if not animations_enabled():
        return 0
    if not floating:
        return base
    return DROP_MS if opening else EXIT_MS


def centred_under(popup: QWidget, frame: QWidget) -> QPoint:
    """Where a popup of its current size sits: centred under the bar frame, GAP below it, kept on screen."""
    origin = frame.mapToGlobal(QPoint(0, 0))
    x = origin.x() + (frame.width() - popup.width()) // 2
    y = origin.y() + frame.height() + GAP
    screen = QApplication.screenAt(frame.mapToGlobal(frame.rect().center()))
    if screen is not None:
        area = screen.geometry()
        x = max(area.left(), min(x, area.right() - popup.width()))
        y = max(area.top(), min(y, area.bottom() - popup.height()))
    return QPoint(x, y)


def thread_start(item: QWidget, frame: QWidget, anchor: QWidget | None = None) -> QPoint:
    """Where the thread leaves the bar: under the item when it sits on a stacked bar's bottom row, else the bar's edge.

    anchor is the part of the item the popup opens from, when the item holds more than that part.
    """
    element = anchor or getattr(item, "_widget_container", None) or item
    center = element.mapToGlobal(QPoint(element.width() // 2, element.height()))
    bar = frame.window()
    on_bottom_row = getattr(bar, "is_stacked", False) and getattr(item, "parent_layout_type", "") in ("left", "right")
    if on_bottom_row:
        return center
    return QPoint(center.x(), frame.mapToGlobal(QPoint(0, frame.height())).y())


class PopupThread(QWidget):
    """A click-through line from the item that opened a popup down into the popup's top border."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowDoesNotAcceptFocus
            | Qt.WindowType.WindowTransparentForInput
            | Qt.WindowType.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setProperty("class", "popup-thread")
        self._color = QColor("#3A4060")

    def get_color(self) -> QColor:
        return self._color

    def set_color(self, color: QColor) -> None:
        self._color = QColor(color)
        self.update()

    # Set by qproperty-threadcolor; lowercase because Qt's stylesheet parser lowercases property names
    threadcolor = pyqtProperty(QColor, fget=get_color, fset=set_color)

    def follow(self, start: QPoint, card: QRect) -> None:
        """Span from start down to the card's top border; hidden when the item is not above the card."""
        end_y = card.top() + BORDER
        if end_y <= start.y() or not card.left() < start.x() < card.right():
            self.hide()
            return
        self.setGeometry(start.x() - THREAD_WIDTH // 2, start.y(), THREAD_WIDTH, end_y - start.y())
        self.show()

    def paintEvent(self, a0: QPaintEvent | None) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), self._color)
        painter.end()


class Floating:
    """The float behaviour one bar-anchored popup owns: its place, its drop-in and its thread."""

    _open: Floating | None = None

    def __init__(
        self, popup: QWidget, item: QWidget, frame_of: Callable[[], QWidget | None], anchor: QWidget | None = None
    ) -> None:
        self._popup = popup
        self._item = item
        self._anchor = anchor
        self._frame_of = frame_of
        self.thread = PopupThread()
        self._drop = QPropertyAnimation(popup, b"pos")
        self._drop.setDuration(DROP_MS)
        self._drop.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._drop.finished.connect(self.place)

    def _frame(self) -> QWidget | None:
        frame = self._frame_of()
        # YASB styles each bar window, not the app, so the thread takes the bar's sheet for its colour
        if frame is not None and not self.thread.styleSheet():
            self.thread.setStyleSheet(frame.window().styleSheet())
        return frame

    def place(self) -> None:
        """Move the popup to its spot under the bar, unless it is dropping in, and hang the thread to it."""
        frame = self._frame()
        if frame is None:
            return
        target = centred_under(self._popup, frame)
        if self._drop.state() == QPropertyAnimation.State.Running:
            self._drop.setEndValue(target)
        else:
            self._popup.move(target)
        self.thread.follow(thread_start(self._item, frame, self._anchor), QRect(target, self._popup.size()))

    def drop_in(self) -> None:
        """Start the open motion: the card drops DROP px into place while it fades in."""
        frame = self._frame()
        if frame is None:
            return
        # One card at a time: Qt closes a Popup window for another, but the tray's Tool window stays open
        if Floating._open is not None and Floating._open is not self:
            Floating._open._popup.hide_animated()  # pyright: ignore[reportAttributeAccessIssue]
        Floating._open = self
        # A bar mid-expand has not reached the size the card hangs from yet
        manager = getattr(frame.window(), "autohide_manager", None)
        if manager is not None:
            manager.finish_motion()
        target = centred_under(self._popup, frame)
        self._drop.stop()
        if not animations_enabled():
            self._popup.move(target)
            self.thread.setWindowOpacity(1.0)
            self.thread.follow(thread_start(self._item, frame, self._anchor), QRect(target, self._popup.size()))
            return
        self._drop.setStartValue(target - QPoint(0, DROP))
        self._drop.setEndValue(target)
        self._popup.move(target - QPoint(0, DROP))
        self._drop.start()
        self.thread.follow(thread_start(self._item, frame, self._anchor), QRect(target, self._popup.size()))

    def fade(self, opacity: float) -> None:
        self.thread.setWindowOpacity(opacity)

    def close(self) -> None:
        if Floating._open is self:
            Floating._open = None
        self._drop.stop()
        self.thread.hide()
