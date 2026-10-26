"""Hover expand and collapse motion for an auto-hide bar that peeks.

The bar window stays one fixed size for the whole motion, large enough for both end states and the
width overshoot. Only the bar frame inside it grows, so Windows never resizes a layered window per
frame. Every widget is rendered once per end state, ahead of time, and the frame paints those images,
so a hover starts on the next frame and no frame lays real widgets out at a size they were not built
for. The real class swap and widget show or hide run once the motion ends, hidden behind the canvas.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import cache
from typing import TYPE_CHECKING

from PyQt6.QtCore import (
    QEasingCurve,
    QElapsedTimer,
    QEvent,
    QObject,
    QPoint,
    QPointF,
    QRect,
    QRectF,
    QSize,
    Qt,
    QTimer,
)
from PyQt6.QtGui import QImage, QPainter, QPaintEvent, QRegion
from PyQt6.QtWidgets import QApplication, QLabel, QWidget

from core.utils.win32.bindings.user32 import SystemParametersInfoBool

if TYPE_CHECKING:
    from core.bar import Bar

type Bezier = tuple[float, float, float, float]

SPI_GETCLIENTAREAANIMATION = 0x1042
SECTIONS = ("left", "center", "right")
CACHE_POLL_MS = 500


@dataclass(frozen=True)
class Track:
    """One animated property: its length in ms, CSS cubic-bezier control points and start delay in ms."""

    duration: int
    curve: Bezier
    delay: int = 0


@dataclass(frozen=True)
class Timing:
    width: Track
    height: Track
    text: Track  # clock and date moving and growing between their peek and full size
    pills: Track  # the side widgets fading


EASE_OUT: Bezier = (0.2, 0.0, 0.0, 1.0)
# The clock and date grow over the width's whole run: on EASE_OUT they reached full size in a few frames, then waited for the bar.
EASE_IN_OUT: Bezier = (0.4, 0.0, 0.2, 1.0)

# The one place to tweak the motion: durations in ms and cubic-bezier curves, as picked from the mocks.
EXPAND = Timing(
    width=Track(250, (0.34, 1.2, 0.64, 1.0)),
    height=Track(190, EASE_OUT),
    text=Track(250, EASE_IN_OUT),
    pills=Track(110, EASE_OUT, delay=120),
)
COLLAPSE = Timing(
    width=Track(260, EASE_OUT),
    height=Track(260, EASE_OUT),
    text=Track(260, EASE_IN_OUT),
    pills=Track(120, EASE_OUT),
)


@cache
def cubic_bezier(x1: float, y1: float, x2: float, y2: float) -> QEasingCurve:
    """The CSS cubic-bezier(x1, y1, x2, y2) timing function as a Qt easing curve."""
    curve = QEasingCurve(QEasingCurve.Type.BezierSpline)
    curve.addCubicBezierSegment(QPointF(x1, y1), QPointF(x2, y2), QPointF(1.0, 1.0))
    return curve


def animations_enabled() -> bool:
    """Whether Windows has client-area animation effects on."""
    return SystemParametersInfoBool(SPI_GETCLIENTAREAANIMATION) is not False


@dataclass(frozen=True)
class Look:
    """The animated state: frame size in px, and 0 to 1 for the text move and the pill opacity."""

    width: float
    height: float
    text: float
    pills: float


@dataclass(frozen=True)
class Shot:
    """A widget's visible element rendered once: its image, where it sits in the bar frame, its text baseline."""

    image: QImage
    rect: QRect
    baseline: float  # y of the text baseline from the top of rect


@dataclass(frozen=True)
class Piece:
    """A widget the peek bar keeps: it exists in both states and moves from one to the other."""

    peek: Shot
    full: Shot


@dataclass(frozen=True)
class Other:
    """A widget only the full bar shows: it fades in, held at its distance from one edge or the center."""

    shot: Shot
    anchor: str


