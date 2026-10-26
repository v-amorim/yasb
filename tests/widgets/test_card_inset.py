# pyright: reportPrivateUsage=false
"""Every card keeps its content 12 px inside its border, and every surface keeps its text 10 px inside its edge.

The cards are built with the user's real styles.css through CSSProcessor and measured after layout. Offscreen
fonts are degenerate, so these tests measure widget boxes and margins, never glyph ink.
"""

from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from PyQt6.QtCore import QPoint, QRect
from PyQt6.QtGui import QImage, QRegion
from PyQt6.QtWidgets import (
    QAbstractButton,
    QAbstractSlider,
    QApplication,
    QCalendarWidget,
    QLabel,
    QLayout,
    QPushButton,
    QWidget,
)

from core.ui.components.fill_slider import FillSlider
from core.utils import floating_popup
from core.utils.css_processor import CSSProcessor
from core.validation.widgets.yasb.brightness import BrightnessConfig
from core.validation.widgets.yasb.clock import ClockConfig
from core.validation.widgets.yasb.control_center import ControlCenterConfig
from core.validation.widgets.yasb.systray import SystrayPopupConfig
from core.validation.widgets.yasb.volume import VolumeConfig
from core.validation.widgets.yasb.weather import WeatherWidgetConfig
from core.widgets.services.systray.systray_popup import SystrayPopup
from core.widgets.services.weather.hour_chart import HourChart
from core.widgets.yasb import brightness, volume, weather
from core.widgets.yasb.brightness import BrightnessWidget
from core.widgets.yasb.clock import ClockWidget
from core.widgets.yasb.control_center import ControlCenterWidget
from core.widgets.yasb.volume import VolumeWidget
from core.widgets.yasb.weather import WeatherWidget
from tests.widgets.test_brightness_menu import _FakeService as _FakeBrightness
from tests.widgets.test_systray_popup import _tile
from tests.widgets.test_volume_menu import _FakeService as _FakeVolume
from tests.widgets.test_weather_card import API_DATA, _FakeFetcher, _FakeIcons, _hourly_api_data

STYLES = Path.home() / ".config" / "yasb" / "styles.css"
CARD_INSET = 12
SURFACE_INSET = 10
TOLERANCE = 0.5

PRESETS = [
    {"name": "Night coding", "icon": "N", "brightness": 15, "contrast": 40},
    {"name": "Reading", "icon": "R", "brightness": 40},
    {"name": "Movie", "icon": "M", "brightness": 25},
    {"name": "Sunny day", "icon": "S", "brightness": 90},
]

type Card = tuple[QWidget, QWidget | None]


@pytest.fixture(scope="module")
def sheet() -> str:
    if not STYLES.is_file():
        pytest.skip("no styles.css in the user's config")
    return CSSProcessor(str(STYLES)).process()


@pytest.fixture
def host(qapp: QApplication, sheet: str) -> Iterator[QWidget]:
    window = QWidget()
    window.bar_frame = window  # type: ignore[attr-defined]
    window.setStyleSheet(sheet)
    yield window
    window.deleteLater()


def _settle(card: QWidget) -> None:
    card.show()
    for _ in range(3):
        QApplication.processEvents()
    card.adjustSize()
    QApplication.processEvents()


def _own_pixels(widget: QWidget) -> tuple[QRect, float] | None:
    """The box the widget itself paints, children left out, and how much of that box it fills."""
    width, height = widget.width(), widget.height()
    if width < 1 or height < 1:
        return None
    image = QImage(widget.size(), QImage.Format.Format_ARGB32)
    image.fill(0)
    widget.render(image, QPoint(), QRegion(), QWidget.RenderFlag(0))
    bits = image.constBits()
    assert bits is not None
    alpha = bits.asstring(image.sizeInBytes())[3::4]
    rows = [y for y in range(height) if any(alpha[y * width : (y + 1) * width])]
    if not rows:
        return None
    cols = [x for x in range(width) if any(alpha[x::width])]
    box = QRect(cols[0], rows[0], cols[-1] - cols[0] + 1, rows[-1] - rows[0] + 1)
    inked = len(alpha) - alpha.count(0)
    return box, inked / (box.width() * box.height())


