# pyright: reportPrivateUsage=false
"""Every gap in the six cards and the bar is a step of 4 or 8 px, beside the settled 12 px card and 10 px surface inset.

A gap is the spacing a layout puts between its items and the margins a layout keeps around them, measured on the
real cards built with the user's styles.css (fixtures shared with test_card_inset). Zero is no gap, so it passes.
"""

import re
from collections.abc import Callable

from PyQt6.QtWidgets import QCalendarWidget, QGridLayout, QLayout, QWidget

from core.widgets.yasb.brightness import BrightnessWidget
from core.widgets.yasb.control_center import ControlCenterWidget
from core.widgets.yasb.volume import VolumeWidget
from tests.widgets.test_card_inset import Card

GAP_STEPS = {0, 4, 8}
INSETS = {10, 12}


def _owner(layout: QLayout) -> str:
    parent = layout.parent()
    while parent is not None and not isinstance(parent, QWidget):
        parent = parent.parent()
    return f"{type(parent).__name__}[{parent.property('class') if parent is not None else ''}]"


def _layouts(card: QWidget) -> list[QLayout]:
    found: list[QLayout] = []
    for layout in card.findChildren(QLayout):
        owner = layout.parentWidget()
        if owner is None or isinstance(owner, QCalendarWidget) or owner.parent() is None and owner is not card:
            continue
        if any(isinstance(p, QCalendarWidget) for p in _ancestors(owner)):
            continue
        found.append(layout)
    if card.layout() is not None:
        found.append(card.layout())
    return found


def _ancestors(widget: QWidget) -> list[QWidget]:
    chain: list[QWidget] = []
    while widget is not None:
        chain.append(widget)
        widget = widget.parentWidget()
    return chain


def _bad_gaps(card: QWidget) -> list[str]:
    bad: list[str] = []
    for layout in _layouts(card):
        steps: dict[str, int] = {}
        if isinstance(layout, QGridLayout):
            if layout.columnCount() > 1:
                steps["h-spacing"] = layout.horizontalSpacing()
            if layout.rowCount() > 1:
                steps["v-spacing"] = layout.verticalSpacing()
        elif layout.count() > 1:
            steps["spacing"] = layout.spacing()
        margins = layout.contentsMargins()
        for side, value in (
            ("left", margins.left()),
            ("top", margins.top()),
            ("right", margins.right()),
            ("bottom", margins.bottom()),
        ):
            if value not in GAP_STEPS | INSETS:
                steps[f"margin-{side}"] = value
        bad.extend(
            f"{_owner(layout)} {type(layout).__name__} {name}={value}"
            for name, value in steps.items()
            if value not in (GAP_STEPS if "spacing" in name else GAP_STEPS | INSETS)
        )
    return bad


def _assert_gaps(card: QWidget) -> None:
    bad = sorted(set(_bad_gaps(card)))
    assert not bad, "\n".join(bad)


def test_gap_step_calendar(calendar: Card):
    _assert_gaps(calendar[0])


def test_gap_step_weather_rows(make_weather: Callable[[str], Card]):
    _assert_gaps(make_weather("rows")[0])


def test_gap_step_weather_chart(make_weather: Callable[[str], Card]):
    _assert_gaps(make_weather("chart")[0])


def test_gap_step_tray(tray: Card):
    _assert_gaps(tray[0])


def test_gap_step_brightness(brightness_card: BrightnessWidget):
    _assert_gaps(brightness_card.dialog)


def test_gap_step_volume(volume_card: VolumeWidget):
    _assert_gaps(volume_card.dialog)


def test_gap_step_control_center(control_center: ControlCenterWidget):
    _assert_gaps(control_center.dialog)


SURFACE_SELECTORS = (".device", ".toggle-devices", ".app-volume", ".plan-name", ".section.media", ".context-menu")
CARD_PREFIXES = (
    ".calendar",
    ".weather-card",
    ".systray-popup",
    ".brightness-menu",
    ".audio-menu",
    ".control-center-menu",
)


def test_gap_step_stylesheet_margins_and_paddings(sheet: str):
    """Section, rule, list and label margins and paddings in the cards; a control's own text padding is its surface."""
    bad: list[str] = []
    uncommented = re.sub(r"/\*.*?\*/", "", sheet, flags=re.DOTALL)
    for selector_text, body in re.findall(r"([^{}]+)\{([^}]*)\}", uncommented):
        selector = selector_text.strip()
        if not selector.startswith(CARD_PREFIXES) or any(name in selector for name in SURFACE_SELECTORS):
            continue
        for prop, value in re.findall(r"((?:margin|padding)[a-z-]*)\s*:\s*([^;]+);", body):
            bad.extend(
                f"{selector.splitlines()[0]} {prop}={px}"
                for px in re.findall(r"(-?\d+)px", value)
                if int(px) not in GAP_STEPS | INSETS
            )
    assert not bad, "\n".join(bad)
