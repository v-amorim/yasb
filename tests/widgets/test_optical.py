# pyright: reportPrivateUsage=false

from collections.abc import Callable, Iterator
from typing import Any

import pytest
from PyQt6.QtWidgets import QApplication, QHBoxLayout, QLabel, QWidget

from core.ui.components import fill_slider
from core.ui.components.fill_slider import FillSlider
from core.utils import optical
from core.utils.optical import icon_shift
from core.validation.widgets.yasb.control_center import FoldersSectionConfig, SystemControlsConfig
from core.widgets.services.control_center.sections import folders, system_controls
from core.widgets.services.control_center.sections.folders import FoldersSectionWidget
from core.widgets.services.control_center.sections.system_controls import SystemControlsSectionWidget

type Pairs = list[tuple[QLabel, QLabel]]

TEXT_LINE = {"text_ascent": 10, "text_descent": 4, "text_height": 14, "cap_height": 7}
ICON_LINE = {"icon_ascent": 10, "icon_descent": 4, "icon_height": 14}


def test_optical_shift_moves_a_high_icon_down():
    # Ink centre 4.5 px above the baseline, cap midline 3.5 px above it: the icon sits 1 px high
    assert icon_shift(**ICON_LINE, ink_top=-9, ink_bottom=0, **TEXT_LINE) == pytest.approx(1.0)


def test_optical_shift_moves_a_low_icon_up():
    assert icon_shift(**ICON_LINE, ink_top=-4, ink_bottom=4, **TEXT_LINE) == pytest.approx(-3.5)


def test_optical_shift_is_zero_when_the_ink_already_sits_on_the_cap_midline():
    assert icon_shift(**ICON_LINE, ink_top=-7, ink_bottom=0, **TEXT_LINE) == pytest.approx(0.0)


def test_optical_shift_counts_the_two_fonts_line_boxes_and_label_heights():
    shift = icon_shift(
        icon_ascent=12,
        icon_descent=6,
        icon_height=18,
        ink_top=-8,
        ink_bottom=0,
        text_ascent=10,
        text_descent=4,
        text_height=14,
        cap_height=7,
    )
    assert shift == pytest.approx(0.5)

    taller_text = icon_shift(**ICON_LINE, ink_top=-9, ink_bottom=0, **{**TEXT_LINE, "text_height": 24})
    assert taller_text == pytest.approx(1.0)


def _row(icon_size: int, text_size: int) -> tuple[QWidget, QLabel, QLabel]:
    host = QWidget()
    layout = QHBoxLayout(host)
    icon, text = QLabel("O", host), QLabel("Hg", host)
    for label, size in ((icon, icon_size), (text, text_size)):
        font = label.font()
        font.setPixelSize(size)
        label.setFont(font)
        layout.addWidget(label)
    return host, icon, text


def _fake_shift(icon: QLabel, text: QLabel) -> float:
    """The offscreen platform has box-glyph fonts that always centre, so stand in a shift that follows both fonts."""
    return (text.font().pixelSize() - icon.font().pixelSize()) / 4


