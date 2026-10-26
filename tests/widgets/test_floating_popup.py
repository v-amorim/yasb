import pytest
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QApplication

from core.utils import floating_popup
from core.utils.floating_popup import DROP_MS, EXIT_MS, PopupThread, fade_ms


def test_thread_colour_comes_from_the_stylesheet(qapp: QApplication) -> None:
    thread = PopupThread()
    thread.setStyleSheet(".popup-thread { qproperty-threadcolor: #ff0000; }")

    thread.ensurePolished()

    assert thread.get_color() == QColor("#ff0000")


def test_exit_fade_of_a_card_is_shorter_than_its_open_fade(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(floating_popup, "animations_enabled", lambda: True)

    assert fade_ms(floating=True, opening=True, base=80) == DROP_MS == 180
    assert fade_ms(floating=True, opening=False, base=80) == EXIT_MS == 120
    assert fade_ms(floating=False, opening=False, base=80) == 80


def test_reduced_motion_fade_has_no_duration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(floating_popup, "animations_enabled", lambda: False)

    assert fade_ms(floating=True, opening=True, base=80) == 0
    assert fade_ms(floating=True, opening=False, base=80) == 0
    assert fade_ms(floating=False, opening=True, base=80) == 0
