# pyright: reportPrivateUsage=false

from collections.abc import Callable, Iterator
from types import SimpleNamespace
from typing import Any

import pytest
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtWidgets import QApplication, QPushButton, QWidget

from core.ui.components.fill_slider import ELIDE_AFTER_CHARS, FillSlider
from core.validation.widgets.yasb.volume import VolumeConfig
from core.widgets.yasb import volume
from core.widgets.yasb.volume import VolumeWidget

type MakeWidget = Callable[..., VolumeWidget]

HEADSET = "Speakers (HECATE G4 TE GAMING HEADSET)"


class _FakeVolume:
    def __init__(self, level: float, muted: bool = False) -> None:
        self.level = level
        self.muted = muted

    def GetMasterVolumeLevelScalar(self) -> float:
        return self.level

    def SetMasterVolumeLevelScalar(self, level: float, context: object) -> None:
        self.level = level

    def GetMasterVolume(self) -> float:
        return self.level

    def SetMasterVolume(self, level: float, context: object) -> None:
        self.level = level

    def GetMute(self) -> int:
        return int(self.muted)

    def SetMute(self, muted: bool, context: object) -> None:
        self.muted = bool(muted)


class _FakeService:
    def __init__(self) -> None:
        self.master = _FakeVolume(0.3)
        # Windows stores 1% as a float just under 0.01
        self.spotify = _FakeVolume(0.009999999776482582)
        self.system = _FakeVolume(0.5)
        self.devices: list[tuple[str, str | None]] = [("monitor", "6 - U34G4C"), ("headset", HEADSET)]

    def __call__(self) -> _FakeService:
        return self

    def register_widget(self, widget: object) -> None:
        pass

    def unregister_widget(self, widget: object) -> None:
        pass

    def get_volume_interface(self) -> _FakeVolume:
        return self.master

    def get_all_devices(self) -> list[tuple[str, str | None]]:
        return self.devices

    def get_speakers(self) -> SimpleNamespace:
        return SimpleNamespace(id="headset")

    def get_active_audio_sessions(
        self, system_sounds_label: str | None = None, **callbacks: object
    ) -> list[dict[str, Any]]:
        apps = [{"name": "spotify.exe", "app_name": "Spotify", "volume_interface": self.spotify, "pid": 4242}]
        if not system_sounds_label:
            return apps
        system = {
            "name": system_sounds_label,
            "app_name": system_sounds_label,
            "volume_interface": self.system,
            "pid": 0,
        }
        return [system, *apps]


@pytest.fixture
def service(monkeypatch: pytest.MonkeyPatch) -> _FakeService:
    fake = _FakeService()
    monkeypatch.setattr(volume, "AudioOutputService", fake)
    return fake


@pytest.fixture
def make_widget(qapp: QApplication, service: _FakeService) -> Iterator[MakeWidget]:
    widgets: list[VolumeWidget] = []

    def make(**menu: Any) -> VolumeWidget:
        config = {"tooltip": False, "slider_beep": False, "audio_menu": {"show_app_icons": False, **menu}}
        widget = VolumeWidget(VolumeConfig.model_validate(config))
        widgets.append(widget)
        return widget

    yield make
    for widget in widgets:
        if widget.dialog is not None:
            # A fading popup keeps its app-wide filter, which would swallow the next test's clicks
            qapp.removeEventFilter(widget.dialog)
            widget.dialog.close()
        widget.deleteLater()


def _right_click(slider: FillSlider) -> None:
    point = QPointF(slider.width() / 2, slider.height() / 2)
    event = QMouseEvent(
        QMouseEvent.Type.MouseButtonPress,
        point,
        slider.mapToGlobal(point),
        Qt.MouseButton.RightButton,
        Qt.MouseButton.RightButton,
        Qt.KeyboardModifier.NoModifier,
    )
    # Straight to the handler: a popup another test left fading would filter a sent event out
    slider.mousePressEvent(event)


def _classes(widget: QWidget) -> set[str]:
    return set(str(widget.property("class")).split())


def _app_rows(widget: VolumeWidget) -> list[FillSlider]:
    assert widget.dialog is not None
    return [row for row in widget.dialog.findChildren(FillSlider) if "app-slider" in _classes(row)]


def test_fill_slider_right_click_signals_without_moving(qapp: QApplication):
    slider = FillSlider("", "Spotify")
    slider.resize(200, 30)
    slider.setValue(40)
    clicks: list[bool] = []
    slider.right_clicked.connect(lambda: clicks.append(True))

    _right_click(slider)

    assert clicks == [True] and slider.value() == 40


def test_fill_slider_caps_a_long_name_and_keeps_its_text(qapp: QApplication):
    slider = FillSlider("", HEADSET)
    name = slider._name

    assert name.text() == HEADSET
    assert name.sizeHint().width() <= name.fontMetrics().averageCharWidth() * ELIDE_AFTER_CHARS
    assert name.minimumSizeHint().width() == 0