def _box(widget: QWidget) -> QRect | None:
    """The widget's content box in its own coordinates: a label's frame, or what a surface or line paints.

    A stylesheet margin sits inside a widget's geometry, so a filled widget is measured by its fill.
    """
    full = QRect(0, 0, widget.width(), widget.height())
    if isinstance(widget, QLabel):
        return full if widget.text() or widget.pixmap() is not None else None
    pixels = _own_pixels(widget)
    framed = isinstance(widget, QAbstractButton | QAbstractSlider | QCalendarWidget | HourChart)
    if pixels is None:
        return full if framed else None
    box, coverage = pixels
    if coverage >= 0.6 or min(box.width(), box.height()) <= 2:
        return box
    return full if framed else None


def _layout_widgets(layout: QLayout | None, skip: set[QWidget]) -> Iterator[QWidget]:
    """The widgets a layout places, looking through nested layouts and through the card's own frame."""
    if layout is None:
        return
    for index in range(layout.count()):
        item = layout.itemAt(index)
        if item is None:
            continue
        widget = item.widget()
        if widget is None:
            yield from _layout_widgets(item.layout(), skip)
        elif widget in skip:
            yield from _layout_widgets(widget.layout(), skip)
        else:
            yield widget


def _content_boxes(card: QWidget, skip: set[QWidget]) -> list[tuple[QRect, QWidget]]:
    """Every label, button, slider and painted surface, plus each widget the card's layouts place as a block."""
    boxes: list[tuple[QRect, QWidget]] = []
    blocks = set(_layout_widgets(card.layout(), skip))
    for widget in card.findChildren(QWidget):
        if widget in skip or widget.isWindow() or not widget.isVisibleTo(card):
            continue
        box = QRect(0, 0, widget.width(), widget.height()) if widget in blocks else _box(widget)
        if box is not None:
            boxes.append((box.translated(widget.mapTo(card, QPoint(0, 0))), widget))
    return boxes


def _insets(card: QWidget, skip: set[QWidget] | None = None) -> dict[str, tuple[float, str]]:
    """Per side, the pixels from the inside of the card's border to its nearest content box, and that box's class."""
    boxes = _content_boxes(card, skip or set())
    border = floating_popup.BORDER
    sides: dict[str, Callable[[tuple[QRect, QWidget]], int]] = {
        "left": lambda item: item[0].left() - border,
        "top": lambda item: item[0].top() - border,
        "right": lambda item: card.width() - item[0].left() - item[0].width() - border,
        "bottom": lambda item: card.height() - item[0].top() - item[0].height() - border,
    }
    result: dict[str, tuple[float, str]] = {}
    for side, inset in sides.items():
        nearest = min(boxes, key=inset)
        result[side] = (inset(nearest), str(nearest[1].property("class") or type(nearest[1]).__name__))
    return result


def _assert_card_inset(card: QWidget, skip: set[QWidget] | None = None) -> None:
    insets = _insets(card, skip)
    assert all(abs(inset - CARD_INSET) <= TOLERANCE for inset, _ in insets.values()), insets


def _text_edges(surface: QWidget) -> tuple[int, int]:
    """Pixels from the surface's left and right edges to its outermost label."""
    labels = [
        label
        for label in surface.findChildren(QLabel)
        if label.isVisibleTo(surface) and (label.text() or label.pixmap() is not None)
    ]
    assert labels, "a surface with no text or icon"
    pixels = _own_pixels(surface)
    fill = pixels[0] if pixels and pixels[1] >= 0.6 else QRect(0, 0, surface.width(), surface.height())
    left = min(label.mapTo(surface, QPoint(0, 0)).x() for label in labels) - fill.left()
    right = fill.left() + fill.width() - max(label.mapTo(surface, QPoint(0, 0)).x() + label.width() for label in labels)
    return left, right


def _assert_surface_inset(surface: QWidget, right_edge: bool = True) -> None:
    """The text or icon sits 10 px from the surface's left edge, and from its right edge when content reaches it."""
    left, right = _text_edges(surface)
    assert abs(left - SURFACE_INSET) <= TOLERANCE, (left, right)
    assert not right_edge or abs(right - SURFACE_INSET) <= TOLERANCE, (left, right)


