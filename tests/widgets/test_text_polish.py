# pyright: reportPrivateUsage=false

from collections.abc import Callable, Iterator
from types import SimpleNamespace
from typing import Any

import pytest
from PyQt6.QtCore import QObject, QPoint, Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QLabel, QTableView, QWidget

from core.ui.components import fill_slider
from core.ui.components.fill_slider import FillSlider
from core.utils import optical
from core.utils.tabular import set_tabular
from core.validation.widgets.yasb.clock import ClockConfig
from core.validation.widgets.yasb.control_center import SlidersSectionConfig, SystemControlsConfig
from core.validation.widgets.yasb.volume import VolumeConfig
from core.validation.widgets.yasb.weather import WeatherWidgetConfig
from core.widgets.services.control_center.sections.sliders import SlidersSectionWidget
from core.widgets.services.control_center.sections.system_controls import SystemControlsSectionWidget
from core.widgets.services.weather.hour_chart import ChartHour, HourTip
from core.widgets.yasb import volume, weather
from core.widgets.yasb.clock import ClockWidget, CustomCalendar
from core.widgets.yasb.volume import VolumeWidget

TNUM = QFont.Tag("tnum")
LONG_DEVICE = "Speakers (HECATE G4 TE GAMING HEADSET WITH A VERY LONG MODEL NAME)"
LONG_APP = "Some Application With A Name That Cannot Possibly Fit In The Row"


def _tabular(widget: QWidget) -> bool:
    return widget.font().featureValue(TNUM) == 1


def test_set_tabular_turns_tnum_on_for_every_widget(qapp: QApplication):
    first, second = QLabel("1"), QLabel("8")
    assert not _tabular(first)

    set_tabular(first, second)

    assert _tabular(first) and _tabular(second)


def test_set_tabular_keeps_the_rest_of_the_font(qapp: QApplication):
    label = QLabel("1")
    font = label.font()
    font.setPointSize(17)
    label.setFont(font)

    set_tabular(label)

    assert label.font().pointSize() == 17


def test_tabular_clock_timer_label(qapp: QApplication):
    widget = ClockWidget(ClockConfig.model_validate({"tooltip": False}))
    try:
        assert _tabular(widget._timer_label)
    finally:
        widget._shared_state.unregister_widget(widget)
        widget.deleteLater()


def test_tabular_fill_slider_value(qapp: QApplication):
    assert _tabular(FillSlider("", "Brightness")._value)


def test_tabular_calendar_table(qapp: QApplication):
    calendar = CustomCalendar()
    table = calendar.findChild(QTableView)

    assert table is not None and _tabular(table)


def test_tabular_hour_tip_labels(qapp: QApplication):
    tip = HourTip(None, "D")
    tip.show_hour(ChartHour("11h", 16, "16°", "15°", 44), 0, 400, 100, 100)

    labels = tip.findChildren(QLabel)
    assert len(labels) == 5 and all(_tabular(label) for label in labels)
    tip.close()


def test_tabular_control_center_slider_values(qapp: QApplication):
    host = QWidget()
    section = SlidersSectionWidget(host, SlidersSectionConfig(), lambda: None, None, None, None, None)

    assert _tabular(section._volume_value_label)
    host.deleteLater()


class _FakeFetcher(QObject):
    finished = pyqtSignal(dict)

    def __init__(self) -> None:
        super().__init__()
        self.started = True

    def make_request(self) -> None:
        pass


class _FakeIcons(QObject):
    finished = pyqtSignal()

    def fetch_icons(self, icon_urls: list[str]) -> None:
        pass

    def get_icon(self, url: str) -> bytes:
        return b""

    def set_icon(self, url: str, data: bytes) -> None:
        pass


def _day(date: str, low: float, high: float) -> dict[str, Any]:
    return {
        "date": date,
        "day": {
            "mintemp_c": low,
            "maxtemp_c": high,
            "daily_chance_of_rain": 40,
            "condition": {"text": "", "icon": "//cdn/icon.png", "code": 1003},
        },
        "hour": [
            {"time": f"{date} {h:02d}:00", "temp_c": 10 + h / 2, "feelslike_c": 9.8 + h / 2, "chance_of_rain": h * 4}
            for h in range(24)
        ],
    }


WEATHER_DATA: dict[str, Any] = {
    "location": {"name": "Here", "localtime": "2026-10-23 10:00"},
    "current": {
        "temp_c": 18.2,
        "feelslike_c": 20.8,
        "humidity": 94,
        "is_day": 1,
        "condition": {"text": "Light rain", "icon": "//cdn/icon.png", "code": 1183},
    },
    "forecast": {
        "forecastday": [_day("2026-10-23", 18.1, 23.9), _day("2026-10-24", 17.0, 25.2), _day("2026-10-25", 18.4, 22.0)]
    },
}


