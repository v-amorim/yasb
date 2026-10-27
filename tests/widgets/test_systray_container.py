import pytest
from PyQt6.QtWidgets import QApplication

from core.validation.widgets.yasb.systray import SystrayWidgetConfig
from core.widgets.yasb.systray import SystrayWidget


def test_the_systray_slot_takes_the_ink_balance_every_bar_slot_gets(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(SystrayWidget, "setup_client", lambda self: None)
    monkeypatch.setattr(SystrayWidget, "set_containers_visibility", lambda self: None)
    widget = SystrayWidget(SystrayWidgetConfig())
    widget.setStyleSheet(".widget-container { qproperty-inkbalance: edges; }")
    widget.ensurePolished()
    widget.widget_container.ensurePolished()

    assert widget.widget_container.property("inkbalance") == "edges"
    widget.deleteLater()
