import os
from collections.abc import Iterator

import pytest
from PyQt6.QtWidgets import QApplication, QLabel, QPushButton, QVBoxLayout, QWidget

from core.validation.widgets.yasb.control_center import FoldersSectionConfig, SystemControlsConfig
from core.widgets.services.control_center.sections import folders, system_controls
from core.widgets.services.control_center.sections.folders import FoldersSectionWidget
from core.widgets.services.control_center.sections.quick_actions import ActionButton
from core.widgets.services.control_center.sections.system_controls import SystemControlsSectionWidget


@pytest.fixture
def host(qapp: QApplication) -> Iterator[QWidget]:
    widget = QWidget()
    yield widget
    widget.deleteLater()


def _rows(section: QWidget, class_name: str) -> list[ActionButton]:
    return [row for row in section.findChildren(ActionButton) if class_name in str(row.property("class")).split()]


def _power_section(host: QWidget, style: str) -> SystemControlsSectionWidget:
    return SystemControlsSectionWidget(host, SystemControlsConfig(power_style=style), lambda: None)


def test_menu_style_keeps_the_power_actions_out_of_the_panel(host: QWidget):
    section = _power_section(host, "menu")

    assert _rows(section, "power-item") == []


def test_power_button_unfolds_the_list_and_a_row_runs_its_action(host: QWidget, monkeypatch: pytest.MonkeyPatch):
    calls: list[str] = []
    monkeypatch.setattr(system_controls.PowerOperations, "shutdown", lambda self: calls.append("shutdown"))
    section = _power_section(host, "list")
    rows = _rows(section, "power-item")
    power_list = rows[0].parentWidget()
    assert power_list is not None and power_list.isHidden()
    assert [row.findChildren(QLabel)[1].text() for row in rows] == ["Lock", "Sign out", "Sleep", "Restart", "Shut down"]
    grid = power_list.layout()
    assert grid is not None
    assert [grid.getItemPosition(grid.indexOf(row)) for row in rows] == [
        (0, 0, 1, 1),
        (0, 1, 1, 1),
        (1, 0, 1, 1),
        (1, 1, 1, 1),
        (2, 0, 1, 2),
    ]

    (power_btn,) = [b for b in section.findChildren(QPushButton) if "power" in str(b.property("class")).split()]
    power_btn.click()
    assert not power_list.isHidden() and "active" in str(power_btn.property("class"))

    rows[-1].clicked.emit()
    assert calls == ["shutdown"]

    section.refresh_state()
    assert power_list.isHidden() and "active" not in str(power_btn.property("class"))


def test_panel_shrinks_back_when_the_power_list_folds(qapp: QApplication):
    panel = QWidget()
    layout = QVBoxLayout(panel)
    section = _power_section(panel, "list")
    layout.addWidget(section)
    panel.show()
    panel.adjustSize()
    folded_height = panel.height()

    section._set_power_list_open(True)
    qapp.processEvents()
    assert panel.height() > folded_height

    section._set_power_list_open(False)
    qapp.processEvents()
    assert panel.height() == folded_height
    panel.deleteLater()


def _settings_section(host: QWidget, **config) -> SystemControlsSectionWidget:
    return SystemControlsSectionWidget(host, SystemControlsConfig(settings_style="list", **config), lambda: None)


def _button(section: QWidget, class_name: str) -> QPushButton:
    (button,) = [b for b in section.findChildren(QPushButton) if class_name in str(b.property("class")).split()]
    return button


def test_menu_style_keeps_the_settings_links_out_of_the_panel(host: QWidget):
    section = SystemControlsSectionWidget(host, SystemControlsConfig(), lambda: None)

    assert _rows(section, "settings-item") == []


def test_settings_list_holds_the_groups_then_all_settings(host: QWidget):
    section = _settings_section(host)
    headers = [
        label.text() for label in section.findChildren(QLabel) if label.property("class") == "settings-group-label"
    ]
    names = [row.findChildren(QLabel)[1].text() for row in _rows(section, "settings-item")]

    assert headers == ["DEVICES", "WINDOWS"]
    assert names == [
        "Sound",
        "Bluetooth",
        "Network",
        "Power",
        "Windows Update",
        "Notifications",
        "Apps",
        "Accounts",
        "Privacy & Security",
        "All settings",
    ]


def test_settings_groups_come_from_the_config(host: QWidget):
    groups = [{"label": "Mine", "items": [{"label": "Display", "uri": "ms-settings:display"}]}]
    section = _settings_section(host, settings_groups=groups)

    assert [row.findChildren(QLabel)[1].text() for row in _rows(section, "settings-item")] == [
        "Display",
        "All settings",
    ]


def test_gear_unfolds_the_settings_list_and_a_row_opens_its_page(host: QWidget, monkeypatch: pytest.MonkeyPatch):
    opened: list[str] = []
    monkeypatch.setattr(system_controls, "shell_open", opened.append)
    section = _settings_section(host)
    rows = _rows(section, "settings-item")
    settings_list = section._settings_list
    assert settings_list is not None and settings_list.isHidden()

    gear = _button(section, "settings")
    gear.click()
    assert not settings_list.isHidden() and "active" in str(gear.property("class"))

    rows[0].clicked.emit()
    assert opened == ["ms-settings:sound"]

    section.refresh_state()
    assert settings_list.isHidden() and "active" not in str(gear.property("class"))


def test_settings_and_power_lists_never_open_together(host: QWidget):
    section = _settings_section(host, power_style="list")
    settings_list, power_list = section._settings_list, section._power_list
    assert settings_list is not None and power_list is not None

    _button(section, "settings").click()
    _button(section, "power").click()
    assert settings_list.isHidden() and not power_list.isHidden()

    _button(section, "settings").click()
    assert not settings_list.isHidden() and power_list.isHidden()


def test_folders_fill_the_columns_and_open_the_expanded_path(host: QWidget, monkeypatch: pytest.MonkeyPatch):
    opened: list[str] = []
    monkeypatch.setattr(folders.os, "startfile", opened.append, raising=False)
    monkeypatch.setattr(folders.os.path, "exists", lambda path: True)
    config = FoldersSectionConfig(
        show=True,
        columns=3,
        items=[{"title": name, "path": f"~/{name}"} for name in ("Home", "Downloads", "Documents", "Github")],
    )
    section = FoldersSectionWidget(host, config)

    rows = _rows(section, "folder")
    layout = section.layout()
    assert [row.findChildren(QLabel)[1].text() for row in rows] == ["Home", "Downloads", "Documents", "Github"]
    assert layout is not None and layout.getItemPosition(layout.indexOf(rows[3]))[:2] == (1, 0)

    rows[1].clicked.emit()
    assert opened == [os.path.expanduser("~/Downloads")]
