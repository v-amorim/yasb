import logging
import math
from collections.abc import Sequence
from typing import override

from PyQt6.QtCore import QEvent, QObject, QPoint, QTimer, pyqtProperty
from PyQt6.QtGui import QImage, QRegion
from PyQt6.QtWidgets import QFrame, QLabel, QWidget

from core.utils.qobject import is_valid_qobject

OFF = "off"
EDGES = "edges"
MASS = "mass"
MODES = (OFF, EDGES, MASS)

INK_FLOOR = 8 / 255
_LABEL_EVENTS = frozenset(
    {
        QEvent.Type.Polish,
        QEvent.Type.FontChange,
        QEvent.Type.StyleChange,
        QEvent.Type.Show,
        QEvent.Type.Hide,
    }
)
_FRAME_EVENTS = _LABEL_EVENTS | {QEvent.Type.Resize, QEvent.Type.LayoutRequest}


def normalize_mode(value: str) -> str:
    mode = value.strip().strip("\"'").lower()
    if mode in MODES:
        return mode
    logging.warning("Unknown ink balance mode %r, expected one of %s; balancing is off", value, ", ".join(MODES))
    return OFF


def column_ink(alpha: bytes, width: int, height: int) -> list[float]:
    """The strongest coverage (0 to 1) in each pixel column of an alpha plane."""
    return [max(alpha[x : width * height : width], default=0) / 255 for x in range(width)]


def ink_edges(columns: Sequence[float]) -> tuple[float, float] | None:
    """Where the drawn ink starts and ends along x, in fractional pixels, or None when nothing is drawn.

    An edge column that is only partly covered pushes its edge inward by the part left uncovered.
    """
    inked = [x for x, coverage in enumerate(columns) if coverage > INK_FLOOR]
    if not inked:
        return None
    first, last = inked[0], inked[-1]
    return first + (1 - columns[first]), last + columns[last]


def ink_centre(alpha: bytes, width: int, height: int) -> float | None:
    """The alpha-weighted horizontal centre of an alpha plane in pixels, or None when nothing is drawn."""
    weights = [sum(alpha[x : width * height : width]) for x in range(width)]
    total = sum(weights)
    if total == 0:
        return None
    return sum((x + 0.5) * weight for x, weight in enumerate(weights)) / total


def balance_delta(mode: str, *, width: float, left: float, right: float, centre: float) -> float:
    """How far the net left margin (left margin minus right margin) must grow, in pixels, to balance the ink.

    left and right are the ink edges, centre the ink's alpha-weighted centre, all measured in a frame of this width.
    A margin of m on the left moves the ink m pixels right but moves the frame's centre only m / 2.
    """
    if mode == EDGES:
        return (width - right) - left
    if mode == MASS:
        return -2 * (centre - width / 2)
    return 0.0


def _ink_plane(frame: QWidget, labels: Sequence[QLabel]) -> tuple[bytes, int, int]:
    """The alpha of the frame's labels drawn as they paint, on a transparent image of the frame's size."""
    image = QImage(frame.width(), frame.height(), QImage.Format.Format_ARGB32)
    image.fill(0)
    for label in labels:
        label.render(image, label.mapTo(frame, QPoint(0, 0)), QRegion(), QWidget.RenderFlag.DrawChildren)
    bits = image.constBits()
    assert bits is not None
    return bits.asstring(image.sizeInBytes())[3::4], image.width(), image.height()


def measure_ink(frame: QWidget, labels: Sequence[QLabel]) -> tuple[float, float, float] | None:
    """(left edge, right edge, centre) of the labels' drawn ink in the frame's coordinates, or None when blank."""
    alpha, width, height = _ink_plane(frame, labels)
    edges = ink_edges(column_ink(alpha, width, height))
    centre = ink_centre(alpha, width, height)
    if edges is None or centre is None:
        return None
    return edges[0], edges[1], centre