@dataclass
class Scene:
    peek_size: QSize
    full_size: QSize
    pieces: list[Piece]
    others: list[Other]
    window: QRect
    full_rect: QRect = field(default_factory=QRect)
    strip: QImage | None = None
    strip_rect: QRect = field(default_factory=QRect)  # screen coordinates

    def piece_box(self, piece: Piece, frame_width: float, t: float) -> tuple[float, float, float]:
        """Left edge, width and text baseline (frame coordinates) of a piece at progress t of its move."""

        def offset(shot: Shot, size: QSize) -> float:
            return shot.rect.x() + shot.rect.width() / 2 - size.width() / 2

        width = _lerp(piece.peek.rect.width(), piece.full.rect.width(), t)
        center = frame_width / 2 + _lerp(offset(piece.peek, self.peek_size), offset(piece.full, self.full_size), t)
        baseline = _lerp(piece.peek.rect.y() + piece.peek.baseline, piece.full.rect.y() + piece.full.baseline, t)
        return center - width / 2, width, baseline


@dataclass
class Cache:
    signature: tuple[object, ...]
    peek: dict[QWidget, tuple[str, Shot]]
    full: dict[QWidget, tuple[str, Shot]]
    peek_size: QSize
    full_size: QSize
    strip: QImage | None = None


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


class _Canvas(QWidget):
    """Covers the bar frame and paints the widget images for the current look."""

    def __init__(self, parent: QWidget, scene: Scene, look: Look):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.scene = scene
        self.look = look

    def paintEvent(self, a0: QPaintEvent | None) -> None:
        scene, look = self.scene, self.look
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        if look.pills > 0:
            painter.setOpacity(look.pills)
            shift_x = {
                "left": 0,
                "center": round((self.width() - scene.full_size.width()) / 2),
                "right": self.width() - scene.full_size.width(),
            }
            shift_y = round((self.height() - scene.full_size.height()) / 2)
            boxes = [scene.piece_box(piece, self.width(), look.text) for piece in scene.pieces]
            group_left = min((left for left, _, _ in boxes), default=self.width() / 2)
            group_right = max((left + width for left, width, _ in boxes), default=self.width() / 2)
            for other in scene.others:
                rect = other.shot.rect
                painter.save()
                if other.anchor == "left":
                    painter.setClipRect(QRectF(0, 0, group_left, self.height()))
                elif other.anchor == "right":
                    painter.setClipRect(QRectF(group_right, 0, self.width() - group_right, self.height()))
                painter.drawImage(rect.x() + shift_x[other.anchor], rect.y() + shift_y, other.shot.image)
                painter.restore()
            painter.setOpacity(1.0)
        for piece in scene.pieces:
            self._paint_piece(painter, piece)
        painter.end()

    def _paint_piece(self, painter: QPainter, piece: Piece) -> None:
        t = self.look.text
        left, width, baseline = self.scene.piece_box(piece, self.width(), t)
        if t <= 0 or t >= 1:
            shot = piece.peek if t <= 0 else piece.full
            painter.drawImage(round(left), round(baseline - shot.baseline), shot.image)
            return
        # One element, two renders at the same rect and baseline: the cross-fade never spans the group
        shots = (piece.peek, piece.full)
        rects = [
            QRectF(
                left,
                baseline - shot.baseline * width / shot.rect.width(),
                width,
                shot.rect.height() * width / shot.rect.width(),
            )
            for shot in shots
        ]
        bounds = rects[0].united(rects[1]).toAlignedRect()
        ratio = piece.peek.image.devicePixelRatio()
        blend = QImage(
            round(bounds.width() * ratio), round(bounds.height() * ratio), QImage.Format.Format_ARGB32_Premultiplied
        )
        blend.setDevicePixelRatio(ratio)
        blend.fill(Qt.GlobalColor.transparent)
        mix = QPainter(blend)
        mix.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        for shot, rect, opacity in zip(shots, rects, (1 - t, t), strict=True):
            mix.setOpacity(opacity)
            mix.drawImage(rect.translated(-QPointF(bounds.topLeft())), shot.image)
            mix.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
        mix.end()
        painter.drawImage(bounds.topLeft(), blend)