def test_default_style_keeps_the_plain_slider(make_widget: MakeWidget):
    widget = make_widget(show_apps=True)
    widget.show_volume_menu()

    assert widget.volume_slider is not None and not isinstance(widget.volume_slider, FillSlider)


def test_fill_style_names_the_master_row_after_the_device(make_widget: MakeWidget):
    widget = make_widget(slider_style="fill")
    widget.show_volume_menu()

    master = widget.volume_slider
    assert isinstance(master, FillSlider)
    assert master._name.text() == HEADSET and master.value() == 30
    assert widget.container.isHidden()


def _device_toggles(widget: VolumeWidget) -> list[QPushButton]:
    assert widget.dialog is not None
    return [button for button in widget.dialog.findChildren(QPushButton) if "toggle-devices" in _classes(button)]


def test_switch_device_unfolds_the_device_list(make_widget: MakeWidget):
    widget = make_widget(slider_style="fill", switch_device_label="Trocar")
    widget.show_volume_menu()
    (toggle,) = _device_toggles(widget)
    assert toggle.text().startswith("Trocar")

    toggle.click()
    assert not widget.container.isHidden() and "expanded" in str(toggle.property("class"))
    toggle.click()
    assert widget.container.isHidden()


def test_one_device_shows_no_switch(make_widget: MakeWidget, service: _FakeService):
    service.devices = [("headset", HEADSET)]
    widget = make_widget(slider_style="fill")
    widget.show_volume_menu()

    assert _device_toggles(widget) == []


def test_right_click_on_the_master_row_mutes_the_system(make_widget: MakeWidget, service: _FakeService):
    widget = make_widget(slider_style="fill")
    widget.show_volume_menu()
    master = widget.volume_slider
    assert isinstance(master, FillSlider)

    _right_click(master)
    assert service.master.muted and "muted" in _classes(master)
    _right_click(master)
    assert not service.master.muted and "muted" not in _classes(master)


def test_app_rows_show_without_a_toggle_and_mute_on_right_click(make_widget: MakeWidget, service: _FakeService):
    widget = make_widget(slider_style="fill", show_apps=True)
    widget.show_volume_menu()

    (spotify,) = _app_rows(widget)
    assert spotify._name.text() == "Spotify" and spotify.value() == 1
    assert widget.app_toggle_btn is None

    spotify.setValue(80)
    assert service.spotify.level == pytest.approx(0.8)

    _right_click(spotify)
    assert service.spotify.muted and "muted" in _classes(spotify)
    assert spotify.isEnabled()
    _right_click(spotify)
    assert not service.spotify.muted and "muted" not in _classes(spotify)


def test_system_sounds_stay_hidden_by_default(make_widget: MakeWidget):
    widget = make_widget(slider_style="fill", show_apps=True)
    widget.show_volume_menu()

    assert [row._name.text() for row in _app_rows(widget)] == ["Spotify"]


def test_system_sounds_row_comes_first_with_its_glyph(make_widget: MakeWidget, service: _FakeService):
    widget = make_widget(
        slider_style="fill", show_apps=True, show_app_icons=True, show_system_sounds=True, system_sounds_label="Sons"
    )
    widget.show_volume_menu()

    system, spotify = _app_rows(widget)
    assert system._name.text() == "Sons" and spotify._name.text() == "Spotify"
    assert system.icon_label.text() == "" and system.value() == 50

    _right_click(system)
    assert service.system.muted and "muted" in _classes(system)
    assert system.icon_label.text() == ""


def _session(pid: int, name: str | None) -> SimpleNamespace:
    process = SimpleNamespace(name=lambda: name, pid=pid) if name else None
    return SimpleNamespace(
        Process=process, ProcessId=pid, GroupingParam="", DisplayName="", SimpleAudioVolume=_FakeVolume(1.0)
    )


def test_service_lists_the_processless_system_session_first():
    from core.widgets.services.volume.service import AudioOutputService

    host = SimpleNamespace(
        get_speakers=lambda: object(),
        get_all_sessions=lambda: [_session(4242, "spotify.exe"), _session(0, None), _session(0, None)],
    )
    get_sessions = AudioOutputService.get_active_audio_sessions

    plain = get_sessions(host, format_name_callback=lambda name: "Spotify")  # type: ignore[arg-type]
    labeled = get_sessions(host, format_name_callback=lambda name: "Spotify", system_sounds_label="System sounds")  # type: ignore[arg-type]

    assert [s["app_name"] for s in plain] == ["Spotify"]
    assert [(s["app_name"], s["pid"]) for s in labeled] == [("System sounds", 0), ("Spotify", 4242)]
