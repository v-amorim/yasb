# pyright: reportPrivateUsage=false

from collections.abc import Callable, Iterator
from typing import Any

import pytest
from pydantic import ValidationError
from PyQt6.QtCore import QObject, QPointF, Qt, pyqtSignal
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtWidgets import QApplication, QGridLayout, QLabel, QPushButton, QSlider, QWidget

from core.ui.components.fill_slider import FillSlider
from core.validation.widgets.yasb.brightness import BrightnessConfig
from core.widgets.yasb import brightness
from core.widgets.yasb.brightness import BrightnessWidget

type MakeWidget = Callable[..., BrightnessWidget]

MONITOR = 1


class _FakeService(QObject):
    brightness_changed = pyqtSignal(int, object)
    contrast_changed = pyqtSignal(int, object)

    def __init__(self) -> None:
        super().__init__()
        self.brightness = {MONITOR: 20}
        self.contrast = {MONITOR: 50}

    def get_monitors(self) -> list[tuple[int, str]]:
        return [(MONITOR, "U34G4C")]

    def get_monitor_subtitle(self, hmonitor: int, index: int = 0) -> str:
        return "Monitor 1"

    def get_brightness(self, hmonitor: int) -> int | None:
        return self.brightness.get(hmonitor)

    def get_contrast(self, hmonitor: int) -> int | None:
        return self.contrast.get(hmonitor)

    def supports_contrast(self, hmonitor: int) -> bool:
        return True

    def set_brightness(self, hmonitor: int, value: int) -> None:
        self.brightness[hmonitor] = value

    def set_contrast(self, hmonitor: int, value: int) -> None:
        self.contrast[hmonitor] = value

    def refresh_now(self) -> None:
        pass


@pytest.fixture
def service(monkeypatch: pytest.MonkeyPatch) -> _FakeService:
    fake = _FakeService()

    def instance(*args: object) -> _FakeService:
        return fake

    monkeypatch.setattr(brightness.BrightnessService, "instance", instance)
    monkeypatch.setattr(brightness, "get_widget_monitor_hwnd", _the_monitor)
    return fake


def _the_monitor(widget: QWidget) -> int:
    return MONITOR


@pytest.fixture
def make_widget(qapp: QApplication, service: _FakeService) -> Iterator[MakeWidget]:
    widgets: list[BrightnessWidget] = []

    def make(**menu: Any) -> BrightnessWidget:
        widget = BrightnessWidget(BrightnessConfig.model_validate({"tooltip": False, "brightness_menu": menu}))
        widgets.append(widget)
        return widget

    yield make
    for widget in widgets:
        if widget.dialog is not None:
            widget.dialog.close()
        widget.deleteLater()