class _StripCanvas(QWidget):
    """Paints the workspace dots under the bar while the real strip window sits out of the motion."""

    def __init__(self, parent: QWidget, image: QImage):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.image = image
        self.opacity = 1.0

    def paintEvent(self, a0: QPaintEvent | None) -> None:
        painter = QPainter(self)
        painter.setOpacity(self.opacity)
        painter.drawImage(0, 0, self.image)
        painter.end()


class BarMotion(QObject):
    """Animates an auto-hide bar between its peek and full size."""

    def __init__(
        self,
        bar: Bar,
        targets: Callable[[], list[QWidget]],
        visuals: Callable[[bool, list[QWidget]], None],
    ):
        super().__init__(bar)
        self._bar = bar
        self._targets = targets
        self._visuals = visuals
        self._shown_peek = False
        self._pending: tuple[bool, list[QWidget]] | None = None
        self._busy = False
        self._landed = False
        self._scene: Scene | None = None
        self._canvas: _Canvas | None = None
        self._strip_canvas: _StripCanvas | None = None
        self._cache: Cache | None = None
        self._rest: dict[bool, tuple[tuple[object, ...], QSize, dict[QWidget, tuple[str, Shot]]]] = {}
        self._strip_image: QImage | None = None
        self._poll_signature: tuple[object, ...] | None = None
        self._peek_look = self._full_look = self._look = Look(0, 0, 0, 0)
        self._from = self._to = self._look
        self._timing = EXPAND
        self._total = 0
        self.expanding = True
        self._clock = QElapsedTimer()
        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._timer.timeout.connect(self._tick)
        self._landing = QTimer(self)
        self._landing.setSingleShot(True)
        self._landing.timeout.connect(self._settle_down)
        self._poll = QTimer(self)
        self._poll.timeout.connect(self.refresh_cache)

    @property
    def active(self) -> bool:
        return self._busy

    def is_collapsing(self) -> bool:
        return self._busy and not self.expanding and self._scene is not None

    def frame_interval(self) -> int:
        """Milliseconds between frames: one per refresh of the screen the bar is on."""
        screen = self._bar.screen()
        hz = screen.refreshRate() if screen is not None else 0
        return max(1, int(1000 / (hz if hz >= 30 else 60)))

    def available(self) -> bool:
        bar = self._bar
        return bool(
            bar.isVisible()
            and bar.animation.get("enabled", False)
            and bar.config.style == "bar"
            and animations_enabled()
        )

    def start_polling(self) -> None:
        """Keep both end states rendered ahead of time while the bar rests."""
        self._poll.start(CACHE_POLL_MS)

    def stop(self) -> None:
        self._poll.stop()
        self.finish()

    def apply_now(self, peeking: bool, hidden: list[QWidget]) -> None:
        self._visuals(peeking, hidden)
        self._shown_peek = peeking

    def run(self, expanding: bool, hidden: list[QWidget]) -> None:
        """Animate to the end state the manager already flipped to; its widgets change once the motion ends."""
        if self._landed:
            self._settle_down()
        if not self.available() and not self._busy:
            self.apply_now(not expanding, hidden)
            self._bar.position_bar()
            return
        self._pending = (not expanding, hidden)
        self.expanding = expanding
        if self._scene is None:
            try:
                self._open(expanding, hidden)
            except Exception:
                logging.exception("Bar motion failed, jumping to the end state")
                self._settle_down()
                return
        self._begin_segment()

    def finish(self) -> None:
        """Jump to the end state of the running motion."""
        if self._busy:
            self._land()
            self._settle_down()

    def seek(self, elapsed: float) -> None:
        """Draw the frame `elapsed` ms into the running segment; the frame timer calls this."""
        if self._scene is None:
            return
        timing = self._timing

        def at(start: float, end: float, track: Track) -> float:
            progress = min(max((elapsed - track.delay) / track.duration, 0.0), 1.0)
            return _lerp(start, end, cubic_bezier(*track.curve).valueForProgress(progress))

        a, b = self._from, self._to
        look = Look(
            at(a.width, b.width, timing.width),
            at(a.height, b.height, timing.height),
            at(a.text, b.text, timing.text),
            at(a.pills, b.pills, timing.pills),
        )
        self._draw(look)
        if elapsed >= self._total:
            self._timer.stop()
            self._land()
            self._landing.start(self.frame_interval())

    def _tick(self) -> None:
        self.seek(self._clock.nsecsElapsed() / 1e6)

    def _begin_segment(self) -> None:
        timing = EXPAND if self.expanding else COLLAPSE
        self._timing = timing
        self._from = self._look
        self._to = self._full_look if self.expanding else self._peek_look
        self._total = max(t.delay + t.duration for t in (timing.width, timing.height, timing.text, timing.pills))
        self._timer.setInterval(self.frame_interval())
        self._clock.start()
        self._timer.start()

    def _signature(self) -> tuple[object, ...]:
        bar = self._bar
        frame = bar.bar_frame
        texts = tuple(label.text() for label in frame.findChildren(QLabel))
        return (hash(bar.styleSheet()), frame.devicePixelRatioF(), bar._popup_extra, texts)

    def refresh_cache(self) -> None:
        """Re-render both end states when something they show has changed, while the bar rests."""
        bar = self._bar
        manager = bar.autohide_manager
        if (
            self._busy
            or manager is None
            or not manager.is_enabled()
            or not bar.isVisible()
            or bar.underMouse()
            or bar._popup_extra
        ):
            return
        signature = self._signature()
        stable, self._poll_signature = self._poll_signature == signature, signature
        if not stable:
            return
        self._note_rest(force=True)
        if len(self._rest) == 2 or (self._cache is not None and self._cache.signature == signature):
            return
        try:
            self._build(self._targets())
        except Exception:
            logging.exception("Bar motion could not render the end states ahead of time")
            self._cache = None

    def _note_rest(self, force: bool = False) -> None:
        """Remember the size the bar really rests at in its current state: the animation must end exactly there."""
        signature = self._signature()
        seen = self._rest.get(self._shown_peek)
        if not force and seen is not None and seen[0] == signature:
            return
        self._rest[self._shown_peek] = (signature, QSize(self._bar.bar_frame.size()), self._shoot_all())
        self._strip_image = self._shoot_strip()

    def _rest_size(self, peeking: bool, built: QSize) -> QSize:
        noted = self._rest.get(peeking)
        return noted[1] if noted is not None else built

    def _settle_layout(self) -> None:
        frame = self._bar.bar_frame
        for _ in range(2):
            # Inner layouts first: a pill's size hint is stale until its own children have been laid out
            for child in reversed(frame.findChildren(QWidget)):
                inner = child.layout()
                if inner is not None:
                    inner.invalidate()
                    inner.activate()
            layout = frame.layout()
            if layout is not None:
                layout.invalidate()
                layout.activate()
            QApplication.sendPostedEvents(None, QEvent.Type.LayoutRequest.value)

    def _shoot(self, widget: QWidget) -> Shot:
        frame = self._bar.bar_frame
        element = getattr(widget, "_widget_container", None) or widget
        ratio = frame.devicePixelRatioF()
        image = QImage(
            max(1, round(element.width() * ratio)),
            max(1, round(element.height() * ratio)),
            QImage.Format.Format_ARGB32_Premultiplied,
        )
        image.setDevicePixelRatio(ratio)
        image.fill(Qt.GlobalColor.transparent)
        element.render(image, QPoint(), QRegion(), QWidget.RenderFlag.DrawChildren)
        label = element if isinstance(element, QLabel) else element.findChild(QLabel)
        if label is None:
            baseline = element.height() / 2
        else:
            metrics = label.fontMetrics()
            top = label.mapTo(element, QPoint(0, 0)).y()
            baseline = top + (label.height() + metrics.ascent() - metrics.descent()) / 2
        return Shot(image, QRect(element.mapTo(frame, QPoint(0, 0)), element.size()), baseline)

    def _shoot_strip(self) -> QImage | None:
        strip = self._bar._below_strip
        if strip is None:
            return None
        strip.adjustSize()
        ratio = strip.devicePixelRatioF()
        image = QImage(
            max(1, round(strip.width() * ratio)),
            max(1, round(strip.height() * ratio)),
            QImage.Format.Format_ARGB32_Premultiplied,
        )
        image.setDevicePixelRatio(ratio)
        image.fill(Qt.GlobalColor.transparent)
        strip.render(image, QPoint(), QRegion(), QWidget.RenderFlag.DrawChildren)
        return image

    def _strip_rect(self, image: QImage, full_rect: QRect) -> QRect:
        """Where the strip hangs: centered under (or over, for a bottom bar) the full bar, as BelowStrip.place puts it."""
        strip = self._bar._below_strip
        assert strip is not None
        width = round(image.width() / image.devicePixelRatio())
        height = round(image.height() / image.devicePixelRatio())
        x = full_rect.center().x() - width // 2
        if self._bar.alignment["position"] == "top":
            y = full_rect.bottom() + 1 + strip.GAP
        else:
            y = full_rect.top() - height - strip.GAP
        return QRect(x, y, width, height)

    def _shoot_all(self) -> dict[QWidget, tuple[str, Shot]]:
        """Every widget the bar shows now, by the section it sits in."""
        return {
            widget: (section, self._shoot(widget))
            for section in SECTIONS
            for widget in self._bar.widgets.get(section, [])
            if not widget.isHidden()
        }

    def _build(self, hidden: list[QWidget]) -> None:
        """Render the bar as it is, flip it to the other state, render again, and flip back without a paint."""
        bar, frame = self._bar, self._bar.bar_frame
        was_busy, self._busy = self._busy, True
        try:
            signature = self._signature()
            here = self._shown_peek
            original, here_size = frame.geometry(), frame.size()
            here_shots = self._shoot_all()
            self.apply_now(not here, hidden)
            width = height = -1
            for _ in range(5):
                _, _, new_width, new_height = bar.resting_geometry(not here)
                if (new_width, new_height) == (width, height):
                    break
                width, height = new_width, new_height
                frame.setGeometry(0, 0, width, height)
                self._settle_layout()
            there_size = QSize(width, height)
            there_shots = self._shoot_all()
            strip = self._shoot_strip()
            self.apply_now(here, hidden)
            frame.setGeometry(original)
            self._settle_layout()
            if bar._auto_width_manager is not None:
                bar._auto_width_manager.update()
            else:
                bar.balance_sections()
        finally:
            self._busy = was_busy
        peek, full = (here_shots, there_shots) if here else (there_shots, here_shots)
        peek_size, full_size = (here_size, there_size) if here else (there_size, here_size)
        self._cache = Cache(signature, peek, full, peek_size, full_size, strip)

    def _screen_rect(self, width: int, height: int) -> QRect:
        bar = self._bar
        geometry = bar.target_screen.geometry()
        x, y = bar.bar_pos(width, height, geometry.width(), geometry.height())
        return QRect(x, y, width, height)

    def _open(self, expanding: bool, hidden: list[QWidget]) -> None:
        bar, frame = self._bar, self._bar.bar_frame
        self._busy = True
        self._note_rest()
        peek_seen, full_seen = self._rest.get(True), self._rest.get(False)
        if peek_seen is not None and full_seen is not None:
            cache = Cache(peek_seen[0], peek_seen[2], full_seen[2], peek_seen[1], full_seen[1], self._strip_image)
        else:
            if self._cache is None or self._cache.signature != self._signature():
                self._build(hidden)
            cache = self._cache
        assert cache is not None
        peek_size, full_size = cache.peek_size, cache.full_size
        start_window = bar.geometry()
        peek_rest = self._rest_size(True, peek_size)
        full_rest = self._rest_size(False, full_size)
        end_size = full_rest if expanding else peek_rest

        peak = max(cubic_bezier(*EXPAND.width.curve).valueForProgress(step / 50) for step in range(51))
        overshoot = round(_lerp(peek_rest.width(), full_rest.width(), peak))
        available = bar.target_screen.geometry().width() - bar.padding["left"] - bar.padding["right"]
        full_rect = self._screen_rect(full_rest.width(), full_rest.height())
        strip_rect = self._strip_rect(cache.strip, full_rect) if cache.strip is not None else QRect()
        window = (
            start_window.united(self._screen_rect(end_size.width(), end_size.height()))
            .united(self._screen_rect(min(overshoot, available), full_size.height()))
            .united(full_rect)
        )
        if cache.strip is not None:
            window = window.united(strip_rect)
        pieces = [
            Piece(cache.peek[widget][1], shot) for widget, (_, shot) in cache.full.items() if widget in cache.peek
        ]
        others = [Other(shot, section) for widget, (section, shot) in cache.full.items() if widget not in cache.peek]
        self._scene = Scene(peek_size, full_size, pieces, others, window, full_rect, cache.strip, strip_rect)
        self._peek_look = Look(peek_rest.width(), peek_rest.height(), 0, 0)
        self._full_look = Look(full_rest.width(), full_rest.height(), 1, 1)
        self._look = self._full_look if not expanding else self._peek_look

        for name in SECTIONS:
            section = bar.section_frame(name)
            if section is not None:
                section.hide()
        self._canvas = _Canvas(frame, self._scene, self._look)
        self._canvas.show()
        if cache.strip is not None and bar._below_strip is not None:
            bar._below_strip.hide()
            self._strip_canvas = _StripCanvas(bar, cache.strip)
            self._strip_canvas.setGeometry(strip_rect.translated(-window.topLeft()))
            self._strip_canvas.show()
        self._draw(self._look)
        # Windows shows the old bitmap at the new rect until the next flush, so flush at once
        bar.setGeometry(window)
        bar.repaint()

    def _draw(self, look: Look) -> None:
        scene, canvas = self._scene, self._canvas
        if scene is None or canvas is None:
            return
        bar = self._bar
        self._look = look
        width, height = round(look.width), round(look.height)
        rect = self._screen_rect(width, height)
        bar.bar_frame.setGeometry(rect.x() - scene.window.x(), rect.y() - scene.window.y(), width, height)
        canvas.setGeometry(0, 0, width, height)
        canvas.look = look
        canvas.update()
        self._fade_strip(look.pills)

    def _fade_strip(self, opacity: float) -> None:
        if self._strip_canvas is not None:
            self._strip_canvas.opacity = opacity
            self._strip_canvas.update()

    def _land(self) -> None:
        """Put the window at its final rect while the canvas still paints, so the swap to real widgets moves nothing."""
        scene, canvas, bar = self._scene, self._canvas, self._bar
        if self._landed or scene is None or canvas is None:
            return
        self._timer.stop()
        look = self._to
        width, height = round(look.width), round(look.height)
        self._look = look
        bar.bar_frame.setGeometry(0, 0, width, height)
        canvas.setGeometry(0, 0, width, height)
        canvas.look = look
        if self._strip_canvas is not None:
            self._strip_canvas.hide()
            self._strip_canvas.deleteLater()
            self._strip_canvas = None
        bar.setGeometry(self._screen_rect(width, height))
        bar.repaint()
        if self.expanding and bar._below_strip is not None:
            bar._below_strip.place(scene.full_rect, scene.full_rect.center().x())
            bar._below_strip.show()
        self._landed = True

    def _settle_down(self) -> None:
        """Hand the bar back to its real widgets, laid out at the final geometry."""
        bar = self._bar
        self._landing.stop()
        self._timer.stop()
        if self._canvas is not None:
            self._canvas.hide()
            self._canvas.deleteLater()
        if self._pending is not None:
            peeking, hidden = self._pending
            self._pending = None
            self.apply_now(peeking, hidden)
        for name in SECTIONS:
            section = bar.section_frame(name)
            if section is not None:
                section.show()
        if self._strip_canvas is not None:
            self._strip_canvas.hide()
            self._strip_canvas.deleteLater()
            self._strip_canvas = None
        self._settle_layout()
        self._canvas = None
        self._scene = None
        self._landed = False
        self._busy = False
        bar.position_bar()
        for _ in range(3):
            self._settle_layout()
            if bar.resting_geometry() == (bar.x(), bar.y(), bar.width(), bar.height()):
                break
            bar.position_bar()
        bar.repaint()
        self._note_rest()
