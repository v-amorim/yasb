# pyright: reportPrivateUsage=false

from PyQt6.QtWidgets import QApplication, QFrame, QPushButton, QWidget

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


def test_bar_anchored_popup_hangs_under_the_bar_and_marks_it(qapp: QApplication) -> None:
    window, frame, button = _bar(qapp)
    config = SystrayPopupConfig(anchor="bar", round_corners=False, alignment="center", offset_top=0)
    popup = SystrayPopup(button.parentWidget(), button, config, 4)

    popup.open("")
    qapp.processEvents()

    assert popup.minimumWidth() == frame.width()
    assert popup.y() == frame.mapToGlobal(frame.rect().bottomLeft()).y() + 1
    assert frame.property("class") == "bar popup-open"
    popup.hide()
    assert frame.property("class") == "bar"
    window.deleteLater()


def test_widget_anchored_popup_leaves_the_bar_alone(qapp: QApplication) -> None:
    window, frame, button = _bar(qapp)
    popup = SystrayPopup(button.parentWidget(), button, SystrayPopupConfig(), 4)

    popup.open("")

    assert frame.property("class") == "bar"
    assert popup.minimumWidth() == 0
    popup.hide()
    window.deleteLater()


def _tile(name: str) -> IconWidget:
    icon = IconWidget()
    icon.data = IconData(hIcon=1, szTip=name, exe="app")
    icon.name = name
    return icon


def test_tiles_fill_three_equal_columns_across_the_bar_width(qapp: QApplication) -> None:
    window, frame, button = _bar(qapp)
    popup = SystrayPopup(button.parentWidget(), button, SystrayPopupConfig(anchor="bar", offset_top=0), 3)
    for i in range(7):
        popup.add_icon(_tile(f"App {'x' * (i * 6)}"))

    popup.open("")
    qapp.processEvents()

    tiles = popup.grid_widget._get_all_icons()
    assert all(tile.tile_mode for tile in tiles)
    assert popup.width() == frame.width()
    assert len({tile.width() for tile in tiles}) == 1
    assert tiles[0].x() == tiles[3].x() == tiles[6].x()
    assert tiles[0].x() < tiles[1].x() < tiles[2].x()
    assert tiles[1].x() - (tiles[0].x() + tiles[0].width()) == 6
    assert tiles[3].y() - (tiles[0].y() + tiles[0].height()) == 6
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
