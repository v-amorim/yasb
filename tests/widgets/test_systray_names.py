from collections.abc import Callable

from core.widgets.services.systray.utils import tray_icon_name


def _describe(text: str) -> Callable[[str], str]:
    return lambda _path: text


def test_tooltip_first_line_wins() -> None:
    assert tray_icon_name("Docker Desktop\nrunning", "c:/d.exe", "docker", _describe("Docker")) == "Docker Desktop"


def test_live_tooltip_falls_back_to_the_description() -> None:
    assert tray_icon_name("Speakers: 45%", "c:/e.exe", "EarTrumpet", _describe("EarTrumpet app")) == "EarTrumpet app"


def test_empty_tooltip_uses_the_description_then_the_exe() -> None:
    assert tray_icon_name("", "c:/a.exe", "arc", _describe("Arc Browser")) == "Arc Browser"
    assert tray_icon_name("  \n", "c:/a.exe", "arc", _describe("")) == "arc"


def test_live_tooltip_is_the_last_resort() -> None:
    assert tray_icon_name("Battery 80%", "", "", _describe("")) == "Battery 80%"
