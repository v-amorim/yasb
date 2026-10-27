# pyright: reportPrivateUsage=false

import pytest
from PyQt6.QtCore import QEasingCurve, QEventLoop, QPropertyAnimation, QTimer
from PyQt6.QtWidgets import QApplication, QFrame, QPushButton, QWidget

from core.utils import floating_popup
from core.utils.utilities import PopupWidget
from core.validation.widgets.yasb.systray import SystrayPopupConfig
from core.widgets.services.systray.systray_popup import SystrayPopup
from core.widgets.services.systray.systray_widget import DropWidget, IconWidget
from core.widgets.services.systray.utils import IconData


def _bar(qapp: QApplication) -> tuple[QWidget, QFrame, QPushButton]:
    window = QWidget()
    window.setGeometry(100, 100, 600, 34)
    frame = QFrame(window)
    frame.setGeometry(0, 0, 600, 34)
    frame.setProperty("class", "bar")
    window.bar_frame = frame  # type: ignore[attr-defined]
    tray = QWidget(window)
    tray.setGeometry(500, 4, 60, 26)
    button = QPushButton(tray)
    window.show()
    return window, frame, button


def _wait(ms: int) -> None:
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def test_bar_anchored_popup_floats_centred_under_the_bar_and_leaves_its_look_alone(qapp: QApplication) -> None:
    window, frame, button = _bar(qapp)
    config = SystrayPopupConfig(anchor="bar", round_corners=False, alignment="left", offset_top=0)
    popup = SystrayPopup(button.parentWidget(), button, config, 4)

    popup.open("")
    _wait(floating_popup.DROP_MS + 60)

    assert popup.minimumWidth() == 0
    assert popup.y() == frame.mapToGlobal(frame.rect().bottomLeft()).y() + 1 + floating_popup.GAP
    frame_center = frame.mapToGlobal(frame.rect().center()).x()
    assert abs(popup.mapToGlobal(popup.rect().center()).x() - frame_center) <= 1
    assert frame.property("class") == "bar"
    popup.hide()
    window.deleteLater()


def test_opening_another_bar_card_closes_the_open_tray_card(qapp: QApplication) -> None:
    window, _, button = _bar(qapp)
    tray = SystrayPopup(button.parentWidget(), button, SystrayPopupConfig(anchor="bar", offset_top=0), 4)
    volume_item = QWidget(window)
    volume_item.setGeometry(20, 4, 60, 26)
    tray.open("")
    qapp.processEvents()

    volume = PopupWidget(volume_item, bar_anchored=True)
    volume.resize(200, 80)
    volume.show()
    qapp.processEvents()

    assert tray._is_closing, "one floating card at a time"
    assert not volume._is_closing
    volume.hide()
    window.deleteLater()


def _bar_tray(qapp: QApplication) -> tuple[QWidget, QFrame, SystrayPopup]:
    window, frame, button = _bar(qapp)
    popup = SystrayPopup(button.parentWidget(), button, SystrayPopupConfig(anchor="bar", offset_top=0), 4)
    return window, frame, popup


