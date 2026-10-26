import pytest
from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QApplication, QHBoxLayout, QPushButton, QWidget

from core.utils import floating_popup
from core.utils.floating_popup import DROP_MS, EXIT_MS, PopupThread, fade_ms, thread_start


def test_thread_colour_comes_from_the_stylesheet(qapp: QApplication) -> None:
    thread = PopupThread()
    thread.setStyleSheet(".popup-thread { qproperty-threadcolor: #ff0000; }")

    thread.ensurePolished()

    assert thread.get_color() == QColor("#ff0000")


def test_thread_hangs_from_the_anchor_not_the_whole_container(qapp: QApplication) -> None:
    # The tray's container also holds its pinned icons, so the thread hung beside the toggle button the card opens from.
    bar = QWidget()
    row = QHBoxLayout(bar)
    row.setContentsMargins(0, 0, 0, 0)
    item = QWidget()
    container = QWidget()
    item._widget_container = container  # type: ignore[attr-defined]
    inner = QHBoxLayout(container)
    inner.setContentsMargins(0, 0, 0, 0)
    button, pinned = QPushButton(), QWidget()
    button.setFixedSize(30, 30)
    pinned.setFixedSize(120, 30)
    inner.addWidget(button)
    inner.addWidget(pinned)
    QHBoxLayout(item).addWidget(container)
    row.addWidget(item)
    bar.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
    bar.show()
    qapp.processEvents()

    under_button = button.mapToGlobal(QPoint(button.width() // 2, 0)).x()
    assert thread_start(item, bar, anchor=button).x() == under_button
    assert thread_start(item, bar).x() != under_button
    bar.close()


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
