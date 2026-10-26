"""A bar pill with an icon and a label balances its sides from the pixels the glyphs draw.

Needs real fonts, so run with QT_QPA_PLATFORM=windows; offscreen fonts have no glyphs and the tests skip.
The pill is built with the user's styles.css, which sets the mode through --ink-balance, and its container is
rendered to read the ink the way the screen would show it. No window is shown on screen.
"""

import re
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from PyQt6.QtCore import QEventLoop, QPoint, Qt, QTimer
from PyQt6.QtGui import QFontDatabase, QImage, QRegion
from PyQt6.QtWidgets import QApplication, QFrame, QHBoxLayout, QLabel, QLayout, QWidget

from core.utils.css_processor import CSSProcessor
from core.utils.ink_balance import EDGES, MASS, balance_delta, column_ink, ink_centre, ink_edges
from core.widgets.base import BaseWidget

STYLES = Path.home() / ".config" / "yasb" / "styles.css"
TOLERANCE = 0.5
ICONS = {"sunny": "\U000f0599", "clear-night": ""}
LABELS = {"short": "8°C", "negative": "-12°C"}
PillBuilder = Callable[[str, str, str], tuple[QWidget, QFrame]]


def _with_mode(sheet: str, mode: str) -> str:
    # The live sheet carries whichever mode the user picked, so a test pins its own.
    return re.sub(r"qproperty-inkbalance:[^;]*;", f'qproperty-inkbalance: "{mode}";', sheet)


def _wait(ms: int = 100) -> None:
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


@pytest.fixture(scope="module")
def sheet(qapp: QApplication) -> str:
    families = set(QFontDatabase.families())
    if not {"Inter", "FiraCode Nerd Font Mono"} <= families:
        pytest.skip("the real fonts are not loaded; run with QT_QPA_PLATFORM=windows")
    if not STYLES.is_file():
        pytest.skip("no styles.css in the user's config")
    css = CSSProcessor(str(STYLES)).process()
    # White text on a transparent container makes the grabbed alpha the glyphs' coverage
    return re.sub(r"(?<![-\w])color:\s*[^;]+;", "color: #FFFFFF;", css)


@pytest.fixture
def pill(sheet: str, qapp: QApplication) -> Iterator[PillBuilder]:
    tops: list[QWidget] = []

    def build(mode: str, icon: str, text: str) -> tuple[QWidget, QFrame]:
        top = QWidget()
        top.setProperty("class", "yasb-bar")
        top.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
        top_layout = QHBoxLayout(top)
        top_layout.setSizeConstraint(QLayout.SizeConstraint.SetFixedSize)
        top_layout.setContentsMargins(0, 0, 0, 0)
        group = QFrame()
        group.setProperty("class", "pill")
        group_layout = QHBoxLayout(group)
        group_layout.setContentsMargins(0, 0, 0, 0)
        widget = BaseWidget(class_name="weather-widget")
        widget._init_container()  # pyright: ignore[reportPrivateUsage]
        widget.build_widget_label(f"<span>{icon}</span> {text}")
        group_layout.addWidget(widget)
        top_layout.addWidget(group)
        top.setStyleSheet(_with_mode(sheet, mode))
        top.show()
        tops.append(top)
        _wait()
        return top, widget._widget_container  # pyright: ignore[reportPrivateUsage]

    yield build
    for top in tops:
        top.close()
        top.deleteLater()


def _ink(container: QFrame) -> tuple[float, float, float]:
    """The drawn ink's left gap, right gap and centre offset from the pill's centre, read from a render of the container."""
    image = QImage(container.size(), QImage.Format.Format_ARGB32)
    image.fill(0)
    container.render(image, QPoint(), QRegion(), QWidget.RenderFlag.DrawChildren)
    bits = image.constBits()
    assert bits is not None
    alpha = bits.asstring(image.sizeInBytes())[3::4]
    width, height = image.width(), image.height()
    edges = ink_edges(column_ink(alpha, width, height))
    centre = ink_centre(alpha, width, height)
    assert edges is not None and centre is not None, "the pill drew nothing"
    return edges[0], width - edges[1], centre - width / 2


def _label_texts(container: QFrame) -> list[str]:
    return [label.text() for label in container.findChildren(QLabel) if not label.isHidden()]


CASES = [
    pytest.param(icon, text, id=f"{icon_name}-{text_name}")
    for icon_name, icon in ICONS.items()
    for text_name, text in LABELS.items()
]


@pytest.mark.parametrize(("icon", "text"), CASES)
def test_ink_balance_edges_gaps_match(pill: PillBuilder, icon: str, text: str):
    _, container = pill(EDGES, icon, text)
    left, right, _ = _ink(container)
    assert abs(left - right) <= TOLERANCE, (left, right, _label_texts(container))


@pytest.mark.parametrize(("icon", "text"), CASES)
def test_ink_balance_mass_centre_on_pill(pill: PillBuilder, icon: str, text: str):
    _, container = pill(MASS, icon, text)
    _, _, offset = _ink(container)
    assert abs(offset) <= TOLERANCE, (offset, _label_texts(container))


def test_ink_balance_off_leaves_the_sides_uneven(pill: PillBuilder):
    gaps = [
        abs(left - right)
        for icon, text in [(i.values[0], i.values[1]) for i in CASES]
        for left, right, _ in [_ink(pill("off", icon, text)[1])]
    ]
    assert max(gaps) > TOLERANCE, gaps


def test_ink_balance_recompute_follows_text_and_font_size(pill: PillBuilder, sheet: str):
    top, container = pill(EDGES, ICONS["clear-night"], LABELS["short"])
    label = next(lbl for lbl in container.findChildren(QLabel) if lbl.property("class") == "label")
    label.setText("-12°C")
    _wait()
    left, right, _ = _ink(container)
    assert abs(left - right) <= TOLERANCE, ("after text", left, right)
    top.setStyleSheet(_with_mode(sheet, EDGES) + ".yasb-bar .pill .widget-container .label { font-size: 18px; }")
    _wait()
    left, right, _ = _ink(container)
    assert abs(left - right) <= TOLERANCE, ("after font", left, right)


def test_ink_balance_recompute_follows_a_mode_switch(pill: PillBuilder):
    _, container = pill(EDGES, ICONS["clear-night"], LABELS["negative"])
    container.setProperty("inkbalance", MASS)
    _wait()
    _, _, offset = _ink(container)
    assert abs(offset) <= TOLERANCE, offset
    container.setProperty("inkbalance", EDGES)
    _wait()
    left, right, _ = _ink(container)
    assert abs(left - right) <= TOLERANCE, (left, right)


def test_ink_math_edges_and_centre_from_an_alpha_plane():
    width, height = 10, 2
    alpha = bytes([0, 0, 255, 255, 0, 0, 128, 0, 0, 0] * height)
    edges = ink_edges(column_ink(alpha, width, height))
    assert edges == (2.0, 6 + 128 / 255)
    assert ink_centre(alpha, width, height) == pytest.approx((2.5 * 255 + 3.5 * 255 + 6.5 * 128) / (255 * 2 + 128))
    assert ink_edges([0.0] * 4) is None


def test_ink_math_delta_grows_the_side_with_the_larger_gap():
    assert balance_delta(EDGES, width=40, left=5, right=33, centre=19) == 2
    assert balance_delta(EDGES, width=40, left=8, right=36, centre=22) == -4
    assert balance_delta(MASS, width=40, left=5, right=30, centre=17) == 6