class _InkBalance(QObject):
    def __init__(self, frame: QFrame) -> None:
        super().__init__(frame)
        self._frame = frame
        self.mode = OFF
        self._applying = False
        # Net margins already tried for this mode, text and width, with how far off each one measured
        self._key: tuple[str, tuple[str, ...], int] | None = None
        self._tried: dict[int, float] = {}
        # Set once a step would revisit a tried margin, so the frame holds still until the key changes
        self._held = False
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(0)
        self._timer.timeout.connect(self.apply)  # type: ignore
        frame.installEventFilter(self)
        for label in frame.findChildren(QLabel):
            label.installEventFilter(self)

    @override
    def eventFilter(self, a0: QObject | None, a1: QEvent | None) -> bool:
        if a1 is None:
            return False
        kind = a1.type()
        if kind == QEvent.Type.ChildAdded and a0 is self._frame and hasattr(a1, "child"):
            child = a1.child()  # type: ignore
            if isinstance(child, QLabel):
                child.installEventFilter(self)
        elif kind in (_FRAME_EVENTS if a0 is self._frame else _LABEL_EVENTS):
            # Layout and geometry settle after the event, so measure on the next loop turn
            self.schedule()
        return False

    def schedule(self) -> None:
        if self.mode != OFF:
            self._timer.start()

    def set_mode(self, mode: str) -> None:
        self.mode = mode
        if mode == OFF:
            self._set_margins(0)
        else:
            self.schedule()

    def _set_margins(self, net: int) -> None:
        layout = self._frame.layout()
        if layout is None:
            return
        margins = layout.contentsMargins()
        left, right = max(net, 0), max(-net, 0)
        if (margins.left(), margins.right()) != (left, right):
            layout.setContentsMargins(left, margins.top(), right, margins.bottom())

    def apply(self) -> None:
        frame = self._frame
        if self._applying or self.mode == OFF or not is_valid_qobject(frame) or not frame.isVisible():
            return
        layout = frame.layout()
        if layout is None:
            return
        self._applying = True
        try:
            layout.activate()
            # A frame narrower than its content has not met its new size yet; its Resize event comes back here
            if frame.width() < frame.minimumSizeHint().width():
                return
            labels = [label for label in frame.findChildren(QLabel) if not label.isHidden()]
            ink = measure_ink(frame, labels)
            if ink is None:
                return
            left, right, centre = ink
            delta = balance_delta(self.mode, width=frame.width(), left=left, right=right, centre=centre)
            # A frame that fits its content changes width with every margin, so only a fixed width keeps its memory
            key = (self.mode, tuple(label.text() for label in labels), frame.width())
            if key != self._key:
                self._key, self._tried, self._held = key, {}, False
            margins = layout.contentsMargins()
            current = margins.left() - margins.right()
            self._tried[current] = abs(delta)
            step = math.floor(delta + 0.5)
            if self._held or not step:
                return
            # A fixed-width slot moves centred content half a pixel per margin pixel, so a step can overshoot both ways
            if current + step in self._tried:
                self._set_margins(min(self._tried, key=self._tried.__getitem__))
                self._held = True
                return
            self._set_margins(current + step)
        finally:
            self._applying = False


class InkBalancedFrame(QFrame):
    """A bar widget's container whose icon and label are balanced from their drawn pixels.

    The mode ("edges", "mass" or "off") is the inkbalance property, so a stylesheet sets it:
    `.widget-container { qproperty-inkbalance: edges; }`.
    """

    def __init__(self) -> None:
        super().__init__()
        self._ink_balance = OFF
        self._balance: _InkBalance | None = None

    def _get_inkbalance(self) -> str:
        return self._ink_balance

    def _set_inkbalance(self, value: str) -> None:
        mode = normalize_mode(value)
        if mode == self._ink_balance:
            return
        self._ink_balance = mode
        if self._balance is None:
            self._balance = _InkBalance(self)
        self._balance.set_mode(mode)

    inkbalance: str = pyqtProperty(str, _get_inkbalance, _set_inkbalance)

    def rebalance(self) -> None:
        """Measure and apply now instead of on the next loop turn."""
        if self._balance is not None:
            self._balance.apply()
