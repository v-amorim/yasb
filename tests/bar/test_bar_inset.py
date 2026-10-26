# pyright: reportPrivateUsage=false
"""The primary bar keeps its clock row and its pill row 12 px inside the bar's inner edge.

The bar is built with the user's real styles.css and the primary bar's real dimensions and layout from config.yaml,
with the real clock widgets and stand-in pills. Offscreen fonts are degenerate, so these tests measure widget boxes
and painted fills, never glyph ink.
"""

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import yaml
from PyQt6.QtCore import QEventLoop, QPoint, QRect, Qt, QTimer
from PyQt6.QtGui import QImage, QRegion
from PyQt6.QtWidgets import QApplication, QFrame, QHBoxLayout, QLabel, QWidget

from core.bar import Bar
from core.utils.css_processor import CSSProcessor
from core.validation.widgets.yasb.clock import ClockConfig
from core.widgets.base import BaseWidget
from core.widgets.yasb.clock import ClockWidget
from tests.bar.test_bar import MakeBar
from tests.widgets.test_card_inset import _own_pixels

CONFIG_DIR = Path.home() / ".config" / "yasb"
BAR_INSET = 12
CLOCK_TO_PILL_GAP = 4
TOLERANCE = 0.5
BORDER = 1


@pytest.fixture(scope="module")
def sheet() -> str:
    if not (CONFIG_DIR / "styles.css").is_file():
        pytest.skip("no styles.css in the user's config")
    return CSSProcessor(str(CONFIG_DIR / "styles.css")).process()


@pytest.fixture(scope="module")
def primary() -> dict[str, Any]:
    with open(CONFIG_DIR / "config.yaml", encoding="utf-8") as file:
        return yaml.safe_load(file)["bars"]["primary-bar"]


def _wait(ms: int) -> None:
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def _container(widget: BaseWidget, class_name: str) -> QHBoxLayout:
    """The one frame inside a bar item's own frame, as the real widgets build it; returns its layout."""
    container = QFrame()
    container.setProperty("class", class_name)
    layout = QHBoxLayout(container)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(0)
    widget.widget_layout.addWidget(container)
    return layout


def _slot(name: str) -> BaseWidget:
    """A pill slot: the widget frame and widget-container every bar item has, one icon in it."""
    slot = BaseWidget(class_name=name)
    icon = QLabel("X")
    icon.setProperty("class", "icon")
    _container(slot, "widget-container").addWidget(icon)
    return slot


def _pill(name: str, slots: tuple[str, str]) -> BaseWidget:
    """What the grouper builds: the widget frame, one container, two slots."""
    pill = BaseWidget(class_name=f"pill {name}")
    layout = _container(pill, "container")
    for slot in slots:
        layout.addWidget(_slot(slot))
    return pill


@pytest.fixture
def bar(make_bar: MakeBar, sheet: str, primary: dict[str, Any], qapp: QApplication) -> Iterator[Bar]:
    clock = {"label": "{%H:%M}", "label_full": "{%H:%M:%S}"}
    built = make_bar(
        widgets={
            "left": [_pill("pill-levels", ("brightness-widget", "volume-widget"))],
            "center": [
                ClockWidget(ClockConfig.model_validate(clock)),
                ClockWidget(ClockConfig.model_validate({**clock, "class_name": "date-pill"})),
            ],
            "right": [
                _pill("pill-status", ("weather-widget", "notification-widget")),
                _pill("pill-tray", ("systray-widget", "control-center-widget")),
            ],
        },
        class_name=primary["class_name"],
        dimensions=primary["dimensions"],
        layouts=primary["layouts"],
        animation={"enabled": False},
    )
    built.setStyleSheet(sheet)
    _wait(50)
    yield built


def _in_bar(bar: Bar, widget: QWidget, box: QRect) -> QRect:
    return box.translated(widget.mapTo(bar.bar_frame, QPoint(0, 0)))


def _clock_boxes(bar: Bar) -> list[QRect]:
    center = bar.section_frame("center")
    assert center is not None
    containers = [w for w in center.findChildren(QFrame) if w.property("class") == "widget-container" and w.isVisible()]
    assert len(containers) == 2
    return [_in_bar(bar, c, QRect(0, 0, c.width(), c.height())) for c in containers]


def _pill_boxes(bar: Bar) -> list[QRect]:
    bottom = bar._bottom_row
    assert bottom is not None
    boxes: list[QRect] = []
    for container in bottom.findChildren(QFrame):
        if container.property("class") == "container" and container.isVisible():
            painted = _own_pixels(container)
            assert painted is not None
            boxes.append(_in_bar(bar, container, painted[0]))
    assert len(boxes) == 3
    return boxes


def _insets(bar: Bar) -> dict[str, float]:
    frame = bar.bar_frame
    clock, pills = _clock_boxes(bar), _pill_boxes(bar)
    everything = clock + pills
    return {
        "top": min(box.top() for box in clock),
        "bottom": frame.height() - BORDER - max(box.bottom() + 1 for box in pills),
        "left": min(box.left() for box in everything) - BORDER,
        "right": frame.width() - BORDER - max(box.right() + 1 for box in everything),
    }


