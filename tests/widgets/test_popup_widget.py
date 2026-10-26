from typing import Any

import pytest
from PyQt6.QtWidgets import QApplication, QFrame, QWidget

from core.utils import utilities
from core.utils.utilities import PopupWidget


@pytest.fixture
def corner_calls(monkeypatch: pytest.MonkeyPatch) -> list[tuple[Any, ...]]:
    calls: list[tuple[Any, ...]] = []
    monkeypatch.setattr(utilities, "is_windows_10", lambda: False)
    monkeypatch.setattr(utilities, "enable_blur", lambda *a, **k: calls.append(("blur", k)))
    monkeypatch.setattr(utilities, "enable_round_corners", lambda hwnd, kind, border: calls.append((kind, border)))
    return calls


def _show(qapp: QApplication, **options: Any) -> None:
    parent = QWidget()
    popup = PopupWidget(parent, **options)
    popup.show()
    popup.hide()
    parent.deleteLater()


def test_round_corners_apply_without_blur(qapp: QApplication, corner_calls: list[tuple[Any, ...]]) -> None:
    _show(qapp, blur=False, round_corners=True, round_corners_type="normal", border_color="#1E202C")

    assert corner_calls == [("normal", "#1E202C")]


def test_square_popup_without_blur_sets_nothing(qapp: QApplication, corner_calls: list[tuple[Any, ...]]) -> None:
    _show(qapp, blur=False, round_corners=False)

    assert corner_calls == []


def test_blur_popup_keeps_corners_in_blur_call(qapp: QApplication, corner_calls: list[tuple[Any, ...]]) -> None:
    _show(qapp, blur=True, round_corners=True)

    assert [call[0] for call in corner_calls] == ["blur"]


def test_anchor_centers_the_popup_on_another_widget(qapp: QApplication) -> None:
    window = QWidget()
    window.setGeometry(100, 100, 600, 40)
    parent = QWidget(window)
    parent.setGeometry(0, 0, 60, 30)
    section = QWidget(window)
    section.setGeometry(200, 0, 200, 34)
    window.show()
    popup = PopupWidget(parent)
    popup.resize(100, 50)

    popup.setPosition(alignment="center", anchor=section)
    centered_on_section = popup.geometry().center().x()
    popup.setPosition(alignment="center")
    centered_on_parent = popup.geometry().center().x()

    assert centered_on_section == section.mapToGlobal(section.rect().center()).x()
    assert centered_on_parent == parent.mapToGlobal(parent.rect().center()).x()
    window.deleteLater()


def test_bar_widget_container_is_marked_while_its_popup_shows(qapp: QApplication) -> None:
    parent = QWidget()
    container = QFrame(parent)
    container.setProperty("class", "widget-container")
    parent._widget_container = container  # type: ignore[attr-defined]
    popup = PopupWidget(parent)

    popup.show()
    assert container.property("class") == "widget-container popup-open"
    popup.hide()
    assert container.property("class") == "widget-container"
    parent.deleteLater()