def _with_class(root: QWidget, name: str, kind: type[QWidget] = QWidget) -> list[Any]:
    return [w for w in root.findChildren(kind) if name in str(w.property("class")).split() and w.isVisibleTo(root)]


@pytest.fixture
def calendar(host: QWidget) -> Iterator[Card]:
    clock = ClockWidget(ClockConfig.model_validate({"calendar": {"extended": False, "anchor": "bar"}}))
    clock.setParent(host)
    clock.show_calendar()
    card = clock._yasb_calendar
    _settle(card)
    yield card, card._popup_content
    card.close()
    clock.deleteLater()


@pytest.fixture
def make_weather(host: QWidget, monkeypatch: pytest.MonkeyPatch) -> Iterator[Callable[[str], Card]]:
    monkeypatch.setattr(weather.WeatherDataFetcher, "get_instance", lambda *args: _FakeFetcher())
    monkeypatch.setattr(weather.IconFetcher, "get_instance", lambda *args: _FakeIcons())
    widgets: list[WeatherWidget] = []

    def make(layout: str) -> Card:
        config = WeatherWidgetConfig.model_validate(
            {
                "api_key": "key",
                "location": "here",
                "hide_decimal": True,
                "weather_card": {"layout": layout, "anchor": "bar"},
            }
        )
        widget = WeatherWidget(config)
        widget.setParent(host)
        widget.process_weather_data(_hourly_api_data() if layout == "chart" else API_DATA)
        widget._popup_card()
        widgets.append(widget)
        _settle(widget.dialog)
        return widget.dialog, widget.dialog._popup_content

    yield make
    for widget in widgets:
        widget.dialog.close()
        widget.deleteLater()


@pytest.fixture
def tray(host: QWidget) -> Iterator[Card]:
    button = QPushButton(host)
    popup = SystrayPopup(host, button, SystrayPopupConfig(anchor="bar"), 4)
    for name in ("Docker", "EarTrumpet", "Steam", "Discord", "Dropbox", "OneDrive"):
        popup.add_icon(_tile(name))
    popup.open("")
    _settle(popup)
    yield popup, popup.grid_widget
    popup.hide()


@pytest.fixture
def brightness_card(host: QWidget, monkeypatch: pytest.MonkeyPatch) -> Iterator[BrightnessWidget]:
    service = _FakeBrightness()
    monkeypatch.setattr(brightness.BrightnessService, "instance", lambda *args: service)
    monkeypatch.setattr(brightness, "get_widget_monitor_hwnd", lambda widget: 1)
    menu = {"slider_style": "fill", "presets": PRESETS, "anchor": "bar"}
    widget = BrightnessWidget(BrightnessConfig.model_validate({"tooltip": False, "brightness_menu": menu}))
    widget.setParent(host)
    widget._show_brightness_menu()
    _settle(widget.dialog)
    yield widget
    widget.dialog.close()
    widget.deleteLater()


@pytest.fixture
def volume_card(host: QWidget, monkeypatch: pytest.MonkeyPatch) -> Iterator[VolumeWidget]:
    monkeypatch.setattr(volume, "AudioOutputService", _FakeVolume())
    menu = {
        "show_apps": True,
        "show_app_icons": False,
        "show_system_sounds": True,
        "slider_style": "fill",
        "anchor": "bar",
    }
    widget = VolumeWidget(VolumeConfig.model_validate({"tooltip": False, "slider_beep": False, "audio_menu": menu}))
    widget.setParent(host)
    widget.show_volume_menu()
    _settle(widget.dialog)
    yield widget
    QApplication.instance().removeEventFilter(widget.dialog)  # type: ignore[union-attr]
    widget.dialog.close()
    widget.deleteLater()