@pytest.fixture
def weather_widget(qapp: QApplication, monkeypatch: pytest.MonkeyPatch) -> Iterator[Callable[[str], Any]]:
    monkeypatch.setattr(weather.WeatherDataFetcher, "get_instance", lambda *args: _FakeFetcher())
    monkeypatch.setattr(weather.IconFetcher, "get_instance", lambda *args: _FakeIcons())
    widgets: list[Any] = []

    def make(layout: str) -> Any:
        config = WeatherWidgetConfig.model_validate(
            {"api_key": "key", "location": "here", "hide_decimal": True, "weather_card": {"layout": layout}}
        )
        widget = weather.WeatherWidget(config)
        widget.process_weather_data(WEATHER_DATA)
        widget._popup_card()
        widgets.append(widget)
        return widget

    yield make
    for widget in widgets:
        widget.dialog.close()
        widget.deleteLater()


def _labels(parent: QObject, class_name: str) -> list[QLabel]:
    return [label for label in parent.findChildren(QLabel) if class_name in str(label.property("class")).split()]


def test_tabular_weather_tile_labels(weather_widget: Callable[[str], Any]):
    widget = weather_widget("chart")

    for class_name in ("tile-low", "tile-high", "tile-rain"):
        labels = _labels(widget.dialog, class_name)
        assert labels and all(_tabular(label) for label in labels), class_name


def test_tabular_more_weather_rows_card(weather_widget: Callable[[str], Any]):
    widget = weather_widget("rows")

    for class_name in ("now-temp", "fact-value", "day-low", "day-high", "day-rain"):
        labels = _labels(widget.dialog, class_name)
        assert labels and all(_tabular(label) for label in labels), class_name


def test_tabular_more_weather_chart_card(weather_widget: Callable[[str], Any]):
    widget = weather_widget("chart")

    for class_name in ("chart-temp", "chart-fact-value"):
        labels = _labels(widget.dialog, class_name)
        assert labels and all(_tabular(label) for label in labels), class_name