def test_reduced_motion_systray_opens_at_its_final_spot_without_fade(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(floating_popup, "animations_enabled", lambda: False)
    window, frame, popup = _bar_tray(qapp)

    popup.open("")

    assert popup._floating is not None
    assert popup._floating._drop.state() != QPropertyAnimation.State.Running
    assert popup.pos() == floating_popup.centred_under(popup, frame)
    assert popup._fade_animation.duration() == 0
    assert popup.windowOpacity() == 1.0
    popup.hide()
    window.deleteLater()


def test_reduced_motion_systray_closes_at_once(qapp: QApplication, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(floating_popup, "animations_enabled", lambda: False)
    window, _, popup = _bar_tray(qapp)
    popup.open("")

    popup.hide_animated()

    assert not popup.isVisible()
    assert not popup._is_closing
    window.deleteLater()


def test_systray_animations_on_drops_in_and_fades_over_180ms(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(floating_popup, "animations_enabled", lambda: True)
    window, frame, popup = _bar_tray(qapp)

    popup.open("")

    assert popup._floating is not None
    assert popup._floating._drop.state() == QPropertyAnimation.State.Running
    assert popup.y() == floating_popup.centred_under(popup, frame).y() - floating_popup.DROP
    assert popup._fade_animation.duration() == floating_popup.DROP_MS
    popup.hide()
    window.deleteLater()


def test_systray_fades_with_the_same_easing_as_popup_widget(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(floating_popup, "animations_enabled", lambda: True)
    window, _, popup = _bar_tray(qapp)

    popup.open("")
    assert popup._fade_animation.easingCurve().type() == QEasingCurve.Type.OutCubic
    popup.hide_animated()

    assert popup._fade_animation.easingCurve().type() == QEasingCurve.Type.InCubic
    popup.hide()
    window.deleteLater()


def test_systray_exit_fade_is_120ms_and_the_next_open_is_180ms_again(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(floating_popup, "animations_enabled", lambda: True)
    window, _, popup = _bar_tray(qapp)
    popup.open("")

    popup.hide_animated()
    assert popup._fade_animation.duration() == floating_popup.EXIT_MS == 120
    popup.hide()
    popup.open("")

    assert popup._fade_animation.duration() == floating_popup.DROP_MS
    popup.hide()
    window.deleteLater()


def test_widget_anchored_popup_leaves_the_bar_alone(qapp: QApplication) -> None:
    window, frame, button = _bar(qapp)
    popup = SystrayPopup(button.parentWidget(), button, SystrayPopupConfig(), 4)

    popup.open("")

    assert frame.property("class") == "bar"
    assert popup.minimumWidth() == 0
    popup.hide()
    window.deleteLater()


def test_the_toggle_buttons_slot_looks_open_while_the_tray_card_shows(qapp: QApplication) -> None:
    window, _, popup = _bar_tray(qapp)
    popup._toggle_btn.setCheckable(True)
    slot = popup._toggle_btn.parentWidget()
    assert slot is not None
    slot.setProperty("class", "widget-container")

    popup.open("")
    assert slot.property("class") == "widget-container popup-open"

    popup.hide_animated()
    assert slot.property("class") == "widget-container"
    popup.hide()
    window.deleteLater()


def _tile(name: str) -> IconWidget:
    icon = IconWidget()
    icon.data = IconData(hIcon=1, szTip=name, exe="app")
    icon.name = name
    return icon


def test_tiles_fill_three_equal_columns(qapp: QApplication) -> None:
    window, frame, button = _bar(qapp)
    popup = SystrayPopup(button.parentWidget(), button, SystrayPopupConfig(anchor="bar", offset_top=0), 3)
    for i in range(7):
        popup.add_icon(_tile(f"App {'x' * (i * 6)}"))

    popup.open("")
    qapp.processEvents()

    tiles = popup.grid_widget._get_all_icons()
    assert all(tile.tile_mode for tile in tiles)
    assert len({tile.width() for tile in tiles}) == 1
    assert tiles[0].x() == tiles[3].x() == tiles[6].x()
    assert tiles[0].x() < tiles[1].x() < tiles[2].x()
    assert tiles[1].x() - (tiles[0].x() + tiles[0].width()) == 8
    assert tiles[3].y() - (tiles[0].y() + tiles[0].height()) == 8
    popup.hide()
    window.deleteLater()


def test_icon_returns_to_a_bare_button_outside_the_grid(qapp: QApplication) -> None:
    grid = DropWidget(grid_cols=3)
    bar = DropWidget()
    icon = _tile("Docker")

    grid.add_icon_to_grid(icon)
    assert icon.tile_mode

    bar.main_layout.addWidget(icon)
    assert not icon.tile_mode
    assert icon.sizeHint().width() < 150