@pytest.fixture
def control_center(host: QWidget, request: pytest.FixtureRequest) -> Iterator[ControlCenterWidget]:
    folders = [{"title": "Home", "path": "~", "icon": "H"}, {"title": "Docs", "path": "~", "icon": "D"}]
    actions = [
        {"id": "toggle_dnd", "label": "Do not disturb", "icon": "D"},
        {"id": "toggle_theme", "label": "Theme", "icon": "T"},
    ]
    config = ControlCenterConfig.model_validate(
        {
            "popup": {"blur": False, "anchor": "bar"},
            "sections": {
                "system_controls": {"power_style": "list", "settings_style": "list"},
                "folders": {"show": True, "items": folders},
                "sliders": {"show": False},
                "power": {"show": False},
                "media": {"show": False},
                "quick_actions": {"actions": actions},
            },
        }
    )
    widget = ControlCenterWidget(config)
    widget.setParent(host)
    widget._show_menu()
    if getattr(request, "param", "settled") == "settled":
        _settle(widget.dialog)
    else:
        for _ in range(3):
            QApplication.processEvents()
    yield widget
    widget.dialog.close()
    widget.deleteLater()


def test_card_inset_calendar(calendar: Card):
    card, content = calendar
    _assert_card_inset(card, {content} if content else set())


def test_card_inset_weather_rows(make_weather: Callable[[str], Card]):
    card, content = make_weather("rows")
    _assert_card_inset(card, {content} if content else set())


def test_card_inset_weather_chart(make_weather: Callable[[str], Card]):
    card, content = make_weather("chart")
    _assert_card_inset(card, {content} if content else set())


def test_card_inset_tray(tray: Card):
    card, content = tray
    _assert_card_inset(card, {content} if content else set())


def test_card_inset_brightness(brightness_card: BrightnessWidget):
    dialog = brightness_card.dialog
    _assert_card_inset(dialog, {dialog._popup_content})


def test_card_inset_volume(volume_card: VolumeWidget):
    dialog = volume_card.dialog
    _assert_card_inset(dialog, {dialog._popup_content})


def test_card_inset_control_center(control_center: ControlCenterWidget):
    dialog = control_center.dialog
    _assert_card_inset(dialog, {dialog._popup_content})


# The live bar opens a card with setPosition then show, and Qt's own sizing in show never reaches the adjustSize override.
@pytest.mark.parametrize("control_center", ["as opened live"], indirect=True)
def test_card_inset_control_center_as_opened_live(control_center: ControlCenterWidget):
    dialog = control_center.dialog
    _assert_card_inset(dialog, {dialog._popup_content})


def test_surface_inset_brightness_fill_slider(brightness_card: BrightnessWidget):
    sliders = [s for s in brightness_card.dialog.findChildren(FillSlider) if s.isVisible()]
    assert len(sliders) == 2
    for slider in sliders:
        _assert_surface_inset(slider)


def test_surface_inset_brightness_preset_tile(brightness_card: BrightnessWidget):
    tiles = _with_class(brightness_card.dialog, "preset", QPushButton)
    assert len(tiles) == len(PRESETS)
    for tile in tiles:
        _assert_surface_inset(tile)


def test_surface_inset_volume_fill_row(volume_card: VolumeWidget):
    sliders = [s for s in volume_card.dialog.findChildren(FillSlider) if s.isVisible()]
    assert len(sliders) >= 3
    for slider in sliders:
        _assert_surface_inset(slider)


def test_surface_inset_tray_tile(tray: Card):
    tiles = [b for b in tray[0].findChildren(QPushButton) if b.isVisible() and b.findChildren(QLabel)]
    assert len(tiles) == 6
    for tile in tiles:
        _assert_surface_inset(tile, right_edge=False)


def _system_controls(control_center: ControlCenterWidget) -> Any:
    return control_center._section_widgets["system_controls"]


def test_surface_inset_control_center_folder_rows(control_center: ControlCenterWidget):
    rows = _with_class(control_center.dialog, "folder")
    assert len(rows) == 2
    for row in rows:
        _assert_surface_inset(row, right_edge=False)


def test_surface_inset_control_center_power_tiles(control_center: ControlCenterWidget):
    _system_controls(control_center)._set_power_list_open(True)
    _settle(control_center.dialog)
    tiles = _with_class(control_center.dialog, "power-item")
    assert len(tiles) == 5
    for tile in tiles:
        _assert_surface_inset(tile, right_edge=False)


def test_surface_inset_control_center_settings_rows(control_center: ControlCenterWidget):
    _system_controls(control_center)._set_settings_list_open(True)
    _settle(control_center.dialog)
    rows = _with_class(control_center.dialog, "settings-item")
    assert rows
    for row in rows:
        _assert_surface_inset(row, right_edge=False)