def test_tabular_more_audio_master_value(qapp: QApplication, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(volume, "AudioOutputService", _FakeService())
    config = {"tooltip": False, "slider_beep": False, "audio_menu": {"slider_style": "fill"}}
    widget = VolumeWidget(VolumeConfig.model_validate(config))
    widget.show_volume_menu()
    assert widget.dialog is not None
    try:
        assert isinstance(widget.volume_slider, FillSlider) and _tabular(widget.volume_slider._value)
    finally:
        widget.dialog.close()
        widget.deleteLater()


def _spy(monkeypatch: pytest.MonkeyPatch, module: Any) -> list[tuple[QLabel, QLabel]]:
    pairs: list[tuple[QLabel, QLabel]] = []
    real = module.center_icon_on_text

    def record(icon: QLabel, text: QLabel) -> None:
        pairs.append((icon, text))
        real(icon, text)

    monkeypatch.setattr(module, "center_icon_on_text", record)
    return pairs


def test_optical_applied_weather_rows_card(weather_widget: Callable[[str], Any], monkeypatch: pytest.MonkeyPatch):
    pairs = _spy(monkeypatch, weather)
    widget = weather_widget("rows")

    classes = {(str(i.property("class")), str(t.property("class"))) for i, t in pairs}
    assert classes == {("day-icon", "day-name"), ("day-drop", "day-rain")}
    assert len(pairs) == 2 * len(_labels(widget.dialog, "day-name"))
    assert all(icon.findChild(optical._OpticalCentering) is not None for icon, _ in pairs)


def test_optical_applied_weather_chart_card(weather_widget: Callable[[str], Any], monkeypatch: pytest.MonkeyPatch):
    pairs = _spy(monkeypatch, weather)
    widget = weather_widget("chart")

    assert {(str(i.property("class")), str(t.property("class"))) for i, t in pairs} == {("tile-drop", "tile-rain")}
    assert len(pairs) == len(_labels(widget.dialog, "tile-rain"))


def test_optical_applied_audio_device_rows(qapp: QApplication, monkeypatch: pytest.MonkeyPatch):
    pairs = _spy(monkeypatch, fill_slider)
    monkeypatch.setattr(volume, "AudioOutputService", _FakeService())
    config = {"tooltip": False, "slider_beep": False, "audio_menu": {"slider_style": "fill", "show_apps": True}}
    widget = VolumeWidget(VolumeConfig.model_validate(config))
    widget.show_volume_menu()
    assert widget.dialog is not None
    try:
        rows = widget.dialog.findChildren(FillSlider)
        assert len(rows) == 2
        assert pairs == [(row._icon, row._name) for row in rows]
    finally:
        widget.dialog.close()
        widget.deleteLater()


def test_main_temp_unit_shows_on_the_card_and_not_on_the_small_tiles(weather_widget: Callable[[str], Any]):
    chart = weather_widget("chart")
    assert [label.text() for label in _labels(chart.dialog, "chart-temp")] == ["18°C"]
    assert [label.text() for label in _labels(chart.dialog, "tile-low")] == ["18°", "17°", "18°"]

    rows = weather_widget("rows")
    assert [label.text() for label in _labels(rows.dialog, "now-temp")] == ["18°C"]
    assert [label.text() for label in _labels(rows.dialog, "fact-value")][0] == "21°"


@pytest.fixture
def host(qapp: QApplication) -> Iterator[QWidget]:
    widget = QWidget()
    yield widget
    widget.deleteLater()


def test_caps_spacing_is_eight_percent_of_the_polished_font_size(host: QWidget):
    section = SystemControlsSectionWidget(host, SystemControlsConfig(settings_style="list"), lambda: None)

    headers = _labels(section, "settings-group-label")
    assert headers and all(header.text() == header.text().upper() for header in headers)
    for header in headers:
        assert header.font().letterSpacingType() == QFont.SpacingType.AbsoluteSpacing
        assert header.font().letterSpacing() == pytest.approx(optical._pixel_size(header.font()) * 0.08, abs=0.02)


def test_caps_spacing_follows_the_font_when_the_stylesheet_changes_it(host: QWidget):
    section = SystemControlsSectionWidget(host, SystemControlsConfig(settings_style="list"), lambda: None)
    header = _labels(section, "settings-group-label")[0]

    for pixels in (10, 25):
        header.setStyleSheet(f"font-size: {pixels}px;")
        header.ensurePolished()
        assert header.font().pixelSize() == pixels
        assert header.font().letterSpacing() == pytest.approx(pixels * 0.08, abs=0.02)


def test_system_labels_use_sentence_case(host: QWidget):
    section = SystemControlsSectionWidget(host, SystemControlsConfig(settings_style="list"), lambda: None)

    texts = {label.text() for label in section.findChildren(QLabel)}
    assert "All settings" in texts and "All Settings" not in texts


class _FakeVolume:
    def GetMasterVolumeLevelScalar(self) -> float:
        return 0.3

    def SetMasterVolumeLevelScalar(self, level: float, context: object) -> None:
        pass

    def GetMasterVolume(self) -> float:
        return 0.3

    def GetMute(self) -> int:
        return 0

    def SetMute(self, muted: bool, context: object) -> None:
        pass


class _FakeService:
    def __call__(self) -> _FakeService:
        return self

    def register_widget(self, widget: object) -> None:
        pass

    def unregister_widget(self, widget: object) -> None:
        pass

    def get_volume_interface(self) -> _FakeVolume:
        return _FakeVolume()

    def get_all_devices(self) -> list[tuple[str, str | None]]:
        return [("headset", LONG_DEVICE)]

    def get_speakers(self) -> SimpleNamespace:
        return SimpleNamespace(id="headset")

    def get_active_audio_sessions(self, **callbacks: Any) -> list[dict[str, Any]]:
        return [{"name": "x.exe", "app_name": LONG_APP, "volume_interface": _FakeVolume(), "pid": 1}]


def test_full_name_reaches_the_label_uncut_and_the_tooltip_when_elided(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(volume, "AudioOutputService", _FakeService())
    menu = {"show_app_icons": False, "show_apps": True, "slider_style": "fill"}
    config = {"tooltip": False, "slider_beep": False, "audio_menu": menu}
    widget = VolumeWidget(VolumeConfig.model_validate(config))
    widget.show_volume_menu()
    assert widget.dialog is not None
    try:
        rows = widget.dialog.findChildren(FillSlider)
        assert len(rows) == 2
        for row, full in zip(rows, (LONG_DEVICE, LONG_APP), strict=True):
            row.resize(120, 30)
            row.grab()
            assert row._name.text() == full
            assert row.toolTip() == full
    finally:
        widget.dialog.close()
        widget.deleteLater()


def test_full_name_no_tooltip_when_the_name_fits(qapp: QApplication):
    row = FillSlider("", "Spotify")
    row.resize(400, 30)
    row.grab()

    assert row.toolTip() == ""


def test_full_name_tooltip_clears_when_the_row_widens(qapp: QApplication):
    row = FillSlider("", LONG_APP)
    row.resize(120, 30)
    row.grab()
    assert row.toolTip() == LONG_APP

    row.resize(1200, 30)
    row.grab()
    assert row.toolTip() == ""


def test_date_pill_click_anywhere_on_the_widget_runs_the_left_callback(qapp: QApplication):
    widget = ClockWidget(ClockConfig.model_validate({"tooltip": False, "class_name": "date-pill"}))
    clicks: list[QPoint] = []
    widget.register_callback("probe", lambda: clicks.append(QPoint()))
    widget.callback_left = "probe"
    widget.resize(120, 40)
    try:
        for point in (QPoint(1, 1), QPoint(60, 20), QPoint(118, 38)):
            QTest.mouseClick(widget, Qt.MouseButton.LeftButton, pos=point)
        assert len(clicks) == 3
    finally:
        widget._shared_state.unregister_widget(widget)
        widget.deleteLater()
