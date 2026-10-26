# pyright: reportPrivateUsage=false

import copy
from collections.abc import Callable, Iterator
from typing import Any

import pytest
from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QApplication, QFrame, QLabel

from core.validation.widgets.yasb.weather import WeatherWidgetConfig
from core.widgets.services.weather.hour_chart import HourChart, HourTip
from core.widgets.yasb import weather
from core.widgets.yasb.weather import WeatherWidget

type MakeWidget = Callable[..., WeatherWidget]


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


def _day(date: str, low: float, high: float, rain: float, code: int) -> dict[str, Any]:
    return {
        "date": date,
        "day": {
            "mintemp_c": low,
            "maxtemp_c": high,
            "daily_chance_of_rain": rain,
            "condition": {"text": "", "icon": "//cdn/icon.png", "code": code},
        },
        "hour": [],
    }


API_DATA: dict[str, Any] = {
    "location": {"name": "São José dos Campos", "localtime": "2026-10-23 10:00"},
    "current": {
        "temp_c": 19.2,
        "feelslike_c": 20.8,
        "humidity": 94,
        "is_day": 1,
        "condition": {"text": "Light rain", "icon": "//cdn/icon.png", "code": 1183},
    },
    "forecast": {
        "forecastday": [
            _day("2026-10-23", 18.1, 23.9, 92, 1183),
            _day("2026-10-24", 17.0, 25.2, 40, 1003),
            _day("2026-10-25", 18.4, 22.0, 85, 1183),
        ]
    },
}


@pytest.fixture
def make_widget(qapp: QApplication, monkeypatch: pytest.MonkeyPatch) -> Iterator[MakeWidget]:
    monkeypatch.setattr(weather.WeatherDataFetcher, "get_instance", lambda *args: _FakeFetcher())
    monkeypatch.setattr(weather.IconFetcher, "get_instance", lambda *args: _FakeIcons())
    widgets: list[WeatherWidget] = []

    def make(**card: Any) -> WeatherWidget:
        config = WeatherWidgetConfig.model_validate(
            {"api_key": "key", "location": "here", "hide_decimal": True, "weather_card": card}
        )
        widget = WeatherWidget(config)
        widget.process_weather_data(API_DATA)
        widgets.append(widget)
        return widget

    yield make
    for widget in widgets:
        widget.dialog.close()
        widget.deleteLater()


# Configs spell Nerd glyphs as surrogate pairs; a QLabel hands them back as one code point
def _glyph(text: str) -> str:
    return text.encode("utf-16", "surrogatepass").decode("utf-16")


def _texts(parent: QObject, class_name: str) -> list[str]:
    return [label.text() for label in parent.findChildren(QLabel) if class_name in str(label.property("class")).split()]


def test_rows_layout_shows_the_now_header(make_widget: MakeWidget):
    widget = make_widget(layout="rows")
    widget._popup_card()

    assert _texts(widget.dialog, "now-temp") == ["19°C"]
    assert _texts(widget.dialog, "now-condition") == ["Rainy"]
    assert _texts(widget.dialog, "fact-label") == ["Feels", "Humidity", "Rain"]
    assert _texts(widget.dialog, "fact-value") == ["21°", "94%", "92%"]
    assert _texts(widget.dialog, "now-place") == ["São José dos Campos"]


def test_rows_layout_lists_each_day_with_its_range_and_rain(make_widget: MakeWidget):
    widget = make_widget(layout="rows")
    widget._popup_card()
    rows = [frame for frame in widget.dialog.findChildren(QFrame) if "day-row" in str(frame.property("class")).split()]

    assert _texts(widget.dialog, "day-name") == ["Today", "Sat 24", "Sun 25"]
    icons = widget.config.icons
    assert _texts(widget.dialog, "day-icon") == [
        _glyph(icons.rainyDay),
        _glyph(icons.cloudyDay),
        _glyph(icons.rainyDay),
    ]
    assert _texts(widget.dialog, "day-low") == ["18°", "17°", "18°"]
    assert _texts(widget.dialog, "day-high") == ["24°", "25°", "22°"]
    assert _texts(widget.dialog, "day-rain") == ["92%", "40%", "85%"]
    assert ["rainy" in str(row.property("class")).split() for row in rows] == [True, False, True]


def _hourly_api_data() -> dict[str, Any]:
    data = copy.deepcopy(API_DATA)
    for day_index, entry in enumerate(data["forecast"]["forecastday"]):
        date = f"2026-10-{23 + day_index}"
        entry["hour"] = [
            {
                "time": f"{date} {hour:02d}:00",
                "temp_c": 10 + hour / 2,
                "feelslike_c": 9.8 + hour / 2,
                "chance_of_rain": hour * 4,
            }
            for hour in range(24)
        ]
    return data


def test_chart_layout_shows_now_chart_and_day_tiles(make_widget: MakeWidget):
    widget = make_widget(layout="chart")
    widget.process_weather_data(_hourly_api_data())
    widget._popup_card()

    assert _texts(widget.dialog, "chart-temp") == ["19°C"]
    assert _texts(widget.dialog, "chart-condition") == ["Rainy"]
    assert _texts(widget.dialog, "chart-fact-label") == ["Feels", "Humidity", "Rain"]
    assert _texts(widget.dialog, "chart-fact-value") == ["21°", "94%", "92%"]
    assert _texts(widget.dialog, "chart-place") == ["São José dos Campos"]
    assert _texts(widget.dialog, "tile-name") == ["Today", "Sat 24", "Sun 25"]
    assert _texts(widget.dialog, "tile-low") == ["18°", "17°", "18°"]
    assert _texts(widget.dialog, "tile-high") == ["24°", "25°", "22°"]
    assert _texts(widget.dialog, "tile-rain") == [" 92%", " 40%", " 85%"]
    tiles = [f for f in widget.dialog.findChildren(QFrame) if "tile" in str(f.property("class")).split()]
    assert ["rainy" in str(tile.property("class")).split() for tile in tiles] == [True, False, True]


def test_chart_covers_the_twelve_hours_after_now(make_widget: MakeWidget):
    widget = make_widget(layout="chart")
    widget.process_weather_data(_hourly_api_data())
    widget._popup_card()
    hours = widget._card_rows["hours"]

    assert [hour.label for hour in hours] == [f"{h:02d}h" for h in range(11, 23)]
    assert hours[0].rain == 44
    assert hours[0].temp_text == "16°"
    assert hours[0].feels_text == "15°"


def test_chart_tooltip_stacks_hour_temperature_and_details(make_widget: MakeWidget):
    widget = make_widget(layout="chart")
    widget.process_weather_data(_hourly_api_data())
    widget._popup_card()
    chart = widget.dialog.findChild(HourChart)
    assert chart is not None

    chart._tip = HourTip(widget.dialog, "D")
    chart._tip.show_hour(widget._card_rows["hours"][0], 0, 400, 100, 100)

    assert _texts(chart._tip, "hour-tip-hour") == ["11h"]
    assert _texts(chart._tip, "hour-tip-temp") == ["16°"]
    assert _texts(chart._tip, "hour-tip-detail") == ["Feels 15° · ", "D", " 44%"]


def test_columns_layout_stays_the_default(make_widget: MakeWidget):
    widget = make_widget()
    widget._popup_card()

    assert _texts(widget.dialog, "day-name") == []
    assert len([f for f in widget.dialog.findChildren(QFrame) if f.property("class") == "weather-card-day"]) >= 2