@pytest.fixture
def fake_shift(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(optical, "measure_shift", _fake_shift)


def _margin_offset(icon: QLabel) -> int:
    margins = icon.contentsMargins()
    return margins.top() - margins.bottom()


def test_optical_reapplies_when_the_font_changes(qapp: QApplication, fake_shift: None):
    host, icon, text = _row(12, 12)
    optical.center_icon_on_text(icon, text)
    host.show()
    qapp.processEvents()
    before = _margin_offset(icon)
    assert before == round(_fake_shift(icon, text) * 2)

    font = text.font()
    font.setPixelSize(48)
    text.setFont(font)
    after = _margin_offset(icon)

    assert after == round(_fake_shift(icon, text) * 2)
    assert after != before
    host.deleteLater()


def test_optical_reapplies_when_the_icon_font_changes(qapp: QApplication, fake_shift: None):
    host, icon, text = _row(12, 12)
    optical.center_icon_on_text(icon, text)
    host.show()
    before = _margin_offset(icon)

    font = icon.font()
    font.setPixelSize(40)
    icon.setFont(font)

    assert _margin_offset(icon) == round(_fake_shift(icon, text) * 2)
    assert _margin_offset(icon) != before
    host.deleteLater()


def test_optical_reapplies_when_the_stylesheet_changes_the_font(qapp: QApplication, fake_shift: None):
    host, icon, text = _row(12, 12)
    optical.center_icon_on_text(icon, text)
    host.show()
    before = _margin_offset(icon)

    text.setStyleSheet("font-size: 60px;")
    qapp.processEvents()

    assert _margin_offset(icon) == round(_fake_shift(icon, text) * 2)
    assert _margin_offset(icon) != before
    host.deleteLater()


def test_optical_margins_settle_and_do_not_loop_on_resize(qapp: QApplication, fake_shift: None):
    host, icon, text = _row(12, 30)
    optical.center_icon_on_text(icon, text)
    host.show()
    qapp.processEvents()
    settled = icon.contentsMargins()
    assert settled.top() == 9 and settled.bottom() == 0

    for width in (200, 260, 220):
        host.resize(width, 80)
        qapp.processEvents()

    assert icon.contentsMargins() == settled
    host.deleteLater()


def test_optical_skips_a_label_with_no_glyph(qapp: QApplication):
    host, icon, text = _row(12, 30)
    icon.setText("")
    optical.center_icon_on_text(icon, text)

    assert _margin_offset(icon) == 0
    host.deleteLater()


def test_optical_centering_twice_leaves_one_filter(qapp: QApplication):
    host, icon, text = _row(12, 30)
    optical.center_icon_on_text(icon, text)
    optical.center_icon_on_text(icon, text)
    qapp.processEvents()

    assert len(icon.findChildren(optical._OpticalCentering)) == 1
    host.deleteLater()


def test_optical_survives_the_text_label_being_deleted(qapp: QApplication):
    host, icon, text = _row(12, 30)
    optical.center_icon_on_text(icon, text)
    text.deleteLater()
    host.show()
    qapp.processEvents()
    font = icon.font()
    font.setPixelSize(20)
    icon.setFont(font)
    host.deleteLater()


@pytest.fixture
def spy(monkeypatch: pytest.MonkeyPatch) -> Callable[[Any], Pairs]:
    def install(module: Any) -> Pairs:
        pairs: Pairs = []
        real = module.center_icon_on_text

        def record(icon: QLabel, text: QLabel) -> None:
            pairs.append((icon, text))
            real(icon, text)

        monkeypatch.setattr(module, "center_icon_on_text", record)
        return pairs

    return install


@pytest.fixture
def host(qapp: QApplication) -> Iterator[QWidget]:
    widget = QWidget()
    yield widget
    widget.deleteLater()


def test_optical_applied_fill_slider(qapp: QApplication, spy: Callable[[Any], Pairs]):
    pairs = spy(fill_slider)
    row = FillSlider("O", "Brightness")

    assert pairs == [(row._icon, row._name)]
    assert row._icon.findChild(optical._OpticalCentering) is not None


def test_optical_applied_power_items(host: QWidget, spy: Callable[[Any], Pairs]):
    pairs = spy(system_controls)
    section = SystemControlsSectionWidget(host, SystemControlsConfig(power_style="list"), lambda: None)

    titles = [text.text() for _, text in pairs if section.isAncestorOf(text)]
    assert titles == ["Lock", "Sign out", "Sleep", "Restart", "Shut down"]
    assert all(icon.property("class") == "icon" and text.property("class") == "label" for icon, text in pairs)


def test_optical_applied_settings_items(host: QWidget, spy: Callable[[Any], Pairs]):
    pairs = spy(system_controls)
    section = SystemControlsSectionWidget(host, SystemControlsConfig(settings_style="list"), lambda: None)

    titles = [text.text() for _, text in pairs if section.isAncestorOf(text)]
    assert titles and titles[-1] == "All settings"
    assert all(icon.parentWidget() is text.parentWidget() for icon, text in pairs)


def test_optical_applied_folders(host: QWidget, spy: Callable[[Any], Pairs]):
    pairs = spy(folders)
    config = FoldersSectionConfig(
        show=True, columns=2, items=[{"title": name, "icon": "F", "path": f"~/{name}"} for name in ("Home", "Docs")]
    )
    FoldersSectionWidget(host, config)

    assert [(icon.text(), text.text()) for icon, text in pairs] == [("F", "Home"), ("F", "Docs")]
