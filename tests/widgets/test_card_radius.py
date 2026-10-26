# pyright: reportPrivateUsage=false
"""Every bar-anchored card rounds its four corners with --radius-card (16 px), and its tiles with --radius-tile (4 px).

A card is rendered with the user's real styles.css and its corners are compared pixel by pixel with a plain frame
that has the same size and border and a 16 px radius, so the test reads the radius the card really paints.
"""

import re
from collections.abc import Callable
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QImage
from PyQt6.QtWidgets import QFrame, QWidget

from core.ui.components.fill_slider import FillSlider
from core.widgets.services.weather.hour_chart import HourTip
from core.widgets.yasb.brightness import BrightnessWidget
from core.widgets.yasb.control_center import ControlCenterWidget
from core.widgets.yasb.volume import VolumeWidget
from tests.widgets.test_card_inset import STYLES, Card

CARD_RADIUS = 16
TILE_RADIUS = 4
CORNER = 20


def _alpha(widget: QWidget) -> tuple[bytes, int, int]:
    image = widget.grab().toImage().convertToFormat(QImage.Format.Format_ARGB32)
    bits = image.constBits()
    assert bits is not None
    return bits.asstring(image.sizeInBytes())[3::4], image.width(), image.height()


def _corners(widget: QWidget) -> list[list[int]]:
    alpha, width, height = _alpha(widget)
    origins = [(0, 0), (width - CORNER, 0), (0, height - CORNER), (width - CORNER, height - CORNER)]
    return [[alpha[(y + oy) * width + x + ox] for y in range(CORNER) for x in range(CORNER)] for ox, oy in origins]


def _reference(card: QWidget, radius: int) -> QWidget:
    """A translucent window holding one styled frame, the way a card is built."""
    window = QWidget()
    window.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    frame = QFrame(window)
    frame.setStyleSheet(
        f"QFrame {{ background-color: #0D0E17; border: 2px solid #3A4060; border-radius: {radius}px; }}"
    )
    window.resize(card.size())
    frame.setGeometry(window.rect())
    return window


def _differing_pixels(card: QWidget, radius: int) -> int:
    reference = _reference(card, radius)
    return sum(
        abs(a - b) > 32 for ours, theirs in zip(_corners(card), _corners(reference)) for a, b in zip(ours, theirs)
    )


def _assert_card_radius(card: QWidget) -> None:
    assert card.width() > 2 * CORNER and card.height() > 2 * CORNER
    assert _differing_pixels(card, CARD_RADIUS) == 0
    assert _differing_pixels(card, 12) > 0


def test_card_radius_calendar(calendar: Card):
    _assert_card_radius(calendar[0])


def test_card_radius_weather_rows(make_weather: Callable[[str], Card]):
    _assert_card_radius(make_weather("rows")[0])


def test_card_radius_weather_chart(make_weather: Callable[[str], Card]):
    _assert_card_radius(make_weather("chart")[0])


def test_card_radius_tray(tray: Card):
    _assert_card_radius(tray[0])


def test_card_radius_brightness(brightness_card: BrightnessWidget):
    _assert_card_radius(brightness_card.dialog)


def test_card_radius_volume(volume_card: VolumeWidget):
    _assert_card_radius(volume_card.dialog)


def test_card_radius_control_center(control_center: ControlCenterWidget):
    _assert_card_radius(control_center.dialog)


def test_card_radius_tokens_in_the_stylesheet(sheet: str):
    assert not re.search(r"(border|qproperty)-radius: *(8|12)(px)?;", _card_scope(STYLES)), "a literal card radius"


def _card_scope(path: Path) -> str:
    prefixes = (
        ".calendar",
        ".weather-card",
        ".systray-popup",
        ".brightness-menu",
        ".audio-menu",
        ".control-center-menu",
    )
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    blocks = re.split(r"(?<=\})\n", text)
    return "\n".join(
        block
        for block in blocks
        if any(
            re.match(re.escape(p) + r"[ ,.:{]", line) for line in block.split("{", 1)[0].split("\n") for p in prefixes
        )
    )


def _repolish(widget: QWidget) -> None:
    style = widget.style()
    assert style is not None
    style.unpolish(widget)
    style.polish(widget)


def test_card_radius_painted_tiles_follow_the_tile_token(brightness_card: BrightnessWidget):
    sliders = [s for s in brightness_card.dialog.findChildren(FillSlider) if s.isVisible()]
    assert sliders
    for slider in sliders:
        slider._radius = 99
        _repolish(slider)
        assert slider._radius == TILE_RADIUS


def test_card_radius_hour_tip_follows_the_tile_token(host: QWidget):
    tip = HourTip(host, "R")
    tip._radius = 99
    _repolish(tip)
    assert tip._radius == TILE_RADIUS
