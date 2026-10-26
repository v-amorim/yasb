from types import SimpleNamespace

from PyQt6.QtWidgets import QApplication, QWidget

from core.validation.widgets.yasb.clock import ClockConfig
from core.widgets.yasb.clock import ClockWidget


def _clock(anchor: str, section: QWidget) -> SimpleNamespace:
    bar = SimpleNamespace(section_frame=lambda name: section if name == "center" else None)
    config = ClockConfig.model_validate({"calendar": {"anchor": anchor}})
    return SimpleNamespace(config=config, parent_layout_type="center", window=lambda: bar)


def test_section_anchor_points_every_clock_at_its_bar_section(qapp: QApplication):
    section = QWidget()

    assert ClockWidget._calendar_anchor(_clock("section", section)) is section  # type: ignore[arg-type]
    assert ClockWidget._calendar_anchor(_clock("widget", section)) is None  # type: ignore[arg-type]
