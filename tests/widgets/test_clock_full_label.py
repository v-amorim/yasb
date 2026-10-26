import re
from collections.abc import Iterator
from datetime import datetime, tzinfo

import pytest
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QApplication

from core.validation.widgets.yasb.clock import ClockConfig
from core.widgets.yasb import clock as clock_module
from core.widgets.yasb.clock import ClockWidget


@pytest.fixture
def clock(qapp: QApplication) -> Iterator[ClockWidget]:
    widget = ClockWidget(ClockConfig.model_validate({"label": "{%H:%M}", "label_full": "{%H:%M:%S}", "tooltip": False}))
    yield widget
    widget._shared_state.unregister_widget(widget)
    widget.deleteLater()


def test_digits_use_tabular_figures_under_the_bar_stylesheet(clock: ClockWidget) -> None:
    # Offscreen has no fonts to measure, so this checks the feature; on Windows Inter's 1 and 8 differ by 3 px without it
    clock.setStyleSheet(".label { font-family: 'Inter'; font-size: 14px; font-weight: 700; }")
    clock.update_label()
    label = clock._widgets[0]
    label.ensurePolished()

    assert label.font().featureValue(QFont.Tag("tnum")) == 1


def _text(clock: ClockWidget) -> str:
    return clock._widgets[0].text()


def test_full_bar_label_shows_until_the_bar_peeks(clock: ClockWidget) -> None:
    clock.update_label()
    assert re.fullmatch(r"\d\d:\d\d:\d\d", _text(clock)), "a bar starts in full"

    clock.on_peek_changed(True)
    assert re.fullmatch(r"\d\d:\d\d", _text(clock))

    clock.on_peek_changed(False)
    assert re.fullmatch(r"\d\d:\d\d:\d\d", _text(clock))


def _at(monkeypatch: pytest.MonkeyPatch, moment: datetime) -> None:
    class Frozen(datetime):
        @classmethod
        def now(cls, tz: tzinfo | None = None) -> datetime:  # type: ignore[override]
            return moment

    monkeypatch.setattr(clock_module, "datetime", Frozen)


def test_full_label_never_narrows_while_the_bar_stays_full(clock: ClockWidget, monkeypatch: pytest.MonkeyPatch) -> None:
    label = clock._widgets[0]
    _at(monkeypatch, datetime(2026, 10, 26, 8, 48, 58))
    clock.update_label()
    widest = label.minimumWidth()

    _at(monkeypatch, datetime(2026, 10, 26, 11, 11, 11))
    clock.update_label()

    assert widest > 0 and label.minimumWidth() == widest, "a narrower second must not shift the row"
    clock.on_peek_changed(True)
    assert label.minimumWidth() == 0


def test_without_a_full_label_peeking_changes_nothing(qapp: QApplication) -> None:
    widget = ClockWidget(ClockConfig.model_validate({"label": "{%H:%M}", "tooltip": False}))
    widget.update_label()
    before = widget._widgets[0].text()

    widget.on_peek_changed(False)

    assert widget._widgets[0].text() == before and widget._widgets[0].minimumWidth() == 0
    widget._shared_state.unregister_widget(widget)
    widget.deleteLater()
