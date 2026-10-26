from collections.abc import Iterator

import pytest
from PyQt6.QtWidgets import QApplication, QWidget

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


def test_content_frame_spans_the_popup_when_the_popup_is_wider_than_its_content(
    qapp: QApplication, bar: QWidget
) -> None:
    widget = _widget(bar)
    widget._show_menu()
    dialog = widget.dialog
    assert dialog is not None
    qapp.processEvents()

    assert dialog.width() == bar.width()
    assert dialog._popup_content.geometry() == dialog.rect()


def test_content_frame_follows_the_popup_when_the_bar_grows_after_it_opened(qapp: QApplication, bar: QWidget) -> None:
    widget = _widget(bar)
    widget._show_menu()
    dialog = widget.dialog
    assert dialog is not None
    bar.resize(900, 34)
    dialog.setPosition(*dialog._pos_args)
    qapp.processEvents()

    assert dialog.width() == 900
    assert dialog._popup_content.geometry() == dialog.rect()