@pytest.mark.parametrize("side", ["top", "bottom", "left", "right"])
def test_bar_inset_rows_sit_12px_from_the_inner_edge(bar: Bar, side: str):
    insets = _insets(bar)
    assert abs(insets[side] - BAR_INSET) <= TOLERANCE, insets


def test_bar_inset_height_is_the_configured_height(bar: Bar, primary: dict[str, Any]):
    assert bar.bar_frame.height() == primary["dimensions"]["height"]


def test_gap_step_bar_clock_row_to_pill_row(bar: Bar):
    clock, pills = _clock_boxes(bar), _pill_boxes(bar)
    gap = min(box.top() for box in pills) - max(box.bottom() + 1 for box in clock)
    assert abs(gap - CLOCK_TO_PILL_GAP) <= TOLERANCE, gap


PILL_RADIUS = 8
BAR_RADIUS = 20


def _corner_alpha(widget: QWidget, flags: QWidget.RenderFlag) -> tuple[bytes, int, int]:
    image = QImage(widget.size(), QImage.Format.Format_ARGB32)
    image.fill(0)
    widget.render(image, QPoint(), QRegion(), flags)
    bits = image.constBits()
    assert bits is not None
    return bits.asstring(image.sizeInBytes())[3::4], image.width(), image.height()


def _corner_windows(alpha: bytes, width: int, height: int, size: int, bottom_only: bool) -> list[bytes]:
    """The corner squares of the painted box, which a margin can inset from the widget's own edges."""
    rows = [y for y in range(height) if any(alpha[y * width : (y + 1) * width])]
    columns = [x for x in range(width) if any(alpha[x::width][:height])]
    top, bottom, left, right = rows[0], rows[-1] + 1, columns[0], columns[-1] + 1
    origins = [(left, bottom - size), (right - size, bottom - size)]
    if not bottom_only:
        origins += [(left, top), (right - size, top)]
    return [bytes(alpha[(y + oy) * width + x + ox] for y in range(size) for x in range(size)) for ox, oy in origins]


def _differs_from_radius(widget: QWidget, radius: int, size: int, bottom_only: bool = False) -> bool:
    """Whether the widget's painted corners differ from a plain frame of the same size with this radius."""
    reference = QFrame()
    rule = f"border-radius: {radius}px;"
    if bottom_only:
        rule = f"border-top: none; border-bottom-left-radius: {radius}px; border-bottom-right-radius: {radius}px;"
    border = "border: 1px solid rgba(155, 163, 196, 0.12);" if bottom_only else ""
    reference.setStyleSheet(f"QFrame {{ background-color: #FFFFFF; {border} {rule} }}")
    reference.resize(widget.size())
    ours = _corner_alpha(widget, QWidget.RenderFlag(0))
    theirs = _corner_alpha(reference, QWidget.RenderFlag(0))
    ours_windows = _corner_windows(*ours, size, bottom_only)
    theirs_windows = _corner_windows(*theirs, size, bottom_only)
    return any(
        abs(a - b) > 32
        for w1, w2 in zip(ours_windows, theirs_windows, strict=True)
        for a, b in zip(w1, w2, strict=True)
    )


def _assert_radius(widget: QWidget, radius: int, size: int, bottom_only: bool = False) -> None:
    assert widget.width() > 2 * size and widget.height() > size
    assert not _differs_from_radius(widget, radius, size, bottom_only)
    assert _differs_from_radius(widget, radius + 4, size, bottom_only)


def _marked_open(container: QWidget) -> None:
    """The popup-open look gives the slot a fill, so its corners can be read."""
    container.setProperty("class", "widget-container popup-open")
    style = container.style()
    assert style is not None
    style.unpolish(container)
    style.polish(container)
    container.update()


def test_pill_corner_pill_groups_are_8(bar: Bar):
    bottom = bar._bottom_row
    assert bottom is not None
    groups = [c for c in bottom.findChildren(QFrame) if c.property("class") == "container" and c.isVisible()]
    assert len(groups) == 3
    for group in groups:
        _assert_radius(group, PILL_RADIUS, PILL_RADIUS + 2)


def test_pill_corner_widget_slots_are_8(bar: Bar):
    bottom = bar._bottom_row
    assert bottom is not None
    slots = [c for c in bottom.findChildren(QFrame) if c.property("class") == "widget-container" and c.isVisible()]
    assert len(slots) == 6
    for slot in slots:
        _marked_open(slot)
        _assert_radius(slot, PILL_RADIUS, PILL_RADIUS + 2)


def test_pill_corner_date_pill_is_8(bar: Bar):
    center = bar.section_frame("center")
    assert center is not None
    pills = [
        c.findChild(QFrame, options=Qt.FindChildOption.FindChildrenRecursively)
        for c in center.findChildren(QFrame)
        if str(c.property("class")).endswith("date-pill") and c.isVisible()
    ]
    assert len(pills) == 1
    date = next(c for c in center.findChildren(QFrame) if c.property("class") == "widget-container" and _is_date(c))
    _assert_radius(date, PILL_RADIUS, PILL_RADIUS + 2)


def _is_date(container: QWidget) -> bool:
    parent = container.parentWidget()
    return parent is not None and "date-pill" in str(parent.property("class"))


def test_pill_corner_bar_bottom_corners_are_20(bar: Bar):
    _assert_radius(bar.bar_frame, BAR_RADIUS, BAR_RADIUS + 4, bottom_only=True)
