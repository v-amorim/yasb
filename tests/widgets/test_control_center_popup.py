from collections.abc import Iterator

import pytest
from PyQt6.QtCore import QEventLoop, QTimer
from PyQt6.QtWidgets import QApplication, QWidget

from core.utils import floating_popup
from core.validation.widgets.yasb.control_center import ControlCenterConfig
from core.widgets.yasb.control_center import ControlCenterWidget


@pytest.fixture
def bar(qapp: QApplication) -> Iterator[QWidget]:
    window = QWidget()
    window.setGeometry(100, 0, 700, 34)
    window.bar_frame = window  # type: ignore[attr-defined]
    window.setStyleSheet(".control-center-menu { min-width: 320px; padding: 8px; border: 1px solid #333; }")
    window.show()
    yield window
    window.deleteLater()


def _wait(ms: int) -> None:
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def _widget(bar: QWidget) -> ControlCenterWidget:
    config = ControlCenterConfig.model_validate(
        {
            "popup": {"anchor": "bar", "blur": False},
            "sections": {
                "sliders": {"show": False},
                "power": {"show": False},
                "media": {"show": False},
                "quick_actions": {"actions": []},
            },
        }
    )
    widget = ControlCenterWidget(config)
    widget.setParent(bar)
    return widget


def _x_center(widget: QWidget) -> int:
    return widget.mapToGlobal(widget.rect().center()).x()


def test_bar_anchored_menu_floats_at_its_own_width_with_the_content_frame_filling_it(
    qapp: QApplication, bar: QWidget
) -> None:
    widget = _widget(bar)
    widget._show_menu()
    dialog = widget.dialog
    assert dialog is not None
    qapp.processEvents()

    assert dialog.width() < bar.width()
    assert dialog._popup_content.geometry() == dialog.rect()


def test_menu_keeps_its_width_and_recentres_when_the_bar_grows_after_it_opened(
    qapp: QApplication, bar: QWidget
) -> None:
    widget = _widget(bar)
    widget._show_menu()
    dialog = widget.dialog
    assert dialog is not None
    qapp.processEvents()
    width = dialog.width()
    bar.resize(900, 34)
    dialog.setPosition(*dialog._pos_args)
    _wait(floating_popup.DROP_MS + 60)

    assert dialog.width() == width
    assert abs(_x_center(dialog) - _x_center(bar)) <= 1
    assert dialog._popup_content.geometry() == dialog.rect()
