from PyQt6.QtCore import QEvent, QRect, Qt
from PyQt6.QtGui import QColor, QFocusEvent
from PyQt6.QtWidgets import QApplication, QPushButton, QWidget

from core.utils.focus_ring import GAP, WIDTH, attach_focus_ring


def _card_with_button(width: int = 40, height: int = 30) -> tuple[QWidget, QPushButton]:
    card = QWidget()
    card.resize(200, 120)
    attach_focus_ring(card)
    button = QPushButton(card)
    button.setGeometry(20, 20, width, height)
    return card, button


def _focus(widget: QWidget, kind: QEvent.Type, reason: Qt.FocusReason) -> None:
    QApplication.sendEvent(widget, QFocusEvent(kind, reason))


def test_tab_draws_the_ring_gap_plus_width_outside_the_control(qapp: QApplication) -> None:
    card, button = _card_with_button()

    _focus(button, QEvent.Type.FocusIn, Qt.FocusReason.TabFocusReason)

    ring = card.focus_ring
    out = GAP + WIDTH
    assert ring.isVisibleTo(card)
    assert ring.geometry() == QRect(20 - out, 20 - out, 40 + 2 * out, 30 + 2 * out)


def test_backtab_draws_it_too(qapp: QApplication) -> None:
    card, button = _card_with_button()

    _focus(button, QEvent.Type.FocusIn, Qt.FocusReason.BacktabFocusReason)

    assert card.focus_ring.isVisibleTo(card)


def test_a_mouse_click_focus_draws_no_ring_and_clears_a_tab_ring(qapp: QApplication) -> None:
    card, button = _card_with_button()
    _focus(button, QEvent.Type.FocusIn, Qt.FocusReason.TabFocusReason)

    _focus(button, QEvent.Type.FocusIn, Qt.FocusReason.MouseFocusReason)

    assert not card.focus_ring.isVisibleTo(card)


def test_losing_focus_clears_the_ring(qapp: QApplication) -> None:
    card, button = _card_with_button()
    _focus(button, QEvent.Type.FocusIn, Qt.FocusReason.TabFocusReason)

    _focus(button, QEvent.Type.FocusOut, Qt.FocusReason.ActiveWindowFocusReason)

    assert not card.focus_ring.isVisibleTo(card)


def test_closing_the_card_clears_the_ring_so_it_does_not_come_back_stale(qapp: QApplication) -> None:
    card, button = _card_with_button()
    _focus(button, QEvent.Type.FocusIn, Qt.FocusReason.TabFocusReason)

    QApplication.sendEvent(card, QEvent(QEvent.Type.Hide))

    assert not card.focus_ring.isVisibleTo(card)


def test_a_window_without_a_ring_is_left_alone(qapp: QApplication) -> None:
    window = QWidget()
    button = QPushButton(window)

    _focus(button, QEvent.Type.FocusIn, Qt.FocusReason.TabFocusReason)

    assert not hasattr(window, "focus_ring")


def test_the_ring_keeps_its_corners_concentric_with_the_control(qapp: QApplication) -> None:
    card, tile = _card_with_button(40, 30)
    round_button = QPushButton(card)
    round_button.setGeometry(100, 20, 30, 30)
    ring = card.focus_ring
    ring.setStyleSheet(".focus-ring { qproperty-radius: 4px; }")
    ring.ensurePolished()

    _focus(tile, QEvent.Type.FocusIn, Qt.FocusReason.TabFocusReason)
    tile_corner = ring.corner_radius()
    _focus(round_button, QEvent.Type.FocusIn, Qt.FocusReason.TabFocusReason)

    assert tile_corner == 4 + GAP + WIDTH / 2
    assert ring.corner_radius() == 15 + GAP + WIDTH / 2


def test_ring_colour_comes_from_the_stylesheet(qapp: QApplication) -> None:
    card, _ = _card_with_button()
    ring = card.focus_ring
    ring.setStyleSheet(".focus-ring { qproperty-ringcolor: #ff0000; }")

    ring.ensurePolished()

    assert ring.get_color() == QColor("#ff0000")