def _press(slider: QSlider, x: float, event_type: QMouseEvent.Type = QMouseEvent.Type.MouseButtonPress) -> None:
    point = QPointF(x, slider.height() / 2)
    event = QMouseEvent(
        event_type,
        point,
        slider.mapToGlobal(point),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(slider, event)


def test_fill_slider_jumps_to_the_cursor_and_prints_its_value(qapp: QApplication):
    slider = FillSlider("", "Brightness")
    slider.resize(200, 30)
    released: list[bool] = []
    slider.sliderReleased.connect(lambda: released.append(True))

    _press(slider, 150)
    assert slider.value() == 75 and slider.isSliderDown()
    _press(slider, 50, QMouseEvent.Type.MouseMove)
    assert slider.value() == 25
    _press(slider, 50, QMouseEvent.Type.MouseButtonRelease)

    assert released == [True] and not slider.isSliderDown()
    assert slider._value.text() == "25%"
    assert not slider._icon.isVisible()


def test_fill_rows_print_levels_synced_from_the_monitor(make_widget: MakeWidget, service: _FakeService):
    widget = make_widget(slider_style="fill")
    widget._show_brightness_menu()
    service.brightness[MONITOR], service.contrast[MONITOR] = 15, 40

    widget._refresh_menu_sliders()

    bright, contrast = widget._sliders[f"brightness_{MONITOR}"], widget._sliders[f"contrast_{MONITOR}"]
    assert isinstance(bright, FillSlider) and isinstance(contrast, FillSlider)
    assert bright._value.text() == "15%" and contrast._value.text() == "40%"


def test_default_style_keeps_plain_sliders(make_widget: MakeWidget):
    widget = make_widget()
    widget._show_brightness_menu()

    sliders = list(widget._sliders.values())
    assert len(sliders) == 2
    assert not any(isinstance(slider, FillSlider) for slider in sliders)


def test_fill_style_draws_rows_with_their_names(make_widget: MakeWidget):
    widget = make_widget(slider_style="fill", brightness_label="Brilho")
    widget._show_brightness_menu()

    bright = widget._sliders[f"brightness_{MONITOR}"]
    assert isinstance(bright, FillSlider)
    assert bright._name.text() == "Brilho"
    assert bright.value() == 20
    assert isinstance(widget._sliders[f"contrast_{MONITOR}"], FillSlider)


def test_a_preset_sets_every_monitor_and_turns_active(make_widget: MakeWidget, service: _FakeService):
    presets = [
        {"name": "Night coding", "icon": "N", "brightness": 15, "contrast": 40},
        {"name": "Sunny day", "brightness": 90},
    ]
    widget = make_widget(slider_style="fill", presets=presets)
    widget._show_brightness_menu()
    night, sunny = (button for button, _ in widget._preset_buttons)
    assert isinstance(night, QPushButton)
    level_texts = [
        label.text()
        for button in (night, sunny)
        for label in button.findChildren(QLabel)
        if label.property("class") == "level"
    ]
    assert level_texts == ["15% / 40%", "90%"]

    night.click()
    assert service.brightness[MONITOR] == 15 and service.contrast[MONITOR] == 40
    assert widget._sliders[f"brightness_{MONITOR}"].value() == 15
    assert night.property("class") == "preset active" and sunny.property("class") == "preset"

    widget._sliders[f"brightness_{MONITOR}"].setValue(60)
    assert night.property("class") == "preset"


def test_preset_label_reads_percentages(make_widget: MakeWidget):
    presets = [{"name": "Night", "brightness": 15, "contrast": 40}, {"name": "Day", "brightness": 90}]
    widget = make_widget(presets=presets)
    widget._show_brightness_menu()

    levels = [
        label.text()
        for button, _ in widget._preset_buttons
        for label in button.findChildren(QLabel)
        if label.property("class") == "level"
    ]
    assert levels == ["15% / 40%", "90%"]


def test_preset_tile_fits_its_labels(make_widget: MakeWidget):
    presets = [{"name": "Night coding", "icon": "N", "brightness": 15, "contrast": 40}]
    widget = make_widget(presets=presets)
    widget._show_brightness_menu()
    QApplication.processEvents()

    (tile, _) = widget._preset_buttons[0]
    labels = tile.findChildren(QLabel)
    assert len(labels) == 3
    assert tile.minimumWidth() >= sum(label.sizeHint().width() for label in labels)
    assert tile.width() >= sum(label.sizeHint().width() for label in labels)


def test_optical_applied_brightness_presets(make_widget: MakeWidget, monkeypatch: pytest.MonkeyPatch):
    pairs: list[tuple[QLabel, QLabel]] = []
    real = brightness.center_icon_on_text
    monkeypatch.setattr(
        brightness, "center_icon_on_text", lambda icon, text: (pairs.append((icon, text)), real(icon, text))
    )
    presets = [{"name": "Night", "icon": "N", "brightness": 15}, {"name": "Plain", "brightness": 90}]
    widget = make_widget(presets=presets)
    widget._show_brightness_menu()

    assert [(icon.text(), text.text()) for icon, text in pairs] == [("N", "Night")]


def test_presets_lay_out_in_the_configured_columns(make_widget: MakeWidget):
    presets = [{"name": str(k), "brightness": k * 10} for k in range(5)]
    widget = make_widget(presets=presets, presets_columns=3)
    widget._show_brightness_menu()

    grid = widget._preset_buttons[0][0].parentWidget()
    assert grid is not None
    layout = grid.layout()
    assert isinstance(layout, QGridLayout)
    rows = {layout.getItemPosition(layout.indexOf(button))[0] for button, _ in widget._preset_buttons}
    assert rows == {0, 1}


@pytest.mark.parametrize(
    "preset",
    [{"name": "Too bright", "brightness": 120}, {"brightness": 50}, {"name": "x", "brightness": 50, "contrast": -1}],
)
def test_a_bad_preset_is_rejected(preset: dict[str, Any]):
    with pytest.raises(ValidationError):
        BrightnessConfig.model_validate({"brightness_menu": {"presets": [preset]}})
